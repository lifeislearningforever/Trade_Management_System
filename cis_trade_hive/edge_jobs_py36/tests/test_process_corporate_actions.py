"""Tests for edge_jobs_py36/process_corporate_actions.py."""
import argparse
import sys
import types
from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from process_corporate_actions import Command
from lib.management_base import CommandError


def _cmd():
    return Command()


def _base_options(**overrides):
    opts = {
        'run_type': 'EOD', 'date': None, 'dry_run': False, 'verbose': False,
        'ca_id': None, 'queue_id': None, 'user': 'SYSTEM', 'batch_size': 100,
        'retry_failed': False, 'reset_stuck': False, 'status': False, 'correction': False,
    }
    opts.update(overrides)
    return opts


@pytest.fixture
def fake_ca_repo():
    """Inject a fake reference_data.repositories.corporate_action_repository module
    (Django-dependent, imported inline inside a couple of methods)."""
    mock_repo_cls = MagicMock()
    fake_module = types.ModuleType('reference_data.repositories.corporate_action_repository')
    fake_module.CorporateActionRepository = mock_repo_cls
    with patch.dict(sys.modules, {'reference_data.repositories.corporate_action_repository': fake_module}):
        yield mock_repo_cls


@pytest.fixture
def fake_core_impala():
    """Inject a fake core.repositories.impala_connection module (Django-dependent,
    imported inline by _reset_stuck_entries/_retry_failed_entries/_correction_run)."""
    mock_mgr = MagicMock()
    fake_module = types.ModuleType('core.repositories.impala_connection')
    fake_module.impala_manager = mock_mgr
    with patch.dict(sys.modules, {'core.repositories.impala_connection': fake_module}):
        yield mock_mgr


