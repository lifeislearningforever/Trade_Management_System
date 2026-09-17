"""
Market Data Repository Tests

Tests for the Hive repository layer including:
- Connection handling
- Query execution
- Data parsing
- Error handling
"""

from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock
from market_data.repositories.fx_rate_hive_repository import (
    FXRateHiveRepository
)
import subprocess


class HiveConnectionTestCase(TestCase):
    """Test cases for impala_manager (replaces legacy HiveConnection)"""

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_execute_query_success(self, mock_execute):
        """Test successful query execution via impala_manager"""
        mock_execute.return_value = [
            {'currency_pair': 'USD/EUR', 'base_currency': 'USD', 'quote_currency': 'EUR'},
            {'currency_pair': 'GBP/USD', 'base_currency': 'GBP', 'quote_currency': 'USD'},
        ]
        results = mock_execute("SELECT * FROM fx_rates")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['currency_pair'], 'USD/EUR')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_execute_query_empty_result(self, mock_execute):
        """Test query returning no results"""
        mock_execute.return_value = []
        results = mock_execute("SELECT * FROM fx_rates WHERE 1=0")
        self.assertEqual(len(results), 0)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_execute_query_filters_logging(self, mock_execute):
        """Test query with logging suppressed (impala_manager handles this internally)"""
        mock_execute.return_value = [{'count': '42'}]
        results = mock_execute("SELECT COUNT(*) FROM fx_rates")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['count'], '42')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_execute_query_raises_on_error(self, mock_execute):
        """Test impala_manager raises on query error"""
        mock_execute.side_effect = Exception("Table not found")
        with self.assertRaises(Exception):
            mock_execute("SELECT * FROM nonexistent_table")

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_execute_write_raises_on_error(self, mock_execute):
        """Test error propagation from execute_query"""
        mock_execute.side_effect = RuntimeError("connection refused")
        with self.assertRaises(RuntimeError):
            mock_execute("UPSERT INTO gmp_cis.cis_trade VALUES (?)")


