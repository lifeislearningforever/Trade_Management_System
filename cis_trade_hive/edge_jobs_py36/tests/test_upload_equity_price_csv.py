"""Tests for edge_jobs_py36/upload_equity_price_csv.py."""
import sys
from decimal import Decimal
from unittest.mock import patch

import pytest

import upload_equity_price_csv as mod
from upload_equity_price_csv import (
    _esc,
    _clean_price,
    _normalise_date,
    _map_headers,
    check_gmp_conflict,
    load_existing_keys,
    parse_csv,
    process_rows,
    _upsert_batch,
    parse_args,
    main,
)


def _write_csv(tmp_path, header, rows, name='prices.csv'):
    path = tmp_path / name
    lines = [','.join(header)] + [','.join(r) for r in rows]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return str(path)


class TestEsc:
    def test_none_returns_empty_quoted(self):
        assert _esc(None) == "''"

    def test_escapes_quote_and_backslash(self):
        assert _esc("O'Brien\\x") == "'O\\'Brien\\\\x'"

    def test_plain_string(self):
        assert _esc('ABC') == "'ABC'"


class TestCleanPrice:
    def test_none_returns_none(self):
        assert _clean_price(None) is None

    def test_empty_string_returns_none(self):
        assert _clean_price('') is None

    def test_whitespace_only_returns_none(self):
        assert _clean_price('   ') is None

    def test_plain_number(self):
        assert _clean_price('1.25') == Decimal('1.25')

    def test_strips_currency_symbols_and_commas(self):
        assert _clean_price('$1,234.56') == Decimal('1234.56')

    def test_strips_percent_and_spaces(self):
        assert _clean_price(' 12.5% ') == Decimal('12.5')

    def test_parenthesized_negative_becomes_negative(self):
        assert _clean_price('(1.25)') is None  # negative rejected below (<=0)

    def test_zero_is_rejected(self):
        assert _clean_price('0') is None

    def test_negative_is_rejected(self):
        assert _clean_price('-5') is None

    def test_invalid_string_returns_none(self):
        assert _clean_price('not-a-price') is None


class TestNormaliseDate:
    def test_none_returns_none(self):
        assert _normalise_date(None) is None

    def test_empty_returns_none(self):
        assert _normalise_date('') is None

    def test_iso_format(self):
        assert _normalise_date('2026-09-17') == '2026-09-17'

    def test_dmy_slash_format(self):
        assert _normalise_date('17/09/2026') == '2026-09-17'

    def test_dmy_dash_format(self):
        assert _normalise_date('17-09-2026') == '2026-09-17'

    def test_yyyymmdd_format(self):
        assert _normalise_date('20260917') == '2026-09-17'

    def test_mdy_slash_format(self):
        assert _normalise_date('09/17/2026') == '2026-09-17'

    def test_unrecognizable_format_returns_none(self):
        assert _normalise_date('not-a-date') is None

    def test_strips_whitespace(self):
        assert _normalise_date('  2026-09-17  ') == '2026-09-17'


class TestMapHeaders:
    def test_maps_canonical_names(self):
        mapping = _map_headers(['security_label', 'price_date', 'price'])
        assert mapping == {'security_label': 0, 'price_date': 1, 'price': 2}

    def test_maps_aliases_case_insensitive(self):
        mapping = _map_headers(['Security Label', 'Price Date', 'Closing Price'])
        assert mapping['security_label'] == 0
        assert mapping['price_date'] == 1
        assert mapping['price'] == 2

    def test_maps_optional_isin_and_currency(self):
        mapping = _map_headers(['name', 'date', 'price', 'ISIN', 'Currency'])
        assert mapping['isin'] == 3
        assert mapping['currency_code'] == 4

    def test_unrecognized_column_is_ignored(self):
        mapping = _map_headers(['name', 'date', 'price', 'random_col'])
        assert 'random_col' not in mapping.values()

    def test_first_matching_column_wins_on_duplicate_alias(self):
        mapping = _map_headers(['name', 'security', 'date', 'price'])
        assert mapping['security_label'] == 0  # 'name' matched first