class TestAddArguments:
    def test_defaults(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        args = parser.parse_args([])
        assert args.run_type == 'EOD'
        assert args.dry_run is False
        assert args.user == 'SYSTEM'
        assert args.batch_size == 100

    def test_run_type_choices_validated(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(['--run-type', 'BOGUS'])

    def test_all_flags_parse(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        args = parser.parse_args([
            '--run-type', 'CORR', '--date', '2026-09-17', '--dry-run', '--verbose-output',
            '--ca-id', '123', '--queue-id', '456', '--user', 'jdoe', '--batch-size', '50',
            '--retry-failed', '--reset-stuck', '--status', '--correction',
        ])
        assert args.run_type == 'CORR'
        assert args.ca_id == 123
        assert args.verbose is True
        assert args.correction is True


class TestGetLastMonthEndFromAlldatesinfo:
    def test_different_months_uses_reporting_date(self):
        cmd = _cmd()
        with patch('process_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'contextual_today': '20260301', 'reporting_date': '20260228'},
            ]
            result = cmd._get_last_month_end_from_alldatesinfo()
        assert result == '2026-02-28'

    def test_same_month_uses_prior_month_end(self):
        cmd = _cmd()
        with patch('process_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'contextual_today': '20260315', 'reporting_date': '20260310'},
            ]
            result = cmd._get_last_month_end_from_alldatesinfo()
        assert result == '2026-02-28'

    def test_falls_back_on_exception(self):
        cmd = _cmd()
        with patch('process_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = cmd._get_last_month_end_from_alldatesinfo()
        assert result  # non-empty fallback date string

    def test_falls_back_when_no_rows(self):
        cmd = _cmd()
        with patch('process_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = cmd._get_last_month_end_from_alldatesinfo()
        assert result


class TestAutoCreateQueueEntry:
    def test_ca_not_found_returns_empty(self, fake_ca_repo, capsys):
        fake_ca_repo.get_by_id.return_value = None
        result = _cmd()._auto_create_queue_entry(1, dry_run=False)
        assert result == []
        assert 'not found' in capsys.readouterr().out

    def test_invalid_status_returns_empty(self, fake_ca_repo, capsys):
        fake_ca_repo.get_by_id.return_value = {'status': 'INITIAL'}
        result = _cmd()._auto_create_queue_entry(1, dry_run=False)
        assert result == []
        assert 'only VALIDATED/APPROVED' in capsys.readouterr().out

    def test_dry_run_returns_empty_without_inserting(self, fake_ca_repo):
        fake_ca_repo.get_by_id.return_value = {
            'status': 'VALIDATED', 'ca_number': 'GMP-1', 'ca_type': 'cash_dividend',
        }
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_queue_repo:
            result = _cmd()._auto_create_queue_entry(1, dry_run=True)
        assert result == []
        mock_queue_repo.insert.assert_not_called()

    def test_successful_insert_returns_entry(self, fake_ca_repo):
        fake_ca_repo.get_by_id.return_value = {
            'status': 'VALIDATED', 'ca_number': 'GMP-1', 'ca_type': 'cash_dividend',
        }
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_queue_repo:
            mock_queue_repo.insert.return_value = (True, 999)
            mock_queue_repo.get_by_id.return_value = {'queue_id': 999}
            result = _cmd()._auto_create_queue_entry(1, dry_run=False)
        assert result == [{'queue_id': 999}]

    def test_insert_failure_returns_empty(self, fake_ca_repo, capsys):
        fake_ca_repo.get_by_id.return_value = {
            'status': 'VALIDATED', 'ca_number': 'GMP-1', 'ca_type': 'cash_dividend',
        }
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_queue_repo:
            mock_queue_repo.insert.return_value = (False, None)
            result = _cmd()._auto_create_queue_entry(1, dry_run=False)
        assert result == []
        assert 'Failed to create queue entry' in capsys.readouterr().out


class TestShowStatistics:
    def test_no_stats_shows_warning(self, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo:
            mock_repo.get_statistics.return_value = {}
            cmd._show_statistics()
        assert 'No statistics available' in capsys.readouterr().out

    def test_shows_counts(self, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo:
            mock_repo.get_statistics.return_value = {
                'pending': 3, 'processing': 0, 'completed': 5, 'failed': 0,
                'total_cash_flows': 10, 'total_amount': Decimal('100'),
            }
            cmd._show_statistics()
        out = capsys.readouterr().out
        assert 'Pending:    3' in out

    def test_shows_reset_stuck_hint_when_processing(self, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo:
            mock_repo.get_statistics.return_value = {'pending': 0, 'processing': 2, 'completed': 0, 'failed': 0}
            cmd._show_statistics()
        assert 'reset-stuck' in capsys.readouterr().out

    def test_shows_retry_failed_hint_when_failed(self, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo:
            mock_repo.get_statistics.return_value = {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 2}
            cmd._show_statistics()
        assert 'retry-failed' in capsys.readouterr().out


class TestProcessPending:
    def test_no_pending_shows_warning(self, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo:
            mock_repo.get_pending.return_value = []
            cmd._process_pending(None, 100, False, False)
        assert 'No pending corporate actions found' in capsys.readouterr().out

    def test_processes_all_entries(self, capsys):
        cmd = _cmd()
        entry = {'queue_id': 1, 'ca_number': 'GMP-1', 'ca_type': 'CASH_DIVIDEND', 'security_name': 'AAPL'}
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo, \
             patch('process_corporate_actions.ca_cash_flow_service') as mock_svc:
            mock_repo.get_pending.return_value = [entry]
            mock_svc.process_ca_cash_flows.return_value = (True, 'ok', 1, Decimal('10'))
            cmd._process_pending(None, 100, False, False)
        out = capsys.readouterr().out
        assert 'Successful: 1' in out

    def test_failed_entry_counted(self, capsys):
        cmd = _cmd()
        entry = {'queue_id': 1, 'ca_number': 'GMP-1', 'ca_type': 'CASH_DIVIDEND', 'security_name': 'AAPL'}
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo, \
             patch('process_corporate_actions.ca_cash_flow_service') as mock_svc:
            mock_repo.get_pending.return_value = [entry]
            mock_svc.process_ca_cash_flows.return_value = (False, 'boom', 0, Decimal('0'))
            cmd._process_pending(None, 100, False, False)
        out = capsys.readouterr().out
        assert 'Failed: 1' in out

    def test_date_maps_to_ex_date_filter(self):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo:
            mock_repo.get_pending.return_value = []
            cmd._process_pending('2026-09-17', 100, False, False)
        kwargs = mock_repo.get_pending.call_args[1]
        assert kwargs.get('ex_date') == '2026-09-17'


class TestProcessCorr:
    def test_no_pending_shows_success_message(self, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo:
            mock_repo.get_pending_for_corr.return_value = []
            cmd._process_corr('2026-08-31', 100, False, False)
        assert 'No unprocessed CAs found' in capsys.readouterr().out

    def test_processes_entries_and_shows_summary(self, capsys):
        cmd = _cmd()
        entry = {'queue_id': 1, 'ca_number': 'GMP-1', 'ca_type': 'CASH_DIVIDEND', 'security_name': 'AAPL', 'ex_date': '2026-08-01', 'status': 'PENDING'}
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo, \
             patch('process_corporate_actions.ca_cash_flow_service') as mock_svc:
            mock_repo.get_pending_for_corr.return_value = [entry]
            mock_svc.process_ca_cash_flows.return_value = (True, 'ok', 2, Decimal('20'))
            cmd._process_corr('2026-08-31', 100, False, False)
        out = capsys.readouterr().out
        assert 'Successful              : 1' in out
        assert 'Cash Flows Created      : 2' in out


class TestProcessSingleQueueEntry:
    def test_not_found_shows_error(self, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo:
            mock_repo.get_by_id.return_value = None
            cmd._process_single_queue_entry(1, False, False)
        assert 'not found' in capsys.readouterr().out

    def test_successful_processing(self, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo, \
             patch('process_corporate_actions.ca_cash_flow_service') as mock_svc:
            mock_repo.get_by_id.return_value = {'queue_id': 1}
            mock_svc.process_ca_cash_flows.return_value = (True, 'ok', 1, Decimal('10'))
            cmd._process_single_queue_entry(1, False, False)
        assert '✓ ok' in capsys.readouterr().out


class TestProcessByCaId:
    def test_auto_creates_when_no_entries(self, fake_ca_repo, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo, \
             patch.object(cmd, '_auto_create_queue_entry', return_value=[]) as mock_auto:
            mock_repo.get_by_ca_id.return_value = []
            cmd._process_by_ca_id(1, False, False)
        mock_auto.assert_called_once()

    def test_skips_completed_entries(self, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo:
            mock_repo.get_by_ca_id.return_value = [{'queue_id': 1, 'status': 'COMPLETED'}]
            cmd._process_by_ca_id(1, False, False)
        assert 'Already completed' in capsys.readouterr().out

    def test_skips_processing_entries(self, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo:
            mock_repo.get_by_ca_id.return_value = [{'queue_id': 1, 'status': 'PROCESSING'}]
            cmd._process_by_ca_id(1, False, False)
        assert 'Currently processing' in capsys.readouterr().out

    def test_processes_pending_entry(self, capsys):
        cmd = _cmd()
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo, \
             patch('process_corporate_actions.ca_cash_flow_service') as mock_svc:
            mock_repo.get_by_ca_id.return_value = [{'queue_id': 1, 'status': 'PENDING'}]
            mock_svc.process_ca_cash_flows.return_value = (True, 'ok', 1, Decimal('10'))
            cmd._process_by_ca_id(1, False, False)
        assert '✓ ok' in capsys.readouterr().out


class TestResetStuckEntries:
    def test_no_stuck_entries(self, fake_core_impala, capsys):
        fake_core_impala.execute_query.return_value = []
        _cmd()._reset_stuck_entries(False)
        assert 'No stuck PROCESSING entries found' in capsys.readouterr().out

    def test_resets_stuck_entries(self, fake_core_impala, capsys):
        fake_core_impala.execute_query.return_value = [{'queue_id': 1, 'ca_number': 'GMP-1'}]
        fake_core_impala.execute_write.return_value = True
        _cmd()._reset_stuck_entries(False)
        out = capsys.readouterr().out
        assert 'Reset 1 of 1' in out

    def test_reset_failure_reported(self, fake_core_impala, capsys):
        fake_core_impala.execute_query.return_value = [{'queue_id': 1, 'ca_number': 'GMP-1'}]
        fake_core_impala.execute_write.return_value = False
        _cmd()._reset_stuck_entries(False)
        out = capsys.readouterr().out
        assert 'Reset 0 of 1' in out

    def test_exception_caught_and_shown(self, fake_core_impala, capsys):
        fake_core_impala.execute_query.side_effect = RuntimeError('boom')
        _cmd()._reset_stuck_entries(False)
        assert 'Error resetting stuck entries' in capsys.readouterr().out


class TestRetryFailedEntries:
    def test_no_failed_entries(self, fake_core_impala, capsys):
        fake_core_impala.execute_query.return_value = []
        _cmd()._retry_failed_entries(False)
        assert 'No failed entries to retry' in capsys.readouterr().out

    def test_retries_and_reprocesses(self, fake_core_impala, capsys):
        fake_core_impala.execute_query.return_value = [
            {'queue_id': 1, 'ca_number': 'GMP-1', 'retry_count': 1},
        ]
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_repo, \
             patch('process_corporate_actions.ca_cash_flow_service') as mock_svc:
            mock_svc.process_ca_cash_flows.return_value = (True, 'ok', 1, Decimal('10'))
            _cmd()._retry_failed_entries(False)
        mock_repo.reset_for_retry.assert_called_once_with(1)

    def test_exception_caught_and_shown(self, fake_core_impala, capsys):
        fake_core_impala.execute_query.side_effect = RuntimeError('boom')
        _cmd()._retry_failed_entries(False)
        assert 'Error retrying failed entries' in capsys.readouterr().out


class TestShowPendingEntriesAndDetails:
    def test_show_pending_entries_prints_table(self, capsys):
        cmd = _cmd()
        entries = [{'queue_id': 1, 'ca_number': 'GMP-1', 'ca_type': 'CASH_DIVIDEND',
                    'security_name': 'AAPL', 'payment_date': '2026-09-20', 'price': '0.25'}]
        cmd._show_pending_entries(entries)
        assert 'GMP-1' in capsys.readouterr().out

    def test_show_entry_details_prints_fields(self, capsys):
        cmd = _cmd()
        entry = {'queue_id': 1, 'ca_id': 2, 'ca_number': 'GMP-1', 'status': 'PENDING'}
        cmd._show_entry_details(entry)
        assert 'GMP-1' in capsys.readouterr().out

    def test_show_entry_details_includes_error_when_present(self, capsys):
        cmd = _cmd()
        entry = {'queue_id': 1, 'error_message': 'boom'}
        cmd._show_entry_details(entry)
        assert 'boom' in capsys.readouterr().out


class TestHandleDispatch:
    def test_status_flag_shows_stats_and_returns(self, capsys):
        cmd = _cmd()
        with patch.object(cmd, '_show_statistics') as mock_show:
            cmd.handle(**_base_options(status=True))
        mock_show.assert_called_once()

    def test_reset_stuck_flag_dispatches(self):
        cmd = _cmd()
        with patch.object(cmd, '_reset_stuck_entries') as mock_reset:
            cmd.handle(**_base_options(reset_stuck=True))
        mock_reset.assert_called_once()

    def test_retry_failed_flag_dispatches(self):
        cmd = _cmd()
        with patch.object(cmd, '_retry_failed_entries') as mock_retry:
            cmd.handle(**_base_options(retry_failed=True))
        mock_retry.assert_called_once()

    def test_queue_id_dispatches_to_single_entry(self):
        cmd = _cmd()
        with patch.object(cmd, '_process_single_queue_entry') as mock_single:
            cmd.handle(**_base_options(queue_id=99))
        mock_single.assert_called_once()

    def test_correction_without_ca_id_raises(self):
        cmd = _cmd()
        with pytest.raises(CommandError, match='requires --ca-id'):
            cmd.handle(**_base_options(correction=True))

    def test_correction_with_ca_id_dispatches(self):
        cmd = _cmd()
        with patch.object(cmd, '_correction_run') as mock_corr:
            cmd.handle(**_base_options(correction=True, ca_id=1))
        mock_corr.assert_called_once()

    def test_ca_id_dispatches_to_process_by_ca_id(self):
        cmd = _cmd()
        with patch.object(cmd, '_process_by_ca_id') as mock_by_ca:
            cmd.handle(**_base_options(ca_id=1))
        mock_by_ca.assert_called_once()

    def test_corr_run_type_dispatches_to_process_corr(self):
        cmd = _cmd()
        with patch.object(cmd, '_get_last_month_end_from_alldatesinfo', return_value='2026-08-31'), \
             patch.object(cmd, '_process_corr') as mock_corr:
            cmd.handle(**_base_options(run_type='CORR'))
        mock_corr.assert_called_once()

    def test_default_dispatches_to_process_pending(self):
        cmd = _cmd()
        with patch.object(cmd, '_process_pending') as mock_pending:
            cmd.handle(**_base_options())
        mock_pending.assert_called_once()

    def test_unhandled_exception_raises_command_error(self):
        cmd = _cmd()
        with patch.object(cmd, '_process_pending', side_effect=RuntimeError('boom')):
            with pytest.raises(CommandError):
                cmd.handle(**_base_options())


class TestCorrectionRun:
    def test_ca_not_found_raises(self, fake_ca_repo, fake_core_impala):
        fake_ca_repo.get_by_id.return_value = None
        with pytest.raises(CommandError, match='not found'):
            _cmd()._correction_run(1, 'jdoe', False, False)

    def test_invalid_status_raises(self, fake_ca_repo, fake_core_impala):
        fake_ca_repo.get_by_id.return_value = {'status': 'INITIAL', 'ca_number': 'GMP-1'}
        with pytest.raises(CommandError, match='Correction requires'):
            _cmd()._correction_run(1, 'jdoe', False, False)

    def test_dry_run_with_no_existing_entries_shows_preview(self, fake_ca_repo, fake_core_impala, capsys):
        fake_ca_repo.get_by_id.return_value = {'status': 'VALIDATED', 'ca_number': 'GMP-1'}
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_queue_repo:
            mock_queue_repo.get_by_ca_id.return_value = []
            _cmd()._correction_run(1, 'jdoe', True, False)
        out = capsys.readouterr().out
        assert 'DRY RUN' in out

    def test_auto_creates_when_no_entries_and_not_dry_run(self, fake_ca_repo, fake_core_impala):
        fake_ca_repo.get_by_id.return_value = {'status': 'VALIDATED', 'ca_number': 'GMP-1'}
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_queue_repo, \
             patch.object(Command, '_auto_create_queue_entry', return_value=[]) as mock_auto:
            mock_queue_repo.get_by_ca_id.return_value = []
            with pytest.raises(CommandError, match='Could not create queue entry'):
                _cmd()._correction_run(1, 'jdoe', False, False)

    def test_voids_existing_cash_flows(self, fake_ca_repo, fake_core_impala):
        fake_ca_repo.get_by_id.return_value = {
            'status': 'VALIDATED', 'ca_number': 'GMP-1', 'ex_date': None,
            'record_date': None, 'payment_date': None, 'price': None,
        }
        fake_core_impala.execute_query.return_value = [{'cash_flow_id': 100}]
        fake_core_impala.execute_write.return_value = True
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_queue_repo, \
             patch('process_corporate_actions.ca_cash_flow_service') as mock_svc:
            mock_queue_repo.get_by_ca_id.return_value = [{'queue_id': 1, 'status': 'PENDING', 'cash_flows_created': 0}]
            mock_svc.process_ca_cash_flows.return_value = (True, 'ok', 1, Decimal('10'))
            _cmd()._correction_run(1, 'jdoe', False, False)
        # void write call happened
        assert fake_core_impala.execute_write.call_count >= 1

    def test_processing_status_entry_is_skipped(self, fake_ca_repo, fake_core_impala, capsys):
        fake_ca_repo.get_by_id.return_value = {
            'status': 'VALIDATED', 'ca_number': 'GMP-1', 'ex_date': None,
            'record_date': None, 'payment_date': None, 'price': None,
        }
        fake_core_impala.execute_query.return_value = []
        with patch('process_corporate_actions.ca_cash_flow_queue_repository') as mock_queue_repo:
            mock_queue_repo.get_by_ca_id.return_value = [{'queue_id': 1, 'status': 'PROCESSING', 'cash_flows_created': 0}]
            _cmd()._correction_run(1, 'jdoe', False, False)
        assert 'use --reset-stuck first' in capsys.readouterr().out