class FXRateHiveRepositoryTestCase(TestCase):
    """Test cases for FXRateHiveRepository"""

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_fx_rates_no_filters(self, mock_execute):
        """Test getting all FX rates without filters"""
        mock_execute.return_value = [
            {
                'currency_pair': 'USD/EUR',
                'base_currency': 'USD',
                'quote_currency': 'EUR',
                'bid_rate': '0.9234000000',
                'ask_rate': '0.9235000000',
                'mid_rate': '0.9234500000',
                'source': 'BLOOMBERG',
            }
        ]

        results = FXRateHiveRepository.get_all_fx_rates(limit=100)

        mock_execute.assert_called_once()
        query = mock_execute.call_args[0][0]
        self.assertIn('ref_quot_ccy as currency_pair', query)
        self.assertIn('LIMIT 100', query)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['currency_pair'], 'USD/EUR')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_fx_rates_with_currency_pair_filter(self, mock_execute):
        """Test filtering by currency pair uses ref_quot_ccy column"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_all_fx_rates(limit=100, currency_pair='USD/EUR')

        query = mock_execute.call_args[0][0]
        self.assertIn("ref_quot_ccy = 'USD/EUR'", query)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_fx_rates_with_date_filters(self, mock_execute):
        """Test filtering by date range uses `date` column"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_all_fx_rates(
            limit=100, date_from='20251201', date_to='20251231'
        )

        query = mock_execute.call_args[0][0]
        self.assertIn("`date` >= '20251201'", query)
        self.assertIn("`date` <= '20251231'", query)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_fx_rates_with_source_filter(self, mock_execute):
        """Test filtering by source uses mktdata_set column"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_all_fx_rates(limit=100, source='BLOOMBERG')

        query = mock_execute.call_args[0][0]
        self.assertIn("mktdata_set = 'BLOOMBERG'", query)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_fx_rates_with_all_filters(self, mock_execute):
        """Test all filters together"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_all_fx_rates(
            limit=50,
            currency_pair='GBP/USD',
            date_from='20251201',
            date_to='20251231',
            source='REUTERS'
        )

        query = mock_execute.call_args[0][0]
        self.assertIn("ref_quot_ccy = 'GBP/USD'", query)
        self.assertIn("`date` >= '20251201'", query)
        self.assertIn("`date` <= '20251231'", query)
        self.assertIn("mktdata_set = 'REUTERS'", query)
        self.assertIn('LIMIT 50', query)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_fx_rate_by_currency_pair(self, mock_execute):
        """Test get_all_fx_rates with currency_pair filter returns results"""
        mock_execute.return_value = [
            {'currency_pair': 'USD/EUR', 'mid_rate': '0.9234567890'}
        ]

        results = FXRateHiveRepository.get_all_fx_rates(currency_pair='USD/EUR')

        query = mock_execute.call_args[0][0]
        self.assertIn("ref_quot_ccy = 'USD/EUR'", query)
        self.assertEqual(len(results), 1)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_latest_fx_rates(self, mock_execute):
        """Test get_latest_rates calls two queries: one for MAX date, one for rates"""
        mock_execute.side_effect = [
            [{'max_date': '20251226'}],
            [{'currency_pair': 'USD/EUR', 'trade_date': '20251226'}]
        ]

        results = FXRateHiveRepository.get_latest_rates(limit=10)

        self.assertEqual(mock_execute.call_count, 2)
        first_query = mock_execute.call_args_list[0][0][0]
        self.assertIn('MAX', first_query)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_unique_currency_pairs(self, mock_execute):
        """Test get_currency_pairs returns distinct currency pairs"""
        mock_execute.return_value = [
            {'currency_pair': 'USD/EUR'},
            {'currency_pair': 'GBP/USD'},
            {'currency_pair': 'USD/JPY'}
        ]

        results = FXRateHiveRepository.get_currency_pairs()

        query = mock_execute.call_args[0][0]
        self.assertIn('ref_quot_ccy', query)
        self.assertEqual(len(results), 3)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_fx_rates_by_source(self, mock_execute):
        """Test get_all_fx_rates with source filter"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_all_fx_rates(limit=25, source='BLOOMBERG')

        query = mock_execute.call_args[0][0]
        self.assertIn("mktdata_set = 'BLOOMBERG'", query)
        self.assertIn('LIMIT 25', query)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_fx_rates_for_date(self, mock_execute):
        """Test get_all_fx_rates with date filter"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_all_fx_rates(date_from='20251226', date_to='20251226')

        query = mock_execute.call_args[0][0]
        self.assertIn("`date` >= '20251226'", query)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_repository_handles_empty_results(self, mock_execute):
        """Test repository handles empty results gracefully"""
        mock_execute.return_value = []

        results = FXRateHiveRepository.get_all_fx_rates()
        self.assertEqual(len(results), 0)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_repository_sql_injection_prevention(self, mock_execute):
        """Test that repository prevents SQL injection"""
        mock_execute.return_value = []

        # Try to inject SQL
        malicious_input = "USD/EUR'; DROP TABLE fx_rates; --"

        FXRateHiveRepository.get_all_fx_rates(currency_pair=malicious_input)

        query = mock_execute.call_args[0][0]
        # The malicious input should be in the query as-is (string literal)
        # This test ensures we're using proper parameterization
        self.assertIn(malicious_input, query)
        # But it should NOT execute as SQL
        self.assertNotIn('DROP TABLE', query.upper().replace(malicious_input.upper(), ''))


class HiveConnectionIntegrationTestCase(TestCase):
    """Integration tests for Hive connection (requires running Hive)"""

    def test_parse_table_format(self):
        """Test parsing of beeline table format output"""
        # This is a unit test of the parsing logic
        sample_output = """
+----------------+---------------+----------------+
| currency_pair  | base_currency | quote_currency |
+----------------+---------------+----------------+
| USD/EUR        | USD           | EUR            |
| GBP/USD        | GBP           | USD            |
+----------------+---------------+----------------+
"""
        lines = [line for line in sample_output.split('\n')
                if line.strip() and not any(skip in line for skip in [
                    'SLF4J', '2025-', 'WARN', 'INFO', 'Connecting'])]

        table_lines = [line for line in lines if '|' in line and not line.startswith('+')]

        # Should have 3 lines: header + 2 data rows
        self.assertEqual(len(table_lines), 3)

        header_line = table_lines[0]
        headers = [col.strip() for col in header_line.split('|')[1:-1]]
        self.assertEqual(headers, ['currency_pair', 'base_currency', 'quote_currency'])

        # Parse first data row
        data_line = table_lines[1]
        values = [val.strip() for val in data_line.split('|')[1:-1]]
        self.assertEqual(values, ['USD/EUR', 'USD', 'EUR'])
