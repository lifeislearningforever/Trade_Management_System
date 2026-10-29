"""
Tests for the stable security_id registry logic introduced in commits 4ed84aa and 7c12783.

Covers:
  - _build_natural_key: all 6 key-type priority rules
  - _get_or_allocate_security_id: registry hit, registry miss (new allocation),
    counter seeding fallback, ID stability on repeat calls, cross-listed security
    isolation
"""

import pytest
from unittest.mock import patch, MagicMock, call

from security.repositories.security_hive_repository import SecurityHiveRepository

REPO = 'security.repositories.security_hive_repository'


# ---------------------------------------------------------------------------
# _build_natural_key
# ---------------------------------------------------------------------------

class TestBuildNaturalKey:

    def test_isin_and_exchange_code_takes_priority(self):
        data = {'isin': 'AU000000ANZ3', 'exchange_code': 'ASX', 'country_of_exchange': 'AU', 'security_name': 'ANZ'}
        key, key_type = SecurityHiveRepository._build_natural_key(data)
        assert key_type == 'ISIN_EXCH'
        assert key == 'ISIN_EXCH:AU000000ANZ3:ASX'

    def test_isin_and_country_when_no_exchange_code(self):
        data = {'isin': 'AU000000ANZ3', 'exchange_code': '', 'country_of_exchange': 'AU', 'security_name': 'ANZ'}
        key, key_type = SecurityHiveRepository._build_natural_key(data)
        assert key_type == 'ISIN_CTY'
        assert key == 'ISIN_CTY:AU000000ANZ3:AU'

    def test_isin_only_when_no_exchange_or_country(self):
        data = {'isin': 'XS1234567890', 'exchange_code': None, 'country_of_exchange': None, 'security_name': 'Bond A'}
        key, key_type = SecurityHiveRepository._build_natural_key(data)
        assert key_type == 'ISIN'
        assert key == 'ISIN:XS1234567890'

    def test_name_and_exchange_when_no_isin(self):
        data = {'isin': '', 'exchange_code': 'SGX', 'country_of_exchange': 'SG', 'security_name': 'Private Fund'}
        key, key_type = SecurityHiveRepository._build_natural_key(data)
        assert key_type == 'NAME_EXCH'
        assert key == 'NAME_EXCH:PRIVATE FUND:SGX'

    def test_name_and_country_when_no_isin_and_no_exchange(self):
        data = {'isin': None, 'exchange_code': '', 'country_of_exchange': 'SG', 'security_name': 'Private Fund'}
        key, key_type = SecurityHiveRepository._build_natural_key(data)
        assert key_type == 'NAME_CTY'
        assert key == 'NAME_CTY:PRIVATE FUND:SG'

    def test_name_only_as_last_resort(self):
        data = {'isin': None, 'exchange_code': None, 'country_of_exchange': None, 'security_name': 'Unlisted Entity'}
        key, key_type = SecurityHiveRepository._build_natural_key(data)
        assert key_type == 'NAME'
        assert key == 'NAME:UNLISTED ENTITY'

    def test_isin_normalised_to_uppercase(self):
        data = {'isin': 'au000000anz3', 'exchange_code': 'asx', 'country_of_exchange': '', 'security_name': 'ANZ'}
        key, key_type = SecurityHiveRepository._build_natural_key(data)
        assert key == 'ISIN_EXCH:AU000000ANZ3:ASX'

    def test_name_normalised_to_uppercase(self):
        data = {'isin': '', 'exchange_code': '', 'country_of_exchange': '', 'security_name': 'some fund'}
        key, key_type = SecurityHiveRepository._build_natural_key(data)
        assert key == 'NAME:SOME FUND'

    def test_whitespace_stripped_from_all_fields(self):
        data = {'isin': '  AU000000ANZ3  ', 'exchange_code': '  ASX  ', 'country_of_exchange': '', 'security_name': 'ANZ'}
        key, key_type = SecurityHiveRepository._build_natural_key(data)
        assert key == 'ISIN_EXCH:AU000000ANZ3:ASX'

    def test_cross_listed_same_isin_different_exchange_gives_different_keys(self):
        """ANZ AU vs ANZ NZ — same ISIN, different exchange → must NOT collapse to same key."""
        anz_au = {'isin': 'AU000000ANZ3', 'exchange_code': 'ASX', 'country_of_exchange': 'AU', 'security_name': 'ANZ'}
        anz_nz = {'isin': 'AU000000ANZ3', 'exchange_code': 'NZX', 'country_of_exchange': 'NZ', 'security_name': 'ANZ'}
        key_au, _ = SecurityHiveRepository._build_natural_key(anz_au)
        key_nz, _ = SecurityHiveRepository._build_natural_key(anz_nz)
        assert key_au != key_nz

    def test_missing_security_data_keys_handled_gracefully(self):
        """Should not raise if optional keys are absent from dict."""
        data = {'security_name': 'Minimal'}
        key, key_type = SecurityHiveRepository._build_natural_key(data)
        assert key_type == 'NAME'
        assert key == 'NAME:MINIMAL'


