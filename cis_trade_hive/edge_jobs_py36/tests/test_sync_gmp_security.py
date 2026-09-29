"""Tests for edge_jobs_py36/sync_gmp_security.py."""
import argparse
import os
from decimal import Decimal
from unittest.mock import patch

import pytest

from sync_gmp_security import (
    Command,
    _parse_int,
    _parse_decimal,
    _parse_bool,
    _normalize_quoted_unquoted,
    _apply_early_env_override,
)


def _row(**overrides):
    row = {
        'security_label': 'AAPL US',
        'isin': 'US0378331005',
        'security_full_name': 'Apple Inc',
        'issuer_name': 'Apple Inc',
        'ticker': 'AAPL',
        'exchange_code': 'NASDAQ',
        'currency_code': 'USD',
        'shares_outstanding': '1000000',
        'm_beta': '1.2',
        'quoted_unquoted': 'Quoted',
        'is_active': 'true',
    }
    row.update(overrides)
    return row


class TestParseInt:
    def test_none_returns_none(self):
        assert _parse_int(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_int('') is None

    def test_null_literal_returns_none(self):
        assert _parse_int('NULL') is None

    def test_valid_int_string(self):
        assert _parse_int('1000000') == 1000000

    def test_decimal_string_truncated_to_int(self):
        assert _parse_int('1000.99') == 1000

    def test_invalid_string_returns_none(self):
        assert _parse_int('not-a-number') is None


class TestParseDecimal:
    def test_none_returns_none(self):
        assert _parse_decimal(None) is None

    def test_empty_returns_none(self):
        assert _parse_decimal('') is None

    def test_valid_decimal(self):
        assert _parse_decimal('1.25') == Decimal('1.25')

    def test_invalid_returns_none(self):
        assert _parse_decimal('garbage') is None


class TestParseBool:
    def test_none_returns_none(self):
        assert _parse_bool(None) is None

    def test_true_string_returns_true(self):
        assert _parse_bool('true') is True

    def test_true_uppercase_returns_true(self):
        assert _parse_bool('TRUE') is True

    def test_false_string_returns_false(self):
        assert _parse_bool('false') is False

    def test_unrecognized_string_returns_none(self):
        assert _parse_bool('maybe') is None


class TestNormalizeQuotedUnquoted:
    def test_none_returns_none(self):
        assert _normalize_quoted_unquoted(None) is None

    def test_empty_returns_none(self):
        assert _normalize_quoted_unquoted('') is None

    def test_quoted_case_insensitive(self):
        assert _normalize_quoted_unquoted('quoted') == 'QUOTED'
        assert _normalize_quoted_unquoted('Quoted') == 'QUOTED'

    def test_unquoted_case_insensitive(self):
        assert _normalize_quoted_unquoted('unquoted') == 'UNQUOTED'

    def test_other_value_uppercased_as_is(self):
        assert _normalize_quoted_unquoted('mixed') == 'MIXED'


class TestApplyEarlyEnvOverride:
    def test_sets_from_space_form(self):
        with patch.dict(os.environ, {}, clear=False):
            _apply_early_env_override(['prog', '--env', 'PROD'])
            assert os.environ['CIS_ENV'] == 'PROD'

    def test_noop_when_absent(self):
        with patch.dict(os.environ, {}, clear=True):
            _apply_early_env_override(['prog'])
            assert 'CIS_ENV' not in os.environ


class TestAddArguments:
    def test_defaults(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args([])
        assert args.batch_size == 2000
        assert args.user == 'GMP_ETL'


class TestFetchGmpRecords:
    def test_returns_results(self):
        cmd = Command()
        with patch('sync_gmp_security.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [_row()]
            result = cmd._fetch_gmp_records(None, 2000)
        assert len(result) == 1

    def test_returns_empty_when_none(self):
        cmd = Command()
        with patch('sync_gmp_security.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            result = cmd._fetch_gmp_records(None, 2000)
        assert result == []

    def test_date_filter_applied(self):
        cmd = Command()
        with patch('sync_gmp_security.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records('2026-09-17', 2000)
        query = mock_mgr.execute_query.call_args[0][0]
        assert "'20260917'" in query

    def test_max_processing_date_used_by_default(self):
        cmd = Command()
        with patch('sync_gmp_security.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records(None, 2000)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'MAX(processing_date)' in query

    def test_batch_size_used_as_limit(self):
        cmd = Command()
        with patch('sync_gmp_security.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records(None, 42)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 42' in query

    def test_exception_returns_empty_list(self, capsys):
        cmd = Command()
        with patch('sync_gmp_security.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = cmd._fetch_gmp_records(None, 2000)
        assert result == []
        assert 'Error fetching GMP records' in capsys.readouterr().err


class TestProcessRow:
    def test_missing_security_label_skipped(self):
        cmd = Command()
        result = cmd._process_row(_row(security_label=''), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'skipped_invalid'
        assert 'missing security_label' in result['error']

    def test_dry_run_no_write(self):
        cmd = Command()
        with patch('sync_gmp_security.security_repository') as mock_repo:
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=True, verbose=False)
        assert result['outcome'] == 'upserted'
        mock_repo.upsert_security.assert_not_called()

    def test_successful_upsert(self):
        cmd = Command()
        with patch('sync_gmp_security.security_repository') as mock_repo:
            mock_repo.upsert_security.return_value = True
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'upserted'

    def test_upsert_false_is_error(self):
        cmd = Command()
        with patch('sync_gmp_security.security_repository') as mock_repo:
            mock_repo.upsert_security.return_value = False
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'errors'

    def test_upsert_exception_is_error(self):
        cmd = Command()
        with patch('sync_gmp_security.security_repository') as mock_repo:
            mock_repo.upsert_security.side_effect = RuntimeError('boom')
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'errors'
        assert 'DB error upserting' in result['error']

    def test_verbose_prints_sync_line(self, capsys):
        cmd = Command()
        with patch('sync_gmp_security.security_repository') as mock_repo:
            mock_repo.upsert_security.return_value = True
            cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=True)
        assert '[SYNC]' in capsys.readouterr().out

    def test_verbose_prints_invalid(self, capsys):
        cmd = Command()
        cmd._process_row(_row(security_label=''), 'GMP_ETL', dry_run=False, verbose=True)
        assert '[INVALID]' in capsys.readouterr().out

    def test_is_active_defaults_to_true_when_unparseable(self):
        cmd = Command()
        with patch('sync_gmp_security.security_repository') as mock_repo:
            mock_repo.upsert_security.return_value = True
            cmd._process_row(_row(is_active='garbled'), 'GMP_ETL', dry_run=False, verbose=False)
        data = mock_repo.upsert_security.call_args[0][0]
        assert data['is_active'] is True

    def test_is_active_false_is_respected(self):
        cmd = Command()
        with patch('sync_gmp_security.security_repository') as mock_repo:
            mock_repo.upsert_security.return_value = True
            cmd._process_row(_row(is_active='false'), 'GMP_ETL', dry_run=False, verbose=False)
        data = mock_repo.upsert_security.call_args[0][0]
        assert data['is_active'] is False

    def test_quoted_unquoted_normalized(self):
        cmd = Command()
        with patch('sync_gmp_security.security_repository') as mock_repo:
            mock_repo.upsert_security.return_value = True
            cmd._process_row(_row(quoted_unquoted='Quoted'), 'GMP_ETL', dry_run=False, verbose=False)
        data = mock_repo.upsert_security.call_args[0][0]
        assert data['quoted_unquoted'] == 'QUOTED'

    def test_numeric_fields_parsed(self):
        cmd = Command()
        with patch('sync_gmp_security.security_repository') as mock_repo:
            mock_repo.upsert_security.return_value = True
            cmd._process_row(_row(shares_outstanding='500', m_beta='0.9'), 'GMP_ETL', dry_run=False, verbose=False)
        data = mock_repo.upsert_security.call_args[0][0]
        assert data['shares_outstanding'] == 500
        assert data['beta'] == Decimal('0.9')

    def test_status_and_src_system_forced(self):
        cmd = Command()
        with patch('sync_gmp_security.security_repository') as mock_repo:
            mock_repo.upsert_security.return_value = True
            cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        data = mock_repo.upsert_security.call_args[0][0]
        assert data['status'] == 'VALIDATED'
        assert data['src_system'] == 'GMP'

    def test_upsert_called_with_created_by(self):
        cmd = Command()
        with patch('sync_gmp_security.security_repository') as mock_repo:
            mock_repo.upsert_security.return_value = True
            cmd._process_row(_row(), 'jdoe', dry_run=False, verbose=False)
        kwargs = mock_repo.upsert_security.call_args[1]
        assert kwargs.get('created_by') == 'jdoe'


class TestPrintHeaderAndSummary:
    def test_header_shows_default_date_filter(self, capsys):
        cmd = Command()
        cmd._print_header(None, False, 'GMP_ETL')
        assert 'latest processing_date per security' in capsys.readouterr().out

    def test_header_dry_run(self, capsys):
        cmd = Command()
        cmd._print_header(None, True, 'GMP_ETL')
        assert 'DRY RUN' in capsys.readouterr().out

    def test_summary_shows_hint_when_upserted_and_not_dry_run(self, capsys):
        cmd = Command()
        cmd._print_summary({'upserted': 1, 'skipped_invalid': 0, 'errors': 0}, [], dry_run=False)
        assert 'sync_gmp_equity_price.py next' in capsys.readouterr().out

    def test_summary_no_hint_when_dry_run(self, capsys):
        cmd = Command()
        cmd._print_summary({'upserted': 1, 'skipped_invalid': 0, 'errors': 0}, [], dry_run=True)
        assert 'sync_gmp_equity_price.py next' not in capsys.readouterr().out

    def test_summary_errors_capped_at_twenty(self, capsys):
        cmd = Command()
        errors = [f'e{i}' for i in range(23)]
        cmd._print_summary({'upserted': 0, 'skipped_invalid': 0, 'errors': 23}, errors, dry_run=False)
        assert '... and 3 more' in capsys.readouterr().out


class TestHandle:
    def test_no_records_prints_warning(self, capsys):
        cmd = Command()
        with patch('sync_gmp_security.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.handle(env=None, database=None, date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        assert 'No GMP security records found' in capsys.readouterr().out

    def test_processes_all_rows(self, capsys):
        cmd = Command()
        with patch('sync_gmp_security.impala_manager') as mock_mgr, \
             patch('sync_gmp_security.security_repository') as mock_repo:
            mock_mgr.execute_query.return_value = [_row(), _row(security_label='MSFT US')]
            mock_repo.upsert_security.return_value = True
            cmd.handle(env=None, database=None, date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        assert 'Upserted into cis_security : 2' in capsys.readouterr().out

    def test_database_override_updates_repository(self):
        cmd = Command()
        with patch('sync_gmp_security.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.handle(env=None, database='custom_db', date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        from sync_gmp_security import SecurityRepository
        assert SecurityRepository.DATABASE == 'custom_db'
