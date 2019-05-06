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
# ============================================================================

"""Utilities for working with the database schemas."""

import inspect
import sys
from typing import Iterator

from sqlalchemy import Table

from recidiviz.persistence.database.schema.aggregate import \
    schema as aggregate_schema
from recidiviz.persistence.database.schema.county import schema as county_schema
from recidiviz.persistence.database.base_schema import Base
from recidiviz.persistence.database.schema.state import schema as state_schema

_SCHEMA_MODULES = [aggregate_schema.__name__,
                   county_schema.__name__,
                   state_schema.__name__]


def get_all_table_classes() -> Iterator[Table]:
    for module_name in _SCHEMA_MODULES:
        yield from _get_all_table_classes(module_name)


def _get_all_table_classes(module_name) -> Iterator[Table]:
    all_members_in_current_module = inspect.getmembers(sys.modules[module_name])
    for _, member in all_members_in_current_module:
        if (inspect.isclass(member)
                and issubclass(member, Base)
                and member is not Base):
            yield member


def get_aggregate_table_classes() -> Iterator[Table]:
    yield from _get_all_table_classes(aggregate_schema.__name__)
