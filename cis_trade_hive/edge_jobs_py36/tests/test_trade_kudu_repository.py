"""Tests for edge_jobs_py36/lib/trade_kudu_repository.py."""
import sys
import types
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from edge_jobs_py36.lib.trade_kudu_repository import TradeKuduRepository
from edge_jobs_py36.lib.trade_validation_repository import ValidationResult


@pytest.fixture
def repo():
    return TradeKuduRepository()


@pytest.fixture
def impala():
    with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
        m.execute_write.return_value = True
        m.execute_query.return_value = []
        m.execute_write_async.return_value = True
        yield m


@pytest.fixture
def qcache():
    with patch('edge_jobs_py36.lib.trade_kudu_repository.query_cache') as m:
        m.get.return_value = None
        yield m


@pytest.fixture
def valid_refs():
    """Patch trade_validation_repository.validate_trade_references to succeed."""
    with patch('edge_jobs_py36.lib.trade_kudu_repository.trade_validation_repository') as m:
        m.validate_trade_references.return_value = (True, [
            ValidationResult(is_valid=True, entity_type='PORTFOLIO', entity_name='P1', message='ok',
                              details={'name': 'P1', 'currency': 'USD'}),
            ValidationResult(is_valid=True, entity_type='SECURITY', entity_name='S1', message='ok',
                              details={'security_name': 'S1', 'currency_code': 'USD', 'security_type': 'EQ'}),
        ])
        m.get_validation_errors.return_value = []
        m.get_portfolio_details.return_value = {'name': 'P1', 'currency': 'USD'}
        m.get_security_details.return_value = {'security_name': 'S1', 'currency_code': 'USD'}
        yield m


class TestEscapeValue:
    def test_none_returns_null(self, repo):
        assert repo.escape_value(None) == 'NULL'

    def test_string_quoted_and_escaped(self, repo):
        assert repo.escape_value("O'Brien") == "'O\\'Brien'"

    def test_bool_lowercased(self, repo):
        assert repo.escape_value(True) == 'true'
        assert repo.escape_value(False) == 'false'

    def test_number_passthrough(self, repo):
        assert repo.escape_value(5) == '5'


class TestToDecimal:
    def test_none_returns_default(self, repo):
        assert repo.to_decimal(None) == '0'

    def test_empty_string_returns_default(self, repo):
        assert repo.to_decimal('') == '0'

    def test_whitespace_string_returns_default(self, repo):
        assert repo.to_decimal('   ') == '0'

    def test_valid_string_number(self, repo):
        assert repo.to_decimal('12.5') == '12.5'

    def test_valid_number(self, repo):
        assert repo.to_decimal(12.5) == '12.5'

    def test_invalid_returns_default(self, repo):
        assert repo.to_decimal('abc', default=99) == '99.0' or repo.to_decimal('abc', default=99) == '99'

    def test_custom_default(self, repo):
        assert repo.to_decimal(None, default=5) == '5'


class TestGetNextId:
    def test_returns_int(self, repo):
        assert isinstance(repo.get_next_id('trade_id'), int)


class TestValidateTradeData:
    def test_missing_required_fields(self, repo, valid_refs):
        valid_refs.validate_trade_references.return_value = (False, [])
        valid_refs.get_validation_errors.return_value = []
        ok, errors, entity_details = repo.validate_trade_data({})
        assert ok is False
        assert any('Portfolio is required' in e for e in errors)
        assert any('Security is required' in e for e in errors)

    def test_valid_buy_trade(self, repo, valid_refs):
        trade_data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
            'trade_date': '2026-01-01', 'counterparty': 'CP1',
            'quantity': 10, 'price': 100, 'open_fx_rate': 1.0,
        }
        ok, errors, entity_details = repo.validate_trade_data(trade_data)
        assert ok is True
        assert entity_details['portfolio']['name'] == 'P1'

    def test_buy_missing_quantity(self, repo, valid_refs):
        trade_data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
            'trade_date': '2026-01-01', 'counterparty': 'CP1', 'price': 100,
        }
        ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is False
        assert any('Quantity is required' in e for e in errors)

    def test_buy_zero_quantity(self, repo, valid_refs):
        # quantity=0 is falsy, so it hits the "Quantity is required" branch,
        # not the "greater than zero" check (only reached for a truthy-but-<=0 value).
        trade_data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
            'trade_date': '2026-01-01', 'counterparty': 'CP1', 'quantity': 0, 'price': 100,
        }
        ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is False
        assert any('Quantity is required' in e for e in errors)

    def test_buy_invalid_quantity_type(self, repo, valid_refs):
        trade_data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
            'trade_date': '2026-01-01', 'counterparty': 'CP1', 'quantity': 'abc', 'price': 100,
        }
        ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is False
        assert any('valid number' in e for e in errors)

    def test_buy_missing_price(self, repo, valid_refs):
        trade_data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
            'trade_date': '2026-01-01', 'counterparty': 'CP1', 'quantity': 10,
        }
        ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is False
        assert any('Price is required' in e for e in errors)

    def test_buy_negative_price(self, repo, valid_refs):
        trade_data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
            'trade_date': '2026-01-01', 'counterparty': 'CP1', 'quantity': 10, 'price': -1,
        }
        ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is False
        assert any('not be negative' in e for e in errors)

    def test_buy_invalid_fx_rate(self, repo, valid_refs):
        trade_data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
            'trade_date': '2026-01-01', 'counterparty': 'CP1', 'quantity': 10, 'price': 100,
            'open_fx_rate': 0,
        }
        ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is False
        assert any('FX rate must be greater than zero' in e for e in errors)

    def test_buy_missing_fx_rate_cross_currency_required(self, repo, valid_refs):
        valid_refs.validate_trade_references.return_value = (True, [
            ValidationResult(is_valid=True, entity_type='PORTFOLIO', entity_name='P1', message='ok',
                              details={'name': 'P1', 'currency': 'SGD'}),
            ValidationResult(is_valid=True, entity_type='SECURITY', entity_name='S1', message='ok',
                              details={'security_name': 'S1', 'currency_code': 'USD'}),
        ])
        trade_data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
            'trade_date': '2026-01-01', 'counterparty': 'CP1', 'quantity': 10, 'price': 100,
        }
        ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is False
        assert any('FX rate is required' in e for e in errors)

    def test_sell_no_trade_detail(self, repo, valid_refs):
        with patch.object(repo, 'get_trade_detail', return_value=None):
            trade_data = {
                'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'SELL',
                'trade_date': '2026-01-01', 'counterparty': 'CP1', 'quantity': 10, 'price': 100,
                'open_fx_rate': 1.0,
            }
            ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is False
        assert any('No trade detail found' in e for e in errors)

    def test_sell_insufficient_quantity(self, repo, valid_refs):
        with patch.object(repo, 'get_trade_detail', return_value={'quantity': 5}):
            trade_data = {
                'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'SELL',
                'trade_date': '2026-01-01', 'counterparty': 'CP1', 'quantity': 10, 'price': 100,
                'open_fx_rate': 1.0,
            }
            ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is False
        assert any('Insufficient quantity' in e for e in errors)

    def test_sell_sufficient_quantity(self, repo, valid_refs):
        with patch.object(repo, 'get_trade_detail', return_value={'quantity': 100}):
            trade_data = {
                'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'SELL',
                'trade_date': '2026-01-01', 'counterparty': 'CP1', 'quantity': 10, 'price': 100,
                'open_fx_rate': 1.0,
            }
            ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is True

    def test_non_buy_sell_type_skips_price_qty_checks(self, repo, valid_refs):
        trade_data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'INCOME',
            'trade_date': '2026-01-01', 'counterparty': 'CP1',
        }
        ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is True

    def test_validation_reference_failure_adds_errors(self, repo, valid_refs):
        valid_refs.validate_trade_references.return_value = (False, [])
        valid_refs.get_validation_errors.return_value = ['Portfolio not found']
        trade_data = {
            'portfolio_short_name': 'BAD', 'security_label': 'S1', 'trade_type': 'INCOME',
            'trade_date': '2026-01-01', 'counterparty': 'CP1',
        }
        ok, errors, _ = repo.validate_trade_data(trade_data)
        assert ok is False
        assert 'Portfolio not found' in errors


