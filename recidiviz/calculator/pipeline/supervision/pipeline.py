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
import argparse
import datetime
import logging
from typing import Dict, Any, List, Tuple, Set, Optional

import apache_beam as beam
from apache_beam.options.pipeline_options import SetupOptions, PipelineOptions
from apache_beam.pvalue import AsDict
from apache_beam.typehints import with_input_types, with_output_types

from recidiviz.calculator.calculation_data_storage_config import DATAFLOW_METRICS_TO_TABLES
from recidiviz.calculator.pipeline.supervision import identifier, calculator
from recidiviz.calculator.pipeline.supervision.metrics import \
    SupervisionMetric, SupervisionPopulationMetric, \
    SupervisionRevocationMetric, SupervisionSuccessMetric, \
    TerminatedSupervisionAssessmentScoreChangeMetric, \
    SupervisionRevocationAnalysisMetric, SupervisionRevocationViolationTypeAnalysisMetric, \
    SuccessfulSupervisionSentenceDaysServedMetric, SupervisionCaseComplianceMetric
from recidiviz.calculator.pipeline.supervision.metrics import \
    SupervisionMetricType
from recidiviz.calculator.pipeline.supervision.supervision_time_bucket import \
    SupervisionTimeBucket
from recidiviz.calculator.pipeline.utils.beam_utils import ConvertDictToKVTuple
from recidiviz.calculator.pipeline.utils.entity_hydration_utils import \
    SetViolationResponseOnIncarcerationPeriod, SetViolationOnViolationsResponse, ConvertSentencesToStateSpecificType
from recidiviz.calculator.pipeline.utils.execution_utils import get_job_id, person_and_kwargs_for_identifier
from recidiviz.calculator.pipeline.utils.extractor_utils import BuildRootEntity
from recidiviz.calculator.pipeline.utils.metric_utils import \
    json_serializable_metric_key
from recidiviz.calculator.pipeline.utils.pipeline_args_utils import add_shared_pipeline_arguments
from recidiviz.persistence.database.schema.state import schema
from recidiviz.persistence.entity.state import entities
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


@with_input_types(beam.typehints.Tuple[entities.StatePerson, List[SupervisionTimeBucket]])
@with_output_types(SupervisionMetric)
class GetSupervisionMetrics(beam.PTransform):
    """Transforms a StatePerson and their SupervisionTimeBuckets into SupervisionMetrics."""
    def __init__(self, pipeline_options: Dict[str, str],
                 metric_types: Set[str],
                 calculation_month_count: int,
                 calculation_end_month: Optional[str] = None):
        super(GetSupervisionMetrics, self).__init__()
        self._pipeline_options = pipeline_options
        self._calculation_end_month = calculation_end_month
        self._calculation_month_count = calculation_month_count

        month_count_string = str(calculation_month_count) if calculation_month_count != -1 else 'all'
        end_month_string = calculation_end_month if calculation_end_month else 'the current month'
        logging.info("Producing metric output for %s month(s) up to %s", month_count_string, end_month_string)

        self._metric_inclusions: Dict[SupervisionMetricType, bool] = {}

        for metric_option in SupervisionMetricType:
            if metric_option.value in metric_types or 'ALL' in metric_types:
                self._metric_inclusions[metric_option] = True
                logging.info("Producing %s metrics", metric_option.value)
            else:
                self._metric_inclusions[metric_option] = False

    def expand(self, input_or_inputs):
        # Calculate supervision metric combinations from a StatePerson and their SupervisionTimeBuckets
        supervision_metric_combinations = (
            input_or_inputs | 'Map to metric combinations' >>
            beam.ParDo(CalculateSupervisionMetricCombinations(),
                       self._calculation_end_month, self._calculation_month_count, self._metric_inclusions))

        # Produce SupervisionMetrics
        supervision_metrics = (supervision_metric_combinations |
                               'Produce SupervisionMetrics' >>
                               beam.ParDo(ProduceSupervisionMetrics(), **self._pipeline_options))

        # Return SupervisionMetrics objects
        return supervision_metrics


