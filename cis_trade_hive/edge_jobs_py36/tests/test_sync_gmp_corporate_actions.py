"""Tests for edge_jobs_py36/sync_gmp_corporate_actions.py."""
import argparse
import os
from decimal import Decimal
from unittest.mock import patch

import pytest

from sync_gmp_corporate_actions import (
    Command,
    map_gmp_ca_type,
    parse_gmp_date,
    parse_gmp_price,
    _apply_early_env_override,
    GMP_CA_TYPE_MAP,
)


def _row(**overrides):
    row = {
        'ca_id': '12345',
        'security': 'AAPL US',
        'ca_type': 'Cash dividend',
        'announcement_date': '2026-09-01',
        'ex_date': '2026-09-10',
        'record_date': '2026-09-11',
        'payment_date': '2026-09-20',
        'price': '0.25',
        'status': 'VALIDATED',
        'processing_date': '20260917',
    }
    row.update(overrides)
    return row


class TestMapGmpCaType:
    def test_none_returns_none(self):
        assert map_gmp_ca_type(None) is None

    def test_empty_returns_none(self):
        assert map_gmp_ca_type('') is None

    def test_known_type_case_insensitive(self):
        assert map_gmp_ca_type('Cash Dividend') == 'CASH_DIVIDEND'
        assert map_gmp_ca_type('cash dividend') == 'CASH_DIVIDEND'

    def test_whitespace_stripped(self):
        assert map_gmp_ca_type('  bonus  ') == 'BONUS_ISSUE'

    def test_gmp_specific_code(self):
        assert map_gmp_ca_type('CLAS SP') == 'SPECIAL_DIVIDEND'

    def test_single_letter_code(self):
        assert map_gmp_ca_type('D') == 'CASH_DIVIDEND'

    def test_unmapped_type_returns_none(self):
        assert map_gmp_ca_type('some totally unknown type') is None

    def test_every_map_value_reachable(self):
        # sanity: every mapping entry actually round-trips through the function
        for gmp_key, cis_val in GMP_CA_TYPE_MAP.items():
            assert map_gmp_ca_type(gmp_key) == cis_val


class TestParseGmpDate:
    def test_none_returns_none(self):
        assert parse_gmp_date(None) is None

    def test_empty_returns_none(self):
        assert parse_gmp_date('') is None

    def test_zero_returns_none(self):
        assert parse_gmp_date('0') is None

    def test_null_literal_returns_none(self):
        assert parse_gmp_date('null') is None
        assert parse_gmp_date('NULL') is None

    def test_dmy_slash_format(self):
        assert parse_gmp_date('17/09/2026') == '2026-09-17'

    def test_iso_format(self):
        assert parse_gmp_date('2026-09-17') == '2026-09-17'

    def test_yyyymmdd_format(self):
        assert parse_gmp_date('20260917') == '2026-09-17'

    def test_dmy_dash_format(self):
        assert parse_gmp_date('17-09-2026') == '2026-09-17'

    def test_mdy_slash_format(self):
        assert parse_gmp_date('09/17/2026') == '2026-09-17'

    def test_unparseable_logs_warning_and_returns_none(self, caplog):
        result = parse_gmp_date('not-a-date')
        assert result is None


class TestParseGmpPrice:
    def test_none_returns_none(self):
        assert parse_gmp_price(None) is None

    def test_empty_returns_none(self):
        assert parse_gmp_price('') is None

    def test_valid_decimal(self):
        assert parse_gmp_price('0.25') == Decimal('0.25')

    def test_invalid_returns_none(self):
        assert parse_gmp_price('garbage') is None


class TestApplyEarlyEnvOverride:
    def test_sets_from_space_form(self):
        with patch.dict(os.environ, {}, clear=False):
            _apply_early_env_override(['prog', '--env', 'UAT'])
            assert os.environ['CIS_ENV'] == 'UAT'

    def test_sets_from_equals_form(self):
        with patch.dict(os.environ, {}, clear=False):
            _apply_early_env_override(['prog', '--env=sit'])
            assert os.environ['CIS_ENV'] == 'SIT'

    def test_noop_when_absent(self):
        with patch.dict(os.environ, {}, clear=True):
            _apply_early_env_override(['prog'])
            assert 'CIS_ENV' not in os.environ


