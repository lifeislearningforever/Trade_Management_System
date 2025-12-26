"""
Market Data View Tests

Tests for Market Data views including:
- FX Rate list view
- FX Dashboard view
- FX Rate detail view
- CSV export functionality
"""

from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, Mock
from market_data.repositories.fx_rate_hive_repository import FXRateHiveRepository


class FXRateListViewTestCase(TestCase):
    """Test cases for FX Rate list view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('market_data:fx_rate_list')

        # Sample data for mocking
        self.sample_fx_data = [
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
                'is_active': 'true'
            },
            {
                'currency_pair': 'GBP/USD',
                'base_currency': 'GBP',
                'quote_currency': 'USD',
                'rate': '1.2567890123',
                'bid_rate': '1.2567000000',
                'ask_rate': '1.2568500000',
                'mid_rate': '1.2567750000',
                'rate_date': '2025-12-26',
                'rate_time': '2025-12-26 10:00:00',
                'source': 'REUTERS',
                'is_active': 'true'
            }
        ]

    @patch.object(FXRateHiveRepository, 'get_all_fx_rates')
    @patch.object(FXRateHiveRepository, 'get_unique_currency_pairs')
    def test_fx_rate_list_view_success(self, mock_currency_pairs, mock_get_all):
        """Test FX rate list view loads successfully"""
        mock_get_all.return_value = self.sample_fx_data
        mock_currency_pairs.return_value = [
            {'currency_pair': 'USD/EUR'},
            {'currency_pair': 'GBP/USD'}
        ]

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'market_data/fx_rate_list.html')
        self.assertIn('fx_rates', response.context)
        self.assertEqual(len(response.context['fx_rates']), 2)

    @patch.object(FXRateHiveRepository, 'get_all_fx_rates')
    @patch.object(FXRateHiveRepository, 'get_unique_currency_pairs')
    def test_fx_rate_list_view_empty(self, mock_currency_pairs, mock_get_all):
        """Test FX rate list view with no data"""
        mock_get_all.return_value = []
        mock_currency_pairs.return_value = []

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['fx_rates']), 0)

    @patch.object(FXRateHiveRepository, 'get_all_fx_rates')
    @patch.object(FXRateHiveRepository, 'get_unique_currency_pairs')
    def test_fx_rate_list_search_filter(self, mock_currency_pairs, mock_get_all):
        """Test search filtering"""
        mock_get_all.return_value = self.sample_fx_data
        mock_currency_pairs.return_value = []

        response = self.client.get(self.url, {'search': 'USD/EUR'})

        self.assertEqual(response.status_code, 200)
        # Search should filter results
        self.assertIn('search_query', response.context)
        self.assertEqual(response.context['search_query'], 'USD/EUR')

    @patch.object(FXRateHiveRepository, 'get_all_fx_rates')
    @patch.object(FXRateHiveRepository, 'get_unique_currency_pairs')
    def test_fx_rate_list_currency_pair_filter(self, mock_currency_pairs, mock_get_all):
        """Test currency pair filtering"""
        mock_get_all.return_value = [self.sample_fx_data[0]]  # Only USD/EUR
        mock_currency_pairs.return_value = []

        response = self.client.get(self.url, {'currency_pair': 'USD/EUR'})

        self.assertEqual(response.status_code, 200)
        mock_get_all.assert_called_once()
        # Verify filter was passed to repository
        call_kwargs = mock_get_all.call_args[1]
        self.assertEqual(call_kwargs.get('currency_pair'), 'USD/EUR')

    @patch.object(FXRateHiveRepository, 'get_all_fx_rates')
    @patch.object(FXRateHiveRepository, 'get_unique_currency_pairs')
    def test_fx_rate_list_csv_export(self, mock_currency_pairs, mock_get_all):
        """Test CSV export functionality"""
        mock_get_all.return_value = self.sample_fx_data
        mock_currency_pairs.return_value = []

        response = self.client.get(self.url, {'export': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('fx_rates', response['Content-Disposition'])

        # Check CSV content
        content = response.content.decode('utf-8')
        self.assertIn('Currency Pair', content)
        self.assertIn('USD/EUR', content)
        self.assertIn('GBP/USD', content)

    @patch.object(FXRateHiveRepository, 'get_all_fx_rates')
    @patch.object(FXRateHiveRepository, 'get_unique_currency_pairs')
    def test_fx_rate_list_pagination(self, mock_currency_pairs, mock_get_all):
        """Test pagination of results"""
        # Create 30 sample rates
        many_rates = [self.sample_fx_data[0].copy() for _ in range(30)]
        for i, rate in enumerate(many_rates):
            rate['rate_time'] = f'2025-12-26 {i:02d}:00:00'

        mock_get_all.return_value = many_rates
        mock_currency_pairs.return_value = []

        # Get first page
        response = self.client.get(self.url, {'page': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['fx_rates']), 25)  # Page size is 25

        # Get second page
        response = self.client.get(self.url, {'page': '2'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['fx_rates']), 5)  # Remaining 5


class FXRateDashboardViewTestCase(TestCase):
    """Test cases for FX Rate dashboard view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('market_data:fx_dashboard')

        self.sample_fx_data = [
            {
                'currency_pair': 'USD/EUR',
                'rate': '0.9234567890',
                'rate_date': '2025-12-26',
                'rate_time': '2025-12-26 10:00:00',
                'source': 'BLOOMBERG'
            }
        ]

    @patch.object(FXRateHiveRepository, 'get_latest_fx_rates')
    @patch.object(FXRateHiveRepository, 'get_unique_currency_pairs')
    def test_fx_dashboard_view_success(self, mock_currency_pairs, mock_latest):
        """Test dashboard view loads successfully"""
        mock_latest.return_value = self.sample_fx_data
        mock_currency_pairs.return_value = [{'currency_pair': 'USD/EUR'}]

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'market_data/fx_rate_dashboard.html')
        self.assertIn('latest_rates', response.context)
        self.assertIn('total_pairs', response.context)

    @patch.object(FXRateHiveRepository, 'get_latest_fx_rates')
    @patch.object(FXRateHiveRepository, 'get_unique_currency_pairs')
    def test_fx_dashboard_metrics(self, mock_currency_pairs, mock_latest):
        """Test dashboard metrics calculation"""
        mock_latest.return_value = self.sample_fx_data
        mock_currency_pairs.return_value = [
            {'currency_pair': 'USD/EUR'},
            {'currency_pair': 'GBP/USD'},
            {'currency_pair': 'USD/JPY'}
        ]

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_pairs'], 3)
        self.assertIn('total_rates', response.context)