class TestGetAllTrades:
    def test_delegates_to_multi_filter(self, repo):
        with patch.object(repo, 'get_all_trades_multi_filter', return_value=[{'trade_id': 1}]) as m:
            result = repo.get_all_trades(portfolio='P1', security='S1')
        assert result == [{'trade_id': 1}]
        kwargs = m.call_args[1]
        assert kwargs['portfolios'] == ['P1']
        assert kwargs['securities'] == ['S1']

    def test_none_portfolio_security_passthrough(self, repo):
        with patch.object(repo, 'get_all_trades_multi_filter', return_value=[]) as m:
            repo.get_all_trades()
        kwargs = m.call_args[1]
        assert kwargs['portfolios'] is None
        assert kwargs['securities'] is None


class TestGetAllTradesMultiFilter:
    def test_simple_query_cache_hit(self, repo, qcache):
        qcache.get.return_value = [{'trade_id': 1}]
        result = repo.get_all_trades_multi_filter(status='INITIAL')
        assert result == [{'trade_id': 1}]

    def test_simple_query_cache_miss_queries_and_sets(self, repo, impala, qcache):
        impala.execute_query.return_value = [{'trade_id': 1}]
        result = repo.get_all_trades_multi_filter(status='INITIAL')
        assert result == [{'trade_id': 1}]
        qcache.set.assert_called_once()

    def test_complex_query_not_cached(self, repo, impala, qcache):
        impala.execute_query.return_value = [{'trade_id': 1}]
        repo.get_all_trades_multi_filter(search='ABC')
        qcache.set.assert_not_called()

    def test_trade_type_filter(self, repo, impala):
        repo.get_all_trades_multi_filter(trade_type='BUY')
        query = impala.execute_query.call_args[0][0]
        assert "t.trade_type = 'BUY'" in query

    def test_status_filter_case_insensitive(self, repo, impala):
        repo.get_all_trades_multi_filter(status='initial')
        query = impala.execute_query.call_args[0][0]
        assert "UPPER(t.status) = 'INITIAL'" in query

    def test_src_system_filter(self, repo, impala):
        repo.get_all_trades_multi_filter(src_system='cis')
        query = impala.execute_query.call_args[0][0]
        assert "UPPER(t.src_system) = 'CIS'" in query

    def test_multi_portfolio_filter(self, repo, impala):
        repo.get_all_trades_multi_filter(portfolios=['P1', 'P2'])
        query = impala.execute_query.call_args[0][0]
        assert "t.portfolio_short_name IN ('P1', 'P2')" in query

    def test_multi_security_filter(self, repo, impala):
        repo.get_all_trades_multi_filter(securities=['S1', 'S2'])
        query = impala.execute_query.call_args[0][0]
        assert "t.security_label IN ('S1', 'S2')" in query

    def test_search_filter(self, repo, impala):
        repo.get_all_trades_multi_filter(search="O'Brien")
        query = impala.execute_query.call_args[0][0]
        assert "LIKE '%O\\'Brien%'" in query

    def test_date_range_filters(self, repo, impala):
        repo.get_all_trades_multi_filter(
            trade_date_from='2026-01-01', trade_date_to='2026-01-31',
            settle_date_from='2026-02-01', settle_date_to='2026-02-28',
        )
        query = impala.execute_query.call_args[0][0]
        assert "t.trade_date >= '2026-01-01'" in query
        assert "t.trade_date <= '2026-01-31'" in query
        assert "t.settle_date >= '2026-02-01'" in query
        assert "t.settle_date <= '2026-02-28'" in query

    def test_none_result_returns_empty_list(self, repo, impala):
        impala.execute_query.return_value = None
        assert repo.get_all_trades_multi_filter(search='x') == []

    def test_exception_returns_empty_list(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_all_trades_multi_filter(search='x') == []


class TestGetTradeById:
    def test_returns_first_result(self, repo, impala):
        impala.execute_query.return_value = [{'trade_id': 1}]
        assert repo.get_trade_by_id(1) == {'trade_id': 1}

    def test_no_result_returns_none(self, repo, impala):
        impala.execute_query.return_value = []
        assert repo.get_trade_by_id(1) is None

    def test_exception_returns_none(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_trade_by_id(1) is None


class TestGetTradeByDealNumber:
    def test_returns_first_result(self, repo, impala):
        impala.execute_query.return_value = [{'deal_number': 'D1'}]
        assert repo.get_trade_by_deal_number('D1') == {'deal_number': 'D1'}

    def test_no_result_returns_none(self, repo, impala):
        impala.execute_query.return_value = []
        assert repo.get_trade_by_deal_number('D1') is None

    def test_exception_returns_none(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_trade_by_deal_number('D1') is None


class TestInsertTrade:
    def base_trade_data(self, **overrides):
        data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
            'trade_date': '2026-01-01', 'counterparty': 'CP1',
            'quantity': 10, 'price': 100, 'open_fx_rate': 1.0,
        }
        data.update(overrides)
        return data

    def test_validation_failure_raises(self, repo, valid_refs):
        valid_refs.validate_trade_references.return_value = (False, [])
        valid_refs.get_validation_errors.return_value = ['bad data']
        with pytest.raises(ValueError):
            repo.insert_trade({}, 'user1')

    def test_success_returns_trade_id(self, repo, valid_refs, impala):
        with patch.object(repo, 'insert_trade_history', return_value=True), \
             patch.object(repo, 'invalidate_statistics_cache'):
            trade_id = repo.insert_trade(self.base_trade_data(), 'user1')
        assert isinstance(trade_id, int)

    def test_write_failure_returns_none(self, repo, valid_refs, impala):
        impala.execute_write.return_value = False
        result = repo.insert_trade(self.base_trade_data(), 'user1')
        assert result is None

    def test_missing_entity_details_refetches(self, repo, valid_refs, impala):
        valid_refs.validate_trade_references.return_value = (True, [])
        with patch.object(repo, 'insert_trade_history', return_value=True), \
             patch.object(repo, 'invalidate_statistics_cache'):
            trade_id = repo.insert_trade(self.base_trade_data(), 'user1')
        valid_refs.get_portfolio_details.assert_called_once()
        valid_refs.get_security_details.assert_called_once()
        assert isinstance(trade_id, int)

    def test_portfolio_currency_queried_directly(self, repo, valid_refs, impala):
        impala.execute_query.return_value = [{'currency': 'SGD'}]
        with patch.object(repo, 'insert_trade_history', return_value=True), \
             patch.object(repo, 'invalidate_statistics_cache'):
            repo.insert_trade(self.base_trade_data(), 'user1')
        query = impala.execute_query.call_args[0][0]
        assert 'SELECT currency FROM' in query

    def test_exception_raises(self, repo):
        with patch.object(repo, 'validate_trade_data', side_effect=RuntimeError('boom')):
            with pytest.raises(RuntimeError):
                repo.insert_trade({}, 'user1')


class TestInsertTradeFast:
    def base_trade_data(self, **overrides):
        data = {
            'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
            'trade_date': '2026-01-01', 'counterparty': 'CP1',
            'quantity': 10, 'price': 100, 'open_fx_rate': 1.0,
        }
        data.update(overrides)
        return data

    def test_skip_validation_with_entity_details(self, repo, impala):
        entity_details = {'portfolio': {'currency': 'USD'}, 'security': {'security_name': 'S1'}}
        with patch.object(repo, 'invalidate_statistics_cache'), \
             patch.object(repo, '_queue_trade_events'):
            trade_id, deal_number = repo.insert_trade_fast(
                self.base_trade_data(), 'user1', skip_validation=True, entity_details=entity_details,
            )
        assert isinstance(trade_id, int)
        assert deal_number is not None

    def test_skip_validation_without_entity_details_basic_check(self, repo, impala):
        with patch.object(repo, 'invalidate_statistics_cache'), \
             patch.object(repo, '_queue_trade_events'):
            trade_id, deal_number = repo.insert_trade_fast(
                self.base_trade_data(), 'user1', skip_validation=True,
            )
        assert isinstance(trade_id, int)

    def test_skip_validation_missing_required_field_raises(self, repo):
        with pytest.raises(ValueError):
            repo.insert_trade_fast({}, 'user1', skip_validation=True)

    def test_full_validation_path(self, repo, valid_refs, impala):
        with patch.object(repo, 'invalidate_statistics_cache'), \
             patch.object(repo, '_queue_trade_events'):
            trade_id, deal_number = repo.insert_trade_fast(
                self.base_trade_data(), 'user1', skip_validation=False,
            )
        assert isinstance(trade_id, int)

    def test_validation_failure_raises(self, repo, valid_refs):
        valid_refs.validate_trade_references.return_value = (False, [])
        valid_refs.get_validation_errors.return_value = ['bad']
        with pytest.raises(ValueError):
            repo.insert_trade_fast({}, 'user1', skip_validation=False)

    def test_write_failure_returns_none_none(self, repo, impala):
        impala.execute_write.return_value = False
        result = repo.insert_trade_fast(self.base_trade_data(), 'user1', skip_validation=True)
        assert result == (None, None)

    def test_exception_raises(self, repo):
        with patch.object(repo, 'get_next_id', side_effect=RuntimeError('boom')):
            with pytest.raises(RuntimeError):
                repo.insert_trade_fast(self.base_trade_data(), 'user1', skip_validation=True)


class TestQueueTradeEvents:
    def test_queues_history_and_settlement(self, repo, impala):
        repo._queue_trade_events(
            trade_id=1, deal_number='D1', trade_data={'trade_type': 'BUY', 'quantity': 10, 'price': 100},
            created_by='user1', portfolio_details={'currency': 'USD'}, security_details={'currency_code': 'USD'},
        )
        assert impala.execute_write_async.call_count == 2

    def test_exception_swallowed(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_write_async.side_effect = RuntimeError('boom')
            # Should not raise
            repo._queue_trade_events(
                trade_id=1, deal_number='D1', trade_data={}, created_by='user1',
                portfolio_details={}, security_details={},
            )


class TestUpdateTrade:
    def test_trade_not_found_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value=None):
            with pytest.raises(ValueError):
                repo.update_trade(1, {}, 'user1')

    def test_validation_failure_raises(self, repo, valid_refs):
        valid_refs.validate_trade_references.return_value = (False, [])
        valid_refs.get_validation_errors.return_value = ['bad']
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'INITIAL', 'deal_number': 'D1'}):
            with pytest.raises(ValueError):
                repo.update_trade(1, {}, 'user1')

    def test_no_changes_returns_true_without_write(self, repo, valid_refs, impala):
        current = {'status': 'INITIAL', 'deal_number': 'D1'}
        with patch.object(repo, 'get_trade_by_id', return_value=current):
            result = repo.update_trade(1, {
                'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'INCOME',
                'trade_date': '2026-01-01', 'counterparty': 'CP1',
            }, 'user1')
        assert result is True

    def test_field_change_updates_and_logs_history(self, repo, valid_refs, impala):
        current = {'status': 'INITIAL', 'deal_number': 'D1', 'quantity': 5}
        with patch.object(repo, 'get_trade_by_id', return_value=current), \
             patch.object(repo, 'insert_trade_history', return_value=True) as hist:
            result = repo.update_trade(1, {
                'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
                'trade_date': '2026-01-01', 'counterparty': 'CP1',
                'quantity': 10, 'price': 100, 'open_fx_rate': 1.0,
            }, 'user1')
        assert result is True
        hist.assert_called_once()

    def test_boolean_field_change(self, repo, valid_refs, impala):
        current = {'status': 'INITIAL', 'deal_number': 'D1', 'udf_disclosure_req': False}
        with patch.object(repo, 'get_trade_by_id', return_value=current), \
             patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.update_trade(1, {
                'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
                'trade_date': '2026-01-01', 'counterparty': 'CP1',
                'quantity': 10, 'price': 100, 'open_fx_rate': 1.0,
                'udf_disclosure_req': True,
            }, 'user1')
        assert result is True

    def test_exception_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', side_effect=RuntimeError('boom')):
            with pytest.raises(RuntimeError):
                repo.update_trade(1, {}, 'user1')


