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
"""Dashboard view configuration."""

# Where the dashboard views and materialized tables live
DASHBOARD_VIEWS_DATASET: str = 'dashboard_views'

# Where the metrics that Dataflow jobs produce live
DATAFLOW_METRICS_DATASET: str = 'dataflow_metrics'

# TODO(1627): Move this variable to bq/export_manager and update name to state
STATE_BASE_TABLES_BQ_DATASET: str = 'pipeline_test_space'
