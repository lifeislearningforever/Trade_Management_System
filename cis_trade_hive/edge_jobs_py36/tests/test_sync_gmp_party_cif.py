"""Tests for edge_jobs_py36/sync_gmp_party_cif.py."""
import argparse
import os
from unittest.mock import patch

import pytest

import sync_gmp_party_cif as mod
from sync_gmp_party_cif import Command, _apply_early_env_override


def _row(**overrides):
    row = {
        'party_name': 'ACME BROKER',
        'm_label': None,
        'country': 'SG',
        'isin': 'US0378331005',
        'description': 'desc',
        'record_type': 'CIF',
        'sub_system': 'cis',
        'data_cat': 'sta',
        'data_frq': 'dly',
        'src_id': 'gmp_cis_sta_dly_party_cif',
        'processing_date': '20260917',
    }
    row.update(overrides)
    return row


class TestApplyEarlyEnvOverride:
    def test_sets_cis_env_from_space_separated_flag(self):
        with patch.dict(os.environ, {}, clear=False):
            _apply_early_env_override(['prog', '--env', 'UAT'])
            assert os.environ['CIS_ENV'] == 'UAT'

    def test_sets_cis_env_from_equals_form(self):
        with patch.dict(os.environ, {}, clear=False):
            _apply_early_env_override(['prog', '--env=sit'])
            assert os.environ['CIS_ENV'] == 'SIT'

    def test_does_nothing_when_env_flag_absent(self):
        with patch.dict(os.environ, {}, clear=True):
            _apply_early_env_override(['prog', '--dry-run'])
            assert 'CIS_ENV' not in os.environ

    def test_ignores_env_flag_with_no_following_value(self):
        with patch.dict(os.environ, {}, clear=True):
            _apply_early_env_override(['prog', '--env'])
            assert 'CIS_ENV' not in os.environ

    def test_uppercases_value(self):
        with patch.dict(os.environ, {}, clear=False):
            _apply_early_env_override(['prog', '--env', 'local'])
            assert os.environ['CIS_ENV'] == 'LOCAL'


