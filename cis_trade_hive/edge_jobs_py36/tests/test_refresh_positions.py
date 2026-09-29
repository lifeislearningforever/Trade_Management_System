"""Tests for edge_jobs_py36/refresh_positions.py."""
from datetime import datetime, date
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from refresh_positions import Command


@pytest.fixture
def cmd():
    return Command()


@pytest.fixture
def impala():
    with patch('refresh_positions.impala_manager') as m:
        m.execute_write.return_value = True
        m.execute_query.return_value = []
        yield m


class TestEscape:
    def test_none(self, cmd):
        assert cmd._escape(None) == ''

    def test_quote_and_backslash(self, cmd):
        assert cmd._escape("O'Brien\\x") == "O\\'Brien\\\\x"


class TestAddArguments:
    def test_defaults(self, cmd):
        import argparse
        parser = argparse.ArgumentParser()
        cmd.add_arguments(parser)
        args = parser.parse_args([])
        assert args.run_type == 'EOD'
        assert args.fill_gaps is False
        assert args.ams_no_reval is False

    def test_custom_args(self, cmd):
        import argparse
        parser = argparse.ArgumentParser()
        cmd.add_arguments(parser)
        args = parser.parse_args([
            '--portfolio', 'P1', '--security', 'S1', '--source', 'GMP',
            '--dry-run', '--run-type', 'CORR', '--position-date', '2026-01-01',
            '--fill-gaps', '--ams-no-reval',
        ])
        assert args.portfolio == 'P1'
        assert args.security == 'S1'
        assert args.source == 'GMP'
        assert args.dry_run is True
        assert args.run_type == 'CORR'
        assert args.position_date == '2026-01-01'
        assert args.fill_gaps is True
        assert args.ams_no_reval is True


class TestGetDatesFromAlldatesinfo:
    def test_different_months_uses_reporting_date(self, cmd, impala):
        impala.execute_query.return_value = [
            {'contextual_today': '20260201', 'reporting_date': '20260131'}
        ]
        reporting, month_end, today = cmd._get_dates_from_alldatesinfo()
        assert reporting == '2026-01-31'
        assert month_end == '2026-01-31'
        assert today == '2026-02-01'

    def test_same_month_uses_prev_calendar_day(self, cmd, impala):
        impala.execute_query.return_value = [
            {'contextual_today': '20260115', 'reporting_date': '20260114'}
        ]
        reporting, month_end, today = cmd._get_dates_from_alldatesinfo()
        assert reporting == '2026-01-14'
        assert month_end == '2025-12-31'
        assert today == '2026-01-15'

    def test_no_rows_falls_back(self, cmd, impala):
        impala.execute_query.return_value = []
        reporting, month_end, today = cmd._get_dates_from_alldatesinfo()
        assert reporting is not None and month_end is not None and today is not None

    def test_exception_falls_back(self, cmd):
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            reporting, month_end, today = cmd._get_dates_from_alldatesinfo()
        assert reporting is not None

    def test_missing_fields_falls_back(self, cmd, impala):
        impala.execute_query.return_value = [{'contextual_today': '', 'reporting_date': ''}]
        reporting, month_end, today = cmd._get_dates_from_alldatesinfo()
        assert reporting is not None


class TestGetOpenPositions:
    def test_basic_query(self, cmd, impala):
        impala.execute_query.return_value = [{'position_id': 1}]
        result = cmd._get_open_positions(None, ['CIS'], '2026-01-01', None)
        assert result == [{'position_id': 1}]

    def test_portfolio_and_security_filters(self, cmd, impala):
        cmd._get_open_positions('P1', ['CIS'], '2026-01-01', 'S1')
        query = impala.execute_query.call_args[0][0]
        assert "portfolio = 'P1'" in query
        assert "security_label = 'S1'" in query

    def test_fill_gaps_adds_join(self, cmd, impala):
        cmd._get_open_positions(None, ['CIS'], '2026-01-01', None, fill_gaps=True, position_type='EOD')
        query = impala.execute_query.call_args[0][0]
        assert 'LEFT JOIN' in query
        assert "position_type = 'EOD'" in query

    def test_fill_gaps_without_position_date_no_join(self, cmd, impala):
        cmd._get_open_positions(None, ['CIS'], None, None, fill_gaps=True)
        query = impala.execute_query.call_args[0][0]
        assert 'LEFT JOIN' not in query

    def test_none_result_returns_empty_list(self, cmd, impala):
        impala.execute_query.return_value = None
        assert cmd._get_open_positions(None, ['CIS'], None, None) == []

    def test_exception_reraises(self, cmd):
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            with pytest.raises(RuntimeError):
                cmd._get_open_positions(None, ['CIS'], None, None)