# ---------------------------------------------------------------------------
# _get_or_allocate_security_id
# ---------------------------------------------------------------------------

SECURITY_DATA = {
    'isin': 'AU000000ANZ3',
    'exchange_code': 'ASX',
    'country_of_exchange': 'AU',
    'security_name': 'ANZ Banking Group',
}


@pytest.fixture
def mock_impala():
    with patch(f'{REPO}.impala_manager') as m:
        yield m


class TestGetOrAllocateSecurityId:

    def test_registry_hit_returns_existing_id(self, mock_impala):
        """When registry already has the natural key, return that ID without touching counter."""
        mock_impala.execute_query.return_value = [{'security_id': 100000000042}]

        result = SecurityHiveRepository._get_or_allocate_security_id(
            SECURITY_DATA, src_system='CIS', created_by='testuser'
        )

        assert result == 100000000042
        # Only one query (registry lookup); counter never read
        assert mock_impala.execute_query.call_count == 1
        mock_impala.execute_write.assert_not_called()

    def test_registry_miss_allocates_new_id_from_counter(self, mock_impala):
        """Registry miss + counter exists → allocate counter's next_id."""
        mock_impala.execute_query.side_effect = [
            [],                              # registry lookup → miss
            [{'next_id': 100000000099}],     # counter read
        ]

        result = SecurityHiveRepository._get_or_allocate_security_id(
            SECURITY_DATA, src_system='CIS', created_by='testuser'
        )

        assert result == 100000000099
        assert mock_impala.execute_write.call_count == 2  # registry insert + counter advance

    def test_registry_miss_and_no_counter_falls_back_to_floor(self, mock_impala):
        """Registry miss + no counter row → seed from ID_FLOOR + 1."""
        mock_impala.execute_query.side_effect = [
            [],   # registry miss
            [],   # counter miss
        ]

        result = SecurityHiveRepository._get_or_allocate_security_id(
            SECURITY_DATA, src_system='GMP', created_by='GMP_ETL'
        )

        assert result == SecurityHiveRepository.ID_FLOOR + 1

    def test_counter_advanced_by_one_after_allocation(self, mock_impala):
        """After allocating ID N the counter must be written as N+1."""
        mock_impala.execute_query.side_effect = [
            [],
            [{'next_id': 100000000200}],
        ]

        SecurityHiveRepository._get_or_allocate_security_id(
            SECURITY_DATA, src_system='CIS', created_by='testuser'
        )

        write_calls = [str(c) for c in mock_impala.execute_write.call_args_list]
        counter_call = next(c for c in write_calls if 'cis_security_id_counter' in c)
        assert '100000000201' in counter_call  # next_id advanced to 200 + 1

    def test_registry_entry_written_with_correct_natural_key(self, mock_impala):
        """Registry UPSERT must include the derived natural key."""
        mock_impala.execute_query.side_effect = [
            [],
            [{'next_id': 100000000001}],
        ]

        SecurityHiveRepository._get_or_allocate_security_id(
            SECURITY_DATA, src_system='CIS', created_by='testuser'
        )

        registry_call = str(mock_impala.execute_write.call_args_list[0])
        assert 'ISIN_EXCH:AU000000ANZ3:ASX' in registry_call

    def test_returned_id_is_integer(self, mock_impala):
        mock_impala.execute_query.return_value = [{'security_id': '100000000042'}]  # string from Impala
        result = SecurityHiveRepository._get_or_allocate_security_id(
            SECURITY_DATA, src_system='CIS', created_by='testuser'
        )
        assert isinstance(result, int)
        assert result == 100000000042

    def test_cross_listed_securities_get_different_ids(self, mock_impala):
        """ANZ AU and ANZ NZ must never share an ID."""
        anz_au = {'isin': 'AU000000ANZ3', 'exchange_code': 'ASX', 'country_of_exchange': 'AU', 'security_name': 'ANZ'}
        anz_nz = {'isin': 'AU000000ANZ3', 'exchange_code': 'NZX', 'country_of_exchange': 'NZ', 'security_name': 'ANZ'}

        # Both are registry misses; counter increments between calls
        mock_impala.execute_query.side_effect = [
            [],                              # AU: registry miss
            [{'next_id': 100000000001}],     # AU: counter → 1
            [],                              # NZ: registry miss
            [{'next_id': 100000000002}],     # NZ: counter → 2
        ]

        id_au = SecurityHiveRepository._get_or_allocate_security_id(anz_au, 'GMP', 'GMP_ETL')
        id_nz = SecurityHiveRepository._get_or_allocate_security_id(anz_nz, 'GMP', 'GMP_ETL')

        assert id_au == 100000000001
        assert id_nz == 100000000002
        assert id_au != id_nz

    def test_same_security_called_twice_hits_registry_second_time(self, mock_impala):
        """Idempotency: same natural key called again must return the same ID from registry."""
        mock_impala.execute_query.side_effect = [
            [],                              # first call: miss
            [{'next_id': 100000000005}],     # first call: counter
            [{'security_id': 100000000005}], # second call: registry hit
        ]

        id_first  = SecurityHiveRepository._get_or_allocate_security_id(SECURITY_DATA, 'CIS', 'u1')
        id_second = SecurityHiveRepository._get_or_allocate_security_id(SECURITY_DATA, 'CIS', 'u1')

        assert id_first == id_second == 100000000005
        # Write only happened once (first call only)
        assert mock_impala.execute_write.call_count == 2  # registry + counter on first call only

    def test_id_floor_is_12_digits(self):
        assert len(str(SecurityHiveRepository.ID_FLOOR)) == 12

    def test_gmp_src_system_stored_in_registry(self, mock_impala):
        """src_system='GMP' must appear in the registry UPSERT."""
        mock_impala.execute_query.side_effect = [[], [{'next_id': 100000000001}]]

        SecurityHiveRepository._get_or_allocate_security_id(SECURITY_DATA, src_system='GMP', created_by='GMP_ETL')

        registry_call = str(mock_impala.execute_write.call_args_list[0])
        assert 'GMP' in registry_call

    def test_cis_src_system_stored_in_registry(self, mock_impala):
        """src_system='CIS' must appear in the registry UPSERT."""
        mock_impala.execute_query.side_effect = [[], [{'next_id': 100000000001}]]

        SecurityHiveRepository._get_or_allocate_security_id(SECURITY_DATA, src_system='CIS', created_by='analyst')

        registry_call = str(mock_impala.execute_write.call_args_list[0])
        assert 'CIS' in registry_call
