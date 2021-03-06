# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2020 Recidiviz, Inc.
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
"""Supervision termination for successful discharge per officer, district, and state, by month."""
# pylint: disable=trailing-whitespace

from recidiviz.big_query.big_query_view import SimpleBigQueryViewBuilder
from recidiviz.calculator.query import bq_utils
from recidiviz.calculator.query.state import dataset_config
from recidiviz.utils.environment import GAE_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override

SUPERVISION_DISCHARGES_BY_OFFICER_BY_MONTH_VIEW_NAME = 'supervision_discharges_by_officer_by_month'

SUPERVISION_DISCHARGES_BY_OFFICER_BY_MONTH_DESCRIPTION = """
 Discharged supervision period metrics aggregated by termination month. Includes total positive discharges per officer,
 average discharges per district, and average discharges per state.
 """

SUPERVISION_DISCHARGES_BY_OFFICER_BY_MONTH_QUERY_TEMPLATE = \
    """
    /*{description}*/
    WITH supervision_periods AS (
      SELECT
        state_code, person_id, supervision_period_id,
        start_date, termination_date, termination_reason,
        EXTRACT(YEAR FROM termination_date) AS year,
        EXTRACT(MONTH FROM termination_date) AS month,
        COALESCE(SPLIT(supervision_site, '|')[OFFSET(0)],
                 agent.district_external_id) AS district,
        COALESCE(agent.agent_external_id, 'UNKNOWN') AS officer_external_id,
      FROM `{project_id}.{state_dataset}.state_supervision_period`
      LEFT JOIN `{project_id}.{reference_dataset}.supervision_period_to_agent_association` agent
        USING (state_code, supervision_period_id)
      -- Do not include any investigative or informal probation supervision periods for ID
      WHERE (state_code != 'US_ID'
             OR supervision_period_supervision_type NOT IN ('INVESTIGATION', 'INFORMAL_PROBATION'))
    ),
    supervision_discharges AS (
      -- Gather all supervision discharges from the last 3 years
      SELECT
        *
      FROM supervision_periods
      WHERE termination_date IS NOT NULL
         AND termination_reason IN ('DISCHARGE', 'EXPIRATION')
         AND EXTRACT(YEAR FROM termination_date) >= EXTRACT(YEAR FROM DATE_SUB(CURRENT_DATE(), INTERVAL 3 YEAR))
    ),
    overlapping_open_period AS (
      -- Find the supervision periods that should not be counted as discharges because of another overlapping period
      SELECT
        p1.supervision_period_id
      FROM supervision_discharges p1
      JOIN supervision_periods p2
        USING (state_code, person_id)
      WHERE p1.supervision_period_id != p2.supervision_period_id
        -- Find any overlapping supervision period (started on or before the discharge, ended after the discharge)
        AND p2.start_date <= p1.termination_date
        AND p1.termination_date < COALESCE(p2.termination_date, CURRENT_DATE())
        -- Count the period as an overlapping open period if it wasn't discharged in the same month
        AND (p2.termination_reason NOT IN ('DISCHARGE', 'EXPIRATION')
            OR DATE_TRUNC(p2.termination_date, MONTH) != DATE_TRUNC(p1.termination_date, MONTH))
    ),
    officers_with_supervision AS (
      -- Get all officers with supervision caseloads each month
      SELECT DISTINCT
        state_code, year, month,
        SPLIT(district, '|')[OFFSET(0)] AS district,
        officer_external_id
      FROM `{project_id}.{reference_dataset}.event_based_supervision_populations`
      WHERE district != 'ALL'
        AND (state_code != 'US_ID' OR supervision_type NOT IN ('ALL', 'INVESTIGATION', 'INFORMAL_PROBATION'))
    ),
    discharges_per_officer AS (
      -- Count the discharges per officer, excluding any non-eligible discharges
      SELECT
        state_code, year, month,
        officer_external_id, district,
        COUNT(DISTINCT person_id) AS discharge_count
      FROM officers_with_supervision
      LEFT JOIN supervision_discharges
        USING (state_code, year, month, officer_external_id, district)
      LEFT JOIN overlapping_open_period USING (supervision_period_id)
      -- Do not count any discharges that are overlapping with another open supervision period
      WHERE overlapping_open_period.supervision_period_id IS NULL
      GROUP BY state_code, year, month, district, officer_external_id
    ),
    avg_discharges_by_district_state AS (
      -- Get the average monthly discharges by district and state
      SELECT
        state_code, year, month,
        district,
        AVG(discharge_count) AS discharge_count
      FROM discharges_per_officer,
      {district_dimension}
      GROUP BY state_code, year, month, district
    )
    SELECT
      state_code, year, month,
      officer_external_id, district,
      discharges_per_officer.discharge_count AS pos_discharges,
      district_avg.discharge_count AS pos_discharges_district_average,
      state_avg.discharge_count AS pos_discharges_state_average
    FROM discharges_per_officer
    LEFT JOIN (
      SELECT * FROM avg_discharges_by_district_state
      WHERE district != 'ALL'
    ) district_avg
      USING (state_code, year, month, district)
    LEFT JOIN (
      SELECT * EXCEPT (district) FROM avg_discharges_by_district_state
      WHERE district = 'ALL'
    ) state_avg
      USING (state_code, year, month)
    ORDER BY state_code, year, month, district, officer_external_id
    """

SUPERVISION_DISCHARGES_BY_OFFICER_BY_MONTH_VIEW_BUILDER = SimpleBigQueryViewBuilder(
    dataset_id=dataset_config.PO_REPORT_DATASET,
    view_id=SUPERVISION_DISCHARGES_BY_OFFICER_BY_MONTH_VIEW_NAME,
    view_query_template=SUPERVISION_DISCHARGES_BY_OFFICER_BY_MONTH_QUERY_TEMPLATE,
    description=SUPERVISION_DISCHARGES_BY_OFFICER_BY_MONTH_DESCRIPTION,
    reference_dataset=dataset_config.REFERENCE_TABLES_DATASET,
    state_dataset=dataset_config.STATE_BASE_DATASET,
    district_dimension=bq_utils.unnest_district(district_column='district'),
)

if __name__ == '__main__':
    with local_project_id_override(GAE_PROJECT_STAGING):
        SUPERVISION_DISCHARGES_BY_OFFICER_BY_MONTH_VIEW_BUILDER.build_and_print()
