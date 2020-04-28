# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2019 Recidiviz, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# =============================================================================

"""Runs the incarceration calculation pipeline. See recidiviz/tools/run_calculation_pipelines.py for details on how to
run.
"""

from __future__ import absolute_import

import argparse
import logging
import sys

from typing import Any, Dict, List, Tuple, Set
import datetime

from apache_beam.pvalue import AsDict
from more_itertools import one

import apache_beam as beam
from apache_beam.options.pipeline_options import SetupOptions
from apache_beam.typehints import with_input_types, with_output_types

from recidiviz.calculator.pipeline.recidivism import identifier
from recidiviz.calculator.pipeline.recidivism import calculator
from recidiviz.calculator.pipeline.recidivism.release_event import ReleaseEvent
from recidiviz.calculator.pipeline.recidivism.metrics import \
    ReincarcerationRecidivismRateMetric, ReincarcerationRecidivismCountMetric, \
    ReincarcerationRecidivismMetric
from recidiviz.calculator.pipeline.recidivism.metrics import ReincarcerationRecidivismMetricType
from recidiviz.calculator.pipeline.utils.beam_utils import ConvertDictToKVTuple
from recidiviz.calculator.pipeline.utils.entity_hydration_utils import \
    SetViolationResponseOnIncarcerationPeriod, SetViolationOnViolationsResponse
from recidiviz.calculator.pipeline.utils.execution_utils import get_job_id
from recidiviz.calculator.pipeline.utils.extractor_utils import BuildRootEntity
from recidiviz.calculator.pipeline.utils.metric_utils import \
    json_serializable_metric_key
from recidiviz.calculator.pipeline.utils.pipeline_args_utils import add_shared_pipeline_arguments, \
    get_apache_beam_pipeline_options_from_args
from recidiviz.persistence.entity.state import entities
from recidiviz.persistence.database.schema.state import schema
from recidiviz.utils import environment

# Cached job_id value
_job_id = None


def job_id(pipeline_options: Dict[str, str]) -> str:
    global _job_id
    if not _job_id:
        _job_id = get_job_id(pipeline_options)
    return _job_id


@environment.test_only
def clear_job_id():
    global _job_id
    _job_id = None


@with_input_types(beam.typehints.Tuple[entities.StatePerson,
                                       List[ReleaseEvent]])
@with_output_types(ReincarcerationRecidivismMetric)
class GetRecidivismMetrics(beam.PTransform):
    """Transforms a StatePerson and ReleaseEvents into RecidivismMetrics."""

    def __init__(self, pipeline_options: Dict[str, str],
                 metric_types: Set[str]):
        super(GetRecidivismMetrics, self).__init__()
        self._pipeline_options = pipeline_options

        self.metric_inclusions: Dict[ReincarcerationRecidivismMetricType, bool] = {}

        for metric_option in ReincarcerationRecidivismMetricType:
            if metric_option.value in metric_types or 'ALL' in metric_types:
                self.metric_inclusions[metric_option] = True
                logging.info("Producing %s metrics", metric_option.value)
            else:
                self.metric_inclusions[metric_option] = False

    def expand(self, input_or_inputs):
        # Calculate recidivism metric combinations from a StatePerson and their
        # ReleaseEvents
        recidivism_metric_combinations = (
            input_or_inputs
            | 'Map to metric combinations' >>
            beam.ParDo(CalculateRecidivismMetricCombinations(), self.metric_inclusions))

        # Produce ReincarcerationRecidivismMetrics for all metrics
        metrics = (recidivism_metric_combinations |
                   'Produce person-level ReincarcerationRecidivismMetrics' >>
                   beam.ParDo(ProduceReincarcerationRecidivismMetric(), **self._pipeline_options))

        # Return ReincarcerationRecidivismMetric objects
        return metrics


@with_input_types(beam.typehints.Tuple[int, Dict[str, Any]],
                  beam.typehints.Optional[Dict[Any, Tuple[Any, Dict[str, Any]]]]
                  )
@with_output_types(beam.typehints.Tuple[entities.StatePerson,
                                        Dict[int, List[ReleaseEvent]]])
