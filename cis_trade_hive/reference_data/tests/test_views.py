"""
Reference Data View Tests

Tests for reference data views including:
- Currency list view
- Country list view
- Calendar list view
- Counterparty list view
- Search/filter functionality
- CSV export
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, Mock, MagicMock


class CurrencyListViewTestCase(TestCase):
    """Test cases for currency list view"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()
        self.url = reverse('reference_data:currency_list')

        # Set up session
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_email'] = 'test@example.com'
        session.save()

        # Sample currency data
        self.sample_currencies = [
            {
                'code': 'USD',
                'name': 'US Dollar',
                'full_name': 'United States Dollar',
                'symbol': '$',
                'decimal_places': 2,
                'rate_precision': 4,
                'calendar': 'NYC',
                'spot_schedule': 'T+2'
            },
            {
                'code': 'EUR',
                'name': 'Euro',
                'full_name': 'European Euro',
                'symbol': '€',
                'decimal_places': 2,
                'rate_precision': 4,
                'calendar': 'EUR',
                'spot_schedule': 'T+2'
            }
        ]

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.currency_service.list_all')
    def test_currency_list_view_success(self, mock_list_all, mock_audit):
        """Test currency list view loads successfully"""
        mock_list_all.return_value = self.sample_currencies

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reference_data/currency_list.html')
        self.assertIn('currencies', response.context)

        # Verify audit log was called
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'VIEW')
        self.assertEqual(call_kwargs['entity_type'], 'REFERENCE_DATA')
        self.assertEqual(call_kwargs['entity_name'], 'Currency')

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.currency_service.list_all')
    def test_currency_search(self, mock_list_all, mock_audit):
        """Test currency search functionality"""
        mock_list_all.return_value = [self.sample_currencies[0]]

        response = self.client.get(self.url, {'search': 'USD'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['search'], 'USD')
        mock_list_all.assert_called_once_with(search='USD')

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.currency_service.list_all')
    def test_currency_csv_export(self, mock_list_all, mock_audit):
        """Test currency CSV export"""
        mock_list_all.return_value = self.sample_currencies

        response = self.client.get(self.url, {'export': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('currencies', response['Content-Disposition'])

        # Check CSV content
        content = response.content.decode('utf-8')
        self.assertIn('USD', content)
        self.assertIn('EUR', content)
        self.assertIn('Code', content)  # Header

        # Verify export was logged
        self.assertEqual(mock_audit.call_count, 2)  # VIEW + EXPORT


class CountryListViewTestCase(TestCase):
    """Test cases for country list view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('reference_data:country_list')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.sample_countries = [
            {'code': 'US', 'name': 'United States'},
            {'code': 'UK', 'name': 'United Kingdom'},
            {'code': 'SG', 'name': 'Singapore'}
        ]

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.country_service.list_all')
    def test_country_list_view_success(self, mock_list_all, mock_audit):
        """Test country list view loads successfully"""
        mock_list_all.return_value = self.sample_countries

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reference_data/country_list.html')
        self.assertIn('countries', response.context)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.country_service.list_all')
    def test_country_search(self, mock_list_all, mock_audit):
        """Test country search functionality"""
        mock_list_all.return_value = [self.sample_countries[0]]

        response = self.client.get(self.url, {'search': 'United'})

        self.assertEqual(response.status_code, 200)
        mock_list_all.assert_called_once_with(search='United')

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.country_service.list_all')
    def test_country_csv_export(self, mock_list_all, mock_audit):
        """Test country CSV export"""
        mock_list_all.return_value = self.sample_countries

        response = self.client.get(self.url, {'export': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

        content = response.content.decode('utf-8')
        self.assertIn('US', content)
        self.assertIn('Singapore', content)


class CalendarListViewTestCase(TestCase):
    """Test cases for calendar list view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('reference_data:calendar_list')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.sample_calendars = [
            {
                'calendar_label': 'NYC',
                'calendar_description': 'New York Calendar',
                'holiday_date': '2025-12-25'
            },
            {
                'calendar_label': 'LON',
                'calendar_description': 'London Calendar',
                'holiday_date': '2025-12-25'
            }
        ]

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.calendar_service.get_distinct_calendars')
    @patch('reference_data.services.reference_data_service.calendar_service.list_all')
    def test_calendar_list_view_success(self, mock_list_all, mock_distinct, mock_audit):
        """Test calendar list view loads successfully"""
        mock_list_all.return_value = self.sample_calendars
        mock_distinct.return_value = [{'calendar_label': 'NYC'}, {'calendar_label': 'LON'}]

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reference_data/calendar_list.html')
        self.assertIn('calendars', response.context)
        self.assertIn('calendar_labels', response.context)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.calendar_service.get_distinct_calendars')
    @patch('reference_data.services.reference_data_service.calendar_service.list_all')
    def test_calendar_filter_by_label(self, mock_list_all, mock_distinct, mock_audit):
        """Test filtering by calendar label"""
        mock_list_all.return_value = [self.sample_calendars[0]]
        mock_distinct.return_value = []

        response = self.client.get(self.url, {'calendar': 'NYC'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_calendar'], 'NYC')

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.calendar_service.get_distinct_calendars')
    @patch('reference_data.services.reference_data_service.calendar_service.list_all')
    def test_calendar_csv_export(self, mock_list_all, mock_distinct, mock_audit):
        """Test calendar CSV export"""
        mock_list_all.return_value = self.sample_calendars
        mock_distinct.return_value = []

        response = self.client.get(self.url, {'export': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

        content = response.content.decode('utf-8')
        self.assertIn('NYC', content)
        self.assertIn('2025-12-25', content)


class CounterpartyListViewTestCase(TestCase):
    """Test cases for counterparty list view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('reference_data:counterparty_list')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.sample_counterparties = [
            {
                'code': 'CP001',
                'name': 'ABC Bank',
                'legal_name': 'ABC Banking Corporation',
                'counterparty_type': 'BANK',
                'email': 'contact@abc.com',
                'phone': '+1234567890',
                'city': 'New York',
                'country': 'US',
                'status': 'ACTIVE',
                'risk_category': 'LOW'
            },
            {
                'code': 'CP002',
                'name': 'XYZ Corp',
                'legal_name': 'XYZ Corporation',
                'counterparty_type': 'CORPORATE',
                'email': 'contact@xyz.com',
                'phone': '+0987654321',
                'city': 'London',
                'country': 'UK',
                'status': 'ACTIVE',
                'risk_category': 'MEDIUM'
            }
        ]

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.counterparty_service.list_all')
    def test_counterparty_list_view_success(self, mock_list_all, mock_audit):
        """Test counterparty list view loads successfully"""
        mock_list_all.return_value = self.sample_counterparties

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reference_data/counterparty_list.html')
        self.assertIn('counterparties', response.context)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.counterparty_service.list_all')
    def test_counterparty_search(self, mock_list_all, mock_audit):
        """Test counterparty search functionality"""
        mock_list_all.return_value = [self.sample_counterparties[0]]

        response = self.client.get(self.url, {'search': 'ABC'})

        self.assertEqual(response.status_code, 200)
        mock_list_all.assert_called_once_with(search='ABC', counterparty_type=None)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.counterparty_service.list_all')
    def test_counterparty_type_filter(self, mock_list_all, mock_audit):
        """Test filtering by counterparty type"""
        mock_list_all.return_value = [self.sample_counterparties[0]]

        response = self.client.get(self.url, {'type': 'BANK'})

        self.assertEqual(response.status_code, 200)
        mock_list_all.assert_called_once_with(search=None, counterparty_type='BANK')

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.counterparty_service.list_all')
    def test_counterparty_csv_export(self, mock_list_all, mock_audit):
        """Test counterparty CSV export"""
        mock_list_all.return_value = self.sample_counterparties

        response = self.client.get(self.url, {'export': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

        content = response.content.decode('utf-8')
        self.assertIn('ABC Bank', content)
        self.assertIn('XYZ Corp', content)
        self.assertIn('BANK', content)


class ReferenceDataURLTestCase(TestCase):
    """Test cases for URL routing"""

    def test_currency_list_url_resolves(self):
        """Test currency list URL resolves correctly"""
        url = reverse('reference_data:currency_list')
        self.assertEqual(url, '/reference-data/currency/')

    def test_country_list_url_resolves(self):
        """Test country list URL resolves correctly"""
        url = reverse('reference_data:country_list')
        self.assertEqual(url, '/reference-data/country/')

    def test_calendar_list_url_resolves(self):
        """Test calendar list URL resolves correctly"""
        url = reverse('reference_data:calendar_list')
        self.assertEqual(url, '/reference-data/calendar/')

    def test_counterparty_list_url_resolves(self):
        """Test counterparty list URL resolves correctly"""
        url = reverse('reference_data:counterparty_list')
        self.assertEqual(url, '/reference-data/counterparty/')


class ReferenceDataErrorHandlingTestCase(TestCase):
    """Test cases for error handling"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.currency_service.list_all')
    def test_currency_list_handles_exception(self, mock_list_all, mock_audit):
        """Test currency list handles exceptions gracefully"""
        mock_list_all.side_effect = Exception('Database error')

        url = reverse('reference_data:currency_list')
        response = self.client.get(url)

        # Should still return 200 with empty list
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['currencies']), 0)