class TestQueuePositionRecalculation:
    def test_success_logs_info(self, repo):
        fake_module = types.ModuleType('trade.services.settlement_service')
        fake_svc = MagicMock()
        fake_svc.process_trade_settlement.return_value = (True, 'ok', {})
        fake_module.settlement_service = fake_svc
        with patch.dict(sys.modules, {'trade.services.settlement_service': fake_module}):
            repo._queue_position_recalculation(
                1, {'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY'},
                {'quantity': 10, 'price': 100}, 'user1',
            )
        fake_svc.process_trade_settlement.assert_called_once()

    def test_failure_logs_warning(self, repo):
        fake_module = types.ModuleType('trade.services.settlement_service')
        fake_svc = MagicMock()
        fake_svc.process_trade_settlement.return_value = (False, 'failed', None)
        fake_module.settlement_service = fake_svc
        with patch.dict(sys.modules, {'trade.services.settlement_service': fake_module}):
            repo._queue_position_recalculation(
                1, {'portfolio_short_name': 'P1'}, {}, 'user1',
            )

    def test_exception_swallowed(self, repo):
        fake_module = types.ModuleType('trade.services.settlement_service')
        fake_svc = MagicMock()
        fake_svc.process_trade_settlement.side_effect = RuntimeError('boom')
        fake_module.settlement_service = fake_svc
        with patch.dict(sys.modules, {'trade.services.settlement_service': fake_module}):
            repo._queue_position_recalculation(1, {}, {}, 'user1')  # should not raise


