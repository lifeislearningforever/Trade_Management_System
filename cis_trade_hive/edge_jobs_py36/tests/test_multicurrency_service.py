"""Tests for edge_jobs_py36/lib/multicurrency_service.py."""
from decimal import Decimal
from unittest.mock import patch

import pytest

from edge_jobs_py36.lib.multicurrency_service import MultiCurrencyService


def _svc():
    return MultiCurrencyService()


class TestEscape:
    def test_none_returns_empty(self):
        assert _svc()._escape(None) == ''

    def test_escapes_quote_and_backslash(self):
        assert _svc()._escape("O'Brien\\x") == "O\\'Brien\\\\x"


class TestCache:
    def test_cache_rate_and_retrieve(self):
        svc = _svc()
        svc._cache_rate('USD-SGD-latest', (Decimal('1.35'), '2026-09-17'))
        assert svc._get_cached_rate('USD-SGD-latest') == (Decimal('1.35'), '2026-09-17')

    def test_get_cached_rate_missing_returns_none(self):
        svc = _svc()
        assert svc._get_cached_rate('nonexistent') is None

    def test_expired_cache_entry_returns_none_and_is_evicted(self):
        svc = _svc()
        svc._cache_ttl = -1  # immediately expired
        svc._cache_rate('USD-SGD-latest', (Decimal('1.35'), '2026-09-17'))
        assert svc._get_cached_rate('USD-SGD-latest') is None
        assert 'USD-SGD-latest' not in svc._fx_cache

    def test_clear_cache_empties_store(self):
        svc = _svc()
        svc._cache_rate('k', (Decimal('1'), 'd'))
        svc.clear_cache()
        assert svc._fx_cache == {}


class TestGetFxRateSameCurrency:
    def test_same_currency_returns_rate_of_one(self):
        svc = _svc()
        rate, date_used = svc.get_fx_rate('USD', 'USD')
        assert rate == Decimal('1')

    def test_same_currency_uses_given_rate_date(self):
        svc = _svc()
        rate, date_used = svc.get_fx_rate('USD', 'USD', rate_date='2026-01-01')
        assert date_used == '2026-01-01'


class TestGetFxRateMissingCurrencies:
    def test_missing_from_currency_defaults_to_one_non_strict(self):
        svc = _svc()
        rate, _ = svc.get_fx_rate('', 'SGD')
        assert rate == Decimal('1')

    def test_missing_from_currency_raises_in_strict_mode(self):
        svc = _svc()
        with pytest.raises(ValueError, match='Currency codes are required'):
            svc.get_fx_rate('', 'SGD', strict=True)


class TestGetFxRateDirectLookup:
    def test_direct_pair_found(self):
        svc = _svc()
        with patch.object(svc, '_lookup_rate', return_value=(Decimal('1.35'), '2026-09-17')):
            rate, date_used = svc.get_fx_rate('USD', 'SGD')
        assert rate == Decimal('1.35')

    def test_direct_pair_cached_after_lookup(self):
        svc = _svc()
        with patch.object(svc, '_lookup_rate', return_value=(Decimal('1.35'), '2026-09-17')) as mock_lookup:
            svc.get_fx_rate('USD', 'SGD')
            svc.get_fx_rate('USD', 'SGD')
        assert mock_lookup.call_count == 1  # second call hit cache


class TestGetFxRateReverseLookup:
    def test_reverse_pair_inverted(self):
        svc = _svc()

        def fake_lookup(from_ccy, to_ccy, rate_date=None):
            if from_ccy == 'USD' and to_ccy == 'SGD':
                return None, None
            if from_ccy == 'SGD' and to_ccy == 'USD':
                return Decimal('0.75'), '2026-09-17'
            return None, None

        with patch.object(svc, '_lookup_rate', side_effect=fake_lookup):
            rate, date_used = svc.get_fx_rate('USD', 'SGD')
        assert rate == (Decimal('1') / Decimal('0.75')).quantize(svc.FX_PRECISION)

    def test_reverse_pair_zero_rate_not_used(self):
        svc = _svc()

        def fake_lookup(from_ccy, to_ccy, rate_date=None):
            if from_ccy == 'SGD' and to_ccy == 'USD':
                return Decimal('0'), '2026-09-17'
            return None, None

        with patch.object(svc, '_lookup_rate', side_effect=fake_lookup):
            rate, _ = svc.get_fx_rate('USD', 'SGD')
        assert rate == Decimal('1')  # falls through to default


class TestGetFxRateTriangulation:
    def test_triangulates_through_usd(self):
        svc = _svc()

        def fake_lookup(from_ccy, to_ccy, rate_date=None):
            mapping = {
                ('EUR', 'USD'): (Decimal('1.1'), '2026-09-17'),
                ('USD', 'SGD'): (Decimal('1.35'), '2026-09-17'),
            }
            return mapping.get((from_ccy, to_ccy), (None, None))

        with patch.object(svc, '_lookup_rate', side_effect=fake_lookup):
            rate, _ = svc.get_fx_rate('EUR', 'SGD')
        expected = (Decimal('1.1') * Decimal('1.35')).quantize(svc.FX_PRECISION)
        assert rate == expected

    def test_no_triangulation_when_from_or_to_is_usd(self):
        svc = _svc()
        with patch.object(svc, '_lookup_rate', return_value=(None, None)) as mock_lookup:
            rate, _ = svc.get_fx_rate('USD', 'SGD')
        # only direct + reverse attempted, no triangulation (2 calls)
        assert mock_lookup.call_count == 2
        assert rate == Decimal('1')


