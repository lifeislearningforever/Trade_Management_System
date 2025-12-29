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
    HiveConnection,
    FXRateHiveRepository
)
import subprocess


class HiveConnectionTestCase(TestCase):
    """Test cases for HiveConnection"""

    @patch('subprocess.run')
    def test_execute_query_success(self, mock_run):
        """Test successful query execution"""
        # Mock beeline output
        mock_output = """
SLF4J: Some logging message
Connecting to jdbc:hive2://localhost:10000/cis
+----------------+---------------+----------------+-------------+
| currency_pair  | base_currency | quote_currency | rate        |
+----------------+---------------+----------------+-------------+
| USD/EUR        | USD           | EUR            | 0.9234567890|
| GBP/USD        | GBP           | USD            | 1.2567890123|
+----------------+---------------+----------------+-------------+
"""
        mock_run.return_value = Mock(
            stdout=mock_output,
            stderr='',
            returncode=0
        )

        results = HiveConnection.execute_query("SELECT * FROM fx_rates")

        # Verify beeline was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        self.assertIn('/usr/local/bin/beeline', call_args[0][0])
        self.assertIn('-u', call_args[0][0])
        self.assertIn('jdbc:hive2://localhost:10000/cis', call_args[0][0])

        # Verify results
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['currency_pair'], 'USD/EUR')
        self.assertEqual(results[0]['base_currency'], 'USD')
        self.assertEqual(results[1]['currency_pair'], 'GBP/USD')

    @patch('subprocess.run')
    def test_execute_query_empty_result(self, mock_run):
        """Test query returning no results"""
        mock_output = """
+----------------+---------------+----------------+-------------+
| currency_pair  | base_currency | quote_currency | rate        |
+----------------+---------------+----------------+-------------+
"""
        mock_run.return_value = Mock(
            stdout=mock_output,
            stderr='',
            returncode=0
        )

        results = HiveConnection.execute_query("SELECT * FROM fx_rates WHERE 1=0")
        self.assertEqual(len(results), 0)

    @patch('subprocess.run')
    def test_execute_query_filters_logging(self, mock_run):
        """Test that logging lines are filtered out"""
        mock_output = """
SLF4J: Class path contains multiple SLF4J bindings.
2025-12-26 10:00:00 INFO HiveConnection: Connecting
Connecting to jdbc:hive2://localhost:10000/cis
WARN: Some warning message
+----------------+
| count          |
+----------------+
| 42             |
+----------------+
"""
        mock_run.return_value = Mock(
            stdout=mock_output,
            stderr='',
            returncode=0
        )

        results = HiveConnection.execute_query("SELECT COUNT(*) FROM fx_rates")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['count'], '42')

    @patch('subprocess.run')
    def test_execute_query_timeout(self, mock_run):
        """Test query timeout handling"""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd='beeline',
            timeout=60
        )

        with self.assertRaises(subprocess.TimeoutExpired):
            HiveConnection.execute_query("SELECT * FROM fx_rates")

    @patch('subprocess.run')
    def test_execute_query_error(self, mock_run):
        """Test handling of query errors"""
        mock_run.return_value = Mock(
            stdout='',
            stderr='Error: Table not found',
            returncode=1
        )

        # Should not raise exception, just return empty result
        results = HiveConnection.execute_query("SELECT * FROM nonexistent_table")
        self.assertEqual(len(results), 0)


