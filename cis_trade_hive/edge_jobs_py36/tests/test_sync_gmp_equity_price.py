"""Tests for edge_jobs_py36/sync_gmp_equity_price.py."""
import argparse
import os
from decimal import Decimal
from unittest.mock import patch

import pytest

from sync_gmp_equity_price import (
    Command,
    parse_gmp_price,
    parse_gmp_price_date,
    _apply_early_env_override,
)


def _row(**overrides):
    row = {
        'security_label': 'AAPL',
        'price_date_raw': '20260917',
        'main_closing_price': '150.25',
        'processing_date': '20260917',
        'currency_code': 'USD',
        'isin': 'US0378331005',
    }
    row.update(overrides)
    return row


class TestParseGmpPrice:
    def test_none_returns_none(self):
        assert parse_gmp_price(None) is None

    def test_empty_string_returns_none(self):
        assert parse_gmp_price('') is None

    def test_literal_none_string_returns_none(self):
        assert parse_gmp_price('None') is None

    def test_literal_null_returns_none(self):
        assert parse_gmp_price('null') is None
        assert parse_gmp_price('NULL') is None

    def test_valid_decimal_string(self):
        assert parse_gmp_price('150.25') == Decimal('150.25')

    def test_valid_float(self):
        assert parse_gmp_price(150.25) == Decimal('150.25')

    def test_valid_int(self):
        assert parse_gmp_price(150) == Decimal('150')

    def test_whitespace_is_stripped(self):
        assert parse_gmp_price('  150.25  ') == Decimal('150.25')

    def test_invalid_string_returns_none(self):
        assert parse_gmp_price('not-a-number') is None


class TestParseGmpPriceDate:
    def test_none_returns_none(self):
        assert parse_gmp_price_date(None) is None

    def test_empty_string_returns_none(self):
        assert parse_gmp_price_date('') is None

    def test_yyyymmdd_converted_to_iso(self):
        assert parse_gmp_price_date('20260917') == '2026-09-17'

    def test_already_iso_passes_through(self):
        assert parse_gmp_price_date('2026-09-17') == '2026-09-17'

    def test_non_digit_eight_char_string_returns_none(self):
        assert parse_gmp_price_date('2026091x') is None

    def test_unrecognizable_format_returns_none(self):
        assert parse_gmp_price_date('bad-date-value') is None

    def test_int_input_is_stringified(self):
        assert parse_gmp_price_date(20260917) == '2026-09-17'


class TestApplyEarlyEnvOverride:
    def test_sets_from_space_form(self):
        with patch.dict(os.environ, {}, clear=False):
            _apply_early_env_override(['prog', '--env', 'PROD'])
            assert os.environ['CIS_ENV'] == 'PROD'

    def test_sets_from_equals_form(self):
        with patch.dict(os.environ, {}, clear=False):
            _apply_early_env_override(['prog', '--env=dr'])
            assert os.environ['CIS_ENV'] == 'DR'

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
        assert args.user == 'GMP_ETL'


