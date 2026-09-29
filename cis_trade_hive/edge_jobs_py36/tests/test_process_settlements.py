"""Tests for edge_jobs_py36/process_settlements.py."""
import argparse
from decimal import Decimal
from unittest.mock import patch

import pytest

from process_settlements import Command
from lib.management_base import CommandError


def _base_options(**overrides):
    opts = {
        'date': None,
        'dry_run': False,
        'verbose': False,
        'user': 'SYSTEM',
        'batch_size': 100,
        'backfill_queue': False,
    }
    opts.update(overrides)
    return opts


def _trade_row(**overrides):
    row = {
        'trade_id': 1,
        'portfolio_short_name': 'UOB-SG',
        'security_label': 'AAPL',
        'trade_type': 'BUY',
        'quantity': 100,
        'price': 150.0,
        'commission': 5,
        'sec_fee': 1,
        'other_charges': 0,
        'trade_date': '2026-09-01',
        'settle_date': '2026-09-19',
        'currency_code': 'USD',
        'portfolio_currency': 'USD',
        'isin': 'US0378331005',
        'security_full_name': 'Apple Inc',
    }
    row.update(overrides)
    return row


class TestAddArguments:
    def test_defaults(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args([])
        assert args.date is None
        assert args.dry_run is False
        assert args.verbose is False
        assert args.user == 'SYSTEM'
        assert args.batch_size == 100
        assert args.backfill_queue is False

    def test_all_flags_parse(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args([
            '--date', '2026-09-17', '--dry-run', '--verbose', '--user', 'jdoe',
            '--batch-size', '50', '--backfill-queue',
        ])
        assert args.date == '2026-09-17'
        assert args.dry_run is True
        assert args.user == 'jdoe'
        assert args.batch_size == 50
        assert args.backfill_queue is True


class TestGetContextualToday:
    def test_returns_value_from_alldatesinfo(self):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'contextual_today': '2026-09-17'}]
            result = cmd._get_contextual_today()
        assert result == '2026-09-17'

    def test_falls_back_to_system_date_when_no_rows(self, capsys):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = cmd._get_contextual_today()
        assert result  # a date string
        assert 'falling back to system date' in capsys.readouterr().out

    def test_falls_back_when_value_is_none(self, capsys):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'contextual_today': None}]
            cmd._get_contextual_today()
        assert 'falling back to system date' in capsys.readouterr().out

    def test_falls_back_on_exception(self, capsys):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            cmd._get_contextual_today()
        assert 'falling back to system date' in capsys.readouterr().out


class TestGetPendingSettlements:
    def test_delegates_to_settlement_service(self):
        cmd = Command()
        with patch('process_settlements.settlement_service') as mock_svc:
            mock_svc.get_pending_settlements.return_value = [{'queue_id': 1}]
            result = cmd._get_pending_settlements('2026-09-17')
        assert result == [{'queue_id': 1}]
        mock_svc.get_pending_settlements.assert_called_once_with('2026-09-17')


class TestShowPendingSettlements:
    def test_prints_table_rows(self, capsys):
        cmd = Command()
        pending = [{
            'queue_id': 1, 'trade_id': 100, 'portfolio_id': 'UOB', 'security_id': 'AAPL',
            'trade_type': 'BUY', 'quantity': 100, 'price': 150, 'settle_date': '2026-09-19',
        }]
        cmd._show_pending_settlements(pending)
        out = capsys.readouterr().out
        assert 'Pending Settlements' in out
        assert 'AAPL' in out

    def test_shows_only_first_twenty_and_overflow_message(self, capsys):
        cmd = Command()
        pending = [{'queue_id': i, 'trade_id': i} for i in range(25)]
        cmd._show_pending_settlements(pending)
        out = capsys.readouterr().out
        assert '... and 5 more records' in out


class TestProcessSettlements:
    def test_delegates_to_settlement_service_and_returns_counts(self):
        cmd = Command()
        with patch('process_settlements.settlement_service') as mock_svc:
            mock_svc.process_pending_settlements.return_value = {
                'processed': 3, 'failed': 1, 'skipped': 0,
            }
            results = cmd._process_settlements([{}, {}, {}, {}], '2026-09-17', 'SYSTEM', 100)
        assert results['processed'] == 3
        assert results['failed'] == 1
        assert results['total'] == 4
        assert 'duration_seconds' in results

    def test_missing_keys_default_to_zero(self):
        cmd = Command()
        with patch('process_settlements.settlement_service') as mock_svc:
            mock_svc.process_pending_settlements.return_value = {}
            results = cmd._process_settlements([], '2026-09-17', 'SYSTEM', 100)
        assert results['processed'] == 0
        assert results['failed'] == 0
        assert results['skipped'] == 0