class TestLoadReferenceData:
    def test_empty_positions_returns_empty_ref(self, cmd):
        ref = cmd._load_reference_data([])
        assert ref['sec_ccy'] == {}
        assert ref['prices'] == {}

    def test_loads_security_currency_and_portfolio_info(self, cmd, impala):
        impala.execute_query.side_effect = [
            [{'security_name': 'SEC1', 'currency_code': 'USD'}],
            [{'name': 'P1', 'currency': 'SGD', 'revaluation_status': 'REVALUED',
              'investment_type': 'SUBSIDIARY CO', 'accounting_section': 'ABC'}],
            [{'security_label': 'SEC1', 'main_closing_price': 100.5}],
            [{'iso_code': 'USD', 'precision': '0000000000.01'}, {'iso_code': 'SGD', 'precision': '0000000000.01'}],
        ]
        with patch('refresh_positions.multicurrency_service') as mc:
            mc.get_fx_rates_batch.return_value = {'USD-SGD': (Decimal('1.35'), '2026-01-01')}
            ref = cmd._load_reference_data([{'security_label': 'SEC1', 'portfolio': 'P1'}])
        assert ref['sec_ccy']['SEC1'] == 'USD'
        assert ref['port_info']['P1']['currency'] == 'SGD'
        assert ref['equity_method']['P1'] is True
        assert ref['prices']['SEC1'] == Decimal('100.5')
        assert ref['fx_rates']['USD-SGD'] == Decimal('1.35')
        assert ref['currency_dp']['USD'] == 2

    def test_non_equity_method_investment_type(self, cmd, impala):
        impala.execute_query.side_effect = [
            [{'name': 'P1', 'currency': 'USD', 'revaluation_status': 'REVALUED',
              'investment_type': 'NORMAL', 'accounting_section': ''}],
            [],
        ]
        ref = cmd._load_reference_data([{'security_label': None, 'portfolio': 'P1'}])
        assert ref['equity_method']['P1'] is False

    def test_no_fx_pairs_when_same_currency(self, cmd, impala):
        impala.execute_query.side_effect = [
            [{'security_name': 'SEC1', 'currency_code': 'USD'}],
            [{'name': 'P1', 'currency': 'USD', 'revaluation_status': '', 'investment_type': '', 'accounting_section': ''}],
            [],
            [],
        ]
        ref = cmd._load_reference_data([{'security_label': 'SEC1', 'portfolio': 'P1'}])
        assert ref['fx_rates'] == {}

    def test_price_is_none_skipped(self, cmd, impala):
        impala.execute_query.side_effect = [
            [{'security_name': 'SEC1', 'currency_code': 'USD'}],
            [],
            [{'security_label': 'SEC1', 'main_closing_price': None}],
            [],
        ]
        ref = cmd._load_reference_data([{'security_label': 'SEC1', 'portfolio': 'P1'}])
        assert 'SEC1' not in ref['prices']

    def test_zero_fx_rate_skipped(self, cmd, impala):
        impala.execute_query.side_effect = [
            [{'security_name': 'SEC1', 'currency_code': 'USD'}],
            [{'name': 'P1', 'currency': 'SGD', 'revaluation_status': '', 'investment_type': '', 'accounting_section': ''}],
            [],
            [],
        ]
        with patch('refresh_positions.multicurrency_service') as mc:
            mc.get_fx_rates_batch.return_value = {'USD-SGD': (Decimal('0'), '2026-01-01')}
            ref = cmd._load_reference_data([{'security_label': 'SEC1', 'portfolio': 'P1'}])
        assert 'USD-SGD' not in ref['fx_rates']

    def test_currency_precision_no_decimal_defaults_to_2(self, cmd, impala):
        impala.execute_query.side_effect = [
            [{'security_name': 'SEC1', 'currency_code': 'USD'}],
            [],
            [{'iso_code': 'USD', 'precision': '100'}],
        ]
        ref = cmd._load_reference_data([{'security_label': 'SEC1', 'portfolio': None}])
        assert ref['currency_dp']['USD'] == 2