class TestFetchGmpRecords:
    def test_returns_results(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [_row()]
            result = cmd._fetch_gmp_records(None, 2000)
        assert len(result) == 1

    def test_returns_empty_list_when_none(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            result = cmd._fetch_gmp_records(None, 2000)
        assert result == []

    def test_excludes_log_del_securities(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records(None, 2000)
        query = mock_mgr.execute_query.call_args[0][0]
        assert "NOT LIKE '%LOG DEL%'" in query

    def test_date_filter_applied_when_given(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records('2026-09-17', 2000)
        query = mock_mgr.execute_query.call_args[0][0]
        assert "'20260917'" in query

    def test_no_date_filter_when_absent(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records(None, 2000)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'CAST(eq.processing_date AS STRING)' not in query

    def test_batch_size_used_as_limit(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd._fetch_gmp_records(None, 777)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 777' in query

    def test_returns_empty_and_logs_on_exception(self, capsys):
        cmd = Command()
        with patch('sync_gmp_equity_price.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = cmd._fetch_gmp_records(None, 2000)
        assert result == []
        assert 'Error fetching GMP records' in capsys.readouterr().err


class TestProcessRow:
    def test_missing_security_label_skipped(self):
        cmd = Command()
        result = cmd._process_row(_row(security_label=''), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'skipped_invalid'
        assert 'missing security label' in result['error']

    def test_unparseable_date_skipped(self):
        cmd = Command()
        result = cmd._process_row(_row(price_date_raw='garbage'), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'skipped_invalid'
        assert 'unparseable date' in result['error']

    def test_invalid_price_skipped(self):
        cmd = Command()
        result = cmd._process_row(_row(main_closing_price='not-a-number'), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'skipped_invalid'
        assert 'invalid price' in result['error']

    def test_missing_currency_code_skipped(self):
        cmd = Command()
        result = cmd._process_row(_row(currency_code=''), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'skipped_invalid'
        assert 'no currency_code match' in result['error']

    def test_dry_run_returns_upserted_without_writing(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.equity_price_repository') as mock_repo:
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=True, verbose=False)
        assert result['outcome'] == 'upserted'
        mock_repo.upsert.assert_not_called()

    def test_successful_upsert(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.equity_price_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'upserted'

    def test_upsert_returns_false_is_error(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.equity_price_repository') as mock_repo:
            mock_repo.upsert.return_value = False
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'errors'
        assert 'Upsert failed' in result['error']

    def test_upsert_exception_is_error(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.equity_price_repository') as mock_repo:
            mock_repo.upsert.side_effect = RuntimeError('db down')
            result = cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        assert result['outcome'] == 'errors'
        assert 'DB error upserting' in result['error']

    def test_verbose_prints_sync_line(self, capsys):
        cmd = Command()
        with patch('sync_gmp_equity_price.equity_price_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=True)
        assert '[SYNC]' in capsys.readouterr().out

    def test_verbose_prints_invalid_for_each_skip_reason(self, capsys):
        cmd = Command()
        cmd._process_row(_row(security_label=''), 'GMP_ETL', dry_run=False, verbose=True)
        assert '[INVALID]' in capsys.readouterr().out

    def test_verbose_prints_invalid_for_unparseable_date(self, capsys):
        cmd = Command()
        cmd._process_row(_row(price_date_raw='garbage'), 'GMP_ETL', dry_run=False, verbose=True)
        assert '[INVALID]' in capsys.readouterr().out

    def test_verbose_prints_invalid_for_bad_price(self, capsys):
        cmd = Command()
        cmd._process_row(_row(main_closing_price='bad'), 'GMP_ETL', dry_run=False, verbose=True)
        assert '[INVALID]' in capsys.readouterr().out

    def test_verbose_prints_invalid_for_missing_currency(self, capsys):
        cmd = Command()
        cmd._process_row(_row(currency_code=''), 'GMP_ETL', dry_run=False, verbose=True)
        assert '[INVALID]' in capsys.readouterr().out

    def test_price_data_uses_parsed_decimal_and_date(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.equity_price_repository') as mock_repo:
            mock_repo.upsert.return_value = True
            cmd._process_row(_row(), 'GMP_ETL', dry_run=False, verbose=False)
        data = mock_repo.upsert.call_args[0][0]
        assert data['main_closing_price'] == Decimal('150.25')
        assert data['price_date'] == '2026-09-17'
        assert data['src_system'] == 'GMP'


class TestPrintHeaderAndSummary:
    def test_header_shows_source_and_target(self, capsys):
        cmd = Command()
        cmd._print_header(None, False, 'GMP_ETL')
        out = capsys.readouterr().out
        assert 'GMP Equity Price Sync' in out
        assert 'cis_equity_price' in out

    def test_header_dry_run_mode(self, capsys):
        cmd = Command()
        cmd._print_header(None, True, 'GMP_ETL')
        assert 'DRY RUN' in capsys.readouterr().out

    def test_header_no_date_filter_line_when_absent(self, capsys):
        cmd = Command()
        cmd._print_header(None, False, 'GMP_ETL')
        assert 'Date filter' not in capsys.readouterr().out

    def test_header_date_filter_line_when_present(self, capsys):
        cmd = Command()
        cmd._print_header('20260917', False, 'GMP_ETL')
        assert 'Date filter  : 20260917' in capsys.readouterr().out

    def test_summary_basic(self, capsys):
        cmd = Command()
        cmd._print_summary({'upserted': 2, 'skipped_invalid': 1, 'errors': 0}, [], dry_run=False)
        assert 'Upserted into cis_equity_price : 2' in capsys.readouterr().out

    def test_summary_dry_run_prefix(self, capsys):
        cmd = Command()
        cmd._print_summary({'upserted': 2, 'skipped_invalid': 0, 'errors': 0}, [], dry_run=True)
        assert '[DRY RUN] Upserted' in capsys.readouterr().out

    def test_summary_lists_errors_capped_at_twenty(self, capsys):
        cmd = Command()
        errors = [f'err {i}' for i in range(22)]
        cmd._print_summary({'upserted': 0, 'skipped_invalid': 0, 'errors': 22}, errors, dry_run=False)
        out = capsys.readouterr().out
        assert '... and 2 more' in out


class TestHandle:
    def test_no_records_prints_warning(self, capsys):
        cmd = Command()
        with patch('sync_gmp_equity_price.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.handle(env=None, database=None, date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        assert 'No GMP equity price records found' in capsys.readouterr().out

    def test_processes_all_rows(self, capsys):
        cmd = Command()
        with patch('sync_gmp_equity_price.impala_manager') as mock_mgr, \
             patch('sync_gmp_equity_price.equity_price_repository') as mock_repo:
            mock_mgr.execute_query.return_value = [_row(), _row(security_label='MSFT')]
            mock_repo.upsert.return_value = True
            cmd.handle(env=None, database=None, date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        assert 'Upserted into cis_equity_price : 2' in capsys.readouterr().out

    def test_database_override_updates_repository(self):
        cmd = Command()
        with patch('sync_gmp_equity_price.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.handle(env=None, database='custom_db', date=None, dry_run=False, verbose=False,
                       user='GMP_ETL', batch_size=2000)
        from sync_gmp_equity_price import EquityPriceRepository
        assert EquityPriceRepository.DATABASE == 'custom_db'
