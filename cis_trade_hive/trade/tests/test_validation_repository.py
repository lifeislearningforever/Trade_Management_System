"""
Trade Validation Repository Tests

Comprehensive tests for TradeValidationRepository and ValidationResult.
Tests portfolio, security, and counterparty validation logic.
"""

import pytest
from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock
from dataclasses import asdict


class ValidationResultTestCase(TestCase):
    """Test cases for ValidationResult dataclass"""

    def test_validation_result_creation(self):
        """Test creating a ValidationResult"""
        from trade.repositories.trade_validation_repository import ValidationResult

        result = ValidationResult(
            is_valid=True,
            entity_type='PORTFOLIO',
            entity_name='PORT001',
            message='Portfolio is valid'
        )

        self.assertTrue(result.is_valid)
        self.assertEqual(result.entity_type, 'PORTFOLIO')
        self.assertEqual(result.entity_name, 'PORT001')
        self.assertEqual(result.message, 'Portfolio is valid')
        self.assertIsNone(result.details)

    def test_validation_result_with_details(self):
        """Test creating a ValidationResult with details"""
        from trade.repositories.trade_validation_repository import ValidationResult

        details = {'name': 'PORT001', 'currency': 'USD'}
        result = ValidationResult(
            is_valid=True,
            entity_type='PORTFOLIO',
            entity_name='PORT001',
            message='Portfolio is valid',
            details=details
        )

        self.assertEqual(result.details, details)
        self.assertEqual(result.details['currency'], 'USD')

    def test_validation_result_invalid(self):
        """Test creating an invalid ValidationResult"""
        from trade.repositories.trade_validation_repository import ValidationResult

        result = ValidationResult(
            is_valid=False,
            entity_type='SECURITY',
            entity_name='INVALID_SEC',
            message='Security not found'
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.message, 'Security not found')


