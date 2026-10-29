"""Tests for edge_jobs_py36/lib/ca_cash_flow_queue_repository.py."""
from decimal import Decimal
from unittest.mock import patch

from edge_jobs_py36.lib.ca_cash_flow_queue_repository import (
    CACashFlowQueueRepository as R,
    ca_cash_flow_queue_repository,
)


class TestEscapeValue:
    def test_none_returns_null(self):
        assert R.escape_value(None) == 'NULL'

    def test_empty_string_returns_null(self):
        assert R.escape_value('') == 'NULL'

    def test_true_returns_lowercase_true(self):
        assert R.escape_value(True) == 'true'

    def test_false_returns_lowercase_false(self):
        assert R.escape_value(False) == 'false'

    def test_int_unquoted(self):
        assert R.escape_value(5) == '5'

    def test_decimal_unquoted(self):
        assert R.escape_value(Decimal('1.5')) == '1.5'

    def test_string_quoted_and_escaped(self):
        assert R.escape_value("O'Brien") == "'O\\'Brien'"


class TestInsert:
    def test_returns_true_and_queue_id_on_success(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            success, queue_id = R.insert({'ca_id': 1, 'ca_number': 'GMP-1'})
        assert success is True
        assert isinstance(queue_id, int)

    def test_query_includes_pending_status(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert({'ca_id': 1, 'ca_number': 'GMP-1'})
        sql = mock_mgr.execute_write.call_args_list[0][0][0]
        assert "'PENDING'" in sql

    def test_updates_ca_processed_flag_on_success(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert({'ca_id': 42, 'ca_number': 'GMP-1'})
        assert mock_mgr.execute_write.call_count == 2
        flag_sql = mock_mgr.execute_write.call_args_list[1][0][0]
        assert 'cis_corporate_actions' in flag_sql
        assert 'ca_id = 42' in flag_sql

    def test_returns_false_none_on_write_failure(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = False
            success, queue_id = R.insert({'ca_id': 1, 'ca_number': 'GMP-1'})
        assert success is False
        assert queue_id is None

    def test_does_not_update_flag_when_write_fails(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = False
            R.insert({'ca_id': 1, 'ca_number': 'GMP-1'})
        assert mock_mgr.execute_write.call_count == 1

    def test_returns_false_none_on_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            success, queue_id = R.insert({'ca_id': 1})
        assert success is False
        assert queue_id is None


class TestGetPending:
    def test_returns_results(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'queue_id': 1}]
            result = R.get_pending()
        assert len(result) == 1

    def test_returns_empty_list_when_none(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert R.get_pending() == []

    def test_query_filters_by_pending_status_and_retry_count(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_pending()
        query = mock_mgr.execute_query.call_args[0][0]
        assert "status = 'PENDING'" in query
        assert f'retry_count < {R.MAX_RETRIES}' in query

    def test_ex_date_filter_takes_priority_over_payment_date(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_pending(ex_date='2026-09-17', payment_date='2026-09-20')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "ex_date = '2026-09-17'" in query
        assert "payment_date = '2026-09-20'" not in query

    def test_payment_date_filter_used_when_no_ex_date(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_pending(payment_date='2026-09-20')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "payment_date = '2026-09-20'" in query

    def test_limit_applied(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_pending(limit=25)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 25' in query

    def test_returns_empty_list_on_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_pending() == []


class TestGetPendingForCorr:
    def test_returns_results(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'queue_id': 1}]
            result = R.get_pending_for_corr('2026-08-31')
        assert len(result) == 1

    def test_query_includes_pending_and_failed_statuses(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_pending_for_corr('2026-08-31')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "'PENDING'" in query
        assert "'FAILED'" in query
        assert "ex_date <= '2026-08-31'" in query

    def test_limit_applied(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            R.get_pending_for_corr('2026-08-31', limit=10)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 10' in query

    def test_returns_empty_list_on_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_pending_for_corr('2026-08-31') == []


class TestGetById:
    def test_returns_first_row(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'queue_id': 1}]
            assert R.get_by_id(1) == {'queue_id': 1}

    def test_returns_none_when_empty(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert R.get_by_id(1) is None

    def test_returns_none_on_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_by_id(1) is None


class TestGetByCaId:
    def test_returns_list(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'queue_id': 1}, {'queue_id': 2}]
            assert len(R.get_by_ca_id(42)) == 2

    def test_returns_empty_list_when_none(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert R.get_by_ca_id(42) == []

    def test_returns_empty_list_on_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_by_ca_id(42) == []


class TestUpdateStatus:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert R.update_status(1, 'PROCESSING') is True

    def test_includes_error_message_when_given(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'FAILED', error_message='boom')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'error_message' in sql
        assert "'boom'" in sql

    def test_includes_cash_flows_created_when_given(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'COMPLETED', cash_flows_created=5)
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'cash_flows_created = 5' in sql

    def test_includes_total_amount_when_given(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'COMPLETED', total_amount=Decimal('100.5'))
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'total_amount = 100.5' in sql

    def test_sets_processed_at_for_completed_status(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'COMPLETED')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'processed_at' in sql

    def test_sets_processed_at_for_failed_status(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'FAILED')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'processed_at' in sql

    def test_no_processed_at_for_pending_status(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.update_status(1, 'PENDING')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'processed_at' not in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert R.update_status(1, 'PROCESSING') is False


class TestMarkProcessing:
    def test_delegates_to_update_status(self):
        with patch.object(R, 'update_status', return_value=True) as mock_update:
            result = R.mark_processing(1)
        assert result is True
        mock_update.assert_called_once_with(1, R.STATUS_PROCESSING)


class TestMarkCompleted:
    def test_returns_true_and_updates_ca_flag(self):
        with patch.object(R, 'update_status', return_value=True), \
             patch.object(R, 'get_by_id', return_value={'ca_id': 42}), \
             patch.object(R, '_update_ca_processed_flag') as mock_flag:
            result = R.mark_completed(1, cash_flows_created=2, total_amount=Decimal('50'))
        assert result is True
        mock_flag.assert_called_once_with(ca_id=42, queued=True, processed=True)

    def test_does_not_update_flag_when_status_update_fails(self):
        with patch.object(R, 'update_status', return_value=False), \
             patch.object(R, '_update_ca_processed_flag') as mock_flag:
            result = R.mark_completed(1)
        assert result is False
        mock_flag.assert_not_called()

    def test_swallows_exception_from_get_by_id(self):
        with patch.object(R, 'update_status', return_value=True), \
             patch.object(R, 'get_by_id', side_effect=RuntimeError('boom')):
            result = R.mark_completed(1)  # should not raise
        assert result is True

    def test_does_not_update_flag_when_entry_has_no_ca_id(self):
        with patch.object(R, 'update_status', return_value=True), \
             patch.object(R, 'get_by_id', return_value={}), \
             patch.object(R, '_update_ca_processed_flag') as mock_flag:
            R.mark_completed(1)
        mock_flag.assert_not_called()


class TestMarkFailed:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert R.mark_failed(1, 'error occurred') is True

    def test_increments_retry_count_and_sets_error(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.mark_failed(1, 'error occurred')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'retry_count = retry_count + 1' in sql
        assert "'error occurred'" in sql
        assert "'FAILED'" in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert R.mark_failed(1, 'error') is False


class TestResetForRetry:
    def test_returns_true_on_success(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert R.reset_for_retry(1) is True

    def test_query_resets_to_pending_and_clears_error(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.reset_for_retry(1)
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'PENDING'" in sql
        assert 'error_message = NULL' in sql
        assert f'retry_count < {R.MAX_RETRIES}' in sql

    def test_returns_false_on_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert R.reset_for_retry(1) is False


class TestGetStatistics:
    def test_returns_default_stats_structure(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            stats = R.get_statistics()
        assert stats['pending'] == 0
        assert stats['total_amount'] == Decimal('0')

    def test_populates_counts_per_status(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'status': 'pending', 'count': 3},
                {'status': 'failed', 'count': 1},
            ]
            stats = R.get_statistics()
        assert stats['pending'] == 3
        assert stats['failed'] == 1

    def test_populates_totals_for_completed(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'status': 'completed', 'count': 5, 'total_cash_flows': 10, 'total_amount': '250.5'},
            ]
            stats = R.get_statistics()
        assert stats['completed'] == 5
        assert stats['total_cash_flows'] == 10
        assert stats['total_amount'] == Decimal('250.5')

    def test_returns_empty_dict_on_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_statistics() == {}

    def test_ignores_unknown_status_key(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': 'weird_status', 'count': 9}]
            stats = R.get_statistics()
        assert 'weird_status' not in stats


class TestInsertLog:
    def test_returns_true_and_log_id_on_success(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            success, log_id = R.insert_log({'queue_id': 1, 'ca_id': 2})
        assert success is True
        assert isinstance(log_id, int)

    def test_default_status_is_success(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            R.insert_log({'queue_id': 1})
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'SUCCESS'" in sql

    def test_returns_false_none_on_write_failure(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = False
            success, log_id = R.insert_log({'queue_id': 1})
        assert success is False
        assert log_id is None

    def test_returns_false_none_on_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            success, log_id = R.insert_log({'queue_id': 1})
        assert success is False
        assert log_id is None


class TestGetLogsByQueueId:
    def test_returns_results(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'log_id': 1}]
            assert len(R.get_logs_by_queue_id(1)) == 1

    def test_returns_empty_list_when_none(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert R.get_logs_by_queue_id(1) == []

    def test_returns_empty_list_on_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert R.get_logs_by_queue_id(1) == []


class TestUpdateCaProcessedFlag:
    def test_sets_queued_and_processed_true(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            R._update_ca_processed_flag(ca_id=42, queued=True, processed=True)
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'cash_flow_queued = true' in sql
        assert 'ca_processed     = true' in sql
        assert 'ca_processed_at' in sql

    def test_sets_queued_true_processed_false_no_processed_at(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            R._update_ca_processed_flag(ca_id=42, queued=True, processed=False)
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'cash_flow_queued = true' in sql
        assert 'ca_processed     = false' in sql
        assert 'ca_processed_at' not in sql

    def test_swallows_exception(self):
        with patch('edge_jobs_py36.lib.ca_cash_flow_queue_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            R._update_ca_processed_flag(ca_id=42, queued=True, processed=True)  # must not raise


class TestSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(ca_cash_flow_queue_repository, R)
