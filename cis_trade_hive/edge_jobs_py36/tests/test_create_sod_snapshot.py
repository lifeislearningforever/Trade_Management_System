"""Tests for edge_jobs_py36/create_sod_snapshot.py."""
import argparse
import sys
import types
from unittest.mock import patch, MagicMock

import pytest

from create_sod_snapshot import Command
from lib.management_base import CommandError


def _cmd():
    return Command()


def _base_options(**overrides):
    opts = {
        'dry_run': False, 'portfolio': None, 'security': None, 'source': None,
        'sod_date': None, 'eod_date': None, 'fill_gaps': False,
    }
    opts.update(overrides)
    return opts


def _eod_row(**overrides):
    row = {
        'portfolio': 'UOB-SG', 'security_label': 'AAPL', 'position_basis': 'SETTLED',
        'position_date': '2026-02-26', 'src_system': 'CIS', 'quantity': 100,
        'isin': None, 'source_table': None,
    }
    row.update(overrides)
    return row


@pytest.fixture
def fake_position_service():
    """Inject a fake trade.services.position_service module so create_sod_snapshot's
    inline `from trade.services.position_service import position_service` import
    (a Django-dependent module we don't want to actually load) resolves to a mock."""
    mock_svc = MagicMock()
    fake_module = types.ModuleType('trade.services.position_service')
    fake_module.position_service = mock_svc
    with patch.dict(sys.modules, {'trade.services.position_service': fake_module}):
        yield mock_svc


