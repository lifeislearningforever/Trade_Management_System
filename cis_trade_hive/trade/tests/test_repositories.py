"""
Trade Repository Tests

Comprehensive tests for TradeKuduRepository operations.
Uses mocking to test repository logic without database connection.
"""

import pytest
from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime


class TradeKuduRepositoryTestCase(TestCase):
    """Test cases for TradeKuduRepository"""

    def setUp(self):
        """Set up test data"""
        from trade.repositories.trade_kudu_repository import trade_kudu_repository, TradeKuduRepository
        self.repository = trade_kudu_repository
        self.TradeKuduRepository = TradeKuduRepository

        # Sample trade data
        self.sample_trade = {
            'trade_id': 1001,
            'deal_number': 'DEAL-20240101-1001',
            'trade_type': 'BUY',
            'portfolio_short_name': 'PORT001',
            'portfolio_full_name': 'Test Portfolio 001',
            'security_label': 'SEC001',
            'security_full_name': 'Test Security 001',
            'security_type': 'EQUITY',
            'trade_status': 'CONFIRMED',
            'trade_date': '2024-01-15',
            'settle_date': '2024-01-17',
            'quantity': 100,
            'price': 50.25,
            'total_amount': 5025.00,
            'status': 'INITIAL',
            'is_active': False,
            'is_deleted': False,
            'src_system': 'CIS',
            'created_by': 'testuser',
            'created_at': '2024-01-15 10:00:00'
        }

        self.sample_trade_input = {
            'trade_type': 'BUY',
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_date': '2024-01-15',
            'settle_date': '2024-01-17',
            'quantity': 100,
            'price': 50.25,
            'total_amount': 5025.00,
            'counterparty': 'BROKER001'
        }

    # =========================================================================
    # ESCAPE VALUE TESTS
    # =========================================================================

    def test_escape_value_none(self):
        """Test escape_value with None returns NULL"""
        result = self.repository.escape_value(None)
        self.assertEqual(result, 'NULL')

    def test_escape_value_string(self):
        """Test escape_value with string"""
        result = self.repository.escape_value('test')
        self.assertEqual(result, "'test'")

    def test_escape_value_string_with_quotes(self):
        """Test escape_value escapes single quotes"""
        result = self.repository.escape_value("test's value")
        self.assertEqual(result, "'test''s value'")

    def test_escape_value_boolean_true(self):
        """Test escape_value with boolean True"""
        result = self.repository.escape_value(True)
        self.assertEqual(result, 'true')

    def test_escape_value_boolean_false(self):
        """Test escape_value with boolean False"""
        result = self.repository.escape_value(False)
        self.assertEqual(result, 'false')

    def test_escape_value_number(self):
        """Test escape_value with number"""
        result = self.repository.escape_value(42)
        self.assertEqual(result, '42')

    def test_escape_value_float(self):
        """Test escape_value with float"""
        result = self.repository.escape_value(3.14)
        self.assertEqual(result, '3.14')

    # =========================================================================
    # TO_DECIMAL TESTS
    # =========================================================================

    def test_to_decimal_none(self):
        """Test to_decimal with None returns default"""
        result = self.repository.to_decimal(None)
        self.assertEqual(result, '0')

    def test_to_decimal_empty_string(self):
        """Test to_decimal with empty string returns default"""
        result = self.repository.to_decimal('')
        self.assertEqual(result, '0')

    def test_to_decimal_valid_string(self):
        """Test to_decimal with valid string"""
        result = self.repository.to_decimal('123.45')
        self.assertEqual(result, '123.45')

    def test_to_decimal_integer(self):
        """Test to_decimal with integer"""
        result = self.repository.to_decimal(100)
        self.assertEqual(result, '100.0')

    def test_to_decimal_float(self):
        """Test to_decimal with float"""
        result = self.repository.to_decimal(99.99)
        self.assertEqual(result, '99.99')

    def test_to_decimal_invalid_string(self):
        """Test to_decimal with invalid string returns default"""
        result = self.repository.to_decimal('invalid')
        self.assertEqual(result, '0')

    def test_to_decimal_custom_default(self):
        """Test to_decimal with custom default"""
        result = self.repository.to_decimal(None, default=10)
        self.assertEqual(result, '10')

    def test_to_decimal_whitespace_string(self):
        """Test to_decimal with whitespace string"""
        result = self.repository.to_decimal('  ')
        self.assertEqual(result, '0')

    # =========================================================================
    # GET_NEXT_ID TESTS
    # =========================================================================

    def test_get_next_id_returns_integer(self):
        """Test get_next_id returns an integer"""
        result = self.repository.get_next_id('trade_id')
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_get_next_id_unique(self):
        """Test get_next_id returns unique values"""
        id1 = self.repository.get_next_id('trade_id')
        id2 = self.repository.get_next_id('trade_id')
        # IDs should be different (timestamp-based)
        self.assertNotEqual(id1, id2)

    # =========================================================================
    # VALIDATE_TRADE_DATA TESTS
    # =========================================================================

    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_validate_trade_data_missing_portfolio(self, mock_validation_repo):
        """Test validation fails when portfolio is missing"""
        mock_validation_repo.validate_trade_references.return_value = (True, [])
        mock_validation_repo.get_validation_errors.return_value = []

        trade_data = {
            'security_label': 'SEC001',
            'trade_type': 'BUY',
            'trade_date': '2024-01-15'
        }

        is_valid, errors, _ = self.repository.validate_trade_data(trade_data)

        self.assertFalse(is_valid)
        self.assertIn("Portfolio is required", errors)

    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_validate_trade_data_missing_security(self, mock_validation_repo):
        """Test validation fails when security is missing"""
        mock_validation_repo.validate_trade_references.return_value = (True, [])
        mock_validation_repo.get_validation_errors.return_value = []

        trade_data = {
            'portfolio_short_name': 'PORT001',
            'trade_type': 'BUY',
            'trade_date': '2024-01-15'
        }

        is_valid, errors, _ = self.repository.validate_trade_data(trade_data)

        self.assertFalse(is_valid)
        self.assertIn("Security is required", errors)

    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_validate_trade_data_missing_trade_type(self, mock_validation_repo):
        """Test validation fails when trade type is missing"""
        mock_validation_repo.validate_trade_references.return_value = (True, [])
        mock_validation_repo.get_validation_errors.return_value = []

        trade_data = {
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_date': '2024-01-15'
        }

        is_valid, errors, _ = self.repository.validate_trade_data(trade_data)

        self.assertFalse(is_valid)
        self.assertIn("Trade type is required", errors)

    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_validate_trade_data_missing_trade_date(self, mock_validation_repo):
        """Test validation fails when trade date is missing"""
        mock_validation_repo.validate_trade_references.return_value = (True, [])
        mock_validation_repo.get_validation_errors.return_value = []

        trade_data = {
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'BUY'
        }

        is_valid, errors, _ = self.repository.validate_trade_data(trade_data)

        self.assertFalse(is_valid)
        self.assertIn("Trade date is required", errors)

    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_validate_trade_data_buy_missing_quantity(self, mock_validation_repo):
        """Test BUY trade validation fails when quantity is missing"""
        mock_validation_repo.validate_trade_references.return_value = (True, [])
        mock_validation_repo.get_validation_errors.return_value = []

        trade_data = {
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'BUY',
            'trade_date': '2024-01-15',
            'price': 50.00
        }

        is_valid, errors, _ = self.repository.validate_trade_data(trade_data)

        self.assertFalse(is_valid)
        self.assertIn("Quantity is required for Buy/Sell trades", errors)

    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_validate_trade_data_buy_missing_price(self, mock_validation_repo):
        """Test BUY trade validation fails when price is missing"""
        mock_validation_repo.validate_trade_references.return_value = (True, [])
        mock_validation_repo.get_validation_errors.return_value = []

        trade_data = {
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'BUY',
            'trade_date': '2024-01-15',
            'quantity': 100
        }

        is_valid, errors, _ = self.repository.validate_trade_data(trade_data)

        self.assertFalse(is_valid)
        self.assertIn("Price is required for Buy/Sell trades", errors)

    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_validate_trade_data_valid(self, mock_validation_repo):
        """Test validation passes with valid data"""
        mock_validation_repo.validate_trade_references.return_value = (True, [])
        mock_validation_repo.get_validation_errors.return_value = []

        trade_data = {
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'BUY',
            'trade_date': '2024-01-15',
            'quantity': 100,
            'price': 50.00
        }

        is_valid, errors, _ = self.repository.validate_trade_data(trade_data)

        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_validate_trade_data_sell_no_position(self, mock_validation_repo):
        """Test SELL validation fails when no position exists"""
        mock_validation_repo.validate_trade_references.return_value = (True, [])
        mock_validation_repo.get_validation_errors.return_value = []

        trade_data = {
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'SELL',
            'trade_date': '2024-01-15',
            'quantity': 100,
            'price': 50.00
        }

        with patch.object(self.repository, 'get_trade_detail', return_value=None):
            is_valid, errors, _ = self.repository.validate_trade_data(trade_data)

        self.assertFalse(is_valid)
        self.assertTrue(any("No trade detail found" in e for e in errors))

    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_validate_trade_data_sell_insufficient_quantity(self, mock_validation_repo):
        """Test SELL validation fails when insufficient quantity"""
        mock_validation_repo.validate_trade_references.return_value = (True, [])
        mock_validation_repo.get_validation_errors.return_value = []

        trade_data = {
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'SELL',
            'trade_date': '2024-01-15',
            'quantity': 200,
            'price': 50.00
        }

        position = {'quantity': 100}  # Only 100 available

        with patch.object(self.repository, 'get_trade_detail', return_value=position):
            is_valid, errors, _ = self.repository.validate_trade_data(trade_data)

        self.assertFalse(is_valid)
        self.assertTrue(any("Insufficient quantity" in e for e in errors))

    # =========================================================================
    # GET_ALL_TRADES TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_trades(self, mock_execute):
        """Test fetching all trades"""
        mock_execute.return_value = [
            self.sample_trade,
            {**self.sample_trade, 'trade_id': 1002, 'deal_number': 'DEAL-20240101-1002'}
        ]

        result = self.repository.get_all_trades(limit=100)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['trade_id'], 1001)
        mock_execute.assert_called_once()

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_trades_with_status_filter(self, mock_execute):
        """Test fetching trades with status filter"""
        mock_execute.return_value = [self.sample_trade]

        result = self.repository.get_all_trades(limit=100, status='INITIAL')

        self.assertEqual(len(result), 1)
        mock_execute.assert_called_once()
        # Check that query contains status filter
        call_args = mock_execute.call_args[0][0]
        self.assertIn("status = 'INITIAL'", call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_trades_with_trade_type_filter(self, mock_execute):
        """Test fetching trades with trade type filter"""
        mock_execute.return_value = [self.sample_trade]

        result = self.repository.get_all_trades(limit=100, trade_type='BUY')

        self.assertEqual(len(result), 1)
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args[0][0]
        self.assertIn("trade_type = 'BUY'", call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_trades_with_search(self, mock_execute):
        """Test fetching trades with search query"""
        mock_execute.return_value = [self.sample_trade]

        result = self.repository.get_all_trades(limit=100, search='DEAL-2024')

        self.assertEqual(len(result), 1)
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args[0][0]
        self.assertIn("LIKE '%DEAL-2024%'", call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_trades_with_date_range(self, mock_execute):
        """Test fetching trades with date range filter"""
        mock_execute.return_value = [self.sample_trade]

        result = self.repository.get_all_trades(
            limit=100,
            trade_date_from='2024-01-01',
            trade_date_to='2024-01-31'
        )

        self.assertEqual(len(result), 1)
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args[0][0]
        self.assertIn("trade_date >= '2024-01-01'", call_args)
        self.assertIn("trade_date <= '2024-01-31'", call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_trades_exception(self, mock_execute):
        """Test get_all_trades handles exception gracefully"""
        mock_execute.side_effect = Exception("Database error")

        result = self.repository.get_all_trades(limit=100)

        self.assertEqual(result, [])

    # =========================================================================
    # GET_ALL_TRADES_MULTI_FILTER TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_trades_multi_filter_portfolios(self, mock_execute):
        """Test fetching trades with multiple portfolio filter"""
        mock_execute.return_value = [self.sample_trade]

        result = self.repository.get_all_trades_multi_filter(
            limit=100,
            portfolios=['PORT001', 'PORT002']
        )

        self.assertEqual(len(result), 1)
        call_args = mock_execute.call_args[0][0]
        self.assertIn("portfolio_short_name IN ('PORT001', 'PORT002')", call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_trades_multi_filter_securities(self, mock_execute):
        """Test fetching trades with multiple security filter"""
        mock_execute.return_value = [self.sample_trade]

        result = self.repository.get_all_trades_multi_filter(
            limit=100,
            securities=['SEC001', 'SEC002', 'SEC003']
        )

        self.assertEqual(len(result), 1)
        call_args = mock_execute.call_args[0][0]
        self.assertIn("security_label IN ('SEC001', 'SEC002', 'SEC003')", call_args)

    # =========================================================================
    # GET_TRADE_BY_ID TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_trade_by_id(self, mock_execute):
        """Test fetching trade by ID"""
        mock_execute.return_value = [self.sample_trade]

        result = self.repository.get_trade_by_id(1001)

        self.assertIsNotNone(result)
        self.assertEqual(result['trade_id'], 1001)
        self.assertEqual(result['deal_number'], 'DEAL-20240101-1001')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_trade_by_id_not_found(self, mock_execute):
        """Test fetching non-existent trade returns None"""
        mock_execute.return_value = []

        result = self.repository.get_trade_by_id(9999)

        self.assertIsNone(result)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_trade_by_id_exception(self, mock_execute):
        """Test get_trade_by_id handles exception"""
        mock_execute.side_effect = Exception("Database error")

        result = self.repository.get_trade_by_id(1001)

        self.assertIsNone(result)

    # =========================================================================
    # GET_TRADE_BY_DEAL_NUMBER TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_trade_by_deal_number(self, mock_execute):
        """Test fetching trade by deal number"""
        mock_execute.return_value = [self.sample_trade]

        result = self.repository.get_trade_by_deal_number('DEAL-20240101-1001')

        self.assertIsNotNone(result)
        self.assertEqual(result['deal_number'], 'DEAL-20240101-1001')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_trade_by_deal_number_not_found(self, mock_execute):
        """Test fetching non-existent deal number returns None"""
        mock_execute.return_value = []

        result = self.repository.get_trade_by_deal_number('NONEXISTENT')

        self.assertIsNone(result)

    # =========================================================================
    # INSERT_TRADE TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_insert_trade_success(self, mock_validation_repo, mock_execute_write):
        """Test inserting a new trade"""
        mock_validation_repo.validate_trade_references.return_value = (True, [])
        mock_validation_repo.get_validation_errors.return_value = []
        mock_validation_repo.get_portfolio_details.return_value = {'name': 'Test Portfolio'}
        mock_validation_repo.get_security_details.return_value = {
            'security_name': 'Test Security',
            'security_type': 'EQUITY'
        }
        mock_execute_write.return_value = True

        trade_data = {
            'trade_type': 'BUY',
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_date': '2024-01-15',
            'quantity': 100,
            'price': 50.00,
        }

        with patch.object(self.repository, 'insert_trade_history', return_value=True):
            with patch.object(self.repository, 'update_position_from_trade', return_value=True):
                result = self.repository.insert_trade(trade_data, created_by='testuser')

        self.assertIsNotNone(result)
        self.assertIsInstance(result, int)
        mock_execute_write.assert_called()

    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_insert_trade_validation_failure(self, mock_validation_repo):
        """Test insert fails when validation fails"""
        mock_validation_repo.validate_trade_references.return_value = (False, [])
        mock_validation_repo.get_validation_errors.return_value = ['Portfolio not found']

        trade_data = {
            'portfolio_short_name': 'INVALID',
            'security_label': 'SEC001',
            'trade_type': 'BUY',
            'trade_date': '2024-01-15',
            'quantity': 100,
            'price': 50.00
        }

        with self.assertRaises(ValueError) as context:
            self.repository.insert_trade(trade_data, created_by='testuser')

        self.assertIn("Portfolio not found", str(context.exception))

    # =========================================================================
    # UPDATE_TRADE TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    @patch('trade.repositories.trade_kudu_repository.trade_validation_repository')
    def test_update_trade_success(self, mock_validation_repo, mock_execute_write):
        """Test updating a trade"""
        mock_validation_repo.validate_trade_references.return_value = (True, [])
        mock_validation_repo.get_validation_errors.return_value = []
        mock_execute_write.return_value = True

        current_trade = {
            **self.sample_trade,
            'status': 'INITIAL'
        }

        updated_data = {
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'BUY',
            'trade_date': '2024-01-15',
            'quantity': 150,  # Changed
            'price': 52.00,   # Changed
        }

        with patch.object(self.repository, 'get_trade_by_id', return_value=current_trade):
            with patch.object(self.repository, 'insert_trade_history', return_value=True):
                result = self.repository.update_trade(1001, updated_data, 'testuser')

        self.assertTrue(result)
        mock_execute_write.assert_called()

    def test_update_trade_not_found(self):
        """Test update fails when trade not found"""
        with patch.object(self.repository, 'get_trade_by_id', return_value=None):
            with self.assertRaises(ValueError) as context:
                self.repository.update_trade(9999, {}, 'testuser')

        self.assertIn("not found", str(context.exception))

    def test_update_trade_invalid_status(self):
        """Test update fails when trade is not in editable status"""
        current_trade = {
            **self.sample_trade,
            'status': 'SETTLED'  # Cannot edit SETTLED trades
        }

        with patch.object(self.repository, 'get_trade_by_id', return_value=current_trade):
            with self.assertRaises(ValueError) as context:
                self.repository.update_trade(1001, {}, 'testuser')

        self.assertIn("Cannot edit trade", str(context.exception))

    # =========================================================================
    # SOFT_DELETE_TRADE TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_soft_delete_trade_success(self, mock_execute_write):
        """Test soft deleting a trade"""
        mock_execute_write.return_value = True

        with patch.object(self.repository, 'get_trade_by_id', return_value=self.sample_trade):
            with patch.object(self.repository, 'insert_trade_history', return_value=True):
                result = self.repository.soft_delete_trade(1001, 'testuser', 'Test reason')

        self.assertTrue(result)
        mock_execute_write.assert_called()

    def test_soft_delete_trade_not_found(self):
        """Test soft delete fails when trade not found"""
        with patch.object(self.repository, 'get_trade_by_id', return_value=None):
            result = self.repository.soft_delete_trade(9999, 'testuser')
            self.assertFalse(result)

    # =========================================================================
    # WORKFLOW TESTS - SUBMIT_FOR_VALIDATION
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_submit_for_validation_success(self, mock_execute_write):
        """Test submitting trade for validation"""
        mock_execute_write.return_value = True
        trade = {**self.sample_trade, 'status': 'INITIAL'}

        with patch.object(self.repository, 'get_trade_by_id', return_value=trade):
            with patch.object(self.repository, 'insert_trade_history', return_value=True):
                result = self.repository.submit_for_validation(1001, 'testuser')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]
        self.assertIn("PENDING_VALIDATION", call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_submit_for_validation_from_modified(self, mock_execute_write):
        """Test submitting MODIFIED trade for validation"""
        mock_execute_write.return_value = True
        trade = {**self.sample_trade, 'status': 'MODIFIED'}

        with patch.object(self.repository, 'get_trade_by_id', return_value=trade):
            with patch.object(self.repository, 'insert_trade_history', return_value=True):
                result = self.repository.submit_for_validation(1001, 'testuser')

        self.assertTrue(result)

    def test_submit_for_validation_invalid_status(self):
        """Test submit fails for invalid status"""
        trade = {**self.sample_trade, 'status': 'SETTLED'}

        with patch.object(self.repository, 'get_trade_by_id', return_value=trade):
            with self.assertRaises(ValueError) as context:
                self.repository.submit_for_validation(1001, 'testuser')

        self.assertIn("Cannot submit", str(context.exception))

    # =========================================================================
    # WORKFLOW TESTS - VALIDATE_TRADE
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_validate_trade_success(self, mock_execute_write):
        """Test validating a trade"""
        mock_execute_write.return_value = True
        trade = {
            **self.sample_trade,
            'status': 'PENDING_VALIDATION',
            'submitted_by': 'maker_user'
        }

        with patch.object(self.repository, 'get_trade_by_id', return_value=trade):
            with patch.object(self.repository, 'insert_trade_history', return_value=True):
                result = self.repository.validate_trade(1001, 'checker_user', 'Approved')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]
        self.assertIn("VALIDATED", call_args)

    def test_validate_trade_four_eyes_violation(self):
        """Test validate fails for four-eyes violation"""
        trade = {
            **self.sample_trade,
            'status': 'PENDING_VALIDATION',
            'submitted_by': 'same_user'
        }

        with patch.object(self.repository, 'get_trade_by_id', return_value=trade):
            with self.assertRaises(ValueError) as context:
                self.repository.validate_trade(1001, 'same_user', 'Approved')

        self.assertIn("Four-eyes", str(context.exception))

    def test_validate_trade_invalid_status(self):
        """Test validate fails for invalid status"""
        trade = {**self.sample_trade, 'status': 'INITIAL'}

        with patch.object(self.repository, 'get_trade_by_id', return_value=trade):
            with self.assertRaises(ValueError) as context:
                self.repository.validate_trade(1001, 'checker_user')

        self.assertIn("Cannot validate", str(context.exception))

    # =========================================================================
    # WORKFLOW TESTS - REJECT_TRADE
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_reject_trade_success(self, mock_execute_write):
        """Test rejecting a trade"""
        mock_execute_write.return_value = True
        trade = {**self.sample_trade, 'status': 'PENDING_VALIDATION'}

        with patch.object(self.repository, 'get_trade_by_id', return_value=trade):
            with patch.object(self.repository, 'insert_trade_history', return_value=True):
                result = self.repository.reject_trade(1001, 'checker_user', 'Rejected - invalid data')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]
        self.assertIn("CANCELLED", call_args)

    def test_reject_trade_invalid_status(self):
        """Test reject fails for invalid status"""
        trade = {**self.sample_trade, 'status': 'VALIDATED'}

        with patch.object(self.repository, 'get_trade_by_id', return_value=trade):
            with self.assertRaises(ValueError) as context:
                self.repository.reject_trade(1001, 'checker_user', 'Reason')

        self.assertIn("Cannot reject", str(context.exception))

    # =========================================================================
    # WORKFLOW TESTS - SETTLE_TRADE
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_settle_trade_success(self, mock_execute_write):
        """Test settling a trade"""
        mock_execute_write.return_value = True
        trade = {**self.sample_trade, 'status': 'VALIDATED'}

        with patch.object(self.repository, 'get_trade_by_id', return_value=trade):
            with patch.object(self.repository, 'insert_trade_history', return_value=True):
                result = self.repository.settle_trade(1001, 'settler_user', 'Settled')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]
        self.assertIn("SETTLED", call_args)
        self.assertIn("is_active = true", call_args)

    def test_settle_trade_invalid_status(self):
        """Test settle fails for invalid status"""
        trade = {**self.sample_trade, 'status': 'PENDING_VALIDATION'}

        with patch.object(self.repository, 'get_trade_by_id', return_value=trade):
            with self.assertRaises(ValueError) as context:
                self.repository.settle_trade(1001, 'settler_user')

        self.assertIn("Cannot settle", str(context.exception))

    # =========================================================================
    # TRADE DETAILS TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_trade_detail(self, mock_execute):
        """Test fetching trade detail"""
        position = {
            'position_id': 1,
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'quantity': 100,
            'average_cost': 50.00,
            'status': 'OPEN'
        }
        mock_execute.return_value = [position]

        result = self.repository.get_trade_detail('PORT001', 'SEC001')

        self.assertIsNotNone(result)
        self.assertEqual(result['quantity'], 100)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_trade_detail_not_found(self, mock_execute):
        """Test fetching non-existent trade detail"""
        mock_execute.return_value = []

        result = self.repository.get_trade_detail('PORT001', 'INVALID')

        self.assertIsNone(result)

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_update_position_from_trade_buy_new(self, mock_execute_write):
        """Test BUY trade creating new position with P&L calculations"""
        mock_execute_write.return_value = True
        trade = {
            'trade_id': 1001,
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'BUY',
            'quantity': 100,
            'price': 50.00,
            'total_amount': 5000.00,
            'trade_date': '2024-01-15'
        }

        with patch.object(self.repository, 'get_position', return_value=None), \
             patch.object(self.repository, '_get_equity_price', return_value=52.00), \
             patch.object(self.repository, 'get_next_id', return_value=1000001):
            result = self.repository.update_position_from_trade(trade, 'testuser')

        self.assertTrue(result)
        mock_execute_write.assert_called()

        # Verify SQL contains correct P&L values (UPSERT VALUES pattern)
        call_args = mock_execute_write.call_args[0][0]
        # market_value = 100 * 52 = 5200, unrealized_pnl = 5200 - 5000 = 200
        self.assertIn('5200.0', call_args)  # market_value
        self.assertIn('200.0', call_args)   # unrealized_pnl
        self.assertIn("'OPEN'", call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_update_position_from_trade_buy_new_no_equity_price(self, mock_execute_write):
        """Test BUY new position falls back to trade price when no equity price"""
        mock_execute_write.return_value = True
        trade = {
            'trade_id': 1001,
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'BUY',
            'quantity': 100,
            'price': 50.00,
            'total_amount': 5000.00,
            'trade_date': '2024-01-15'
        }

        with patch.object(self.repository, 'get_position', return_value=None), \
             patch.object(self.repository, '_get_equity_price', return_value=None), \
             patch.object(self.repository, 'get_next_id', return_value=1000001):
            result = self.repository.update_position_from_trade(trade, 'testuser')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]
        # When no equity price, falls back to trade price (50)
        # market_value = 100 * 50 = 5000, unrealized_pnl = 5000 - 5000 = 0
        self.assertIn('5000.0', call_args)  # market_value

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_update_position_from_trade_buy_existing(self, mock_execute_write):
        """Test BUY into existing position with weighted avg cost and P&L"""
        mock_execute_write.return_value = True
        trade = {
            'trade_id': 1002,
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'BUY',
            'quantity': 50,
            'price': 60.00,
            'total_amount': 3000.00,
            'trade_date': '2024-01-16'
        }
        existing_detail = {
            'position_id': 1,
            'quantity': 100,
            'average_cost': 50.00,
            'total_cost': 5000.00,
            'realized_pnl': 0
        }

        with patch.object(self.repository, 'get_position', return_value=existing_detail), \
             patch.object(self.repository, '_get_equity_price', return_value=58.00), \
             patch.object(self.repository, 'get_next_id', return_value=1000001):
            result = self.repository.update_position_from_trade(trade, 'testuser')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]

        # new_qty = 100 + 50 = 150
        # new_avg_cost = (100*50 + 50*60) / 150 = (5000+3000)/150 = 53.333...
        # new_total_cost = 150 * 53.333... = 8000
        # market_value = 150 * 58 = 8700
        # unrealized_pnl = 8700 - 8000 = 700
        self.assertIn('UPSERT INTO', call_args)
        self.assertIn('cis_trade_position', call_args)
        self.assertIn('8700.0', call_args)   # market_value
        self.assertIn('700.0', call_args)    # unrealized_pnl

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_update_position_from_trade_sell_partial(self, mock_execute_write):
        """Test SELL partial position with realized P&L calculation"""
        mock_execute_write.return_value = True
        trade = {
            'trade_id': 1003,
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'SELL',
            'quantity': 30,
            'price': 55.00,
            'total_amount': 1650.00,
            'trade_date': '2024-01-17'
        }
        existing_detail = {
            'position_id': 1,
            'quantity': 100,
            'average_cost': 50.00,
            'total_cost': 5000.00,
            'realized_pnl': 0
        }

        with patch.object(self.repository, 'get_position', return_value=existing_detail), \
             patch.object(self.repository, '_get_equity_price', return_value=55.00), \
             patch.object(self.repository, 'get_next_id', return_value=1000001):
            result = self.repository.update_position_from_trade(trade, 'testuser')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]

        # new_qty = 100 - 30 = 70
        # sell_cost_basis = 30 * 50 = 1500
        # realized_pnl_this_trade = 1650 - 1500 = 150
        # cumulative_realized_pnl = 0 + 150 = 150
        # new_total_cost = 70 * 50 = 3500 (avg_cost unchanged on sell)
        # market_value = 70 * 55 = 3850
        # unrealized_pnl = 3850 - 3500 = 350
        self.assertIn('UPSERT INTO', call_args)
        self.assertIn('cis_trade_position', call_args)
        self.assertIn('150.0', call_args)    # realized_pnl
        self.assertIn('3850.0', call_args)   # market_value
        self.assertIn('350.0', call_args)    # unrealized_pnl

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_update_position_from_trade_sell_full(self, mock_execute_write):
        """Test SELL full position closes it with cumulative realized P&L"""
        mock_execute_write.return_value = True
        trade = {
            'trade_id': 1004,
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'SELL',
            'quantity': 100,
            'price': 55.00,
            'total_amount': 5500.00,
            'trade_date': '2024-01-18'
        }
        existing_detail = {
            'position_id': 1,
            'quantity': 100,
            'average_cost': 50.00,
            'total_cost': 5000.00,
            'realized_pnl': 150.00  # Carried forward from previous sell
        }

        with patch.object(self.repository, 'get_position', return_value=existing_detail), \
             patch.object(self.repository, '_get_equity_price', return_value=55.00), \
             patch.object(self.repository, 'get_next_id', return_value=1000001):
            result = self.repository.update_position_from_trade(trade, 'testuser')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]

        # Full sell: qty becomes 0
        # sell_cost_basis = 100 * 50 = 5000
        # realized_pnl_this_trade = 5500 - 5000 = 500
        # cumulative_realized_pnl = 150 + 500 = 650
        self.assertIn('UPSERT INTO', call_args)
        self.assertIn('cis_trade_position', call_args)
        self.assertIn('650.0', call_args)    # realized_pnl
        self.assertIn("'CLOSED'", call_args)
        self.assertIn('false', call_args)    # is_active

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_update_position_sell_at_loss(self, mock_execute_write):
        """Test SELL at a loss produces negative realized P&L"""
        mock_execute_write.return_value = True
        trade = {
            'trade_id': 1005,
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'SELL',
            'quantity': 50,
            'price': 40.00,
            'total_amount': 2000.00,
            'trade_date': '2024-01-19'
        }
        existing_detail = {
            'position_id': 1,
            'quantity': 100,
            'average_cost': 50.00,
            'total_cost': 5000.00,
            'realized_pnl': 0
        }

        with patch.object(self.repository, 'get_position', return_value=existing_detail), \
             patch.object(self.repository, '_get_equity_price', return_value=40.00), \
             patch.object(self.repository, 'get_next_id', return_value=1000001):
            result = self.repository.update_position_from_trade(trade, 'testuser')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]
        # sell_cost_basis = 50 * 50 = 2500
        # realized_pnl = 2000 - 2500 = -500 (loss)
        # Check that -500 appears in the SQL
        self.assertIn('-500.0', call_args)

    def test_update_position_exception_returns_false(self):
        """Test update_position_from_trade returns False on exception"""
        trade = {
            'trade_id': 1001,
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_type': 'BUY',
            'quantity': 100,
            'price': 50.00,
            'trade_date': '2024-01-15'
        }

        with patch.object(self.repository, 'get_position', side_effect=Exception("DB error")):
            result = self.repository.update_position_from_trade(trade, 'testuser')

        self.assertFalse(result)

    # =========================================================================
    # HISTORY TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_write_async')
    def test_insert_trade_history_async(self, mock_execute_async):
        """Test inserting trade history asynchronously"""
        result = self.repository.insert_trade_history(
            trade_id=1001,
            deal_number='DEAL-001',
            action='CREATE',
            old_status=None,
            new_status='INITIAL',
            changes={},
            comments='Trade created',
            performed_by='testuser',
            async_write=True
        )

        self.assertTrue(result)
        mock_execute_async.assert_called_once()

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_insert_trade_history_sync(self, mock_execute_write):
        """Test inserting trade history synchronously"""
        mock_execute_write.return_value = True

        result = self.repository.insert_trade_history(
            trade_id=1001,
            deal_number='DEAL-001',
            action='CREATE',
            old_status=None,
            new_status='INITIAL',
            changes={},
            comments='Trade created',
            performed_by='testuser',
            async_write=False
        )

        self.assertTrue(result)
        mock_execute_write.assert_called_once()

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_trade_history(self, mock_execute):
        """Test fetching trade history"""
        history_records = [
            {'history_id': 1, 'action': 'CREATE', 'new_status': 'INITIAL'},
            {'history_id': 2, 'action': 'SUBMIT', 'new_status': 'PENDING_VALIDATION'}
        ]
        mock_execute.return_value = history_records

        result = self.repository.get_trade_history(1001)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['action'], 'CREATE')

    # =========================================================================
    # STATISTICS TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_trade_statistics(self, mock_execute):
        """Test fetching trade statistics"""
        mock_execute.return_value = [
            {'status': 'INITIAL', 'trade_type': 'BUY', 'count': 10},
            {'status': 'PENDING_VALIDATION', 'trade_type': 'BUY', 'count': 5},
            {'status': 'VALIDATED', 'trade_type': 'SELL', 'count': 3},
            {'status': 'SETTLED', 'trade_type': 'BUY', 'count': 20},
        ]

        result = self.repository.get_trade_statistics()

        self.assertEqual(result['total_trades'], 38)
        self.assertEqual(result['pending_validation'], 5)
        self.assertEqual(result['pending_settlement'], 3)
        self.assertEqual(result['settled'], 20)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_trade_statistics_empty(self, mock_execute):
        """Test fetching trade statistics with no data"""
        mock_execute.return_value = []

        result = self.repository.get_trade_statistics()

        self.assertEqual(result['total_trades'], 0)
        self.assertEqual(result['pending_validation'], 0)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_trade_statistics_exception(self, mock_execute):
        """Test get_trade_statistics handles exception"""
        mock_execute.side_effect = Exception("Database error")

        result = self.repository.get_trade_statistics()

        self.assertEqual(result['total_trades'], 0)

    # =========================================================================
    # PENDING TRADES TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_pending_validation_trades(self, mock_execute):
        """Test fetching pending validation trades"""
        mock_execute.return_value = [
            {**self.sample_trade, 'status': 'PENDING_VALIDATION'}
        ]

        result = self.repository.get_pending_validation_trades()

        self.assertEqual(len(result), 1)
        call_args = mock_execute.call_args[0][0]
        self.assertIn("PENDING_VALIDATION", call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_pending_settlement_trades(self, mock_execute):
        """Test fetching pending settlement trades"""
        mock_execute.return_value = [
            {**self.sample_trade, 'status': 'VALIDATED'}
        ]

        result = self.repository.get_pending_settlement_trades()

        self.assertEqual(len(result), 1)
        call_args = mock_execute.call_args[0][0]
        self.assertIn("VALIDATED", call_args)

    # =========================================================================
    # TRADE TYPE CONSTANTS TESTS
    # =========================================================================

    def test_trade_type_constants(self):
        """Test trade type constants are defined"""
        self.assertEqual(self.TradeKuduRepository.TRADE_TYPE_BUY, 'BUY')
        self.assertEqual(self.TradeKuduRepository.TRADE_TYPE_SELL, 'SELL')
        self.assertEqual(self.TradeKuduRepository.TRADE_TYPE_ADD_LONG, 'ADD_LONG')
        self.assertEqual(self.TradeKuduRepository.TRADE_TYPE_DELIVER_LONG, 'DELIVER_LONG')
        self.assertEqual(self.TradeKuduRepository.TRADE_TYPE_REDUCTION_BASIS, 'REDUCTION_BASIS')
        self.assertEqual(self.TradeKuduRepository.TRADE_TYPE_INCOME, 'INCOME')
        self.assertEqual(self.TradeKuduRepository.TRADE_TYPE_SPLIT_TRANSACTION, 'SPLIT_TRANSACTION')

    def test_all_trade_types_list(self):
        """Test ALL_TRADE_TYPES list contains all types"""
        self.assertEqual(len(self.TradeKuduRepository.ALL_TRADE_TYPES), 7)
        self.assertIn('BUY', self.TradeKuduRepository.ALL_TRADE_TYPES)
        self.assertIn('SELL', self.TradeKuduRepository.ALL_TRADE_TYPES)

    # =========================================================================
    # STATUS CONSTANTS TESTS
    # =========================================================================

    def test_status_constants(self):
        """Test status constants are defined"""
        self.assertEqual(self.TradeKuduRepository.STATUS_INITIAL, 'INITIAL')
        self.assertEqual(self.TradeKuduRepository.STATUS_MODIFIED, 'MODIFIED')
        self.assertEqual(self.TradeKuduRepository.STATUS_PENDING_VALIDATION, 'PENDING_VALIDATION')
        self.assertEqual(self.TradeKuduRepository.STATUS_VALIDATED, 'VALIDATED')
        self.assertEqual(self.TradeKuduRepository.STATUS_CANCELLED, 'CANCELLED')
        self.assertEqual(self.TradeKuduRepository.STATUS_SETTLED, 'SETTLED')

    def test_maker_editable_statuses(self):
        """Test MAKER_EDITABLE_STATUSES list"""
        expected = ['INITIAL', 'MODIFIED', 'CANCELLED']
        self.assertEqual(self.TradeKuduRepository.MAKER_EDITABLE_STATUSES, expected)

    def test_checker_actionable_statuses(self):
        """Test CHECKER_ACTIONABLE_STATUSES list"""
        expected = ['PENDING_VALIDATION', 'VALIDATED']
        self.assertEqual(self.TradeKuduRepository.CHECKER_ACTIONABLE_STATUSES, expected)

    # =========================================================================
    # GET_POSITION ALIAS TESTS
    # =========================================================================

    def test_get_position_alias(self):
        """Test get_trade_detail is an alias for get_position"""
        with patch.object(self.repository, 'get_position', return_value={'quantity': 100}) as mock_position:
            result = self.repository.get_trade_detail('PORT001', 'SEC001')

        self.assertEqual(result['quantity'], 100)
        mock_position.assert_called_once_with('PORT001', 'SEC001')

    # =========================================================================
    # GET_POSITION_BY_ID TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_position_by_id(self, mock_execute):
        """Test fetching position by position_id"""
        position = {
            'position_id': 42,
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'quantity': 100,
            'status': 'OPEN'
        }
        mock_execute.return_value = [position]

        result = self.repository.get_position_by_id(42)

        self.assertIsNotNone(result)
        self.assertEqual(result['position_id'], 42)
        call_args = mock_execute.call_args[0][0]
        self.assertIn('position_id = 42', call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_position_by_id_not_found(self, mock_execute):
        """Test get_position_by_id returns None when not found"""
        mock_execute.return_value = []

        result = self.repository.get_position_by_id(999)

        self.assertIsNone(result)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_position_by_id_exception(self, mock_execute):
        """Test get_position_by_id handles exception"""
        mock_execute.side_effect = Exception("DB error")

        result = self.repository.get_position_by_id(42)

        self.assertIsNone(result)

    # =========================================================================
    # GET_ALL_POSITIONS TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_positions(self, mock_execute):
        """Test fetching all positions"""
        mock_execute.return_value = [
            {'position_id': 1, 'status': 'OPEN'},
            {'position_id': 2, 'status': 'OPEN'}
        ]

        result = self.repository.get_all_positions()

        self.assertEqual(len(result), 2)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_positions_with_status_filter(self, mock_execute):
        """Test fetching positions with status filter"""
        mock_execute.return_value = [{'position_id': 1, 'status': 'OPEN'}]

        result = self.repository.get_all_positions(status='OPEN')

        self.assertEqual(len(result), 1)
        call_args = mock_execute.call_args[0][0]
        self.assertIn("status = 'OPEN'", call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_positions_empty(self, mock_execute):
        """Test get_all_positions returns empty list when no results"""
        mock_execute.return_value = []

        result = self.repository.get_all_positions()

        self.assertEqual(result, [])

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_positions_exception(self, mock_execute):
        """Test get_all_positions handles exception"""
        mock_execute.side_effect = Exception("DB error")

        result = self.repository.get_all_positions()

        self.assertEqual(result, [])

    # =========================================================================
    # GET_POSITION_VERSIONS TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_position_versions(self, mock_execute):
        """Test fetching position versions (history)"""
        mock_execute.return_value = [
            {'version': 1, 'trade_type': 'BUY', 'quantity': 100},
            {'version': 2, 'trade_type': 'SELL', 'quantity': 70}
        ]

        result = self.repository.get_position_versions(42)

        self.assertEqual(len(result), 2)
        call_args = mock_execute.call_args[0][0]
        self.assertIn('position_id = 42', call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_position_versions_empty(self, mock_execute):
        """Test get_position_versions returns empty list when none found"""
        mock_execute.return_value = []

        result = self.repository.get_position_versions(42)

        self.assertEqual(result, [])

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_position_versions_exception(self, mock_execute):
        """Test get_position_versions handles exception"""
        mock_execute.side_effect = Exception("DB error")

        result = self.repository.get_position_versions(42)

        self.assertEqual(result, [])

    # =========================================================================
    # GET_POSITION_STATISTICS TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_position_statistics(self, mock_execute):
        """Test fetching position statistics"""
        mock_execute.return_value = [{
            'total_positions': 5,
            'total_market_value': 50000.0,
            'total_unrealized_pnl': 2500.0,
            'total_realized_pnl': 1200.0
        }]

        result = self.repository.get_position_statistics()

        self.assertEqual(result['total_positions'], 5)
        self.assertEqual(result['total_market_value'], 50000.0)
        self.assertEqual(result['total_unrealized_pnl'], 2500.0)
        self.assertEqual(result['total_realized_pnl'], 1200.0)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_position_statistics_empty(self, mock_execute):
        """Test position statistics with no data"""
        mock_execute.return_value = []

        result = self.repository.get_position_statistics()

        self.assertEqual(result['total_positions'], 0)
        self.assertEqual(result['total_market_value'], 0)
        self.assertEqual(result['total_unrealized_pnl'], 0)
        self.assertEqual(result['total_realized_pnl'], 0)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_position_statistics_null_values(self, mock_execute):
        """Test position statistics handles null aggregates"""
        mock_execute.return_value = [{
            'total_positions': 0,
            'total_market_value': None,
            'total_unrealized_pnl': None,
            'total_realized_pnl': None
        }]

        result = self.repository.get_position_statistics()

        self.assertEqual(result['total_positions'], 0)
        self.assertEqual(result['total_market_value'], 0)
        self.assertEqual(result['total_unrealized_pnl'], 0)
        self.assertEqual(result['total_realized_pnl'], 0)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_position_statistics_exception(self, mock_execute):
        """Test position statistics handles exception"""
        mock_execute.side_effect = Exception("DB error")

        result = self.repository.get_position_statistics()

        self.assertEqual(result['total_positions'], 0)

    # =========================================================================
    # _GET_EQUITY_PRICE TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_equity_price_from_equity_table(self, mock_execute):
        """Test fetching equity price from cis_equity_price"""
        mock_execute.return_value = [{'main_closing_price': 52.50}]

        result = self.repository._get_equity_price('SEC001')

        self.assertAlmostEqual(result, 52.50)
        call_args = mock_execute.call_args[0][0]
        self.assertIn('cis_equity_price', call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_equity_price_no_fallback_to_security(self, mock_execute):
        """Test equity price returns None when no equity price found (no security fallback)"""
        mock_execute.return_value = []  # No equity price

        result = self.repository._get_equity_price('SEC001')

        self.assertIsNone(result)
        self.assertEqual(mock_execute.call_count, 1)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_equity_price_no_price_found(self, mock_execute):
        """Test returns None when no price available"""
        mock_execute.return_value = []  # No equity price

        result = self.repository._get_equity_price('SEC001')

        self.assertIsNone(result)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_equity_price_exception(self, mock_execute):
        """Test _get_equity_price handles exception"""
        mock_execute.side_effect = Exception("DB error")

        result = self.repository._get_equity_price('SEC001')

        self.assertIsNone(result)


    # =========================================================================
    # REFRESH_MARKET_VALUES TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_refresh_market_values(self, mock_execute_write):
        """Test batch refresh of market values"""
        mock_execute_write.return_value = True
        positions = [
            {
                'position_id': 1,
                'security_label': 'SEC001',
                'quantity': 100,
                'total_cost': 5000.0,
                'portfolio_short_name': 'PORT001'
            },
            {
                'position_id': 2,
                'security_label': 'SEC002',
                'quantity': 200,
                'total_cost': 10000.0,
                'portfolio_short_name': 'PORT001'
            }
        ]

        with patch.object(self.repository, 'get_all_positions', return_value=positions), \
             patch.object(self.repository, '_get_equity_price', side_effect=[55.00, 52.00]):
            result = self.repository.refresh_market_values()

        self.assertEqual(result['updated'], 2)
        self.assertEqual(result['skipped'], 0)
        self.assertEqual(result['errors'], 0)
        self.assertEqual(mock_execute_write.call_count, 2)

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_refresh_market_values_skips_no_price(self, mock_execute_write):
        """Test refresh skips positions with no available price"""
        positions = [
            {
                'position_id': 1,
                'security_label': 'SEC001',
                'quantity': 100,
                'total_cost': 5000.0
            }
        ]

        with patch.object(self.repository, 'get_all_positions', return_value=positions), \
             patch.object(self.repository, '_get_equity_price', return_value=None):
            result = self.repository.refresh_market_values()

        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['skipped'], 1)
        mock_execute_write.assert_not_called()

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_refresh_market_values_with_portfolio_filter(self, mock_execute_write):
        """Test refresh with portfolio filter"""
        mock_execute_write.return_value = True
        positions = [
            {
                'position_id': 1,
                'security_label': 'SEC001',
                'quantity': 100,
                'total_cost': 5000.0,
                'portfolio_short_name': 'PORT001'
            },
            {
                'position_id': 2,
                'security_label': 'SEC002',
                'quantity': 200,
                'total_cost': 10000.0,
                'portfolio_short_name': 'PORT002'
            }
        ]

        with patch.object(self.repository, 'get_all_positions', return_value=positions), \
             patch.object(self.repository, '_get_equity_price', return_value=55.00):
            result = self.repository.refresh_market_values(portfolio_filter='PORT001')

        # Only PORT001 should be updated
        self.assertEqual(result['updated'], 1)

    def test_refresh_market_values_no_positions(self):
        """Test refresh with no open positions"""
        with patch.object(self.repository, 'get_all_positions', return_value=[]):
            result = self.repository.refresh_market_values()

        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['skipped'], 0)
        self.assertEqual(result['errors'], 0)

    # =========================================================================
    # SPREADSHEET SCENARIO: 5-TRADE P&L LIFECYCLE TEST
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_spreadsheet_pnl_lifecycle(self, mock_execute_write):
        """
        Test the complete 5-trade lifecycle from Trade_Example.xlsx:
        Trade 1: BUY 100 @ 10 -> Position: qty=100, avg=10, cost=1000
        Trade 2: BUY 50 @ 12  -> Position: qty=150, avg=10.67, cost=1600
        Trade 3: SELL 30 @ 15 -> Position: qty=120, realized=130 (450 - 320)
        Trade 4: SELL 120 @ 8 -> Position: CLOSED, realized=130+(-320)=-190
        Trade 5: BUY 200 @ 9  -> New Position: qty=200, avg=9, cost=1800
        """
        mock_execute_write.return_value = True

        # ---- Trade 1: BUY 100 @ 10, equity_price = 10 ----
        trade1 = {
            'trade_id': 1, 'portfolio_short_name': 'ABC',
            'security_label': 'BC', 'trade_type': 'BUY',
            'quantity': 100, 'price': 10.00, 'total_amount': 1000.00,
            'trade_date': '2024-01-01'
        }

        with patch.object(self.repository, 'get_position', return_value=None), \
             patch.object(self.repository, '_get_equity_price', return_value=10.00), \
             patch.object(self.repository, 'get_next_id', return_value=1000001):
            result = self.repository.update_position_from_trade(trade1, 'user')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]
        self.assertIn('UPSERT INTO', call_args)
        self.assertIn('cis_trade_position', call_args)
        # market_value = 100 * 10 = 1000, unrealized = 0
        self.assertIn('1000.0', call_args)

        # ---- Trade 2: BUY 50 @ 12, equity_price = 10 ----
        trade2 = {
            'trade_id': 2, 'portfolio_short_name': 'ABC',
            'security_label': 'BC', 'trade_type': 'BUY',
            'quantity': 50, 'price': 12.00, 'total_amount': 600.00,
            'trade_date': '2024-01-02'
        }
        existing_after_t1 = {
            'position_id': 1, 'quantity': 100,
            'average_cost': 10.00, 'total_cost': 1000.00,
            'realized_pnl': 0
        }

        with patch.object(self.repository, 'get_position', return_value=existing_after_t1), \
             patch.object(self.repository, '_get_equity_price', return_value=10.00), \
             patch.object(self.repository, 'get_next_id', return_value=1000002):
            result = self.repository.update_position_from_trade(trade2, 'user')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]
        # new_qty = 150, new_avg = (100*10 + 50*12)/150 = 1600/150 = 10.666...
        # market_value = 150 * 10 = 1500
        self.assertIn('UPSERT INTO', call_args)
        self.assertIn('1500.0', call_args)

        # ---- Trade 3: SELL 30 @ 15, equity_price = 10 ----
        trade3 = {
            'trade_id': 3, 'portfolio_short_name': 'ABC',
            'security_label': 'BC', 'trade_type': 'SELL',
            'quantity': 30, 'price': 15.00, 'total_amount': 450.00,
            'trade_date': '2024-01-03'
        }
        avg_cost_after_t2 = 1600 / 150
        existing_after_t2 = {
            'position_id': 1, 'quantity': 150,
            'average_cost': avg_cost_after_t2, 'total_cost': 1600.00,
            'realized_pnl': 0
        }

        with patch.object(self.repository, 'get_position', return_value=existing_after_t2), \
             patch.object(self.repository, '_get_equity_price', return_value=10.00), \
             patch.object(self.repository, 'get_next_id', return_value=1000003):
            result = self.repository.update_position_from_trade(trade3, 'user')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]
        # new_qty = 150 - 30 = 120
        # realized_pnl_this_trade = 450 - 320 = 130
        self.assertIn('UPSERT INTO', call_args)
        self.assertIn('130.0', call_args)  # realized_pnl

        # ---- Trade 4: SELL 120 @ 8, equity_price = 10 -> CLOSE ----
        trade4 = {
            'trade_id': 4, 'portfolio_short_name': 'ABC',
            'security_label': 'BC', 'trade_type': 'SELL',
            'quantity': 120, 'price': 8.00, 'total_amount': 960.00,
            'trade_date': '2024-01-04'
        }
        new_total_cost_after_t3 = 120 * avg_cost_after_t2
        existing_after_t3 = {
            'position_id': 1, 'quantity': 120,
            'average_cost': avg_cost_after_t2, 'total_cost': new_total_cost_after_t3,
            'realized_pnl': 130.00
        }

        with patch.object(self.repository, 'get_position', return_value=existing_after_t3), \
             patch.object(self.repository, '_get_equity_price', return_value=10.00), \
             patch.object(self.repository, 'get_next_id', return_value=1000004):
            result = self.repository.update_position_from_trade(trade4, 'user')

        self.assertTrue(result)
        close_call_args = mock_execute_write.call_args[0][0]
        # Full sell -> position closed
        self.assertIn("'CLOSED'", close_call_args)
        self.assertIn('false', close_call_args)  # is_active

        # ---- Trade 5: BUY 200 @ 9 -> New Position ----
        trade5 = {
            'trade_id': 5, 'portfolio_short_name': 'ABC',
            'security_label': 'BC', 'trade_type': 'BUY',
            'quantity': 200, 'price': 9.00, 'total_amount': 1800.00,
            'trade_date': '2024-01-05'
        }

        with patch.object(self.repository, 'get_position', return_value=None), \
             patch.object(self.repository, '_get_equity_price', return_value=10.00), \
             patch.object(self.repository, 'get_next_id', return_value=1000005):
            result = self.repository.update_position_from_trade(trade5, 'user')

        self.assertTrue(result)
        call_args = mock_execute_write.call_args[0][0]
        # quantity = 200, avg_cost = 9.00
        # market_value = 200 * 10 = 2000
        self.assertIn('UPSERT INTO', call_args)
        self.assertIn('2000.0', call_args)
