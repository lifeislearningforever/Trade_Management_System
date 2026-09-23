"""Tests for edge_jobs_py36/lib/udf_field_repository.py."""
import hashlib
from unittest.mock import patch

import pytest

from edge_jobs_py36.lib.udf_field_repository import UDFFieldRepository, udf_field_repository


def _repo():
    return UDFFieldRepository()


class TestEscapeString:
    def test_none_returns_empty_string(self):
        assert _repo()._escape_string(None) == ''

    def test_escapes_single_quote(self):
        assert _repo()._escape_string("O'Brien") == "O\\'Brien"

    def test_plain_string_unchanged(self):
        assert _repo()._escape_string('ABC') == 'ABC'


class TestGenerateCompositeId:
    def test_deterministic_for_same_inputs(self):
        repo = _repo()
        a = repo._generate_composite_id('TRADE', 'Fund Type', 'Equity')
        b = repo._generate_composite_id('TRADE', 'Fund Type', 'Equity')
        assert a == b

    def test_matches_manual_md5(self):
        repo = _repo()
        expected = hashlib.md5('TRADE|Fund Type|Equity'.encode()).hexdigest()
        assert repo._generate_composite_id('TRADE', 'Fund Type', 'Equity') == expected

    def test_different_inputs_differ(self):
        repo = _repo()
        a = repo._generate_composite_id('TRADE', 'Fund Type', 'Equity')
        b = repo._generate_composite_id('TRADE', 'Fund Type', 'Bond')
        assert a != b