class TestProcessPosition:
    def base_ref(self):
        return {
            'sec_ccy': {'SEC1': 'USD'},
            'equity_method': {'P1': False},
            'port_info': {'P1': {'currency': 'SGD', 'revaluation_status': 'REVALUED', 'accounting_section': ''}},
            'prices': {'SEC1': Decimal('100')},
            'fx_rates': {'USD-SGD': Decimal('1.35')},
            'fx_rate_dates': {'USD-SGD': '2026-01-05'},
            'currency_dp': {'USD': 2, 'SGD': 2},
        }

    def base_position(self, **overrides):
        pos = {
            'position_id': 1, 'portfolio': 'P1', 'security_label': 'SEC1',
            'quantity': 100, 'cost_fc': 9000, 'cost_lc': 8000,
            'provision_fc': 0, 'provision_lc': 0,
            'average_cost_fc': 90, 'average_cost_lc': 80,
            'position_date': '2026-01-05', 'src_system': 'CIS',
            'position_basis': 'TRADED',
            'market_value_fc': 9500,
        }
        pos.update(overrides)
        return pos

    def test_none_quantity_skipped(self, cmd):
        insert_rows = []
        result = cmd._process_position(self.base_position(quantity=None), False, '2026-01-01', self.base_ref(), insert_rows)
        assert result == 'skipped'

    def test_empty_quantity_skipped(self, cmd):
        insert_rows = []
        result = cmd._process_position(self.base_position(quantity=' '), False, '2026-01-01', self.base_ref(), insert_rows)
        assert result == 'skipped'

    def test_invalid_quantity_skipped(self, cmd):
        insert_rows = []
        result = cmd._process_position(self.base_position(quantity='notanumber'), False, '2026-01-01', self.base_ref(), insert_rows)
        assert result == 'skipped'

    def test_ams_no_reval_delegates(self, cmd):
        insert_rows = []
        position = self.base_position(src_system='AMS_STREET', position_basis='SETTLED')
        with patch.object(cmd, '_copy_position_unchanged', return_value='updated') as copy_mock:
            result = cmd._process_position(position, False, '2026-01-01', self.base_ref(), insert_rows, ams_no_reval=True)
        assert result == 'updated'
        copy_mock.assert_called_once()

    def test_ams_no_reval_only_applies_to_settled(self, cmd):
        insert_rows = []
        position = self.base_position(src_system='AMS_STREET', position_basis='TRADED')
        result = cmd._process_position(position, False, '2026-01-01', self.base_ref(), insert_rows, ams_no_reval=True)
        assert result == 'updated'
        assert len(insert_rows) == 1

    def test_basic_updated_with_price(self, cmd):
        insert_rows = []
        result = cmd._process_position(self.base_position(), False, '2026-01-01', self.base_ref(), insert_rows)
        assert result == 'updated'
        assert len(insert_rows) == 1
        assert insert_rows[0]['market_value_fc'] == Decimal('10000')

    def test_dry_run_no_insert_row(self, cmd):
        insert_rows = []
        result = cmd._process_position(self.base_position(), True, '2026-01-01', self.base_ref(), insert_rows)
        assert result == 'updated'
        assert insert_rows == []

    def test_no_price_int_zeroes_market_value(self, cmd):
        ref = self.base_ref()
        ref['prices'] = {}
        insert_rows = []
        result = cmd._process_position(self.base_position(), False, '2026-01-01', ref, insert_rows, run_type='INT')
        assert insert_rows[0]['market_value_fc'] == Decimal('0')

    def test_no_price_eod_keeps_existing_market_value(self, cmd):
        ref = self.base_ref()
        ref['prices'] = {}
        insert_rows = []
        result = cmd._process_position(self.base_position(), False, '2026-01-01', ref, insert_rows, run_type='EOD')
        assert insert_rows[0]['market_value_fc'] == Decimal('9500')

    def test_no_price_eod_zero_quantity_price_dec_zero(self, cmd):
        ref = self.base_ref()
        ref['prices'] = {}
        insert_rows = []
        result = cmd._process_position(self.base_position(quantity=0), False, '2026-01-01', ref, insert_rows, run_type='EOD')
        assert result == 'updated'

    def test_equity_method_zeroes_unrealized_pnl(self, cmd):
        ref = self.base_ref()
        ref['equity_method'] = {'P1': True}
        insert_rows = []
        cmd._process_position(self.base_position(), False, '2026-01-01', ref, insert_rows)
        assert insert_rows[0]['unrealized_pnl_fc'] == Decimal('0')
        assert insert_rows[0]['unrealized_pnl_lc'] == Decimal('0')

    def test_liqn_accounting_section_zeroes_unrealized_pnl(self, cmd):
        ref = self.base_ref()
        ref['port_info']['P1']['accounting_section'] = 'liqn'
        insert_rows = []
        cmd._process_position(self.base_position(), False, '2026-01-01', ref, insert_rows)
        assert insert_rows[0]['unrealized_pnl_fc'] == Decimal('0')

    def test_non_revalued_carries_forward_lc(self, cmd):
        ref = self.base_ref()
        ref['port_info']['P1']['revaluation_status'] = 'NON-REVALUED'
        insert_rows = []
        cmd._process_position(self.base_position(), False, '2026-01-01', ref, insert_rows)
        assert insert_rows[0]['cost_lc_write'] == Decimal('8000')

    def test_revalued_fx_rate_newer_than_position_date_recomputes(self, cmd):
        ref = self.base_ref()
        ref['fx_rate_dates'] = {'USD-SGD': '2026-01-10'}  # after position_date 2026-01-05
        insert_rows = []
        cmd._process_position(self.base_position(), False, '2026-01-01', ref, insert_rows)
        assert insert_rows[0]['cost_lc_write'] == round(Decimal('9000') * Decimal('1.35'), 2)

    def test_revalued_fx_rate_older_than_position_date_keeps_as_traded(self, cmd):
        ref = self.base_ref()
        ref['fx_rate_dates'] = {'USD-SGD': '2026-01-01'}  # before position_date 2026-01-05
        insert_rows = []
        cmd._process_position(self.base_position(), False, '2026-01-01', ref, insert_rows)
        assert insert_rows[0]['cost_lc_write'] == Decimal('8000')

    def test_fx_rate_date_yyyymmdd_normalized(self, cmd):
        ref = self.base_ref()
        ref['fx_rate_dates'] = {'USD-SGD': '20260110'}
        insert_rows = []
        cmd._process_position(self.base_position(), False, '2026-01-01', ref, insert_rows)
        assert insert_rows[0]['cost_lc_write'] != Decimal('8000')

    def test_ams_street_uses_currency_dp_not_avp_precision(self, cmd):
        ref = self.base_ref()
        insert_rows = []
        position = self.base_position(src_system='AMS_STREET', position_basis='TRADED')
        cmd._process_position(position, False, '2026-01-01', ref, insert_rows)
        assert insert_rows[0]['fc_dp'] == 2

    def test_non_ams_uses_avp_precision(self, cmd):
        ref = self.base_ref()
        insert_rows = []
        cmd._process_position(self.base_position(), False, '2026-01-01', ref, insert_rows)
        assert insert_rows[0]['fc_dp'] == 8