class TestSoftDeleteTrade:
    def test_returns_false_when_not_found(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value=None):
            result = repo.soft_delete_trade(1, 'user1')
        assert result is False

    def test_success(self, repo, impala):
        with patch.object(repo, 'get_trade_by_id', return_value={'deal_number': 'D1', 'status': 'INITIAL'}), \
             patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.soft_delete_trade(1, 'user1', reason='dup')
        assert result is True

    def test_exception_returns_false(self, repo):
        with patch.object(repo, 'get_trade_by_id', side_effect=RuntimeError('boom')):
            result = repo.soft_delete_trade(1, 'user1')
        assert result is False


class TestSubmitForValidation:
    def test_not_found_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value=None):
            with pytest.raises(ValueError):
                repo.submit_for_validation(1, 'user1')

    def test_invalid_status_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'SETTLED'}):
            with pytest.raises(ValueError):
                repo.submit_for_validation(1, 'user1')

    def test_success(self, repo, impala):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'INITIAL', 'deal_number': 'D1'}), \
             patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.submit_for_validation(1, 'user1')
        assert result is True


class TestValidateTrade:
    def test_not_found_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value=None):
            with pytest.raises(ValueError):
                repo.validate_trade(1, 'user1')

    def test_invalid_status_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'SETTLED', 'created_by': 'x'}):
            with pytest.raises(ValueError):
                repo.validate_trade(1, 'user1')

    def test_four_eyes_same_user_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'INITIAL', 'created_by': 'user1'}):
            with pytest.raises(ValueError, match='Four-eyes'):
                repo.validate_trade(1, 'user1')

    def test_success(self, repo, impala):
        with patch.object(repo, 'get_trade_by_id', return_value={
            'status': 'INITIAL', 'created_by': 'maker', 'deal_number': 'D1',
        }), patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.validate_trade(1, 'checker1', comments='ok')
        assert result is True