class TestShowSummary:
    def test_shows_basic_counts(self, capsys):
        cmd = Command()
        cmd._show_summary({'total': 5, 'processed': 4, 'failed': 0, 'skipped': 1, 'duration_seconds': 1.23})
        out = capsys.readouterr().out
        assert 'Total Records:     5' in out
        assert 'Processed:         4' in out
        assert 'Duration:          1.23 seconds' in out

    def test_shows_failed_when_nonzero(self, capsys):
        cmd = Command()
        cmd._show_summary({'total': 5, 'processed': 3, 'failed': 2, 'skipped': 0, 'duration_seconds': 0})
        assert 'Failed:            2' in capsys.readouterr().out

    def test_defaults_duration_to_zero_when_missing(self, capsys):
        cmd = Command()
        cmd._show_summary({'total': 0, 'processed': 0, 'failed': 0, 'skipped': 0})
        assert 'Duration:          0.00 seconds' in capsys.readouterr().out


class TestShowPositionResults:
    def test_prints_rows_when_found(self, capsys):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{
                'portfolio_short_name': 'UOB', 'security_label': 'AAPL', 'quantity': 100,
                'average_cost': 150, 'total_cost': 15000, 'realized_pnl': 0, 'status': 'OPEN',
            }]
            cmd._show_position_results('2026-09-17', 'SYSTEM')
        assert 'AAPL' in capsys.readouterr().out

    def test_prints_no_records_message_when_empty(self, capsys):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._show_position_results('2026-09-17', 'SYSTEM')
        assert 'No position records found' in capsys.readouterr().out

    def test_shows_warning_on_exception(self, capsys):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            cmd._show_position_results('2026-09-17', 'SYSTEM')
        assert 'Could not fetch position results' in capsys.readouterr().out


class TestBackfillSettlementQueue:
    def test_no_rows_returns_zeros(self, capsys):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = cmd._backfill_settlement_queue('2026-09-17', 'SYSTEM', dry_run=False)
        assert result == (0, 0, 0)
        assert 'No unqueued future-settle trades found' in capsys.readouterr().out

    def test_dry_run_counts_as_queued_without_calling_service(self):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr, \
             patch('process_settlements.settlement_service') as mock_svc:
            mock_mgr.execute_query.return_value = [_trade_row()]
            queued, skipped, failed = cmd._backfill_settlement_queue('2026-09-17', 'SYSTEM', dry_run=True)
        assert queued == 1
        mock_svc._queue_for_settlement.assert_not_called()

    def test_successful_queue_increments_queued(self):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr, \
             patch('process_settlements.settlement_service') as mock_svc:
            mock_mgr.execute_query.return_value = [_trade_row()]
            mock_svc._queue_for_settlement.return_value = (True, 'queued', None)
            queued, skipped, failed = cmd._backfill_settlement_queue('2026-09-17', 'SYSTEM', dry_run=False)
        assert queued == 1
        assert failed == 0

    def test_service_returns_false_increments_failed(self, capsys):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr, \
             patch('process_settlements.settlement_service') as mock_svc:
            mock_mgr.execute_query.return_value = [_trade_row()]
            mock_svc._queue_for_settlement.return_value = (False, 'already exists', None)
            queued, skipped, failed = cmd._backfill_settlement_queue('2026-09-17', 'SYSTEM', dry_run=False)
        assert failed == 1
        assert 'already exists' in capsys.readouterr().out

    def test_service_exception_increments_failed(self, capsys):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr, \
             patch('process_settlements.settlement_service') as mock_svc:
            mock_mgr.execute_query.return_value = [_trade_row()]
            mock_svc._queue_for_settlement.side_effect = RuntimeError('db down')
            queued, skipped, failed = cmd._backfill_settlement_queue('2026-09-17', 'SYSTEM', dry_run=False)
        assert failed == 1
        assert 'Error' in capsys.readouterr().out

    def test_passes_computed_charges_and_position_basis_settled(self):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr, \
             patch('process_settlements.settlement_service') as mock_svc:
            mock_mgr.execute_query.return_value = [_trade_row(commission=5, sec_fee=2, other_charges=1)]
            mock_svc._queue_for_settlement.return_value = (True, 'ok', None)
            cmd._backfill_settlement_queue('2026-09-17', 'SYSTEM', dry_run=False)
        kwargs = mock_svc._queue_for_settlement.call_args[1]
        assert kwargs['charges'] == Decimal('8')
        assert kwargs['position_basis'] == 'SETTLED'

    def test_outer_query_exception_returns_zeros(self, capsys):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('connection error')
            result = cmd._backfill_settlement_queue('2026-09-17', 'SYSTEM', dry_run=False)
        assert result == (0, 0, 0)
        assert 'Backfill query failed' in capsys.readouterr().out