class TestCopyPositionUnchanged:
    def test_copies_values_forward_unchanged(self, cmd):
        ref = {
            'sec_ccy': {'SEC1': 'USD'},
            'port_info': {'P1': {'currency': 'SGD'}},
        }
        position = {
            'portfolio': 'P1', 'security_label': 'SEC1', 'quantity': 10,
            'market_value_fc': 1000, 'market_value_lc': 1350,
            'unrealized_pnl_fc': 100, 'unrealized_pnl_lc': 135,
            'net_book_value_fc': 900, 'net_book_value_lc': 1215,
            'average_cost_lc': 90, 'cost_lc': 900, 'provision_lc': 0,
        }
        insert_rows = []
        result = cmd._copy_position_unchanged(position, False, ref, insert_rows)
        assert result == 'updated'
        assert insert_rows[0]['market_value_fc'] == Decimal('1000')
        assert insert_rows[0]['fc_dp'] == 8

    def test_dry_run_no_insert(self, cmd):
        ref = {'sec_ccy': {}, 'port_info': {}}
        position = {'portfolio': 'P1', 'security_label': 'SEC1', 'quantity': 10, 'market_value_fc': 1000}
        insert_rows = []
        result = cmd._copy_position_unchanged(position, True, ref, insert_rows)
        assert result == 'updated'
        assert insert_rows == []

    def test_zero_quantity_price_dec_zero(self, cmd):
        ref = {'sec_ccy': {}, 'port_info': {}}
        position = {'portfolio': 'P1', 'security_label': 'SEC1', 'quantity': 0, 'market_value_fc': 0}
        insert_rows = []
        result = cmd._copy_position_unchanged(position, False, ref, insert_rows)
        assert result == 'updated'
        assert insert_rows[0]['price_dec'] == Decimal('0')


class TestBatchMarkSourceNotLatest:
    def test_marks_existing_rows_not_latest(self, cmd, impala):
        impala.execute_query.return_value = [{
            'position_id': 1, 'version_id': 2, 'portfolio': 'P1', 'security_label': 'S1',
            'position_basis': 'TRADED', 'position_date': '2026-01-01', 'src_system': 'CIS',
            'processing_date': '20260101', 'quantity': 10,
        }]
        insert_rows = [{'position': {'position_id': 1}}]
        cmd._batch_mark_source_not_latest(insert_rows)
        upsert_calls = [c for c in impala.execute_write.call_args_list if 'is_latest' in c[0][0]]
        assert len(upsert_calls) == 1
        assert 'false' in upsert_calls[0][0][0]

    def test_empty_insert_rows_no_query(self, cmd, impala):
        cmd._batch_mark_source_not_latest([])
        impala.execute_query.assert_not_called()

    def test_none_position_id_skipped(self, cmd, impala):
        insert_rows = [{'position': {'position_id': None}}]
        cmd._batch_mark_source_not_latest(insert_rows)
        impala.execute_query.assert_not_called()

    def test_with_isin_and_source_table(self, cmd, impala):
        impala.execute_query.return_value = [{
            'position_id': 1, 'version_id': 2, 'portfolio': 'P1', 'security_label': 'S1',
            'position_basis': 'TRADED', 'position_date': '2026-01-01', 'src_system': 'CIS',
            'processing_date': '20260101', 'quantity': 10, 'isin': 'ISIN1',
            'source_table': 'cis_trade_position', 'processing_timestamp': '2026-01-01 10:00:00',
        }]
        insert_rows = [{'position': {'position_id': 1}}]
        cmd._batch_mark_source_not_latest(insert_rows)
        query = impala.execute_write.call_args[0][0]
        assert 'ISIN1' in query


