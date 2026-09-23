"""Tests for edge_jobs_py36/lib/trade_validation_repository.py."""
from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from edge_jobs_py36.lib.trade_validation_repository import (
    TradeValidationRepository,
    ValidationResult,
    trade_validation_repository,
)


def _repo():
    return TradeValidationRepository()


@pytest.fixture(autouse=True)
def _no_cache():
    """Every test gets an empty query_cache mock so results never leak between tests."""
    with patch('edge_jobs_py36.lib.trade_validation_repository.query_cache') as mock_cache:
        mock_cache.get.return_value = None
        yield mock_cache


class TestEscapeValue:
    def test_none_returns_null(self):
        assert TradeValidationRepository.escape_value(None) == 'NULL'

    def test_string_quoted_and_escaped(self):
        assert TradeValidationRepository.escape_value("O'Brien") == "'O\\'Brien'"

    def test_bool_lowercased(self):
        assert TradeValidationRepository.escape_value(True) == 'true'
        assert TradeValidationRepository.escape_value(False) == 'false'

    def test_int_stringified(self):
        assert TradeValidationRepository.escape_value(42) == '42'


class TestValidatePortfolio:
    def test_empty_name_is_invalid(self):
        repo = _repo()
        result = repo.validate_portfolio('')
        assert result.is_valid is False
        assert 'required' in result.message

    def test_whitespace_only_name_is_invalid(self):
        repo = _repo()
        result = repo.validate_portfolio('   ')
        assert result.is_valid is False

    def test_returns_cached_result(self, _no_cache):
        repo = _repo()
        cached_result = ValidationResult(True, 'PORTFOLIO', 'UOB-SG', 'cached')
        _no_cache.get.return_value = cached_result
        result = repo.validate_portfolio('UOB-SG')
        assert result is cached_result

    def test_not_found_returns_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = repo.validate_portfolio('UOB-SG')
        assert result.is_valid is False
        assert 'not found' in result.message

    def test_valid_status_and_active_returns_valid(self, _no_cache):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': 'SETTLED', 'is_active': True}]
            result = repo.validate_portfolio('UOB-SG')
        assert result.is_valid is True
        _no_cache.set.assert_called_once()

    def test_invalid_status_returns_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': 'INITIAL', 'is_active': True}]
            result = repo.validate_portfolio('UOB-SG')
        assert result.is_valid is False
        assert 'status' in result.message

    def test_case_insensitive_status_match(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': 'settled', 'is_active': True}]
            result = repo.validate_portfolio('UOB-SG')
        assert result.is_valid is True

    def test_inactive_portfolio_returns_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': 'SETTLED', 'is_active': False}]
            result = repo.validate_portfolio('UOB-SG')
        assert result.is_valid is False
        assert 'not active' in result.message

    def test_exception_returns_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = repo.validate_portfolio('UOB-SG')
        assert result.is_valid is False
        assert 'Error validating portfolio' in result.message


class TestGetValidPortfolios:
    def test_returns_results(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'portfolio_short_name': 'UOB-SG'}]
            result = repo.get_valid_portfolios()
        assert len(result) == 1

    def test_returns_cached_when_no_search(self, _no_cache):
        repo = _repo()
        _no_cache.get.return_value = [{'portfolio_short_name': 'CACHED'}]
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            result = repo.get_valid_portfolios()
        assert result == [{'portfolio_short_name': 'CACHED'}]
        mock_mgr.execute_query.assert_not_called()

    def test_search_bypasses_cache(self, _no_cache):
        repo = _repo()
        _no_cache.get.return_value = [{'portfolio_short_name': 'CACHED'}]
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_valid_portfolios(search='UOB')
        mock_mgr.execute_query.assert_called_once()

    def test_search_term_included_in_query(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_valid_portfolios(search='UOB')
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'uob' in query.lower()

    def test_limit_applied(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_valid_portfolios(limit=25)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 25' in query

    def test_returns_empty_list_on_exception(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_valid_portfolios() == []


class TestValidateSecurity:
    def test_empty_name_is_invalid(self):
        repo = _repo()
        result = repo.validate_security('')
        assert result.is_valid is False

    def test_not_found_returns_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = repo.validate_security('AAPL')
        assert result.is_valid is False
        assert 'not found' in result.message

    def test_active_status_returns_valid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': 'ACTIVE', 'is_active': True}]
            result = repo.validate_security('AAPL')
        assert result.is_valid is True

    def test_null_status_treated_as_legacy_valid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': None, 'is_active': True}]
            result = repo.validate_security('AAPL')
        assert result.is_valid is True

    def test_empty_string_status_treated_as_legacy_valid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': '', 'is_active': True}]
            result = repo.validate_security('AAPL')
        assert result.is_valid is True

    def test_invalid_status_returns_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': 'REJECTED', 'is_active': True}]
            result = repo.validate_security('AAPL')
        assert result.is_valid is False

    def test_is_active_string_true_parsed(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': 'ACTIVE', 'is_active': 'true'}]
            result = repo.validate_security('AAPL')
        assert result.is_valid is True

    def test_is_active_string_false_parsed(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': 'ACTIVE', 'is_active': 'false'}]
            result = repo.validate_security('AAPL')
        assert result.is_valid is False

    def test_is_active_none_defaults_to_true(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'status': 'ACTIVE', 'is_active': None}]
            result = repo.validate_security('AAPL')
        assert result.is_valid is True

    def test_exception_returns_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = repo.validate_security('AAPL')
        assert result.is_valid is False


class TestGetValidSecurities:
    def test_returns_results(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'security_label': 'AAPL'}]
            assert len(repo.get_valid_securities()) == 1

    def test_search_matches_name_isin_and_ticker(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_valid_securities(search='AAPL')
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'security_name' in query
        assert 'isin' in query
        assert 'ticker' in query

    def test_no_limit_by_default(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_valid_securities()
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT' not in query

    def test_limit_applied_when_given(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_valid_securities(limit=10)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 10' in query

    def test_returns_empty_list_on_exception(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_valid_securities() == []


class TestValidateCounterparty:
    def test_empty_name_is_valid_and_optional(self):
        repo = _repo()
        result = repo.validate_counterparty('')
        assert result.is_valid is True
        assert 'optional' in result.message

    def test_not_found_returns_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = repo.validate_counterparty('BROKER1')
        assert result.is_valid is False

    def test_deleted_counterparty_is_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'is_active': True, 'is_deleted': True}]
            result = repo.validate_counterparty('BROKER1')
        assert result.is_valid is False
        assert 'deleted' in result.message

    def test_inactive_counterparty_is_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'is_active': False, 'is_deleted': False}]
            result = repo.validate_counterparty('BROKER1')
        assert result.is_valid is False
        assert 'not active' in result.message

    def test_active_counterparty_is_valid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'is_active': True, 'is_deleted': False}]
            result = repo.validate_counterparty('BROKER1')
        assert result.is_valid is True

    def test_exception_returns_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            result = repo.validate_counterparty('BROKER1')
        assert result.is_valid is False


class TestGetValidCounterparties:
    def test_returns_results(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'party_short_name': 'BROKER1'}]
            assert len(repo.get_valid_counterparties()) == 1

    def test_returns_empty_list_on_exception(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert repo.get_valid_counterparties() == []

    def test_search_filters_by_short_and_full_name(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            repo.get_valid_counterparties(search='BROKER')
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'party_short_name' in query
        assert 'party_full_name' in query


class TestParseDate:
    def test_none_returns_none(self):
        assert _repo()._parse_date(None) is None

    def test_date_object_passthrough(self):
        d = date(2026, 9, 17)
        assert _repo()._parse_date(d) == d

    def test_iso_format(self):
        assert _repo()._parse_date('2026-09-17') == date(2026, 9, 17)

    def test_yyyymmdd_format(self):
        assert _repo()._parse_date('20260917') == date(2026, 9, 17)

    def test_dmy_dash_format(self):
        assert _repo()._parse_date('17-09-2026') == date(2026, 9, 17)

    def test_dmy_slash_format(self):
        assert _repo()._parse_date('17/09/2026') == date(2026, 9, 17)

    def test_unparseable_returns_none(self):
        assert _repo()._parse_date('garbage') is None


class TestValidateSettlementDate:
    def test_missing_trade_date_is_invalid(self):
        repo = _repo()
        result = repo.validate_settlement_date('', '2026-09-18')
        assert result.is_valid is False
        assert 'Trade date is required' in result.message

    def test_missing_settle_date_is_invalid(self):
        repo = _repo()
        result = repo.validate_settlement_date('2026-09-17', '')
        assert result.is_valid is False
        assert 'Settlement date is required' in result.message

    def test_invalid_trade_date_format(self):
        repo = _repo()
        result = repo.validate_settlement_date('garbage', '2026-09-18')
        assert result.is_valid is False
        assert 'Invalid trade date format' in result.message

    def test_invalid_settle_date_format(self):
        repo = _repo()
        result = repo.validate_settlement_date('2026-09-17', 'garbage')
        assert result.is_valid is False
        assert 'Invalid settlement date format' in result.message

    def test_trade_date_in_future_is_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.system_date_service') as mock_svc:
            mock_svc.get_system_date.return_value = date(2026, 9, 17)
            result = repo.validate_settlement_date('2026-09-20', '2026-09-21')
        assert result.is_valid is False
        assert 'cannot be in the future' in result.message

    def test_settle_before_trade_is_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.system_date_service') as mock_svc:
            mock_svc.get_system_date.return_value = date(2026, 9, 17)
            result = repo.validate_settlement_date('2026-09-17', '2026-09-16')
        assert result.is_valid is False
        assert 'cannot be before trade date' in result.message

    def test_valid_dates_return_valid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.system_date_service') as mock_svc:
            mock_svc.get_system_date.return_value = date(2026, 9, 17)
            result = repo.validate_settlement_date('2026-09-17', '2026-09-19')
        assert result.is_valid is True

    def test_equal_dates_are_valid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.system_date_service') as mock_svc:
            mock_svc.get_system_date.return_value = date(2026, 9, 17)
            result = repo.validate_settlement_date('2026-09-17', '2026-09-17')
        assert result.is_valid is True

    def test_exception_returns_invalid(self):
        repo = _repo()
        with patch('edge_jobs_py36.lib.trade_validation_repository.system_date_service') as mock_svc:
            mock_svc.get_system_date.side_effect = RuntimeError('boom')
            result = repo.validate_settlement_date('2026-09-17', '2026-09-19')
        assert result.is_valid is False


class TestValidateTradeReferences:
    def test_all_valid_returns_true(self):
        repo = _repo()
        with patch.object(repo, 'validate_portfolio', return_value=ValidationResult(True, 'PORTFOLIO', 'P', 'ok')), \
             patch.object(repo, 'validate_security', return_value=ValidationResult(True, 'SECURITY', 'S', 'ok')):
            all_valid, results = repo.validate_trade_references('P', 'S')
        assert all_valid is True
        assert len(results) == 2

    def test_invalid_portfolio_fails_overall(self):
        repo = _repo()
        with patch.object(repo, 'validate_portfolio', return_value=ValidationResult(False, 'PORTFOLIO', 'P', 'bad')), \
             patch.object(repo, 'validate_security', return_value=ValidationResult(True, 'SECURITY', 'S', 'ok')):
            all_valid, results = repo.validate_trade_references('P', 'S')
        assert all_valid is False

    def test_counterparty_included_when_given(self):
        repo = _repo()
        with patch.object(repo, 'validate_portfolio', return_value=ValidationResult(True, 'PORTFOLIO', 'P', 'ok')), \
             patch.object(repo, 'validate_security', return_value=ValidationResult(True, 'SECURITY', 'S', 'ok')), \
             patch.object(repo, 'validate_counterparty', return_value=ValidationResult(True, 'COUNTERPARTY', 'C', 'ok')) as mock_cp:
            all_valid, results = repo.validate_trade_references('P', 'S', counterparty_name='C')
        mock_cp.assert_called_once_with('C')
        assert len(results) == 3

    def test_dates_included_when_both_given(self):
        repo = _repo()
        with patch.object(repo, 'validate_portfolio', return_value=ValidationResult(True, 'PORTFOLIO', 'P', 'ok')), \
             patch.object(repo, 'validate_security', return_value=ValidationResult(True, 'SECURITY', 'S', 'ok')), \
             patch.object(repo, 'validate_settlement_date', return_value=ValidationResult(True, 'DATE', 'd', 'ok')) as mock_date:
            all_valid, results = repo.validate_trade_references(
                'P', 'S', trade_date='2026-09-17', settle_date='2026-09-19',
            )
        mock_date.assert_called_once()
        assert len(results) == 3

    def test_dates_skipped_when_only_one_given(self):
        repo = _repo()
        with patch.object(repo, 'validate_portfolio', return_value=ValidationResult(True, 'PORTFOLIO', 'P', 'ok')), \
             patch.object(repo, 'validate_security', return_value=ValidationResult(True, 'SECURITY', 'S', 'ok')), \
             patch.object(repo, 'validate_settlement_date') as mock_date:
            repo.validate_trade_references('P', 'S', trade_date='2026-09-17')
        mock_date.assert_not_called()


class TestGetValidationErrors:
    def test_extracts_only_invalid_messages(self):
        repo = _repo()
        results = [
            ValidationResult(True, 'PORTFOLIO', 'P', 'ok'),
            ValidationResult(False, 'SECURITY', 'S', 'bad security'),
        ]
        errors = repo.get_validation_errors(results)
        assert errors == ['bad security']

    def test_empty_list_when_all_valid(self):
        repo = _repo()
        results = [ValidationResult(True, 'PORTFOLIO', 'P', 'ok')]
        assert repo.get_validation_errors(results) == []


class TestGetDetailsHelpers:
    def test_get_portfolio_details_returns_details_when_valid(self):
        repo = _repo()
        with patch.object(repo, 'validate_portfolio', return_value=ValidationResult(True, 'PORTFOLIO', 'P', 'ok', details={'name': 'P'})):
            assert repo.get_portfolio_details('P') == {'name': 'P'}

    def test_get_portfolio_details_returns_none_when_invalid(self):
        repo = _repo()
        with patch.object(repo, 'validate_portfolio', return_value=ValidationResult(False, 'PORTFOLIO', 'P', 'bad')):
            assert repo.get_portfolio_details('P') is None

    def test_get_security_details_returns_details_when_valid(self):
        repo = _repo()
        with patch.object(repo, 'validate_security', return_value=ValidationResult(True, 'SECURITY', 'S', 'ok', details={'name': 'S'})):
            assert repo.get_security_details('S') == {'name': 'S'}

    def test_get_counterparty_details_returns_details_when_valid(self):
        repo = _repo()
        with patch.object(repo, 'validate_counterparty', return_value=ValidationResult(True, 'COUNTERPARTY', 'C', 'ok', details={'name': 'C'})):
            assert repo.get_counterparty_details('C') == {'name': 'C'}


class TestSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(trade_validation_repository, TradeValidationRepository)
