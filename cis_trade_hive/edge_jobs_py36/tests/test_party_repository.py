"""Tests for edge_jobs_py36/lib/party_repository.py."""
from unittest.mock import patch

from edge_jobs_py36.lib.party_repository import PartyRepository, party_repository


class TestEscapeSql:
    def test_none_returns_empty_string(self):
        assert PartyRepository._escape_sql(None) == ''

    def test_plain_string_unchanged(self):
        assert PartyRepository._escape_sql('ABC') == 'ABC'

    def test_escapes_single_quote(self):
        assert PartyRepository._escape_sql("O'Brien") == "O\\'Brien"

    def test_escapes_backslash(self):
        assert PartyRepository._escape_sql('a\\b') == 'a\\\\b'

    def test_converts_non_string_to_string(self):
        assert PartyRepository._escape_sql(42) == '42'


class TestUpsertRequiredField:
    def test_always_includes_party_short_name_column(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'party_short_name' in query
        assert "'ACME'" in query

    def test_missing_party_short_name_defaults_to_empty(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = PartyRepository.upsert({})
        assert result is True
        query = mock_mgr.execute_write.call_args[0][0]
        assert "''" in query


class TestUpsertStringFields:
    def test_string_field_present_is_quoted(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'city': 'Singapore'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert "'Singapore'" in query

    def test_string_field_none_becomes_null(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'city': None})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'city' in query
        assert 'NULL' in query

    def test_string_field_empty_string_becomes_null(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'city': ''})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'NULL' in query

    def test_string_field_absent_is_not_included(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'address_line_0' not in query

    def test_string_field_with_quote_is_escaped(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'party_full_name': "O'Brien Ltd"})
        query = mock_mgr.execute_write.call_args[0][0]
        assert "O\\'Brien Ltd" in query

    def test_string_field_non_string_value_is_stringified(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'processing_date': 20260917})
        query = mock_mgr.execute_write.call_args[0][0]
        assert "'20260917'" in query


class TestUpsertBooleanFields:
    def test_boolean_true_becomes_true_literal(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'is_broker': True})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'TRUE' in query

    def test_boolean_false_becomes_false_literal(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'is_broker': False})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'FALSE' in query

    def test_boolean_string_true_is_uppercased(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'is_custodian': 'true'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'TRUE' in query

    def test_boolean_string_false_is_uppercased(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'is_custodian': 'false'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'FALSE' in query

    def test_boolean_invalid_value_defaults_to_false(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'is_bank': 'maybe'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'is_bank' in query
        assert 'FALSE' in query

    def test_boolean_field_absent_not_included(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'is_broker' not in query

    def test_boolean_field_int_value_defaults_to_false(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'is_active': 1})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'is_active' in query


class TestUpsertTimestampFields:
    def test_created_at_present_uses_now_function(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'created_at': 'ignored-value'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'created_at' in query
        assert 'NOW()' in query

    def test_updated_at_present_uses_now_function(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME', 'updated_at': 'ignored-value'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'updated_at' in query
        assert 'NOW()' in query

    def test_timestamp_fields_absent_not_included(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'created_at' not in query
        assert 'updated_at' not in query


class TestUpsertQueryStructure:
    def test_query_contains_upsert_and_table(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'UPSERT INTO' in query
        assert 'cis_party' in query

    def test_execute_write_called_with_database_kwarg(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyRepository.upsert({'party_short_name': 'ACME'})
        kwargs = mock_mgr.execute_write.call_args[1]
        assert kwargs.get('database') == PartyRepository.DATABASE


class TestUpsertOutcomes:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert PartyRepository.upsert({'party_short_name': 'ACME'}) is True

    def test_returns_false_on_write_failure(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = False
            assert PartyRepository.upsert({'party_short_name': 'ACME'}) is False

    def test_returns_false_and_swallows_exception(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert PartyRepository.upsert({'party_short_name': 'ACME'}) is False


class TestSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(party_repository, PartyRepository)

    def test_singleton_upsert_works(self):
        with patch('edge_jobs_py36.lib.party_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert party_repository.upsert({'party_short_name': 'ACME'}) is True
