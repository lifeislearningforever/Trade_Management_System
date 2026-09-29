"""Tests for edge_jobs_py36/lib/cash_flow_repository.py."""
from unittest.mock import patch

from edge_jobs_py36.lib.cash_flow_repository import CashFlowRepository as R, cash_flow_repository


class TestEscapeValue:
    def test_none_and_empty_return_null(self):
        assert R.escape_value(None) == 'NULL'
        assert R.escape_value('') == 'NULL'

    def test_bool_lowercased(self):
        assert R.escape_value(True) == 'true'
        assert R.escape_value(False) == 'false'

    def test_string_quoted_and_escaped(self):
        assert R.escape_value("O'Brien") == "'O\\'Brien'"

    def test_int_stringified(self):
        assert R.escape_value(42) == '42'


class TestToDecimal:
    def test_none_returns_default(self):
        assert R.to_decimal(None) == '0'

    def test_empty_string_returns_default(self):
        assert R.to_decimal('') == '0'

    def test_whitespace_only_string_returns_default(self):
        assert R.to_decimal('   ') == '0'

    def test_valid_string_number(self):
        assert R.to_decimal('1.5') == '1.5'

    def test_valid_numeric_type(self):
        assert R.to_decimal(2) == '2.0'

    def test_invalid_string_returns_default(self):
        assert R.to_decimal('garbage', default=99) == '99'

    def test_custom_default(self):
        assert R.to_decimal(None, default=5) == '5'