class ClassifyReleaseEvents(beam.DoFn):
    """Classifies releases as either recidivism or non-recidivism events."""

    # pylint: disable=arguments-differ
    def process(self, element, person_id_to_county):
        """Identifies instances of recidivism and non-recidivism.

        Sends the identifier the StateIncarcerationPeriods for a given
        StatePerson, which returns a list of ReleaseEvents for each year the
        individual was released from incarceration.

        Args:
            element: Tuple containing person_id and a dictionary with
                a StatePerson and a list of StateIncarcerationPeriods

        Yields:
            Tuple containing the StatePerson and a collection
            of ReleaseEvents.
        """
        _, person_incarceration_periods = element

        # Get the StateIncarcerationPeriods as a list
        incarceration_periods = \
            list(person_incarceration_periods['incarceration_periods'])

        # Get the StatePerson
        person = one(person_incarceration_periods['person'])

        # Get the person's county of residence, if present
        person_id_to_county_fields = person_id_to_county.get(
            person.person_id, None)
        county_of_residence = \
            person_id_to_county_fields.get('county_of_residence', None) \
            if person_id_to_county_fields else None

        release_events_by_cohort_year = \
            identifier.find_release_events_by_cohort_year(
                incarceration_periods, county_of_residence)

        if not release_events_by_cohort_year:
            logging.info("No valid release events identified for person with"
                         "id: %d. Excluding them from the "
                         "calculations.", person.person_id)
        else:
            yield (person, release_events_by_cohort_year)

    def to_runner_api_parameter(self, _):
        pass  # Passing unused abstract method.


@with_input_types(beam.typehints.Tuple[entities.StatePerson, Dict[int, List[ReleaseEvent]]],
                  beam.typehints.Dict[ReincarcerationRecidivismMetricType, bool])
@with_output_types(beam.typehints.Tuple[Dict[str, Any], Any])
class CalculateRecidivismMetricCombinations(beam.DoFn):
    """Calculates recidivism metric combinations."""

    #pylint: disable=arguments-differ
    def process(self, element, metric_inclusions):
        """Produces various recidivism metric combinations.

        Sends the calculator the StatePerson entity and their corresponding ReleaseEvents for mapping all recidivism
        combinations.

        Args:
            element: Tuple containing a StatePerson and their ReleaseEvents
            metric_inclusions: A dictionary where the keys are each ReincarcerationRecidivismMetricType, and the values
                are boolean flags for whether or not to include that metric type in the calculations
        Yields:
            Each recidivism metric combination.
        """
        person, release_events = element

        # Calculate recidivism metric combinations for this person and events
        metric_combinations = calculator.map_recidivism_combinations(person, release_events, metric_inclusions)

        # Return each of the recidivism metric combinations
        for metric_combination in metric_combinations:
            yield metric_combination

    def to_runner_api_parameter(self, _):
        pass  # Passing unused abstract method.


@with_input_types(beam.typehints.Tuple[Dict[str, Any], Any],
                  **{'runner': str,
                     'project': str,
                     'job_name': str,
                     'region': str,
                     'job_timestamp': str}
                  )
@with_output_types(ReincarcerationRecidivismMetric)
class ProduceReincarcerationRecidivismMetric(beam.DoFn):
    """Produces ReincarcerationRecidivismMetrics."""

    def process(self, element, *args, **kwargs):
        """Converts a recidivism metric key into a ReincarcerationRecidivismMetric.

        The pipeline options are sent in as the **kwargs so that the
        job_id(pipeline_options) function can be called to retrieve the job_id.

        Args:
            element: A tuple containing string representation of the metric_key
                for a given recidivism metric, and the value of that metric.
            **kwargs: This should be a dictionary with values for the
                following keys:
                    - runner: Either 'DirectRunner' or 'DataflowRunner'
                    - project: GCP project ID
                    - job_name: Name of the pipeline job
                    - region: Region where the pipeline job is running
                    - job_timestamp: Timestamp for the current job, to be used
                        if the job is running locally.

        Yields:
            The ReincarcerationRecidivismMetric.
        """
        pipeline_options = kwargs

        pipeline_job_id = job_id(pipeline_options)

        (dict_metric_key, value) = element

        if value is None:
            # Due to how the pipeline arrives at this function, this should be
            # impossible.
            raise ValueError("No value associated with this metric key.")

        metric_type = dict_metric_key.get('metric_type')

        if metric_type == ReincarcerationRecidivismMetricType.COUNT:
            if dict_metric_key.get('person_id') is not None:
                # The count value for all person-level metrics should be 1
                value = 1

            # For count metrics, the value is the number of returns
            dict_metric_key['returns'] = value

            recidivism_metric = ReincarcerationRecidivismCountMetric.build_from_metric_key_group(
                dict_metric_key, pipeline_job_id)
        elif metric_type == ReincarcerationRecidivismMetricType.RATE:
            dict_metric_key['total_releases'] = 1
            dict_metric_key['recidivated_releases'] = value
            dict_metric_key['recidivism_rate'] = value

            recidivism_metric = ReincarcerationRecidivismRateMetric.build_from_metric_key_group(
                dict_metric_key, pipeline_job_id)
        else:
            logging.error("Unexpected metric of type: %s", dict_metric_key.get('metric_type'))
            return

        if recidivism_metric:
            yield recidivism_metric

    def to_runner_api_parameter(self, _):
        pass  # Passing unused abstract method.


