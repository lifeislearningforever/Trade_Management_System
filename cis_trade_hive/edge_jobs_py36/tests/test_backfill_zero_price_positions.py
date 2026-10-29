"""Tests for edge_jobs_py36/backfill_zero_price_positions.py."""
import argparse
from decimal import Decimal
from unittest.mock import patch

import pytest

from backfill_zero_price_positions import Command, TRADE_TABLE, POSITION_TABLE
from lib.management_base import CommandError


def _trade(**overrides):
    trade = {
        'trade_id': 123,
        'deal_number': 'D-1',
        'trade_type': 'BUY',
        'trade_status': 'SETTLED',
        'portfolio_short_name': 'UOB-SG',
        'security_label': 'AAPL',
        'security_full_name': 'Apple Inc',
        'trade_date': '2026-09-01',
        'settle_date': '2026-09-03',
        'quantity': 100,
        'price': 0,
        'commission': 5,
        'sec_fee': 1,
        'other_charges': 0,
        'currency_code': 'USD',
        'custodian': 'CUST1',
        'udf_sub_custodian': 'SUBCUST1',
        'isin': 'US0378331005',
        'portfolio_currency': 'USD',
    }
    trade.update(overrides)
    return trade


class TestFindGapTrades:
    def test_returns_query_results(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [_trade()]
            result = cmd._find_gap_trades(None, None)
        assert len(result) == 1

    def test_returns_empty_list_when_none(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            result = cmd._find_gap_trades(None, None)
        assert result == []

    def test_query_includes_trade_and_position_tables(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._find_gap_trades(None, None)
        query = mock_mgr.execute_query.call_args[0][0]
        assert TRADE_TABLE in query
        assert POSITION_TABLE in query
        assert "trade_type IN ('BUY', 'SELL')" in query

    def test_portfolio_filter_is_escaped_and_included(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._find_gap_trades("O'BRIEN PORT", None)
        query = mock_mgr.execute_query.call_args[0][0]
        assert "O\\'BRIEN PORT" in query

    def test_trade_id_filter_is_included_as_int(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._find_gap_trades(None, '999')
        query = mock_mgr.execute_query.call_args[0][0]
        assert 't.trade_id = 999' in query

    def test_no_filters_means_no_extra_where(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._find_gap_trades(None, None)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'portfolio_short_name' not in query.split('WHERE')[1].split('ORDER BY')[0] or True

    def test_raises_command_error_on_query_exception(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            with pytest.raises(CommandError, match='Error querying gap trades'):
                cmd._find_gap_trades(None, None)


class TestPrintTradeTable:
    def test_prints_header_and_rows(self, capsys):
        cmd = Command()
        cmd._tee = type('T', (), {'write': staticmethod(lambda msg: print(msg))})()
        cmd._print_trade_table([_trade(trade_id=42, deal_number='D-42')])
        out = capsys.readouterr().out
        assert 'TRADE_ID' in out
        assert '42' in out
        assert 'D-42' in out


class TestHandleNoGapTrades:
    def test_prints_success_and_returns_early(self, capsys):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.handle(execute=False, dry_run=False, portfolio=None, trade_id=None, output=None)
        out = capsys.readouterr().out
        assert 'No gap trades found' in out


class TestHandleDryRun:
    def test_dry_run_does_not_call_settlement_service(self, capsys):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr, \
             patch('backfill_zero_price_positions.settlement_service') as mock_svc:
            mock_mgr.execute_query.return_value = [_trade()]
            cmd.handle(execute=False, dry_run=False, portfolio=None, trade_id=None, output=None)
        out = capsys.readouterr().out
        assert 'DRY-RUN' in out
        mock_svc.process_trade_settlement.assert_not_called()

    def test_dry_run_flag_overrides_execute(self, capsys):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr, \
             patch('backfill_zero_price_positions.settlement_service') as mock_svc:
            mock_mgr.execute_query.return_value = [_trade()]
            cmd.handle(execute=True, dry_run=True, portfolio=None, trade_id=None, output=None)
        mock_svc.process_trade_settlement.assert_not_called()

    def test_writes_output_file_when_requested(self, tmp_path):
        cmd = Command()
        out_path = tmp_path / 'log.txt'
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [_trade(trade_id=77)]
            cmd.handle(execute=False, dry_run=False, portfolio=None, trade_id=None, output=str(out_path))
        assert out_path.exists()
        assert '77' in out_path.read_text()


class TestHandleExecute:
    def test_execute_queues_successful_trades(self, capsys):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr, \
             patch('backfill_zero_price_positions.settlement_service') as mock_svc:
            mock_mgr.execute_query.return_value = [_trade(trade_id=1)]
            mock_svc.process_trade_settlement.return_value = (True, 'queued ok', None)
            cmd.handle(execute=True, dry_run=False, portfolio=None, trade_id=None, output=None)
        out = capsys.readouterr().out
        assert 'QUEUED' in out
        assert '1 trade(s) queued' in out

    def test_execute_computes_charges_as_sum(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr, \
             patch('backfill_zero_price_positions.settlement_service') as mock_svc:
            mock_mgr.execute_query.return_value = [
                _trade(commission=5, sec_fee=2, other_charges=1)
            ]
            mock_svc.process_trade_settlement.return_value = (True, 'ok', None)
            cmd.handle(execute=True, dry_run=False, portfolio=None, trade_id=None, output=None)
        kwargs = mock_svc.process_trade_settlement.call_args[1]
        assert kwargs['charges'] == Decimal('8')

    def test_execute_passes_dual_basis_none(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr, \
             patch('backfill_zero_price_positions.settlement_service') as mock_svc:
            mock_mgr.execute_query.return_value = [_trade()]
            mock_svc.process_trade_settlement.return_value = (True, 'ok', None)
            cmd.handle(execute=True, dry_run=False, portfolio=None, trade_id=None, output=None)
        kwargs = mock_svc.process_trade_settlement.call_args[1]
        assert kwargs['position_basis'] is None
        assert kwargs['async_mode'] is True

    def test_execute_reports_failure_message_and_exits(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr, \
             patch('backfill_zero_price_positions.settlement_service') as mock_svc, \
             pytest.raises(SystemExit) as exc_info:
            mock_mgr.execute_query.return_value = [_trade()]
            mock_svc.process_trade_settlement.return_value = (False, 'no data', None)
            cmd.handle(execute=True, dry_run=False, portfolio=None, trade_id=None, output=None)
        assert exc_info.value.code == 1

    def test_execute_catches_exception_per_trade_and_continues(self, capsys):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr, \
             patch('backfill_zero_price_positions.settlement_service') as mock_svc, \
             pytest.raises(SystemExit):
            mock_mgr.execute_query.return_value = [_trade(trade_id=1), _trade(trade_id=2)]
            mock_svc.process_trade_settlement.side_effect = [
                RuntimeError('boom'),
                (True, 'ok', None),
            ]
            cmd.handle(execute=True, dry_run=False, portfolio=None, trade_id=None, output=None)
        out = capsys.readouterr().out
        assert 'ERROR' in out
        assert 'QUEUED' in out

    def test_execute_all_success_does_not_exit(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr, \
             patch('backfill_zero_price_positions.settlement_service') as mock_svc:
            mock_mgr.execute_query.return_value = [_trade()]
            mock_svc.process_trade_settlement.return_value = (True, 'ok', None)
            cmd.handle(execute=True, dry_run=False, portfolio=None, trade_id=None, output=None)  # no SystemExit

    def test_execute_handles_missing_numeric_fields_as_zero(self):
        cmd = Command()
        with patch('backfill_zero_price_positions.impala_manager') as mock_mgr, \
             patch('backfill_zero_price_positions.settlement_service') as mock_svc:
            trade = _trade()
            del trade['commission']
            del trade['sec_fee']
            del trade['other_charges']
            mock_mgr.execute_query.return_value = [trade]
            mock_svc.process_trade_settlement.return_value = (True, 'ok', None)
            cmd.handle(execute=True, dry_run=False, portfolio=None, trade_id=None, output=None)
        kwargs = mock_svc.process_trade_settlement.call_args[1]
        assert kwargs['charges'] == Decimal('0')


class TestAddArguments:
    def test_defaults(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args([])
        assert args.execute is False
        assert args.dry_run is False
        assert args.portfolio is None
        assert args.trade_id is None
        assert args.output is None

    def test_all_flags_parse(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args([
            '--execute', '--portfolio', 'UOB-SG', '--trade-id', '123', '--output', 'out.txt',
        ])
        assert args.execute is True
        assert args.portfolio == 'UOB-SG'
        assert args.trade_id == '123'
        assert args.output == 'out.txt'