class TestGetAll:
    def test_returns_results(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cash_flow_id': 1}]
            assert len(R.get_all()) == 1

    def test_excludes_deleted_by_default(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all()
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'is_deleted = false' in query

    def test_includes_deleted_when_requested(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(include_deleted=True)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'is_deleted = false' not in query

    def test_status_filter(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(status='APPROVED')
        assert "status = 'APPROVED'" in mock_mgr.execute_query.call_args[0][0]

    def test_search_filter_matches_three_columns(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(search='AAPL')
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'cash_flow_number' in query
        assert 'security_label' in query
        assert 'portfolio_short_name' in query

    def test_portfolio_short_name_filter(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(portfolio_short_name='UOB-SG')
        assert "portfolio_short_name = 'UOB-SG'" in mock_mgr.execute_query.call_args[0][0]

    def test_portfolios_list_filter_uses_in_clause(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(portfolios=['UOB-SG', 'UOB-HK'])
        query = mock_mgr.execute_query.call_args[0][0]
        assert "'UOB-SG'" in query
        assert "'UOB-HK'" in query

    def test_cash_flow_type_filter_case_insensitive(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(cash_flow_type='cash_dividend')
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LOWER(cash_flow_type)' in query

    def test_offset_and_limit_applied(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_all(offset=10, limit=20)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'OFFSET 10' in query
        assert 'LIMIT 20' in query

    def test_returns_empty_list_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_all() == []


class TestGetById:
    def test_returns_first_result(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cash_flow_id': 1}]
            assert R.get_by_id(1) == {'cash_flow_id': 1}

    def test_returns_none_when_empty(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert R.get_by_id(1) is None

    def test_returns_none_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_by_id(1) is None


class TestGetByCashFlowNumber:
    def test_returns_first_result(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cash_flow_number': 'CF-1'}]
            assert R.get_by_cash_flow_number('CF-1') == {'cash_flow_number': 'CF-1'}

    def test_returns_none_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_by_cash_flow_number('CF-1') is None


class TestGetPendingApprovals:
    def test_returns_results(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cash_flow_id': 1}]
            assert len(R.get_pending_approvals()) == 1

    def test_query_filters_initial_modified(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_pending_approvals()
        query = mock_mgr.execute_query.call_args[0][0]
        assert "'INITIAL'" in query
        assert "'MODIFIED'" in query

    def test_returns_empty_list_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_pending_approvals() == []


class TestGetByPortfolio:
    def test_returns_results(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cash_flow_id': 1}]
            assert len(R.get_by_portfolio('UOB-SG')) == 1

    def test_returns_empty_list_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_by_portfolio('UOB-SG') == []


class TestInsert:
    def _cf_data(self, **overrides):
        data = {
            'cash_flow_number': 'CF-1', 'portfolio_short_name': 'UOB-SG',
            'security_label': 'AAPL', 'cash_flow_type': 'CASH_DIVIDEND',
            'send_receive': 'RECEIVE', 'local_ccy_amt': '100.5', 'ca_id': '5',
        }
        data.update(overrides)
        return data

    def test_returns_true_and_id_on_success(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            mock_mgr.execute_query.return_value = [{'cash_flow_id': 1}]
            success, cf_id = R.insert(self._cf_data(), created_by='jdoe')
        assert success is True
        assert isinstance(cf_id, int)

    def test_returns_false_none_on_write_failure(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = False
            success, cf_id = R.insert(self._cf_data(), created_by='jdoe')
        assert success is False
        assert cf_id is None

    def test_returns_false_none_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            success, cf_id = R.insert(self._cf_data(), created_by='jdoe')
        assert success is False
        assert cf_id is None

    def test_int_field_ca_id_cast_properly(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            mock_mgr.execute_query.return_value = []
            R.insert(self._cf_data(ca_id='7'), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert ', 7,' in sql or 'ca_id' in sql

    def test_invalid_int_field_becomes_null(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            mock_mgr.execute_query.return_value = []
            R.insert(self._cf_data(ca_id='not-a-number'), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'NULL' in sql

    def test_bool_field_cf_processed(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            mock_mgr.execute_query.return_value = []
            R.insert(self._cf_data(cf_processed=True), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'true' in sql

    def test_status_defaults_to_initial(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            mock_mgr.execute_query.return_value = []
            R.insert(self._cf_data(), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'INITIAL'" in sql

    def test_src_system_defaults_to_cis(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            mock_mgr.execute_query.return_value = []
            R.insert(self._cf_data(), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'CIS'" in sql

    def test_ca_validated_auto_populates_validation_fields(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            mock_mgr.execute_query.return_value = []
            R.insert(self._cf_data(status='VALIDATED', src_system='CA'), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'SYSTEM_CA' in sql
        assert 'Auto-validated' in sql

    def test_non_ca_validated_does_not_auto_populate(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            mock_mgr.execute_query.return_value = []
            R.insert(self._cf_data(status='VALIDATED'), created_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'SYSTEM_CA' not in sql

    def test_verify_query_failure_does_not_fail_insert(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            mock_mgr.execute_query.side_effect = RuntimeError('verify failed')
            success, cf_id = R.insert(self._cf_data(), created_by='jdoe')
        assert success is True


class TestUpdate:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert R.update(1, {'cash_flow_type': 'INTEREST'}, updated_by='jdoe') is True

    def test_decimal_field_formatted(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update(1, {'local_ccy_amt': '150.5'}, updated_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert '150.5' in sql

    def test_boolean_field_formatted(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update(1, {'cf_processed': True}, updated_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'cf_processed = true' in sql

    def test_always_updates_audit_fields(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update(1, {'cash_flow_type': 'INTEREST'}, updated_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'updated_by' in sql
        assert 'updated_at' in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert R.update(1, {'cash_flow_type': 'INTEREST'}, updated_by='jdoe') is False


class TestUpdateStatus:
    def test_validated_sets_validation_fields_and_active(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'VALIDATED', updated_by='jdoe', comments='ok')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'validated_by' in sql
        assert 'is_active = true' in sql
        assert "'ok'" in sql

    def test_approved_sets_validation_fields(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'APPROVED', updated_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'validated_by' in sql

    def test_settled_sets_settlement_fields(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'SETTLED', updated_by='jdoe', comments='paid')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'settled_by' in sql
        assert "'paid'" in sql

    def test_cancelled_sets_cancel_fields_and_inactive(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'CANCELLED', updated_by='jdoe', comments='wrong CA')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'cancelled_by' in sql
        assert 'is_active = false' in sql
        assert "'wrong CA'" in sql

    def test_other_status_only_updates_base_fields(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'REJECTED', updated_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'validated_by' not in sql
        assert 'settled_by' not in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert R.update_status(1, 'VALIDATED', updated_by='jdoe') is False


class TestSoftDelete:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert R.soft_delete(1, deleted_by='jdoe') is True

    def test_sets_is_deleted_and_inactive(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.soft_delete(1, deleted_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'is_deleted = true' in sql
        assert 'is_active = false' in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert R.soft_delete(1, deleted_by='jdoe') is False


class TestRestore:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert R.restore(1, restored_by='jdoe') is True

    def test_sets_status_to_modified(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.restore(1, restored_by='jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "status = 'MODIFIED'" in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert R.restore(1, restored_by='jdoe') is False


class TestInsertHistory:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = R.insert_history(1, 'CF-1', 'UOB-SG', 'CREATE', 'INITIAL', {}, 'note', 'jdoe')
        assert result is True

    def test_changes_serialized_with_decimal_handling(self):
        from decimal import Decimal
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert_history(1, 'CF-1', 'UOB-SG', 'UPDATE', 'MODIFIED', {'amount': Decimal('1.5')}, 'note', 'jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'amount' in sql

    def test_empty_changes_becomes_empty_json(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert_history(1, 'CF-1', 'UOB-SG', 'CREATE', 'INITIAL', {}, 'note', 'jdoe')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert '{}' in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            result = R.insert_history(1, 'CF-1', 'UOB-SG', 'CREATE', 'INITIAL', {}, 'note', 'jdoe')
        assert result is False


class TestGetHistory:
    def test_returns_results(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'history_id': 1}]
            assert len(R.get_history(1)) == 1

    def test_returns_empty_list_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_history(1) == []


class TestGenerateCashFlowNumber:
    def test_first_of_day_is_sequence_one(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = R.generate_cash_flow_number()
        assert result.endswith('00001')

    def test_increments_from_last_sequence(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            from datetime import datetime
            today = datetime.now().strftime('%Y%m%d')
            mock_mgr.execute_query.return_value = [{'cash_flow_number': f'CF-{today}-00003'}]
            result = R.generate_cash_flow_number()
        assert result.endswith('00004')

    def test_unparseable_resets_to_one(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cash_flow_number': 'garbage'}]
            result = R.generate_cash_flow_number()
        assert result.endswith('00001')

    def test_exception_falls_back_to_timestamp(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = R.generate_cash_flow_number()
        assert result.startswith('CF-')


class TestGetStatistics:
    def test_returns_aggregated_counts(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [
                [{'status': 'APPROVED', 'count': 5}, {'status': 'MODIFIED', 'count': 2}],
                [{'count': 3}],
                [{'cash_flow_type': 'CASH_DIVIDEND', 'count': 4}],
            ]
            stats = R.get_statistics()
        assert stats['total'] == 7
        assert stats['approved'] == 5
        assert stats['modified'] == 2
        assert stats['pending_approval'] == 2
        assert stats['approved_today'] == 3

    def test_returns_zeroed_defaults_on_exception(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            stats = R.get_statistics()
        assert stats['total'] == 0
        assert stats['by_type'] == []

    def test_handles_empty_results(self):
        with patch('edge_jobs_py36.lib.cash_flow_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [None, None, None]
            stats = R.get_statistics()
        assert stats['total'] == 0
        assert stats['approved_today'] == 0


class TestSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(cash_flow_repository, R)
