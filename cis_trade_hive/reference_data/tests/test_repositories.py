"""
Reference Data Repository Tests

Tests for reference data repository operations.
"""

import pytest
from django.test import TestCase
from unittest.mock import patch, Mock


class ReferenceDataRepositoryTestCase(TestCase):
    """Test cases for Reference Data repositories"""

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_currencies(self, mock_execute):
        """Test fetching all currencies"""
        from reference_data.repositories import currency_repository

        mock_execute.return_value = [
            {'iso_code': 'USD', 'name': 'US Dollar', 'symbol': '$'},
            {'iso_code': 'EUR', 'name': 'Euro', 'symbol': '€'}
        ]

        result = currency_repository.list_all()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['code'], 'USD')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_countries(self, mock_execute):
        """Test fetching all countries"""
        from reference_data.repositories import country_repository

        mock_execute.return_value = [
            {'label': 'US', 'full_name': 'United States'},
            {'label': 'UK', 'full_name': 'United Kingdom'}
        ]

        result = country_repository.list_all()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['code'], 'US')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_calendars(self, mock_execute):
        """Test fetching all calendars"""
        from reference_data.repositories import calendar_repository

        mock_execute.return_value = [
            {'calendar_label': 'NYC', 'calendar_description': 'New York'},
            {'calendar_label': 'LON', 'calendar_description': 'London'}
        ]

        result = calendar_repository.list_all()

        self.assertEqual(len(result), 2)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_counterparties(self, mock_execute):
        """Test fetching all counterparties"""
        from reference_data.repositories import counterparty_repository

        mock_execute.return_value = [
            {'code': 'CP001', 'name': 'ABC Bank', 'legal_name': 'ABC Banking Corporation'},
            {'code': 'CP002', 'name': 'XYZ Corp', 'legal_name': 'XYZ Corporation'}
        ]

        result = counterparty_repository.list_all()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['code'], 'CP001')