class TestRejectTrade:
    def test_not_found_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value=None):
            with pytest.raises(ValueError):
                repo.reject_trade(1, 'user1')

    def test_invalid_status_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'SETTLED'}):
            with pytest.raises(ValueError):
                repo.reject_trade(1, 'user1')

    def test_success(self, repo, impala):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'INITIAL', 'deal_number': 'D1'}), \
             patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.reject_trade(1, 'user1', reason='bad data')
        assert result is True


class TestCancelTrade:
    def test_not_found_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value=None):
            with pytest.raises(ValueError):
                repo.cancel_trade(1, 'user1')

    def test_success(self, repo, impala):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'SETTLED', 'deal_number': 'D1'}), \
             patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.cancel_trade(1, 'user1', reason='mistake')
        assert result is True


class TestRestoreTrade:
    def test_not_found_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value=None):
            with pytest.raises(ValueError):
                repo.restore_trade(1, 'user1')

    def test_non_cancelled_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'INITIAL'}):
            with pytest.raises(ValueError):
                repo.restore_trade(1, 'user1')

    def test_success(self, repo, impala):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'CANCELLED', 'deal_number': 'D1'}), \
             patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.restore_trade(1, 'user1')
        assert result is True


class TestSubmitForCancellation:
    def test_not_found_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value=None):
            with pytest.raises(ValueError):
                repo.submit_for_cancellation(1, 'user1')

    def test_success(self, repo, impala):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'SETTLED', 'deal_number': 'D1'}), \
             patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.submit_for_cancellation(1, 'user1', reason='dup')
        assert result is True


class TestApproveCancellation:
    def test_not_found_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value=None):
            with pytest.raises(ValueError):
                repo.approve_cancellation(1, 'user1')

    def test_not_pending_cancellation_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'INITIAL', 'is_deleted': False}):
            with pytest.raises(ValueError):
                repo.approve_cancellation(1, 'user1')

    def test_success(self, repo, impala):
        with patch.object(repo, 'get_trade_by_id', return_value={
            'status': 'MODIFIED', 'is_deleted': True, 'deal_number': 'D1',
        }), patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.approve_cancellation(1, 'user1', comments='ok')
        assert result is True


class TestRejectCancellation:
    def test_not_found_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value=None):
            with pytest.raises(ValueError):
                repo.reject_cancellation(1, 'user1')

    def test_not_pending_cancellation_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'INITIAL', 'is_deleted': False}):
            with pytest.raises(ValueError):
                repo.reject_cancellation(1, 'user1')

    def test_reverts_to_prior_status_from_history(self, repo, impala):
        with patch.object(repo, 'get_trade_by_id', return_value={
            'status': 'MODIFIED', 'is_deleted': True, 'deal_number': 'D1',
        }), patch.object(repo, 'get_trade_history', return_value=[
            {'action': 'CANCEL_REQUEST', 'old_status': 'SETTLED'},
        ]), patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.reject_cancellation(1, 'user1')
        assert result == 'SETTLED'

    def test_defaults_to_modified_when_no_history_match(self, repo, impala):
        with patch.object(repo, 'get_trade_by_id', return_value={
            'status': 'MODIFIED', 'is_deleted': True, 'deal_number': 'D1',
        }), patch.object(repo, 'get_trade_history', return_value=[]), \
             patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.reject_cancellation(1, 'user1')
        assert result == 'MODIFIED'


class TestSettleTrade:
    def test_not_found_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value=None):
            with pytest.raises(ValueError):
                repo.settle_trade(1, 'user1')

    def test_invalid_status_raises(self, repo):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'INITIAL'}):
            with pytest.raises(ValueError):
                repo.settle_trade(1, 'user1')

    def test_success(self, repo, impala):
        with patch.object(repo, 'get_trade_by_id', return_value={'status': 'VALIDATED', 'deal_number': 'D1'}), \
             patch.object(repo, 'insert_trade_history', return_value=True):
            result = repo.settle_trade(1, 'user1', comments='ok')
        assert result is True