class TestBatchUpsertEod:
    def test_upserts_and_calls_cleanup(self, cmd, impala):
        insert_rows = [{
            'position': {
                'portfolio': 'P1', 'security_label': 'SEC1', 'position_basis': 'TRADED',
                'position_date': '2026-01-01', 'src_system': 'CIS', 'quantity': 10,
                'average_cost_fc': 90, 'cost_fc': 900,
            },
            'price_dec': Decimal('95'), 'market_value_fc': Decimal('950'), 'market_value_lc': Decimal('1000'),
            'unrealized_pnl_fc': Decimal('50'), 'unrealized_pnl_lc': Decimal('55'),
            'nbv_fc': Decimal('900'), 'nbv_lc': Decimal('950'),
            'average_cost_lc': Decimal('95'), 'cost_lc_write': Decimal('950'),
            'provision_lc_write': Decimal('0'), 'fc_dp': 2, 'lc_dp': 2,
        }]
        with patch.object(cmd, '_cleanup_stale_duplicates') as cleanup_mock:
            cmd._batch_upsert_eod(insert_rows, '2026-01-01', position_type='EOD')
        upsert_calls = [c for c in impala.execute_write.call_args_list if 'UPSERT INTO' in c[0][0]]
        assert len(upsert_calls) == 1
        cleanup_mock.assert_called_once()

    def test_carries_forward_existing_accumulator_fields(self, cmd, impala):
        impala.execute_query.return_value = [{
            'position_id': 999999999, 'dividend_fc': 55, 'dividend_lc': 60,
            'uncall_fc': 0, 'uncall_lc': 0, 'pipeline_fc': 0, 'pipeline_lc': 0,
            'realized_pnl_fc': 0, 'realized_pnl_lc': 0, 'provision_fc': 0, 'provision_lc': 0,
        }]
        insert_rows = [{
            'position': {
                'portfolio': 'P1', 'security_label': 'SEC1', 'position_basis': 'TRADED',
                'position_date': '2026-01-01', 'src_system': 'CIS', 'quantity': 10,
                'average_cost_fc': 90, 'cost_fc': 900, 'dividend_fc': 0,
            },
            'price_dec': Decimal('95'), 'market_value_fc': Decimal('950'), 'market_value_lc': Decimal('1000'),
            'unrealized_pnl_fc': Decimal('50'), 'unrealized_pnl_lc': Decimal('55'),
            'nbv_fc': Decimal('900'), 'nbv_lc': Decimal('950'),
            'average_cost_lc': Decimal('95'), 'cost_lc_write': Decimal('950'),
            'provision_lc_write': Decimal('0'), 'fc_dp': 2, 'lc_dp': 2,
        }]
        with patch.object(cmd, '_cleanup_stale_duplicates'), \
             patch('refresh_positions.position_id_service') as pid_svc:
            pid_svc.position_id.return_value = 999999999
            cmd._batch_upsert_eod(insert_rows, '2026-01-01', position_type='EOD')
        upsert_calls = [c for c in impala.execute_write.call_args_list if 'UPSERT INTO' in c[0][0]]
        assert '55' in upsert_calls[0][0][0]  # dividend_fc carried from existing

    def test_no_existing_row_uses_source_position_values(self, cmd, impala):
        impala.execute_query.return_value = []
        insert_rows = [{
            'position': {
                'portfolio': 'P1', 'security_label': 'SEC1', 'position_basis': 'TRADED',
                'position_date': '2026-01-01', 'src_system': 'CIS', 'quantity': 10,
                'average_cost_fc': 90, 'cost_fc': 900, 'isin': 'ISIN1', 'source_table': 'x',
            },
            'price_dec': Decimal('95'), 'market_value_fc': Decimal('950'), 'market_value_lc': Decimal('1000'),
            'unrealized_pnl_fc': Decimal('50'), 'unrealized_pnl_lc': Decimal('55'),
            'nbv_fc': Decimal('900'), 'nbv_lc': Decimal('950'),
            'average_cost_lc': Decimal('95'), 'cost_lc_write': Decimal('950'),
            'provision_lc_write': Decimal('0'), 'fc_dp': 2, 'lc_dp': 2,
        }]
        with patch.object(cmd, '_cleanup_stale_duplicates'):
            cmd._batch_upsert_eod(insert_rows, '2026-01-01', position_type='EOD')
        upsert_calls = [c for c in impala.execute_write.call_args_list if 'UPSERT INTO' in c[0][0]]
        assert 'ISIN1' in upsert_calls[0][0][0]

    def test_empty_insert_rows_no_upsert(self, cmd, impala):
        with patch.object(cmd, '_cleanup_stale_duplicates') as cleanup_mock:
            cmd._batch_upsert_eod([], '2026-01-01')
        impala.execute_write.assert_not_called()
        cleanup_mock.assert_called_once()


class TestCleanupStaleDuplicates:
    def test_no_pairs_no_write(self, cmd, impala):
        cmd._cleanup_stale_duplicates([], 'EOD', '2026-01-01')
        impala.execute_write.assert_not_called()

    def test_writes_update_for_stale_duplicates(self, cmd, impala, capsys):
        insert_rows = [{'position': {
            'portfolio': 'P1', 'security_label': 'SEC1', 'position_basis': 'TRADED',
            'position_date': '2026-01-01', 'src_system': 'CIS',
        }}]
        with patch('refresh_positions.position_id_service') as pid_svc:
            pid_svc.position_id.return_value = 123
            cmd._cleanup_stale_duplicates(insert_rows, 'EOD', '2026-01-01')
        update_calls = [c for c in impala.execute_write.call_args_list if 'UPDATE' in c[0][0]]
        assert len(update_calls) == 1
        assert '123' in update_calls[0][0][0]

    def test_missing_position_date_uses_run_date(self, cmd, impala):
        insert_rows = [{'position': {
            'portfolio': 'P1', 'security_label': 'SEC1', 'position_basis': 'TRADED',
            'position_date': None, 'src_system': 'CIS',
        }}]
        with patch('refresh_positions.position_id_service') as pid_svc:
            pid_svc.position_id.return_value = 123
            cmd._cleanup_stale_duplicates(insert_rows, 'EOD', '2026-01-01')
        update_calls = [c for c in impala.execute_write.call_args_list if 'UPDATE' in c[0][0]]
        assert len(update_calls) == 1


