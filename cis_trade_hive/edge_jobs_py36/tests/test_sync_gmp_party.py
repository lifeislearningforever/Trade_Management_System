"""Tests for edge_jobs_py36/sync_gmp_party.py."""
import argparse
import os
from unittest.mock import patch

import pytest

from sync_gmp_party import Command, _yn_to_bool, _apply_early_env_override


def _row(**overrides):
    row = {
        'counterparty_short_name': 'ACME BROKER',
        'counterparty_full_name': 'Acme Broker Pte Ltd',
        'record_type': 'BROKER',
        'is_broker': 'Y',
        'is_custodian': 'N',
        'is_subsidiate': 'Y',
        'sub_system': 'cis',
        'data_cat': 'sta',
        'data_frq': 'dly',
        'processing_date': '20260917',
    }
    row.update(overrides)
    return row


class TestYnToBool:
    def test_y_uppercase_is_true(self):
        assert _yn_to_bool('Y') is True

    def test_y_lowercase_is_true(self):
        assert _yn_to_bool('y') is True

    def test_n_is_false(self):
        assert _yn_to_bool('N') is False

    def test_none_is_false(self):
        assert _yn_to_bool(None) is False

    def test_empty_string_is_false(self):
        assert _yn_to_bool('') is False

    def test_whitespace_around_y_is_true(self):
        assert _yn_to_bool('  Y  ') is True

    def test_other_value_is_false(self):
        assert _yn_to_bool('MAYBE') is False


class TestApplyEarlyEnvOverride:
    def test_sets_from_space_form(self):
        with patch.dict(os.environ, {}, clear=False):
            _apply_early_env_override(['prog', '--env', 'SIT'])
            assert os.environ['CIS_ENV'] == 'SIT'

    def test_sets_from_equals_form(self):
        with patch.dict(os.environ, {}, clear=False):
            _apply_early_env_override(['prog', '--env=uat'])
            assert os.environ['CIS_ENV'] == 'UAT'

    def test_noop_when_absent(self):
        with patch.dict(os.environ, {}, clear=True):
            _apply_early_env_override(['prog'])
            assert 'CIS_ENV' not in os.environ


