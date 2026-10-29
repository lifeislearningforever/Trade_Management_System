"""Tests for edge_jobs_py36/lib/corporate_action_repository.py."""
from decimal import Decimal
from unittest.mock import patch

from edge_jobs_py36.lib.corporate_action_repository import (
    CorporateActionRepository as R,
    corporate_action_repository,
)


class TestEscapeValue:
    def test_none_returns_null(self):
        assert R.escape_value(None) == 'NULL'

    def test_empty_string_returns_null(self):
        assert R.escape_value('') == 'NULL'

    def test_bool_true(self):
        assert R.escape_value(True) == 'true'

    def test_bool_false(self):
        assert R.escape_value(False) == 'false'

    def test_int_unquoted(self):
        assert R.escape_value(42) == '42'

    def test_float_unquoted(self):
        assert R.escape_value(1.5) == '1.5'

    def test_decimal_unquoted(self):
        assert R.escape_value(Decimal('2.75')) == '2.75'

    def test_numeric_looking_string_unquoted(self):
        assert R.escape_value('123.45') == '123.45'

    def test_negative_numeric_string_unquoted(self):
        assert R.escape_value('-5.5') == '-5.5'

    def test_non_numeric_string_quoted_and_escaped(self):
        assert R.escape_value("O'Brien") == "'O\\'Brien'"


