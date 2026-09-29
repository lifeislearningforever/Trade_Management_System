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


class FXRateListViewTestCase(TestCase):
    """Test cases for FX Rate list view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('market_data:fx_rate_list')

        self.sample_fx_data = [
            {
                'currency_pair': 'USD-EUR',
                'base_currency': 'USD',
                'quote_currency': 'EUR',
                'rate': '0.9234567890',
                'bid_rate': '0.9234000000',
                'ask_rate': '0.9235000000',
                'mid_rate': '0.9234500000',
                'trade_date': '20251226',
                'rate_time': '2025-12-26 10:00:00',
                'source': 'BLOOMBERG',
                'is_active': 'true'
            },
            {
                'currency_pair': 'GBP-USD',
                'base_currency': 'GBP',
                'quote_currency': 'USD',
                'rate': '1.2567890123',
                'bid_rate': '1.2567000000',
                'ask_rate': '1.2568500000',
                'mid_rate': '1.2567750000',
                'trade_date': '20251226',
                'rate_time': '2025-12-26 10:00:00',
                'source': 'REUTERS',
                'is_active': 'true'
            }
        ]

    @patch('market_data.views.fx_rate_service')
    def test_fx_rate_list_view_success(self, mock_service):
        """Test FX rate list view loads successfully"""
        mock_service.get_fx_rates.return_value = self.sample_fx_data
        mock_service.get_currency_pairs.return_value = ['USD/EUR', 'GBP/USD']
        mock_service.get_base_currencies.return_value = ['USD', 'GBP']
        mock_service.get_sources.return_value = ['BLOOMBERG', 'REUTERS']

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'market_data/fx_rate_list.html')
        self.assertIn('page_obj', response.context)
        self.assertEqual(len(response.context['page_obj']), 2)

    @patch('market_data.views.fx_rate_service')
    def test_fx_rate_list_view_empty(self, mock_service):
        """Test FX rate list view with no data"""
        mock_service.get_fx_rates.return_value = []
        mock_service.get_currency_pairs.return_value = []
        mock_service.get_base_currencies.return_value = []
        mock_service.get_sources.return_value = []

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['page_obj']), 0)

    @patch('market_data.views.fx_rate_service')
    def test_fx_rate_list_search_filter(self, mock_service):
        """Test search filtering passes currency_pair to service"""
        mock_service.get_fx_rates.return_value = self.sample_fx_data
        mock_service.get_currency_pairs.return_value = []
        mock_service.get_base_currencies.return_value = []
        mock_service.get_sources.return_value = []

        response = self.client.get(self.url, {'currency_pair': 'USD/EUR'})

        self.assertEqual(response.status_code, 200)
        call_kwargs = mock_service.get_fx_rates.call_args[1]
        self.assertEqual(call_kwargs.get('currency_pair'), 'USD/EUR')

    @patch('market_data.views.fx_rate_service')
    def test_fx_rate_list_currency_pair_filter(self, mock_service):
        """Test currency pair filter is passed to service"""
        mock_service.get_fx_rates.return_value = [self.sample_fx_data[0]]
        mock_service.get_currency_pairs.return_value = []
        mock_service.get_base_currencies.return_value = []
        mock_service.get_sources.return_value = []

        response = self.client.get(self.url, {'currency_pair': 'USD/EUR'})

        self.assertEqual(response.status_code, 200)
        mock_service.get_fx_rates.assert_called_once()
        call_kwargs = mock_service.get_fx_rates.call_args[1]
        self.assertEqual(call_kwargs.get('currency_pair'), 'USD/EUR')

    @patch('market_data.views.audit_log_kudu_repository')
    @patch('market_data.views.fx_rate_service')
    def test_fx_rate_list_csv_export(self, mock_service, mock_audit):
        """Test CSV export functionality"""
        mock_service.get_fx_rates.return_value = self.sample_fx_data
        mock_service.get_currency_pairs.return_value = []
        mock_service.get_base_currencies.return_value = []
        mock_service.get_sources.return_value = []

        response = self.client.get(self.url, {'export': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('fx_rates', response['Content-Disposition'])

        content = response.content.decode('utf-8')
        self.assertIn('Currency Pair', content)
        self.assertIn('USD-EUR', content)
        self.assertIn('GBP-USD', content)

    @patch('market_data.views.fx_rate_service')
    def test_fx_rate_list_pagination(self, mock_service):
        """Test pagination of results"""
        many_rates = [self.sample_fx_data[0].copy() for _ in range(30)]
        for i, rate in enumerate(many_rates):
            rate['rate_time'] = f'2025-12-26 {i:02d}:00:00'

        mock_service.get_fx_rates.return_value = many_rates
        mock_service.get_currency_pairs.return_value = []
        mock_service.get_base_currencies.return_value = []
        mock_service.get_sources.return_value = []

        response = self.client.get(self.url, {'page': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['page_obj'].has_next())
        self.assertEqual(len(response.context['page_obj']), 25)

        response = self.client.get(self.url, {'page': '2'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['page_obj']), 5)


class FXRateDashboardViewTestCase(TestCase):
    """Test cases for FX Rate dashboard view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('market_data:fx_dashboard')

    @patch('market_data.views.equity_price_service')
    @patch('market_data.views.fx_rate_service')
    def test_fx_dashboard_view_success(self, mock_fx_service, mock_eq_service):
        """Test dashboard view loads successfully"""
        mock_fx_service.get_statistics.return_value = {
            'total_records': 100, 'unique_pairs': 10, 'unique_sources': 3,
            'latest_date': '20251226', 'earliest_date': '20250101', 'source_breakdown': []
        }
        mock_fx_service.get_latest_rates.return_value = [
            {'currency_pair': 'USD-EUR', 'rate': '0.923', 'trade_date': '20251226',
             'rate_time': '2025-12-26 10:00:00', 'source': 'BLOOMBERG'}
        ]
        mock_fx_service.get_base_currencies.return_value = ['USD', 'GBP']
        mock_eq_service.get_statistics.return_value = {}
        mock_eq_service.get_equity_prices.return_value = []

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'market_data/market_data_dashboard.html')

    @patch('market_data.views.equity_price_service')
    @patch('market_data.views.fx_rate_service')
    def test_fx_dashboard_metrics(self, mock_fx_service, mock_eq_service):
        """Test dashboard metrics are passed to template"""
        mock_fx_service.get_statistics.return_value = {
            'total_records': 500, 'unique_pairs': 15, 'unique_sources': 4,
            'latest_date': '20251226', 'earliest_date': '20250101', 'source_breakdown': []
        }
        mock_fx_service.get_latest_rates.return_value = []
        mock_fx_service.get_base_currencies.return_value = []
        mock_eq_service.get_statistics.return_value = {}
        mock_eq_service.get_equity_prices.return_value = []

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('fx_stats', response.context)


