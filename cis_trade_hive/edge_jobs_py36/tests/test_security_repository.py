"""Tests for edge_jobs_py36/lib/security_repository.py."""
from unittest.mock import patch

from edge_jobs_py36.lib.security_repository import SecurityRepository, security_repository


class TestEscapeValue:
    def test_none_returns_null(self):
        assert SecurityRepository.escape_value(None) == 'NULL'

    def test_empty_string_returns_null(self):
        assert SecurityRepository.escape_value('') == 'NULL'

    def test_true_returns_lowercase_true(self):
        assert SecurityRepository.escape_value(True) == 'true'

    def test_false_returns_lowercase_false(self):
        assert SecurityRepository.escape_value(False) == 'false'

    def test_int_returns_unquoted_string(self):
        assert SecurityRepository.escape_value(42) == '42'

    def test_float_returns_unquoted_string(self):
        assert SecurityRepository.escape_value(3.14) == '3.14'

    def test_string_is_quoted(self):
        assert SecurityRepository.escape_value('ACME') == "'ACME'"

    def test_string_with_quote_is_escaped(self):
        assert SecurityRepository.escape_value("O'Brien") == "'O\\'Brien'"

    def test_string_with_backslash_is_escaped(self):
        assert SecurityRepository.escape_value('a\\b') == "'a\\\\b'"

    def test_zero_int_is_not_null(self):
        """0 is falsy but must not collapse to NULL like '' or None."""
        assert SecurityRepository.escape_value(0) == '0'


