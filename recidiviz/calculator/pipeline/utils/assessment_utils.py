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
"""Utils for dealing with assessment data in the calculation pipelines."""
import logging
from datetime import date
from typing import List, Tuple, Optional

from recidiviz.common.constants.state.state_assessment import \
    StateAssessmentType, StateAssessmentLevel
from recidiviz.persistence.entity.state.entities import StateAssessment

ASSESSMENT_TYPES_TO_INCLUDE = {
    'program': {
        'US_ID': [StateAssessmentType.LSIR],
        'US_MO': [
            StateAssessmentType.ORAS_COMMUNITY_SUPERVISION,
            StateAssessmentType.ORAS_COMMUNITY_SUPERVISION_SCREENING
        ],
        'US_ND': [StateAssessmentType.LSIR],
    },
    'supervision': {
        'US_ID': [StateAssessmentType.LSIR],
        'US_MO': [
            StateAssessmentType.ORAS_COMMUNITY_SUPERVISION,
            StateAssessmentType.ORAS_COMMUNITY_SUPERVISION_SCREENING
        ],
        'US_ND': [StateAssessmentType.LSIR],
    },
}


def find_most_recent_assessment(cutoff_date: date, assessments: List[StateAssessment]) -> Optional[StateAssessment]:
    """Finds the assessment that happened before or on the given date and has the date closest to the given date.
    Returns the assessment."""
    if assessments:
        assessments_before_date = [
            assessment for assessment in assessments
            if assessment.assessment_date is not None
            and assessment.assessment_date <= cutoff_date
        ]

        if assessments_before_date:
            assessments_before_date.sort(
                key=lambda b: b.assessment_date)

            most_recent_assessment = assessments_before_date[-1]
            return most_recent_assessment

    return None


def most_recent_assessment_attributes(cutoff_date: date, assessments: List[StateAssessment]) -> \
        Tuple[Optional[int], Optional[StateAssessmentLevel], Optional[StateAssessmentType]]:
    """Finds the assessment that happened before or on the given date and has the date closest to the given date.
    Returns the assessment score, assessment level, and the assessment type."""
    most_recent_assessment = find_most_recent_assessment(cutoff_date, assessments)

    if most_recent_assessment:
        return most_recent_assessment.assessment_score, \
               most_recent_assessment.assessment_level, \
               most_recent_assessment.assessment_type

    return None, None, None


def assessment_score_bucket(assessment_score: int,
                            assessment_level: Optional[StateAssessmentLevel],
                            assessment_type: StateAssessmentType) -> \
        Optional[str]:
    """Calculates the assessment score bucket that applies to measurement.

    Args:
        assessment_score: the person's assessment score
        assessment_level: the person's assessment level
        assessment_type: the type of assessment

    NOTE: Only LSIR and ORAS buckets are currently supported
    TODO(2742): Add calculation support for all supported StateAssessmentTypes

    Returns:
        A string representation of the assessment score for the person.
        None if the assessment type is not supported.
    """
    if assessment_type == StateAssessmentType.LSIR:
        if assessment_score < 24:
            return '0-23'
        if assessment_score <= 29:
            return '24-29'
        if assessment_score <= 38:
            return '30-38'
        return '39+'

    if assessment_type and assessment_type.value.startswith('ORAS'):
        if assessment_level:
            return assessment_level.value
        return None

    logging.warning("Assessment type %s is unsupported.", assessment_type)

    return None


def find_assessment_score_change(start_date: date,
                                 termination_date: date,
                                 assessments: List[StateAssessment]) -> \
        Tuple[Optional[int], Optional[int], Optional[StateAssessmentLevel],
              Optional[StateAssessmentType]]:
    """Finds the difference in scores between the first reassessment
    (the second assessment) and the last assessment that happened
    between the start_date and termination_date (inclusive). Returns the
    assessment score change, the ending assessment score, the ending assessment
    level, and the assessment type. If there aren't enough assessments to
    compare, or the first reassessment and the last assessment are not of the
    same type, returns (None, None, None, None)."""
    if assessments:
        assessments_in_period = [
            assessment for assessment in assessments
            if assessment.assessment_date is not None
            and start_date <= assessment.assessment_date <= termination_date
        ]

        # If this person had less than 3 assessments then we cannot compare
        # the first reassessment to the most recent assessment.
        # TODO(2782): Investigate whether to update this logic
        if assessments_in_period and len(assessments_in_period) >= 3:
            assessments_in_period.sort(
                key=lambda b: b.assessment_date)

            first_reassessment = assessments_in_period[1]
            last_assessment = assessments_in_period[-1]

            # Assessments must be of the same type
            if last_assessment.assessment_type == \
                    first_reassessment.assessment_type:
                first_assessment_date = first_reassessment.assessment_date
                last_assessment_date = last_assessment.assessment_date

                # Ensure these assessments were actually issued on different
                # days
                if first_assessment_date and last_assessment_date and\
                        last_assessment_date > first_assessment_date:
                    first_reassessment_score = \
                        first_reassessment.assessment_score
                    last_assessment_score = last_assessment.assessment_score

                    if first_reassessment_score is not None and \
                            last_assessment_score is not None:

                        assessment_score_change = \
                            (last_assessment_score
                             - first_reassessment_score)

                        return assessment_score_change, \
                            last_assessment.assessment_score, \
                            last_assessment.assessment_level, \
                            last_assessment.assessment_type

    return None, None, None, None


def include_assessment_in_metric(pipeline: str, state_code: str, assessment_type: StateAssessmentType) -> bool:
    """Returns whether assessment data from the assessment with the given StateAssessmentType should be included in
    the results for metrics in the given pipeline with the given state_code."""
    values_for_pipeline = ASSESSMENT_TYPES_TO_INCLUDE.get(pipeline)

    if values_for_pipeline:
        assessment_types_to_include = values_for_pipeline.get(state_code)

        if assessment_types_to_include:
            return assessment_type is not None and assessment_type in assessment_types_to_include

        logging.warning("Unsupported state_code: %s for pipeline type: %s."
                        " Update ASSESSMENT_TYPES_TO_INCLUDE.", state_code, pipeline)

    logging.warning("Unsupported pipeline type: %s for state_code: %s. Update ASSESSMENT_TYPES_TO_INCLUDE.",
                    pipeline, state_code)
    return False
