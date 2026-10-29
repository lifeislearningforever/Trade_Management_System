"""Tests for edge_jobs_py36/upload_amsiceq_positions.py."""
import argparse
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from upload_amsiceq_positions import Command


def _cmd():
    return Command()


class TestAddArguments:
    def test_defaults(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        args = parser.parse_args([])
        assert args.file == Command.DEFAULT_FILE
        assert args.dry_run is False
        assert args.skip_portfolios is False
        assert args.skip_securities is False

    def test_all_flags_parse(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        args = parser.parse_args([
            '--file', 'x.xlsx', '--dry-run', '--skip-portfolios', '--skip-securities',
        ])
        assert args.file == 'x.xlsx'
        assert args.dry_run is True
        assert args.skip_portfolios is True
        assert args.skip_securities is True


class TestEscapeString:
    def test_none_returns_empty(self):
        assert _cmd()._escape_string(None) == ''

    def test_escapes_quote_and_backslash(self):
        assert _cmd()._escape_string("O'Brien\\x") == "O\\'Brien\\\\x"


class TestToDecimal:
    def test_none_returns_default(self):
        assert _cmd()._to_decimal(None, Decimal('0')) == Decimal('0')

    def test_nan_returns_default(self):
        assert _cmd()._to_decimal(float('nan'), Decimal('0')) == Decimal('0')

    def test_valid_number_converted(self):
        assert _cmd()._to_decimal('1.25', 0) == Decimal('1.25')

    def test_invalid_value_returns_default(self):
        assert _cmd()._to_decimal('garbage', Decimal('99')) == Decimal('99')

    def test_default_can_be_none(self):
        assert _cmd()._to_decimal(None, None) is None


class TestFormatNullableString:
    def test_none_returns_null(self):
        assert _cmd()._format_nullable_string(None) == 'NULL'

    def test_nan_returns_null(self):
        assert _cmd()._format_nullable_string(float('nan')) == 'NULL'

    def test_value_is_quoted_and_escaped(self):
        assert _cmd()._format_nullable_string("O'Brien") == "'O\\'Brien'"


class TestFormatNullableDecimal:
    def test_none_returns_null(self):
        assert _cmd()._format_nullable_decimal(None) == 'NULL'

    def test_nan_returns_null(self):
        assert _cmd()._format_nullable_decimal(float('nan')) == 'NULL'

    def test_decimal_stringified(self):
        assert _cmd()._format_nullable_decimal(Decimal('1.5')) == '1.5'


class TestPortfolioExists:
    def test_returns_true_when_found(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'name': 'UOIOIF'}]
            assert _cmd()._portfolio_exists('UOIOIF') is True

    def test_returns_false_when_not_found(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert _cmd()._portfolio_exists('UOIOIF') is False

    def test_returns_false_on_exception(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert _cmd()._portfolio_exists('UOIOIF') is False


class TestCreatePortfolio:
    def test_returns_true_on_success(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert _cmd()._create_portfolio('UOIOIF') is True

    def test_query_uses_usd_currency(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            _cmd()._create_portfolio('UOIOIF')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'USD'" in sql
        assert "'UOIOIF'" in sql

    def test_returns_false_on_exception(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert _cmd()._create_portfolio('UOIOIF') is False


class TestEnsurePortfoliosExist:
    def test_skips_none_and_nan_codes(self, capsys):
        cmd = _cmd()
        with patch.object(cmd, '_portfolio_exists') as mock_exists:
            cmd._ensure_portfolios_exist([None, float('nan')], dry_run=False)
        mock_exists.assert_not_called()

    def test_existing_portfolio_not_recreated(self, capsys):
        cmd = _cmd()
        with patch.object(cmd, '_portfolio_exists', return_value=True), \
             patch.object(cmd, '_create_portfolio') as mock_create:
            cmd._ensure_portfolios_exist(['UOIOIF'], dry_run=False)
        mock_create.assert_not_called()
        assert 'EXISTS' in capsys.readouterr().out

    def test_missing_portfolio_created_when_not_dry_run(self):
        cmd = _cmd()
        with patch.object(cmd, '_portfolio_exists', return_value=False), \
             patch.object(cmd, '_create_portfolio', return_value=True) as mock_create:
            cmd._ensure_portfolios_exist(['UOIOIF'], dry_run=False)
        mock_create.assert_called_once_with('UOIOIF')

    def test_dry_run_does_not_create(self):
        cmd = _cmd()
        with patch.object(cmd, '_portfolio_exists', return_value=False), \
             patch.object(cmd, '_create_portfolio') as mock_create:
            cmd._ensure_portfolios_exist(['UOIOIF'], dry_run=True)
        mock_create.assert_not_called()

    def test_create_failure_prints_error(self, capsys):
        cmd = _cmd()
        with patch.object(cmd, '_portfolio_exists', return_value=False), \
             patch.object(cmd, '_create_portfolio', return_value=False):
            cmd._ensure_portfolios_exist(['UOIOIF'], dry_run=False)
        assert 'Failed to create' in capsys.readouterr().err


class TestFindSecurityByIsin:
    def test_returns_first_result(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_name': 'APPLE'}]
            assert _cmd()._find_security_by_isin('US0378331005')['security_name'] == 'APPLE'

    def test_returns_none_when_not_found(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert _cmd()._find_security_by_isin('US0378331005') is None

    def test_returns_none_on_exception(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert _cmd()._find_security_by_isin('US0378331005') is None


class TestCreatePlaceholderSecurity:
    def test_returns_dict_on_success(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = _cmd()._create_placeholder_security('US0378331005')
        assert result['isin'] == 'US0378331005'
        assert result['security_name'] == 'US0378331005'

    def test_returns_none_on_write_failure(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = False
            assert _cmd()._create_placeholder_security('US0378331005') is None

    def test_returns_none_on_exception(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert _cmd()._create_placeholder_security('US0378331005') is None


class TestBuildSecurityCache:
    def test_skips_none_and_nan_isins(self):
        cmd = _cmd()
        with patch.object(cmd, '_find_security_by_isin') as mock_find:
            result = cmd._build_security_cache([None, float('nan')], dry_run=False)
        mock_find.assert_not_called()
        assert result == {}

    def test_found_security_added_to_cache(self):
        cmd = _cmd()
        with patch.object(cmd, '_find_security_by_isin', return_value={'security_name': 'APPLE'}):
            result = cmd._build_security_cache(['US0378331005'], dry_run=False)
        assert result['US0378331005']['security_name'] == 'APPLE'

    def test_not_found_creates_placeholder_when_not_dry_run(self):
        cmd = _cmd()
        with patch.object(cmd, '_find_security_by_isin', return_value=None), \
             patch.object(cmd, '_create_placeholder_security', return_value={'security_name': 'PLACEHOLDER'}):
            result = cmd._build_security_cache(['US0378331005'], dry_run=False)
        assert result['US0378331005']['security_name'] == 'PLACEHOLDER'

    def test_not_found_creates_mock_entry_on_dry_run(self):
        cmd = _cmd()
        with patch.object(cmd, '_find_security_by_isin', return_value=None), \
             patch.object(cmd, '_create_placeholder_security') as mock_create:
            result = cmd._build_security_cache(['US0378331005'], dry_run=True)
        mock_create.assert_not_called()
        assert result['US0378331005']['isin'] == 'US0378331005'


class TestExtractPositionData:
    def _row(self, **overrides):
        data = {
            'isin': 'US0378331005', 'quantity': 100, 'cost_unit_price': 150,
            'cost_value_local': 15000, 'market_unit_price': 160, 'market_value_local': 16000,
            'unrealized_pnl_local': 1000, 'security_currency': 'USD', 'pct_ratio': 0.5,
            'country': 'US', 'asset_class': 'EQUITY', 'listing_status': 'LISTED',
            'cost_value_base': 15000, 'market_value_base': 16000, 'unrealized_pnl_base': 1000,
            'valuation_date': None,
        }
        data.update(overrides)
        return pd.Series(data)

    def test_extracts_quantity_and_cost(self):
        cmd = _cmd()
        result = cmd._extract_position_data(self._row(), {'security_name': 'AAPL'}, 'UOIOIF', 1, 2)
        assert result['quantity'] == Decimal('100')
        assert result['average_cost'] == Decimal('150')

    def test_uses_position_id_and_version_id_passed_in(self):
        cmd = _cmd()
        result = cmd._extract_position_data(self._row(), {}, 'UOIOIF', 111, 222)
        assert result['position_id'] == 111
        assert result['version_id'] == 222

    def test_falls_back_to_isin_when_no_security_name(self):
        cmd = _cmd()
        result = cmd._extract_position_data(self._row(), {}, 'UOIOIF', 1, 2)
        assert result['security_label'] == 'US0378331005'

    def test_valuation_date_from_datetime_object(self):
        cmd = _cmd()
        from datetime import datetime
        row = self._row(valuation_date=datetime(2026, 9, 17))
        result = cmd._extract_position_data(row, {}, 'UOIOIF', 1, 2)
        assert result['valuation_date'] == '2026-09-17'

    def test_position_date_falls_back_to_today_when_no_valuation_date(self):
        cmd = _cmd()
        result = cmd._extract_position_data(self._row(valuation_date=None), {}, 'UOIOIF', 1, 2)
        assert result['position_date']  # non-empty

    def test_src_system_is_amsiceq(self):
        cmd = _cmd()
        result = cmd._extract_position_data(self._row(), {}, 'UOIOIF', 1, 2)
        assert result['src_system'] == 'AMSICEQ'

    def test_portfolio_currency_is_usd(self):
        cmd = _cmd()
        result = cmd._extract_position_data(self._row(), {}, 'UOIOIF', 1, 2)
        assert result['portfolio_currency'] == 'USD'


class TestUploadPosition:
    def _row(self, **overrides):
        data = {'isin': 'US0378331005', 'portfolio_code': 'UOIOIF', 'quantity': 100}
        data.update(overrides)
        return pd.Series(data)

    def test_missing_isin_is_skipped(self):
        cmd = _cmd()
        result = cmd._upload_position(self._row(isin=''), {}, dry_run=False, row_num=1, total_rows=1)
        assert result == 'skipped'

    def test_missing_portfolio_code_is_skipped(self):
        cmd = _cmd()
        result = cmd._upload_position(self._row(portfolio_code=''), {}, dry_run=False, row_num=1, total_rows=1)
        assert result == 'skipped'

    def test_dry_run_returns_success_without_writing(self):
        cmd = _cmd()
        with patch.object(cmd, '_insert_position') as mock_insert:
            result = cmd._upload_position(self._row(), {}, dry_run=True, row_num=1, total_rows=1)
        assert result == 'success'
        mock_insert.assert_not_called()

    def test_successful_insert_returns_success(self):
        cmd = _cmd()
        with patch.object(cmd, '_insert_position', return_value=True), \
             patch.object(cmd, '_insert_position_history', return_value=True):
            result = cmd._upload_position(self._row(), {}, dry_run=False, row_num=1, total_rows=1)
        assert result == 'success'

    def test_position_insert_failure_returns_error(self):
        cmd = _cmd()
        with patch.object(cmd, '_insert_position', return_value=False):
            result = cmd._upload_position(self._row(), {}, dry_run=False, row_num=1, total_rows=1)
        assert result == 'error'

    def test_history_insert_failure_still_returns_success(self, capsys):
        cmd = _cmd()
        with patch.object(cmd, '_insert_position', return_value=True), \
             patch.object(cmd, '_insert_position_history', return_value=False):
            result = cmd._upload_position(self._row(), {}, dry_run=False, row_num=1, total_rows=1)
        assert result == 'success'
        assert 'history insert failed' in capsys.readouterr().err


class TestInsertPosition:
    def _data(self, **overrides):
        data = {
            'version_id': 1, 'position_id': 2, 'position_date': '2026-09-17',
            'portfolio_short_name': 'UOIOIF', 'security_label': 'AAPL',
            'quantity': Decimal('100'), 'average_cost': Decimal('150'), 'total_cost': Decimal('15000'),
            'realized_pnl': Decimal('0'), 'current_price': Decimal('160'), 'market_value': Decimal('16000'),
            'unrealized_pnl': Decimal('1000'), 'trade_id': 0, 'trade_type': 'INITIAL_LOAD',
            'status': 'OPEN', 'is_active': True, 'created_by': 'AMSICEQ_UPLOAD', 'created_at': '2026-09-17 10:00:00',
            'src_system': 'AMSICEQ', 'security_currency': 'USD', 'portfolio_currency': 'USD',
            'pct_ratio': None, 'isin': 'US0378331005', 'country': None, 'asset_class': None,
            'listing_status': None, 'cost_value_local': None, 'cost_value_base': None,
            'market_value_local': None, 'market_value_base': None, 'unrealized_pnl_local': None,
            'unrealized_pnl_base': None, 'valuation_date': None, 'market_unit_price': None,
        }
        data.update(overrides)
        return data

    def test_retires_prior_latest_before_insert(self):
        cmd = _cmd()
        with patch.object(cmd, '_retire_prior_latest') as mock_retire, \
             patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            cmd._insert_position(self._data())
        mock_retire.assert_called_once_with('UOIOIF', 'AAPL', '2026-09-17')

    def test_returns_true_on_success(self):
        cmd = _cmd()
        with patch.object(cmd, '_retire_prior_latest'), \
             patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert cmd._insert_position(self._data()) is True

    def test_sets_is_latest_true(self):
        cmd = _cmd()
        with patch.object(cmd, '_retire_prior_latest'), \
             patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            cmd._insert_position(self._data())
        sql = mock_mgr.execute_write.call_args[0][0]
        assert ', true,' in sql or 'true' in sql

    def test_returns_false_on_exception(self):
        cmd = _cmd()
        with patch.object(cmd, '_retire_prior_latest'), \
             patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert cmd._insert_position(self._data()) is False


class TestRetirePriorLatest:
    def test_calls_execute_write_with_update(self):
        cmd = _cmd()
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            cmd._retire_prior_latest('UOIOIF', 'AAPL', '2026-09-17')
        sql = mock_mgr.execute_write.call_args[0][0]
        assert 'is_latest = false' in sql
        assert "'UOIOIF'" in sql

    def test_swallows_exception(self):
        cmd = _cmd()
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            cmd._retire_prior_latest('UOIOIF', 'AAPL', '2026-09-17')  # must not raise


class TestInsertPositionHistory:
    def _data(self):
        return {
            'version_id': 1, 'position_id': 2, 'position_date': '2026-09-17',
            'portfolio_short_name': 'UOIOIF', 'security_label': 'AAPL',
            'quantity': Decimal('100'), 'average_cost': Decimal('150'), 'total_cost': Decimal('15000'),
            'realized_pnl': Decimal('0'), 'current_price': Decimal('160'), 'market_value': Decimal('16000'),
            'unrealized_pnl': Decimal('1000'), 'trade_id': 0, 'trade_type': 'INITIAL_LOAD',
            'status': 'OPEN', 'is_active': True, 'created_by': 'AMSICEQ_UPLOAD', 'created_at': '2026-09-17 10:00:00',
            'src_system': 'AMSICEQ', 'security_currency': 'USD', 'portfolio_currency': 'USD',
            'pct_ratio': None, 'isin': 'US0378331005', 'country': None, 'asset_class': None,
            'listing_status': None, 'cost_value_local': None, 'cost_value_base': None,
            'market_value_local': None, 'market_value_base': None, 'unrealized_pnl_local': None,
            'unrealized_pnl_base': None, 'valuation_date': None, 'market_unit_price': None,
        }

    def test_returns_true_on_success(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            assert _cmd()._insert_position_history(self._data()) is True

    def test_returns_false_on_exception(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            assert _cmd()._insert_position_history(self._data()) is False

    def test_change_type_is_initial_load(self):
        with patch('upload_amsiceq_positions.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            _cmd()._insert_position_history(self._data())
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'INITIAL_LOAD'" in sql


class TestLoadExcel:
    def test_returns_none_when_file_missing(self, tmp_path):
        cmd = _cmd()
        result = cmd._load_excel(str(tmp_path / 'nonexistent.xlsx'))
        assert result is None

    def test_returns_none_when_missing_required_columns(self, tmp_path):
        cmd = _cmd()
        xlsx_path = tmp_path / 'test.xlsx'
        df = pd.DataFrame({'some_other_col': [1, 2]})
        df.to_excel(xlsx_path, index=False)
        result = cmd._load_excel(str(xlsx_path))
        assert result is None

    def test_loads_valid_file_with_required_columns(self, tmp_path):
        cmd = _cmd()
        xlsx_path = tmp_path / 'test.xlsx'
        df = pd.DataFrame({'isin': ['US1'], 'portfolio_code': ['UOIOIF'], 'quantity': [100]})
        df.to_excel(xlsx_path, index=False)
        result = cmd._load_excel(str(xlsx_path))
        assert result is not None
        assert len(result) == 1

    def test_maps_column_aliases_case_insensitively(self, tmp_path):
        cmd = _cmd()
        xlsx_path = tmp_path / 'test.xlsx'
        df = pd.DataFrame({
            'ISIN': ['US1'], 'Portfolio_Code_Repeated': ['UOIOIF'], 'quantity': [100],
        })
        df.to_excel(xlsx_path, index=False)
        result = cmd._load_excel(str(xlsx_path))
        assert result is not None
        assert 'portfolio_code' in result.columns


class TestHandle:
    def test_load_excel_failure_returns_early(self, capsys):
        cmd = _cmd()
        with patch.object(cmd, '_load_excel', return_value=None):
            cmd.handle(file='x.xlsx', dry_run=False, skip_portfolios=True, skip_securities=True)
        assert 'Failed to load Excel file' in capsys.readouterr().err

    def test_load_excel_exception_returns_early(self, capsys):
        cmd = _cmd()
        with patch.object(cmd, '_load_excel', side_effect=RuntimeError('boom')):
            cmd.handle(file='x.xlsx', dry_run=False, skip_portfolios=True, skip_securities=True)
        assert 'Error loading Excel file' in capsys.readouterr().err

    def test_successful_run_shows_summary(self, capsys):
        cmd = _cmd()
        df = pd.DataFrame({
            'isin': ['US1'], 'portfolio_code': ['UOIOIF'], 'quantity': [100],
        })
        with patch.object(cmd, '_load_excel', return_value=df), \
             patch.object(cmd, '_upload_position', return_value='success'):
            cmd.handle(file='x.xlsx', dry_run=False, skip_portfolios=True, skip_securities=True)
        out = capsys.readouterr().out
        assert 'Successful: 1' in out

    def test_skip_portfolios_true_skips_ensure_call(self):
        cmd = _cmd()
        df = pd.DataFrame({'isin': ['US1'], 'portfolio_code': ['UOIOIF'], 'quantity': [100]})
        with patch.object(cmd, '_load_excel', return_value=df), \
             patch.object(cmd, '_ensure_portfolios_exist') as mock_ensure, \
             patch.object(cmd, '_upload_position', return_value='success'):
            cmd.handle(file='x.xlsx', dry_run=False, skip_portfolios=True, skip_securities=True)
        mock_ensure.assert_not_called()

    def test_skip_securities_true_skips_cache_build(self):
        cmd = _cmd()
        df = pd.DataFrame({'isin': ['US1'], 'portfolio_code': ['UOIOIF'], 'quantity': [100]})
        with patch.object(cmd, '_load_excel', return_value=df), \
             patch.object(cmd, '_build_security_cache') as mock_cache, \
             patch.object(cmd, '_upload_position', return_value='success'):
            cmd.handle(file='x.xlsx', dry_run=False, skip_portfolios=True, skip_securities=True)
        mock_cache.assert_not_called()

    def test_per_row_exception_counted_as_error(self, capsys):
        cmd = _cmd()
        df = pd.DataFrame({'isin': ['US1'], 'portfolio_code': ['UOIOIF'], 'quantity': [100]})
        with patch.object(cmd, '_load_excel', return_value=df), \
             patch.object(cmd, '_upload_position', side_effect=RuntimeError('boom')):
            cmd.handle(file='x.xlsx', dry_run=False, skip_portfolios=True, skip_securities=True)
        out = capsys.readouterr().out
        assert 'Errors: 1' in out

    def test_dry_run_prints_dry_run_banner(self, capsys):
        cmd = _cmd()
        df = pd.DataFrame({'isin': ['US1'], 'portfolio_code': ['UOIOIF'], 'quantity': [100]})
        with patch.object(cmd, '_load_excel', return_value=df), \
             patch.object(cmd, '_upload_position', return_value='success'):
            cmd.handle(file='x.xlsx', dry_run=True, skip_portfolios=True, skip_securities=True)
        assert 'DRY RUN MODE' in capsys.readouterr().out