class TestGetSecurityByIsin:
    def test_returns_first_result_row(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'isin': 'US0378331005', 'security_name': 'APPLE'}]
            result = SecurityRepository.get_security_by_isin('US0378331005')
        assert result['security_name'] == 'APPLE'

    def test_returns_none_when_no_rows(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = SecurityRepository.get_security_by_isin('UNKNOWN')
        assert result is None

    def test_returns_none_on_exception(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = SecurityRepository.get_security_by_isin('US0378331005')
        assert result is None

    def test_query_uses_escaped_isin(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            SecurityRepository.get_security_by_isin("O'BRIEN")
        query = mock_mgr.execute_query.call_args[0][0]
        assert "O\\'BRIEN" in query


class TestBuildNaturalKey:
    def test_isin_and_exchange_takes_priority(self):
        key, key_type = SecurityRepository._build_natural_key({
            'isin': 'us0378331005', 'exchange_code': 'nasdaq', 'country_of_exchange': 'US',
        })
        assert key == 'ISIN_EXCH:US0378331005:NASDAQ'
        assert key_type == 'ISIN_EXCH'

    def test_isin_and_country_when_no_exchange(self):
        key, key_type = SecurityRepository._build_natural_key({
            'isin': 'us0378331005', 'country_of_exchange': 'us',
        })
        assert key == 'ISIN_CTY:US0378331005:US'
        assert key_type == 'ISIN_CTY'

    def test_isin_only_when_no_exchange_or_country(self):
        key, key_type = SecurityRepository._build_natural_key({'isin': 'us0378331005'})
        assert key == 'ISIN:US0378331005'
        assert key_type == 'ISIN'

    def test_name_and_exchange_when_no_isin(self):
        key, key_type = SecurityRepository._build_natural_key({
            'security_name': 'apple inc', 'exchange_code': 'nasdaq',
        })
        assert key == 'NAME_EXCH:APPLE INC:NASDAQ'
        assert key_type == 'NAME_EXCH'

    def test_name_and_country_when_no_isin_or_exchange(self):
        key, key_type = SecurityRepository._build_natural_key({
            'security_name': 'apple inc', 'country_of_exchange': 'us',
        })
        assert key == 'NAME_CTY:APPLE INC:US'
        assert key_type == 'NAME_CTY'

    def test_name_only_as_last_resort(self):
        key, key_type = SecurityRepository._build_natural_key({'security_name': 'apple inc'})
        assert key == 'NAME:APPLE INC'
        assert key_type == 'NAME'

    def test_completely_empty_data_produces_empty_name_key(self):
        key, key_type = SecurityRepository._build_natural_key({})
        assert key == 'NAME:'
        assert key_type == 'NAME'

    def test_whitespace_is_stripped_and_uppercased(self):
        key, key_type = SecurityRepository._build_natural_key({'isin': '  us0378331005  '})
        assert key == 'ISIN:US0378331005'


class TestGetOrAllocateSecurityId:
    def test_returns_existing_id_on_registry_hit(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            result = SecurityRepository.get_or_allocate_security_id(
                {'isin': 'US0378331005'}, 'GMP', 'GMP_ETL'
            )
        assert result == 100000000123
        mock_mgr.execute_write.assert_not_called()

    def test_allocates_new_id_from_counter_on_registry_miss(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [
                [],  # registry miss
                [{'next_id': 100000000500}],  # counter hit
            ]
            mock_mgr.execute_write.return_value = True
            result = SecurityRepository.get_or_allocate_security_id(
                {'isin': 'US0378331005'}, 'GMP', 'GMP_ETL'
            )
        assert result == 100000000500

    def test_falls_back_to_id_floor_when_counter_missing(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [[], []]
            mock_mgr.execute_write.return_value = True
            result = SecurityRepository.get_or_allocate_security_id(
                {'isin': 'US0378331005'}, 'GMP', 'GMP_ETL'
            )
        assert result == SecurityRepository.ID_FLOOR + 1

    def test_writes_registry_and_advances_counter_on_miss(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [[], [{'next_id': 100000000500}]]
            mock_mgr.execute_write.return_value = True
            SecurityRepository.get_or_allocate_security_id(
                {'isin': 'US0378331005', 'security_name': 'APPLE'}, 'GMP', 'GMP_ETL'
            )
        assert mock_mgr.execute_write.call_count == 2
        registry_sql = mock_mgr.execute_write.call_args_list[0][0][0]
        counter_sql = mock_mgr.execute_write.call_args_list[1][0][0]
        assert 'cis_security_id_registry' in registry_sql
        assert '100000000500' in registry_sql
        assert 'cis_security_id_counter' in counter_sql
        assert '100000000501' in counter_sql  # advanced by 1

    def test_registry_write_handles_missing_optional_fields_as_null(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [[], []]
            mock_mgr.execute_write.return_value = True
            SecurityRepository.get_or_allocate_security_id(
                {'security_name': 'NO ISIN CO'}, 'GMP', 'GMP_ETL'
            )
        registry_sql = mock_mgr.execute_write.call_args_list[0][0][0]
        assert 'NULL' in registry_sql


class TestUpsertSecurity:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            mock_mgr.execute_write.return_value = True
            result = SecurityRepository.upsert_security(
                {'isin': 'US0378331005', 'security_name': 'APPLE'}, 'GMP_ETL'
            )
        assert result is True

    def test_includes_allocated_security_id_in_query(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            mock_mgr.execute_write.return_value = True
            SecurityRepository.upsert_security(
                {'isin': 'US0378331005', 'security_name': 'APPLE'}, 'GMP_ETL'
            )
        upsert_sql = mock_mgr.execute_write.call_args[0][0]
        assert '100000000123' in upsert_sql
        assert 'cis_security' in upsert_sql

    def test_includes_mapped_fields_present_in_data(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            mock_mgr.execute_write.return_value = True
            SecurityRepository.upsert_security(
                {'isin': 'US0378331005', 'security_name': 'APPLE', 'ticker': 'AAPL'}, 'GMP_ETL'
            )
        upsert_sql = mock_mgr.execute_write.call_args[0][0]
        assert 'ticker' in upsert_sql
        assert "'AAPL'" in upsert_sql

    def test_excludes_unmapped_fields_not_present_in_data(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            mock_mgr.execute_write.return_value = True
            SecurityRepository.upsert_security(
                {'isin': 'US0378331005', 'security_name': 'APPLE'}, 'GMP_ETL'
            )
        upsert_sql = mock_mgr.execute_write.call_args[0][0]
        assert 'beta' not in upsert_sql

    def test_status_defaults_to_validated(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            mock_mgr.execute_write.return_value = True
            SecurityRepository.upsert_security({'isin': 'X'}, 'GMP_ETL')
        upsert_sql = mock_mgr.execute_write.call_args[0][0]
        assert "'VALIDATED'" in upsert_sql

    def test_src_system_defaults_to_gmp(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            mock_mgr.execute_write.return_value = True
            SecurityRepository.upsert_security({'isin': 'X'}, 'GMP_ETL')
        upsert_sql = mock_mgr.execute_write.call_args[0][0]
        assert "'GMP'" in upsert_sql

    def test_is_active_defaults_to_true(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            mock_mgr.execute_write.return_value = True
            SecurityRepository.upsert_security({'isin': 'X'}, 'GMP_ETL')
        upsert_sql = mock_mgr.execute_write.call_args[0][0]
        assert 'true' in upsert_sql

    def test_is_active_explicit_false_is_respected(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            mock_mgr.execute_write.return_value = True
            SecurityRepository.upsert_security({'isin': 'X', 'is_active': False}, 'GMP_ETL')
        upsert_sql = mock_mgr.execute_write.call_args[0][0]
        assert 'false' in upsert_sql

    def test_created_by_appears_for_created_by_and_updated_by(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            mock_mgr.execute_write.return_value = True
            SecurityRepository.upsert_security({'isin': 'X'}, 'jdoe')
        upsert_sql = mock_mgr.execute_write.call_args[0][0]
        assert upsert_sql.count("'jdoe'") == 2

    def test_returns_false_on_exception_during_allocation(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = SecurityRepository.upsert_security({'isin': 'X'}, 'GMP_ETL')
        assert result is False

    def test_returns_false_when_write_fails(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            mock_mgr.execute_write.return_value = False
            result = SecurityRepository.upsert_security({'isin': 'X'}, 'GMP_ETL')
        assert result is False


class TestSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(security_repository, SecurityRepository)

    def test_singleton_upsert_works(self):
        with patch('edge_jobs_py36.lib.security_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_id': 100000000123}]
            mock_mgr.execute_write.return_value = True
            result = security_repository.upsert_security({'isin': 'X'}, 'GMP_ETL')
        assert result is True
