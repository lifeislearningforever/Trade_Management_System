"""Tests for edge_jobs_py36/lib/settlement_service.py."""
import sys
import types
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from edge_jobs_py36.lib.settlement_service import SettlementService


@pytest.fixture
def svc():
    mock_pos_svc = MagicMock()
    return SettlementService(position_svc=mock_pos_svc)


@pytest.fixture
def impala():
    with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
        m.execute_write.return_value = True
        m.execute_query.return_value = []
        yield m


@pytest.fixture
def sds():
    with patch('edge_jobs_py36.lib.settlement_service.system_date_service') as m:
        m.get_system_date.return_value = date(2026, 1, 10)
        yield m


@pytest.fixture
def fake_queue_service():
    """Inject fake trade.services.position_queue_service for the property's inline import."""
    mock_svc = MagicMock()
    fake_module = types.ModuleType('trade.services.position_queue_service')
    fake_module.position_queue_service = mock_svc
    with patch.dict(sys.modules, {'trade.services.position_queue_service': fake_module}):
        yield mock_svc


@pytest.fixture
def fake_position_id_service():
    mock_id_fn = MagicMock(return_value=999)
    fake_module = types.ModuleType('trade.services.position_id_service')
    fake_module.position_id = mock_id_fn
    with patch.dict(sys.modules, {'trade.services.position_id_service': fake_module}):
        yield mock_id_fn


class TestInit:
    def test_default_position_service(self):
        s = SettlementService()
        assert s.position_service is not None
        assert s._position_queue_service is None


class TestPositionQueueServiceProperty:
    def test_lazy_loads_and_caches(self, svc, fake_queue_service):
        result1 = svc.position_queue_service
        result2 = svc.position_queue_service
        assert result1 is fake_queue_service
        assert result2 is fake_queue_service


class TestParseDate:
    def test_none_returns_none(self, svc):
        assert svc._parse_date(None) is None

    def test_empty_returns_none(self, svc):
        assert svc._parse_date('') is None

    def test_date_object_passthrough(self, svc):
        d = date(2026, 1, 1)
        assert svc._parse_date(d) == d

    def test_iso_format(self, svc):
        assert svc._parse_date('2026-01-15') == date(2026, 1, 15)

    def test_yyyymmdd_format(self, svc):
        assert svc._parse_date('20260115') == date(2026, 1, 15)

    def test_dmy_dash_format(self, svc):
        assert svc._parse_date('15-01-2026') == date(2026, 1, 15)

    def test_dmy_slash_format(self, svc):
        assert svc._parse_date('15/01/2026') == date(2026, 1, 15)

    def test_unparseable_returns_none(self, svc):
        assert svc._parse_date('not-a-date') is None