class TestAddArguments:
    def test_defaults(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args([])
        assert args.env is None
        assert args.database is None
        assert args.date is None
        assert args.dry_run is False
        assert args.verbose is False
        assert args.user == 'GMP_ETL'
        assert args.batch_size == 2000

    def test_env_choices_validated(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(['--env', 'BOGUS'])

    def test_date_alias_flags(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args(['--processing-date', '20260917'])
        assert args.date == '20260917'
        args2 = parser.parse_args(['-d', '20260917'])
        assert args2.date == '20260917'


class TestFetchGmpRecords:
    def test_returns_results_when_present(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [_row()]
            result = cmd._fetch_gmp_records(None, 2000)
        assert len(result) == 1

    def test_returns_empty_list_when_none(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            result = cmd._fetch_gmp_records(None, 2000)
        assert result == []

    def test_uses_max_processing_date_when_no_date_given(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records(None, 2000)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'MAX(processing_date)' in query

    def test_uses_explicit_date_filter_and_strips_hyphens(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records('2026-09-17', 2000)
        query = mock_mgr.execute_query.call_args[0][0]
        assert "'20260917'" in query
        assert 'MAX(processing_date)' not in query

    def test_batch_size_used_as_limit(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records(None, 500)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 500' in query

    def test_returns_empty_list_and_logs_on_exception(self, capsys):
        cmd = Command()
        with patch('sync_gmp_party_cif.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = cmd._fetch_gmp_records(None, 2000)
        assert result == []
        assert 'Error fetching GMP records' in capsys.readouterr().err


class TestProcessRow:
    def test_missing_party_name_is_skipped_invalid(self):
        cmd = Command()
        result = cmd._process_row(_row(party_name=''), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'skipped_invalid'
        assert 'missing party_name' in result['error']

    def test_dry_run_returns_upserted_without_writing(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.party_cif_repository') as mock_repo:
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=True, verbose=False)
        assert result['outcome'] == 'upserted'
        mock_repo.upsert.assert_not_called()

    def test_successful_upsert(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.party_cif_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'upserted'

    def test_upsert_returns_false_is_an_error(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.party_cif_repository') as mock_repo:
            mock_repo.upsert.return_value = False
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'errors'
        assert 'Upsert failed' in result['error']

    def test_upsert_exception_is_an_error(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.party_cif_repository') as mock_repo:
            mock_repo.upsert.side_effect = RuntimeError('db down')
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'errors'
        assert 'DB error upserting' in result['error']

    def test_m_label_auto_generated_when_absent_and_country_present(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.party_cif_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(m_label=None, country='SG'), 'GMP_ETL', dry_run=False, verbose=False)
        cif_data = mock_repo.upsert.call_args[0][0]
        assert cif_data['m_label'] == 'ACME BROKER_SG'

    def test_m_label_explicit_value_is_used(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.party_cif_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(m_label='CUSTOM_LABEL'), 'GMP_ETL', dry_run=False, verbose=False)
        cif_data = mock_repo.upsert.call_args[0][0]
        assert cif_data['m_label'] == 'CUSTOM_LABEL'

    def test_verbose_prints_sync_line(self, capsys):
        cmd = Command()
        with patch('sync_gmp_party_cif.party_cif_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=True)
        out = capsys.readouterr().out
        assert '[SYNC]' in out

    def test_verbose_prints_invalid_warning(self, capsys):
        cmd = Command()
        cmd._process_row(_row(party_name=''), 'GMP_ETL', dry_run=False, verbose=True)
        out = capsys.readouterr().out
        assert '[INVALID]' in out

    def test_src_system_is_forced_to_gmp(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.party_cif_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        cif_data = mock_repo.upsert.call_args[0][0]
        assert cif_data['src_system'] == 'GMP'

    def test_created_by_and_updated_by_use_run_by(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.party_cif_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(), 'jdoe', dry_run=False, verbose=False)
        cif_data = mock_repo.upsert.call_args[0][0]
        assert cif_data['created_by'] == 'jdoe'
        assert cif_data['updated_by'] == 'jdoe'


class TestPrintHeaderAndSummary:
    def test_print_header_shows_defaults(self, capsys):
        cmd = Command()
        cmd._print_header(None, False, 'GMP_ETL')
        out = capsys.readouterr().out
        assert 'GMP Party CIF Sync' in out
        assert 'latest processing_date' in out

    def test_print_header_shows_date_filter_when_given(self, capsys):
        cmd = Command()
        cmd._print_header('20260917', False, 'GMP_ETL')
        out = capsys.readouterr().out
        assert 'Date filter  : 20260917' in out

    def test_print_header_shows_dry_run_mode(self, capsys):
        cmd = Command()
        cmd._print_header(None, True, 'GMP_ETL')
        out = capsys.readouterr().out
        assert 'DRY RUN' in out

    def test_print_header_shows_overridden_env_and_database(self, capsys):
        cmd = Command()
        cmd._print_header(None, False, 'GMP_ETL', env_override='UAT', database_override='custom_db')
        out = capsys.readouterr().out
        assert '(overridden)' in out

    def test_print_summary_basic_counts(self, capsys):
        cmd = Command()
        cmd._print_summary({'upserted': 3, 'skipped_invalid': 1, 'errors': 0}, [], dry_run=False)
        out = capsys.readouterr().out
        assert 'Upserted into cis_party_cif : 3' in out

    def test_print_summary_dry_run_prefix(self, capsys):
        cmd = Command()
        cmd._print_summary({'upserted': 3, 'skipped_invalid': 0, 'errors': 0}, [], dry_run=True)
        out = capsys.readouterr().out
        assert '[DRY RUN] Upserted' in out

    def test_print_summary_lists_errors_up_to_twenty(self, capsys):
        cmd = Command()
        errors = [f'err {i}' for i in range(25)]
        cmd._print_summary({'upserted': 0, 'skipped_invalid': 0, 'errors': 25}, errors, dry_run=False)
        out = capsys.readouterr().out
        assert 'err 0' in out
        assert '... and 5 more' in out


class TestHandle:
    def test_no_records_prints_warning_and_returns(self, capsys):
        cmd = Command()
        with patch('sync_gmp_party_cif.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.handle(env=None, database=None, date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        out = capsys.readouterr().out
        assert 'No GMP party CIF records found' in out

    def test_processes_all_rows_and_prints_summary(self, capsys):
        cmd = Command()
        with patch('sync_gmp_party_cif.impala_manager') as mock_mgr, \
             patch('sync_gmp_party_cif.party_cif_repository') as mock_repo:
            mock_mgr.execute_query.return_value = [_row(), _row(party_name='OTHER')]
            mock_repo.upsert.return_value = True
            cmd.handle(env=None, database=None, date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        out = capsys.readouterr().out
        assert 'Upserted into cis_party_cif : 2' in out

    def test_database_override_updates_repository_database(self):
        cmd = Command()
        with patch('sync_gmp_party_cif.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.handle(env=None, database='custom_db', date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        from sync_gmp_party_cif import PartyCifRepository
        assert PartyCifRepository.DATABASE == 'custom_db'

    def test_mixed_outcomes_counted_correctly(self, capsys):
        cmd = Command()
        with patch('sync_gmp_party_cif.impala_manager') as mock_mgr, \
             patch('sync_gmp_party_cif.party_cif_repository') as mock_repo:
            mock_mgr.execute_query.return_value = [
                _row(party_name='A'), _row(party_name=''), _row(party_name='C'),
            ]
            mock_repo.upsert.side_effect = [True, RuntimeError('boom')]
            cmd.handle(env=None, database=None, date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        out = capsys.readouterr().out
        assert 'Upserted into cis_party_cif : 1' in out
        assert 'Skipped (invalid)            : 1' in out
        assert 'Errors                       : 1' in out
