"""Tests for edge_jobs_py36/lib/position_queue_service.py."""
import queue as queue_mod
import time as time_mod
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock, call

import pytest

from edge_jobs_py36.lib.position_queue_service import PositionQueueService


@pytest.fixture
def svc():
    mock_pos_svc = MagicMock()
    mock_pos_svc.POSITION_TABLE = 'cis_trade_position'
    mock_pos_svc._escape = lambda v: str(v).replace("'", "\\'")
    return PositionQueueService(position_svc=mock_pos_svc)


@pytest.fixture
def impala():
    with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
        m.execute_write.return_value = True
        m.execute_query.return_value = []
        yield m


@pytest.fixture
def notify_user_mock():
    with patch('edge_jobs_py36.lib.position_queue_service.notify_user') as m:
        yield m


@pytest.fixture
def notify_admins_mock():
    with patch('edge_jobs_py36.lib.position_queue_service.notify_admins') as m:
        yield m


class TestInit:
    def test_default_uses_singleton_position_service(self):
        s = PositionQueueService()
        assert s.position_service is not None
        assert s._worker_running is False
        assert s._worker_thread is None

    def test_custom_position_service(self, svc):
        assert svc.position_service is not None


class TestEnqueuePositionCalculation:
    def test_enqueue_db_queue_success(self, svc, impala):
        ok, msg, qid = svc.enqueue_position_calculation(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', queued_by='user1',
        )
        assert ok is True
        assert qid is not None
        assert 'queued' in msg.lower()
        impala.execute_write.assert_called_once()

    def test_enqueue_db_queue_failure(self, svc, impala):
        impala.execute_write.return_value = False
        ok, msg, qid = svc.enqueue_position_calculation(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', queued_by='user1',
        )
        assert ok is False
        assert qid is None

    def test_enqueue_in_memory_queue(self, svc):
        ok, msg, qid = svc.enqueue_position_calculation(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', queued_by='user1', use_db_queue=False,
        )
        assert ok is True
        assert svc._in_memory_queue.qsize() == 1

    def test_enqueue_with_lc_amounts_all_present(self, svc, impala):
        ok, msg, qid = svc.enqueue_position_calculation(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', queued_by='user1',
            gross_amount_lc=Decimal('1000'), total_amount_lc=Decimal('990'),
            gross_amount_fc=Decimal('500'),
        )
        assert ok is True
        query = impala.execute_write.call_args[0][0]
        assert "LC:" in query

    def test_enqueue_with_chain_recalc_metadata_only(self, svc, impala):
        ok, msg, qid = svc.enqueue_position_calculation(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', queued_by='user1',
            chain_recalc_metadata='CHAIN_RECALC:P1:S1:2026-01-01',
        )
        assert ok is True
        query = impala.execute_write.call_args[0][0]
        assert 'CHAIN_RECALC' in query

    def test_enqueue_with_lc_meta_and_chain_recalc_combined(self, svc, impala):
        ok, msg, qid = svc.enqueue_position_calculation(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', queued_by='user1',
            gross_amount_lc=Decimal('1000'),
            chain_recalc_metadata='CHAIN_RECALC:P1:S1:2026-01-01',
        )
        assert ok is True

    def test_enqueue_uses_position_date_override(self, svc, impala):
        ok, msg, qid = svc.enqueue_position_calculation(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', queued_by='user1', position_date='2025-12-31',
        )
        assert ok is True
        query = impala.execute_write.call_args[0][0]
        assert '2025-12-31' in query

    def test_enqueue_exception_returns_false(self, svc):
        with patch.object(svc, '_generate_id', side_effect=RuntimeError('boom')):
            ok, msg, qid = svc.enqueue_position_calculation(
                trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
                quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
                settle_date='2026-01-01', queued_by='user1',
            )
        assert ok is False
        assert qid is None
        assert 'Queue error' in msg


class TestInsertQueueItem:
    def make_item(self, **overrides):
        item = {
            'queue_id': 1, 'trade_id': 2, 'deal_number': 'D1',
            'portfolio_id': 'P1', 'security_id': 'S1', 'trade_type': 'BUY',
            'quantity': 10.0, 'price': 100.0, 'charges': 1.0,
            'settle_date': '2026-01-01', 'position_date': '2026-01-01',
            'position_basis': 'TRADED', 'security_currency': 'USD',
            'portfolio_currency': 'USD', 'isin': 'ISIN1', 'security_name': 'Sec 1',
            'status': 'PENDING', 'retry_count': 0, 'queued_at': datetime(2026, 1, 1, 10, 0, 0),
            'queued_by': 'user1', 'error_message': None,
        }
        item.update(overrides)
        return item

    def test_insert_success(self, svc, impala):
        result = svc._insert_queue_item(self.make_item())
        assert result is True
        impala.execute_write.assert_called_once()

    def test_insert_with_null_optional_fields(self, svc, impala):
        item = self.make_item(security_currency=None, portfolio_currency=None, isin=None, security_name=None)
        result = svc._insert_queue_item(item)
        assert result is True
        query = impala.execute_write.call_args[0][0]
        assert 'NULL' in query

    def test_insert_with_error_message(self, svc, impala):
        item = self.make_item(error_message="it's an error")
        result = svc._insert_queue_item(item)
        assert result is True
        query = impala.execute_write.call_args[0][0]
        assert "it\\'s an error" in query

    def test_insert_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('db down')
            result = svc._insert_queue_item(self.make_item())
        assert result is False