class TestHandle:
    def test_no_pending_settlements_prints_warning_and_returns(self, capsys):
        cmd = Command()
        with patch('process_settlements.impala_manager') as mock_mgr, \
             patch('process_settlements.settlement_service') as mock_svc:
            mock_svc.get_pending_settlements.return_value = []
            cmd.handle(**_base_options(date='2026-09-17'))
        out = capsys.readouterr().out
        assert 'No pending settlements found' in out

    def test_dry_run_stops_before_processing(self, capsys):
        cmd = Command()
        with patch('process_settlements.settlement_service') as mock_svc:
            mock_svc.get_pending_settlements.return_value = [{'queue_id': 1}]
            cmd.handle(**_base_options(date='2026-09-17', dry_run=True))
        out = capsys.readouterr().out
        assert 'DRY RUN - No changes made' in out
        mock_svc.process_pending_settlements.assert_not_called()

    def test_full_run_processes_and_shows_summary(self, capsys):
        cmd = Command()
        with patch('process_settlements.settlement_service') as mock_svc:
            mock_svc.get_pending_settlements.return_value = [{'queue_id': 1}]
            mock_svc.process_pending_settlements.return_value = {'processed': 1, 'failed': 0, 'skipped': 0}
            cmd.handle(**_base_options(date='2026-09-17'))
        out = capsys.readouterr().out
        assert 'EOD Settlement Processing Completed Successfully' in out

    def test_verbose_shows_position_results(self, capsys):
        cmd = Command()
        with patch('process_settlements.settlement_service') as mock_svc, \
             patch('process_settlements.impala_manager') as mock_mgr:
            mock_svc.get_pending_settlements.return_value = [{'queue_id': 1}]
            mock_svc.process_pending_settlements.return_value = {'processed': 1, 'failed': 0, 'skipped': 0}
            mock_mgr.execute_query.return_value = []
            cmd.handle(**_base_options(date='2026-09-17', verbose=True))
        out = capsys.readouterr().out
        assert 'Position Results' in out

    def test_uses_explicit_date_flag_over_contextual_today(self, capsys):
        cmd = Command()
        with patch('process_settlements.settlement_service') as mock_svc, \
             patch.object(cmd, '_get_contextual_today') as mock_today:
            mock_svc.get_pending_settlements.return_value = []
            cmd.handle(**_base_options(date='2026-01-01'))
        mock_today.assert_not_called()
        out = capsys.readouterr().out
        assert '--date flag' in out

    def test_uses_contextual_today_when_date_not_given(self, capsys):
        cmd = Command()
        with patch('process_settlements.settlement_service') as mock_svc, \
             patch.object(cmd, '_get_contextual_today', return_value='2026-09-17') as mock_today:
            mock_svc.get_pending_settlements.return_value = []
            cmd.handle(**_base_options(date=None))
        mock_today.assert_called_once()
        out = capsys.readouterr().out
        assert 'alldatesinfo.contextual_today' in out

    def test_backfill_queue_flag_runs_backfill_first(self, capsys):
        cmd = Command()
        with patch.object(cmd, '_backfill_settlement_queue', return_value=(2, 1, 0)) as mock_backfill, \
             patch('process_settlements.settlement_service') as mock_svc:
            mock_svc.get_pending_settlements.return_value = []
            cmd.handle(**_base_options(date='2026-09-17', backfill_queue=True))
        mock_backfill.assert_called_once()
        out = capsys.readouterr().out
        assert 'Backfilling Settlement Queue' in out

    def test_unhandled_exception_raises_command_error(self):
        cmd = Command()
        with patch('process_settlements.settlement_service') as mock_svc:
            mock_svc.get_pending_settlements.side_effect = RuntimeError('catastrophic failure')
            with pytest.raises(CommandError, match='EOD settlement processing failed'):
                cmd.handle(**_base_options(date='2026-09-17'))
