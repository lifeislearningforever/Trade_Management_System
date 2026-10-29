"""Tests for edge_jobs_py36/lib/party_cif_repository.py."""
from unittest.mock import patch

from edge_jobs_py36.lib.party_cif_repository import PartyCifRepository, party_cif_repository


class TestEscapeSql:
    def test_none_returns_empty_string(self):
        assert PartyCifRepository._escape_sql(None) == ''

    def test_escapes_single_quote(self):
        assert PartyCifRepository._escape_sql("O'Brien") == "O\\'Brien"

    def test_escapes_backslash(self):
        assert PartyCifRepository._escape_sql('a\\b') == 'a\\\\b'


class TestUpsertCompositeKey:
    def test_includes_party_name_m_label_country(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'country': 'SG'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert "'ACME'" in query
        assert "'SG'" in query

    def test_m_label_auto_generated_from_party_name_and_country(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'country': 'SG'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert "'ACME_SG'" in query

    def test_m_label_falls_back_to_party_name_only_when_no_country(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert "'ACME'" in query

    def test_explicit_m_label_is_used_verbatim(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'country': 'SG', 'm_label': 'CUSTOM_LABEL'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert "'CUSTOM_LABEL'" in query
        assert "'ACME_SG'" not in query

    def test_missing_party_name_defaults_to_empty(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = PartyCifRepository.upsert({'country': 'SG'})
        assert result is True

    def test_missing_country_defaults_to_empty(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = PartyCifRepository.upsert({'party_name': 'ACME'})
        assert result is True


class TestUpsertStringFields:
    def test_isin_field_present_is_quoted(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'isin': 'US0378331005'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert "'US0378331005'" in query

    def test_string_field_none_becomes_null(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'description': None})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'NULL' in query

    def test_string_field_empty_string_becomes_null(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'description': ''})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'NULL' in query

    def test_string_field_absent_not_included(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'src_system' not in query

    def test_string_field_with_quote_is_escaped(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'description': "O'Brien"})
        query = mock_mgr.execute_write.call_args[0][0]
        assert "O\\'Brien" in query

    def test_string_field_non_string_value_is_stringified(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'processing_date': 20260917})
        query = mock_mgr.execute_write.call_args[0][0]
        assert "'20260917'" in query


class TestUpsertBooleanFields:
    def test_is_active_true_becomes_true_literal(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'is_active': True})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'TRUE' in query

    def test_is_active_false_becomes_false_literal(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'is_active': False})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'FALSE' in query

    def test_is_deleted_string_true_is_uppercased(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'is_deleted': 'true'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'TRUE' in query

    def test_boolean_invalid_value_defaults_to_false(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'is_deleted': 'unknown'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'FALSE' in query

    def test_is_active_defaults_to_true_when_absent(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'is_active' in query
        assert 'TRUE' in query

    def test_is_deleted_defaults_to_false_when_absent(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'is_deleted' in query
        assert 'FALSE' in query

    def test_explicit_is_active_and_is_deleted_are_respected(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME', 'is_active': False, 'is_deleted': True})
        query = mock_mgr.execute_write.call_args[0][0]
        # both booleans reflect explicit values, not the defaults
        assert query.count('is_active') == 1
        assert query.count('is_deleted') == 1


class TestUpsertTimestamps:
    def test_created_at_and_updated_at_always_use_now(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'created_at' in query
        assert 'updated_at' in query
        assert query.count('NOW()') == 2


class TestUpsertQueryStructure:
    def test_query_contains_upsert_and_table(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME'})
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'UPSERT INTO' in query
        assert 'cis_party_cif' in query

    def test_execute_write_called_with_database_kwarg(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            PartyCifRepository.upsert({'party_name': 'ACME'})
        kwargs = mock_mgr.execute_write.call_args[1]
        assert kwargs.get('database') == PartyCifRepository.DATABASE


class TestUpsertOutcomes:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert PartyCifRepository.upsert({'party_name': 'ACME'}) is True

    def test_returns_false_on_write_failure(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = False
            assert PartyCifRepository.upsert({'party_name': 'ACME'}) is False

    def test_returns_false_and_swallows_exception(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert PartyCifRepository.upsert({'party_name': 'ACME'}) is False


class TestSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(party_cif_repository, PartyCifRepository)

    def test_singleton_upsert_works(self):
        with patch('edge_jobs_py36.lib.party_cif_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert party_cif_repository.upsert({'party_name': 'ACME'}) is True