class TestWorkerLifecycle:
    def test_start_worker_starts_thread(self, svc):
        with patch.object(svc, '_worker_loop'):
            svc.start_worker()
            assert svc._worker_running is True
            assert svc._worker_thread is not None
            svc._worker_thread.join(timeout=2)

    def test_start_worker_already_running_warns(self, svc):
        svc._worker_running = True
        svc.start_worker()
        assert svc._worker_thread is None

    def test_stop_worker_joins_thread(self, svc):
        with patch.object(svc, '_worker_loop'):
            svc.start_worker()
            svc.stop_worker()
        assert svc._worker_running is False

    def test_stop_worker_no_thread(self, svc):
        svc.stop_worker()
        assert svc._worker_running is False

    def test_worker_loop_processes_then_stops(self, svc):
        calls = []

        def fake_process_batch():
            calls.append(1)
            svc._worker_running = False
            return 1

        with patch.object(svc, '_process_batch', side_effect=fake_process_batch), \
             patch.object(svc, '_process_in_memory_queue'):
            svc._worker_running = True
            svc._worker_loop()
        assert len(calls) == 1

    def test_worker_loop_sleeps_when_nothing_processed(self, svc):
        state = {'n': 0}

        def fake_process_batch():
            state['n'] += 1
            if state['n'] >= 1:
                svc._worker_running = False
            return 0

        with patch.object(svc, '_process_batch', side_effect=fake_process_batch), \
             patch.object(svc, '_process_in_memory_queue'), \
             patch('edge_jobs_py36.lib.position_queue_service.time.sleep') as sleep_mock:
            svc._worker_running = True
            svc._worker_loop()
        sleep_mock.assert_called_with(svc.POLL_INTERVAL)

    def test_worker_loop_handles_exception(self, svc):
        state = {'n': 0}

        def raise_once():
            state['n'] += 1
            svc._worker_running = False
            raise RuntimeError('boom')

        with patch.object(svc, '_process_batch', side_effect=raise_once), \
             patch('edge_jobs_py36.lib.position_queue_service.time.sleep') as sleep_mock:
            svc._worker_running = True
            svc._worker_loop()
        sleep_mock.assert_called_with(svc.POLL_INTERVAL)


class TestProcessBatch:
    def test_no_pending_returns_zero(self, svc):
        with patch.object(svc, 'get_pending_items', return_value=[]):
            assert svc._process_batch() == 0

    def test_processes_all_pending(self, svc):
        items = [{'queue_id': 1}, {'queue_id': 2}]
        with patch.object(svc, 'get_pending_items', return_value=items), \
             patch.object(svc, '_process_item') as proc:
            count = svc._process_batch()
        assert count == 2
        assert proc.call_count == 2

    def test_exception_returns_zero(self, svc):
        with patch.object(svc, 'get_pending_items', side_effect=RuntimeError('boom')):
            assert svc._process_batch() == 0


class TestProcessInMemoryQueue:
    def test_processes_items_until_empty(self, svc):
        svc._in_memory_queue.put({'queue_id': 1})
        svc._in_memory_queue.put({'queue_id': 2})
        with patch.object(svc, '_process_item') as proc:
            svc._process_in_memory_queue()
        assert proc.call_count == 2
        assert svc._in_memory_queue.empty()

    def test_stops_at_batch_size(self, svc):
        svc.BATCH_SIZE = 1
        svc._in_memory_queue.put({'queue_id': 1})
        svc._in_memory_queue.put({'queue_id': 2})
        with patch.object(svc, '_process_item') as proc:
            svc._process_in_memory_queue()
        assert proc.call_count == 1

    def test_swallows_processing_exception_and_continues(self, svc):
        svc._in_memory_queue.put({'queue_id': 1})
        svc._in_memory_queue.put({'queue_id': 2})
        with patch.object(svc, '_process_item', side_effect=[RuntimeError('boom'), None]):
            svc._process_in_memory_queue()
        assert svc._in_memory_queue.empty()