class TestGetAll:
    def test_returns_results(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'ca_id': 1}]
            result = R.get_all()
        assert len(result) == 1

    def test_returns_empty_list_when_none(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert R.get_all() == []

    def test_excludes_deleted_by_default(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all()
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'is_deleted = false' in query

    def test_includes_deleted_when_requested(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(include_deleted=True)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'is_deleted = false' not in query

    def test_status_filter_applied(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(status='VALIDATED')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "status = 'VALIDATED'" in query

    def test_search_filter_applied_to_both_columns(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(search='AAPL')
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'ca_number' in query
        assert 'security_name' in query
        assert '%AAPL%' in query

    def test_ca_type_filter_applied(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(ca_type='CASH_DIVIDEND')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "ca_type = 'CASH_DIVIDEND'" in query

    def test_security_name_filter_applied(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(security_name='AAPL')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "security_name = 'AAPL'" in query

    def test_offset_applied_when_positive(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(offset=20)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'OFFSET 20' in query

    def test_offset_not_applied_when_zero(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(offset=0)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'OFFSET' not in query

    def test_limit_applied(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(limit=50)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 50' in query

    def test_returns_empty_list_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_all() == []


class TestGetById:
    def test_returns_first_result(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'ca_id': 1}]
            assert R.get_by_id(1) == {'ca_id': 1}

    def test_returns_none_when_empty(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert R.get_by_id(1) is None

    def test_returns_none_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_by_id(1) is None


class TestGetByCaNumber:
    def test_returns_first_result(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'ca_number': 'GMP-1'}]
            assert R.get_by_ca_number('GMP-1') == {'ca_number': 'GMP-1'}

    def test_returns_none_when_empty(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert R.get_by_ca_number('GMP-1') is None

    def test_returns_none_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_by_ca_number('GMP-1') is None


class TestGetPendingApprovals:
    def test_returns_results(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'ca_id': 1}]
            assert len(R.get_pending_approvals()) == 1

    def test_query_filters_initial_and_modified(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_pending_approvals()
        query = mock_mgr.execute_query.call_args[0][0]
        assert "'INITIAL'" in query
        assert "'MODIFIED'" in query

    def test_returns_empty_list_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_pending_approvals() == []


class TestInsert:
    def _ca_data(self, **overrides):
        data = {
            'ca_number': 'GMP-1', 'ca_type': 'CASH_DIVIDEND', 'security_name': 'AAPL',
            'ex_date': '2026-09-17', 'price': '0.25', 'currency': 'USD',
        }
        data.update(overrides)
        return data

    def test_returns_true_and_ca_id_on_success(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            success, ca_id = R.insert(self._ca_data(), created_by='jdoe')
        assert success is True
        assert isinstance(ca_id, int)

    def test_returns_false_none_when_write_fails(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = False
            success, ca_id = R.insert(self._ca_data(), created_by='jdoe')
        assert success is False
        assert ca_id is None

    def test_returns_false_none_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            success, ca_id = R.insert(self._ca_data(), created_by='jdoe')
        assert success is False
        assert ca_id is None

    def test_only_present_and_non_empty_fields_included(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert({'ca_number': 'GMP-1'}, created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'ca_type' not in sql
        assert 'ca_number' in sql

    def test_price_rounded_to_seven_decimals(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert(self._ca_data(price='0.123456789'), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert '0.1234568' in sql

    def test_invalid_price_becomes_null(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert(self._ca_data(price='not-a-number'), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'NULL' in sql

    def test_status_defaults_to_initial(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert(self._ca_data(), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'INITIAL'" in sql

    def test_explicit_status_respected(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert(self._ca_data(status='VALIDATED'), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'VALIDATED'" in sql

    def test_src_system_defaults_to_cis_when_absent(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert(self._ca_data(), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'CIS'" in sql

    def test_explicit_src_system_respected(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert(self._ca_data(src_system='GMP'), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'GMP'" in sql

    def test_is_active_true_is_deleted_false(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert(self._ca_data(), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'true' in sql
        assert 'false' in sql


class TestUpdate:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert R.update(1, {'ca_type': 'INTEREST'}, updated_by='jdoe') is True

    def test_unrelated_fields_ignored_but_audit_fields_still_written(self):
        """update() always appends updated_by/updated_at to set_clauses, so the
        'no fields to update' guard is unreachable in practice -- a call with
        only an unknown field still issues a write, touching audit fields only."""
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = R.update(1, {'unrelated_field': 'x'}, updated_by='jdoe')
        assert result is True
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'unrelated_field' not in sql
        assert 'updated_by' in sql

    def test_always_updates_audit_fields(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update(1, {'ca_type': 'INTEREST'}, updated_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'updated_by' in sql
        assert 'updated_at' in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert R.update(1, {'ca_type': 'INTEREST'}, updated_by='jdoe') is False


class TestUpdateStatus:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert R.update_status(1, 'VALIDATED', updated_by='jdoe') is True

    def test_includes_reviewed_by_and_at(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'VALIDATED', updated_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'reviewed_by' in sql
        assert 'reviewed_at' in sql

    def test_includes_reviewed_comments_when_given(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'VALIDATED', updated_by='jdoe', reviewed_comments='looks good')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'looks good' in sql

    def test_validated_status_sets_is_active_true(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'VALIDATED', updated_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'is_active = true' in sql

    def test_non_validated_status_does_not_touch_is_active(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'REJECTED', updated_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'is_active = true' not in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert R.update_status(1, 'VALIDATED', updated_by='jdoe') is False


class TestSoftDelete:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert R.soft_delete(1, deleted_by='jdoe') is True

    def test_sets_is_deleted_true_is_active_false(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.soft_delete(1, deleted_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'is_deleted = true' in sql
        assert 'is_active = false' in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert R.soft_delete(1, deleted_by='jdoe') is False


class TestRestore:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert R.restore(1, restored_by='jdoe') is True

    def test_sets_status_to_modified(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.restore(1, restored_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "status = 'MODIFIED'" in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert R.restore(1, restored_by='jdoe') is False


class TestGetStatistics:
    def test_returns_aggregated_counts(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [
                [{'status': 'VALIDATED', 'count': 5}, {'status': 'INITIAL', 'count': 2}],
                [{'ca_type': 'CASH_DIVIDEND', 'count': 4}],
            ]
            stats = R.get_statistics()
        assert stats['total'] == 7
        assert stats['validated'] == 5
        assert stats['pending_approval'] == 2
        assert stats['by_type'] == [{'ca_type': 'CASH_DIVIDEND', 'count': 4}]

    def test_returns_zeroed_defaults_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            stats = R.get_statistics()
        assert stats['total'] == 0
        assert stats['by_type'] == []

    def test_handles_empty_status_results(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [None, None]
            stats = R.get_statistics()
        assert stats['total'] == 0
        assert stats['status_breakdown'] == {}


class TestInsertHistory:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = R.insert_history(1, 'GMP-1', 'AAPL', 'CREATE', 'INITIAL', {}, 'note', 'jdoe')
        assert result is True

    def test_changes_serialized_as_json(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert_history(1, 'GMP-1', 'AAPL', 'UPDATE', 'MODIFIED', {'ca_type': 'INTEREST'}, 'note', 'jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'ca_type' in sql

    def test_empty_changes_becomes_empty_json_object(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert_history(1, 'GMP-1', 'AAPL', 'CREATE', 'INITIAL', {}, 'note', 'jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert '{}' in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            result = R.insert_history(1, 'GMP-1', 'AAPL', 'CREATE', 'INITIAL', {}, 'note', 'jdoe')
        assert result is False


class TestGetHistory:
    def test_returns_results(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'history_id': 1}]
            assert len(R.get_history(1)) == 1

    def test_returns_empty_list_when_none(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert R.get_history(1) == []

    def test_returns_empty_list_on_exception(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_history(1) == []

    def test_limit_applied(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_history(1, limit=10)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 10' in query


class TestGenerateCaNumber:
    def test_first_of_the_day_is_sequence_one(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = R.generate_ca_number()
        assert result.endswith('00001')

    def test_increments_from_last_sequence(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            from datetime import datetime
            today = datetime.now().strftime('%Y%m%d')
            mock_mgr.execute_query.return_value = [{'ca_number': f'CA-{today}-00007'}]
            result = R.generate_ca_number()
        assert result.endswith('00008')

    def test_unparseable_last_number_resets_to_one(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'ca_number': 'garbage-format'}]
            result = R.generate_ca_number()
        assert result.endswith('00001')

    def test_empty_last_number_resets_to_one(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'ca_number': ''}]
            result = R.generate_ca_number()
        assert result.endswith('00001')

    def test_exception_falls_back_to_timestamp_format(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = R.generate_ca_number()
        assert result.startswith('CA-')

    def test_result_uses_today_date_prefix(self):
        with patch('edge_jobs_py36.lib.corporate_action_repository.impala_manager') as mock_mgr:
            from datetime import datetime
            today = datetime.now().strftime('%Y%m%d')
            mock_mgr.execute_query.return_value = []
            result = R.generate_ca_number()
        assert result.startswith(f'CA-{today}-')


class TestSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(corporate_action_repository, R)
