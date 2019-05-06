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
"""Validates that data in converted Entity objects conforms to data
assumptions."""

from typing import List, Tuple, Callable

from recidiviz.persistence.entities import Person, PersonType, StatePerson
from recidiviz.persistence.entity_validator.county.county_validator import \
    validate_county_person
from recidiviz.persistence.entity_validator.state.state_validator import \
    validate_state_person


def validate(people: List[PersonType]) -> Tuple[List[PersonType], int]:
    """Validates a list of Person entities and returns the valid people and
    the number of people with validation errors."""
    data_validation_errors = 0
    validated_people = []
    for person in people:
        validator = _get_validator(person)
        if validator(person):
            validated_people.append(person)
        else:
            data_validation_errors += 1
    return validated_people, data_validation_errors


def _get_validator(person: PersonType) -> Callable[[PersonType], bool]:
    if isinstance(person, Person):
        return validate_county_person

    if isinstance(person, StatePerson):
        return validate_state_person

    raise ValueError("Person entity to validate was not of expected type "
                     "Person or StatePerson but [{}]"
                     .format(person.__class__.__name__))