class FXRateDetailViewTestCase(TestCase):
    """Test cases for FX Rate detail view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.currency_pair = 'USD-EUR'
        self.url = reverse('market_data:fx_rate_detail', args=[self.currency_pair])

        self.sample_history = [
            {
                'currency_pair': 'USD-EUR',
                'base_currency': 'USD',
                'quote_currency': 'EUR',
                'rate': '0.9234567890',
                'bid_rate': '0.9234000000',
                'ask_rate': '0.9235000000',
                'mid_rate': '0.9234500000',
                'trade_date': '20251226',
                'rate_time': '2025-12-26 10:00:00',
                'source': 'BLOOMBERG',
            }
        ]

    @patch('market_data.views.fx_rate_service')
    def test_fx_rate_detail_view_success(self, mock_service):
        """Test FX rate detail view loads successfully"""
        mock_service.get_rate_history.return_value = self.sample_history

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'market_data/fx_rate_detail.html')
        self.assertIn('currency_pair', response.context)
        self.assertEqual(response.context['currency_pair'], 'USD-EUR')

    @patch('market_data.views.fx_rate_service')
    def test_fx_rate_detail_view_not_found(self, mock_service):
        """Test detail view with non-existent currency pair"""
        mock_service.get_rate_history.return_value = []

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['history'], [])

    @patch('market_data.views.fx_rate_service')
    def test_fx_rate_detail_view_multiple_sources(self, mock_service):
        """Test detail view with multiple history entries"""
        history = [
            {**self.sample_history[0], 'source': 'BLOOMBERG'},
            {**self.sample_history[0], 'source': 'REUTERS', 'rate_time': '2025-12-26 09:00:00'},
            {**self.sample_history[0], 'source': 'API', 'rate_time': '2025-12-26 08:00:00'}
        ]
        mock_service.get_rate_history.return_value = history

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('history', response.context)


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
            'trade_date': '20251226',
            'rate_time': '2025-12-26 10:00:00',
            'source': 'BLOOMBERG',
        }

        wrapper = FXRateWrapper(data, index=0)

        self.assertEqual(wrapper.currency_pair, 'USD/EUR')
        self.assertEqual(wrapper.base_currency, 'USD')
        self.assertEqual(wrapper.quote_currency, 'EUR')
        self.assertEqual(float(wrapper.rate), float('0.9234500000'))  # rate = mid_rate
        self.assertIsNotNone(wrapper.id)

    def test_wrapper_get_spread(self):
        """Test FXRateWrapper get_spread returns spread field (pre-calculated by repo)"""
        from market_data.views import FXRateWrapper

        data = {
            'currency_pair': 'USD/EUR',
            'bid_rate': '0.9234000000',
            'ask_rate': '0.9235000000',
            'rate': '0.9234567890',
            'spread': 0.0001,  # Pre-calculated by repository
            'trade_date': '20251226',
        }

        wrapper = FXRateWrapper(data, index=0)
        spread = wrapper.get_spread()

        self.assertEqual(float(spread), 0.0001)

    def test_wrapper_missing_fields(self):
        """Test FXRateWrapper handles missing fields"""
        from market_data.views import FXRateWrapper

        minimal_data = {
            'currency_pair': 'USD/EUR',
            'rate': '0.9234567890'
        }

        wrapper = FXRateWrapper(minimal_data, index=0)

        self.assertEqual(wrapper.currency_pair, 'USD/EUR')
        self.assertEqual(float(wrapper.rate), 0.0)  # rate = mid_rate, defaults to 0
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
        url = reverse('market_data:fx_rate_detail', args=['USD_EUR'])
        self.assertIn('USD_EUR', url)