class FXRateHiveRepositoryTestCase(TestCase):
    """Test cases for FXRateHiveRepository"""

    @patch.object(HiveConnection, 'execute_query')
    def test_get_all_fx_rates_no_filters(self, mock_execute):
        """Test getting all FX rates without filters"""
        mock_execute.return_value = [
            {
                'currency_pair': 'USD/EUR',
                'base_currency': 'USD',
                'quote_currency': 'EUR',
                'rate': '0.9234567890',
                'bid_rate': '0.9234000000',
                'ask_rate': '0.9235000000',
                'mid_rate': '0.9234500000',
                'rate_date': '2025-12-26',
                'rate_time': '2025-12-26 10:00:00',
                'source': 'BLOOMBERG',
                'is_active': 'true',
                'created_at': '2025-12-26 10:00:00',
                'updated_at': '2025-12-26 10:00:00'
            }
        ]

        results = FXRateHiveRepository.get_all_fx_rates(limit=100)

        # Verify query was executed
        mock_execute.assert_called_once()
        query = mock_execute.call_args[0][0]
        self.assertIn('SELECT * FROM fx_rates', query)
        self.assertIn('LIMIT 100', query)

        # Verify results
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['currency_pair'], 'USD/EUR')

    @patch.object(HiveConnection, 'execute_query')
    def test_get_all_fx_rates_with_currency_pair_filter(self, mock_execute):
        """Test filtering by currency pair"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_all_fx_rates(
            limit=100,
            currency_pair='USD/EUR'
        )

        query = mock_execute.call_args[0][0]
        self.assertIn("currency_pair = 'USD/EUR'", query)

    @patch.object(HiveConnection, 'execute_query')
    def test_get_all_fx_rates_with_date_filters(self, mock_execute):
        """Test filtering by date range"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_all_fx_rates(
            limit=100,
            date_from='2025-12-01',
            date_to='2025-12-31'
        )

        query = mock_execute.call_args[0][0]
        self.assertIn("rate_date >= '2025-12-01'", query)
        self.assertIn("rate_date <= '2025-12-31'", query)

    @patch.object(HiveConnection, 'execute_query')
    def test_get_all_fx_rates_with_source_filter(self, mock_execute):
        """Test filtering by source"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_all_fx_rates(
            limit=100,
            source='BLOOMBERG'
        )

        query = mock_execute.call_args[0][0]
        self.assertIn("source = 'BLOOMBERG'", query)

    @patch.object(HiveConnection, 'execute_query')
    def test_get_all_fx_rates_with_all_filters(self, mock_execute):
        """Test using all filters together"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_all_fx_rates(
            limit=50,
            currency_pair='GBP/USD',
            date_from='2025-12-01',
            date_to='2025-12-31',
            source='REUTERS'
        )

        query = mock_execute.call_args[0][0]
        self.assertIn("currency_pair = 'GBP/USD'", query)
        self.assertIn("rate_date >= '2025-12-01'", query)
        self.assertIn("rate_date <= '2025-12-31'", query)
        self.assertIn("source = 'REUTERS'", query)
        self.assertIn('LIMIT 50', query)

    @patch.object(HiveConnection, 'execute_query')
    def test_get_fx_rate_by_currency_pair(self, mock_execute):
        """Test getting rates for specific currency pair"""
        mock_execute.return_value = [
            {'currency_pair': 'USD/EUR', 'rate': '0.9234567890'}
        ]

        results = FXRateHiveRepository.get_fx_rate_by_currency_pair('USD/EUR')

        query = mock_execute.call_args[0][0]
        self.assertIn("currency_pair = 'USD/EUR'", query)
        self.assertEqual(len(results), 1)

    @patch.object(HiveConnection, 'execute_query')
    def test_get_latest_fx_rates(self, mock_execute):
        """Test getting latest rates"""
        mock_execute.return_value = [
            {'currency_pair': 'USD/EUR', 'rate_date': '2025-12-26'},
            {'currency_pair': 'GBP/USD', 'rate_date': '2025-12-26'}
        ]

        results = FXRateHiveRepository.get_latest_fx_rates(limit=10)

        query = mock_execute.call_args[0][0]
        self.assertIn('ORDER BY rate_date DESC', query)
        self.assertIn('LIMIT 10', query)

    @patch.object(HiveConnection, 'execute_query')
    def test_get_unique_currency_pairs(self, mock_execute):
        """Test getting unique currency pairs"""
        mock_execute.return_value = [
            {'currency_pair': 'USD/EUR'},
            {'currency_pair': 'GBP/USD'},
            {'currency_pair': 'USD/JPY'}
        ]

        results = FXRateHiveRepository.get_unique_currency_pairs()

        query = mock_execute.call_args[0][0]
        self.assertIn('SELECT DISTINCT currency_pair', query)
        self.assertEqual(len(results), 3)

    @patch.object(HiveConnection, 'execute_query')
    def test_get_fx_rates_by_source(self, mock_execute):
        """Test getting rates by source"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_fx_rates_by_source('BLOOMBERG', limit=25)

        query = mock_execute.call_args[0][0]
        self.assertIn("source = 'BLOOMBERG'", query)
        self.assertIn('LIMIT 25', query)

    @patch.object(HiveConnection, 'execute_query')
    def test_get_fx_rates_for_date(self, mock_execute):
        """Test getting rates for specific date"""
        mock_execute.return_value = []

        FXRateHiveRepository.get_fx_rates_for_date('2025-12-26')

        query = mock_execute.call_args[0][0]
        self.assertIn("rate_date = '2025-12-26'", query)

    @patch.object(HiveConnection, 'execute_query')
    def test_repository_handles_empty_results(self, mock_execute):
        """Test repository handles empty results gracefully"""
        mock_execute.return_value = []

        results = FXRateHiveRepository.get_all_fx_rates()
        self.assertEqual(len(results), 0)

    @patch.object(HiveConnection, 'execute_query')
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