class TestInsertEodPosition:
    def test_success(self, cmd, impala):
        position = {'portfolio': 'P1', 'security_label': 'S1', 'position_basis': 'TRADED', 'quantity': 10}
        result = cmd._insert_eod_position(
            position, Decimal('100'),
            Decimal('1000'), Decimal('1350'), Decimal('50'), Decimal('67'),
            Decimal('950'), Decimal('1283'), Decimal('95'), Decimal('950'),
            run_date='2026-01-01',
        )
        assert result is True

    def test_with_isin(self, cmd, impala):
        position = {'portfolio': 'P1', 'security_label': 'S1', 'position_basis': 'TRADED', 'quantity': 10, 'isin': 'ISIN1', 'source_table': 'x'}
        cmd._insert_eod_position(
            position, Decimal('100'),
            Decimal('1000'), Decimal('1350'), Decimal('50'), Decimal('67'),
            Decimal('950'), Decimal('1283'), Decimal('95'), Decimal('950'),
            run_date='2026-01-01',
        )
        insert_call = [c for c in impala.execute_write.call_args_list if 'INSERT INTO' in c[0][0]]
        assert 'ISIN1' in insert_call[0][0][0]

    def test_exception_returns_false(self, cmd):
        with patch('refresh_positions.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            position = {'portfolio': 'P1', 'security_label': 'S1', 'position_basis': 'TRADED', 'quantity': 10}
            result = cmd._insert_eod_position(
                position, Decimal('100'),
                Decimal('1000'), Decimal('1350'), Decimal('50'), Decimal('67'),
                Decimal('950'), Decimal('1283'), Decimal('95'), Decimal('950'),
                run_date='2026-01-01',
            )
        assert result is False

    def test_uses_current_date_when_run_date_none(self, cmd, impala):
        position = {'portfolio': 'P1', 'security_label': 'S1', 'position_basis': 'TRADED', 'quantity': 10}
        result = cmd._insert_eod_position(
            position, Decimal('100'),
            Decimal('1000'), Decimal('1350'), Decimal('50'), Decimal('67'),
            Decimal('950'), Decimal('1283'), Decimal('95'), Decimal('950'),
        )
        assert result is True


class TestPublishPositionRep:
    def test_returns_count(self, cmd, impala):
        impala.execute_query.return_value = [{'cnt': 5}]
        result = cmd._publish_position_rep('2026-01-01', ['CIS'])
        assert result == 5

    def test_no_count_result_returns_zero(self, cmd, impala):
        impala.execute_query.return_value = None
        result = cmd._publish_position_rep('2026-01-01', ['CIS'])
        assert result == 0

    def test_null_count_returns_zero(self, cmd, impala):
        impala.execute_query.return_value = [{'cnt': None}]
        result = cmd._publish_position_rep('2026-01-01', ['CIS'])
        assert result == 0


class TestGetLatestPrice:
    def test_returns_price(self, cmd, impala):
        impala.execute_query.return_value = [{'main_closing_price': 100.5}]
        assert cmd._get_latest_price('SEC1') == Decimal('100.5')

    def test_no_result_returns_none(self, cmd, impala):
        impala.execute_query.return_value = []
        assert cmd._get_latest_price('SEC1') is None

    def test_exception_returns_none(self, cmd):
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert cmd._get_latest_price('SEC1') is None


class TestGetSecurityCurrency:
    def test_returns_currency(self, cmd, impala):
        impala.execute_query.return_value = [{'currency_code': 'USD'}]
        assert cmd._get_security_currency('SEC1') == 'USD'

    def test_no_result_returns_none(self, cmd, impala):
        impala.execute_query.return_value = []
        assert cmd._get_security_currency('SEC1') is None

    def test_exception_returns_none(self, cmd):
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert cmd._get_security_currency('SEC1') is None


class TestGetPortfolioInfo:
    def test_returns_row(self, cmd, impala):
        impala.execute_query.return_value = [{'currency': 'SGD', 'revaluation_status': 'REVALUED'}]
        assert cmd._get_portfolio_info('P1') == {'currency': 'SGD', 'revaluation_status': 'REVALUED'}

    def test_no_result_returns_empty_dict(self, cmd, impala):
        impala.execute_query.return_value = []
        assert cmd._get_portfolio_info('P1') == {}

    def test_exception_returns_empty_dict(self, cmd):
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert cmd._get_portfolio_info('P1') == {}


class TestGetFxRate:
    def test_same_currency_returns_one(self, cmd):
        assert cmd._get_fx_rate('USD', 'USD') == Decimal('1')

    def test_missing_currency_returns_one(self, cmd):
        assert cmd._get_fx_rate(None, 'USD') == Decimal('1')

    def test_returns_rate(self, cmd, impala):
        impala.execute_query.return_value = [{'spot_rate_d': 1.35}]
        assert cmd._get_fx_rate('USD', 'SGD') == Decimal('1.35')

    def test_no_result_returns_one(self, cmd, impala):
        impala.execute_query.return_value = []
        assert cmd._get_fx_rate('USD', 'SGD') == Decimal('1')

    def test_exception_returns_one(self, cmd):
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert cmd._get_fx_rate('USD', 'SGD') == Decimal('1')


class TestGetCurrencyDp:
    def test_empty_currency_returns_default(self, cmd):
        assert cmd._get_currency_dp('') == 2

    def test_returns_parsed_precision(self, cmd, impala):
        impala.execute_query.return_value = [{'precision': '0000000000.01'}]
        assert cmd._get_currency_dp('USD') == 2

    def test_no_result_returns_default(self, cmd, impala):
        impala.execute_query.return_value = []
        assert cmd._get_currency_dp('XYZ') == 2

    def test_exception_returns_default(self, cmd):
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert cmd._get_currency_dp('USD') == 2


class TestIsEquityMethodSecurity:
    def test_assoc_returns_true(self, cmd, impala):
        impala.execute_query.return_value = [{'security_investment': 'ASSOC'}]
        assert cmd._is_equity_method_security('SEC1') is True

    def test_subsi_returns_true(self, cmd, impala):
        impala.execute_query.return_value = [{'security_investment': 'SUBSI'}]
        assert cmd._is_equity_method_security('SEC1') is True

    def test_other_returns_false(self, cmd, impala):
        impala.execute_query.return_value = [{'security_investment': 'NORMAL'}]
        assert cmd._is_equity_method_security('SEC1') is False

    def test_no_result_returns_false(self, cmd, impala):
        impala.execute_query.return_value = []
        assert cmd._is_equity_method_security('SEC1') is False

    def test_exception_returns_false(self, cmd):
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert cmd._is_equity_method_security('SEC1') is False


class TestHandle:
    def make_options(self, **overrides):
        opts = {
            'portfolio': None, 'security': None, 'source': None, 'dry_run': False,
            'run_type': 'EOD', 'position_date': '2026-01-01', 'fill_gaps': False,
            'ams_no_reval': False,
        }
        opts.update(overrides)
        return opts

    def test_no_positions_found(self, capsys):
        cmd = Command()
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.return_value = []
            cmd.handle(**self.make_options())
        out = capsys.readouterr().out
        assert 'No positions found' in out

    def test_successful_run_writes_and_publishes(self, capsys):
        cmd = Command()
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = [
                [{
                    'position_id': 1, 'portfolio': 'P1', 'security_label': 'SEC1',
                    'quantity': 10, 'cost_fc': 900, 'cost_lc': 950,
                    'provision_fc': 0, 'provision_lc': 0, 'average_cost_fc': 90, 'average_cost_lc': 95,
                    'position_date': '2026-01-01', 'src_system': 'CIS', 'position_basis': 'TRADED',
                    'market_value_fc': 950,
                }],  # _get_open_positions
                [], [], [], [],  # _load_reference_data (securities, portfolios, prices, currency)
                [],  # existing accumulator fetch in _batch_upsert_eod
                [{
                    'position_id': 1, 'version_id': 2, 'portfolio': 'P1', 'security_label': 'SEC1',
                    'position_basis': 'TRADED', 'position_date': '2026-01-01', 'src_system': 'CIS',
                    'processing_date': '20260101', 'quantity': 10,
                }],  # _batch_mark_source_not_latest existing fetch
                [{'cnt': 1}],  # _publish_position_rep count
            ]
            m.execute_write.return_value = True
            cmd.handle(**self.make_options())
        out = capsys.readouterr().out
        assert 'revaluation completed' in out

    def test_dry_run_skips_writes(self, capsys):
        cmd = Command()
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = [
                [{
                    'position_id': 1, 'portfolio': 'P1', 'security_label': 'SEC1',
                    'quantity': 10, 'cost_fc': 900, 'cost_lc': 950,
                    'provision_fc': 0, 'provision_lc': 0, 'average_cost_fc': 90, 'average_cost_lc': 95,
                    'position_date': '2026-01-01', 'src_system': 'CIS', 'position_basis': 'TRADED',
                    'market_value_fc': 950,
                }],
                [], [], [], [],
            ]
            cmd.handle(**self.make_options(dry_run=True))
        m.execute_write.assert_not_called()
        out = capsys.readouterr().out
        assert 'DRY RUN' in out

    def test_position_processing_exception_counted_as_error(self, capsys):
        cmd = Command()
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = [
                [{
                    'position_id': 1, 'portfolio': 'P1', 'security_label': 'SEC1',
                    'quantity': 10, 'cost_fc': 900, 'cost_lc': 950,
                    'provision_fc': 0, 'provision_lc': 0, 'average_cost_fc': 90, 'average_cost_lc': 95,
                    'position_date': '2026-01-01', 'src_system': 'CIS', 'position_basis': 'TRADED',
                    'market_value_fc': 950,
                }],
                [], [], [], [],
            ]
            with patch.object(cmd, '_process_position', side_effect=RuntimeError('boom')):
                cmd.handle(**self.make_options())
        out = capsys.readouterr().out
        assert 'Errors          : 1' in out

    def test_skipped_position_counted(self, capsys):
        cmd = Command()
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = [
                [{
                    'position_id': 1, 'portfolio': 'P1', 'security_label': 'SEC1',
                    'quantity': None,
                }],
                [], [], [], [],
            ]
            cmd.handle(**self.make_options(dry_run=True))
        out = capsys.readouterr().out
        assert 'Skipped         : 1' in out

    def test_corr_run_type_no_publish(self, capsys):
        cmd = Command()
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = [
                [{
                    'position_id': 1, 'portfolio': 'P1', 'security_label': 'SEC1',
                    'quantity': 10, 'cost_fc': 900, 'cost_lc': 950,
                    'provision_fc': 0, 'provision_lc': 0, 'average_cost_fc': 90, 'average_cost_lc': 95,
                    'position_date': '2026-01-01', 'src_system': 'CIS', 'position_basis': 'TRADED',
                    'market_value_fc': 950,
                }],
                [], [], [], [],
                [],
                [{
                    'position_id': 1, 'version_id': 2, 'portfolio': 'P1', 'security_label': 'SEC1',
                    'position_basis': 'TRADED', 'position_date': '2026-01-01', 'src_system': 'CIS',
                    'processing_date': '20260101', 'quantity': 10,
                }],
            ]
            m.execute_write.return_value = True
            cmd.handle(**self.make_options(run_type='CORR'))
        out = capsys.readouterr().out
        assert 'cis_position_rep' not in out

    def test_int_run_type_infers_position_date(self, capsys):
        cmd = Command()
        with patch.object(cmd, '_get_dates_from_alldatesinfo', return_value=('2026-01-05', '2025-12-31', '2026-01-10')):
            with patch('refresh_positions.impala_manager') as m:
                m.execute_query.return_value = []
                cmd.handle(**self.make_options(position_date=None, run_type='INT'))
        out = capsys.readouterr().out
        assert '2026-01-10' in out

    def test_corr_run_type_infers_last_month_end(self, capsys):
        cmd = Command()
        with patch.object(cmd, '_get_dates_from_alldatesinfo', return_value=('2026-01-05', '2025-12-31', '2026-01-10')):
            with patch('refresh_positions.impala_manager') as m:
                m.execute_query.return_value = []
                cmd.handle(**self.make_options(position_date=None, run_type='CORR'))
        out = capsys.readouterr().out
        assert '2025-12-31' in out

    def test_fill_gaps_and_ams_no_reval_flags_printed(self, capsys):
        cmd = Command()
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.return_value = []
            cmd.handle(**self.make_options(fill_gaps=True, ams_no_reval=True))
        out = capsys.readouterr().out
        assert 'Fill-gaps' in out
        assert 'AMS no-reval' in out

    def test_portfolio_and_security_filters_printed(self, capsys):
        cmd = Command()
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.return_value = []
            cmd.handle(**self.make_options(portfolio='P1', security='S1'))
        out = capsys.readouterr().out
        assert 'Portfolio  : P1' in out
        assert 'Security   : S1' in out

    def test_source_filter_restricts_sources_list(self, capsys):
        cmd = Command()
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.return_value = []
            cmd.handle(**self.make_options(source='GMP'))
        out = capsys.readouterr().out
        assert 'Sources    : GMP' in out

    def test_fatal_error_reraised(self, capsys):
        cmd = Command()
        with patch.object(cmd, '_get_open_positions', side_effect=RuntimeError('fatal boom')):
            with pytest.raises(RuntimeError):
                cmd.handle(**self.make_options())
        out = capsys.readouterr().err
        assert 'Fatal error' in out

    def test_progress_message_printed_at_200_increments(self, capsys):
        cmd = Command()
        positions = [{
            'position_id': i, 'portfolio': 'P1', 'security_label': 'SEC1',
            'quantity': 10, 'cost_fc': 900, 'cost_lc': 950,
            'provision_fc': 0, 'provision_lc': 0, 'average_cost_fc': 90, 'average_cost_lc': 95,
            'position_date': '2026-01-01', 'src_system': 'CIS', 'position_basis': 'TRADED',
            'market_value_fc': 950,
        } for i in range(1, 201)]
        with patch('refresh_positions.impala_manager') as m:
            m.execute_query.side_effect = [positions, [], [], [], []]
            cmd.handle(**self.make_options(dry_run=True))
        out = capsys.readouterr().out
        assert 'Processing 200/200' in out