class TestParseChainRecalcMetadata:
    def test_none_metadata(self, svc):
        assert svc._parse_chain_recalc_metadata(None) is None

    def test_empty_metadata(self, svc):
        assert svc._parse_chain_recalc_metadata('') is None

    def test_non_chain_recalc_metadata(self, svc):
        assert svc._parse_chain_recalc_metadata('SOMETHING_ELSE:1:2:3') is None

    def test_colon_format(self, svc):
        result = svc._parse_chain_recalc_metadata('CHAIN_RECALC:P1:S1:2026-01-01')
        assert result == {'portfolio_id': 'P1', 'security_id': 'S1', 'from_date': '2026-01-01'}

    def test_space_format(self, svc):
        result = svc._parse_chain_recalc_metadata('CHAIN_RECALC P1 S1 2026-01-01')
        assert result == {'portfolio_id': 'P1', 'security_id': 'S1', 'from_date': '2026-01-01'}

    def test_colon_format_too_few_parts_falls_through_to_space_parse(self, svc):
        result = svc._parse_chain_recalc_metadata('CHAIN_RECALC:P1')
        assert result is None

    def test_unparseable_logs_warning_returns_none(self, svc):
        result = svc._parse_chain_recalc_metadata('CHAIN_RECALC')
        assert result is None

    def test_exception_returns_none(self, svc):
        class Bad(str):
            def startswith(self, *a, **kw):
                if a and a[0] == 'CHAIN_RECALC:':
                    raise RuntimeError('boom')
                return True
        with patch('edge_jobs_py36.lib.position_queue_service.logger'):
            result = svc._parse_chain_recalc_metadata(Bad('CHAIN_RECALC:x'))
        assert result is None


class TestUpdateStatus:
    def test_basic_update(self, svc, impala):
        result = svc._update_status(1, svc.STATUS_PROCESSING)
        assert result is True
        query = impala.execute_write.call_args[0][0]
        assert "status = 'PROCESSING'" in query

    def test_update_with_error_message(self, svc, impala):
        svc._update_status(1, svc.STATUS_FAILED, error_message="it's bad")
        query = impala.execute_write.call_args[0][0]
        assert "error_message = 'it\\'s bad'" in query

    def test_update_completed_sets_processed_at(self, svc, impala):
        svc._update_status(1, svc.STATUS_COMPLETED)
        query = impala.execute_write.call_args[0][0]
        assert 'processed_at' in query

    def test_update_dead_letter_sets_processed_at(self, svc, impala):
        svc._update_status(1, svc.STATUS_DEAD_LETTER)
        query = impala.execute_write.call_args[0][0]
        assert 'processed_at' in query

    def test_update_with_increment_retry(self, svc, impala):
        svc._update_status(1, svc.STATUS_PENDING, increment_retry=True)
        query = impala.execute_write.call_args[0][0]
        assert 'retry_count = CAST(retry_count + 1 AS INT)' in query

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            assert svc._update_status(1, svc.STATUS_FAILED) is False