class TestAddArguments:
    def test_defaults(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args([])
        assert args.full_sync is False
        assert args.user == 'SYSTEM'
        assert args.batch_size == 500

    def test_full_sync_flag(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args(['--full-sync'])
        assert args.full_sync is True


class TestFetchGmpRecords:
    def test_returns_results(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [_row()]
            result = cmd._fetch_gmp_records(None, 500)
        assert len(result) == 1

    def test_returns_empty_when_none(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            result = cmd._fetch_gmp_records(None, 500)
        assert result == []

    def test_date_filter_applied_when_given(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records('2026-09-17', 500)
        query = mock_mgr.execute_query.call_args[0][0]
        assert "'20260917'" in query

    def test_no_date_filter_when_absent(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records(None, 500)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'CAST(processing_date AS STRING)' not in query

    def test_batch_size_used_as_limit(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records(None, 250)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 250' in query

    def test_exception_returns_empty_list(self, capsys):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = cmd._fetch_gmp_records(None, 500)
        assert result == []
        assert 'Error fetching GMP records' in capsys.readouterr().err


class TestGetSyncedGmpCaNumbers:
    def test_returns_set_of_ca_numbers(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'ca_number': 'GMP-1'}, {'ca_number': 'GMP-2'}]
            result = cmd._get_synced_gmp_ca_numbers()
        assert result == {'GMP-1', 'GMP-2'}

    def test_returns_empty_set_when_no_results(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert cmd._get_synced_gmp_ca_numbers() == set()

    def test_returns_empty_set_on_exception(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert cmd._get_synced_gmp_ca_numbers() == set()

    def test_filters_out_none_ca_numbers(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'ca_number': None}, {'ca_number': 'GMP-1'}]
            result = cmd._get_synced_gmp_ca_numbers()
        assert result == {'GMP-1'}


class TestProcessRow:
    def test_missing_ca_id_is_invalid(self):
        cmd = Command()
        result = cmd._process_row(_row(ca_id=''), set(), 'SYSTEM', dry_run=False, verbose=False)
        assert result['outcome'] == 'skipped_invalid'
        assert 'missing ca_id' in result['error']

    def test_missing_security_is_invalid(self):
        cmd = Command()
        result = cmd._process_row(_row(security=''), set(), 'SYSTEM', dry_run=False, verbose=False)
        assert result['outcome'] == 'skipped_invalid'
        assert 'missing security' in result['error']

    def test_unmapped_ca_type_is_invalid(self):
        cmd = Command()
        result = cmd._process_row(_row(ca_type='some unknown type'), set(), 'SYSTEM', dry_run=False, verbose=False)
        assert result['outcome'] == 'skipped_invalid'
        assert 'unknown ca_type' in result['error']

    def test_already_synced_ca_number_is_duplicate(self):
        cmd = Command()
        result = cmd._process_row(_row(ca_id='12345'), {'GMP-12345'}, 'SYSTEM', dry_run=False, verbose=False)
        assert result['outcome'] == 'skipped_duplicate'

    def test_dry_run_returns_inserted_and_queued_without_writing(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.corporate_action_repository') as mock_repo:
            result = cmd._process_row(_row(), set(), 'SYSTEM', dry_run=True, verbose=False)
        assert result['outcome'] == 'inserted'
        assert result['queued'] is True
        mock_repo.insert.assert_not_called()

    def test_successful_insert_and_queue(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.corporate_action_repository') as mock_repo, \
             patch('sync_gmp_corporate_actions.ca_cash_flow_service') as mock_ca_svc:
            mock_repo.insert.return_value = (True, 999)
            mock_ca_svc.queue_ca_for_processing.return_value = (True, 1)
            result = cmd._process_row(_row(), set(), 'SYSTEM', dry_run=False, verbose=False)
        assert result['outcome'] == 'inserted'
        assert result['queued'] is True

    def test_insert_failure_is_error(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.corporate_action_repository') as mock_repo:
            mock_repo.insert.return_value = (False, None)
            result = cmd._process_row(_row(), set(), 'SYSTEM', dry_run=False, verbose=False)
        assert result['outcome'] == 'errors'
        assert 'Insert failed' in result['error']

    def test_insert_exception_is_error(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.corporate_action_repository') as mock_repo:
            mock_repo.insert.side_effect = RuntimeError('db down')
            result = cmd._process_row(_row(), set(), 'SYSTEM', dry_run=False, verbose=False)
        assert result['outcome'] == 'errors'
        assert 'DB error inserting' in result['error']

    def test_inserted_ca_number_added_to_synced_set(self):
        cmd = Command()
        synced = set()
        with patch('sync_gmp_corporate_actions.corporate_action_repository') as mock_repo, \
             patch('sync_gmp_corporate_actions.ca_cash_flow_service') as mock_ca_svc:
            mock_repo.insert.return_value = (True, 999)
            mock_ca_svc.queue_ca_for_processing.return_value = (True, 1)
            cmd._process_row(_row(ca_id='777'), synced, 'SYSTEM', dry_run=False, verbose=False)
        assert 'GMP-777' in synced

    def test_queue_failure_still_counts_as_inserted_not_queued(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.corporate_action_repository') as mock_repo, \
             patch('sync_gmp_corporate_actions.ca_cash_flow_service') as mock_ca_svc:
            mock_repo.insert.return_value = (True, 999)
            mock_ca_svc.queue_ca_for_processing.return_value = (False, None)
            result = cmd._process_row(_row(), set(), 'SYSTEM', dry_run=False, verbose=False)
        assert result['outcome'] == 'inserted'
        assert result['queued'] is False

    def test_queue_exception_is_swallowed_and_not_queued(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.corporate_action_repository') as mock_repo, \
             patch('sync_gmp_corporate_actions.ca_cash_flow_service') as mock_ca_svc:
            mock_repo.insert.return_value = (True, 999)
            mock_ca_svc.queue_ca_for_processing.side_effect = RuntimeError('queue down')
            result = cmd._process_row(_row(), set(), 'SYSTEM', dry_run=False, verbose=False)
        assert result['outcome'] == 'inserted'
        assert result['queued'] is False

    def test_verbose_prints_sync_line(self, capsys):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.corporate_action_repository') as mock_repo, \
             patch('sync_gmp_corporate_actions.ca_cash_flow_service') as mock_ca_svc:
            mock_repo.insert.return_value = (True, 999)
            mock_ca_svc.queue_ca_for_processing.return_value = (True, 1)
            cmd._process_row(_row(), set(), 'SYSTEM', dry_run=False, verbose=True)
        assert '[SYNC]' in capsys.readouterr().out

    def test_verbose_prints_skip_for_duplicate(self, capsys):
        cmd = Command()
        cmd._process_row(_row(ca_id='12345'), {'GMP-12345'}, 'SYSTEM', dry_run=False, verbose=True)
        assert '[SKIP]' in capsys.readouterr().out

    def test_verbose_prints_queued_confirmation(self, capsys):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.corporate_action_repository') as mock_repo, \
             patch('sync_gmp_corporate_actions.ca_cash_flow_service') as mock_ca_svc:
            mock_repo.insert.return_value = (True, 999)
            mock_ca_svc.queue_ca_for_processing.return_value = (True, 42)
            cmd._process_row(_row(), set(), 'SYSTEM', dry_run=False, verbose=True)
        assert 'queue_id=42' in capsys.readouterr().out


class TestPrintHeaderAndSummary:
    def test_header_basic(self, capsys):
        cmd = Command()
        cmd._print_header(None, False, 'SYSTEM')
        out = capsys.readouterr().out
        assert 'GMP Corporate Action Sync' in out

    def test_header_dry_run(self, capsys):
        cmd = Command()
        cmd._print_header(None, True, 'SYSTEM')
        assert 'DRY RUN' in capsys.readouterr().out

    def test_summary_shows_next_step_hint_when_inserted_and_not_dry_run(self, capsys):
        cmd = Command()
        cmd._print_summary({'inserted': 1, 'queued': 1, 'skipped_duplicate': 0,
                             'skipped_invalid': 0, 'errors': 0}, [], dry_run=False)
        assert 'process_corporate_actions' in capsys.readouterr().out

    def test_summary_no_hint_when_dry_run(self, capsys):
        cmd = Command()
        cmd._print_summary({'inserted': 1, 'queued': 1, 'skipped_duplicate': 0,
                             'skipped_invalid': 0, 'errors': 0}, [], dry_run=True)
        assert 'process_corporate_actions' not in capsys.readouterr().out

    def test_summary_errors_capped_at_twenty(self, capsys):
        cmd = Command()
        errors = [f'e{i}' for i in range(21)]
        cmd._print_summary({'inserted': 0, 'queued': 0, 'skipped_duplicate': 0,
                             'skipped_invalid': 0, 'errors': 21}, errors, dry_run=False)
        assert '... and 1 more' in capsys.readouterr().out


class TestHandle:
    def test_no_records_prints_warning(self, capsys):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.handle(env=None, database=None, date=None, dry_run=False, full_sync=False,
                       verbose=False, user='SYSTEM', batch_size=500)
        assert 'No GMP corporate action records found' in capsys.readouterr().out

    def test_full_sync_skips_synced_lookup(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr, \
             patch.object(cmd, '_get_synced_gmp_ca_numbers') as mock_synced:
            mock_mgr.execute_query.return_value = []
            cmd.handle(env=None, database=None, date=None, dry_run=False, full_sync=True,
                       verbose=False, user='SYSTEM', batch_size=500)
        mock_synced.assert_not_called()

    def test_processes_all_rows_and_shows_summary(self, capsys):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr, \
             patch('sync_gmp_corporate_actions.corporate_action_repository') as mock_repo, \
             patch('sync_gmp_corporate_actions.ca_cash_flow_service') as mock_ca_svc:
            mock_mgr.execute_query.return_value = [_row(ca_id='1'), _row(ca_id='2')]
            mock_repo.insert.return_value = (True, 999)
            mock_ca_svc.queue_ca_for_processing.return_value = (True, 1)
            cmd.handle(env=None, database=None, date=None, dry_run=False, full_sync=True,
                       verbose=False, user='SYSTEM', batch_size=500)
        out = capsys.readouterr().out
        assert 'Inserted into cis_corporate_actions : 2' in out

    def test_database_override_updates_all_repositories(self):
        cmd = Command()
        with patch('sync_gmp_corporate_actions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.handle(env=None, database='custom_db', date=None, dry_run=False, full_sync=True,
                       verbose=False, user='SYSTEM', batch_size=500)
        from sync_gmp_corporate_actions import (
            CorporateActionRepository, CACashFlowService, CACashFlowQueueRepository,
        )
        assert CorporateActionRepository.DATABASE == 'custom_db'
        assert CACashFlowService.DATABASE == 'custom_db'
        assert CACashFlowQueueRepository.DATABASE == 'custom_db'
