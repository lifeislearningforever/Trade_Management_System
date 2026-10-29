"""Tests for edge_jobs_py36/process_approved_cashflows.py."""
import sys
import types
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from process_approved_cashflows import Command, _escape, _sign


@pytest.fixture
def cmd():
    c = Command()
    return c


@pytest.fixture
def impala():
    with patch('process_approved_cashflows.impala_manager') as m:
        m.execute_write.return_value = True
        m.execute_query.return_value = []
        yield m


@pytest.fixture
def fake_position_service():
    """Inject fake trade.services.position_service for the inline import in _reduce_avp."""
    mock_svc = MagicMock()
    mock_svc._get_portfolio_revaluation_status.return_value = 'NON-REVALUED'
    mock_svc._is_equity_method_portfolio.return_value = False
    mock_svc._get_fx_rate.return_value = Decimal('1.5')
    fake_module = types.ModuleType('trade.services.position_service')
    fake_module.position_service = mock_svc
    with patch.dict(sys.modules, {'trade.services.position_service': fake_module}):
        yield mock_svc


class TestEscape:
    def test_none(self):
        assert _escape(None) == ''

    def test_quote_and_backslash(self):
        assert _escape("O'Brien\\x") == "O\\'Brien\\\\x"


class TestSign:
    def test_send_is_positive(self):
        assert _sign('SEND', 'CF1') == Decimal('1')

    def test_increase_is_positive(self):
        assert _sign('INCREASE', 'CF1') == Decimal('1')

    def test_receive_is_negative(self):
        assert _sign('RECEIVE', 'CF1') == Decimal('-1')

    def test_decrease_is_negative(self):
        assert _sign('DECREASE', 'CF1') == Decimal('-1')

    def test_none_defaults_positive(self):
        assert _sign(None, 'CF1') == Decimal('1')

    def test_unrecognised_defaults_positive(self):
        assert _sign('WHATEVER', 'CF1') == Decimal('1')

    def test_case_insensitive(self):
        assert _sign('send', 'CF1') == Decimal('1')
        assert _sign(' receive ', 'CF1') == Decimal('-1')


class TestAddArguments:
    def test_defaults(self, cmd):
        import argparse
        parser = argparse.ArgumentParser()
        cmd.add_arguments(parser)
        args = parser.parse_args([])
        assert args.dry_run is False
        assert args.portfolio is None
        assert args.reprocess is False
        assert args.run_type == 'EOD'
        assert args.position_date is None

    def test_custom_args(self, cmd):
        import argparse
        parser = argparse.ArgumentParser()
        cmd.add_arguments(parser)
        args = parser.parse_args([
            '--dry-run', '--portfolio', 'P1', '--reprocess',
            '--run-type', 'CORR', '--position-date', '2026-01-01',
        ])
        assert args.dry_run is True
        assert args.portfolio == 'P1'
        assert args.reprocess is True
        assert args.run_type == 'CORR'
        assert args.position_date == '2026-01-01'


