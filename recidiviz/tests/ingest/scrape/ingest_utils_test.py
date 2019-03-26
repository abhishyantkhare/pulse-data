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

"""Tests for ingest/ingest_utils.py."""

from mock import Mock, PropertyMock, patch

from recidiviz.common import common_utils
from recidiviz.ingest.models import ingest_info, ingest_info_pb2
from recidiviz.ingest.scrape import constants, ingest_utils


def fake_modules(*names):
    modules = []
    for name in names:
        fake_module = Mock()
        type(fake_module).name = PropertyMock(return_value=name)
        modules.append(fake_module)
    return modules


class TestIngestUtils:
    """Tests for regions.py."""

    def _create_generated_id(self):
        self.counter += 1
        return str(self.counter) + common_utils.GENERATED_ID_SUFFIX

    def setup_method(self, _):
        self.counter = 0

    @patch('pkgutil.iter_modules',
           return_value=fake_modules('us_ny', 'us_pa', 'us_vt', 'us_pa_greene'))
    def test_validate_regions_one_ok(self, _mock_modules):
        assert ingest_utils.validate_regions(['us_ny']) == {'us_ny'}

    @patch('pkgutil.iter_modules',
           return_value=fake_modules('us_ny', 'us_pa', 'us_vt', 'us_pa_greene'))
    def test_validate_regions_one_all(self, _mock_modules):
        assert ingest_utils.validate_regions(['all']) == {
            'us_ny',
            'us_pa',
            'us_vt',
            'us_pa_greene',
        }

    @patch('pkgutil.iter_modules',
           return_value=fake_modules('us_ny', 'us_pa', 'us_vt', 'us_pa_greene'))
    def test_validate_regions_one_invalid(self, _mock_modules):
        assert not ingest_utils.validate_regions(['ca_bc'])

    @patch('pkgutil.iter_modules',
           return_value=fake_modules('us_ny', 'us_pa', 'us_vt', 'us_pa_greene'))
    def test_validate_regions_multiple_ok(self, _mock_modules):
        assert ingest_utils.validate_regions(['us_pa', 'us_ny']) == {'us_pa',
                                                                     'us_ny'}

    @patch('pkgutil.iter_modules',
           return_value=fake_modules('us_ny', 'us_pa', 'us_vt', 'us_pa_greene'))
    def test_validate_regions_multiple_invalid(self, _mock_modules):
        assert not ingest_utils.validate_regions(['us_pa', 'invalid'])

    @patch('pkgutil.iter_modules',
           return_value=fake_modules('us_ny', 'us_pa', 'us_vt', 'us_pa_greene'))
    @patch("recidiviz.utils.environment.get_gae_environment")
    @patch("recidiviz.utils.regions.get_region")
    def test_validate_regions_multiple_all(
            self, mock_region, mock_env, _mock_modules):
        fake_region = Mock()
        mock_region.return_value = fake_region
        fake_region.environment = 'production'
        mock_env.return_value = 'production'

        assert ingest_utils.validate_regions(['us_pa', 'all']) == {
            'us_ny',
            'us_pa',
            'us_vt',
            'us_pa_greene',
        }

    @patch('pkgutil.iter_modules',
           return_value=fake_modules('us_a', 'us_b', 'us_c', 'us_d'))
    @patch("recidiviz.utils.environment.get_gae_environment")
    @patch("recidiviz.utils.regions.get_region")
    def test_validate_regions_environments(
            self, mock_region, mock_env, _mock_modules):
        region_prod, region_staging, region_none = Mock(), Mock(), Mock()
        region_prod.environment = 'production'
        region_staging.environment = 'staging'
        region_none.environment = False

        mock_region.side_effect = [
            region_prod, region_none, region_prod, region_staging
        ]
        mock_env.return_value = 'production'

        assert len(ingest_utils.validate_regions(['all'])) == 2

    @patch('pkgutil.iter_modules',
           return_value=fake_modules('us_ny', 'us_pa', 'us_vt', 'us_pa_greene'))
    def test_validate_regions_multiple_all_invalid(self, _mock_modules):
        assert not ingest_utils.validate_regions(['all', 'invalid'])

    @patch('pkgutil.iter_modules',
           return_value=fake_modules('us_ny', 'us_pa', 'us_vt', 'us_pa_greene'))
    def test_validate_regions_empty(self, _mock_modules):
        assert ingest_utils.validate_regions([]) == set()

    def test_validate_scrape_types_one_ok(self):
        assert ingest_utils.validate_scrape_types(
            [constants.ScrapeType.SNAPSHOT.value]) == \
            [constants.ScrapeType.SNAPSHOT]

    def test_validate_scrape_types_one_all(self):
        assert ingest_utils.validate_scrape_types(['all']) == [
            constants.ScrapeType.BACKGROUND, constants.ScrapeType.SNAPSHOT]

    def test_validate_scrape_types_one_invalid(self):
        assert not ingest_utils.validate_scrape_types(['When You Were Young'])

    def test_validate_scrape_types_multiple_ok(self):
        assert ingest_utils.validate_scrape_types(
            [constants.ScrapeType.BACKGROUND.value,
             constants.ScrapeType.SNAPSHOT.value]) == \
            [constants.ScrapeType.BACKGROUND, constants.ScrapeType.SNAPSHOT]

    def test_validate_scrape_types_multiple_invalid(self):
        assert not ingest_utils.validate_scrape_types(
            [constants.ScrapeType.BACKGROUND.value, 'invalid'])

    def test_validate_scrape_types_multiple_all(self):
        assert ingest_utils.validate_scrape_types(
            [constants.ScrapeType.BACKGROUND.value, 'all']) == \
            [constants.ScrapeType.BACKGROUND, constants.ScrapeType.SNAPSHOT]

    def test_validate_scrape_types_multiple_all_invalid(self):
        assert not ingest_utils.validate_scrape_types(['all', 'invalid'])

    def test_validate_scrape_types_empty(self):
        assert ingest_utils.validate_scrape_types(
            []) == [constants.ScrapeType.BACKGROUND]

    @patch("recidiviz.common.common_utils.create_generated_id")
    def test_convert_ingest_info_id_is_generated(self, mock_create):
        mock_create.side_effect = self._create_generated_id
        info = ingest_info.IngestInfo()
        person = info.create_person()
        person.surname = 'testname'
        person.create_booking()

        expected_proto = ingest_info_pb2.IngestInfo()
        proto_person = expected_proto.people.add()
        proto_person.surname = 'testname'
        proto_person.person_id = '1_GENERATE'
        proto_booking = expected_proto.bookings.add()
        proto_booking.booking_id = '2_GENERATE'
        proto_person.booking_ids.append(proto_booking.booking_id)

        proto = ingest_utils.convert_ingest_info_to_proto(info)
        assert proto == expected_proto

        info_back = ingest_utils.convert_proto_to_ingest_info(proto)
        assert info_back == info

    def test_convert_ingest_info_id_is_not_generated(self):
        info = ingest_info.IngestInfo()
        person = info.create_person()
        person.person_id = 'id1'
        person.surname = 'testname'
        booking = person.create_booking()
        booking.booking_id = 'id2'
        booking.admission_date = 'testdate'

        expected_proto = ingest_info_pb2.IngestInfo()
        person = expected_proto.people.add()
        person.person_id = 'id1'
        person.surname = 'testname'
        person.booking_ids.append('id2')
        booking = expected_proto.bookings.add()
        booking.booking_id = 'id2'
        booking.admission_date = 'testdate'

        proto = ingest_utils.convert_ingest_info_to_proto(info)
        assert expected_proto == proto

        info_back = ingest_utils.convert_proto_to_ingest_info(proto)
        assert info_back == info

    @patch("recidiviz.common.common_utils.create_generated_id")
    def test_convert_ingest_info_one_charge_to_one_bond(self, mock_create):
        mock_create.side_effect = self._create_generated_id
        info = ingest_info.IngestInfo()
        person = info.create_person()
        person.person_id = 'id1'

        booking = person.create_booking()
        booking.booking_id = 'id1'
        charge = booking.create_charge()
        charge.charge_id = 'id1'
        bond1 = charge.create_bond()
        bond1.amount = '$1'
        charge = booking.create_charge()
        charge.charge_id = 'id2'
        bond2 = charge.create_bond()
        bond2.amount = '$1'

        expected_proto = ingest_info_pb2.IngestInfo()
        person = expected_proto.people.add()
        person.person_id = 'id1'
        person.booking_ids.append('id1')
        booking = expected_proto.bookings.add()
        booking.booking_id = 'id1'
        booking.charge_ids.extend(['id1', 'id2'])
        charge = expected_proto.charges.add()
        charge.charge_id = 'id1'
        proto_bond1 = expected_proto.bonds.add()
        proto_bond1.amount = '$1'
        proto_bond1.bond_id = '1_GENERATE'
        charge.bond_id = proto_bond1.bond_id
        charge = expected_proto.charges.add()
        charge.charge_id = 'id2'
        proto_bond2 = expected_proto.bonds.add()
        proto_bond2.amount = '$1'
        proto_bond2.bond_id = '2_GENERATE'
        charge.bond_id = proto_bond2.bond_id

        proto = ingest_utils.convert_ingest_info_to_proto(info)
        assert expected_proto == proto

        info_back = ingest_utils.convert_proto_to_ingest_info(proto)
        assert info_back == info

    @patch("recidiviz.common.common_utils.create_generated_id")
    def test_convert_ingest_info_many_charge_to_one_bond(self, mock_create):
        mock_create.side_effect = self._create_generated_id
        info = ingest_info.IngestInfo()
        person = info.create_person()
        person.person_id = 'id1'

        booking = person.create_booking()
        booking.booking_id = 'id1'
        charge = booking.create_charge()
        charge.charge_id = 'id1'
        bond1 = charge.create_bond()
        bond1.amount = '$1'
        charge = booking.create_charge()
        charge.charge_id = 'id2'
        charge.bond = bond1

        expected_proto = ingest_info_pb2.IngestInfo()
        person = expected_proto.people.add()
        person.person_id = 'id1'
        person.booking_ids.append('id1')
        booking = expected_proto.bookings.add()
        booking.booking_id = 'id1'
        booking.charge_ids.extend(['id1', 'id2'])
        charge = expected_proto.charges.add()
        charge.charge_id = 'id1'
        proto_bond = expected_proto.bonds.add()
        proto_bond.amount = '$1'
        proto_bond.bond_id = '1_GENERATE'
        charge.bond_id = proto_bond.bond_id
        charge = expected_proto.charges.add()
        charge.charge_id = 'id2'
        charge.bond_id = proto_bond.bond_id

        proto = ingest_utils.convert_ingest_info_to_proto(info)
        assert len(proto.bonds) == 1
        assert expected_proto == proto

        info_back = ingest_utils.convert_proto_to_ingest_info(proto)
        assert info_back == info

    def test_serializable(self):
        info = ingest_info.IngestInfo()
        person = info.create_person()
        person.person_id = 'id1'

        booking = person.create_booking()
        booking.booking_id = 'id1'
        charge = booking.create_charge()
        charge.charge_id = 'id1'
        bond1 = charge.create_bond()
        bond1.amount = '$1'
        charge = booking.create_charge()
        charge.charge_id = 'id2'
        bond2 = charge.create_bond()
        bond2.amount = '$1'

        converted_info = ingest_utils.ingest_info_from_serializable(
            ingest_utils.ingest_info_to_serializable(info))

        assert converted_info == info
