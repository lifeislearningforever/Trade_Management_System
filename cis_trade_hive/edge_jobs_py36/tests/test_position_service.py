"""Tests for edge_jobs_py36/lib/position_service.py."""
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from edge_jobs_py36.lib.position_service import PositionService


@pytest.fixture
def svc():
    return PositionService()


@pytest.fixture
def impala():
    with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
        m.execute_write.return_value = True
        m.execute_query.return_value = []
        yield m


@pytest.fixture
def sds():
    with patch('edge_jobs_py36.lib.position_service.system_date_service') as m:
        m.get_system_date.return_value = date(2026, 1, 10)
        yield m


@pytest.fixture
def mcs():
    with patch('edge_jobs_py36.lib.position_service.multicurrency_service') as m:
        m.get_fx_rate.return_value = (Decimal('1'), None)
        yield m


class TestGetCurrencyDp:
    def test_empty_currency_returns_default(self, svc):
        assert svc._get_currency_dp('') == 2

    def test_returns_parsed_precision(self, svc, impala):
        impala.execute_query.return_value = [{'precision': '0000000000.01'}]
        assert svc._get_currency_dp('USD') == 2

    def test_no_result_returns_default(self, svc, impala):
        impala.execute_query.return_value = []
        assert svc._get_currency_dp('XYZ') == 2

    def test_exception_returns_default(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc._get_currency_dp('USD') == 2


class TestRoundAmount:
    def test_none_returns_none(self):
        assert PositionService._round_amount(None, 2) is None

    def test_rounds_half_up(self):
        assert PositionService._round_amount(1.005, 2) == 1.01

    def test_zero_decimal_places(self):
        assert PositionService._round_amount(1.5, 0) == 2.0


class TestDerivePositionType:
    def test_invalid_format_returns_false(self, svc, sds):
        ok, msg, ptype = svc._derive_position_type('bad-date')
        assert ok is False
        assert ptype is None

    def test_today_returns_int(self, svc, sds):
        ok, msg, ptype = svc._derive_position_type('2026-01-10')
        assert ok is True
        assert ptype == 'INT'

    def test_past_returns_int(self, svc, sds):
        ok, msg, ptype = svc._derive_position_type('2026-01-05')
        assert ok is True
        assert ptype == 'INT'

    def test_future_returns_false(self, svc, sds):
        ok, msg, ptype = svc._derive_position_type('2026-02-01')
        assert ok is False
        assert ptype is None
        assert 'Future' in msg

    def test_today_as_string_normalized(self, svc):
        with patch('edge_jobs_py36.lib.position_service.system_date_service') as m:
            m.get_system_date.return_value = '2026-01-10'
            ok, msg, ptype = svc._derive_position_type('2026-01-10')
        assert ok is True


class TestEscape:
    def test_none(self, svc):
        assert svc._escape(None) == ''

    def test_quote_backslash(self, svc):
        assert svc._escape("O'Brien\\x") == "O\\'Brien\\\\x"


class TestGenerateId:
    def test_returns_int(self, svc):
        assert isinstance(svc._generate_id(), int)


class TestGetCurrentPosition:
    def test_returns_first_result(self, svc, impala):
        impala.execute_query.return_value = [{'quantity': 10}]
        result = svc._get_current_position('P1', 'S1')
        assert result == {'quantity': 10}

    def test_no_result_returns_none(self, svc, impala):
        impala.execute_query.return_value = []
        assert svc._get_current_position('P1', 'S1') is None

    def test_exception_returns_none(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc._get_current_position('P1', 'S1') is None


class TestGetPosition:
    def test_delegates_to_get_current_position(self, svc):
        with patch.object(svc, '_get_current_position', return_value={'x': 1}) as m:
            result = svc.get_position('P1', 'S1')
        assert result == {'x': 1}
        m.assert_called_once_with('P1', 'S1')


class TestGetAllPositions:
    def test_returns_results(self, svc, impala):
        impala.execute_query.return_value = [{'x': 1}]
        result = svc.get_all_positions(portfolio_id='P1')
        assert result == [{'x': 1}]
        query = impala.execute_query.call_args[0][0]
        assert "portfolio_short_name = 'P1'" in query

    def test_no_filters(self, svc, impala):
        svc.get_all_positions(portfolio_id=None, status=None)
        query = impala.execute_query.call_args[0][0]
        assert 'portfolio_short_name' not in query

    def test_none_result_returns_empty_list(self, svc, impala):
        impala.execute_query.return_value = None
        assert svc.get_all_positions() == []

    def test_exception_returns_empty_list(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_all_positions() == []


class TestGetPositionAsOfDate:
    def test_returns_first_result(self, svc, impala):
        impala.execute_query.return_value = [{'quantity': 10}]
        result = svc._get_position_as_of_date('P1', 'S1', '2026-01-01')
        assert result == {'quantity': 10}

    def test_exclude_trade_id_adds_clause(self, svc, impala):
        impala.execute_query.return_value = [{'quantity': 10}]
        svc._get_position_as_of_date('P1', 'S1', '2026-01-01', exclude_trade_id=5)
        query = impala.execute_query.call_args[0][0]
        assert 'trade_id != 5' in query

    def test_exception_returns_none(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc._get_position_as_of_date('P1', 'S1', '2026-01-01') is None

    def test_retries_then_falls_back_to_golden_copy(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_service.time.sleep'):
            m.execute_query.side_effect = [[], [], [{'quantity': 5, 'src_system': 'GMP', 'position_date': '2025-12-31'}]]
            result = svc._get_position_as_of_date('P1', 'S1', '2026-01-01')
        assert result == {'quantity': 5, 'src_system': 'GMP', 'position_date': '2025-12-31'}

    def test_found_on_first_retry_no_golden_fallback(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_service.time.sleep'):
            m.execute_query.side_effect = [[], [{'quantity': 7}]]
            result = svc._get_position_as_of_date('P1', 'S1', '2026-01-01')
        assert result == {'quantity': 7}

    def test_include_same_date_false_uses_lt_operator(self, svc, impala):
        svc._get_position_as_of_date('P1', 'S1', '2026-01-01', include_same_date=False)
        query = impala.execute_query.call_args[0][0]
        assert "position_date < '2026-01-01'" in query


class TestGetPositionFromGoldenCopy:
    def test_returns_reshaped_row(self, svc, impala):
        impala.execute_query.return_value = [{'quantity': 10, 'src_system': 'GMP', 'position_date': '2025-12-31'}]
        result = svc._get_position_from_golden_copy('P1', 'S1', '2026-01-01', '<=', 'TRADED')
        assert result['quantity'] == 10

    def test_no_rows_returns_none(self, svc, impala):
        impala.execute_query.return_value = []
        assert svc._get_position_from_golden_copy('P1', 'S1', '2026-01-01', '<=', 'TRADED') is None

    def test_exception_returns_none(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc._get_position_from_golden_copy('P1', 'S1', '2026-01-01', '<=', 'TRADED') is None


class TestIsEquityMethodPortfolio:
    def test_subsidiary_returns_true(self, svc, impala):
        impala.execute_query.return_value = [{'investment_type': 'SUBSIDIARY CO'}]
        assert svc._is_equity_method_portfolio('P1') is True

    def test_other_returns_false(self, svc, impala):
        impala.execute_query.return_value = [{'investment_type': 'NORMAL'}]
        assert svc._is_equity_method_portfolio('P1') is False

    def test_no_result_returns_false(self, svc, impala):
        impala.execute_query.return_value = []
        assert svc._is_equity_method_portfolio('P1') is False

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc._is_equity_method_portfolio('P1') is False


class TestGetFxRate:
    def test_same_currency_returns_one(self, svc):
        assert svc._get_fx_rate('USD', 'USD') == Decimal('1')

    def test_missing_currency_non_strict_returns_fallback(self, svc):
        assert svc._get_fx_rate(None, 'USD', fallback_rate=Decimal('2')) == Decimal('2')

    def test_missing_currency_non_strict_no_fallback_returns_one(self, svc):
        assert svc._get_fx_rate(None, 'USD') == Decimal('1')

    def test_missing_currency_strict_raises(self, svc):
        with pytest.raises(ValueError):
            svc._get_fx_rate(None, 'USD', strict=True)

    def test_uses_multicurrency_service_rate(self, svc, mcs):
        mcs.get_fx_rate.return_value = (Decimal('1.35'), '2026-01-01')
        result = svc._get_fx_rate('USD', 'SGD')
        assert result == Decimal('1.35')

    def test_falls_back_to_implied_rate_when_table_returns_one(self, svc, mcs):
        mcs.get_fx_rate.return_value = (Decimal('1'), None)
        result = svc._get_fx_rate('USD', 'SGD', fallback_rate=Decimal('1.4'))
        assert result == Decimal('1.4')

    def test_value_error_propagates(self, svc, mcs):
        mcs.get_fx_rate.side_effect = ValueError('strict failure')
        with pytest.raises(ValueError):
            svc._get_fx_rate('USD', 'SGD')

    def test_generic_exception_non_strict_returns_fallback(self, svc, mcs):
        mcs.get_fx_rate.side_effect = RuntimeError('boom')
        result = svc._get_fx_rate('USD', 'SGD', fallback_rate=Decimal('1.5'))
        assert result == Decimal('1.5')

    def test_generic_exception_strict_raises_value_error(self, svc, mcs):
        mcs.get_fx_rate.side_effect = RuntimeError('boom')
        with pytest.raises(ValueError):
            svc._get_fx_rate('USD', 'SGD', strict=True)


class TestGetPortfolioRevaluationStatus:
    def test_returns_status(self, svc, impala):
        impala.execute_query.return_value = [{'revaluation_status': 'non-revalued'}]
        assert svc._get_portfolio_revaluation_status('P1') == 'NON-REVALUED'

    def test_no_result_defaults_revalued(self, svc, impala):
        impala.execute_query.return_value = []
        assert svc._get_portfolio_revaluation_status('P1') == 'REVALUED'

    def test_invalid_status_defaults_revalued(self, svc, impala):
        impala.execute_query.return_value = [{'revaluation_status': 'GARBAGE'}]
        assert svc._get_portfolio_revaluation_status('P1') == 'REVALUED'

    def test_repeated_exceptions_raise_runtime_error(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            with pytest.raises(RuntimeError):
                svc._get_portfolio_revaluation_status('P1')

    def test_transient_error_then_success(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = [RuntimeError('boom'), [{'revaluation_status': 'REVALUED'}]]
            result = svc._get_portfolio_revaluation_status('P1')
        assert result == 'REVALUED'


class TestResolveCurrencies:
    def test_both_supplied_passthrough(self, svc):
        sec, port = svc._resolve_currencies('P1', 'S1', 'USD', 'SGD')
        assert (sec, port) == ('USD', 'SGD')

    def test_resolves_missing_security_currency(self, svc, impala):
        impala.execute_query.return_value = [{'currency_code': 'USD'}]
        sec, port = svc._resolve_currencies('P1', 'S1', None, 'SGD')
        assert sec == 'USD'
        assert port == 'SGD'

    def test_resolves_missing_portfolio_currency(self, svc, impala):
        impala.execute_query.return_value = [{'currency': 'SGD'}]
        sec, port = svc._resolve_currencies('P1', 'S1', 'USD', None)
        assert sec == 'USD'
        assert port == 'SGD'

    def test_resolves_both_missing(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = [[{'currency_code': 'USD'}], [{'currency': 'SGD'}]]
            sec, port = svc._resolve_currencies('P1', 'S1', None, None)
        assert sec == 'USD'
        assert port == 'SGD'

    def test_exception_returns_originals(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            sec, port = svc._resolve_currencies('P1', 'S1', None, None)
        assert sec is None
        assert port is None


class TestValidateTradeForPosition:
    def test_non_position_affecting_type_valid(self, svc):
        ok, errors = svc.validate_trade_for_position('CANCEL', Decimal('10'), Decimal('100'), 'P1', 'S1')
        assert ok is True
        assert errors == []

    def test_zero_quantity_invalid(self, svc):
        ok, errors = svc.validate_trade_for_position('BUY', Decimal('0'), Decimal('100'), 'P1', 'S1')
        assert ok is False
        assert any('positive' in e for e in errors)

    def test_negative_price_invalid(self, svc):
        ok, errors = svc.validate_trade_for_position('BUY', Decimal('10'), Decimal('-1'), 'P1', 'S1')
        assert ok is False
        assert any('negative' in e for e in errors)

    def test_sell_insufficient_quantity(self, svc):
        with patch.object(svc, '_get_current_position', return_value={'quantity': 5}):
            ok, errors = svc.validate_trade_for_position('SELL', Decimal('10'), Decimal('100'), 'P1', 'S1')
        assert ok is False
        assert any('Insufficient' in e for e in errors)

    def test_sell_no_position_insufficient(self, svc):
        with patch.object(svc, '_get_current_position', return_value=None):
            ok, errors = svc.validate_trade_for_position('SELL', Decimal('10'), Decimal('100'), 'P1', 'S1')
        assert ok is False

    def test_valid_buy(self, svc):
        ok, errors = svc.validate_trade_for_position('BUY', Decimal('10'), Decimal('100'), 'P1', 'S1')
        assert ok is True
        assert errors == []


class TestCalculatePosition:
    def common_kwargs(self, **overrides):
        kwargs = dict(
            portfolio_id='P1', security_id='S1', trade_type='BUY',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            position_date='2026-01-10', trade_id=1, updated_by='user1',
        )
        kwargs.update(overrides)
        return kwargs

    def test_non_position_affecting_type_returns_true_noop(self, svc, sds):
        ok, msg, result = svc.calculate_position(**self.common_kwargs(trade_type='CANCEL'))
        assert ok is True
        assert result is None

    def test_idempotency_guard_returns_existing(self, svc, sds, impala):
        impala.execute_query.return_value = [{'version_id': 5, 'position_id': 1}]
        ok, msg, result = svc.calculate_position(**self.common_kwargs())
        assert ok is True
        assert 'idempotency guard' in msg
        assert result == {'version_id': 5, 'position_id': 1}

    def test_chain_recalc_skips_idempotency_guard(self, svc, sds, impala):
        with patch.object(svc, '_process_buy', return_value=(True, 'ok', {})) as pb:
            ok, msg, result = svc.calculate_position(**self.common_kwargs(is_chain_recalc=True))
        pb.assert_called_once()

    def test_zero_quantity_fails(self, svc, sds, impala):
        ok, msg, result = svc.calculate_position(**self.common_kwargs(quantity=Decimal('0')))
        assert ok is False
        assert 'positive' in msg

    def test_negative_price_fails(self, svc, sds, impala):
        ok, msg, result = svc.calculate_position(**self.common_kwargs(price=Decimal('-1')))
        assert ok is False
        assert 'negative' in msg

    def test_invalid_position_date_fails(self, svc, sds, impala):
        ok, msg, result = svc.calculate_position(**self.common_kwargs(position_date='bad-date'))
        assert ok is False

    def test_buy_routes_to_process_buy(self, svc, sds, impala):
        with patch.object(svc, '_process_buy', return_value=(True, 'ok', {'x': 1})) as pb:
            ok, msg, result = svc.calculate_position(**self.common_kwargs())
        assert ok is True
        pb.assert_called_once()

    def test_sell_routes_to_process_sell(self, svc, sds, impala):
        with patch.object(svc, '_process_sell', return_value=(True, 'ok', {'x': 1})) as ps:
            ok, msg, result = svc.calculate_position(**self.common_kwargs(trade_type='SELL'))
        assert ok is True
        ps.assert_called_once()

    def test_chain_recalc_uses_base_position_override_dict(self, svc, sds):
        with patch.object(svc, '_process_buy', return_value=(True, 'ok', {})) as pb:
            svc.calculate_position(**self.common_kwargs(
                is_chain_recalc=True, base_position_override={'quantity': 5},
            ))
        assert pb.call_args[1]['current'] == {'quantity': 5}

    def test_chain_recalc_empty_override_means_fresh_start(self, svc, sds):
        with patch.object(svc, '_process_buy', return_value=(True, 'ok', {})) as pb:
            svc.calculate_position(**self.common_kwargs(
                is_chain_recalc=True, base_position_override={},
            ))
        assert pb.call_args[1]['current'] is None

    def test_chain_recalc_none_override_does_db_lookup(self, svc, sds):
        with patch.object(svc, '_get_position_as_of_date', return_value={'quantity': 3}) as lookup, \
             patch.object(svc, '_process_buy', return_value=(True, 'ok', {})):
            svc.calculate_position(**self.common_kwargs(is_chain_recalc=True))
        lookup.assert_called_once()

    def test_outer_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.position_service.system_date_service') as m:
            m.get_system_date.side_effect = RuntimeError('boom')
            ok, msg, result = svc.calculate_position(**self.common_kwargs())
        assert ok is False
        assert 'Position calculation error' in msg


class TestProcessBuy:
    def base_kwargs(self, **overrides):
        kwargs = dict(
            current=None, portfolio_id='P1', security_id='S1',
            quantity=Decimal('10'), price=Decimal('100'), charges=Decimal('1'),
            position_date='2026-01-10', trade_id=1, updated_by='user1',
            security_currency='USD', portfolio_currency='USD',
        )
        kwargs.update(overrides)
        return kwargs

    def test_new_position_created(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_buy(**self.base_kwargs())
        assert ok is True
        assert position['quantity'] == 10.0
        assert position['average_cost_fc'] == 100.0

    def test_adds_to_existing_position(self, svc, impala):
        current = {
            'quantity': 100, 'average_cost_fc': 90, 'total_cost_fc': 9000, 'realized_pnl_fc': 0,
            'total_cost_lc': 9000, 'realized_pnl_lc': 0,
        }
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_buy(**self.base_kwargs(current=current))
        assert ok is True
        assert position['quantity'] == 110.0

    def test_uses_gross_amount_fc_when_supplied(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=100), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_buy(**self.base_kwargs(gross_amount_fc=Decimal('999')))
        assert position['total_cost_fc'] == 999.0

    def test_equity_method_zeroes_unrealized_pnl(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=True), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_buy(**self.base_kwargs())
        assert position['unrealized_pnl_fc'] == 0.0

    def test_cross_currency_non_revalued_uses_effective_gross_lc(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=100), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='NON-REVALUED'), \
             patch.object(svc, '_get_fx_rate', return_value=Decimal('1.35')), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_buy(**self.base_kwargs(
                security_currency='USD', portfolio_currency='SGD', gross_amount_lc=Decimal('1350'),
            ))
        assert position['total_cost_lc'] == 1350.0

    def test_cross_currency_revalued_uses_fx_rate(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=100), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_get_fx_rate', return_value=Decimal('1.35')), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_buy(**self.base_kwargs(
                security_currency='USD', portfolio_currency='SGD',
            ))
        assert position['total_cost_lc'] == 1350.0

    def test_carries_forward_uncall_pipeline_provision_from_current(self, svc, impala):
        current = {
            'quantity': 100, 'average_cost_fc': 90, 'total_cost_fc': 9000, 'realized_pnl_fc': 0,
            'total_cost_lc': 9000, 'realized_pnl_lc': 0,
            'uncall_fc': 5, 'uncall_lc': 5, 'pipeline_fc': 3, 'pipeline_lc': 3,
            'provision_fc': 1, 'provision_lc': 1, 'dividend_fc': 2, 'dividend_lc': 2,
        }
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_buy(**self.base_kwargs(current=current))
        assert position['uncall_fc'] == 5
        assert position['provision_fc'] == 1
        assert position['dividend_fc'] == 2

    def test_explicit_uncall_overrides_carried(self, svc, impala):
        current = {'quantity': 100, 'average_cost_fc': 90, 'total_cost_fc': 9000, 'uncall_fc': 5}
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_buy(**self.base_kwargs(current=current, uncall_fc=Decimal('99')))
        assert position['uncall_fc'] == 99.0

    def test_zero_market_price_produces_zero_market_value(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=0), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_buy(**self.base_kwargs())
        assert position['market_value_fc'] == 0.0

    def test_none_market_price_falls_back_to_trade_price(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=None), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_buy(**self.base_kwargs())
        assert position['market_price'] == 100.0

    def test_save_failure_returns_false(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=100), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=False):
            ok, msg, position = svc._process_buy(**self.base_kwargs())
        assert ok is False
        assert position is None


class TestProcessSell:
    def base_kwargs(self, **overrides):
        current = {
            'quantity': 100, 'average_cost_fc': 90, 'realized_pnl_fc': 0,
            'average_cost_lc': 95, 'total_cost_lc': 9500, 'realized_pnl_lc': 0,
            'dividend_fc': 0, 'dividend_lc': 0, 'provision_fc': 0, 'provision_lc': 0,
        }
        kwargs = dict(
            current=current, portfolio_id='P1', security_id='S1',
            quantity=Decimal('20'), price=Decimal('110'),
            position_date='2026-01-10', trade_id=1, updated_by='user1',
            security_currency='USD', portfolio_currency='USD',
        )
        kwargs.update(overrides)
        return kwargs

    def test_no_position_fails(self, svc):
        ok, msg, result = svc._process_sell(**self.base_kwargs(current=None))
        assert ok is False
        assert 'No position' in msg

    def test_short_sell_rejected(self, svc):
        current = {'quantity': 5, 'average_cost_fc': 90}
        ok, msg, result = svc._process_sell(**self.base_kwargs(current=current, quantity=Decimal('10')))
        assert ok is False
        assert 'Insufficient' in msg

    def test_partial_sell_avp_unchanged(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_sell(**self.base_kwargs())
        assert ok is True
        assert position['status'] == 'OPEN'
        assert position['average_cost_fc'] == 90.0
        assert position['quantity'] == 80.0

    def test_full_close_sets_closed_status(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_sell(**self.base_kwargs(quantity=Decimal('100')))
        assert ok is True
        assert position['status'] == 'CLOSED'
        assert position['is_active'] is False
        assert position['quantity'] == 0

    def test_realized_pnl_computed(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_sell(**self.base_kwargs())
        # (110 - 90) * 20 = 400
        assert position['realized_pnl_fc'] == 400.0

    def test_uses_gross_amount_fc_when_supplied(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_sell(**self.base_kwargs(gross_amount_fc=Decimal('2200')))
        assert ok is True

    def test_non_revalued_cross_currency_uses_trade_lc(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='NON-REVALUED'), \
             patch.object(svc, '_get_fx_rate', return_value=Decimal('1.35')), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_sell(**self.base_kwargs(
                security_currency='USD', portfolio_currency='SGD', trade_lc=Decimal('2200'),
            ))
        assert ok is True

    def test_equity_method_zeroes_unrealized_pnl(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=True), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_sell(**self.base_kwargs())
        assert position['unrealized_pnl_fc'] == 0.0

    def test_zero_avg_cost_lc_fallback_uses_fx_rate(self, svc, impala):
        current = {
            'quantity': 100, 'average_cost_fc': 90, 'realized_pnl_fc': 0,
            'average_cost_lc': 0, 'total_cost_lc': 0, 'realized_pnl_lc': 0,
        }
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_get_fx_rate', return_value=Decimal('1.35')), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_sell(**self.base_kwargs(
                current=current, security_currency='USD', portfolio_currency='SGD',
            ))
        assert ok is True

    def test_none_market_price_falls_back_to_avg_cost(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=None), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_sell(**self.base_kwargs())
        assert position['market_price'] == 90.0

    def test_save_failure_returns_false(self, svc, impala):
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=False):
            ok, msg, position = svc._process_sell(**self.base_kwargs())
        assert ok is False
        assert position is None

    def test_partial_sell_carries_uncall_pipeline_explicit_override(self, svc, impala):
        current = {
            'quantity': 100, 'average_cost_fc': 90, 'realized_pnl_fc': 0,
            'average_cost_lc': 95, 'total_cost_lc': 9500, 'realized_pnl_lc': 0,
            'uncall_fc': 3,
        }
        with patch.object(svc, '_get_market_price', return_value=105), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED'), \
             patch.object(svc, '_save_position', return_value=True):
            ok, msg, position = svc._process_sell(**self.base_kwargs(current=current, uncall_fc=Decimal('7')))
        assert position['uncall_fc'] == 7.0


class TestSavePosition:
    def base_position_data(self, **overrides):
        pd = {
            'position_id': 1, 'portfolio_short_name': 'P1', 'security_label': 'S1',
            'quantity': 10.0, 'average_cost_fc': 100.0, 'total_cost_fc': 1000.0,
            'average_cost_lc': 100.0, 'total_cost_lc': 1000.0,
            'realized_pnl_fc': 0.0, 'unrealized_pnl_fc': 0.0,
            'realized_pnl_lc': 0.0, 'market_price': 100.0, 'market_value_fc': 1000.0,
            'market_value_lc': 1000.0, 'dividend_fc': 0.0, 'dividend_lc': 0.0,
            'trade_id': 1, 'trade_type': 'BUY', 'position_date': '2026-01-10',
            'status': 'OPEN', 'is_active': True, 'security_currency': 'USD',
            'portfolio_currency': 'USD', 'isin': 'ISIN1', 'position_type': 'INT',
            'position_basis': 'TRADED', 'uncall_fc': 0, 'uncall_lc': 0,
            'pipeline_fc': 0, 'pipeline_lc': 0, 'provision_fc': 0, 'provision_lc': 0,
            '_reval_status': 'REVALUED', '_is_equity_method': False,
            '_expect_prior_version': False,
        }
        pd.update(overrides)
        return pd

    def test_success_writes_and_syncs(self, svc, impala):
        with patch.object(svc, '_mark_old_versions_not_latest', return_value=True), \
             patch.object(svc, '_sync_to_cis_position', return_value=True) as sync_mock:
            result = svc._save_position(self.base_position_data(), 'user1')
        assert result is True
        sync_mock.assert_called_once()

    def test_write_failure_no_sync(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_write.return_value = False
            with patch.object(svc, '_mark_old_versions_not_latest', return_value=True), \
                 patch.object(svc, '_sync_to_cis_position') as sync_mock:
                result = svc._save_position(self.base_position_data(), 'user1')
        assert result is False
        sync_mock.assert_not_called()

    def test_non_revalued_uses_historical_lc(self, svc, impala):
        pd = self.base_position_data(_reval_status='NON-REVALUED', average_cost_lc=95.0, total_cost_lc=950.0)
        with patch.object(svc, '_mark_old_versions_not_latest', return_value=True), \
             patch.object(svc, '_sync_to_cis_position', return_value=True):
            result = svc._save_position(pd, 'user1')
        assert result is True

    def test_non_revalued_fallback_to_current_fx_when_no_historical(self, svc, impala):
        pd = self.base_position_data(_reval_status='NON-REVALUED', average_cost_lc=0, total_cost_lc=0, realized_pnl_lc=0)
        with patch.object(svc, '_mark_old_versions_not_latest', return_value=True), \
             patch.object(svc, '_sync_to_cis_position', return_value=True):
            result = svc._save_position(pd, 'user1')
        assert result is True

    def test_fx_rate_lookup_value_error_falls_back_to_one(self, svc, impala):
        pd = self.base_position_data(security_currency='USD', portfolio_currency='SGD')
        with patch.object(svc, '_get_fx_rate', side_effect=ValueError('no rate')), \
             patch.object(svc, '_mark_old_versions_not_latest', return_value=True), \
             patch.object(svc, '_sync_to_cis_position', return_value=True):
            result = svc._save_position(pd, 'user1')
        assert result is True

    def test_equity_method_zeroes_unrealized_pnl_lc(self, svc, impala):
        pd = self.base_position_data(_is_equity_method=True)
        with patch.object(svc, '_mark_old_versions_not_latest', return_value=True), \
             patch.object(svc, '_sync_to_cis_position', return_value=True):
            result = svc._save_position(pd, 'user1')
        assert result is True

    def test_is_equity_method_none_queries_fresh(self, svc, impala):
        pd = self.base_position_data()
        del pd['_is_equity_method']
        with patch.object(svc, '_mark_old_versions_not_latest', return_value=True), \
             patch.object(svc, '_is_equity_method_portfolio', return_value=False) as em, \
             patch.object(svc, '_sync_to_cis_position', return_value=True):
            svc._save_position(pd, 'user1')
        em.assert_called_once()

    def test_reval_status_none_queries_fresh(self, svc, impala):
        pd = self.base_position_data()
        del pd['_reval_status']
        with patch.object(svc, '_mark_old_versions_not_latest', return_value=True), \
             patch.object(svc, '_get_portfolio_revaluation_status', return_value='REVALUED') as rv, \
             patch.object(svc, '_sync_to_cis_position', return_value=True):
            svc._save_position(pd, 'user1')
        rv.assert_called_once()

    def test_exception_returns_false(self, svc):
        with patch.object(svc, '_mark_old_versions_not_latest', side_effect=RuntimeError('boom')):
            result = svc._save_position(self.base_position_data(), 'user1')
        assert result is False


class TestSyncToCisPosition:
    def test_success(self, svc, impala):
        result = svc._sync_to_cis_position({'portfolio': 'P1', 'security_label': 'S1'}, 'user1')
        assert result is True

    def test_write_failure_returns_false(self, svc, impala):
        impala.execute_write.return_value = False
        result = svc._sync_to_cis_position({'portfolio': 'P1', 'security_label': 'S1'}, 'user1')
        assert result is False

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            result = svc._sync_to_cis_position({'portfolio': 'P1', 'security_label': 'S1'}, 'user1')
        assert result is False


class TestMarkOldVersionsNotLatest:
    def test_no_existing_rows_returns_true(self, svc, impala):
        impala.execute_query.return_value = []
        result = svc._mark_old_versions_not_latest('P1', 'S1', '2026-01-01', 'TRADED')
        assert result is True

    def test_marks_existing_rows(self, svc, impala):
        impala.execute_query.return_value = [{
            'version_id': 1, 'position_id': 2, 'position_date': '2026-01-01',
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'quantity': 10,
        }]
        result = svc._mark_old_versions_not_latest('P1', 'S1', '2026-01-01', 'TRADED')
        assert result is True
        upsert_calls = [c for c in impala.execute_write.call_args_list if 'is_latest' in c[0][0]]
        assert len(upsert_calls) == 1

    def test_expect_prior_version_retries_and_finds(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_service.time.sleep'):
            m.execute_query.side_effect = [
                [],
                [{'version_id': 1, 'position_id': 2, 'position_date': '2026-01-01',
                  'portfolio_short_name': 'P1', 'security_label': 'S1', 'quantity': 10}],
            ]
            result = svc._mark_old_versions_not_latest('P1', 'S1', '2026-01-01', 'TRADED', expect_prior_version=True)
        assert result is True

    def test_expect_prior_version_exhausts_retries(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m, \
             patch('edge_jobs_py36.lib.position_service.time.sleep'):
            m.execute_query.return_value = []
            result = svc._mark_old_versions_not_latest('P1', 'S1', '2026-01-01', 'TRADED', expect_prior_version=True)
        assert result is True  # no rows to update, still returns True

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            result = svc._mark_old_versions_not_latest('P1', 'S1', '2026-01-01', 'TRADED')
        assert result is False


class TestSyncToPositionMaster:
    def test_success(self, svc, impala):
        position_data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'isin': 'ISIN1',
            'quantity': 10, 'position_date': '2026-01-01',
        }
        result = svc._sync_to_position_master(position_data, 'user1')
        assert result is True

    def test_write_failure_returns_false(self, svc, impala):
        impala.execute_write.return_value = False
        result = svc._sync_to_position_master({'portfolio_short_name': 'P1', 'security_label': 'S1'}, 'user1')
        assert result is False

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            result = svc._sync_to_position_master({'portfolio_short_name': 'P1', 'security_label': 'S1'}, 'user1')
        assert result is False


class TestGetMarketPrice:
    def test_returns_price(self, svc, impala):
        impala.execute_query.return_value = [{'main_closing_price': 100.5}]
        assert svc._get_market_price('SEC1') == 100.5

    def test_none_price_returns_none(self, svc, impala):
        impala.execute_query.return_value = [{'main_closing_price': None}]
        assert svc._get_market_price('SEC1') is None

    def test_no_result_returns_none(self, svc, impala):
        impala.execute_query.return_value = []
        assert svc._get_market_price('SEC1') is None

    def test_exception_returns_none(self, svc):
        with patch('edge_jobs_py36.lib.position_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc._get_market_price('SEC1') is None