class FXRateDetailViewTestCase(TestCase):
    """Test cases for FX Rate detail view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.currency_pair = 'USD/EUR'
        self.url = reverse('market_data:fx_rate_detail', args=[self.currency_pair])

        self.sample_fx_data = [
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
                'is_active': 'true'
            }
        ]

    @patch.object(FXRateHiveRepository, 'get_fx_rate_by_currency_pair')
    def test_fx_rate_detail_view_success(self, mock_get_rate):
        """Test FX rate detail view loads successfully"""
        mock_get_rate.return_value = self.sample_fx_data

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'market_data/fx_rate_detail.html')
        self.assertIn('currency_pair', response.context)
        self.assertEqual(response.context['currency_pair'], 'USD/EUR')
        self.assertIn('rates_history', response.context)

    @patch.object(FXRateHiveRepository, 'get_fx_rate_by_currency_pair')
    def test_fx_rate_detail_view_not_found(self, mock_get_rate):
        """Test detail view with non-existent currency pair"""
        mock_get_rate.return_value = []

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rates_history']), 0)

    @patch.object(FXRateHiveRepository, 'get_fx_rate_by_currency_pair')
    def test_fx_rate_detail_view_multiple_sources(self, mock_get_rate):
        """Test detail view with rates from multiple sources"""
        multiple_rates = [
            {**self.sample_fx_data[0], 'source': 'BLOOMBERG'},
            {**self.sample_fx_data[0], 'source': 'REUTERS', 'rate_time': '2025-12-26 09:00:00'},
            {**self.sample_fx_data[0], 'source': 'API', 'rate_time': '2025-12-26 08:00:00'}
        ]
        mock_get_rate.return_value = multiple_rates

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rates_history']), 3)


class FXRateWrapperTestCase(TestCase):
    """Test cases for FXRateWrapper class"""

    def test_wrapper_initialization(self):
        """Test FXRateWrapper initialization"""
        from market_data.views import FXRateWrapper

        data = {
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
            'is_active': 'true'
        }

        wrapper = FXRateWrapper(data, index=0)

        self.assertEqual(wrapper.currency_pair, 'USD/EUR')
        self.assertEqual(wrapper.base_currency, 'USD')
        self.assertEqual(wrapper.quote_currency, 'EUR')
        self.assertEqual(float(wrapper.rate), 0.9234567890)
        self.assertIsNotNone(wrapper.id)

    def test_wrapper_get_spread(self):
        """Test FXRateWrapper get_spread method"""
        from market_data.views import FXRateWrapper

        data = {
            'currency_pair': 'USD/EUR',
            'bid_rate': '0.9234000000',
            'ask_rate': '0.9235000000',
            'rate': '0.9234567890',
            'rate_date': '2025-12-26',
            'rate_time': '2025-12-26 10:00:00'
        }

        wrapper = FXRateWrapper(data, index=0)
        spread = wrapper.get_spread()

        self.assertIsNotNone(spread)
        self.assertAlmostEqual(float(spread), 0.0001, places=4)

    def test_wrapper_missing_fields(self):
        """Test FXRateWrapper handles missing fields"""
        from market_data.views import FXRateWrapper

        minimal_data = {
            'currency_pair': 'USD/EUR',
            'rate': '0.9234567890'
        }

        wrapper = FXRateWrapper(minimal_data, index=0)

        self.assertEqual(wrapper.currency_pair, 'USD/EUR')
        self.assertEqual(float(wrapper.rate), 0.9234567890)
        # Missing fields should default to empty strings or 0
        self.assertEqual(wrapper.base_currency, '')
        self.assertEqual(wrapper.bid_rate, 0)


class ViewURLTestCase(TestCase):
    """Test cases for URL routing"""

    def test_fx_rate_list_url_resolves(self):
        """Test FX rate list URL resolves correctly"""
        url = reverse('market_data:fx_rate_list')
        self.assertEqual(url, '/market-data/fx-rates/')

    def test_fx_dashboard_url_resolves(self):
        """Test FX dashboard URL resolves correctly"""
        url = reverse('market_data:fx_dashboard')
        self.assertEqual(url, '/market-data/fx-rates/dashboard/')

    def test_fx_rate_detail_url_resolves(self):
        """Test FX rate detail URL resolves correctly"""
        url = reverse('market_data:fx_rate_detail', args=['USD/EUR'])
        self.assertEqual(url, '/market-data/fx-rates/USD/EUR/')