class TestCheckGmpConflict:
    def test_empty_set_returns_empty_list_without_query(self):
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            result = check_gmp_conflict(set())
        assert result == []
        mock_mgr.execute_query.assert_not_called()

    def test_returns_conflicting_dates(self):
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'price_date': '2026-09-17'}]
            result = check_gmp_conflict({'2026-09-17'})
        assert result == ['2026-09-17']

    def test_returns_empty_when_no_conflicts(self):
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = check_gmp_conflict({'2026-09-17'})
        assert result == []

    def test_query_filters_by_gmp_source_and_dates(self):
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            check_gmp_conflict({'2026-09-17', '2026-09-18'})
        query = mock_mgr.execute_query.call_args[0][0]
        assert "src_system = 'GMP'" in query
        assert "'2026-09-17'" in query
        assert "'2026-09-18'" in query


class TestLoadExistingKeys:
    def test_returns_set_of_tuples(self):
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'security_label': 'AAPL', 'price_date': '2026-09-17'},
            ]
            keys = load_existing_keys()
        assert ('AAPL', '2026-09-17') in keys

    def test_no_price_dates_filter_has_where_1_equals_1(self):
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            load_existing_keys(price_dates=None)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'WHERE 1=1' in query

    def test_single_date_uses_equality_filter(self):
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            load_existing_keys(price_dates={'2026-09-17'})
        query = mock_mgr.execute_query.call_args[0][0]
        assert "price_date = '2026-09-17'" in query

    def test_multiple_dates_uses_in_clause(self):
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            load_existing_keys(price_dates={'2026-09-17', '2026-09-18'})
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'price_date IN' in query

    def test_returns_empty_set_when_no_rows(self):
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            keys = load_existing_keys()
        assert keys == set()


class TestParseCsv:
    def test_parses_rows_with_canonical_headers(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'],
                               [['AAPL', '2026-09-17', '150.25']])
        rows = parse_csv(csv_path, None)
        assert rows[0]['security_label'] == 'AAPL'
        assert rows[0]['price'] == '150.25'

    def test_missing_security_label_column_raises(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['date', 'price'], [['2026-09-17', '150']])
        with pytest.raises(ValueError, match='missing required security_label column'):
            parse_csv(csv_path, None)

    def test_missing_price_column_raises(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['security_label', 'date'], [['AAPL', '2026-09-17']])
        with pytest.raises(ValueError, match='missing required price column'):
            parse_csv(csv_path, None)

    def test_missing_price_date_without_override_raises(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['security_label', 'price'], [['AAPL', '150']])
        with pytest.raises(ValueError, match="missing 'price_date' column"):
            parse_csv(csv_path, None)

    def test_missing_price_date_with_override_is_ok(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['security_label', 'price'], [['AAPL', '150']])
        rows = parse_csv(csv_path, '2026-09-17')
        assert rows[0]['price_date'] == '2026-09-17'

    def test_skips_blank_lines(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'],
                               [['AAPL', '2026-09-17', '150'], [',,'], ['MSFT', '2026-09-17', '300']])
        rows = parse_csv(csv_path, None)
        assert len(rows) == 2

    def test_override_date_takes_priority_over_csv_value(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'],
                               [['AAPL', '2026-01-01', '150']])
        rows = parse_csv(csv_path, '2026-09-17')
        assert rows[0]['price_date'] == '2026-09-17'

    def test_optional_columns_default_empty_when_absent(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'],
                               [['AAPL', '2026-09-17', '150']])
        rows = parse_csv(csv_path, None)
        assert rows[0]['isin'] == ''
        assert rows[0]['currency_code'] == ''

    def test_lineno_starts_at_two(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'],
                               [['AAPL', '2026-09-17', '150']])
        rows = parse_csv(csv_path, None)
        assert rows[0]['lineno'] == 2