@with_input_types(beam.typehints.Tuple[int, Dict[str, Any]],
                  beam.typehints.Optional[Dict[Any, Tuple[Any, Dict[str, Any]]]],
                  beam.typehints.Optional[Dict[Any, Tuple[Any, Dict[str, Any]]]])
@with_output_types(beam.typehints.Tuple[entities.StatePerson, List[SupervisionTimeBucket]])
class ClassifySupervisionTimeBuckets(beam.DoFn):
    """Classifies time on supervision according to multiple types of measurement."""

    #pylint: disable=arguments-differ
    def process(self, element, ssvr_agent_associations, supervision_period_to_agent_associations):
        """Identifies various events related to supervision relevant to calculations."""
        _, person_entities = element

        person, kwargs = person_and_kwargs_for_identifier(person_entities)

        # Add these arguments to the keyword args for the identifier
        kwargs['ssvr_agent_associations'] = ssvr_agent_associations
        kwargs['supervision_period_to_agent_associations'] = supervision_period_to_agent_associations

        # Find the SupervisionTimeBuckets from the supervision and incarceration
        # periods
        supervision_time_buckets = identifier.find_supervision_time_buckets(**kwargs)

        if not supervision_time_buckets:
            logging.info("No valid supervision time buckets for person with id: %d. Excluding them from the "
                         "calculations.", person.person_id)
        else:
            yield person, supervision_time_buckets

    def to_runner_api_parameter(self, _):
        pass  # Passing unused abstract method.


@with_input_types(beam.typehints.Tuple[entities.StatePerson, List[SupervisionTimeBucket]],
                  beam.typehints.Optional[str],
                  beam.typehints.Optional[int],
                  beam.typehints.Dict[SupervisionMetricType, bool])
@with_output_types(beam.typehints.Tuple[Dict[str, Any], Any])
class CalculateSupervisionMetricCombinations(beam.DoFn):
    """Calculates supervision metric combinations."""

    #pylint: disable=arguments-differ
    def process(self, element, calculation_end_month, calculation_month_count, metric_inclusions):
        """Produces various supervision metric combinations.

        Sends the calculator the StatePerson entity and their corresponding SupervisionTimeBuckets for mapping all
        supervision combinations.

        Args:
            element: Tuple containing a StatePerson and their SupervisionTimeBuckets
            calculation_end_month: The year and month of the last month for which metrics should be calculated.
            calculation_month_count: The number of months to limit the monthly calculation output to.
            metric_inclusions: A dictionary where the keys are each SupervisionMetricType, and the values are boolean
                values for whether or not to include that metric type in the calculations
        Yields:
            Each supervision metric combination.
        """
        person, supervision_time_buckets = element

        # Calculate supervision metric combinations for this person and their supervision time buckets
        metric_combinations = calculator.map_supervision_combinations(person,
                                                                      supervision_time_buckets,
                                                                      metric_inclusions,
                                                                      calculation_end_month,
                                                                      calculation_month_count)

        # Return each of the supervision metric combinations
        for metric_combination in metric_combinations:
            yield metric_combination

    def to_runner_api_parameter(self, _):
        pass  # Passing unused abstract method.


@with_input_types(beam.typehints.Tuple[Dict[str, Any], Any],
                  **{'runner': str,
                     'project': str,
                     'job_name': str,
                     'region': str,
                     'job_timestamp': str})