class TestGetFxRateNotFound:
    def test_defaults_to_one_when_not_found_non_strict(self):
        svc = _svc()
        with patch.object(svc, '_lookup_rate', return_value=(None, None)):
            rate, _ = svc.get_fx_rate('EUR', 'JPY')
        assert rate == Decimal('1')

    def test_raises_in_strict_mode_when_not_found(self):
        svc = _svc()
        with patch.object(svc, '_lookup_rate', return_value=(None, None)):
            with pytest.raises(ValueError, match='FX rate not found'):
                svc.get_fx_rate('EUR', 'JPY', strict=True)

    def test_exception_defaults_to_one_non_strict(self):
        svc = _svc()
        with patch.object(svc, '_lookup_rate', side_effect=RuntimeError('boom')):
            rate, _ = svc.get_fx_rate('EUR', 'JPY')
        assert rate == Decimal('1')

    def test_exception_raises_value_error_in_strict_mode(self):
        svc = _svc()
        with patch.object(svc, '_lookup_rate', side_effect=RuntimeError('boom')):
            with pytest.raises(ValueError, match='Error fetching FX rate'):
                svc.get_fx_rate('EUR', 'JPY', strict=True)


class TestLookupRate:
    def test_returns_rate_and_date_when_found(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'spot_rate_d': '1.35', 'date': '20260917'}]
            rate, date_used = svc._lookup_rate('USD', 'SGD')
        assert rate == Decimal('1.35')

    def test_returns_none_none_when_no_results(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            rate, date_used = svc._lookup_rate('USD', 'SGD')
        assert rate is None
        assert date_used is None

    def test_returns_none_none_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            rate, date_used = svc._lookup_rate('USD', 'SGD')
        assert rate is None

    def test_falls_back_to_closest_earlier_date(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [[], [{'spot_rate_d': '1.3', 'date': '20260910'}]]
            rate, date_used = svc._lookup_rate('USD', 'SGD', rate_date='2026-09-17')
        assert rate == Decimal('1.3')
        assert mock_mgr.execute_query.call_count == 2

    def test_no_rate_date_uses_latest_query(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            svc._lookup_rate('USD', 'SGD', rate_date=None)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'ORDER BY `date` DESC' in query

    def test_null_spot_rate_treated_as_not_found(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'spot_rate_d': None, 'date': '20260917'}]
            rate, _ = svc._lookup_rate('USD', 'SGD')
        assert rate is None


class TestGetLatestRatesForCurrency:
    def test_returns_deduplicated_list(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'ref_quot_ccy': 'USD-SGD', 'spot_rate_d': '1.35', 'date': '20260917'},
                {'ref_quot_ccy': 'USD-SGD', 'spot_rate_d': '1.30', 'date': '20260910'},  # older dup
                {'ref_quot_ccy': 'USD-EUR', 'spot_rate_d': '0.9', 'date': '20260917'},
            ]
            result = svc.get_latest_rates_for_currency('USD')
        assert len(result) == 2

    def test_returns_empty_list_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_latest_rates_for_currency('USD') == []

    def test_returns_empty_list_when_none(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            assert svc.get_latest_rates_for_currency('USD') == []


class TestGetFxRatesBatch:
    def test_empty_input_returns_empty_dict(self):
        svc = _svc()
        assert svc.get_fx_rates_batch([]) == {}

    def test_same_currency_pairs_default_to_one(self):
        svc = _svc()
        result = svc.get_fx_rates_batch([('USD', 'USD')])
        assert result['USD-USD'][0] == Decimal('1')

    def test_missing_currency_defaults_to_one(self):
        svc = _svc()
        result = svc.get_fx_rates_batch([('', 'SGD')])
        assert result['-SGD'][0] == Decimal('1')

    def test_direct_pair_fetched_from_query(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'ref_quot_ccy': 'USD-SGD', 'spot_rate_d': '1.35', 'date': '2026-09-17'},
            ]
            result = svc.get_fx_rates_batch([('USD', 'SGD')])
        assert result['USD-SGD'][0] == Decimal('1.35')

    def test_reverse_pair_inverted(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'ref_quot_ccy': 'SGD-USD', 'spot_rate_d': '0.75', 'date': '2026-09-17'},
            ]
            result = svc.get_fx_rates_batch([('USD', 'SGD')])
        expected = (Decimal('1') / Decimal('0.75')).quantize(svc.FX_PRECISION)
        assert result['USD-SGD'][0] == expected

    def test_reverse_pair_zero_defaults_to_one(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'ref_quot_ccy': 'SGD-USD', 'spot_rate_d': '0', 'date': '2026-09-17'},
            ]
            result = svc.get_fx_rates_batch([('USD', 'SGD')])
        assert result['USD-SGD'][0] == Decimal('1')

    def test_no_rate_found_defaults_to_one(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = svc.get_fx_rates_batch([('USD', 'JPY')])
        assert result['USD-JPY'][0] == Decimal('1')

    def test_uses_cache_for_already_cached_pairs(self):
        svc = _svc()
        svc._cache_rate('USD-SGD-latest', (Decimal('1.4'), '2026-09-17'))
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            result = svc.get_fx_rates_batch([('USD', 'SGD')])
        assert result['USD-SGD'][0] == Decimal('1.4')
        mock_mgr.execute_query.assert_not_called()

    def test_exception_falls_back_to_one_for_unfetched_pairs(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = svc.get_fx_rates_batch([('USD', 'SGD')])
        assert result['USD-SGD'][0] == Decimal('1')

    def test_date_filter_applied_in_query(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            svc.get_fx_rates_batch([('USD', 'SGD')], rate_date='2026-09-17')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "'20260917'" in query


class TestConvertAmount:
    def test_same_currency_no_conversion(self):
        svc = _svc()
        converted, rate = svc.convert_amount(Decimal('100'), 'USD', 'USD')
        assert converted == Decimal('100')
        assert rate == Decimal('1')

    def test_applies_fx_rate(self):
        svc = _svc()
        with patch.object(svc, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-09-17')):
            converted, rate = svc.convert_amount(Decimal('100'), 'USD', 'SGD')
        assert converted == Decimal('135.00000000')
        assert rate == Decimal('1.35')


class TestCalculatePositionValues:
    def test_computes_local_and_base_values(self):
        svc = _svc()
        with patch.object(svc, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-09-17')):
            result = svc.calculate_position_values(
                quantity=Decimal('100'), avg_cost_local=Decimal('10'), current_price=Decimal('12'),
                security_currency='USD', portfolio_currency='SGD',
            )
        assert result['cost_value_local'] == 1000.0
        assert result['market_value_local'] == 1200.0
        assert result['unrealized_pnl_local'] == 200.0
        assert result['cost_value_base'] == 1350.0
        assert result['fx_rate'] == 1.35


class TestCalculateRealizedPnlMulticurrency:
    def test_computes_realized_pnl_both_currencies(self):
        svc = _svc()
        with patch.object(svc, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-09-17')):
            result = svc.calculate_realized_pnl_multicurrency(
                sell_quantity=Decimal('10'), sell_price=Decimal('15'), avg_cost=Decimal('10'),
                security_currency='USD', portfolio_currency='SGD',
            )
        assert result['realized_pnl_local'] == 50.0
        assert result['realized_pnl_base'] == 67.5


class TestGetPortfolioCurrency:
    def test_returns_currency(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'currency': 'SGD'}]
            assert svc.get_portfolio_currency('UOB-SG') == 'SGD'

    def test_returns_none_when_no_results(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert svc.get_portfolio_currency('UOB-SG') is None

    def test_returns_none_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_portfolio_currency('UOB-SG') is None


class TestGetSecurityCurrency:
    def test_returns_currency(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_currency': 'USD'}]
            assert svc.get_security_currency('AAPL') == 'USD'

    def test_returns_none_when_no_results(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert svc.get_security_currency('AAPL') is None

    def test_returns_none_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.multicurrency_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_security_currency('AAPL') is None


class TestGetPositionCurrencies:
    def test_returns_both_currencies(self):
        svc = _svc()
        with patch.object(svc, 'get_security_currency', return_value='USD'), \
             patch.object(svc, 'get_portfolio_currency', return_value='SGD'):
            sec_ccy, pf_ccy = svc.get_position_currencies('UOB-SG', 'AAPL')
        assert sec_ccy == 'USD'
        assert pf_ccy == 'SGD'


class TestRefreshPositionValues:
    def test_uses_current_price_when_given(self):
        svc = _svc()
        position = {
            'quantity': 100, 'average_cost': 10, 'security_currency': 'USD', 'portfolio_currency': 'SGD',
        }
        with patch.object(svc, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-09-17')):
            result = svc.refresh_position_values(position, current_price=Decimal('12'))
        assert result['market_value_local'] == 1200.0

    def test_uses_avg_cost_as_current_price_when_not_given(self):
        svc = _svc()
        position = {
            'quantity': 100, 'average_cost': 10, 'security_currency': 'USD', 'portfolio_currency': 'SGD',
        }
        with patch.object(svc, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-09-17')):
            result = svc.refresh_position_values(position)
        assert result['market_value_local'] == 1000.0  # falls back to avg_cost since no current_price key

    def test_defaults_currencies_to_usd_when_missing(self):
        svc = _svc()
        position = {'quantity': 100, 'average_cost': 10}
        with patch.object(svc, 'get_fx_rate', return_value=(Decimal('1'), '2026-09-17')) as mock_fx:
            svc.refresh_position_values(position)
        args = mock_fx.call_args[0]
        assert args[0] == 'USD'
        assert args[1] == 'USD'