@with_input_types(ReincarcerationRecidivismMetric)
@with_output_types(beam.typehints.Dict[str, Any])
class RecidivismMetricWritableDict(beam.DoFn):
    """Builds a dictionary in the format necessary to write the output to
    BigQuery."""

    def process(self, element, *args, **kwargs):
        """The beam.io.WriteToBigQuery transform requires elements to be in
        dictionary form, where the values are in formats as required by BigQuery
        I/O connector.

        For a list of required formats, see the "Data types" section of:
            https://beam.apache.org/documentation/io/built-in/google-bigquery/

        Args:
            element: A ReincarcerationRecidivismMetric

        Yields:
            A dictionary representation of the ReincarcerationRecidivismMetric
                in the format Dict[str, Any] so that it can be written to
                BigQuery using beam.io.WriteToBigQuery.
        """
        element_dict = json_serializable_metric_key(element.__dict__)

        if isinstance(element, ReincarcerationRecidivismRateMetric):
            yield beam.pvalue.TaggedOutput('rates', element_dict)
        elif isinstance(element, ReincarcerationRecidivismCountMetric):
            yield beam.pvalue.TaggedOutput('counts', element_dict)

    def to_runner_api_parameter(self, _):
        pass  # Passing unused abstract method.


def parse_arguments(argv):
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser()

    # Parse arguments
    add_shared_pipeline_arguments(parser)

    parser.add_argument('--metric_types',
                        dest='metric_types',
                        type=str,
                        nargs='+',
                        choices=[
                            'ALL',
                            ReincarcerationRecidivismMetricType.COUNT.value,
                            ReincarcerationRecidivismMetricType.RATE.value
                        ],
                        help='A list of the types of metric to calculate.',
                        default={'ALL'})
    return parser.parse_known_args(argv)