class TestGetObjectTypes:
    def test_returns_list_of_types(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'object_type': 'TRADE'}, {'object_type': 'PORTFOLIO'}]
            result = repo.get_object_types()
        assert result == ['TRADE', 'PORTFOLIO']

    def test_returns_empty_list_when_none(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert repo.get_object_types() == []

    def test_returns_empty_list_on_exception(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_object_types() == []

    def test_query_filters_definitions_only_and_active(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_object_types()
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'is_active = true' in query
        assert "field_value = ''" in query


class TestGetFieldsByEntity:
    def test_returns_field_name_dicts(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'field_name': 'Fund Type'}]
            result = repo.get_fields_by_entity('TRADE')
        assert result == [{'field_name': 'Fund Type'}]

    def test_returns_empty_list_when_none(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert repo.get_fields_by_entity('TRADE') == []

    def test_escapes_object_type_in_query(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_fields_by_entity("O'BRIEN")
        query = mock_mgr.execute_query.call_args[0][0]
        assert "O\\'BRIEN" in query

    def test_returns_empty_list_on_exception(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_fields_by_entity('TRADE') == []


class TestGetFieldValues:
    def test_returns_results(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'field_value': 'Equity'}]
            result = repo.get_field_values('TRADE', 'Fund Type')
        assert result == [{'field_value': 'Equity'}]

    def test_returns_empty_list_when_no_results(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert repo.get_field_values('TRADE', 'Fund Type') == []

    def test_returns_empty_list_on_exception(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_field_values('TRADE', 'Fund Type') == []

    def test_query_excludes_empty_field_values(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_field_values('TRADE', 'Fund Type')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "field_value != ''" in query


class TestGetAll:
    def test_returns_results_with_generated_udf_id(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'Equity'},
            ]
            result = repo.get_all()
        assert 'udf_id' in result[0]

    def test_returns_empty_list_when_none(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert repo.get_all() == []

    def test_filters_by_object_type_when_given(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_all(object_type='TRADE')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "object_type = 'TRADE'" in query

    def test_filters_by_is_active_true(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_all(is_active=True)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'is_active = true' in query

    def test_filters_by_is_active_false(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_all(is_active=False)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'is_active = false' in query

    def test_no_is_active_filter_when_none(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_all(is_active=None)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'is_active = true' not in query
        assert 'is_active = false' not in query

    def test_returns_empty_list_on_exception(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_all() == []


class TestGetByKey:
    def test_returns_record_with_udf_id(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'Equity'},
            ]
            result = repo.get_by_key('TRADE', 'Fund Type', 'Equity')
        assert result['udf_id']

    def test_returns_none_when_no_match(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert repo.get_by_key('TRADE', 'Fund Type', 'Equity') is None

    def test_returns_none_on_exception(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_by_key('TRADE', 'Fund Type', 'Equity') is None


class TestGetById:
    def test_returns_matching_record(self):
        repo = _repo()
        record = {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'Equity'}
        target_id = repo._generate_composite_id('TRADE', 'Fund Type', 'Equity')
        with patch.object(repo, 'get_all', return_value=[dict(record, udf_id=target_id)]):
            result = repo.get_by_id(target_id)
        assert result['object_type'] == 'TRADE'

    def test_returns_none_when_no_match(self):
        repo = _repo()
        with patch.object(repo, 'get_all', return_value=[]):
            assert repo.get_by_id('nonexistent') is None

    def test_returns_none_on_exception(self):
        repo = _repo()
        with patch.object(repo, 'get_all', side_effect=RuntimeError('boom')):
            assert repo.get_by_id('any') is None

    def test_includes_inactive_records(self):
        repo = _repo()
        with patch.object(repo, 'get_all') as mock_get_all:
            mock_get_all.return_value = []
            repo.get_by_id('any')
        assert mock_get_all.call_args[1]['is_active'] is None


class TestCreate:
    def test_missing_required_field_returns_none(self):
        repo = _repo()
        result = repo.create({'object_type': 'TRADE'})  # missing field_name, created_by
        assert result is None

    def test_successful_create_returns_udf_id(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = repo.create({
                'object_type': 'TRADE', 'field_name': 'Fund Type',
                'field_value': 'Equity', 'created_by': 'jdoe',
            })
        assert result is not None

    def test_returns_none_when_write_fails(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = False
            result = repo.create({
                'object_type': 'TRADE', 'field_name': 'Fund Type', 'created_by': 'jdoe',
            })
        assert result is None

    def test_updated_by_defaults_to_created_by(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            repo.create({'object_type': 'TRADE', 'field_name': 'Fund Type', 'created_by': 'jdoe'})
        sql = mock_mgr.execute_write.call_args[0][0]
        assert sql.count("'jdoe'") == 2

    def test_is_active_defaults_to_true(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            repo.create({'object_type': 'TRADE', 'field_name': 'Fund Type', 'created_by': 'jdoe'})
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'true' in sql

    def test_returns_none_on_exception(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            result = repo.create({'object_type': 'TRADE', 'field_name': 'Fund Type', 'created_by': 'jdoe'})
        assert result is None


class TestUpdate:
    def test_returns_false_when_id_not_found(self):
        repo = _repo()
        with patch.object(repo, 'get_by_id', return_value=None):
            assert repo.update('bad-id', {'updated_by': 'jdoe'}) is False

    def test_successful_update_returns_true(self):
        repo = _repo()
        existing = {
            'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'Equity',
            'is_active': True, 'created_by': 'jdoe', 'created_at': '2026-01-01 00:00:00',
        }
        with patch.object(repo, 'get_by_id', return_value=existing), \
             patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = repo.update('some-id', {'updated_by': 'jdoe2'})
        assert result is True

    def test_preserves_existing_composite_key(self):
        repo = _repo()
        existing = {
            'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'Equity',
            'is_active': True, 'created_by': 'jdoe', 'created_at': '2026-01-01 00:00:00',
        }
        with patch.object(repo, 'get_by_id', return_value=existing), \
             patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            repo.update('some-id', {'updated_by': 'jdoe2'})
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'TRADE'" in sql
        assert "'Fund Type'" in sql
        assert "'Equity'" in sql

    def test_returns_false_on_exception(self):
        repo = _repo()
        with patch.object(repo, 'get_by_id', side_effect=RuntimeError('boom')):
            assert repo.update('some-id', {}) is False


class TestSoftDelete:
    def test_returns_false_when_not_found(self):
        repo = _repo()
        with patch.object(repo, 'get_by_id', return_value=None):
            assert repo.soft_delete('bad-id', 'jdoe') is False

    def test_calls_update_with_is_active_false(self):
        repo = _repo()
        with patch.object(repo, 'get_by_id', return_value={'object_type': 'TRADE'}), \
             patch.object(repo, 'update', return_value=True) as mock_update:
            result = repo.soft_delete('some-id', 'jdoe')
        assert result is True
        args = mock_update.call_args[0]
        assert args[1]['is_active'] is False
        assert args[1]['updated_by'] == 'jdoe'

    def test_returns_false_on_exception(self):
        repo = _repo()
        with patch.object(repo, 'get_by_id', side_effect=RuntimeError('boom')):
            assert repo.soft_delete('some-id', 'jdoe') is False


class TestRestore:
    def test_returns_false_when_not_found(self):
        repo = _repo()
        with patch.object(repo, 'get_by_id', return_value=None):
            assert repo.restore('bad-id', 'jdoe') is False

    def test_calls_update_with_is_active_true(self):
        repo = _repo()
        with patch.object(repo, 'get_by_id', return_value={'object_type': 'TRADE'}), \
             patch.object(repo, 'update', return_value=True) as mock_update:
            result = repo.restore('some-id', 'jdoe')
        assert result is True
        args = mock_update.call_args[0]
        assert args[1]['is_active'] is True

    def test_returns_false_on_exception(self):
        repo = _repo()
        with patch.object(repo, 'get_by_id', side_effect=RuntimeError('boom')):
            assert repo.restore('some-id', 'jdoe') is False


class TestAddFieldDefinition:
    def test_creates_with_empty_field_value(self):
        repo = _repo()
        with patch.object(repo, 'create', return_value='hash-id') as mock_create:
            result = repo.add_field_definition('TRADE', 'Fund Type', 'jdoe')
        assert result is True
        assert mock_create.call_args[0][0]['field_value'] == ''

    def test_returns_false_when_create_returns_none(self):
        repo = _repo()
        with patch.object(repo, 'create', return_value=None):
            assert repo.add_field_definition('TRADE', 'Fund Type', 'jdoe') is False


class TestAddFieldValue:
    def test_raises_on_empty_field_value(self):
        repo = _repo()
        with pytest.raises(ValueError, match='field_value cannot be empty'):
            repo.add_field_value('TRADE', 'Fund Type', '', 'jdoe')

    def test_creates_with_given_field_value(self):
        repo = _repo()
        with patch.object(repo, 'create', return_value='hash-id') as mock_create:
            result = repo.add_field_value('TRADE', 'Fund Type', 'Equity', 'jdoe')
        assert result is True
        assert mock_create.call_args[0][0]['field_value'] == 'Equity'


class TestGetNextId:
    def test_returns_int(self):
        repo = _repo()
        assert isinstance(repo.get_next_id(), int)


class TestUpdateById:
    def test_delegates_to_update(self):
        repo = _repo()
        with patch.object(repo, 'update', return_value=True) as mock_update:
            result = repo.update_by_id('some-id', {'updated_by': 'jdoe'})
        assert result is True
        mock_update.assert_called_once_with('some-id', {'updated_by': 'jdoe'})


class TestGetStatsByEntity:
    def test_delegates_to_get_dashboard_stats(self):
        repo = _repo()
        with patch.object(repo, 'get_dashboard_stats', return_value=[{'object_type': 'TRADE'}]) as mock_stats:
            result = repo.get_stats_by_entity()
        assert result == [{'object_type': 'TRADE'}]
        mock_stats.assert_called_once()


class TestGetDashboardStats:
    def test_returns_stats_list(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'object_type': 'TRADE', 'total_fields': 10, 'active_fields': 8, 'inactive_fields': 2},
            ]
            result = repo.get_dashboard_stats()
        assert result[0]['total_fields'] == 10

    def test_returns_empty_list_when_none(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert repo.get_dashboard_stats() == []

    def test_handles_null_counts_as_zero(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'object_type': 'TRADE', 'total_fields': None, 'active_fields': None, 'inactive_fields': None},
            ]
            result = repo.get_dashboard_stats()
        assert result[0]['total_fields'] == 0

    def test_returns_empty_list_on_exception(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.udf_field_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_dashboard_stats() == []


class TestSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(udf_field_repository, UDFFieldRepository)