class TestGetPreviousMonthEnd:
    def test_returns_last_day_of_prev_month(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.datetime') as dt:
            dt.now.return_value = datetime(2026, 2, 15)
            result = svc._get_previous_month_end()
        assert result == date(2026, 1, 31)


class TestGetCurrentMonthStart:
    def test_returns_first_of_month(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.datetime') as dt:
            dt.now.return_value = datetime(2026, 2, 15)
            result = svc._get_current_month_start()
        assert result == date(2026, 2, 1)


class TestGetDatesInRange:
    def test_returns_inclusive_range(self, svc):
        result = svc._get_dates_in_range('2026-01-01', '2026-01-03')
        assert result == ['2026-01-01', '2026-01-02', '2026-01-03']

    def test_invalid_dates_returns_empty(self, svc):
        assert svc._get_dates_in_range('bad', '2026-01-03') == []


class TestUtilities:
    def test_generate_id_is_int(self, svc):
        assert isinstance(svc._generate_id(), int)

    def test_escape_none(self, svc):
        assert svc._escape(None) == ''

    def test_escape_quote_backslash(self, svc):
        assert svc._escape("O'Brien\\x") == "O\\'Brien\\\\x"

    def test_null_or_str_none(self, svc):
        assert svc._null_or_str(None) == 'NULL'

    def test_null_or_str_empty(self, svc):
        assert svc._null_or_str('') == 'NULL'

    def test_null_or_str_value(self, svc):
        assert svc._null_or_str("it's") == "'it\\'s'"


class TestGetSecurityIsinAndName:
    def test_returns_isin_and_name(self, svc, impala):
        impala.execute_query.return_value = [{'isin': 'ISIN1', 'security_name': 'Sec 1'}]
        isin, name = svc._get_security_isin_and_name('SEC1')
        assert isin == 'ISIN1'
        assert name == 'Sec 1'

    def test_no_result_returns_none_none(self, svc, impala):
        impala.execute_query.return_value = []
        isin, name = svc._get_security_isin_and_name('SEC1')
        assert isin is None and name is None

    def test_exception_returns_none_none(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            isin, name = svc._get_security_isin_and_name('SEC1')
        assert isin is None and name is None


class TestValidateBackdatedSettlement:
    def test_invalid_date_format(self, svc):
        ok, msg = svc.validate_backdated_settlement('not-a-date')
        assert ok is False
        assert 'Invalid date format' in msg

    def test_future_date(self, svc):
        future = (datetime.now().date() + timedelta(days=5)).strftime('%Y-%m-%d')
        ok, msg = svc.validate_backdated_settlement(future)
        assert ok is True
        assert 'Future settlement' in msg

    def test_same_day(self, svc):
        today = datetime.now().date().strftime('%Y-%m-%d')
        ok, msg = svc.validate_backdated_settlement(today)
        assert ok is True
        assert 'Same-day' in msg

    def test_backdated_before_prev_month_end_warns(self, svc):
        old_date = (datetime.now().date().replace(day=1) - timedelta(days=40)).strftime('%Y-%m-%d')
        ok, msg = svc.validate_backdated_settlement(old_date)
        assert ok is True
        assert 'Warning' in msg

    def test_backdated_within_current_month_allowed(self, svc):
        today = datetime.now().date()
        if today.day > 1:
            yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')
            ok, msg = svc.validate_backdated_settlement(yesterday)
            assert ok is True
            assert 'allowed' in msg


class TestGetPendingSettlements:
    def test_returns_results(self, svc, impala):
        impala.execute_query.return_value = [{'queue_id': 1}]
        result = svc.get_pending_settlements('2026-01-01')
        assert result == [{'queue_id': 1}]

    def test_default_date_used_when_none(self, svc, impala):
        svc.get_pending_settlements()
        query = impala.execute_query.call_args[0][0]
        assert 'settle_date <=' in query

    def test_none_result_returns_empty_list(self, svc, impala):
        impala.execute_query.return_value = None
        assert svc.get_pending_settlements('2026-01-01') == []

    def test_exception_returns_empty_list(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_pending_settlements('2026-01-01') == []


class TestUpdateQueueStatus:
    def test_basic_update(self, svc, impala):
        result = svc._update_queue_status(1, svc.STATUS_PROCESSING)
        assert result is True
        query = impala.execute_write.call_args[0][0]
        assert "status = 'PROCESSING'" in query

    def test_with_error_message(self, svc, impala):
        svc._update_queue_status(1, svc.STATUS_FAILED, error_message="it's bad")
        query = impala.execute_write.call_args[0][0]
        assert "error_message = 'it\\'s bad'" in query

    def test_completed_sets_processed_at(self, svc, impala):
        svc._update_queue_status(1, svc.STATUS_COMPLETED)
        query = impala.execute_write.call_args[0][0]
        assert 'processed_at' in query

    def test_failed_sets_retry_count_and_processed_at(self, svc, impala):
        svc._update_queue_status(1, svc.STATUS_FAILED)
        query = impala.execute_write.call_args[0][0]
        assert 'retry_count' in query
        assert 'processed_at' in query

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            assert svc._update_queue_status(1, svc.STATUS_FAILED) is False


class TestGetSettlementStatistics:
    def test_aggregates_by_status(self, svc, impala):
        impala.execute_query.return_value = [
            {'status': 'PENDING', 'count': 3}, {'status': 'COMPLETED', 'count': 7},
        ]
        stats = svc.get_settlement_statistics()
        assert stats['pending'] == 3
        assert stats['completed'] == 7
        assert stats['total'] == 10

    def test_no_results_returns_zeros(self, svc, impala):
        impala.execute_query.return_value = None
        stats = svc.get_settlement_statistics()
        assert stats['total'] == 0

    def test_exception_returns_default(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            stats = svc.get_settlement_statistics()
        assert stats == {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0, 'total': 0}


class TestQueueForSettlement:
    def test_success(self, svc, impala):
        ok, msg, result = svc._queue_for_settlement(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-02-01', updated_by='user1',
        )
        assert ok is True
        assert result['status'] == svc.STATUS_PENDING

    def test_failure(self, svc, impala):
        impala.execute_write.return_value = False
        ok, msg, result = svc._queue_for_settlement(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-02-01', updated_by='user1',
        )
        assert ok is False
        assert result is None

    def test_with_lc_fc_amounts(self, svc, impala):
        ok, msg, result = svc._queue_for_settlement(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-02-01', updated_by='user1',
            trade_lc=Decimal('900'), gross_amount_lc=Decimal('1000'), gross_amount_fc=Decimal('950'),
        )
        assert ok is True
        query = impala.execute_write.call_args[0][0]
        assert 'CAST(900.0' in query

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            ok, msg, result = svc._queue_for_settlement(
                trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
                quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
                settle_date='2026-02-01', updated_by='user1',
            )
        assert ok is False


class TestFlagForChainRecalculation:
    def test_success(self, svc, impala):
        result = svc._flag_for_chain_recalculation(1, 'P1', 'S1', '2026-01-01')
        assert result is True
        query = impala.execute_write.call_args[0][0]
        assert 'CHAIN_RECALC:P1:S1:2026-01-01' in query

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            result = svc._flag_for_chain_recalculation(1, 'P1', 'S1', '2026-01-01')
        assert result is False


class TestProcessImmediateSettlement:
    def test_success(self, svc):
        svc.position_service.calculate_position.return_value = (True, 'ok', {'x': 1})
        ok, msg, position = svc._process_immediate_settlement(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            position_date='2026-01-01', updated_by='user1',
        )
        assert ok is True
        assert position == {'x': 1}

    def test_failure(self, svc):
        svc.position_service.calculate_position.return_value = (False, 'failed', None)
        ok, msg, position = svc._process_immediate_settlement(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            position_date='2026-01-01', updated_by='user1',
        )
        assert ok is False
        assert position is None

    def test_forwards_gross_amounts(self, svc):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        svc._process_immediate_settlement(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            position_date='2026-01-01', updated_by='user1',
            gross_amount_fc=Decimal('1000'), gross_amount_lc=Decimal('900'),
        )
        kwargs = svc.position_service.calculate_position.call_args[1]
        assert kwargs['gross_amount_fc'] == Decimal('1000')
        assert kwargs['gross_amount_lc'] == Decimal('900')


class TestQueueForAsyncProcessing:
    def test_backdated_generates_chain_recalc_metadata(self, svc, fake_queue_service):
        fake_queue_service.enqueue_position_calculation.return_value = (True, 'ok', 1)
        ok, msg, result = svc._queue_for_async_processing(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-01', updated_by='user1', settlement_type='BACKDATED',
            trade_date='2026-01-01',
        )
        assert ok is True
        kwargs = fake_queue_service.enqueue_position_calculation.call_args[1]
        assert kwargs['chain_recalc_metadata'] == 'CHAIN_RECALC:P1:S1:2026-01-01'

    def test_t0_with_prior_backdated_upgrades_to_chain_recalc(self, svc, fake_queue_service, impala, sds):
        impala.execute_query.return_value = [{'1': 1}]  # prior backdated exists
        fake_queue_service.enqueue_position_calculation.return_value = (True, 'ok', 1)
        ok, msg, result = svc._queue_for_async_processing(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-10', updated_by='user1', settlement_type='T+0',
            trade_date='2026-01-10',
        )
        assert ok is True
        kwargs = fake_queue_service.enqueue_position_calculation.call_args[1]
        assert kwargs['chain_recalc_metadata'] is not None

    def test_t0_without_prior_backdated_no_chain_recalc(self, svc, fake_queue_service, impala, sds):
        impala.execute_query.return_value = []
        fake_queue_service.enqueue_position_calculation.return_value = (True, 'ok', 1)
        ok, msg, result = svc._queue_for_async_processing(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-01-10', updated_by='user1', settlement_type='T+0',
            trade_date='2026-01-10',
        )
        kwargs = fake_queue_service.enqueue_position_calculation.call_args[1]
        assert kwargs['chain_recalc_metadata'] is None

    def test_t0_check_exception_swallowed(self, svc, fake_queue_service, sds):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            fake_queue_service.enqueue_position_calculation.return_value = (True, 'ok', 1)
            ok, msg, result = svc._queue_for_async_processing(
                trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
                quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
                settle_date='2026-01-10', updated_by='user1', settlement_type='T+0',
                trade_date='2026-01-10',
            )
        assert ok is True

    def test_future_settlement_no_chain_recalc(self, svc, fake_queue_service):
        fake_queue_service.enqueue_position_calculation.return_value = (True, 'ok', 1)
        ok, msg, result = svc._queue_for_async_processing(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-02-01', updated_by='user1', settlement_type='FUTURE',
        )
        kwargs = fake_queue_service.enqueue_position_calculation.call_args[1]
        assert kwargs['chain_recalc_metadata'] is None

    def test_enqueue_failure_returns_false(self, svc, fake_queue_service):
        fake_queue_service.enqueue_position_calculation.return_value = (False, 'queue full', None)
        ok, msg, result = svc._queue_for_async_processing(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-02-01', updated_by='user1', settlement_type='FUTURE',
        )
        assert ok is False
        assert result is None

    def test_exception_returns_false(self, svc, fake_queue_service):
        fake_queue_service.enqueue_position_calculation.side_effect = RuntimeError('boom')
        ok, msg, result = svc._queue_for_async_processing(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            settle_date='2026-02-01', updated_by='user1', settlement_type='FUTURE',
        )
        assert ok is False
        assert 'Queue error' in msg


class TestProcessPendingSettlements:
    def test_no_pending_returns_zero_counters(self, svc, impala):
        result = svc.process_pending_settlements('2026-01-01')
        assert result == {'processed': 0, 'failed': 0, 'skipped': 0}

    def test_successful_settlement_marks_completed(self, svc, impala):
        impala.execute_query.return_value = [{
            'queue_id': 1, 'trade_id': 2, 'portfolio_id': 'P1', 'security_id': 'S1',
            'trade_type': 'BUY', 'quantity': 10, 'price': 100, 'settle_date': '2026-01-01',
        }]
        svc.position_service.calculate_position.return_value = (True, 'ok', {'x': 1})
        result = svc.process_pending_settlements('2026-01-01')
        assert result['processed'] == 1

    def test_failed_settlement_marks_failed(self, svc, impala):
        impala.execute_query.return_value = [{
            'queue_id': 1, 'trade_id': 2, 'portfolio_id': 'P1', 'security_id': 'S1',
            'trade_type': 'BUY', 'quantity': 10, 'price': 100, 'settle_date': '2026-01-01',
        }]
        svc.position_service.calculate_position.return_value = (False, 'bad', None)
        result = svc.process_pending_settlements('2026-01-01')
        assert result['failed'] == 1

    def test_exception_during_item_processing_marks_failed(self, svc, impala):
        impala.execute_query.return_value = [{
            'queue_id': 1, 'trade_id': 2, 'portfolio_id': 'P1', 'security_id': 'S1',
            'trade_type': 'BUY', 'quantity': 10, 'price': 100, 'settle_date': '2026-01-01',
        }]
        svc.position_service.calculate_position.side_effect = RuntimeError('boom')
        result = svc.process_pending_settlements('2026-01-01')
        assert result['failed'] == 1

    def test_lc_fc_amounts_forwarded(self, svc, impala):
        impala.execute_query.return_value = [{
            'queue_id': 1, 'trade_id': 2, 'portfolio_id': 'P1', 'security_id': 'S1',
            'trade_type': 'BUY', 'quantity': 10, 'price': 100, 'settle_date': '2026-01-01',
            'trade_lc': '900', 'gross_amount_lc': '1000', 'gross_amount_fc': '950',
        }]
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        svc.process_pending_settlements('2026-01-01')
        kwargs = svc.position_service.calculate_position.call_args[1]
        assert kwargs['trade_lc'] == Decimal('900')

    def test_default_date_used_when_none(self, svc, impala):
        result = svc.process_pending_settlements()
        assert result == {'processed': 0, 'failed': 0, 'skipped': 0}

    def test_outer_exception_returns_partial_counters(self, svc):
        with patch.object(svc, 'get_pending_settlements', side_effect=RuntimeError('boom')):
            result = svc.process_pending_settlements('2026-01-01')
        assert result == {'processed': 0, 'failed': 0, 'skipped': 0}


class TestProcessBackdatedSettlement:
    def test_success_triggers_chain_recalc(self, svc):
        svc.position_service.calculate_position.return_value = (True, 'ok', {'x': 1})
        with patch.object(svc, '_recalculate_position_chain', return_value={'recalculated': 3, 'errors': 0}) as rc:
            ok, msg, result = svc._process_backdated_settlement(
                trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
                quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
                settle_date='2025-12-01', updated_by='user1', trade_date='2025-12-01',
                position_basis='TRADED',
            )
        assert ok is True
        assert '3 positions' in msg
        rc.assert_called_once()

    def test_failure_returns_early(self, svc):
        svc.position_service.calculate_position.return_value = (False, 'bad', None)
        with patch.object(svc, '_recalculate_position_chain') as rc:
            ok, msg, result = svc._process_backdated_settlement(
                trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
                quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
                settle_date='2025-12-01', updated_by='user1',
            )
        assert ok is False
        rc.assert_not_called()

    def test_very_old_backdated_logs_warning(self, svc):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        very_old = '2020-01-01'
        with patch.object(svc, '_recalculate_position_chain', return_value={'recalculated': 0, 'errors': 0}):
            ok, msg, result = svc._process_backdated_settlement(
                trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
                quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
                settle_date=very_old, updated_by='user1',
            )
        assert ok is True

    def test_settled_basis_uses_settle_date_as_position_date(self, svc):
        svc.position_service.calculate_position.return_value = (True, 'ok', None)
        with patch.object(svc, '_recalculate_position_chain', return_value={'recalculated': 0, 'errors': 0}):
            svc._process_backdated_settlement(
                trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
                quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
                settle_date='2025-12-01', updated_by='user1', trade_date='2025-11-28',
                position_basis='SETTLED',
            )
        kwargs = svc.position_service.calculate_position.call_args[1]
        assert kwargs['position_date'] == '2025-12-01'


class TestRecalculatePositionChain:
    def test_no_trades_zeroes_positions(self, svc, impala, sds):
        impala.execute_query.return_value = []
        result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result == {'recalculated': 0, 'errors': 0}
        zero_calls = [c for c in impala.execute_write.call_args_list if 'is_latest' in c[0][0] and 'false' in c[0][0]]
        assert len(zero_calls) >= 1

    def test_no_trades_cis_position_zero_exception_nonfatal(self, svc, sds):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.return_value = []
            calls = {'n': 0}
            def write_side_effect(*a, **kw):
                calls['n'] += 1
                if calls['n'] == 2:
                    raise RuntimeError('boom')
                return True
            m.execute_write.side_effect = write_side_effect
            result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result == {'recalculated': 0, 'errors': 0}

    def test_no_trades_first_zero_exception_logged(self, svc, sds):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.return_value = []
            def write_side_effect(query, **kw):
                if 'cis_trade_position' in query and 'quantity' in query:
                    raise RuntimeError('boom')
                return True
            m.execute_write.side_effect = write_side_effect
            result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result == {'recalculated': 0, 'errors': 0}

    def test_drain_queue_exception_nonfatal(self, svc, sds):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            calls = {'n': 0}
            def write_side_effect(*a, **kw):
                calls['n'] += 1
                if calls['n'] == 1:
                    raise RuntimeError('boom')
                return True
            m.execute_write.side_effect = write_side_effect
            m.execute_query.return_value = []
            result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result == {'recalculated': 0, 'errors': 0}

    def test_recalculates_trades_both_bases(self, svc, sds, fake_position_id_service):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-01-02', 'settle_date': '2026-01-02',
                'security_currency': 'USD', 'portfolio_currency': 'SGD',
                'total_amount_lc': '900', 'gross_amount_lc': '1000', 'gross_amount_fc': '950',
            }]
            m.execute_query.side_effect = [
                trades,  # main trades query
                [], [],  # seed queries for TRADED, SETTLED
                [{'isin': 'ISIN1', 'security_name': 'Sec1'}],  # isin lookup
            ]
            svc.position_service.calculate_position.return_value = (True, 'ok', {'quantity': 10})
            with patch.object(svc, '_fill_carry_forward_positions'):
                result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result['recalculated'] == 2
        assert result['errors'] == 0

    def test_skips_basis_with_empty_pos_date(self, svc, sds, fake_position_id_service):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-01-02', 'settle_date': '',
            }]
            m.execute_query.side_effect = [trades, [], [], []]
            svc.position_service.calculate_position.return_value = (True, 'ok', {})
            with patch.object(svc, '_fill_carry_forward_positions'):
                result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result['recalculated'] == 1

    def test_skips_basis_pos_date_before_from_date(self, svc, sds, fake_position_id_service):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2025-12-01', 'settle_date': '2025-12-01',
            }]
            m.execute_query.side_effect = [trades, [], [], []]
            svc.position_service.calculate_position.return_value = (True, 'ok', {})
            with patch.object(svc, '_fill_carry_forward_positions'):
                result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result['recalculated'] == 0

    def test_skips_basis_pos_date_after_today(self, svc, sds, fake_position_id_service):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-02-01', 'settle_date': '2026-02-01',
            }]
            m.execute_query.side_effect = [trades, [], [], []]
            svc.position_service.calculate_position.return_value = (True, 'ok', {})
            with patch.object(svc, '_fill_carry_forward_positions'):
                result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result['recalculated'] == 0

    def test_calculate_position_failure_increments_errors(self, svc, sds, fake_position_id_service):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-01-02', 'settle_date': '2026-01-02',
            }]
            m.execute_query.side_effect = [trades, [], [], []]
            svc.position_service.calculate_position.return_value = (False, 'bad', None)
            with patch.object(svc, '_fill_carry_forward_positions'):
                result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result['errors'] == 2

    def test_calculate_position_exception_increments_errors(self, svc, sds, fake_position_id_service):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            trades = [{
                'trade_id': 1, 'trade_type': 'BUY', 'quantity': 10, 'price': 100,
                'charges': 1, 'trade_date': '2026-01-02', 'settle_date': '2026-01-02',
            }]
            m.execute_query.side_effect = [trades, [], [], []]
            svc.position_service.calculate_position.side_effect = RuntimeError('boom')
            with patch.object(svc, '_fill_carry_forward_positions'):
                result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result['errors'] == 2

    def test_seeds_from_prior_position(self, svc, sds, fake_position_id_service):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.side_effect = [
                [],  # no trades
            ]
            result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result == {'recalculated': 0, 'errors': 0}

    def test_outer_exception_returns_partial_counters(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.system_date_service') as sds2:
            sds2.get_system_date.side_effect = RuntimeError('boom')
            result = svc._recalculate_position_chain('P1', 'S1', '2026-01-01', 'user1')
        assert result == {'recalculated': 0, 'errors': 0}


class TestFillCarryForwardPositions:
    def test_no_gap_days_no_writes(self, svc, impala):
        counters = {'recalculated': 0, 'errors': 0}
        impala.execute_query.side_effect = [
            [{'biz_date': '20260102'}],  # alldatesinfo
            [],  # existing rows
            [],  # seed TRADED
            [],  # seed SETTLED
        ]
        with patch.object(svc, '_get_security_isin_and_name', return_value=(None, None)):
            svc._fill_carry_forward_positions('P1', 'S1', '2026-01-01', '2026-01-02', 'user1', counters)
        assert counters['recalculated'] == 0

    def test_carries_forward_on_gap_day(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.side_effect = [
                [{'biz_date': '20260102'}],  # alldatesinfo
                [],  # existing rows (none exist)
                [{'position_id': 1, 'quantity': 10}],  # seed TRADED
                [],  # seed SETTLED
            ]
            with patch.object(svc, '_get_security_isin_and_name', return_value=('ISIN1', 'Sec1')), \
                 patch.object(svc, '_write_carry_forward_position', return_value={'quantity': 10}) as wcf:
                svc._fill_carry_forward_positions('P1', 'S1', '2026-01-01', '2026-01-02', 'user1', counters)
        # Both 2026-01-01 and 2026-01-02 are weekdays with no existing row, so both
        # get carried forward (calendar fallback unions with the sparse alldatesinfo result).
        assert counters['recalculated'] == 2
        assert wcf.call_count == 2

    def test_carry_forward_write_exception_nonfatal(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.side_effect = [
                [{'biz_date': '20260102'}],
                [],
                [{'position_id': 1, 'quantity': 10}],
                [],
            ]
            with patch.object(svc, '_get_security_isin_and_name', return_value=(None, None)), \
                 patch.object(svc, '_write_carry_forward_position', side_effect=RuntimeError('boom')):
                svc._fill_carry_forward_positions('P1', 'S1', '2026-01-01', '2026-01-02', 'user1', counters)
        assert counters['recalculated'] == 0  # write failed, not counted

    def test_existing_position_updates_last_known(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.side_effect = [
                [{'biz_date': '20260102'}],
                [{'position_basis': 'TRADED', 'position_date': '2026-01-02'}],  # existing row
                [],  # seed TRADED
                [{'position_id': 5, 'quantity': 20}],  # row for existing date
                [],  # seed SETTLED
            ]
            with patch.object(svc, '_get_security_isin_and_name', return_value=(None, None)):
                svc._fill_carry_forward_positions('P1', 'S1', '2026-01-01', '2026-01-02', 'user1', counters)
        assert counters['recalculated'] == 0

    def test_alldatesinfo_exception_falls_back_to_calendar(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            def query_side_effect(query, **kw):
                if 'alldatesinfo' in query:
                    raise RuntimeError('boom')
                return []
            m.execute_query.side_effect = query_side_effect
            with patch.object(svc, '_get_security_isin_and_name', return_value=(None, None)):
                svc._fill_carry_forward_positions('P1', 'S1', '2026-01-01', '2026-01-02', 'user1', counters)
        assert counters['recalculated'] == 0

    def test_no_prior_position_skips_gap_day(self, svc):
        counters = {'recalculated': 0, 'errors': 0}
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.side_effect = [
                [{'biz_date': '20260102'}],
                [],  # existing rows
                [],  # seed TRADED (no prior)
                [],  # seed SETTLED (no prior)
            ]
            with patch.object(svc, '_get_security_isin_and_name', return_value=(None, None)), \
                 patch.object(svc, '_write_carry_forward_position') as wcf:
                svc._fill_carry_forward_positions('P1', 'S1', '2026-01-01', '2026-01-02', 'user1', counters)
        wcf.assert_not_called()

    def test_outer_exception_swallowed(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            counters = {'recalculated': 0, 'errors': 0}
            with patch.object(svc, '_get_security_isin_and_name', side_effect=RuntimeError('boom')):
                svc._fill_carry_forward_positions('P1', 'S1', '2026-01-01', '2026-01-02', 'user1', counters)
        # should not raise
        assert counters == {'recalculated': 0, 'errors': 0}


class TestWriteCarryForwardPosition:
    def base_source(self, **overrides):
        src = {
            'quantity': 10, 'average_cost_fc': 90, 'total_cost_fc': 900,
            'average_cost_lc': 95, 'total_cost_lc': 950, 'market_value_fc': 950,
            'realized_pnl_fc': 0, 'realized_pnl_lc': 0, 'unrealized_pnl_fc': 50,
            'market_price': 95, 'dividend_fc': 0, 'dividend_lc': 0,
            'trade_id': 1, 'trade_type': 'BUY', 'security_currency': 'USD',
            'portfolio_currency': 'SGD', 'fx_rate': 1.35, 'status': 'OPEN',
            'uncall_fc': 0, 'uncall_lc': 0, 'pipeline_fc': 0, 'pipeline_lc': 0,
            'provision_fc': 0, 'provision_lc': 0, 'position_type': 'INT',
        }
        src.update(overrides)
        return src

    def test_writes_upserts_position_and_syncs(self, svc, impala, fake_position_id_service):
        svc.position_service._get_fx_rate.return_value = Decimal('1.35')
        svc.position_service._get_portfolio_revaluation_status.return_value = 'REVALUED'
        svc.position_service._is_equity_method_portfolio.return_value = False
        svc.position_service._get_currency_dp.return_value = 2
        svc.position_service._round_amount.side_effect = lambda v, dp: round(v, dp)
        result = svc._write_carry_forward_position(
            self.base_source(), 'TRADED', '2026-01-02', 'P1', 'S1', 'user1', isin='ISIN1',
        )
        assert result['position_date'] == '2026-01-02'
        upsert_calls = [c for c in impala.execute_write.call_args_list if 'UPSERT INTO' in c[0][0]]
        assert len(upsert_calls) >= 1

    def test_non_revalued_carries_lc_forward(self, svc, impala, fake_position_id_service):
        svc.position_service._get_fx_rate.return_value = Decimal('1.35')
        svc.position_service._get_portfolio_revaluation_status.return_value = 'NON-REVALUED'
        svc.position_service._is_equity_method_portfolio.return_value = False
        svc.position_service._get_currency_dp.return_value = 2
        svc.position_service._round_amount.side_effect = lambda v, dp: round(v, dp)
        result = svc._write_carry_forward_position(
            self.base_source(), 'TRADED', '2026-01-02', 'P1', 'S1', 'user1',
        )
        assert result['average_cost_lc'] == 95

    def test_equity_method_zeroes_unrealized_pnl_lc(self, svc, impala, fake_position_id_service):
        svc.position_service._get_fx_rate.return_value = Decimal('1.35')
        svc.position_service._get_portfolio_revaluation_status.return_value = 'REVALUED'
        svc.position_service._is_equity_method_portfolio.return_value = True
        svc.position_service._get_currency_dp.return_value = 2
        svc.position_service._round_amount.side_effect = lambda v, dp: round(v, dp)
        result = svc._write_carry_forward_position(
            self.base_source(), 'TRADED', '2026-01-02', 'P1', 'S1', 'user1',
        )
        assert result['unrealized_pnl_lc'] == 0

    def test_missing_currency_uses_source_fx_rate(self, svc, impala, fake_position_id_service):
        svc.position_service._get_portfolio_revaluation_status.return_value = 'REVALUED'
        svc.position_service._is_equity_method_portfolio.return_value = False
        svc.position_service._get_currency_dp.return_value = 2
        svc.position_service._round_amount.side_effect = lambda v, dp: round(v, dp)
        source = self.base_source(security_currency=None, portfolio_currency=None)
        result = svc._write_carry_forward_position(
            source, 'TRADED', '2026-01-02', 'P1', 'S1', 'user1',
        )
        assert result['fx_rate'] == 1.35


class TestSyncCarryForwardToCisPosition:
    def test_writes_upsert(self, svc, impala):
        svc.position_service._get_currency_dp.return_value = 2
        svc.position_service._round_amount.side_effect = lambda v, dp: round(v, dp)
        svc._sync_carry_forward_to_cis_position(
            source={'total_cost_fc': 900, 'unrealized_pnl_fc': 50, 'provision_fc': 0,
                    'total_cost_lc': 950, 'unrealized_pnl_lc': 55, 'provision_lc': 0,
                    'quantity': 10, 'position_type': 'INT'},
            basis='TRADED', position_date='2026-01-02',
            portfolio_id='P1', security_id='S1', position_id=1,
            updated_by='user1', timestamp='2026-01-02 10:00:00', isin='ISIN1',
        )
        upsert_calls = [c for c in impala.execute_write.call_args_list if 'UPSERT INTO' in c[0][0]]
        assert len(upsert_calls) == 1
        assert 'ISIN1' in upsert_calls[0][0][0]

    def test_exception_swallowed_nonfatal(self, svc):
        svc.position_service._get_currency_dp.return_value = 2
        svc.position_service._round_amount.side_effect = lambda v, dp: round(v, dp)
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            svc._sync_carry_forward_to_cis_position(
                source={'total_cost_fc': 900, 'unrealized_pnl_fc': 50, 'provision_fc': 0,
                        'total_cost_lc': 950, 'unrealized_pnl_lc': 55, 'provision_lc': 0,
                        'quantity': 10},
                basis='TRADED', position_date='2026-01-02',
                portfolio_id='P1', security_id='S1', position_id=1,
                updated_by='user1', timestamp='2026-01-02 10:00:00',
            )  # should not raise


class TestMarkOldVersionsNotLatestInSettlement:
    def test_writes_update(self, svc, impala):
        svc._mark_old_versions_not_latest_in_settlement('P1', 'S1', '2026-01-02', 'TRADED', '2026-01-02 10:00:00')
        query = impala.execute_write.call_args[0][0]
        assert 'is_latest' in query and 'false' in query

    def test_exception_nonfatal(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            svc._mark_old_versions_not_latest_in_settlement('P1', 'S1', '2026-01-02', 'TRADED', '2026-01-02 10:00:00')


class TestProcessTradeSettlement:
    def common_kwargs(self, **overrides):
        kwargs = dict(
            trade_id=1, portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            trade_date='2026-01-10', settle_date='2026-01-10', updated_by='user1',
        )
        kwargs.update(overrides)
        return kwargs

    def test_invalid_settle_date_returns_false(self, svc, sds):
        ok, msg, result = svc.process_trade_settlement(**self.common_kwargs(settle_date='bad-date'))
        assert ok is False
        assert 'Invalid settlement date' in msg

    def test_dual_basis_both_succeed(self, svc, sds, fake_queue_service):
        fake_queue_service.enqueue_position_calculation.return_value = (True, 'ok', 1)
        ok, msg, result = svc.process_trade_settlement(**self.common_kwargs())
        assert ok is True
        assert 'TRADED' in msg and 'SETTLED' in msg

    def test_dual_basis_one_fails_overall_false(self, svc, sds, fake_queue_service):
        fake_queue_service.enqueue_position_calculation.side_effect = [
            (True, 'ok', 1), (False, 'fail', None),
        ]
        ok, msg, result = svc.process_trade_settlement(**self.common_kwargs())
        assert ok is False

    def test_single_basis_call(self, svc, sds, fake_queue_service):
        fake_queue_service.enqueue_position_calculation.return_value = (True, 'ok', 1)
        ok, msg, result = svc.process_trade_settlement(**self.common_kwargs(position_basis='TRADED'))
        assert ok is True

    def test_future_settle_date_settled_basis_queued(self, svc, sds, impala):
        future_date = '2026-02-15'
        with patch.object(svc, '_queue_for_async_processing', return_value=(True, 'ok', {})) as async_mock, \
             patch.object(svc, '_queue_for_settlement', return_value=(True, 'ok', {})) as future_mock:
            ok, msg, result = svc.process_trade_settlement(**self.common_kwargs(settle_date=future_date))
        future_mock.assert_called_once()
        async_mock.assert_called_once()  # TRADED still goes async

    def test_sync_mode_t0_calls_process_immediate(self, svc, sds, impala):
        with patch.object(svc, '_process_immediate_settlement', return_value=(True, 'ok', {})) as imm_mock:
            ok, msg, result = svc.process_trade_settlement(
                **self.common_kwargs(async_mode=False, position_basis='TRADED')
            )
        imm_mock.assert_called_once()
        assert ok is True

    def test_sync_mode_future_calls_queue_for_settlement(self, svc, sds, impala):
        future_date = '2026-02-15'
        with patch.object(svc, '_queue_for_settlement', return_value=(True, 'ok', {})) as fut_mock:
            ok, msg, result = svc.process_trade_settlement(
                **self.common_kwargs(async_mode=False, settle_date=future_date, trade_date=future_date, position_basis='SETTLED')
            )
        fut_mock.assert_called_once()

    def test_sync_mode_backdated_calls_process_backdated(self, svc, sds, impala):
        with patch.object(svc, '_process_backdated_settlement', return_value=(True, 'ok', {})) as bd_mock:
            ok, msg, result = svc.process_trade_settlement(
                **self.common_kwargs(async_mode=False, settle_date='2025-12-01', trade_date='2025-12-01', position_basis='TRADED')
            )
        bd_mock.assert_called_once()

    def test_sync_mode_clears_stale_position_via_core_impala(self, svc, sds):
        fake_module = types.ModuleType('core.repositories.impala_connection')
        fake_imp = MagicMock()
        fake_imp.execute_write.return_value = True
        fake_module.impala_manager = fake_imp
        with patch.dict(sys.modules, {'core.repositories.impala_connection': fake_module}):
            with patch.object(svc, '_process_immediate_settlement', return_value=(True, 'ok', {})):
                svc.process_trade_settlement(
                    **self.common_kwargs(async_mode=False, position_basis='TRADED')
                )
        fake_imp.execute_write.assert_called_once()

    def test_sync_mode_clear_stale_exception_nonfatal(self, svc, sds):
        fake_module = types.ModuleType('core.repositories.impala_connection')
        fake_imp = MagicMock()
        fake_imp.execute_write.side_effect = RuntimeError('boom')
        fake_module.impala_manager = fake_imp
        with patch.dict(sys.modules, {'core.repositories.impala_connection': fake_module}):
            with patch.object(svc, '_process_immediate_settlement', return_value=(True, 'ok', {})):
                ok, msg, result = svc.process_trade_settlement(
                    **self.common_kwargs(async_mode=False, position_basis='TRADED')
                )
        assert ok is True

    def test_backdated_trade_date_settled_today_uses_per_basis_type(self, svc, sds, fake_queue_service):
        # trade_date backdated but settle_date == today: TRADED basis should be BACKDATED,
        # SETTLED basis should be T+0 — verified via which async helper each basis uses.
        fake_queue_service.enqueue_position_calculation.return_value = (True, 'ok', 1)
        with patch.object(svc, '_queue_for_async_processing', wraps=svc._queue_for_async_processing) as async_spy:
            ok, msg, result = svc.process_trade_settlement(
                **self.common_kwargs(trade_date='2026-01-05', settle_date='2026-01-10')
            )
        call_settlement_types = [c[1]['settlement_type'] for c in async_spy.call_args_list]
        assert 'BACKDATED' in call_settlement_types
        assert 'T+0' in call_settlement_types

    def test_outer_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.settlement_service.system_date_service') as sds2:
            sds2.get_system_date.side_effect = RuntimeError('boom')
            ok, msg, result = svc.process_trade_settlement(**self.common_kwargs())
        assert ok is False
        assert 'Settlement processing error' in msg