class TestProcessRows:
    def _row(self, **overrides):
        row = {
            'lineno': 2, 'security_label': 'AAPL', 'price_date': '2026-09-17',
            'price': '150.25', 'isin': '', 'currency_code': '',
        }
        row.update(overrides)
        return row

    def test_empty_security_label_counted_invalid(self):
        with patch('upload_equity_price_csv._upsert_batch'):
            summary = process_rows([self._row(security_label='  ')], set(), False, True, 500)
        assert summary['invalid'] == 1

    def test_bad_price_counted_invalid(self):
        with patch('upload_equity_price_csv._upsert_batch'):
            summary = process_rows([self._row(price='not-a-price')], set(), False, True, 500)
        assert summary['invalid'] == 1

    def test_bad_date_counted_invalid(self):
        with patch('upload_equity_price_csv._upsert_batch'):
            summary = process_rows([self._row(price_date='garbage')], set(), False, True, 500)
        assert summary['invalid'] == 1

    def test_existing_key_skipped_without_overwrite(self):
        with patch('upload_equity_price_csv._upsert_batch') as mock_upsert:
            summary = process_rows(
                [self._row()], {('AAPL', '2026-09-17')}, overwrite=False, dry_run=True, batch_size=500,
            )
        assert summary['skip'] == 1
        mock_upsert.assert_not_called()

    def test_existing_key_reprocessed_with_overwrite(self):
        with patch('upload_equity_price_csv._upsert_batch') as mock_upsert:
            summary = process_rows(
                [self._row()], {('AAPL', '2026-09-17')}, overwrite=True, dry_run=True, batch_size=500,
            )
        assert summary['upsert'] == 1
        mock_upsert.assert_called_once()

    def test_valid_new_row_is_upserted(self):
        with patch('upload_equity_price_csv._upsert_batch') as mock_upsert:
            summary = process_rows([self._row()], set(), False, True, 500)
        assert summary['upsert'] == 1
        assert summary['total'] == 1

    def test_batch_flushed_when_size_reached(self):
        rows = [self._row(security_label=f'SEC{i}') for i in range(3)]
        with patch('upload_equity_price_csv._upsert_batch') as mock_upsert:
            process_rows(rows, set(), False, True, batch_size=2)
        assert mock_upsert.call_count == 2  # one batch of 2, one final flush of 1

    def test_errors_list_has_line_number(self):
        with patch('upload_equity_price_csv._upsert_batch'):
            summary = process_rows([self._row(price='bad', lineno=5)], set(), False, True, 500)
        assert 'Line 5' in summary['errors'][0]