class TradeValidationRepositoryTestCase(TestCase):
    """Test cases for TradeValidationRepository"""

    def setUp(self):
        """Set up test data"""
        from trade.repositories.trade_validation_repository import (
            trade_validation_repository, TradeValidationRepository
        )
        from core.repositories.impala_connection import query_cache

        # Clear cache before each test to ensure isolated tests
        query_cache.clear()

        self.repository = trade_validation_repository
        self.TradeValidationRepository = TradeValidationRepository

        # Sample portfolio data
        self.valid_portfolio = {
            'name': 'PORT001',
            'currency': 'USD',
            'manager': 'John Doe',
            'cash_balance': 'USD',
            'status': 'SETTLED',
            'is_active': True
        }

        # Sample security data
        self.valid_security = {
            'security_name': 'SEC001',
            'security_type': 'EQUITY',
            'isin': 'US1234567890',
            'ticker': 'TEST',
            'currency_code': 'USD',
            'price': 50.00,
            'issuer': 'Test Corp',
            'status': 'ACTIVE',
            'is_active': True
        }

        # Sample counterparty data
        self.valid_counterparty = {
            'counterparty_short_name': 'BROKER001',
            'counterparty_full_name': 'Test Broker Inc',
            'country': 'US',
            'is_broker': True,
            'is_custodian': False,
            'is_active': True,
            'is_deleted': False
        }

    # =========================================================================
    # ESCAPE_VALUE TESTS
    # =========================================================================

    def test_escape_value_none(self):
        """Test escape_value with None"""
        result = self.repository.escape_value(None)
        self.assertEqual(result, 'NULL')

    def test_escape_value_string(self):
        """Test escape_value with string"""
        result = self.repository.escape_value('test')
        self.assertEqual(result, "'test'")

    def test_escape_value_string_with_quotes(self):
        """Test escape_value escapes single quotes"""
        result = self.repository.escape_value("O'Brien")
        self.assertEqual(result, "'O''Brien'")

    def test_escape_value_boolean(self):
        """Test escape_value with boolean"""
        self.assertEqual(self.repository.escape_value(True), 'true')
        self.assertEqual(self.repository.escape_value(False), 'false')

    def test_escape_value_number(self):
        """Test escape_value with number"""
        result = self.repository.escape_value(42)
        self.assertEqual(result, '42')

    # =========================================================================
    # PORTFOLIO VALIDATION TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_portfolio_valid(self, mock_execute):
        """Test validating a valid portfolio"""
        mock_execute.return_value = [self.valid_portfolio]

        result = self.repository.validate_portfolio('PORT001')

        self.assertTrue(result.is_valid)
        self.assertEqual(result.entity_type, 'PORTFOLIO')
        self.assertEqual(result.entity_name, 'PORT001')
        self.assertIn('valid for trading', result.message)
        self.assertEqual(result.details['name'], 'PORT001')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_portfolio_not_found(self, mock_execute):
        """Test validating non-existent portfolio"""
        mock_execute.return_value = []

        result = self.repository.validate_portfolio('NONEXISTENT')

        self.assertFalse(result.is_valid)
        self.assertIn('not found', result.message)

    def test_validate_portfolio_empty_name(self):
        """Test validating empty portfolio name"""
        result = self.repository.validate_portfolio('')

        self.assertFalse(result.is_valid)
        self.assertIn('required', result.message)

    def test_validate_portfolio_none_name(self):
        """Test validating None portfolio name"""
        result = self.repository.validate_portfolio(None)

        self.assertFalse(result.is_valid)
        self.assertIn('required', result.message)

    def test_validate_portfolio_whitespace_name(self):
        """Test validating whitespace-only portfolio name"""
        result = self.repository.validate_portfolio('   ')

        self.assertFalse(result.is_valid)
        self.assertIn('required', result.message)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_portfolio_invalid_status(self, mock_execute):
        """Test validating portfolio with invalid status"""
        invalid_portfolio = {**self.valid_portfolio, 'status': 'DRAFT'}
        mock_execute.return_value = [invalid_portfolio]

        result = self.repository.validate_portfolio('PORT001')

        self.assertFalse(result.is_valid)
        self.assertIn('Only SETTLED portfolios', result.message)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_portfolio_not_active(self, mock_execute):
        """Test validating inactive portfolio"""
        inactive_portfolio = {**self.valid_portfolio, 'is_active': False}
        mock_execute.return_value = [inactive_portfolio]

        result = self.repository.validate_portfolio('PORT001')

        self.assertFalse(result.is_valid)
        self.assertIn('not active', result.message)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_portfolio_case_insensitive_status(self, mock_execute):
        """Test portfolio validation is case-insensitive for status"""
        lowercase_portfolio = {**self.valid_portfolio, 'status': 'settled'}
        mock_execute.return_value = [lowercase_portfolio]

        result = self.repository.validate_portfolio('PORT001')

        self.assertTrue(result.is_valid)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_portfolio_exception(self, mock_execute):
        """Test validate_portfolio handles exception"""
        mock_execute.side_effect = Exception("Database error")

        result = self.repository.validate_portfolio('PORT001')

        self.assertFalse(result.is_valid)
        self.assertIn('Error validating', result.message)

    # =========================================================================
    # GET_VALID_PORTFOLIOS TESTS
    # =========================================================================

    @patch('trade.repositories.trade_validation_repository.impala_manager.execute_query')
    @patch('trade.repositories.trade_validation_repository.query_cache')
    def test_get_valid_portfolios(self, mock_cache, mock_execute):
        """Test fetching valid portfolios"""
        mock_cache.get.return_value = None
        mock_execute.return_value = [
            {'portfolio_short_name': 'PORT001', 'currency': 'USD'},
            {'portfolio_short_name': 'PORT002', 'currency': 'EUR'}
        ]

        result = self.repository.get_valid_portfolios()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['portfolio_short_name'], 'PORT001')

    @patch('trade.repositories.trade_validation_repository.impala_manager.execute_query')
    @patch('trade.repositories.trade_validation_repository.query_cache')
    def test_get_valid_portfolios_with_search(self, mock_cache, mock_execute):
        """Test fetching portfolios with search filter"""
        mock_cache.get.return_value = None
        mock_execute.return_value = [{'portfolio_short_name': 'PORT001'}]

        result = self.repository.get_valid_portfolios(search='PORT')

        self.assertEqual(len(result), 1)
        call_args = mock_execute.call_args[0][0]
        self.assertIn("like '%port%'", call_args.lower())

    @patch('trade.repositories.trade_validation_repository.impala_manager.execute_query')
    @patch('trade.repositories.trade_validation_repository.query_cache')
    def test_get_valid_portfolios_cached(self, mock_cache, mock_execute):
        """Test portfolios are fetched from cache"""
        cached_data = [{'portfolio_short_name': 'CACHED_PORT'}]
        mock_cache.get.return_value = cached_data

        result = self.repository.get_valid_portfolios()

        self.assertEqual(result, cached_data)
        mock_execute.assert_not_called()

    @patch('trade.repositories.trade_validation_repository.impala_manager.execute_query')
    @patch('trade.repositories.trade_validation_repository.query_cache')
    def test_get_valid_portfolios_exception(self, mock_cache, mock_execute):
        """Test get_valid_portfolios handles exception"""
        mock_cache.get.return_value = None
        mock_execute.side_effect = Exception("Database error")

        result = self.repository.get_valid_portfolios()

        self.assertEqual(result, [])

    # =========================================================================
    # SECURITY VALIDATION TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_valid(self, mock_execute):
        """Test validating a valid security"""
        mock_execute.return_value = [self.valid_security]

        result = self.repository.validate_security('SEC001')

        self.assertTrue(result.is_valid)
        self.assertEqual(result.entity_type, 'SECURITY')
        self.assertEqual(result.entity_name, 'SEC001')
        self.assertIn('valid for trading', result.message)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_not_found(self, mock_execute):
        """Test validating non-existent security"""
        mock_execute.return_value = []

        result = self.repository.validate_security('NONEXISTENT')

        self.assertFalse(result.is_valid)
        self.assertIn('not found', result.message)

    def test_validate_security_empty_name(self):
        """Test validating empty security name"""
        result = self.repository.validate_security('')

        self.assertFalse(result.is_valid)
        self.assertIn('required', result.message)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_invalid_status(self, mock_execute):
        """Test validating security with invalid status"""
        invalid_security = {**self.valid_security, 'status': 'INACTIVE'}
        mock_execute.return_value = [invalid_security]

        result = self.repository.validate_security('SEC001')

        self.assertFalse(result.is_valid)
        # The message now includes INITIAL and VALIDATED as valid statuses
        self.assertIn('Only ACTIVE, APPROVED, INITIAL, or VALIDATED', result.message)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_approved_status(self, mock_execute):
        """Test validating security with APPROVED status"""
        approved_security = {**self.valid_security, 'status': 'APPROVED'}
        mock_execute.return_value = [approved_security]

        result = self.repository.validate_security('SEC001')

        self.assertTrue(result.is_valid)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_settled_status(self, mock_execute):
        """Test validating security with SETTLED status"""
        settled_security = {**self.valid_security, 'status': 'SETTLED'}
        mock_execute.return_value = [settled_security]

        result = self.repository.validate_security('SEC001')

        self.assertTrue(result.is_valid)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_null_status_legacy(self, mock_execute):
        """Test validating security with NULL status (legacy data)"""
        legacy_security = {**self.valid_security, 'status': None}
        mock_execute.return_value = [legacy_security]

        result = self.repository.validate_security('SEC001')

        self.assertTrue(result.is_valid)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_empty_status_legacy(self, mock_execute):
        """Test validating security with empty status (legacy data)"""
        legacy_security = {**self.valid_security, 'status': ''}
        mock_execute.return_value = [legacy_security]

        result = self.repository.validate_security('SEC001')

        self.assertTrue(result.is_valid)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_not_active(self, mock_execute):
        """Test validating inactive security"""
        inactive_security = {**self.valid_security, 'is_active': False}
        mock_execute.return_value = [inactive_security]

        result = self.repository.validate_security('SEC001')

        self.assertFalse(result.is_valid)
        self.assertIn('not active', result.message)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_is_active_string_true(self, mock_execute):
        """Test validating security with is_active as string 'true'"""
        security = {**self.valid_security, 'is_active': 'true'}
        mock_execute.return_value = [security]

        result = self.repository.validate_security('SEC001')

        self.assertTrue(result.is_valid)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_is_active_string_false(self, mock_execute):
        """Test validating security with is_active as string 'false'"""
        security = {**self.valid_security, 'is_active': 'false'}
        mock_execute.return_value = [security]

        result = self.repository.validate_security('SEC001')

        self.assertFalse(result.is_valid)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_is_active_none(self, mock_execute):
        """Test validating security with is_active as None (default to True)"""
        security = {**self.valid_security, 'is_active': None}
        mock_execute.return_value = [security]

        result = self.repository.validate_security('SEC001')

        self.assertTrue(result.is_valid)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_security_exception(self, mock_execute):
        """Test validate_security handles exception"""
        mock_execute.side_effect = Exception("Database error")

        result = self.repository.validate_security('SEC001')

        self.assertFalse(result.is_valid)
        self.assertIn('Error validating', result.message)

    # =========================================================================
    # GET_VALID_SECURITIES TESTS
    # =========================================================================

    @patch('trade.repositories.trade_validation_repository.impala_manager.execute_query')
    @patch('trade.repositories.trade_validation_repository.query_cache')
    def test_get_valid_securities(self, mock_cache, mock_execute):
        """Test fetching valid securities"""
        mock_cache.get.return_value = None
        mock_execute.return_value = [
            {'security_label': 'SEC001', 'security_type': 'EQUITY'},
            {'security_label': 'SEC002', 'security_type': 'BOND'}
        ]

        result = self.repository.get_valid_securities()

        self.assertEqual(len(result), 2)

    @patch('trade.repositories.trade_validation_repository.impala_manager.execute_query')
    @patch('trade.repositories.trade_validation_repository.query_cache')
    def test_get_valid_securities_with_search(self, mock_cache, mock_execute):
        """Test fetching securities with search filter"""
        mock_cache.get.return_value = None
        mock_execute.return_value = [{'security_label': 'SEC001'}]

        result = self.repository.get_valid_securities(search='SEC')

        self.assertEqual(len(result), 1)
        call_args = mock_execute.call_args[0][0]
        # Search should work on security_name, isin, or ticker
        self.assertIn('LIKE', call_args)

    @patch('trade.repositories.trade_validation_repository.impala_manager.execute_query')
    @patch('trade.repositories.trade_validation_repository.query_cache')
    def test_get_valid_securities_exception(self, mock_cache, mock_execute):
        """Test get_valid_securities handles exception"""
        mock_cache.get.return_value = None
        mock_execute.side_effect = Exception("Database error")

        result = self.repository.get_valid_securities()

        self.assertEqual(result, [])

    # =========================================================================
    # COUNTERPARTY VALIDATION TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_counterparty_valid(self, mock_execute):
        """Test validating a valid counterparty"""
        mock_execute.return_value = [self.valid_counterparty]

        result = self.repository.validate_counterparty('BROKER001')

        self.assertTrue(result.is_valid)
        self.assertEqual(result.entity_type, 'COUNTERPARTY')
        self.assertEqual(result.entity_name, 'BROKER001')
        self.assertIn('valid', result.message)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_counterparty_not_found(self, mock_execute):
        """Test validating non-existent counterparty"""
        mock_execute.return_value = []

        result = self.repository.validate_counterparty('NONEXISTENT')

        self.assertFalse(result.is_valid)
        self.assertIn('not found', result.message)

    def test_validate_counterparty_empty_optional(self):
        """Test validating empty counterparty (optional field)"""
        result = self.repository.validate_counterparty('')

        self.assertTrue(result.is_valid)
        self.assertIn('optional', result.message)

    def test_validate_counterparty_none_optional(self):
        """Test validating None counterparty (optional field)"""
        result = self.repository.validate_counterparty(None)

        self.assertTrue(result.is_valid)
        self.assertIn('optional', result.message)

    def test_validate_counterparty_whitespace_optional(self):
        """Test validating whitespace counterparty (optional field)"""
        result = self.repository.validate_counterparty('   ')

        self.assertTrue(result.is_valid)
        self.assertIn('optional', result.message)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_counterparty_not_active(self, mock_execute):
        """Test validating inactive counterparty"""
        inactive_cp = {**self.valid_counterparty, 'is_active': False}
        mock_execute.return_value = [inactive_cp]

        result = self.repository.validate_counterparty('BROKER001')

        self.assertFalse(result.is_valid)
        self.assertIn('not active', result.message)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_counterparty_deleted(self, mock_execute):
        """Test validating deleted counterparty"""
        deleted_cp = {**self.valid_counterparty, 'is_deleted': True}
        mock_execute.return_value = [deleted_cp]

        result = self.repository.validate_counterparty('BROKER001')

        self.assertFalse(result.is_valid)
        self.assertIn('deleted', result.message)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_counterparty_exception(self, mock_execute):
        """Test validate_counterparty handles exception"""
        mock_execute.side_effect = Exception("Database error")

        result = self.repository.validate_counterparty('BROKER001')

        self.assertFalse(result.is_valid)
        self.assertIn('Error validating', result.message)

    # =========================================================================
    # GET_VALID_COUNTERPARTIES TESTS
    # =========================================================================

    @patch('trade.repositories.trade_validation_repository.impala_manager.execute_query')
    @patch('trade.repositories.trade_validation_repository.query_cache')
    def test_get_valid_counterparties(self, mock_cache, mock_execute):
        """Test fetching valid counterparties"""
        mock_cache.get.return_value = None
        mock_execute.return_value = [
            {'counterparty_short_name': 'CP001'},
            {'counterparty_short_name': 'CP002'}
        ]

        result = self.repository.get_valid_counterparties()

        self.assertEqual(len(result), 2)

    @patch('trade.repositories.trade_validation_repository.impala_manager.execute_query')
    @patch('trade.repositories.trade_validation_repository.query_cache')
    def test_get_valid_counterparties_with_search(self, mock_cache, mock_execute):
        """Test fetching counterparties with search filter"""
        mock_cache.get.return_value = None
        mock_execute.return_value = [{'counterparty_short_name': 'BROKER001'}]

        result = self.repository.get_valid_counterparties(search='BROKER')

        self.assertEqual(len(result), 1)

    @patch('trade.repositories.trade_validation_repository.impala_manager.execute_query')
    @patch('trade.repositories.trade_validation_repository.query_cache')
    def test_get_valid_counterparties_exception(self, mock_cache, mock_execute):
        """Test get_valid_counterparties handles exception"""
        mock_cache.get.return_value = None
        mock_execute.side_effect = Exception("Database error")

        result = self.repository.get_valid_counterparties()

        self.assertEqual(result, [])

    # =========================================================================
    # COMBINED VALIDATION TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_trade_references_all_valid(self, mock_execute):
        """Test combined validation with all valid references"""
        # Setup mock to return valid data for each entity
        def side_effect(query, database=None):
            if 'cis_portfolio' in query:
                return [self.valid_portfolio]
            elif 'cis_security' in query:
                return [self.valid_security]
            elif 'cis_party' in query:
                return [self.valid_counterparty]
            return []

        mock_execute.side_effect = side_effect

        all_valid, results = self.repository.validate_trade_references(
            portfolio_name='PORT001',
            security_name='SEC001',
            counterparty_name='BROKER001'
        )

        self.assertTrue(all_valid)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.is_valid for r in results))

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_trade_references_portfolio_invalid(self, mock_execute):
        """Test combined validation with invalid portfolio"""
        def side_effect(query, database=None):
            if 'cis_portfolio' in query:
                return []  # Portfolio not found
            elif 'cis_security' in query:
                return [self.valid_security]
            return []

        mock_execute.side_effect = side_effect

        all_valid, results = self.repository.validate_trade_references(
            portfolio_name='INVALID',
            security_name='SEC001'
        )

        self.assertFalse(all_valid)
        # At least one result should be invalid
        portfolio_result = next(r for r in results if r.entity_type == 'PORTFOLIO')
        self.assertFalse(portfolio_result.is_valid)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_validate_trade_references_no_counterparty(self, mock_execute):
        """Test combined validation without counterparty"""
        def side_effect(query, database=None):
            if 'cis_portfolio' in query:
                return [self.valid_portfolio]
            elif 'cis_security' in query:
                return [self.valid_security]
            return []

        mock_execute.side_effect = side_effect

        all_valid, results = self.repository.validate_trade_references(
            portfolio_name='PORT001',
            security_name='SEC001',
            counterparty_name=None
        )

        self.assertTrue(all_valid)
        self.assertEqual(len(results), 2)  # Only portfolio and security

    # =========================================================================
    # GET_VALIDATION_ERRORS TESTS
    # =========================================================================

    def test_get_validation_errors(self):
        """Test extracting error messages from validation results"""
        from trade.repositories.trade_validation_repository import ValidationResult

        results = [
            ValidationResult(True, 'PORTFOLIO', 'PORT001', 'Valid'),
            ValidationResult(False, 'SECURITY', 'SEC001', 'Security not found'),
            ValidationResult(False, 'COUNTERPARTY', 'CP001', 'Counterparty not active')
        ]

        errors = self.repository.get_validation_errors(results)

        self.assertEqual(len(errors), 2)
        self.assertIn('Security not found', errors)
        self.assertIn('Counterparty not active', errors)

    def test_get_validation_errors_all_valid(self):
        """Test get_validation_errors with all valid results"""
        from trade.repositories.trade_validation_repository import ValidationResult

        results = [
            ValidationResult(True, 'PORTFOLIO', 'PORT001', 'Valid'),
            ValidationResult(True, 'SECURITY', 'SEC001', 'Valid')
        ]

        errors = self.repository.get_validation_errors(results)

        self.assertEqual(len(errors), 0)

    # =========================================================================
    # AUTO-POPULATE HELPERS TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_portfolio_details(self, mock_execute):
        """Test getting portfolio details for auto-populate"""
        mock_execute.return_value = [self.valid_portfolio]

        result = self.repository.get_portfolio_details('PORT001')

        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'PORT001')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_portfolio_details_invalid(self, mock_execute):
        """Test getting details for invalid portfolio"""
        mock_execute.return_value = []

        result = self.repository.get_portfolio_details('INVALID')

        self.assertIsNone(result)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_security_details(self, mock_execute):
        """Test getting security details for auto-populate"""
        mock_execute.return_value = [self.valid_security]

        result = self.repository.get_security_details('SEC001')

        self.assertIsNotNone(result)
        self.assertEqual(result['security_name'], 'SEC001')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_security_details_invalid(self, mock_execute):
        """Test getting details for invalid security"""
        mock_execute.return_value = []

        result = self.repository.get_security_details('INVALID')

        self.assertIsNone(result)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_counterparty_details(self, mock_execute):
        """Test getting counterparty details for auto-populate"""
        mock_execute.return_value = [self.valid_counterparty]

        result = self.repository.get_counterparty_details('BROKER001')

        self.assertIsNotNone(result)
        self.assertEqual(result['counterparty_short_name'], 'BROKER001')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_counterparty_details_invalid(self, mock_execute):
        """Test getting details for invalid counterparty"""
        mock_execute.return_value = []

        result = self.repository.get_counterparty_details('INVALID')

        self.assertIsNone(result)

    # =========================================================================
    # CONSTANTS TESTS
    # =========================================================================

    def test_database_constant(self):
        """Test DATABASE constant"""
        self.assertEqual(self.TradeValidationRepository.DATABASE, 'gmp_cis')

    def test_portfolio_table_constant(self):
        """Test PORTFOLIO_TABLE constant"""
        self.assertEqual(self.TradeValidationRepository.PORTFOLIO_TABLE, 'cis_portfolio')

    def test_security_table_constant(self):
        """Test SECURITY_TABLE constant"""
        self.assertEqual(self.TradeValidationRepository.SECURITY_TABLE, 'cis_security')

    def test_counterparty_table_constant(self):
        """Test COUNTERPARTY_TABLE constant"""
        self.assertEqual(self.TradeValidationRepository.COUNTERPARTY_TABLE, 'cis_party')

    def test_portfolio_valid_statuses(self):
        """Test PORTFOLIO_VALID_STATUSES"""
        self.assertIn('SETTLED', self.TradeValidationRepository.PORTFOLIO_VALID_STATUSES)
        self.assertIn('settled', self.TradeValidationRepository.PORTFOLIO_VALID_STATUSES)

    def test_security_valid_statuses(self):
        """Test SECURITY_VALID_STATUSES"""
        self.assertIn('ACTIVE', self.TradeValidationRepository.SECURITY_VALID_STATUSES)
        self.assertIn('APPROVED', self.TradeValidationRepository.SECURITY_VALID_STATUSES)
        self.assertIn('SETTLED', self.TradeValidationRepository.SECURITY_VALID_STATUSES)
        self.assertIn(None, self.TradeValidationRepository.SECURITY_VALID_STATUSES)

    def test_cache_ttl(self):
        """Test CACHE_TTL constant"""
        self.assertEqual(self.TradeValidationRepository.CACHE_TTL, 300)  # 5 minutes