@with_output_types(SupervisionMetric)
class ProduceSupervisionMetrics(beam.DoFn):
    """Produces SupervisionMetrics ready for persistence."""
    def process(self, element, *args, **kwargs):
        pipeline_options = kwargs

        pipeline_job_id = job_id(pipeline_options)

        (dict_metric_key, value) = element

        if value is None:
            # Due to how the pipeline arrives at this function, this should be impossible.
            raise ValueError("No value associated with this metric key.")

        # Convert JSON string to dictionary
        metric_type = dict_metric_key.get('metric_type')

        if metric_type == SupervisionMetricType.ASSESSMENT_CHANGE:
            dict_metric_key['count'] = 1
            dict_metric_key['average_score_change'] = value

            supervision_metric = TerminatedSupervisionAssessmentScoreChangeMetric.build_from_metric_key_group(
                dict_metric_key, pipeline_job_id
            )
        elif metric_type == SupervisionMetricType.POPULATION:
            dict_metric_key['count'] = 1

            supervision_metric = SupervisionPopulationMetric.build_from_metric_key_group(
                dict_metric_key, pipeline_job_id)
        elif metric_type == SupervisionMetricType.REVOCATION:
            dict_metric_key['count'] = 1

            supervision_metric = SupervisionRevocationMetric.build_from_metric_key_group(
                dict_metric_key, pipeline_job_id)
        elif metric_type == SupervisionMetricType.REVOCATION_ANALYSIS:
            dict_metric_key['count'] = 1

            supervision_metric = SupervisionRevocationAnalysisMetric.build_from_metric_key_group(
                dict_metric_key, pipeline_job_id
            )
        elif metric_type == SupervisionMetricType.REVOCATION_VIOLATION_TYPE_ANALYSIS:
            dict_metric_key['count'] = value

            supervision_metric = SupervisionRevocationViolationTypeAnalysisMetric.build_from_metric_key_group(
                dict_metric_key, pipeline_job_id
            )
        elif metric_type == SupervisionMetricType.SUCCESS:
            dict_metric_key['successful_completion_count'] = value
            dict_metric_key['projected_completion_count'] = 1

            supervision_metric = SupervisionSuccessMetric.build_from_metric_key_group(
                dict_metric_key, pipeline_job_id)
        elif metric_type == SupervisionMetricType.SUCCESSFUL_SENTENCE_DAYS_SERVED:
            dict_metric_key['successful_completion_count'] = 1
            dict_metric_key['average_days_served'] = value

            supervision_metric = SuccessfulSupervisionSentenceDaysServedMetric.build_from_metric_key_group(
                dict_metric_key, pipeline_job_id
            )
        elif metric_type == SupervisionMetricType.COMPLIANCE:
            dict_metric_key['count'] = 1

            supervision_metric = SupervisionCaseComplianceMetric.build_from_metric_key_group(
                dict_metric_key, pipeline_job_id)
        else:
            logging.error("Unexpected metric of type: %s",
                          dict_metric_key.get('metric_type'))
            return

        if supervision_metric:
            yield supervision_metric

    def to_runner_api_parameter(self, _):
        pass  # Passing unused abstract method.


@with_input_types(SupervisionMetric)
@with_output_types(beam.typehints.Dict[str, Any])
class SupervisionMetricWritableDict(beam.DoFn):
    """Builds a dictionary in the format necessary to write the output to BigQuery."""

    def process(self, element, *args, **kwargs):
        """The beam.io.WriteToBigQuery transform requires elements to be in dictionary form, where the values are in
        formats as required by BigQuery I/O connector.

        For a list of required formats, see the "Data types" section of:
            https://beam.apache.org/documentation/io/built-in/google-bigquery/

        Args:
            element: A SupervisionMetric

        Yields:
            A dictionary representation of the SupervisionMetric in the format Dict[str, Any] so that it can be written
                to BigQuery using beam.io.WriteToBigQuery.
        """
        element_dict = json_serializable_metric_key(element.__dict__)

        if isinstance(element, SupervisionCaseComplianceMetric):
            yield beam.pvalue.TaggedOutput('compliances', element_dict)
        elif isinstance(element, SupervisionPopulationMetric):
            yield beam.pvalue.TaggedOutput('populations', element_dict)
        elif isinstance(element, SupervisionRevocationAnalysisMetric):
            yield beam.pvalue.TaggedOutput('revocation_analyses', element_dict)
        elif isinstance(element, SupervisionRevocationViolationTypeAnalysisMetric):
            yield beam.pvalue.TaggedOutput('revocation_violation_type_analyses', element_dict)
        elif isinstance(element, SupervisionRevocationMetric) \
                and not isinstance(element, SupervisionRevocationAnalysisMetric):
            yield beam.pvalue.TaggedOutput('revocations', element_dict)
        elif isinstance(element, SupervisionSuccessMetric):
            yield beam.pvalue.TaggedOutput('successes', element_dict)
        elif isinstance(element, SuccessfulSupervisionSentenceDaysServedMetric):
            yield beam.pvalue.TaggedOutput('successful_sentence_lengths', element_dict)
        elif isinstance(element, TerminatedSupervisionAssessmentScoreChangeMetric):
            yield beam.pvalue.TaggedOutput('assessment_changes', element_dict)

    def to_runner_api_parameter(self, _):
        pass  # Passing unused abstract method.