class TestGetPosition:
    def test_returns_first_result(self, repo, impala):
        impala.execute_query.return_value = [{'position_id': 1}]
        assert repo.get_position('P1', 'S1') == {'position_id': 1}

    def test_no_result_returns_none(self, repo, impala):
        impala.execute_query.return_value = []
        assert repo.get_position('P1', 'S1') is None

    def test_exception_returns_none(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_position('P1', 'S1') is None


class TestGetTradeDetail:
    def test_delegates_to_get_position(self, repo):
        with patch.object(repo, 'get_position', return_value={'x': 1}) as m:
            result = repo.get_trade_detail('P1', 'S1')
        assert result == {'x': 1}
        m.assert_called_once_with('P1', 'S1', 'TRADED')


class TestGetPositionById:
    def test_returns_first_result(self, repo, impala):
        impala.execute_query.return_value = [{'position_id': 1}]
        assert repo.get_position_by_id(1) == {'position_id': 1}

    def test_exception_returns_none(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_position_by_id(1) is None


class TestGetAllPositions:
    def test_returns_results(self, repo, impala):
        impala.execute_query.return_value = [{'position_id': 1}]
        assert repo.get_all_positions() == [{'position_id': 1}]

    def test_status_filter(self, repo, impala):
        repo.get_all_positions(status='OPEN')
        query = impala.execute_query.call_args[0][0]
        assert "p.status = 'OPEN'" in query

    def test_none_result_returns_empty_list(self, repo, impala):
        impala.execute_query.return_value = None
        assert repo.get_all_positions() == []

    def test_exception_returns_empty_list(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_all_positions() == []


class TestGetPositionVersions:
    def test_returns_results(self, repo, impala):
        impala.execute_query.return_value = [{'version_id': 1}]
        assert repo.get_position_versions(1) == [{'version_id': 1}]

    def test_none_result_returns_empty_list(self, repo, impala):
        impala.execute_query.return_value = None
        assert repo.get_position_versions(1) == []

    def test_exception_returns_empty_list(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_position_versions(1) == []


class TestGetPositionStatistics:
    def test_returns_stats(self, repo, impala):
        impala.execute_query.return_value = [{
            'total_positions': 5, 'total_market_value': 1000.5,
            'total_unrealized_pnl': 50, 'total_realized_pnl': 10,
        }]
        stats = repo.get_position_statistics()
        assert stats['total_positions'] == 5
        assert stats['total_market_value'] == 1000.5

    def test_no_result_returns_zeros(self, repo, impala):
        impala.execute_query.return_value = []
        stats = repo.get_position_statistics()
        assert stats['total_positions'] == 0

    def test_exception_returns_zeros(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            stats = repo.get_position_statistics()
        assert stats['total_positions'] == 0


class TestGetEquityPrice:
    def test_returns_price(self, repo, impala):
        impala.execute_query.return_value = [{'main_closing_price': 100.5}]
        assert repo._get_equity_price('S1') == 100.5

    def test_no_result_returns_none(self, repo, impala):
        impala.execute_query.return_value = []
        assert repo._get_equity_price('S1') is None

    def test_none_price_returns_none(self, repo, impala):
        impala.execute_query.return_value = [{'main_closing_price': None}]
        assert repo._get_equity_price('S1') is None

    def test_exception_returns_none(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo._get_equity_price('S1') is None


class TestGetFxRate:
    def test_same_currency_returns_one(self, repo):
        assert repo._get_fx_rate('USD', 'USD') == 1.0

    def test_direct_pair_found(self, repo, impala):
        impala.execute_query.return_value = [{'spot_rate_d': 1.35}]
        assert repo._get_fx_rate('USD', 'SGD') == 1.35

    def test_reverse_pair_inverted(self, repo, impala):
        impala.execute_query.side_effect = [[], [{'spot_rate_d': 0.74}]]
        result = repo._get_fx_rate('USD', 'SGD')
        assert abs(result - (1 / 0.74)) < 0.0001

    def test_reverse_pair_zero_rate_returns_none(self, repo, impala):
        impala.execute_query.side_effect = [[], [{'spot_rate_d': 0}]]
        assert repo._get_fx_rate('USD', 'SGD') is None

    def test_no_rate_found_returns_none(self, repo, impala):
        impala.execute_query.side_effect = [[], []]
        assert repo._get_fx_rate('USD', 'SGD') is None

    def test_with_rate_date(self, repo, impala):
        impala.execute_query.return_value = [{'spot_rate_d': 1.35}]
        repo._get_fx_rate('USD', 'SGD', rate_date='20260101')
        query = impala.execute_query.call_args[0][0]
        assert "'20260101'" in query

    def test_exception_returns_none(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo._get_fx_rate('USD', 'SGD') is None


class TestGetPortfolioCurrency:
    def test_returns_currency(self, repo, impala):
        impala.execute_query.return_value = [{'currency': 'USD'}]
        assert repo._get_portfolio_currency('P1') == 'USD'

    def test_no_result_returns_none(self, repo, impala):
        impala.execute_query.return_value = []
        assert repo._get_portfolio_currency('P1') is None

    def test_exception_returns_none(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo._get_portfolio_currency('P1') is None


class TestGetSecurityDetailsPrivate:
    def test_returns_details(self, repo, impala):
        impala.execute_query.return_value = [{'security_currency': 'USD'}]
        assert repo._get_security_details('S1') == {'security_currency': 'USD'}

    def test_no_result_returns_none(self, repo, impala):
        impala.execute_query.return_value = []
        assert repo._get_security_details('S1') is None

    def test_exception_returns_none(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo._get_security_details('S1') is None


class TestUpdatePositionFromTrade:
    def common_mocks(self, repo, current_position=None, equity_price=100.0):
        return [
            patch.object(repo, 'get_position', return_value=current_position),
            patch.object(repo, '_get_equity_price', return_value=equity_price),
            patch.object(repo, '_get_portfolio_currency', return_value='USD'),
            patch.object(repo, '_get_security_details', return_value={'security_currency': 'USD', 'isin': 'ISIN1'}),
            patch.object(repo, '_get_fx_rate', return_value=1.0),
        ]

    def test_new_buy_position(self, repo):
        mocks = self.common_mocks(repo)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.object(repo, '_insert_position_version', return_value=True) as ins:
            trade = {'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'BUY',
                      'quantity': 10, 'price': 100, 'trade_id': 1, 'trade_date': '2026-01-01'}
            result = repo.update_position_from_trade(trade, 'user1')
        assert result is True
        ins.assert_called_once()

    def test_add_to_existing_buy_position(self, repo):
        current = {'position_id': 1, 'quantity': 100, 'average_cost': 90, 'realized_pnl': 0}
        mocks = self.common_mocks(repo, current_position=current)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.object(repo, '_insert_position_version', return_value=True) as ins:
            trade = {'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'ADD_LONG',
                      'quantity': 10, 'price': 100, 'trade_id': 1, 'trade_date': '2026-01-01'}
            result = repo.update_position_from_trade(trade, 'user1')
        assert result is True

    def test_full_close_sell(self, repo):
        current = {'position_id': 1, 'quantity': 10, 'average_cost': 90, 'realized_pnl': 0}
        mocks = self.common_mocks(repo, current_position=current)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.object(repo, '_insert_position_version', return_value=True) as ins:
            trade = {'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'SELL',
                      'quantity': 10, 'price': 100, 'total_amount': 1000, 'trade_id': 1, 'trade_date': '2026-01-01'}
            result = repo.update_position_from_trade(trade, 'user1')
        assert result is True
        call_kwargs = ins.call_args[1]
        assert call_kwargs['status'] == 'CLOSED'

    def test_partial_sell(self, repo):
        current = {'position_id': 1, 'quantity': 100, 'average_cost': 90, 'realized_pnl': 0}
        mocks = self.common_mocks(repo, current_position=current)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.object(repo, '_insert_position_version', return_value=True) as ins:
            trade = {'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'DELIVER_LONG',
                      'quantity': 10, 'price': 100, 'total_amount': 1000, 'trade_id': 1, 'trade_date': '2026-01-01'}
            result = repo.update_position_from_trade(trade, 'user1')
        assert result is True
        call_kwargs = ins.call_args[1]
        assert call_kwargs['status'] == 'OPEN'

    def test_sell_no_current_position_no_op(self, repo):
        mocks = self.common_mocks(repo, current_position=None)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
            trade = {'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'SELL',
                      'quantity': 10, 'price': 100, 'trade_id': 1, 'trade_date': '2026-01-01'}
            result = repo.update_position_from_trade(trade, 'user1')
        assert result is True

    def test_other_trade_type_no_op(self, repo):
        mocks = self.common_mocks(repo)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
            trade = {'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_type': 'INCOME',
                      'quantity': 10, 'price': 100, 'trade_id': 1, 'trade_date': '2026-01-01'}
            result = repo.update_position_from_trade(trade, 'user1')
        assert result is True

    def test_exception_returns_false(self, repo):
        with patch.object(repo, 'get_position', side_effect=RuntimeError('boom')):
            result = repo.update_position_from_trade({'trade_type': 'BUY'}, 'user1')
        assert result is False


class TestInsertPositionVersion:
    def test_success(self, repo, impala):
        result = repo._insert_position_version(
            version_id=1, position_id=2, position_date='2026-01-01',
            portfolio='P1', security='S1', quantity=10, average_cost=100,
            total_cost=1000, realized_pnl=0, current_price=105, market_value=1050,
            unrealized_pnl=50, trade_id=1, trade_type='BUY', status='OPEN',
            is_active=True, created_by='user1',
        )
        assert result is True

    def test_computes_fx_rate_when_missing(self, repo, impala):
        with patch.object(repo, '_get_fx_rate', return_value=1.35) as fx:
            repo._insert_position_version(
                version_id=1, position_id=2, position_date='2026-01-01',
                portfolio='P1', security='S1', quantity=10, average_cost=100,
                total_cost=1000, realized_pnl=0, current_price=105, market_value=1050,
                unrealized_pnl=50, trade_id=1, trade_type='BUY', status='OPEN',
                is_active=True, created_by='user1',
                security_currency='USD', portfolio_currency='SGD',
            )
        fx.assert_called_once()

    def test_write_failure_returns_false(self, repo, impala):
        impala.execute_write.return_value = False
        result = repo._insert_position_version(
            version_id=1, position_id=2, position_date='2026-01-01',
            portfolio='P1', security='S1', quantity=10, average_cost=100,
            total_cost=1000, realized_pnl=0, current_price=105, market_value=1050,
            unrealized_pnl=50, trade_id=1, trade_type='BUY', status='OPEN',
            is_active=True, created_by='user1',
        )
        assert result is False

    def test_exception_returns_false(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            result = repo._insert_position_version(
                version_id=1, position_id=2, position_date='2026-01-01',
                portfolio='P1', security='S1', quantity=10, average_cost=100,
                total_cost=1000, realized_pnl=0, current_price=105, market_value=1050,
                unrealized_pnl=50, trade_id=1, trade_type='BUY', status='OPEN',
                is_active=True, created_by='user1',
            )
        assert result is False


class TestRefreshMarketValues:
    def test_skips_zero_quantity(self, repo):
        with patch.object(repo, 'get_all_positions', return_value=[{'quantity': 0, 'total_cost': 0}]):
            counters = repo.refresh_market_values()
        assert counters['skipped'] == 1

    def test_skips_when_no_price(self, repo):
        with patch.object(repo, 'get_all_positions', return_value=[{'quantity': 10, 'total_cost': 1000}]), \
             patch.object(repo, '_get_equity_price', return_value=None):
            counters = repo.refresh_market_values()
        assert counters['skipped'] == 1

    def test_updates_position_with_price(self, repo):
        positions = [{'quantity': 10, 'total_cost': 1000, 'position_id': 1, 'average_cost': 100,
                       'realized_pnl': 0, 'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_id': 1}]
        with patch.object(repo, 'get_all_positions', return_value=positions), \
             patch.object(repo, '_get_equity_price', return_value=105), \
             patch.object(repo, '_insert_position_version', return_value=True):
            counters = repo.refresh_market_values()
        assert counters['updated'] == 1

    def test_insert_failure_counts_error(self, repo):
        positions = [{'quantity': 10, 'total_cost': 1000, 'position_id': 1, 'average_cost': 100,
                       'realized_pnl': 0, 'portfolio_short_name': 'P1', 'security_label': 'S1', 'trade_id': 1}]
        with patch.object(repo, 'get_all_positions', return_value=positions), \
             patch.object(repo, '_get_equity_price', return_value=105), \
             patch.object(repo, '_insert_position_version', return_value=False):
            counters = repo.refresh_market_values()
        assert counters['errors'] == 1

    def test_portfolio_filter(self, repo):
        positions = [
            {'quantity': 10, 'total_cost': 1000, 'position_id': 1, 'portfolio_short_name': 'P1', 'security_label': 'S1'},
            {'quantity': 10, 'total_cost': 1000, 'position_id': 2, 'portfolio_short_name': 'P2', 'security_label': 'S1'},
        ]
        with patch.object(repo, 'get_all_positions', return_value=positions), \
             patch.object(repo, '_get_equity_price', return_value=105), \
             patch.object(repo, '_insert_position_version', return_value=True):
            counters = repo.refresh_market_values(portfolio_filter='P1')
        assert counters['updated'] == 1

    def test_exception_in_loop_counted_as_error(self, repo):
        positions = [{'quantity': 10, 'total_cost': 1000, 'position_id': 1, 'portfolio_short_name': 'P1', 'security_label': 'S1'}]
        with patch.object(repo, 'get_all_positions', return_value=positions), \
             patch.object(repo, '_get_equity_price', side_effect=RuntimeError('boom')):
            counters = repo.refresh_market_values()
        assert counters['errors'] == 1

    def test_outer_exception_returns_partial_counters(self, repo):
        with patch.object(repo, 'get_all_positions', side_effect=RuntimeError('boom')):
            counters = repo.refresh_market_values()
        assert counters == {'updated': 0, 'skipped': 0, 'errors': 0}


class TestInsertTradeHistory:
    def test_async_write(self, repo, impala):
        result = repo.insert_trade_history(
            1, 'D1', 'CREATE', None, 'INITIAL', {}, 'created', 'user1', async_write=True,
        )
        assert result is True
        impala.execute_write_async.assert_called_once()

    def test_sync_write(self, repo, impala):
        result = repo.insert_trade_history(
            1, 'D1', 'CREATE', None, 'INITIAL', {}, 'created', 'user1', async_write=False,
        )
        assert result is True
        impala.execute_write.assert_called_once()

    def test_changes_with_special_chars_escaped(self, repo, impala):
        repo.insert_trade_history(
            1, 'D1', 'UPDATE', 'INITIAL', 'MODIFIED',
            {'field': {'old': "O'Brien", 'new': 'X'}}, 'updated', 'user1', async_write=False,
        )
        query = impala.execute_write.call_args[0][0]
        assert "O\\'Brien" in query

    def test_exception_returns_false(self, repo):
        with patch.object(repo, 'get_next_id', side_effect=RuntimeError('boom')):
            result = repo.insert_trade_history(1, 'D1', 'CREATE', None, 'INITIAL', {}, '', 'user1')
        assert result is False


class TestGetTradeHistory:
    def test_returns_results(self, repo, impala):
        impala.execute_query.return_value = [{'history_id': 1}]
        assert repo.get_trade_history(1) == [{'history_id': 1}]

    def test_none_result_returns_empty_list(self, repo, impala):
        impala.execute_query.return_value = None
        assert repo.get_trade_history(1) == []

    def test_exception_returns_empty_list(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_trade_history(1) == []


class TestGetTradeStatistics:
    def test_cache_hit_returns_cached(self, repo, qcache):
        qcache.get.return_value = {'total_trades': 5}
        stats = repo.get_trade_statistics()
        assert stats == {'total_trades': 5}

    def test_cache_miss_queries_and_aggregates(self, repo, impala, qcache):
        impala.execute_query.side_effect = [
            [
                {'status': 'INITIAL', 'trade_type': 'BUY', 'cnt': 2, 'today_cnt': 1, 'total_notional': 1000},
                {'status': 'VALIDATED', 'trade_type': 'SELL', 'cnt': 1, 'today_cnt': 0, 'total_notional': 500},
                {'status': 'SETTLED', 'trade_type': 'BUY', 'cnt': 3, 'today_cnt': 0, 'total_notional': 3000},
                {'status': 'CANCELLED', 'trade_type': 'SELL', 'cnt': 1, 'today_cnt': 0, 'total_notional': 100},
            ],
            [{'cnt': 1}],
        ]
        stats = repo.get_trade_statistics()
        assert stats['total_trades'] == 7
        assert stats['pending_validation'] == 2 + 1  # INITIAL bucket + pending cancel
        assert stats['pending_settlement'] == 1
        assert stats['settled'] == 3
        assert stats['cancelled'] == 1
        assert stats['buy_notional'] == 4000
        assert stats['sell_notional'] == 600
        qcache.set.assert_called_once()

    def test_no_use_cache_skips_cache_check(self, repo, impala, qcache):
        impala.execute_query.side_effect = [[], [{'cnt': 0}]]
        repo.get_trade_statistics(use_cache=False)
        qcache.get.assert_not_called()

    def test_no_results_returns_zero_stats(self, repo, impala, qcache):
        impala.execute_query.side_effect = [[], [{'cnt': 0}]]
        stats = repo.get_trade_statistics()
        assert stats['total_trades'] == 0

    def test_exception_returns_default_stats(self, repo, qcache):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            stats = repo.get_trade_statistics()
        assert stats['total_trades'] == 0
        assert stats['status_breakdown'] == []


class TestInvalidateStatisticsCache:
    def test_invalidates_stats_and_list_caches(self, repo, qcache):
        repo.invalidate_statistics_cache()
        assert qcache.invalidate.call_count > 1


class TestGetPendingValidationTrades:
    def test_returns_results(self, repo, impala):
        impala.execute_query.return_value = [{'trade_id': 1}]
        assert repo.get_pending_validation_trades() == [{'trade_id': 1}]

    def test_cis_only_false_omits_clause(self, repo, impala):
        repo.get_pending_validation_trades(cis_only=False)
        query = impala.execute_query.call_args[0][0]
        assert "src_system" not in query

    def test_none_result_returns_empty_list(self, repo, impala):
        impala.execute_query.return_value = None
        assert repo.get_pending_validation_trades() == []

    def test_exception_returns_empty_list(self, repo):
        with patch('edge_jobs_py36.lib.trade_kudu_repository.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_pending_validation_trades() == []


class TestGetPendingSettlementTrades:
    def test_delegates_to_get_all_trades(self, repo):
        with patch.object(repo, 'get_all_trades', return_value=[{'trade_id': 1}]) as m:
            result = repo.get_pending_settlement_trades()
        assert result == [{'trade_id': 1}]
        kwargs = m.call_args[1]
        assert kwargs['status'] == 'VALIDATED'