class TestGetDatesFromAlldatesinfo:
    def test_different_months_uses_reporting_date(self, cmd, impala):
        impala.execute_query.return_value = [
            {'contextual_today': '20260201', 'reporting_date': '20260131'}
        ]
        reporting, month_end = cmd._get_dates_from_alldatesinfo()
        assert reporting == '2026-01-31'
        assert month_end == '2026-01-31'

    def test_same_month_uses_prev_calendar_day(self, cmd, impala):
        impala.execute_query.return_value = [
            {'contextual_today': '20260115', 'reporting_date': '20260114'}
        ]
        reporting, month_end = cmd._get_dates_from_alldatesinfo()
        assert reporting == '2026-01-14'
        assert month_end == '2025-12-31'

    def test_no_rows_falls_back(self, cmd, impala):
        impala.execute_query.return_value = []
        reporting, month_end = cmd._get_dates_from_alldatesinfo()
        assert reporting is not None
        assert month_end is not None

    def test_exception_falls_back(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            reporting, month_end = cmd._get_dates_from_alldatesinfo()
        assert reporting is not None
        assert month_end is not None

    def test_missing_ct_or_rd_falls_back(self, cmd, impala):
        impala.execute_query.return_value = [{'contextual_today': '', 'reporting_date': ''}]
        reporting, month_end = cmd._get_dates_from_alldatesinfo()
        assert reporting is not None


class TestGetApprovedCashFlows:
    def test_basic_query(self, cmd, impala):
        impala.execute_query.return_value = [{'cash_flow_id': 1}]
        result = cmd._get_approved_cash_flows('2026-01-01', None, False)
        assert result == [{'cash_flow_id': 1}]
        query = impala.execute_query.call_args[0][0]
        assert "cf_processed" in query

    def test_reprocess_skips_cf_processed_filter(self, cmd, impala):
        cmd._get_approved_cash_flows('2026-01-01', None, True)
        query = impala.execute_query.call_args[0][0]
        assert 'cf_processed' not in query

    def test_portfolio_filter_applied(self, cmd, impala):
        cmd._get_approved_cash_flows('2026-01-01', 'PF1', False)
        query = impala.execute_query.call_args[0][0]
        assert "portfolio_short_name = 'PF1'" in query

    def test_none_results_returns_empty_list(self, cmd, impala):
        impala.execute_query.return_value = None
        assert cmd._get_approved_cash_flows('2026-01-01', None, False) == []


class TestGetSecurityCurrency:
    def test_returns_currency(self, cmd, impala):
        impala.execute_query.return_value = [{'currency_code': 'USD'}]
        assert cmd._get_security_currency('SEC1') == 'USD'

    def test_no_result_returns_empty(self, cmd, impala):
        impala.execute_query.return_value = []
        assert cmd._get_security_currency('SEC1') == ''

    def test_exception_returns_empty(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert cmd._get_security_currency('SEC1') == ''


class TestGetPortfolioCurrency:
    def test_returns_currency(self, cmd, impala):
        impala.execute_query.return_value = [{'currency': 'SGD'}]
        assert cmd._get_portfolio_currency('P1') == 'SGD'

    def test_no_result_returns_empty(self, cmd, impala):
        impala.execute_query.return_value = []
        assert cmd._get_portfolio_currency('P1') == ''

    def test_exception_returns_empty(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert cmd._get_portfolio_currency('P1') == ''


class TestGetCurrencyDp:
    def test_empty_currency_returns_default(self, cmd):
        assert cmd._get_currency_dp('') == 2

    def test_returns_parsed_precision(self, cmd, impala):
        impala.execute_query.return_value = [{'precision': '0000000000.01'}]
        assert cmd._get_currency_dp('USD') == 2

    def test_no_result_returns_default(self, cmd, impala):
        impala.execute_query.return_value = []
        assert cmd._get_currency_dp('XYZ') == 2

    def test_no_decimal_point_returns_default(self, cmd, impala):
        impala.execute_query.return_value = [{'precision': '100'}]
        assert cmd._get_currency_dp('XYZ') == 2

    def test_exception_returns_default(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert cmd._get_currency_dp('USD') == 2


class TestBuildSeedPosition:
    def test_builds_zero_quantity_settled_position(self, cmd, impala):
        with patch('process_approved_cashflows.multicurrency_service') as mc:
            mc.get_fx_rate.return_value = (Decimal('1.2'), 'source')
            pos = cmd._build_seed_position('P1', 'S1', '2026-01-01')
        assert pos['quantity'] == 0
        assert pos['position_basis'] == 'SETTLED'
        assert pos['is_latest'] is True
        assert pos['fx_rate'] == 1.2

    def test_fx_rate_lookup_failure_defaults_to_one(self, cmd):
        with patch('process_approved_cashflows.multicurrency_service') as mc:
            mc.get_fx_rate.side_effect = RuntimeError('boom')
            pos = cmd._build_seed_position('P1', 'S1', '2026-01-01')
        assert pos['fx_rate'] == 1.0


class TestGetCurrentPositions:
    def test_finds_ledger_position(self, cmd, impala):
        impala.execute_query.return_value = [{'position_id': 1, 'version_id': 2}]
        result = cmd._get_current_positions('P1', 'S1')
        assert len(result) == 1
        assert result[0][1] == 'CIS'
        assert result[0][0]['_from_ledger'] is True

    def test_falls_back_to_golden_copy(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = [[], [{'position_id': 5, 'src_system': 'GMP', 'quantity': 10}]]
            result = cmd._get_current_positions('P1', 'S1')
        assert len(result) == 1
        assert result[0][1] == 'GMP'
        assert result[0][0]['_from_ledger'] is False

    def test_no_positions_found_returns_empty(self, cmd, impala):
        impala.execute_query.return_value = []
        assert cmd._get_current_positions('P1', 'S1') == []

    def test_include_traded_fetches_both_bases(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = [
                [{'position_id': 1, 'position_basis': 'SETTLED'}],
                [{'position_id': 2, 'position_basis': 'TRADED'}],
            ]
            result = cmd._get_current_positions('P1', 'S1', include_traded=True)
        assert len(result) == 2

    def test_position_date_filter_applied(self, cmd, impala):
        impala.execute_query.return_value = [{'position_id': 1}]
        cmd._get_current_positions('P1', 'S1', position_date='2026-01-01')
        query = impala.execute_query.call_args[0][0]
        assert "position_date = '2026-01-01'" in query

    def test_ledger_query_exception_falls_through_to_golden(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = [RuntimeError('boom'), [{'position_id': 9, 'src_system': 'AMS'}]]
            result = cmd._get_current_positions('P1', 'S1')
        assert result[0][1] == 'AMS'

    def test_golden_query_exception_returns_empty(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = [[], RuntimeError('boom')]
            result = cmd._get_current_positions('P1', 'S1')
        assert result == []

    def test_include_traded_partial_ledger_falls_back_for_missing_basis(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            # SETTLED found in ledger, TRADED not found in ledger -> fallback to golden for TRADED
            m.execute_query.side_effect = [
                [{'position_id': 1, 'position_basis': 'SETTLED'}],  # ledger SETTLED
                [],  # ledger TRADED
                [{'position_id': 2, 'src_system': 'GMP', 'position_basis': 'TRADED'}],  # golden TRADED
            ]
            result = cmd._get_current_positions('P1', 'S1', include_traded=True)
        assert len(result) == 2
        bases = {r[0].get('position_basis') for r in result}
        assert bases == {'SETTLED', 'TRADED'}


class TestAccumulateField:
    def test_dry_run_no_write(self, cmd, impala):
        position = {'uncall_fc': 10, 'uncall_lc': 8}
        ok, msg = cmd._accumulate_field(
            position, 'P1', 'S1', '2026-01-01',
            fc_field='uncall_fc', lc_field='uncall_lc',
            delta_fc=Decimal('5'), delta_lc=Decimal('4'),
            cf_type='UNCALL_COMMITMENT', cf_id=1, cf_number='CF1',
            amount_fc=Decimal('5'), amount_lc=Decimal('4'), dry_run=True,
        )
        assert ok is True
        assert 'DRY RUN' in msg
        impala.execute_write.assert_not_called()

    def test_writes_new_version_on_success(self, cmd, impala):
        position = {'uncall_fc': 10, 'uncall_lc': 8, 'position_id': 1, 'version_id': 2, '_from_ledger': True}
        ok, msg = cmd._accumulate_field(
            position, 'P1', 'S1', '2026-01-01',
            fc_field='uncall_fc', lc_field='uncall_lc',
            delta_fc=Decimal('5'), delta_lc=Decimal('4'),
            cf_type='UNCALL_COMMITMENT', cf_id=1, cf_number='CF1',
            amount_fc=Decimal('5'), amount_lc=Decimal('4'),
        )
        assert ok is True
        assert '15' in msg

    def test_write_failure_returns_false(self, cmd, impala):
        impala.execute_write.return_value = False
        position = {'uncall_fc': 10, 'uncall_lc': 8, 'position_id': 1, 'version_id': 2, '_from_ledger': True}
        ok, msg = cmd._accumulate_field(
            position, 'P1', 'S1', '2026-01-01',
            fc_field='uncall_fc', lc_field='uncall_lc',
            delta_fc=Decimal('5'), delta_lc=Decimal('4'),
            cf_type='UNCALL_COMMITMENT', cf_id=1, cf_number='CF1',
            amount_fc=Decimal('5'), amount_lc=Decimal('4'),
        )
        assert ok is False
        assert 'failed' in msg


class TestReduceAvp:
    def base_position(self):
        return {
            'quantity': 100, 'total_cost_fc': 1000, 'total_cost_lc': 900,
            'market_value_fc': 1200, 'market_value_lc': 1100,
            'position_id': 1, 'version_id': 2, '_from_ledger': True,
        }

    def test_zero_quantity_fails(self, cmd, fake_position_service):
        position = self.base_position()
        position['quantity'] = 0
        ok, msg = cmd._reduce_avp(
            position, 'P1', 'S1', '2026-01-01',
            amount_fc=Decimal('100'), amount_lc=Decimal('90'),
            cf_type='RETURN_OF_CAPITAL', cf_id=1, cf_number='CF1',
            raw_amount_fc=Decimal('100'), raw_amount_lc=Decimal('90'),
        )
        assert ok is False
        assert 'quantity is 0' in msg

    def test_dry_run_non_revalued(self, cmd, fake_position_service):
        position = self.base_position()
        ok, msg = cmd._reduce_avp(
            position, 'P1', 'S1', '2026-01-01',
            amount_fc=Decimal('100'), amount_lc=Decimal('90'),
            cf_type='RETURN_OF_CAPITAL', cf_id=1, cf_number='CF1',
            raw_amount_fc=Decimal('100'), raw_amount_lc=Decimal('90'), dry_run=True,
        )
        assert ok is True
        assert 'DRY RUN' in msg
        assert 'NON-REVALUED' in msg

    def test_revalued_uses_fx_rate(self, cmd, fake_position_service, impala):
        fake_position_service._get_portfolio_revaluation_status.return_value = 'REVALUED'
        position = self.base_position()
        ok, msg = cmd._reduce_avp(
            position, 'P1', 'S1', '2026-01-01',
            amount_fc=Decimal('100'), amount_lc=Decimal('90'),
            cf_type='CAPITAL_DISTRIBUTION', cf_id=1, cf_number='CF1',
            raw_amount_fc=Decimal('100'), raw_amount_lc=Decimal('90'),
        )
        assert ok is True
        assert 'REVALUED' in msg

    def test_equity_method_zeroes_unrealized_pnl(self, cmd, fake_position_service, impala):
        fake_position_service._is_equity_method_portfolio.return_value = True
        position = self.base_position()
        cmd._reduce_avp(
            position, 'P1', 'S1', '2026-01-01',
            amount_fc=Decimal('100'), amount_lc=Decimal('90'),
            cf_type='RETURN_OF_CAPITAL', cf_id=1, cf_number='CF1',
            raw_amount_fc=Decimal('100'), raw_amount_lc=Decimal('90'), dry_run=True,
        )
        assert fake_position_service._is_equity_method_portfolio.called

    def test_total_cost_floored_at_zero(self, cmd, fake_position_service):
        position = self.base_position()
        position['total_cost_fc'] = 50
        position['total_cost_lc'] = 45
        ok, msg = cmd._reduce_avp(
            position, 'P1', 'S1', '2026-01-01',
            amount_fc=Decimal('-1000'), amount_lc=Decimal('-900'),
            cf_type='RETURN_OF_CAPITAL', cf_id=1, cf_number='CF1',
            raw_amount_fc=Decimal('1000'), raw_amount_lc=Decimal('900'), dry_run=True,
        )
        assert ok is True
        assert 'total_cost_fc 50 + (-1000) = 0' in msg

    def test_write_success(self, cmd, fake_position_service, impala):
        position = self.base_position()
        ok, msg = cmd._reduce_avp(
            position, 'P1', 'S1', '2026-01-01',
            amount_fc=Decimal('100'), amount_lc=Decimal('90'),
            cf_type='RETURN_OF_CAPITAL', cf_id=1, cf_number='CF1',
            raw_amount_fc=Decimal('100'), raw_amount_lc=Decimal('90'),
        )
        assert ok is True

    def test_write_failure(self, cmd, fake_position_service, impala):
        impala.execute_write.return_value = False
        position = self.base_position()
        ok, msg = cmd._reduce_avp(
            position, 'P1', 'S1', '2026-01-01',
            amount_fc=Decimal('100'), amount_lc=Decimal('90'),
            cf_type='RETURN_OF_CAPITAL', cf_id=1, cf_number='CF1',
            raw_amount_fc=Decimal('100'), raw_amount_lc=Decimal('90'),
        )
        assert ok is False
        assert 'failed' in msg


class TestWriteNewPositionVersion:
    def test_ledger_write_success_syncs_golden(self, cmd, impala):
        current = {
            'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED',
            '_from_ledger': True, 'quantity': 10,
        }
        result = cmd._write_new_position_version(
            current, 'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
            {'uncall_fc': 15.0}, cf_id=1, cf_number='CF1',
            cf_amount_fc=5.0, cf_amount_lc=4.0,
        )
        assert result is True
        insert_calls = [c for c in impala.execute_write.call_args_list if 'INSERT INTO' in c[0][0]]
        assert len(insert_calls) == 1

    def test_no_position_id_generates_new_one(self, cmd, impala):
        current = {'_from_ledger': True, 'quantity': 10}
        result = cmd._write_new_position_version(
            current, 'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
            {'uncall_fc': 15.0}, cf_id=1, cf_number='CF1',
            cf_amount_fc=5.0, cf_amount_lc=4.0,
        )
        assert result is True

    def test_missing_position_id_with_old_version_raises(self, cmd, impala):
        current = {'_from_ledger': True, 'quantity': 10, 'version_id': 99}
        result = cmd._write_new_position_version(
            current, 'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
            {'uncall_fc': 15.0}, cf_id=1, cf_number='CF1',
            cf_amount_fc=5.0, cf_amount_lc=4.0,
        )
        assert result is False

    def test_non_ledger_routes_to_golden_sync_only(self, cmd, impala):
        current = {'_from_ledger': False, 'quantity': 10}
        with patch.object(cmd, '_sync_to_golden_position') as sync_mock:
            result = cmd._write_new_position_version(
                current, 'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
                {'uncall_fc': 15.0}, cf_id=1, cf_number='CF1',
                cf_amount_fc=5.0, cf_amount_lc=4.0, pos_src='GMP',
            )
        assert result is True
        sync_mock.assert_called_once()

    def test_corr_run_type_sets_position_type(self, cmd, impala):
        current = {'position_id': 1, 'version_id': 2, '_from_ledger': True, 'quantity': 10}
        cmd._write_new_position_version(
            current, 'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
            {'uncall_fc': 15.0}, cf_id=1, cf_number='CF1',
            cf_amount_fc=5.0, cf_amount_lc=4.0, run_type='CORR',
        )
        insert_calls = [c for c in impala.execute_write.call_args_list if 'INSERT INTO' in c[0][0]]
        assert "'CORR'" in insert_calls[0][0][0]

    def test_write_failure_returns_false(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_write.return_value = False
            current = {'position_id': 1, 'version_id': 2, '_from_ledger': True, 'quantity': 10}
            result = cmd._write_new_position_version(
                current, 'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
                {'uncall_fc': 15.0}, cf_id=1, cf_number='CF1',
                cf_amount_fc=5.0, cf_amount_lc=4.0,
            )
        assert result is False

    def test_exception_returns_false(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            current = {'position_id': 1, 'version_id': 2, '_from_ledger': True, 'quantity': 10}
            result = cmd._write_new_position_version(
                current, 'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
                {'uncall_fc': 15.0}, cf_id=1, cf_number='CF1',
                cf_amount_fc=5.0, cf_amount_lc=4.0,
            )
        assert result is False

    def test_none_field_value_treated_as_zero(self, cmd, impala):
        current = {
            'position_id': 1, 'version_id': 2, '_from_ledger': True,
            'quantity': 10, 'market_price': None,
        }
        result = cmd._write_new_position_version(
            current, 'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
            {'uncall_fc': 15.0}, cf_id=1, cf_number='CF1',
            cf_amount_fc=5.0, cf_amount_lc=4.0,
        )
        assert result is True


class TestSyncToGoldenPosition:
    def test_existing_row_reuses_position_id(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.return_value = [{
                'position_id': 42, 'src_system': 'CIS', 'position_basis': 'SETTLED',
                'isin': 'ISIN1', 'source_table': 'cis_trade_position',
            }]
            m.execute_write.return_value = True
            cmd._sync_to_golden_position(
                'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
                current={'position_basis': 'SETTLED'}, overrides={'uncall_fc': 15.0},
                cf_id=1, cf_number='CF1', cf_amount_fc=5.0, cf_amount_lc=4.0,
            )
        upsert_call = m.execute_write.call_args[0][0]
        assert '42' in upsert_call

    def test_no_existing_row_generates_new_position_id(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.return_value = []
            m.execute_write.return_value = True
            cmd._sync_to_golden_position(
                'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
                current={'position_basis': 'SETTLED'}, overrides={'uncall_fc': 15.0},
                cf_id=1, cf_number='CF1', cf_amount_fc=5.0, cf_amount_lc=4.0,
            )
        m.execute_write.assert_called_once()

    def test_write_failure_logged_non_fatal(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.return_value = []
            m.execute_write.return_value = False
            # Should not raise
            cmd._sync_to_golden_position(
                'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
                current={'position_basis': 'SETTLED'}, overrides={'uncall_fc': 15.0},
                cf_id=1, cf_number='CF1', cf_amount_fc=5.0, cf_amount_lc=4.0,
            )

    def test_exception_swallowed_non_fatal(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            # Should not raise
            cmd._sync_to_golden_position(
                'P1', 'S1', '2026-01-01', 'UNCALL_COMMITMENT',
                current={'position_basis': 'SETTLED'}, overrides={'uncall_fc': 15.0},
                cf_id=1, cf_number='CF1', cf_amount_fc=5.0, cf_amount_lc=4.0,
            )

    def test_prefers_override_field_names_over_golden_aliases(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.return_value = [{
                'position_id': 42, 'src_system': 'CIS', 'position_basis': 'SETTLED',
                'cost_fc': 999,
            }]
            m.execute_write.return_value = True
            cmd._sync_to_golden_position(
                'P1', 'S1', '2026-01-01', 'RETURN_OF_CAPITAL',
                current={'position_basis': 'SETTLED', 'total_cost_fc': 500},
                overrides={'total_cost_fc': 500.0},
                cf_id=1, cf_number='CF1', cf_amount_fc=5.0, cf_amount_lc=4.0,
            )
        upsert_call = m.execute_write.call_args[0][0]
        assert '500' in upsert_call


class TestMarkCfProcessed:
    def test_updates_cf_processed(self, cmd, impala):
        cmd._mark_cf_processed(1)
        query = impala.execute_write.call_args[0][0]
        assert 'cf_processed = true' in query

    def test_exception_swallowed(self, cmd):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            cmd._mark_cf_processed(1)  # should not raise


class TestApplyToPosition:
    def make_cf(self, **overrides):
        cf = {'cash_flow_id': 1, 'cash_flow_number': 'CF1'}
        cf.update(overrides)
        return cf

    def test_no_position_and_not_seedable_returns_false(self, cmd, impala):
        impala.execute_query.return_value = []
        ok, msg = cmd._apply_to_position(
            cf=self.make_cf(), cf_type='DIVIDEND', portfolio='P1', security='S1',
            amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='SEND',
            payment_date='2026-01-01', dry_run=False,
        )
        assert ok is False
        assert 'No open position' in msg

    def test_seed_position_used_for_seedable_types(self, cmd, impala):
        impala.execute_query.return_value = []
        with patch('process_approved_cashflows.multicurrency_service') as mc:
            mc.get_fx_rate.return_value = (Decimal('1'), 'src')
            ok, msg = cmd._apply_to_position(
                cf=self.make_cf(), cf_type='UNCALL_COMMITMENT', portfolio='P1', security='S1',
                amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='SEND',
                payment_date='2026-01-01', dry_run=True,
            )
        assert ok is True

    def test_dividend_type_routes_to_accumulate(self, cmd, impala):
        impala.execute_query.return_value = [{'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED', 'dividend_fc': 0, 'dividend_lc': 0}]
        ok, msg = cmd._apply_to_position(
            cf=self.make_cf(), cf_type='DIVIDEND', portfolio='P1', security='S1',
            amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='SEND',
            payment_date='2026-01-01', dry_run=True,
        )
        assert ok is True
        assert 'DIVIDEND' in msg

    def test_cash_dividend_routes_to_accumulate(self, cmd, impala):
        impala.execute_query.return_value = [{'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED', 'dividend_fc': 0, 'dividend_lc': 0}]
        ok, msg = cmd._apply_to_position(
            cf=self.make_cf(), cf_type='CASH_DIVIDEND', portfolio='P1', security='S1',
            amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='SEND',
            payment_date='2026-01-01', dry_run=True,
        )
        assert ok is True

    def test_provision_routes_to_accumulate(self, cmd, impala):
        impala.execute_query.return_value = [{'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED', 'provision_fc': 0, 'provision_lc': 0}]
        ok, msg = cmd._apply_to_position(
            cf=self.make_cf(), cf_type='PROVISION', portfolio='P1', security='S1',
            amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='SEND',
            payment_date='2026-01-01', dry_run=True,
        )
        assert ok is True

    def test_pipeline_routes_to_accumulate(self, cmd, impala):
        impala.execute_query.return_value = [{'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED', 'pipeline_fc': 0, 'pipeline_lc': 0}]
        ok, msg = cmd._apply_to_position(
            cf=self.make_cf(), cf_type='PIPELINE', portfolio='P1', security='S1',
            amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='SEND',
            payment_date='2026-01-01', dry_run=True,
        )
        assert ok is True

    def test_ytd_realise_routes_to_accumulate(self, cmd, impala):
        impala.execute_query.return_value = [{'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED', 'realized_pnl_fc': 0, 'realized_pnl_lc': 0}]
        ok, msg = cmd._apply_to_position(
            cf=self.make_cf(), cf_type='YTD_REALISE', portfolio='P1', security='S1',
            amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='SEND',
            payment_date='2026-01-01', dry_run=True,
        )
        assert ok is True

    def test_income_distribution_routes_to_accumulate(self, cmd, impala):
        impala.execute_query.return_value = [{'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED', 'realized_pnl_fc': 0, 'realized_pnl_lc': 0}]
        ok, msg = cmd._apply_to_position(
            cf=self.make_cf(), cf_type='INCOME_DISTRIBUTION', portfolio='P1', security='S1',
            amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='SEND',
            payment_date='2026-01-01', dry_run=True,
        )
        assert ok is True

    def test_return_of_capital_routes_to_reduce_avp(self, cmd, impala, fake_position_service):
        impala.execute_query.return_value = [{
            'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED',
            'quantity': 100, 'total_cost_fc': 1000, 'total_cost_lc': 900,
            'market_value_fc': 1200, 'market_value_lc': 1100,
        }]
        ok, msg = cmd._apply_to_position(
            cf=self.make_cf(), cf_type='RETURN_OF_CAPITAL', portfolio='P1', security='S1',
            amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='DECREASE',
            payment_date='2026-01-01', dry_run=True,
        )
        assert ok is True

    def test_capital_distribution_routes_to_reduce_avp(self, cmd, impala, fake_position_service):
        impala.execute_query.return_value = [{
            'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED',
            'quantity': 100, 'total_cost_fc': 1000, 'total_cost_lc': 900,
            'market_value_fc': 1200, 'market_value_lc': 1100,
        }]
        ok, msg = cmd._apply_to_position(
            cf=self.make_cf(), cf_type='CAPITAL_DISTRIBUTION', portfolio='P1', security='S1',
            amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='INCREASE',
            payment_date='2026-01-01', dry_run=True,
        )
        assert ok is True

    def test_unrecognised_type_returns_false(self, cmd, impala):
        impala.execute_query.return_value = [{'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED'}]
        ok, msg = cmd._apply_to_position(
            cf=self.make_cf(), cf_type='SOME_UNKNOWN', portfolio='P1', security='S1',
            amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='SEND',
            payment_date='2026-01-01', dry_run=True,
        )
        assert ok is False
        assert 'Unrecognised' in msg

    def test_multiple_positions_any_success_returns_true(self, cmd, fake_position_service):
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = [
                [{'position_id': 1, 'position_basis': 'SETTLED', 'quantity': 100, 'total_cost_fc': 1000, 'total_cost_lc': 900, 'market_value_fc': 1200, 'market_value_lc': 1100}],
                [{'position_id': 2, 'position_basis': 'TRADED', 'quantity': 0, 'total_cost_fc': 0, 'total_cost_lc': 0, 'market_value_fc': 0, 'market_value_lc': 0}],
            ]
            ok, msg = cmd._apply_to_position(
                cf=self.make_cf(), cf_type='RETURN_OF_CAPITAL', portfolio='P1', security='S1',
                amount_fc=Decimal('10'), amount_lc=Decimal('9'), send_receive='DECREASE',
                payment_date='2026-01-01', dry_run=True,
            )
        assert ok is True  # SETTLED succeeds even though TRADED (qty=0) fails


class TestHandle:
    def make_options(self, **overrides):
        opts = {
            'run_type': 'EOD', 'position_date': '2026-01-01', 'dry_run': False,
            'portfolio': None, 'reprocess': False,
        }
        opts.update(overrides)
        return opts

    def test_no_cash_flows_found(self, capsys, impala):
        cmd = Command()
        impala.execute_query.return_value = []
        cmd.handle(**self.make_options())
        out = capsys.readouterr().out
        assert 'No approved cash flows found' in out

    def test_fetch_exception_raises_command_error(self):
        cmd = Command()
        from lib.management_base import CommandError
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            with pytest.raises(CommandError):
                cmd.handle(**self.make_options())

    def test_other_type_skipped(self, capsys):
        cmd = Command()
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.return_value = [{
                'cash_flow_id': 1, 'cash_flow_number': 'CF1', 'cash_flow_type': 'OTHER',
                'portfolio_short_name': 'P1', 'security_label': 'S1', 'send_receive': 'SEND',
                'foreign_ccy_amt': 10, 'local_ccy_amt': 9, 'payment_date': '2026-01-01',
            }]
            cmd.handle(**self.make_options())
        out = capsys.readouterr().out
        assert 'Skipping type OTHER' in out

    def test_missing_portfolio_or_security_skipped(self):
        cmd = Command()
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.return_value = [{
                'cash_flow_id': 1, 'cash_flow_number': 'CF1', 'cash_flow_type': 'DIVIDEND',
                'portfolio_short_name': '', 'security_label': 'S1', 'send_receive': 'SEND',
                'foreign_ccy_amt': 10, 'local_ccy_amt': 9, 'payment_date': '2026-01-01',
            }]
            cmd.handle(**self.make_options())

    def test_successful_processing_marks_cf_processed(self):
        cmd = Command()
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = [
                [{
                    'cash_flow_id': 1, 'cash_flow_number': 'CF1', 'cash_flow_type': 'DIVIDEND',
                    'portfolio_short_name': 'P1', 'security_label': 'S1', 'send_receive': 'SEND',
                    'foreign_ccy_amt': 10, 'local_ccy_amt': 9, 'payment_date': '2026-01-01',
                }],
                [{'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED', 'dividend_fc': 0, 'dividend_lc': 0}],
            ]
            m.execute_write.return_value = True
            cmd.handle(**self.make_options())
        write_calls = [c for c in m.execute_write.call_args_list if 'cf_processed' in c[0][0]]
        assert len(write_calls) == 1

    def test_dry_run_does_not_mark_processed(self):
        cmd = Command()
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = [
                [{
                    'cash_flow_id': 1, 'cash_flow_number': 'CF1', 'cash_flow_type': 'DIVIDEND',
                    'portfolio_short_name': 'P1', 'security_label': 'S1', 'send_receive': 'SEND',
                    'foreign_ccy_amt': 10, 'local_ccy_amt': 9, 'payment_date': '2026-01-01',
                }],
                [{'position_id': 1, 'version_id': 2, 'position_basis': 'SETTLED', 'dividend_fc': 0, 'dividend_lc': 0}],
            ]
            m.execute_write.return_value = True
            cmd.handle(**self.make_options(dry_run=True))
        write_calls = [c for c in m.execute_write.call_args_list if 'cf_processed' in c[0][0]]
        assert len(write_calls) == 0

    def test_no_position_increments_no_position_stat(self, capsys):
        cmd = Command()
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = [
                [{
                    'cash_flow_id': 1, 'cash_flow_number': 'CF1', 'cash_flow_type': 'DIVIDEND',
                    'portfolio_short_name': 'P1', 'security_label': 'S1', 'send_receive': 'SEND',
                    'foreign_ccy_amt': 10, 'local_ccy_amt': 9, 'payment_date': '2026-01-01',
                }],
                [], [],
            ]
            cmd.handle(**self.make_options())
        out = capsys.readouterr().out
        assert 'No position' in out

    def test_apply_exception_counted_as_failed(self, capsys):
        cmd = Command()
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = [
                [{
                    'cash_flow_id': 1, 'cash_flow_number': 'CF1', 'cash_flow_type': 'DIVIDEND',
                    'portfolio_short_name': 'P1', 'security_label': 'S1', 'send_receive': 'SEND',
                    'foreign_ccy_amt': 10, 'local_ccy_amt': 9, 'payment_date': '2026-01-01',
                }],
            ]
            with patch.object(cmd, '_apply_to_position', side_effect=RuntimeError('boom')):
                cmd.handle(**self.make_options())
        out = capsys.readouterr().out
        assert 'Failed' in out

    def test_position_date_inferred_when_not_supplied(self, impala):
        cmd = Command()
        with patch.object(cmd, '_get_dates_from_alldatesinfo', return_value=('2026-01-05', '2025-12-31')) as di:
            impala.execute_query.return_value = []
            cmd.handle(**self.make_options(position_date=None, run_type='EOD'))
        di.assert_called_once()

    def test_corr_run_type_uses_last_month_end(self, capsys, impala):
        cmd = Command()
        with patch.object(cmd, '_get_dates_from_alldatesinfo', return_value=('2026-01-05', '2025-12-31')):
            impala.execute_query.return_value = []
            cmd.handle(**self.make_options(position_date=None, run_type='CORR'))
        out = capsys.readouterr().out
        assert '2025-12-31' in out

    def test_portfolio_filter_printed(self, capsys, impala):
        cmd = Command()
        impala.execute_query.return_value = []
        cmd.handle(**self.make_options(portfolio='PF1'))
        out = capsys.readouterr().out
        assert 'PF1' in out

    def test_dry_run_printed(self, capsys, impala):
        cmd = Command()
        impala.execute_query.return_value = []
        cmd.handle(**self.make_options(dry_run=True))
        out = capsys.readouterr().out
        assert 'DRY RUN' in out

    def test_reprocess_printed(self, capsys, impala):
        cmd = Command()
        impala.execute_query.return_value = []
        cmd.handle(**self.make_options(reprocess=True))
        out = capsys.readouterr().out
        assert 'REPROCESS' in out

    def test_failed_stat_printed_in_error_style(self, capsys):
        cmd = Command()
        with patch('process_approved_cashflows.impala_manager') as m:
            m.execute_query.side_effect = [
                [{
                    'cash_flow_id': 1, 'cash_flow_number': 'CF1', 'cash_flow_type': 'DIVIDEND',
                    'portfolio_short_name': 'P1', 'security_label': 'S1', 'send_receive': 'SEND',
                    'foreign_ccy_amt': 10, 'local_ccy_amt': 9, 'payment_date': '2026-01-01',
                }],
            ]
            with patch.object(cmd, '_apply_to_position', return_value=(False, 'some real failure')):
                cmd.handle(**self.make_options())
        out = capsys.readouterr().out
        assert 'Failed       : 1' in out