def get_arg_parser() -> argparse.ArgumentParser:
    """Returns the parser for the command-line arguments for this pipeline."""
    parser = argparse.ArgumentParser()

    # Parse arguments
    add_shared_pipeline_arguments(parser, include_calculation_limit_args=True)

    metric_type_options: List[str] = [
        metric_type.value for metric_type in SupervisionMetricType
    ]

    metric_type_options.append('ALL')

    parser.add_argument('--metric_types',
                        dest='metric_types',
                        type=str,
                        nargs='+',
                        choices=metric_type_options,
                        help='A list of the types of metric to calculate.',
                        default={'ALL'})

    return parser


def run(apache_beam_pipeline_options: PipelineOptions,
        data_input: str,
        reference_input: str,
        output: str,
        calculation_month_count: int,
        metric_types: List[str],
        state_code: Optional[str],
        calculation_end_month: Optional[str],
        person_filter_ids: Optional[List[int]]):
    """Runs the supervision calculation pipeline."""

    # Workaround to load SQLAlchemy objects at start of pipeline. This is necessary because the BuildRootEntity
    # function tries to access attributes of relationship properties on the SQLAlchemy room_schema_class before they
    # have been loaded. However, if *any* SQLAlchemy objects have been instantiated, then the relationship properties
    # are loaded and their attributes can be successfully accessed.
    _ = schema.StatePerson()

    apache_beam_pipeline_options.view_as(SetupOptions).save_main_session = True

    # Get pipeline job details
    all_pipeline_options = apache_beam_pipeline_options.get_all_options()

    input_dataset = all_pipeline_options['project'] + '.' + data_input
    reference_dataset = all_pipeline_options['project'] + '.' + reference_input

    person_id_filter_set = set(person_filter_ids) if person_filter_ids else None

    with beam.Pipeline(options=apache_beam_pipeline_options) as p:
        # Get StatePersons
        persons = (p | 'Load Persons' >> BuildRootEntity(dataset=input_dataset,
                                                         root_entity_class=entities.StatePerson,
                                                         unifying_id_field=entities.StatePerson.get_class_id_name(),
                                                         build_related_entities=True,
                                                         unifying_id_field_filter_set=person_id_filter_set,
                                                         state_code=state_code))

        # Get StateIncarcerationPeriods
        incarceration_periods = (p | 'Load IncarcerationPeriods' >> BuildRootEntity(
            dataset=input_dataset,
            root_entity_class=entities.StateIncarcerationPeriod,
            unifying_id_field=entities.StatePerson.get_class_id_name(),
            build_related_entities=True,
            unifying_id_field_filter_set=person_id_filter_set,
            state_code=state_code
        ))

        # Get StateSupervisionViolations
        supervision_violations = (p | 'Load SupervisionViolations' >> BuildRootEntity(
            dataset=input_dataset,
            root_entity_class=entities.StateSupervisionViolation,
            unifying_id_field=entities.StatePerson.get_class_id_name(),
            build_related_entities=True,
            unifying_id_field_filter_set=person_id_filter_set,
            state_code=state_code
        ))

        # TODO(2769): Don't bring this in as a root entity
        # Get StateSupervisionViolationResponses
        supervision_violation_responses = (p | 'Load SupervisionViolationResponses' >> BuildRootEntity(
            dataset=input_dataset,
            root_entity_class=entities.StateSupervisionViolationResponse,
            unifying_id_field=entities.StatePerson.get_class_id_name(),
            build_related_entities=True,
            unifying_id_field_filter_set=person_id_filter_set,
            state_code=state_code
        ))

        # Get StateSupervisionSentences
        supervision_sentences = (p | 'Load SupervisionSentences' >> BuildRootEntity(
            dataset=input_dataset,
            root_entity_class=entities.StateSupervisionSentence,
            unifying_id_field=entities.StatePerson.get_class_id_name(),
            build_related_entities=True,
            unifying_id_field_filter_set=person_id_filter_set,
            state_code=state_code
        ))

        # Get StateIncarcerationSentences
        incarceration_sentences = (p | 'Load IncarcerationSentences' >> BuildRootEntity(
            dataset=input_dataset,
            root_entity_class=entities.StateIncarcerationSentence,
            unifying_id_field=entities.StatePerson.get_class_id_name(),
            build_related_entities=True,
            unifying_id_field_filter_set=person_id_filter_set,
            state_code=state_code
        ))

        # Get StateSupervisionPeriods
        supervision_periods = (p | 'Load SupervisionPeriods' >> BuildRootEntity(
            dataset=input_dataset,
            root_entity_class=entities.StateSupervisionPeriod,
            unifying_id_field=entities.StatePerson.get_class_id_name(),
            build_related_entities=True,
            unifying_id_field_filter_set=person_id_filter_set,
            state_code=state_code
        ))

        # Get StateAssessments
        assessments = (p | 'Load Assessments' >> BuildRootEntity(
            dataset=input_dataset,
            root_entity_class=entities.StateAssessment,
            unifying_id_field=entities.StatePerson.get_class_id_name(),
            build_related_entities=False,
            unifying_id_field_filter_set=person_id_filter_set,
            state_code=state_code
        ))

        supervision_contacts = (p | 'Load StateSupervisionContacts' >> BuildRootEntity(
            dataset=input_dataset,
            root_entity_class=entities.StateSupervisionContact,
            unifying_id_field=entities.StatePerson.get_class_id_name(),
            build_related_entities=False,
            unifying_id_field_filter_set=person_id_filter_set,
            state_code=state_code
        ))

        # Bring in the table that associates StateSupervisionViolationResponses to information about StateAgents
        ssvr_to_agent_association_query = f"SELECT * FROM `{reference_dataset}.ssvr_to_agent_association`"

        ssvr_to_agent_associations = (p | "Read SSVR to Agent table from BigQuery" >>
                                      beam.io.Read(beam.io.BigQuerySource
                                                   (query=ssvr_to_agent_association_query,
                                                    use_standard_sql=True)))

        # Convert the association table rows into key-value tuples with the value for the
        # supervision_violation_response_id column as the key
        ssvr_agent_associations_as_kv = (ssvr_to_agent_associations | 'Convert SSVR to Agent table to KV tuples' >>
                                         beam.ParDo(ConvertDictToKVTuple(),
                                                    'supervision_violation_response_id')
                                         )

        supervision_period_to_agent_association_query = f"SELECT * FROM `{reference_dataset}." \
                                                        f"supervision_period_to_agent_association`"

        supervision_period_to_agent_associations = (p | "Read Supervision Period to Agent table from BigQuery" >>
                                                    beam.io.Read(beam.io.BigQuerySource
                                                                 (query=supervision_period_to_agent_association_query,
                                                                  use_standard_sql=True)))

        # Convert the association table rows into key-value tuples with the value for the supervision_period_id column
        # as the key
        supervision_period_to_agent_associations_as_kv = (supervision_period_to_agent_associations |
                                                          'Convert Supervision Period to Agent table to KV tuples' >>
                                                          beam.ParDo(ConvertDictToKVTuple(),
                                                                     'supervision_period_id')
                                                          )

        if state_code is None or state_code == 'US_MO':
            # Bring in the reference table that includes sentence status ranking information
            us_mo_sentence_status_query = f"SELECT * FROM `{reference_dataset}.us_mo_sentence_statuses`"

            us_mo_sentence_statuses = (p | "Read MO sentence status table from BigQuery" >>
                                       beam.io.Read(beam.io.BigQuerySource(query=us_mo_sentence_status_query,
                                                                           use_standard_sql=True)))
        else:
            us_mo_sentence_statuses = (p | f"Generate empty MO statuses list for non-MO state run: {state_code} " >>
                                       beam.Create([]))

        us_mo_sentence_status_rankings_as_kv = (
            us_mo_sentence_statuses |
            'Convert MO sentence status ranking table to KV tuples' >>
            beam.ParDo(ConvertDictToKVTuple(), 'person_id')
        )

        sentences_and_statuses = (
            {'incarceration_sentences': incarceration_sentences,
             'supervision_sentences': supervision_sentences,
             'sentence_statuses': us_mo_sentence_status_rankings_as_kv}
            | 'Group sentences to the sentence statuses for that person' >>
            beam.CoGroupByKey()
        )

        sentences_converted = (
            sentences_and_statuses
            | 'Convert to state-specific sentences' >>
            beam.ParDo(ConvertSentencesToStateSpecificType()).with_outputs('incarceration_sentences',
                                                                           'supervision_sentences')
        )

        # Group StateSupervisionViolationResponses and StateSupervisionViolations by person_id
        supervision_violations_and_responses = (
            {'violations': supervision_violations,
             'violation_responses': supervision_violation_responses
             } | 'Group StateSupervisionViolationResponses to '
                 'StateSupervisionViolations' >>
            beam.CoGroupByKey()
        )

        # Set the fully hydrated StateSupervisionViolation entities on the corresponding
        # StateSupervisionViolationResponses
        violation_responses_with_hydrated_violations = (
            supervision_violations_and_responses
            | 'Set hydrated StateSupervisionViolations on '
            'the StateSupervisionViolationResponses' >>
            beam.ParDo(SetViolationOnViolationsResponse()))

        # Group StateIncarcerationPeriods and StateSupervisionViolationResponses by person_id
        incarceration_periods_and_violation_responses = (
            {'incarceration_periods': incarceration_periods,
             'violation_responses':
                 violation_responses_with_hydrated_violations}
            | 'Group StateIncarcerationPeriods to '
              'StateSupervisionViolationResponses' >>
            beam.CoGroupByKey()
        )

        # Set the fully hydrated StateSupervisionViolationResponse entities on the corresponding
        # StateIncarcerationPeriods
        incarceration_periods_with_source_violations = (
            incarceration_periods_and_violation_responses
            | 'Set hydrated StateSupervisionViolationResponses on '
            'the StateIncarcerationPeriods' >>
            beam.ParDo(SetViolationResponseOnIncarcerationPeriod()))

        # Group each StatePerson with their StateIncarcerationPeriods and StateSupervisionSentences
        person_periods_and_sentences = (
            {'person': persons,
             'assessments': assessments,
             'incarceration_periods':
                 incarceration_periods_with_source_violations,
             'supervision_periods': supervision_periods,
             'supervision_sentences': sentences_converted.supervision_sentences,
             'incarceration_sentences': sentences_converted.incarceration_sentences,
             'violation_responses': violation_responses_with_hydrated_violations,
             'supervision_contacts': supervision_contacts
             }
            | 'Group StatePerson to all entities' >>
            beam.CoGroupByKey()
        )

        # Identify SupervisionTimeBuckets from the StatePerson's StateSupervisionSentences and StateIncarcerationPeriods
        person_time_buckets = (
            person_periods_and_sentences
            | 'Get SupervisionTimeBuckets' >>
            beam.ParDo(ClassifySupervisionTimeBuckets(),
                       AsDict(ssvr_agent_associations_as_kv),
                       AsDict(supervision_period_to_agent_associations_as_kv)))

        # Get pipeline job details for accessing job_id
        all_pipeline_options = apache_beam_pipeline_options.get_all_options()

        # Get the type of metric to calculate
        metric_types_set = set(metric_types)

        # Add timestamp for local jobs
        job_timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H_%M_%S.%f')
        all_pipeline_options['job_timestamp'] = job_timestamp

        # Get supervision metrics
        supervision_metrics = (person_time_buckets | 'Get Supervision Metrics' >>
                               GetSupervisionMetrics(
                                   pipeline_options=all_pipeline_options,
                                   metric_types=metric_types_set,
                                   calculation_end_month=calculation_end_month,
                                   calculation_month_count=calculation_month_count))
        if person_id_filter_set:
            logging.warning("Non-empty person filter set - returning before writing metrics.")
            return

        # Convert the metrics into a format that's writable to BQ
        writable_metrics = (supervision_metrics | 'Convert to dict to be written to BQ' >>
                            beam.ParDo(
                                SupervisionMetricWritableDict()).with_outputs(
                                    'populations', 'revocations', 'successes',
                                    'successful_sentence_lengths', 'assessment_changes', 'revocation_analyses',
                                    'revocation_violation_type_analyses', 'compliances'
                                )
                            )

        # Write the metrics to the output tables in BigQuery
        assessment_changes_table_id = DATAFLOW_METRICS_TO_TABLES.get(TerminatedSupervisionAssessmentScoreChangeMetric)
        compliance_table_id = DATAFLOW_METRICS_TO_TABLES.get(SupervisionCaseComplianceMetric)
        populations_table_id = DATAFLOW_METRICS_TO_TABLES.get(SupervisionPopulationMetric)
        revocations_table_id = DATAFLOW_METRICS_TO_TABLES.get(SupervisionRevocationMetric)
        revocation_analysis_table_id = DATAFLOW_METRICS_TO_TABLES.get(SupervisionRevocationAnalysisMetric)
        revocation_violation_type_analysis_table_id = \
            DATAFLOW_METRICS_TO_TABLES.get(SupervisionRevocationViolationTypeAnalysisMetric)
        successes_table_id = DATAFLOW_METRICS_TO_TABLES.get(SupervisionSuccessMetric)
        successful_sentence_lengths_table_id = DATAFLOW_METRICS_TO_TABLES.get(
            SuccessfulSupervisionSentenceDaysServedMetric)

        _ = (writable_metrics.populations
             | f"Write population metrics to BQ table: {populations_table_id}" >>
             beam.io.WriteToBigQuery(
                 table=populations_table_id,
                 dataset=output,
                 create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                 write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
             ))

        _ = (writable_metrics.revocations
             | f"Write revocation metrics to BQ table: {revocations_table_id}" >>
             beam.io.WriteToBigQuery(
                 table=revocations_table_id,
                 dataset=output,
                 create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                 write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
             ))

        _ = (writable_metrics.successes
             | f"Write success metrics to BQ table: {successes_table_id}" >>
             beam.io.WriteToBigQuery(
                 table=successes_table_id,
                 dataset=output,
                 create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                 write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
             ))

        _ = (writable_metrics.successful_sentence_lengths
             | f"Write supervision successful sentence length metrics to BQ"
               f" table: {successful_sentence_lengths_table_id}" >>
             beam.io.WriteToBigQuery(
                 table=successful_sentence_lengths_table_id,
                 dataset=output,
                 create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                 write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
             ))

        _ = (writable_metrics.assessment_changes
             | f"Write assessment change metrics to BQ table: {assessment_changes_table_id}" >>
             beam.io.WriteToBigQuery(
                 table=assessment_changes_table_id,
                 dataset=output,
                 create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                 write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
             ))

        _ = (writable_metrics.revocation_analyses
             | f"Write revocation analyses metrics to BQ table: {revocation_analysis_table_id}" >>
             beam.io.WriteToBigQuery(
                 table=revocation_analysis_table_id,
                 dataset=output,
                 create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                 write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
             ))

        _ = (writable_metrics.revocation_violation_type_analyses
             | f"Write revocation violation type analyses metrics to BQ table: "
               f"{revocation_violation_type_analysis_table_id}" >>
             beam.io.WriteToBigQuery(
                 table=revocation_violation_type_analysis_table_id,
                 dataset=output,
                 create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                 write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
             ))

        _ = (writable_metrics.compliances
             | f"Write compliance metrics to BQ table: {compliance_table_id}" >>
             beam.io.WriteToBigQuery(
                 table=compliance_table_id,
                 dataset=output,
                 create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                 write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
             ))
