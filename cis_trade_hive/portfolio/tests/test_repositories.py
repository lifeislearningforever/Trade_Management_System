"""
Portfolio Repository Tests

Tests for portfolio Hive/Kudu repository operations.
"""

import pytest
from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock


class PortfolioHiveRepositoryTestCase(TestCase):
    """Test cases for PortfolioHiveRepository"""

    def setUp(self):
        """Set up test data"""
        from portfolio.repositories.portfolio_hive_repository import portfolio_hive_repository
        self.repository = portfolio_hive_repository

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_portfolios(self, mock_execute):
        """Test fetching all portfolios"""
        mock_execute.return_value = [
            {'name': 'PORT1', 'status': 'ACTIVE', 'currency': 'USD'},
            {'name': 'PORT2', 'status': 'DRAFT', 'currency': 'EUR'}
        ]

        result = self.repository.get_all_portfolios(limit=100)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'PORT1')
        mock_execute.assert_called_once()

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_portfolio_by_code(self, mock_execute):
        """Test fetching portfolio by code"""
        mock_execute.return_value = [
            {'name': 'PORT1', 'status': 'ACTIVE', 'currency': 'USD'}
        ]

        result = self.repository.get_portfolio_by_code('PORT1')

        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'PORT1')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_portfolio_by_code_not_found(self, mock_execute):
        """Test fetching non-existent portfolio"""
        mock_execute.return_value = []

        result = self.repository.get_portfolio_by_code('NONEXISTENT')

        self.assertIsNone(result)

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_insert_portfolio(self, mock_execute):
        """Test inserting new portfolio"""
        mock_execute.return_value = True

        portfolio_data = {
            'name': 'NEW_PORT',
            'description': 'Test',
            'currency': 'USD',
            'manager': 'John Doe'
        }

        result = self.repository.insert_portfolio(portfolio_data, created_by='testuser')

        self.assertTrue(result)
        mock_execute.assert_called_once()

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_update_portfolio_status(self, mock_execute):
        """Test updating portfolio status"""
        mock_execute.return_value = True

        result = self.repository.update_portfolio_status(
            portfolio_code='PORT1',
            status='APPROVED',
            is_active=True,
            updated_by='testuser'
        )

        self.assertTrue(result)
        mock_execute.assert_called_once()

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_currencies(self, mock_execute):
        """Test fetching distinct currencies"""
        mock_execute.return_value = [
            {'currency': 'USD'},
            {'currency': 'EUR'},
            {'currency': 'GBP'}
        ]

        result = self.repository.get_currencies()

        self.assertEqual(len(result), 3)
        self.assertIn('USD', result)