class TestAddArguments:
    def test_defaults(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args([])
        assert args.env is None
        assert args.dry_run is False
        assert args.batch_size == 2000


class TestFetchGmpRecords:
    def test_returns_results(self):
        cmd = Command()
        with patch('sync_gmp_party.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [_row()]
            result = cmd._fetch_gmp_records(None, 2000)
        assert len(result) == 1

    def test_returns_empty_list_when_none(self):
        cmd = Command()
        with patch('sync_gmp_party.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            result = cmd._fetch_gmp_records(None, 2000)
        assert result == []

    def test_date_filter_applied_when_given(self):
        cmd = Command()
        with patch('sync_gmp_party.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records('2026-09-17', 2000)
        query = mock_mgr.execute_query.call_args[0][0]
        assert "'20260917'" in query

    def test_max_processing_date_used_when_no_date_given(self):
        cmd = Command()
        with patch('sync_gmp_party.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records(None, 2000)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'MAX(processing_date)' in query

    def test_batch_size_used_as_limit(self):
        cmd = Command()
        with patch('sync_gmp_party.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records(None, 333)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 333' in query

    def test_returns_empty_and_logs_on_exception(self, capsys):
        cmd = Command()
        with patch('sync_gmp_party.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = cmd._fetch_gmp_records(None, 2000)
        assert result == []
        assert 'Error fetching GMP records' in capsys.readouterr().err


class TestProcessRow:
    def test_missing_short_name_skipped(self):
        cmd = Command()
        result = cmd._process_row(_row(counterparty_short_name=''), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'skipped_invalid'
        assert 'missing counterparty_short_name' in result['error']

    def test_dry_run_returns_upserted_without_writing(self):
        cmd = Command()
        with patch('sync_gmp_party.party_repository') as mock_repo:
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=True, verbose=False)
        assert result['outcome'] == 'upserted'
        mock_repo.upsert.assert_not_called()

    def test_successful_upsert(self):
        cmd = Command()
        with patch('sync_gmp_party.party_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'upserted'

    def test_upsert_returns_false_is_error(self):
        cmd = Command()
        with patch('sync_gmp_party.party_repository') as mock_repo:
            mock_repo.upsert.return_value = False
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'errors'
        assert 'Upsert failed' in result['error']

    def test_upsert_exception_is_error(self):
        cmd = Command()
        with patch('sync_gmp_party.party_repository') as mock_repo:
            mock_repo.upsert.side_effect = RuntimeError('db down')
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'errors'
        assert 'DB error upserting' in result['error']

    def test_verbose_prints_sync_line(self, capsys):
        cmd = Command()
        with patch('sync_gmp_party.party_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=True)
        assert '[SYNC]' in capsys.readouterr().out

    def test_verbose_prints_invalid_warning(self, capsys):
        cmd = Command()
        cmd._process_row(_row(counterparty_short_name=''), 'GMP_ETL', dry_run=False, verbose=True)
        assert '[INVALID]' in capsys.readouterr().out

    def test_yn_flags_are_converted_to_booleans(self):
        cmd = Command()
        with patch('sync_gmp_party.party_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(is_broker='Y', is_custodian='N'), 'GMP_ETL', dry_run=False, verbose=False)
        data = mock_repo.upsert.call_args[0][0]
        assert data['is_broker'] is True
        assert data['is_custodian'] is False

    def test_is_subsidiate_source_field_maps_to_is_subsidiary(self):
        cmd = Command()
        with patch('sync_gmp_party.party_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(is_subsidiate='Y'), 'GMP_ETL', dry_run=False, verbose=False)
        data = mock_repo.upsert.call_args[0][0]
        assert data['is_subsidiary'] is True

    def test_status_forced_to_validated_and_src_system_gmp(self):
        cmd = Command()
        with patch('sync_gmp_party.party_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        data = mock_repo.upsert.call_args[0][0]
        assert data['status'] == 'VALIDATED'
        assert data['src_system'] == 'GMP'

    def test_created_by_and_updated_by_use_run_by(self):
        cmd = Command()
        with patch('sync_gmp_party.party_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(), 'jdoe', dry_run=False, verbose=False)
        data = mock_repo.upsert.call_args[0][0]
        assert data['created_by'] == 'jdoe'
        assert data['updated_by'] == 'jdoe'


class TestPrintHeaderAndSummary:
    def test_header_default_date_filter_line(self, capsys):
        cmd = Command()
        cmd._print_header(None, False, 'GMP_ETL')
        assert 'latest processing_date per party' in capsys.readouterr().out

    def test_header_explicit_date(self, capsys):
        cmd = Command()
        cmd._print_header('20260917', False, 'GMP_ETL')
        assert 'Date filter  : 20260917' in capsys.readouterr().out

    def test_header_dry_run(self, capsys):
        cmd = Command()
        cmd._print_header(None, True, 'GMP_ETL')
        assert 'DRY RUN' in capsys.readouterr().out

    def test_summary_basic(self, capsys):
        cmd = Command()
        cmd._print_summary({'upserted': 4, 'skipped_invalid': 0, 'errors': 0}, [], dry_run=False)
        assert 'Upserted into cis_party : 4' in capsys.readouterr().out

    def test_summary_shows_next_step_hint_when_upserted_and_not_dry_run(self, capsys):
        cmd = Command()
        cmd._print_summary({'upserted': 1, 'skipped_invalid': 0, 'errors': 0}, [], dry_run=False)
        assert 'sync_gmp_party_cif.py next' in capsys.readouterr().out

    def test_summary_no_hint_when_dry_run(self, capsys):
        cmd = Command()
        cmd._print_summary({'upserted': 1, 'skipped_invalid': 0, 'errors': 0}, [], dry_run=True)
        assert 'sync_gmp_party_cif.py next' not in capsys.readouterr().out

    def test_summary_no_hint_when_nothing_upserted(self, capsys):
        cmd = Command()
        cmd._print_summary({'upserted': 0, 'skipped_invalid': 0, 'errors': 0}, [], dry_run=False)
        assert 'sync_gmp_party_cif.py next' not in capsys.readouterr().out

    def test_summary_lists_errors_capped_at_twenty(self, capsys):
        cmd = Command()
        errors = [f'err {i}' for i in range(21)]
        cmd._print_summary({'upserted': 0, 'skipped_invalid': 0, 'errors': 21}, errors, dry_run=False)
        assert '... and 1 more' in capsys.readouterr().out


class TestHandle:
    def test_no_records_prints_warning(self, capsys):
        cmd = Command()
        with patch('sync_gmp_party.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.handle(env=None, database=None, date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        assert 'No GMP party records found' in capsys.readouterr().out

    def test_processes_all_rows(self, capsys):
        cmd = Command()
        with patch('sync_gmp_party.impala_manager') as mock_mgr, \
             patch('sync_gmp_party.party_repository') as mock_repo:
            mock_mgr.execute_query.return_value = [_row(), _row(counterparty_short_name='OTHER')]
            mock_repo.upsert.return_value = True
            cmd.handle(env=None, database=None, date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        assert 'Upserted into cis_party : 2' in capsys.readouterr().out

    def test_database_override_updates_repository(self):
        cmd = Command()
        with patch('sync_gmp_party.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.handle(env=None, database='custom_db', date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        from sync_gmp_party import PartyRepository
        assert PartyRepository.DATABASE == 'custom_db'