class TestUpsertBatch:
    def test_dry_run_does_not_call_execute_write(self):
        batch = [{
            'security_label': 'AAPL', 'price_date': '2026-09-17', 'isin': '',
            'currency_code': '', 'price': '150.25', 'now_ts': '2026-09-17 10:00:00',
        }]
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            _upsert_batch(batch, dry_run=True)
        mock_mgr.execute_write.assert_not_called()

    def test_live_run_calls_execute_write(self):
        batch = [{
            'security_label': 'AAPL', 'price_date': '2026-09-17', 'isin': 'US0378331005',
            'currency_code': 'USD', 'price': '150.25', 'now_ts': '2026-09-17 10:00:00',
        }]
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            _upsert_batch(batch, dry_run=False)
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'UPSERT INTO' in sql
        assert "'AAPL'" in sql
        assert "'US0378331005'" in sql

    def test_missing_isin_and_currency_become_null(self):
        batch = [{
            'security_label': 'AAPL', 'price_date': '2026-09-17', 'isin': '',
            'currency_code': '', 'price': '150.25', 'now_ts': '2026-09-17 10:00:00',
        }]
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            _upsert_batch(batch, dry_run=False)
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'NULL' in sql

    def test_logs_error_when_write_fails(self, caplog):
        batch = [{
            'security_label': 'AAPL', 'price_date': '2026-09-17', 'isin': '',
            'currency_code': '', 'price': '150.25', 'now_ts': '2026-09-17 10:00:00',
        }]
        with patch('upload_equity_price_csv.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = False
            _upsert_batch(batch, dry_run=False)  # should not raise


class TestParseArgs:
    def test_requires_file(self):
        with patch.object(sys, 'argv', ['prog']):
            with pytest.raises(SystemExit):
                parse_args()

    def test_defaults(self):
        with patch.object(sys, 'argv', ['prog', '--file', 'x.csv']):
            args = parse_args()
        assert args.file == 'x.csv'
        assert args.price_date is None
        assert args.overwrite is False
        assert args.dry_run is False
        assert args.batch_size == 500
        assert args.force_gmp_override is False

    def test_all_flags(self):
        with patch.object(sys, 'argv', [
            'prog', '--file', 'x.csv', '--price-date', '2026-09-17', '--overwrite',
            '--dry-run', '--batch-size', '50', '--force-gmp-override', '--debug',
        ]):
            args = parse_args()
        assert args.overwrite is True
        assert args.batch_size == 50
        assert args.force_gmp_override is True
        assert args.debug is True


class TestMain:
    def test_exits_when_file_not_found(self, capsys):
        with patch.object(sys, 'argv', ['prog', '--file', '/no/such/file.csv']), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        assert 'file not found' in capsys.readouterr().out

    def test_exits_on_invalid_price_date_override(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'],
                               [['AAPL', '2026-09-17', '150']])
        with patch.object(sys, 'argv', ['prog', '--file', csv_path, '--price-date', 'garbage']), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        assert 'invalid --price-date' in capsys.readouterr().out

    def test_exits_zero_when_no_data_rows(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'], [])
        with patch.object(sys, 'argv', ['prog', '--file', csv_path]), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        assert 'nothing to do' in capsys.readouterr().out

    def test_exits_on_csv_parse_error(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['date', 'price'], [['2026-09-17', '150']])
        with patch.object(sys, 'argv', ['prog', '--file', csv_path]), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        assert 'ERROR reading CSV' in capsys.readouterr().out

    def test_gmp_guard_blocks_upload_when_conflict_found(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'],
                               [['AAPL', '2026-09-17', '150']])
        with patch.object(sys, 'argv', ['prog', '--file', csv_path]), \
             patch('upload_equity_price_csv.check_gmp_conflict', return_value=['2026-09-17']), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        assert 'GMP prices already exist' in capsys.readouterr().out

    def test_gmp_guard_bypassed_with_force_flag(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'],
                               [['AAPL', '2026-09-17', '150']])
        with patch.object(sys, 'argv', ['prog', '--file', csv_path, '--force-gmp-override', '--dry-run']), \
             patch('upload_equity_price_csv.check_gmp_conflict') as mock_check, \
             patch('upload_equity_price_csv.load_existing_keys', return_value=set()):
            main()
        mock_check.assert_not_called()

    def test_successful_dry_run_prints_results(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'],
                               [['AAPL', '2026-09-17', '150']])
        with patch.object(sys, 'argv', ['prog', '--file', csv_path, '--dry-run']), \
             patch('upload_equity_price_csv.check_gmp_conflict', return_value=[]), \
             patch('upload_equity_price_csv.load_existing_keys', return_value=set()):
            main()
        out = capsys.readouterr().out
        assert 'RESULTS' in out
        assert 'Inserted    : 1 (dry-run' in out

    def test_exits_one_when_all_rows_invalid(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'],
                               [['AAPL', '2026-09-17', 'bad-price']])
        with patch.object(sys, 'argv', ['prog', '--file', csv_path, '--dry-run']), \
             patch('upload_equity_price_csv.check_gmp_conflict', return_value=[]), \
             patch('upload_equity_price_csv.load_existing_keys', return_value=set()), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_does_not_exit_when_some_rows_succeed(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['security_label', 'price_date', 'price'],
                               [['AAPL', '2026-09-17', '150'], ['MSFT', '2026-09-17', 'bad']])
        with patch.object(sys, 'argv', ['prog', '--file', csv_path, '--dry-run']), \
             patch('upload_equity_price_csv.check_gmp_conflict', return_value=[]), \
             patch('upload_equity_price_csv.load_existing_keys', return_value=set()):
            main()  # should not raise SystemExit