def run(argv):
    """Runs the recidivism calculation pipeline."""

    # Workaround to load SQLAlchemy objects at start of pipeline. This is
    # necessary because the BuildRootEntity function tries to access attributes
    # of relationship properties on the SQLAlchemy room_schema_class before they
    # have been loaded. However, if *any* SQLAlchemy objects have been
    # instantiated, then the relationship properties are loaded and their
    # attributes can be successfully accessed.
    _ = schema.StatePerson()

    # Parse command-line arguments
    known_args, remaining_args = parse_arguments(argv)

    pipeline_options = get_apache_beam_pipeline_options_from_args(remaining_args)
    pipeline_options.view_as(SetupOptions).save_main_session = True

    # Get pipeline job details
    all_pipeline_options = pipeline_options.get_all_options()

    query_dataset = all_pipeline_options['project'] + '.' + known_args.input
    reference_dataset = all_pipeline_options['project'] + '.' + \
                        known_args.reference_input

    person_id_filter_set = set(known_args.person_filter_ids) if known_args.person_filter_ids else None
    state_code = known_args.state_code

    with beam.Pipeline(options=pipeline_options) as p:
        # Get StatePersons
        persons = (p
                   | 'Load Persons' >>
                   BuildRootEntity(dataset=query_dataset, root_entity_class=entities.StatePerson,
                                   unifying_id_field=entities.StatePerson.get_class_id_name(),
                                   build_related_entities=True, unifying_id_field_filter_set=person_id_filter_set))

        # Get StateIncarcerationPeriods
        incarceration_periods = (p
                                 | 'Load IncarcerationPeriods' >>
                                 BuildRootEntity(dataset=query_dataset,
                                                 root_entity_class=entities.StateIncarcerationPeriod,
                                                 unifying_id_field=entities.StatePerson.get_class_id_name(),
                                                 build_related_entities=True,
                                                 unifying_id_field_filter_set=person_id_filter_set,
                                                 state_code=state_code
                                                 ))

        # Get StateSupervisionViolations
        supervision_violations = \
            (p
             | 'Load SupervisionViolations' >>
             BuildRootEntity(dataset=query_dataset, root_entity_class=entities.StateSupervisionViolation,
                             unifying_id_field=entities.StatePerson.get_class_id_name(), build_related_entities=True,
                             unifying_id_field_filter_set=person_id_filter_set,
                             state_code=state_code
                             ))

        # TODO(2769): Don't bring this in as a root entity
        # Get StateSupervisionViolationResponses
        supervision_violation_responses = \
            (p
             | 'Load SupervisionViolationResponses' >>
             BuildRootEntity(dataset=query_dataset, root_entity_class=entities.StateSupervisionViolationResponse,
                             unifying_id_field=entities.StatePerson.get_class_id_name(), build_related_entities=True,
                             unifying_id_field_filter_set=person_id_filter_set,
                             state_code=state_code
                             ))

        # Group StateSupervisionViolationResponses and
        # StateSupervisionViolations by person_id
        supervision_violations_and_responses = (
            {'violations': supervision_violations,
             'violation_responses': supervision_violation_responses
             } | 'Group StateSupervisionViolationResponses to '
                 'StateSupervisionViolations' >>
            beam.CoGroupByKey()
        )

        # Set the fully hydrated StateSupervisionViolation entities on
        # the corresponding StateSupervisionViolationResponses
        violation_responses_with_hydrated_violations = (
            supervision_violations_and_responses
            | 'Set hydrated StateSupervisionViolations on '
              'the StateSupervisionViolationResponses' >>
            beam.ParDo(SetViolationOnViolationsResponse()))

        # Group StateIncarcerationPeriods and StateSupervisionViolationResponses
        # by person_id
        incarceration_periods_and_violation_responses = (
            {'incarceration_periods': incarceration_periods,
             'violation_responses':
                 violation_responses_with_hydrated_violations}
            | 'Group StateIncarcerationPeriods to '
              'StateSupervisionViolationResponses' >>
            beam.CoGroupByKey()
        )

        # Set the fully hydrated StateSupervisionViolationResponse entities on
        # the corresponding StateIncarcerationPeriods
        incarceration_periods_with_source_violations = (
            incarceration_periods_and_violation_responses
            | 'Set hydrated StateSupervisionViolationResponses on '
            'the StateIncarcerationPeriods' >>
            beam.ParDo(SetViolationResponseOnIncarcerationPeriod()))

        # Group each StatePerson with their StateIncarcerationPeriods
        person_and_incarceration_periods = (
            {'person': persons,
             'incarceration_periods':
                 incarceration_periods_with_source_violations}
            | 'Group StatePerson to StateIncarcerationPeriods' >>
            beam.CoGroupByKey()
        )

        # Bring in the table that associates people and their county of
        # residence
        person_id_to_county_query = \
            f"SELECT * FROM " \
            f"`{reference_dataset}.persons_to_recent_county_of_residence`"

        person_id_to_county_kv = (
            p
            | "Read person_id to county associations from BigQuery" >>
            beam.io.Read(beam.io.BigQuerySource(
                query=person_id_to_county_query,
                use_standard_sql=True))
            | "Convert person_id to county association table to KV" >>
            beam.ParDo(ConvertDictToKVTuple(), 'person_id')
        )

        # Identify ReleaseEvents events from the StatePerson's
        # StateIncarcerationPeriods
        person_events = (
            person_and_incarceration_periods
            | "ClassifyReleaseEvents" >>
            beam.ParDo(ClassifyReleaseEvents(), AsDict(person_id_to_county_kv))
        )

        # Get pipeline job details for accessing job_id
        all_pipeline_options = pipeline_options.get_all_options()

        # Add timestamp for local jobs
        job_timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H_%M_%S.%f')
        all_pipeline_options['job_timestamp'] = job_timestamp

        # Get the type of metric to calculate
        metric_types = set(known_args.metric_types)

        # Get recidivism metrics
        recidivism_metrics = (person_events
                              | 'Get Recidivism Metrics' >>
                              GetRecidivismMetrics(
                                  pipeline_options=all_pipeline_options,
                                  metric_types=metric_types))

        if person_id_filter_set:
            logging.warning("Non-empty person filter set - returning before writing metrics.")
            return

        # Convert the metrics into a format that's writable to BQ
        writable_metrics = (recidivism_metrics
                            | 'Convert to dict to be written to BQ' >>
                            beam.ParDo(
                                RecidivismMetricWritableDict()).with_outputs('rates', 'counts'))

        # Write the recidivism metrics to the output tables in BigQuery
        rates_table = known_args.output + '.recidivism_rate_metrics'
        counts_table = known_args.output + '.recidivism_count_metrics'

        _ = (writable_metrics.rates
             | f"Write rate metrics to BQ table: {rates_table}" >>
             beam.io.WriteToBigQuery(
                 table=rates_table,
                 create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                 write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
             ))

        _ = (writable_metrics.counts
             | f"Write count metrics to BQ table: {counts_table}" >>
             beam.io.WriteToBigQuery(
                 table=counts_table,
                 create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                 write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
             ))


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    run(sys.argv)
