"""Tests for edge_jobs_py36/lib/trade_dropdown_service.py."""
from unittest.mock import patch, MagicMock

import pytest

from edge_jobs_py36.lib.trade_dropdown_service import (
    TradeDropdownService,
    UDF_BATCH_CACHE_KEY,
    DROPDOWN_ALL_CACHE_KEY,
)


def _svc():
    return TradeDropdownService()


@pytest.fixture(autouse=True)
def _no_cache():
    with patch('edge_jobs_py36.lib.trade_dropdown_service.cache') as mock_cache:
        mock_cache.get.return_value = None
        yield mock_cache


class TestGetCacheKey:
    def test_normalizes_spaces_and_slashes(self):
        svc = _svc()
        assert svc._get_cache_key('Fund Type') == 'udf_trade_fund_type'
        assert svc._get_cache_key('UOBN/UOBN-HK') == 'udf_trade_uobn_uobn-hk'


class TestLoadAllUdfFieldsBatch:
    def test_returns_cached_batch(self, _no_cache):
        cached = {'Fund Type': [{'value': 'EQUITY', 'label': 'Equity'}]}
        _no_cache.get.return_value = cached
        result = _svc()._load_all_udf_fields_batch()
        assert result is cached

    def test_groups_fields_by_name(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.udf_field_repository') as mock_repo:
            mock_repo.get_all.return_value = [
                {'field_name': 'Fund Type', 'field_value': 'equity_fund'},
                {'field_name': 'Fund Type', 'field_value': 'bond_fund'},
            ]
            result = svc._load_all_udf_fields_batch()
        assert len(result['Fund Type']) == 2
        assert result['Fund Type'][0]['label'] == 'Equity Fund'

    def test_skips_rows_missing_name_or_value(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.udf_field_repository') as mock_repo:
            mock_repo.get_all.return_value = [
                {'field_name': '', 'field_value': 'x'},
                {'field_name': 'Fund Type', 'field_value': ''},
            ]
            result = svc._load_all_udf_fields_batch()
        assert result == {}

    def test_returns_empty_dict_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.udf_field_repository') as mock_repo:
            mock_repo.get_all.side_effect = RuntimeError('boom')
            assert svc._load_all_udf_fields_batch() == {}

    def test_caches_batch_and_individual_fields(self, _no_cache):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.udf_field_repository') as mock_repo:
            mock_repo.get_all.return_value = [{'field_name': 'Fund Type', 'field_value': 'equity'}]
            svc._load_all_udf_fields_batch()
        assert _no_cache.set.call_count == 2  # batch + individual field


class TestGetUdfOptions:
    def test_returns_cached_options(self, _no_cache):
        cached = [{'value': 'x', 'label': 'X'}]
        _no_cache.get.return_value = cached
        result = _svc()._get_udf_options('Fund Type')
        assert result is cached

    def test_cache_error_falls_through_to_batch(self, _no_cache):
        svc = _svc()
        _no_cache.get.side_effect = RuntimeError('cache down')
        with patch.object(svc, '_load_all_udf_fields_batch', return_value={'Fund Type': [{'value': 'x'}]}):
            result = svc._get_udf_options('Fund Type')
        assert result == [{'value': 'x'}]

    def test_batch_hit_returns_options(self):
        svc = _svc()
        with patch.object(svc, '_load_all_udf_fields_batch', return_value={'Fund Type': [{'value': 'x'}]}):
            result = svc._get_udf_options('Fund Type')
        assert result == [{'value': 'x'}]

    def test_batch_miss_falls_back_to_single_query(self):
        svc = _svc()
        with patch.object(svc, '_load_all_udf_fields_batch', return_value={}), \
             patch('edge_jobs_py36.lib.trade_dropdown_service.udf_field_repository') as mock_repo:
            mock_repo.get_field_values.return_value = [{'field_value': 'equity_fund'}]
            result = svc._get_udf_options('Fund Type')
        assert result[0]['label'] == 'Equity Fund'

    def test_returns_empty_list_when_nothing_found(self):
        svc = _svc()
        with patch.object(svc, '_load_all_udf_fields_batch', return_value={}), \
             patch('edge_jobs_py36.lib.trade_dropdown_service.udf_field_repository') as mock_repo:
            mock_repo.get_field_values.return_value = []
            result = svc._get_udf_options('Fund Type')
        assert result == []

    def test_returns_empty_list_on_fallback_exception(self):
        svc = _svc()
        with patch.object(svc, '_load_all_udf_fields_batch', side_effect=RuntimeError('boom')), \
             patch('edge_jobs_py36.lib.trade_dropdown_service.udf_field_repository') as mock_repo:
            mock_repo.get_field_values.side_effect = RuntimeError('boom2')
            result = svc._get_udf_options('Fund Type')
        assert result == []


class TestInvalidateUdfCache:
    def test_invalidates_specific_field_and_batch(self, _no_cache):
        svc = _svc()
        svc.invalidate_udf_cache('Fund Type')
        assert _no_cache.delete.call_count == 2

    def test_no_field_only_invalidates_batch(self, _no_cache):
        svc = _svc()
        svc.invalidate_udf_cache()
        _no_cache.delete.assert_called_once_with(UDF_BATCH_CACHE_KEY)

    def test_swallows_exception(self, _no_cache):
        _no_cache.delete.side_effect = RuntimeError('boom')
        _svc().invalidate_udf_cache('Fund Type')  # must not raise


class TestWarmUdfCache:
    def test_returns_count_of_fields(self):
        svc = _svc()
        with patch.object(svc, '_load_all_udf_fields_batch', return_value={'a': [], 'b': []}):
            assert svc.warm_udf_cache() == 2

    def test_returns_zero_on_exception(self):
        svc = _svc()
        with patch.object(svc, '_load_all_udf_fields_batch', side_effect=RuntimeError('boom')):
            assert svc.warm_udf_cache() == 0


class TestGetAllDropdownOptions:
    def test_returns_cached_result(self, _no_cache):
        cached = {'trade_types': []}
        _no_cache.get.return_value = cached
        result = _svc().get_all_dropdown_options()
        assert result is cached

    def test_builds_full_result_with_all_loaders_mocked(self):
        svc = _svc()
        with patch.object(svc, '_load_all_udf_fields_batch', return_value={}), \
             patch.object(svc, 'get_portfolios', return_value=[]), \
             patch.object(svc, 'get_currencies', return_value=[]), \
             patch.object(svc, 'get_securities', return_value=[]), \
             patch.object(svc, 'get_counterparties', return_value=[]), \
             patch.object(svc, 'get_brokers', return_value=[]), \
             patch.object(svc, 'get_custodians', return_value=[]):
            result = svc.get_all_dropdown_options()
        assert 'trade_types' in result
        assert 'portfolios' in result
        assert 'selling_rules' in result

    def test_udf_loader_exception_defaults_to_empty_list(self):
        svc = _svc()
        with patch.object(svc, '_load_all_udf_fields_batch', return_value={}), \
             patch.object(svc, 'get_selling_rules', side_effect=RuntimeError('boom')), \
             patch.object(svc, 'get_portfolios', return_value=[]), \
             patch.object(svc, 'get_currencies', return_value=[]), \
             patch.object(svc, 'get_securities', return_value=[]), \
             patch.object(svc, 'get_counterparties', return_value=[]), \
             patch.object(svc, 'get_brokers', return_value=[]), \
             patch.object(svc, 'get_custodians', return_value=[]):
            result = svc.get_all_dropdown_options()
        assert result['selling_rules'] == []

    def test_entity_loader_exception_defaults_to_empty_list(self):
        svc = _svc()
        with patch.object(svc, '_load_all_udf_fields_batch', return_value={}), \
             patch.object(svc, 'get_portfolios', side_effect=RuntimeError('boom')), \
             patch.object(svc, 'get_currencies', return_value=[]), \
             patch.object(svc, 'get_securities', return_value=[]), \
             patch.object(svc, 'get_counterparties', return_value=[]), \
             patch.object(svc, 'get_brokers', return_value=[]), \
             patch.object(svc, 'get_custodians', return_value=[]):
            result = svc.get_all_dropdown_options()
        assert result['portfolios'] == []


class TestInvalidateDropdownCache:
    def test_deletes_cache_key(self, _no_cache):
        _svc().invalidate_dropdown_cache()
        _no_cache.delete.assert_called_once_with(DROPDOWN_ALL_CACHE_KEY)

    def test_swallows_exception(self, _no_cache):
        _no_cache.delete.side_effect = RuntimeError('boom')
        _svc().invalidate_dropdown_cache()  # must not raise


class TestStaticOptions:
    def test_trade_types_only_buy_sell(self):
        values = [o['value'] for o in _svc().get_trade_types()]
        assert values == ['BUY', 'SELL']

    def test_trade_statuses_returns_workflow_list(self):
        values = [o['value'] for o in _svc().get_trade_statuses()]
        assert 'INITIAL' in values
        assert 'SETTLED' in values


class TestGetPortfolios:
    def test_manager_and_currency_combined(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.trade_validation_repository') as mock_repo:
            mock_repo.get_valid_portfolios.return_value = [
                {'portfolio_short_name': 'UOB-SG', 'manager': 'M1', 'currency': 'USD'},
            ]
            result = svc.get_portfolios()
        assert result[0]['full_name'] == 'M1 (USD)'

    def test_manager_only(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.trade_validation_repository') as mock_repo:
            mock_repo.get_valid_portfolios.return_value = [
                {'portfolio_short_name': 'UOB-SG', 'manager': 'M1', 'currency': ''},
            ]
            result = svc.get_portfolios()
        assert result[0]['full_name'] == 'M1'

    def test_neither_falls_back_to_short_name(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.trade_validation_repository') as mock_repo:
            mock_repo.get_valid_portfolios.return_value = [
                {'portfolio_short_name': 'UOB-SG', 'manager': '', 'currency': ''},
            ]
            result = svc.get_portfolios()
        assert result[0]['full_name'] == 'UOB-SG'


class TestGetSecurities:
    def test_maps_fields(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.trade_validation_repository') as mock_repo:
            mock_repo.get_valid_securities.return_value = [
                {'security_label': 'AAPL', 'isin': 'US1', 'currency_code': 'USD'},
            ]
            result = svc.get_securities()
        assert result[0]['value'] == 'AAPL'
        assert result[0]['isin'] == 'US1'


class TestGetCounterparties:
    def test_maps_fields(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.trade_validation_repository') as mock_repo:
            mock_repo.get_valid_counterparties.return_value = [
                {'party_short_name': 'BROKER1', 'party_full_name': 'Broker One', 'is_broker': True},
            ]
            result = svc.get_counterparties()
        assert result[0]['value'] == 'BROKER1'
        assert result[0]['is_broker'] is True


class TestGetBrokers:
    def test_returns_query_results(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'value': 'BROKER1', 'label': 'Broker One'}]
            result = svc.get_brokers()
        assert result[0]['label'] == 'Broker One (BROKER1)'

    def test_falls_back_to_defaults_when_empty(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = svc.get_brokers()
        assert any(o['value'] == 'UOB KAY HIAN' for o in result)

    def test_falls_back_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = svc.get_brokers()
        assert any(o['value'] == 'DBS VICKERS' for o in result)


class TestGetCustodians:
    def test_returns_query_results(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'value': 'DBS', 'label': 'DBS Bank'}]
            result = svc.get_custodians()
        assert result[0]['label'] == 'DBS Bank (DBS)'

    def test_falls_back_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = svc.get_custodians()
        assert any(o['value'] == 'HSBC' for o in result)


class TestGlLookups:
    def test_gl_fund_types_returns_results(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'value': 'FUND1', 'label': 'FUND1'}]
            assert svc.get_gl_fund_types() == [{'value': 'FUND1', 'label': 'FUND1'}]

    def test_gl_fund_types_empty_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_gl_fund_types() == []

    def test_gl_cost_centres_always_empty(self):
        assert _svc().get_gl_cost_centres() == []

    def test_gl_account_codes_returns_results(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'value': 'GL1', 'label': 'GL1'}]
            assert svc.get_gl_account_codes() == [{'value': 'GL1', 'label': 'GL1'}]


class TestUdfBackedOptionsWithFallback:
    """Every get_* method here follows: try _get_udf_options, else hardcoded defaults."""

    @pytest.mark.parametrize('method_name,udf_field', [
        ('get_selling_rules', 'Selling Rule'),
        ('get_open_close_options', 'Open/Close Position'),
        ('get_extensions', 'Extension'),
        ('get_fund_types', 'Fund Type'),
        ('get_income_exp_types', 'Income/Exp Type'),
        ('get_uobn_options', 'UOBN/UOBN-HK'),
        ('get_section_options', 'Section 31/26'),
        ('get_revision_codes', 'Revision Code'),
        ('get_amor_methods', 'Amortisation Method'),
        ('get_delivery_types', 'Delivery Type'),
        ('get_income_types', 'Income Type'),
        ('get_split_types', 'Split Type'),
        ('get_reduction_types', 'Reduction Type'),
    ])
    def test_returns_udf_options_when_present(self, method_name, udf_field):
        svc = _svc()
        with patch.object(svc, '_get_udf_options', return_value=[{'value': 'CUSTOM', 'label': 'Custom'}]) as mock_get:
            result = getattr(svc, method_name)()
        assert result == [{'value': 'CUSTOM', 'label': 'Custom'}]
        mock_get.assert_called_once_with(udf_field)

    @pytest.mark.parametrize('method_name', [
        'get_selling_rules', 'get_open_close_options', 'get_extensions', 'get_fund_types',
        'get_income_exp_types', 'get_uobn_options', 'get_section_options', 'get_revision_codes',
        'get_amor_methods', 'get_delivery_types', 'get_income_types', 'get_split_types',
        'get_reduction_types',
    ])
    def test_falls_back_to_defaults_when_udf_empty(self, method_name):
        svc = _svc()
        with patch.object(svc, '_get_udf_options', return_value=[]):
            result = getattr(svc, method_name)()
        assert len(result) > 0


class TestGetCurrencies:
    def test_combines_security_and_equity_price_currencies(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [
                [{'currency_code': 'USD'}],
                [{'currency_code': 'SGD'}],
            ]
            result = svc.get_currencies()
        values = {o['value'] for o in result}
        assert values == {'USD', 'SGD'}

    def test_falls_back_to_defaults_when_none_found(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = svc.get_currencies()
        assert any(o['value'] == 'USD' for o in result)

    def test_one_query_failing_does_not_break_the_other(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [RuntimeError('boom'), [{'currency_code': 'EUR'}]]
            result = svc.get_currencies()
        assert any(o['value'] == 'EUR' for o in result)


class TestGetSecuritiesByCurrency:
    def test_empty_currency_returns_empty_list(self):
        assert _svc().get_securities_by_currency('') == []

    def test_merges_security_and_price_data(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [
                [{'security_name': 'AAPL', 'isin': 'US1', 'market': 'NASDAQ'}],
                [{'security_label': 'AAPL', 'isin': 'US1', 'price': 150.0, 'price_date': '2026-09-17'}],
            ]
            result = svc.get_securities_by_currency('USD')
        assert result[0]['price'] == 150.0
        assert result[0]['market'] == 'NASDAQ'

    def test_price_only_row_creates_new_entry(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [
                [],
                [{'security_label': 'MSFT', 'isin': 'US2', 'price': 300.0, 'price_date': '2026-09-17'}],
            ]
            result = svc.get_securities_by_currency('USD')
        assert result[0]['value'] == 'MSFT'

    def test_zero_price_does_not_overwrite_existing(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = [
                [{'security_name': 'AAPL', 'isin': 'US1', 'market': 'NASDAQ'}],
                [{'security_label': 'AAPL', 'isin': 'US1', 'price': 0, 'price_date': '2026-09-17'}],
            ]
            result = svc.get_securities_by_currency('USD')
        assert result[0]['price'] == 0

    def test_query_exception_does_not_crash(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_securities_by_currency('USD') == []


class TestGetEquityPrice:
    def test_empty_security_label_returns_not_found(self):
        assert _svc().get_equity_price('') == {'price': 0, 'found': False}

    def test_returns_price_when_found(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'security_label': 'AAPL', 'currency_code': 'USD', 'price': 150.0, 'price_date': '2026-09-17', 'isin': 'US1'},
            ]
            result = svc.get_equity_price('AAPL')
        assert result['found'] is True
        assert result['price'] == 150.0

    def test_zero_price_returns_not_found(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'price': 0}]
            result = svc.get_equity_price('AAPL')
        assert result['found'] is False

    def test_currency_filter_applied_when_given(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            svc.get_equity_price('AAPL', currency_code='USD')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "currency_code = 'USD'" in query

    def test_exception_returns_not_found(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = svc.get_equity_price('AAPL')
        assert result == {'price': 0, 'found': False}


class TestGetBrokerCharges:
    def test_empty_broker_returns_empty(self):
        assert _svc().get_broker_charges('') == []

    def test_returns_charges(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{
                'fee_type': 'Brokerage', 'broker': 'BROKER1', 'exchange': 'SGX',
                'fee_rule': 'Percent', 'fee_value': 0.5, 'rounding_method': 'Round Up',
            }]
            result = svc.get_broker_charges('BROKER1')
        assert result[0]['fee_type'] == 'Brokerage'

    def test_exchange_filter_applied(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            svc.get_broker_charges('BROKER1', exchange='SGX')
        query = mock_mgr.execute_query.call_args[0][0]
        assert "exchange = 'SGX'" in query

    def test_returns_empty_list_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_broker_charges('BROKER1') == []


class TestGetCurrencyDp:
    def test_empty_currency_returns_default(self):
        assert _svc()._get_currency_dp('') == TradeDropdownService._DEFAULT_FEE_ROUNDING_DP

    def test_parses_precision_string(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'precision': '0000000000.01'}]
            assert svc._get_currency_dp('USD') == 2

    def test_no_result_returns_default(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert svc._get_currency_dp('USD') == TradeDropdownService._DEFAULT_FEE_ROUNDING_DP

    def test_exception_returns_default(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert svc._get_currency_dp('USD') == TradeDropdownService._DEFAULT_FEE_ROUNDING_DP

    def test_precision_no_decimal_point_returns_default(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'precision': '1'}]
            assert svc._get_currency_dp('USD') == TradeDropdownService._DEFAULT_FEE_ROUNDING_DP


class TestRoundFee:
    def test_round_down_truncates(self):
        assert TradeDropdownService._round_fee(1.239, 'Round down', 2) == 1.23

    def test_round_up_rounds_away_from_zero(self):
        assert TradeDropdownService._round_fee(1.231, 'Round up', 2) == 1.24

    def test_default_uses_half_up(self):
        assert TradeDropdownService._round_fee(1.235, '', 2) == 1.24

    def test_unrecognized_method_uses_half_up(self):
        assert TradeDropdownService._round_fee(1.235, 'Weird Method', 2) == 1.24

    def test_zero_decimal_places(self):
        assert TradeDropdownService._round_fee(1.6, 'Round down', 0) == 1.0


class TestCalculateTradeCharges:
    def test_percent_fee_calculated_on_trade_value(self):
        svc = _svc()
        with patch.object(svc, 'get_broker_charges', return_value=[
            {'fee_type': 'Brokerage', 'fee_rule': 'Percent', 'fee_value': 1.0, 'rounding_method': 'Round Up'},
        ]), patch.object(svc, '_get_currency_dp', return_value=2):
            result = svc.calculate_trade_charges('BROKER1', 100, 10.0)
        assert result['trade_value'] == 1000.0
        assert result['charges'][0]['calculated_fee'] == 10.0

    def test_flat_fee_ignores_trade_value(self):
        svc = _svc()
        with patch.object(svc, 'get_broker_charges', return_value=[
            {'fee_type': 'Handling', 'fee_rule': 'Flat', 'fee_value': 5.0, 'rounding_method': ''},
        ]), patch.object(svc, '_get_currency_dp', return_value=2):
            result = svc.calculate_trade_charges('BROKER1', 100, 10.0)
        assert result['charges'][0]['calculated_fee'] == 5.0

    def test_gst_applied_on_subtotal_of_other_fees(self):
        svc = _svc()
        with patch.object(svc, 'get_broker_charges', return_value=[
            {'fee_type': 'Brokerage', 'fee_rule': 'Flat', 'fee_value': 10.0, 'rounding_method': ''},
            {'fee_type': 'GST', 'fee_rule': 'Percent', 'fee_value': 10.0, 'rounding_method': ''},
        ]), patch.object(svc, '_get_currency_dp', return_value=2):
            result = svc.calculate_trade_charges('BROKER1', 100, 10.0)
        gst_charge = next(c for c in result['charges'] if c['fee_type'] == 'GST')
        assert gst_charge['calculated_fee'] == 1.0  # 10% of 10.0

    def test_buy_adds_charges_to_grand_total(self):
        svc = _svc()
        with patch.object(svc, 'get_broker_charges', return_value=[
            {'fee_type': 'Fee', 'fee_rule': 'Flat', 'fee_value': 5.0, 'rounding_method': ''},
        ]), patch.object(svc, '_get_currency_dp', return_value=2):
            result = svc.calculate_trade_charges('BROKER1', 100, 10.0, trade_type='BUY')
        assert result['grand_total'] == 1005.0

    def test_sell_subtracts_charges_from_grand_total(self):
        svc = _svc()
        with patch.object(svc, 'get_broker_charges', return_value=[
            {'fee_type': 'Fee', 'fee_rule': 'Flat', 'fee_value': 5.0, 'rounding_method': ''},
        ]), patch.object(svc, '_get_currency_dp', return_value=2):
            result = svc.calculate_trade_charges('BROKER1', 100, 10.0, trade_type='SELL')
        assert result['grand_total'] == 995.0

    def test_unknown_fee_rule_treated_as_zero(self):
        svc = _svc()
        with patch.object(svc, 'get_broker_charges', return_value=[
            {'fee_type': 'Weird', 'fee_rule': 'unknown_rule', 'fee_value': 5.0, 'rounding_method': ''},
        ]), patch.object(svc, '_get_currency_dp', return_value=2):
            result = svc.calculate_trade_charges('BROKER1', 100, 10.0)
        assert result['charges'][0]['calculated_fee'] == 0.0

    def test_no_charges_returns_zero_total(self):
        svc = _svc()
        with patch.object(svc, 'get_broker_charges', return_value=[]), \
             patch.object(svc, '_get_currency_dp', return_value=2):
            result = svc.calculate_trade_charges('BROKER1', 100, 10.0)
        assert result['total_charges'] == 0.0
        assert result['grand_total'] == 1000.0


class TestGetExchanges:
    def test_returns_results_with_country_label(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'exchange': 'SGX', 'country_of_exchange': 'SG'}]
            result = svc.get_exchanges()
        assert result[0]['label'] == 'SGX (SG)'

    def test_returns_empty_list_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_exchanges() == []


class TestGetExchangesForBroker:
    def test_empty_broker_returns_empty(self):
        assert _svc().get_exchanges_for_broker('') == []

    def test_returns_results(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'exchange': 'SGX', 'country_of_exchange': 'SG'}]
            result = svc.get_exchanges_for_broker('BROKER1')
        assert result[0]['value'] == 'SGX'

    def test_returns_empty_list_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_exchanges_for_broker('BROKER1') == []


class TestGetBrokersFromChargeLut:
    def test_returns_results(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'broker': 'BROKER1'}]
            assert svc.get_brokers_from_charge_lut() == [{'value': 'BROKER1', 'label': 'BROKER1'}]

    def test_returns_empty_list_on_exception(self):
        svc = _svc()
        with patch('edge_jobs_py36.lib.trade_dropdown_service.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_brokers_from_charge_lut() == []