class TestGetPendingItems:
    def test_returns_results(self, svc, impala):
        impala.execute_query.return_value = [{'queue_id': 1}]
        result = svc.get_pending_items(limit=50)
        assert result == [{'queue_id': 1}]
        query = impala.execute_query.call_args[0][0]
        assert 'LIMIT 50' in query

    def test_returns_empty_list_when_none(self, svc, impala):
        impala.execute_query.return_value = None
        assert svc.get_pending_items() == []

    def test_exception_returns_empty_list(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_pending_items() == []


class TestGetQueueStatistics:
    def test_aggregates_by_status(self, svc, impala):
        impala.execute_query.return_value = [
            {'status': 'PENDING', 'count': 5},
            {'status': 'DEAD_LETTER', 'count': 2},
            {'status': 'COMPLETED', 'count': 10},
        ]
        stats = svc.get_queue_statistics()
        assert stats['pending'] == 5
        assert stats['dead_letter'] == 2
        assert stats['completed'] == 10
        assert stats['total'] == 17

    def test_no_results_returns_zeros(self, svc, impala):
        impala.execute_query.return_value = None
        stats = svc.get_queue_statistics()
        assert stats['total'] == 0

    def test_exception_returns_default_dict(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            stats = svc.get_queue_statistics()
        assert stats == {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0, 'dead_letter': 0, 'total': 0}


class TestRetryFailedItems:
    def test_success(self, svc, impala):
        result = svc.retry_failed_items()
        assert result == {'retried': 1}

    def test_failure(self, svc, impala):
        impala.execute_write.return_value = False
        result = svc.retry_failed_items()
        assert result == {'retried': 0}

    def test_exception(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            result = svc.retry_failed_items()
        assert result == {'retried': 0}


class TestPurgeCompleted:
    def test_success(self, svc, impala):
        result = svc.purge_completed(days_old=10)
        assert result == {'purged': 1}
        query = impala.execute_write.call_args[0][0]
        assert 'DELETE FROM' in query

    def test_failure(self, svc, impala):
        impala.execute_write.return_value = False
        result = svc.purge_completed()
        assert result == {'purged': 0}

    def test_exception(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            result = svc.purge_completed()
        assert result == {'purged': 0}


class TestProcessImmediately:
    def test_calls_calculate_position_with_defaults(self, svc):
        svc.position_service.calculate_position.return_value = (True, 'ok', {'x': 1})
        result = svc.process_immediately(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', updated_by='user1',
        )
        assert result == (True, 'ok', {'x': 1})
        kwargs = svc.position_service.calculate_position.call_args[1]
        assert kwargs['position_date'] == '2026-01-01'
        assert kwargs['trade_lc'] is None
        assert kwargs['gross_amount_lc'] is None
        assert kwargs['gross_amount_fc'] is None

    def test_uses_position_date_override(self, svc):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        svc.process_immediately(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', updated_by='user1', position_date='2025-12-25',
        )
        kwargs = svc.position_service.calculate_position.call_args[1]
        assert kwargs['position_date'] == '2025-12-25'

    def test_passes_lc_fc_kwargs(self, svc):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        svc.process_immediately(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', updated_by='user1',
            gross_amount_lc=Decimal('100'), total_amount_lc=Decimal('90'),
            gross_amount_fc=Decimal('50'),
        )
        kwargs = svc.position_service.calculate_position.call_args[1]
        assert kwargs['trade_lc'] == Decimal('90')
        assert kwargs['gross_amount_lc'] == Decimal('100')
        assert kwargs['gross_amount_fc'] == Decimal('50')

    def test_trade_lc_alias_kwarg(self, svc):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        svc.process_immediately(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', updated_by='user1', trade_lc=Decimal('77'),
        )
        kwargs = svc.position_service.calculate_position.call_args[1]
        assert kwargs['trade_lc'] == Decimal('77')


class TestUtilities:
    def test_generate_id_is_int(self, svc):
        assert isinstance(svc._generate_id(), int)

    def test_generate_id_unique_across_calls(self, svc):
        ids = {svc._generate_id() for _ in range(5)}
        assert len(ids) >= 1  # timestamps may collide within same ms but shouldn't error

    def test_escape_none(self, svc):
        assert svc._escape(None) == ''

    def test_escape_quote_and_backslash(self, svc):
        assert svc._escape("O'Brien\\x") == "O\\'Brien\\\\x"

    def test_null_or_str_none(self, svc):
        assert svc._null_or_str(None) == 'NULL'

    def test_null_or_str_empty(self, svc):
        assert svc._null_or_str('') == 'NULL'

    def test_null_or_str_value(self, svc):
        assert svc._null_or_str("it's") == "'it\\'s'"


class TestGetBusinessDatesBetween:
    def test_returns_dates_from_query(self, svc, impala):
        impala.execute_query.return_value = [
            {'biz_date': '20260102'}, {'biz_date': '20260103'},
        ]
        result = svc._get_business_dates_between('2026-01-01', '2026-01-03')
        assert result == ['2026-01-02', '2026-01-03']

    def test_returns_dashed_date_passthrough(self, svc, impala):
        impala.execute_query.return_value = [{'biz_date': '2026-01-02'}]
        result = svc._get_business_dates_between('2026-01-01', '2026-01-03')
        assert result == ['2026-01-02']

    def test_falls_back_to_calendar_days_on_empty_result(self, svc, impala):
        impala.execute_query.return_value = []
        result = svc._get_business_dates_between('2026-01-01', '2026-01-02')
        # weekdays only, exclusive of from_date, inclusive of to_date (both Thu/Fri)
        assert result == ['2026-01-02']

    def test_falls_back_on_exception(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            result = svc._get_business_dates_between('2026-01-01', '2026-01-03')
        assert isinstance(result, list)

    def test_excludes_weekends_in_fallback(self, svc, impala):
        impala.execute_query.return_value = []
        # 2026-01-02 is a Friday, 01-03 Saturday, 01-04 Sunday, 01-05 Monday
        result = svc._get_business_dates_between('2026-01-01', '2026-01-05')
        assert '2026-01-03' not in result
        assert '2026-01-04' not in result
        assert '2026-01-05' in result


class TestCarryForwardToToday:
    def test_skips_when_already_at_today(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        svc._carry_forward_to_today(
            portfolio_id='P1', security_id='S1',
            last_trade_date_by_basis={'TRADED': '2026-01-05'},
            today_str='2026-01-05', counters=counters,
        )
        assert counters['recalculated'] == 0
        svc.position_service._get_position_as_of_date.assert_not_called()

    def test_no_fill_dates_skips(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        with patch.object(svc, '_get_business_dates_between', return_value=[]):
            svc._carry_forward_to_today(
                portfolio_id='P1', security_id='S1',
                last_trade_date_by_basis={'TRADED': '2026-01-01'},
                today_str='2026-01-05', counters=counters,
            )
        assert counters['recalculated'] == 0

    def test_no_running_position_warns_and_skips(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        svc.position_service._get_position_as_of_date.return_value = None
        with patch.object(svc, '_get_business_dates_between', return_value=['2026-01-02']):
            svc._carry_forward_to_today(
                portfolio_id='P1', security_id='S1',
                last_trade_date_by_basis={'TRADED': '2026-01-01'},
                today_str='2026-01-05', counters=counters,
            )
        assert counters['recalculated'] == 0

    def test_carries_forward_successfully(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        svc.position_service._get_position_as_of_date.return_value = {'quantity': 10}
        svc.position_service._save_position.return_value = True
        with patch.object(svc, '_get_business_dates_between', return_value=['2026-01-02', '2026-01-03']):
            svc._carry_forward_to_today(
                portfolio_id='P1', security_id='S1',
                last_trade_date_by_basis={'TRADED': '2026-01-01'},
                today_str='2026-01-05', counters=counters,
            )
        assert counters['recalculated'] == 2
        assert svc.position_service._save_position.call_count == 2

    def test_carry_forward_save_failure_increments_errors(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        svc.position_service._get_position_as_of_date.return_value = {'quantity': 10}
        svc.position_service._save_position.return_value = False
        with patch.object(svc, '_get_business_dates_between', return_value=['2026-01-02']):
            svc._carry_forward_to_today(
                portfolio_id='P1', security_id='S1',
                last_trade_date_by_basis={'TRADED': '2026-01-01'},
                today_str='2026-01-05', counters=counters,
            )
        assert counters['errors'] == 1

    def test_carry_forward_exception_increments_errors(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        svc.position_service._get_position_as_of_date.return_value = {'quantity': 10}
        svc.position_service._save_position.side_effect = RuntimeError('boom')
        with patch.object(svc, '_get_business_dates_between', return_value=['2026-01-02']):
            svc._carry_forward_to_today(
                portfolio_id='P1', security_id='S1',
                last_trade_date_by_basis={'TRADED': '2026-01-01'},
                today_str='2026-01-05', counters=counters,
            )
        assert counters['errors'] == 1

    def test_multiple_bases_processed(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        svc.position_service._get_position_as_of_date.return_value = {'quantity': 10}
        svc.position_service._save_position.return_value = True
        with patch.object(svc, '_get_business_dates_between', return_value=['2026-01-02']):
            svc._carry_forward_to_today(
                portfolio_id='P1', security_id='S1',
                last_trade_date_by_basis={'TRADED': '2026-01-01', 'SETTLED': '2026-01-01'},
                today_str='2026-01-05', counters=counters,
            )
        assert counters['recalculated'] == 2


class TestHandleFailure:
    def make_item(self, retry_count=0):
        return {
            'queue_id': 1, 'trade_id': 2, 'deal_number': 'D1',
            'queued_by': 'user1', 'portfolio_id': 'P1', 'security_id': 'S1',
            'security_name': None, 'isin': 'ISIN1', 'retry_count': retry_count,
        }

    def test_retry_under_max_updates_status_db_queue(self, svc, impala, notify_user_mock):
        svc._handle_failure(self.make_item(retry_count=0), 'some error', is_db_queue=True)
        query = impala.execute_write.call_args[0][0]
        assert "status = 'PENDING'" in query
        notify_user_mock.assert_called_once()

    def test_retry_under_max_in_memory_requeues(self, svc, notify_user_mock):
        item = self.make_item(retry_count=1)
        svc._handle_failure(item, 'some error', is_db_queue=False)
        assert svc._in_memory_queue.qsize() == 1
        assert item['retry_count'] == 2

    def test_max_retries_moves_to_dead_letter(self, svc, impala, notify_user_mock, notify_admins_mock):
        item = self.make_item(retry_count=3)
        svc._handle_failure(item, 'fatal error', is_db_queue=True)
        query = impala.execute_write.call_args[0][0]
        assert "status = 'DEAD_LETTER'" in query
        notify_user_mock.assert_called_once()
        notify_admins_mock.assert_called_once()

    def test_dead_letter_in_memory_queue_no_db_update(self, svc, notify_user_mock, notify_admins_mock):
        item = self.make_item(retry_count=5)
        svc._handle_failure(item, 'fatal error', is_db_queue=False)
        notify_admins_mock.assert_called_once()

    def test_dead_letter_error_truncated_in_admin_notification(self, svc, impala, notify_user_mock, notify_admins_mock):
        item = self.make_item(retry_count=3)
        long_error = 'x' * 500
        svc._handle_failure(item, long_error, is_db_queue=True)
        admin_payload = notify_admins_mock.call_args[0][1]
        assert len(admin_payload['message']) < 500


class TestProcessItem:
    def make_item(self, **overrides):
        item = {
            'queue_id': 1, 'trade_id': 2, 'deal_number': 'D1',
            'portfolio_id': 'P1', 'security_id': 'S1', 'trade_type': 'BUY',
            'quantity': 10.0, 'price': 100.0, 'charges': 1.0,
            'settle_date': '2026-01-01', 'position_date': '2026-01-01',
            'position_basis': 'TRADED', 'security_currency': 'USD',
            'portfolio_currency': 'USD', 'isin': 'ISIN1', 'security_name': 'Sec 1',
            'queued_by': 'user1', 'error_message': None,
            'queued_at': datetime.now(),
            'gross_amount_lc': None, 'total_amount_lc': None, 'gross_amount_fc': None,
        }
        item.update(overrides)
        return item

    def test_success_path_updates_completed_and_notifies(self, svc, impala, notify_user_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', {'x': 1})
        svc._process_item(self.make_item())
        completed_calls = [c for c in impala.execute_write.call_args_list if 'COMPLETED' in c[0][0]]
        assert len(completed_calls) == 1
        assert notify_user_mock.call_count == 2  # PROCESSING + COMPLETED

    def test_failure_path_calls_handle_failure(self, svc, impala, notify_user_mock):
        svc.position_service.calculate_position.return_value = (False, 'calc failed', None)
        with patch.object(svc, '_handle_failure') as hf:
            svc._process_item(self.make_item())
        hf.assert_called_once()

    def test_exception_during_calculate_position_calls_handle_failure(self, svc, impala, notify_user_mock):
        svc.position_service.calculate_position.side_effect = RuntimeError('boom')
        with patch.object(svc, '_handle_failure') as hf:
            svc._process_item(self.make_item())
        hf.assert_called_once()

    def test_in_memory_queue_skips_db_status_update(self, svc, notify_user_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            svc._process_item(self.make_item(), is_db_queue=False)
            m.execute_write.assert_not_called()

    def test_sla_breach_triggers_notifications(self, svc, impala, notify_user_mock, notify_admins_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        old_time = datetime.now() - timedelta(seconds=svc.SLA_SECONDS + 100)
        svc._process_item(self.make_item(queued_at=old_time))
        notify_admins_mock.assert_called_once()

    def test_sla_breach_queued_at_as_string(self, svc, impala, notify_user_mock, notify_admins_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        old_time = (datetime.now() - timedelta(seconds=svc.SLA_SECONDS + 100)).strftime('%Y-%m-%d %H:%M:%S')
        svc._process_item(self.make_item(queued_at=old_time))
        notify_admins_mock.assert_called_once()

    def test_no_sla_breach_within_limit(self, svc, impala, notify_user_mock, notify_admins_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        svc._process_item(self.make_item(queued_at=datetime.now()))
        notify_admins_mock.assert_not_called()

    def test_lc_amounts_from_item_used_directly(self, svc, impala, notify_user_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        svc._process_item(self.make_item(
            gross_amount_lc=Decimal('10'), total_amount_lc=Decimal('9'), gross_amount_fc=Decimal('5'),
        ))
        kwargs = svc.position_service.calculate_position.call_args[1]
        assert kwargs['gross_amount_lc'] == Decimal('10')
        assert kwargs['trade_lc'] == Decimal('9')
        assert kwargs['gross_amount_fc'] == Decimal('5')

    def test_lc_amounts_parsed_from_error_message_three_field(self, svc, impala, notify_user_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        svc._process_item(self.make_item(error_message='LC:100.0:90.0:50.0'))
        kwargs = svc.position_service.calculate_position.call_args[1]
        assert kwargs['gross_amount_lc'] == Decimal('100.0')
        assert kwargs['trade_lc'] == Decimal('90.0')
        assert kwargs['gross_amount_fc'] == Decimal('50.0')

    def test_lc_amounts_parsed_from_error_message_two_field_legacy(self, svc, impala, notify_user_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        svc._process_item(self.make_item(error_message='LC:100.0:90.0'))
        kwargs = svc.position_service.calculate_position.call_args[1]
        assert kwargs['gross_amount_lc'] == Decimal('100.0')
        assert kwargs['trade_lc'] == Decimal('90.0')
        assert kwargs['gross_amount_fc'] is None

    def test_lc_parse_failure_logs_warning(self, svc, impala, notify_user_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        svc._process_item(self.make_item(error_message='LC:notanumber:xx'))
        # Should not raise; falls through to fetch-from-cis_trade branch
        assert svc.position_service.calculate_position.called

    def test_lc_amounts_fetched_from_cis_trade_when_missing(self, svc, notify_user_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            m.execute_write.return_value = True
            m.execute_query.return_value = [{'total_amount_lc': '90', 'gross_amount_lc': '100', 'gross_amount_fc': '50'}]
            svc._process_item(self.make_item())
        kwargs = svc.position_service.calculate_position.call_args[1]
        assert kwargs['gross_amount_lc'] == Decimal('100')

    def test_lc_fetch_from_cis_trade_exception_handled(self, svc, notify_user_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            m.execute_write.return_value = True
            m.execute_query.side_effect = RuntimeError('boom')
            svc._process_item(self.make_item())
        assert svc.position_service.calculate_position.called

    def test_chain_recalc_detected_and_processed_success(self, svc, impala, notify_user_mock):
        impala.execute_query.return_value = []  # dedup check finds nothing
        with patch.object(svc, '_process_chain_recalculation', return_value={'recalculated': 2, 'errors': 0}) as pcr:
            svc._process_item(self.make_item(error_message='CHAIN_RECALC:P1:S1:2026-01-01'))
        pcr.assert_called_once()
        completed_calls = [c for c in impala.execute_write.call_args_list if 'COMPLETED' in c[0][0]]
        assert len(completed_calls) == 1

    def test_chain_recalc_with_lc_prefix(self, svc, impala, notify_user_mock):
        impala.execute_query.return_value = []
        with patch.object(svc, '_process_chain_recalculation', return_value={'recalculated': 1, 'errors': 0}) as pcr:
            svc._process_item(self.make_item(error_message='LC:1:2:3|CHAIN_RECALC:P1:S1:2026-01-01'))
        pcr.assert_called_once()

    def test_chain_recalc_dedup_already_completed_marks_completed(self, svc, notify_user_mock):
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            m.execute_write.return_value = True
            m.execute_query.return_value = [{'1': 1}]
            with patch.object(svc, '_process_chain_recalculation') as pcr:
                svc._process_item(self.make_item(error_message='CHAIN_RECALC:P1:S1:2026-01-01'))
            pcr.assert_not_called()
            completed_calls = [c for c in m.execute_write.call_args_list if 'COMPLETED' in c[0][0]]
            assert len(completed_calls) == 1

    def test_chain_recalc_dedup_check_exception_continues(self, svc, notify_user_mock):
        with patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m:
            m.execute_write.return_value = True
            m.execute_query.side_effect = RuntimeError('boom')
            with patch.object(svc, '_process_chain_recalculation', return_value={'recalculated': 1, 'errors': 0}) as pcr:
                svc._process_item(self.make_item(error_message='CHAIN_RECALC:P1:S1:2026-01-01'))
            pcr.assert_called_once()

    def test_chain_recalc_with_errors_calls_handle_failure(self, svc, impala, notify_user_mock):
        impala.execute_query.return_value = []
        with patch.object(svc, '_process_chain_recalculation', return_value={'recalculated': 0, 'errors': 1}), \
             patch.object(svc, '_handle_failure') as hf:
            svc._process_item(self.make_item(error_message='CHAIN_RECALC:P1:S1:2026-01-01'))
        hf.assert_called_once()

    def test_chain_recalc_no_trades_found_calls_handle_failure(self, svc, impala, notify_user_mock):
        impala.execute_query.return_value = []
        with patch.object(svc, '_process_chain_recalculation', return_value={'recalculated': 0, 'errors': 0}), \
             patch.object(svc, '_handle_failure') as hf:
            svc._process_item(self.make_item(error_message='CHAIN_RECALC:P1:S1:2026-01-01'))
        hf.assert_called_once()

    def test_deal_number_defaults_to_trade_id_string(self, svc, impala, notify_user_mock):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        svc._process_item(self.make_item(deal_number=None, trade_id=99))
        payload = notify_user_mock.call_args_list[0][0][2]
        assert payload['deal_number'] == '99'


class TestProcessChainRecalculation:
    def base_chain_info(self):
        return {'portfolio_id': 'P1', 'security_id': 'S1', 'from_date': '2026-01-01'}

    def test_no_trades_found_returns_zero_counters(self, svc, impala):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds:
            sds.get_system_date.return_value = datetime(2026, 1, 10)
            impala.execute_query.return_value = []
            result = svc._process_chain_recalculation(self.base_chain_info())
        assert result == {'recalculated': 0, 'errors': 0, 'deleted': 0}

    def test_from_date_yyyymmdd_normalized(self, svc, impala):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds:
            sds.get_system_date.return_value = datetime(2026, 1, 10)
            impala.execute_query.return_value = []
            info = dict(self.base_chain_info())
            info['from_date'] = '20260101'
            svc._process_chain_recalculation(info)
        first_query = impala.execute_query.call_args_list[0][0][0]
        assert '2026-01-01' in first_query

    def test_from_date_iso_with_time_normalized(self, svc, impala):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds:
            sds.get_system_date.return_value = datetime(2026, 1, 10)
            impala.execute_query.return_value = []
            info = dict(self.base_chain_info())
            info['from_date'] = '2026-01-01T00:00:00'
            svc._process_chain_recalculation(info)
        first_query = impala.execute_query.call_args_list[0][0][0]
        assert '2026-01-01' in first_query

    def test_recalculates_trades_both_bases(self, svc, notify_user_mock):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds, \
             patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_queue_service.time.sleep'), \
             patch.object(svc, '_carry_forward_to_today'):
            sds.get_system_date.return_value = datetime(2026, 1, 10)
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-01-02', 'settle_date': '2026-01-02',
                'total_amount_lc': '990', 'gross_amount_lc': '1000', 'gross_amount_fc': '500',
            }]
            m.execute_query.side_effect = [trades, []]  # trades query, then stale rows query
            svc.position_service._get_position_as_of_date.return_value = {}
            svc.position_service.calculate_position.return_value = (True, 'ok', {'quantity': 10})
            result = svc._process_chain_recalculation(self.base_chain_info())
        assert result['recalculated'] == 2  # TRADED + SETTLED
        assert result['errors'] == 0

    def test_skips_basis_with_empty_pos_date(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds, \
             patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_queue_service.time.sleep'), \
             patch.object(svc, '_carry_forward_to_today'):
            sds.get_system_date.return_value = datetime(2026, 1, 10)
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-01-02', 'settle_date': '',
            }]
            m.execute_query.side_effect = [trades, []]
            svc.position_service._get_position_as_of_date.return_value = {}
            svc.position_service.calculate_position.return_value = (True, 'ok', {})
            result = svc._process_chain_recalculation(self.base_chain_info())
        assert result['recalculated'] == 1  # only TRADED basis ran

    def test_skips_basis_pos_date_before_from_date(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds, \
             patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_queue_service.time.sleep'), \
             patch.object(svc, '_carry_forward_to_today'):
            sds.get_system_date.return_value = datetime(2026, 1, 10)
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2025-12-01', 'settle_date': '2025-12-01',
            }]
            m.execute_query.side_effect = [trades, []]
            svc.position_service._get_position_as_of_date.return_value = {}
            svc.position_service.calculate_position.return_value = (True, 'ok', {})
            result = svc._process_chain_recalculation(self.base_chain_info())
        assert result['recalculated'] == 0

    def test_skips_basis_pos_date_after_today(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds, \
             patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_queue_service.time.sleep'), \
             patch.object(svc, '_carry_forward_to_today'):
            sds.get_system_date.return_value = datetime(2026, 1, 10)
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-02-01', 'settle_date': '2026-02-01',
            }]
            m.execute_query.side_effect = [trades, []]
            svc.position_service._get_position_as_of_date.return_value = {}
            svc.position_service.calculate_position.return_value = (True, 'ok', {})
            result = svc._process_chain_recalculation(self.base_chain_info())
        assert result['recalculated'] == 0

    def test_calculate_position_failure_increments_errors(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds, \
             patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_queue_service.time.sleep'), \
             patch.object(svc, '_carry_forward_to_today'):
            sds.get_system_date.return_value = datetime(2026, 1, 10)
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-01-02', 'settle_date': '2026-01-02',
            }]
            m.execute_query.side_effect = [trades, []]
            svc.position_service._get_position_as_of_date.return_value = {}
            svc.position_service.calculate_position.return_value = (False, 'bad', None)
            result = svc._process_chain_recalculation(self.base_chain_info())
        assert result['errors'] == 2

    def test_calculate_position_exception_increments_errors(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds, \
             patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_queue_service.time.sleep'), \
             patch.object(svc, '_carry_forward_to_today'):
            sds.get_system_date.return_value = datetime(2026, 1, 10)
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-01-02', 'settle_date': '2026-01-02',
            }]
            m.execute_query.side_effect = [trades, []]
            svc.position_service._get_position_as_of_date.return_value = {}
            svc.position_service.calculate_position.side_effect = RuntimeError('boom')
            result = svc._process_chain_recalculation(self.base_chain_info())
        assert result['errors'] == 2

    def test_pre_invalidates_stale_rows(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds, \
             patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_queue_service.time.sleep'), \
             patch.object(svc, '_carry_forward_to_today'):
            sds.get_system_date.return_value = datetime(2026, 1, 10)
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-01-02', 'settle_date': '2026-01-02',
            }]
            stale = [{
                'version_id': 5, 'position_id': 6, 'position_date': '2026-01-02',
                'position_basis': 'TRADED', 'portfolio_short_name': 'P1', 'security_label': 'S1',
                'quantity': 10, 'trade_id': 1, 'trade_type': 'BUY',
            }]
            m.execute_query.side_effect = [trades, stale]
            svc.position_service._get_position_as_of_date.return_value = {}
            svc.position_service.calculate_position.return_value = (True, 'ok', {})
            svc._process_chain_recalculation(self.base_chain_info())
        upsert_calls = [c for c in m.execute_write.call_args_list if 'UPSERT INTO' in c[0][0]]
        assert len(upsert_calls) == 1

    def test_exception_returns_partial_counters(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds:
            sds.get_system_date.side_effect = RuntimeError('boom')
            result = svc._process_chain_recalculation(self.base_chain_info())
        assert result == {'recalculated': 0, 'errors': 0, 'deleted': 0}

    def test_seeds_last_position_from_before_from_date(self, svc):
        with patch('edge_jobs_py36.lib.position_queue_service.system_date_service') as sds, \
             patch('edge_jobs_py36.lib.position_queue_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_queue_service.time.sleep'), \
             patch.object(svc, '_carry_forward_to_today'):
            sds.get_system_date.return_value = datetime(2026, 1, 10)
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-01-02', 'settle_date': '2026-01-02',
            }]
            m.execute_query.side_effect = [trades, []]
            svc.position_service._get_position_as_of_date.return_value = {'quantity': 100}
            svc.position_service.calculate_position.return_value = (True, 'ok', {})
            svc._process_chain_recalculation(self.base_chain_info())
        assert svc.position_service._get_position_as_of_date.call_count == 2  # TRADED + SETTLED seed