class TestAddArguments:
    def test_defaults(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        args = parser.parse_args([])
        assert args.dry_run is False
        assert args.fill_gaps is False
        assert args.source is None

    def test_source_choices_validated(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(['--source', 'BOGUS'])

    def test_all_flags_parse(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        args = parser.parse_args([
            '--dry-run', '--portfolio', 'UOB-SG', '--security', 'AAPL', '--source', 'CIS',
            '--sod-date', '2026-09-17', '--eod-date', '2026-09-16', '--fill-gaps',
        ])
        assert args.dry_run is True
        assert args.portfolio == 'UOB-SG'
        assert args.source == 'CIS'
        assert args.fill_gaps is True


class TestEscape:
    def test_none_returns_empty(self):
        assert Command._escape(None) == ''

    def test_escapes_quote_and_backslash(self):
        assert Command._escape("O'Brien\\x") == "O\\'Brien\\\\x"


class TestToIso:
    def test_converts_yyyymmdd(self):
        assert Command._to_iso('20260917') == '2026-09-17'

    def test_passthrough_when_not_8_chars(self):
        assert Command._to_iso('2026-09-17') == '2026-09-17'


class TestGetBusinessDates:
    def test_returns_dates_from_row(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'contextual_today': '20260917', 'reporting_date': '20260916'},
            ]
            today, reporting = cmd._get_business_dates()
        assert today == '20260917'
        assert reporting == '20260916'

    def test_returns_none_none_when_no_rows(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert cmd._get_business_dates() == (None, None)

    def test_returns_none_none_on_exception(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert cmd._get_business_dates() == (None, None)


class TestGetEodRows:
    def test_returns_results(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [_eod_row()]
            result = cmd._get_eod_rows('2026-02-26', ['CIS'], None)
        assert len(result) == 1

    def test_returns_empty_list_when_none(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert cmd._get_eod_rows('2026-02-26', ['CIS'], None) == []

    def test_portfolio_filter_applied(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._get_eod_rows('2026-02-26', ['CIS'], 'UOB-SG')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "portfolio = 'UOB-SG'" in query

    def test_security_filter_applied(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._get_eod_rows('2026-02-26', ['CIS'], None, security_filter='AAPL')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "security_label = 'AAPL'" in query

    def test_fill_gaps_adds_left_join_and_where(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._get_eod_rows('2026-02-26', ['CIS'], None, fill_gaps=True, sod_date='2026-09-17')
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LEFT JOIN' in query
        assert 'existing_sod.portfolio IS NULL' in query

    def test_no_fill_gaps_omits_join(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._get_eod_rows('2026-02-26', ['CIS'], None, fill_gaps=False)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LEFT JOIN' not in query

    def test_reraises_on_exception(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            with pytest.raises(RuntimeError):
                cmd._get_eod_rows('2026-02-26', ['CIS'], None)


class TestGetPendingSettlements:
    def test_returns_results(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'queue_id': 1}]
            assert len(cmd._get_pending_settlements('2026-09-17')) == 1

    def test_returns_empty_list_when_none(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert cmd._get_pending_settlements('2026-09-17') == []

    def test_returns_empty_list_on_exception(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert cmd._get_pending_settlements('2026-09-17') == []

    def test_query_filters_by_settle_date_and_pending_status(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._get_pending_settlements('2026-09-17')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "settle_date = '2026-09-17'" in query
        assert "status      = 'PENDING'" in query


class TestDeleteExistingSod:
    def test_calls_execute_write_with_delete(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            cmd._delete_existing_sod('2026-09-17', ['CIS'], None)
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'DELETE FROM' in sql
        assert "position_date  = '2026-09-17'" in sql

    def test_portfolio_and_security_filters_applied(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            cmd._delete_existing_sod('2026-09-17', ['CIS'], 'UOB-SG', security_filter='AAPL')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "portfolio = 'UOB-SG'" in sql
        assert "security_label = 'AAPL'" in sql

    def test_reraises_on_exception(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            with pytest.raises(RuntimeError):
                cmd._delete_existing_sod('2026-09-17', ['CIS'], None)


class TestMarkSettlementsCompleted:
    def test_noop_for_empty_list(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            cmd._mark_settlements_completed([])
        mock_mgr.execute_write.assert_not_called()

    def test_updates_status_to_completed(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            cmd._mark_settlements_completed([1, 2, 3])
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'COMPLETED'" in sql
        assert '1, 2, 3' in sql

    def test_swallows_exception(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            cmd._mark_settlements_completed([1])  # must not raise


class TestMarkSettlementsFailed:
    def test_noop_for_empty_list(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            cmd._mark_settlements_failed([])
        mock_mgr.execute_write.assert_not_called()

    def test_updates_status_to_failed(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            cmd._mark_settlements_failed([1])
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'FAILED'" in sql

    def test_swallows_exception(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            cmd._mark_settlements_failed([1])  # must not raise


class TestBatchInsertSod:
    def test_normal_rows_batched_in_one_write(self):
        cmd = _cmd()
        rows = [_eod_row(), _eod_row(security_label='MSFT')]
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            total = cmd._batch_insert_sod(rows, '2026-09-17', '20260917')
        assert total == 2
        assert mock_mgr.execute_write.call_count == 1

    def test_special_char_rows_inserted_individually(self):
        cmd = _cmd()
        rows = [_eod_row(security_label="O'BRIEN CO")]
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            cmd._batch_insert_sod(rows, '2026-09-17', '20260917')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "O\\'BRIEN CO" in sql

    def test_upload_source_uses_fnv_hash_expression(self):
        cmd = _cmd()
        rows = [_eod_row(src_system='USER_UPLOAD')]
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            cmd._batch_insert_sod(rows, '2026-09-17', '20260917')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'fnv_hash' in sql

    def test_non_upload_source_uses_timestamp_id(self):
        cmd = _cmd()
        rows = [_eod_row(src_system='CIS')]
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            cmd._batch_insert_sod(rows, '2026-09-17', '20260917')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'fnv_hash' not in sql

    def test_empty_rows_returns_zero(self):
        cmd = _cmd()
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            total = cmd._batch_insert_sod([], '2026-09-17', '20260917')
        assert total == 0
        mock_mgr.execute_write.assert_not_called()

    def test_is_latest_true_and_position_type_sod(self):
        cmd = _cmd()
        rows = [_eod_row()]
        with patch('create_sod_snapshot.impala_manager') as mock_mgr:
            cmd._batch_insert_sod(rows, '2026-09-17', '20260917')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'SOD'" in sql
        assert 'true' in sql


class TestHandleNoEodRows:
    def test_prints_warning_and_returns(self, capsys):
        cmd = _cmd()
        with patch.object(cmd, '_get_business_dates', return_value=('20260917', '20260916')), \
             patch.object(cmd, '_get_eod_rows', return_value=[]):
            cmd.handle(**_base_options())
        out = capsys.readouterr().out
        assert 'nothing to snapshot' in out


class TestHandleMissingDates:
    def test_raises_command_error_without_override(self):
        cmd = _cmd()
        with patch.object(cmd, '_get_business_dates', return_value=(None, None)):
            with pytest.raises(CommandError, match='Could not read business dates'):
                cmd.handle(**_base_options())

    def test_manual_override_avoids_error(self, capsys):
        cmd = _cmd()
        with patch.object(cmd, '_get_business_dates', return_value=(None, None)), \
             patch.object(cmd, '_get_eod_rows', return_value=[]):
            cmd.handle(**_base_options(sod_date='2026-09-17', eod_date='2026-09-16'))
        out = capsys.readouterr().out
        assert 'manual override' in out


class TestHandleDryRun:
    def test_dry_run_shows_preview_and_returns_without_writing(self, capsys):
        cmd = _cmd()
        with patch.object(cmd, '_get_business_dates', return_value=('20260917', '20260916')), \
             patch.object(cmd, '_get_eod_rows', return_value=[_eod_row()]), \
             patch.object(cmd, '_get_pending_settlements', return_value=[]), \
             patch.object(cmd, '_batch_insert_sod') as mock_insert:
            cmd.handle(**_base_options(dry_run=True))
        mock_insert.assert_not_called()
        assert 'DRY RUN' in capsys.readouterr().out


class TestHandleFullRun:
    def test_no_pending_settlements_batch_inserts_all_eod_rows(self, capsys):
        cmd = _cmd()
        with patch.object(cmd, '_get_business_dates', return_value=('20260917', '20260916')), \
             patch.object(cmd, '_get_eod_rows', return_value=[_eod_row()]), \
             patch.object(cmd, '_get_pending_settlements', return_value=[]), \
             patch.object(cmd, '_delete_existing_sod'), \
             patch.object(cmd, '_batch_insert_sod', return_value=1) as mock_insert:
            cmd.handle(**_base_options())
        mock_insert.assert_called_once()
        assert 'SOD snapshot complete' in capsys.readouterr().out

    def test_fill_gaps_skips_delete_existing_sod(self):
        cmd = _cmd()
        with patch.object(cmd, '_get_business_dates', return_value=('20260917', '20260916')), \
             patch.object(cmd, '_get_eod_rows', return_value=[_eod_row()]), \
             patch.object(cmd, '_get_pending_settlements', return_value=[]), \
             patch.object(cmd, '_delete_existing_sod') as mock_delete, \
             patch.object(cmd, '_batch_insert_sod', return_value=1):
            cmd.handle(**_base_options(fill_gaps=True))
        mock_delete.assert_not_called()

    def test_successful_settlement_application_marks_completed(self, fake_position_service, capsys):
        cmd = _cmd()
        settlement = {
            'queue_id': 1, 'trade_id': 100, 'portfolio_id': 'UOB-SG', 'security_id': 'AAPL',
            'trade_type': 'BUY', 'quantity': 10, 'price': 100, 'charges': 0,
            'position_basis': 'SETTLED',
        }
        fake_position_service.calculate_position.return_value = (True, 'ok', None)
        with patch.object(cmd, '_get_business_dates', return_value=('20260917', '20260916')), \
             patch.object(cmd, '_get_eod_rows', return_value=[_eod_row()]), \
             patch.object(cmd, '_get_pending_settlements', return_value=[settlement]), \
             patch.object(cmd, '_delete_existing_sod'), \
             patch.object(cmd, '_batch_insert_sod', return_value=0), \
             patch.object(cmd, '_mark_settlements_completed') as mock_mark:
            cmd.handle(**_base_options())
        mock_mark.assert_called_once_with([1])
        assert 'Applied BUY' in capsys.readouterr().out

    def test_failed_settlement_application_marks_failed(self, fake_position_service):
        cmd = _cmd()
        settlement = {
            'queue_id': 2, 'trade_id': 200, 'portfolio_id': 'UOB-SG', 'security_id': 'AAPL',
            'trade_type': 'BUY', 'quantity': 10, 'price': 100, 'charges': 0,
            'position_basis': 'SETTLED',
        }
        fake_position_service.calculate_position.return_value = (False, 'failed reason', None)
        with patch.object(cmd, '_get_business_dates', return_value=('20260917', '20260916')), \
             patch.object(cmd, '_get_eod_rows', return_value=[_eod_row()]), \
             patch.object(cmd, '_get_pending_settlements', return_value=[settlement]), \
             patch.object(cmd, '_delete_existing_sod'), \
             patch.object(cmd, '_batch_insert_sod', return_value=1), \
             patch.object(cmd, '_mark_settlements_failed') as mock_mark_failed:
            cmd.handle(**_base_options())
        mock_mark_failed.assert_called_once_with([2])

    def test_settlement_exception_marks_failed(self, fake_position_service):
        cmd = _cmd()
        settlement = {
            'queue_id': 3, 'trade_id': 300, 'portfolio_id': 'UOB-SG', 'security_id': 'AAPL',
            'trade_type': 'BUY', 'quantity': 10, 'price': 100, 'charges': 0,
            'position_basis': 'SETTLED',
        }
        fake_position_service.calculate_position.side_effect = RuntimeError('boom')
        with patch.object(cmd, '_get_business_dates', return_value=('20260917', '20260916')), \
             patch.object(cmd, '_get_eod_rows', return_value=[_eod_row()]), \
             patch.object(cmd, '_get_pending_settlements', return_value=[settlement]), \
             patch.object(cmd, '_delete_existing_sod'), \
             patch.object(cmd, '_batch_insert_sod', return_value=1), \
             patch.object(cmd, '_mark_settlements_failed') as mock_mark_failed:
            cmd.handle(**_base_options())
        mock_mark_failed.assert_called_once_with([3])

    def test_applied_settlement_key_excluded_from_plain_eod_copy(self, fake_position_service):
        cmd = _cmd()
        eod_row = _eod_row(portfolio='UOB-SG', security_label='AAPL', position_basis='SETTLED')
        settlement = {
            'queue_id': 4, 'trade_id': 400, 'portfolio_id': 'UOB-SG', 'security_id': 'AAPL',
            'trade_type': 'BUY', 'quantity': 10, 'price': 100, 'charges': 0,
            'position_basis': 'SETTLED',
        }
        fake_position_service.calculate_position.return_value = (True, 'ok', None)
        with patch.object(cmd, '_get_business_dates', return_value=('20260917', '20260916')), \
             patch.object(cmd, '_get_eod_rows', return_value=[eod_row]), \
             patch.object(cmd, '_get_pending_settlements', return_value=[settlement]), \
             patch.object(cmd, '_delete_existing_sod'), \
             patch.object(cmd, '_batch_insert_sod', return_value=0) as mock_insert:
            cmd.handle(**_base_options())
        # the EOD row matching the applied settlement's key was excluded from batch insert
        sod_rows_arg = mock_insert.call_args[0][0]
        assert sod_rows_arg == []

    def test_portfolio_and_source_filters_forwarded_to_get_eod_rows(self):
        cmd = _cmd()
        with patch.object(cmd, '_get_business_dates', return_value=('20260917', '20260916')), \
             patch.object(cmd, '_get_eod_rows', return_value=[]) as mock_get_eod, \
             patch.object(cmd, '_get_pending_settlements', return_value=[]):
            cmd.handle(**_base_options(portfolio='UOB-SG', source='CIS'))
        args, kwargs = mock_get_eod.call_args
        assert args[1] == ['CIS']
        assert args[2] == 'UOB-SG'
