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
        # Note: VIEW audit logging is now commented out, only EXPORT logs

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
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('currencies', response['Content-Disposition'])

        # Check CSV content
        content = response.content.decode('utf-8')
        self.assertIn('USD', content)
        self.assertIn('EUR', content)
        self.assertIn('Code', content)  # Header

        # Verify export was logged (only EXPORT, VIEW is commented out)
        self.assertEqual(mock_audit.call_count, 1)
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'EXPORT')

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.currency_service.list_all')
    def test_currency_list_empty_search(self, mock_list_all, mock_audit):
        """Test currency list with empty search returns all"""
        mock_list_all.return_value = self.sample_currencies

        response = self.client.get(self.url, {'search': ''})

        self.assertEqual(response.status_code, 200)
        mock_list_all.assert_called_once_with(search=None)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.currency_service.list_all')
    def test_currency_list_pagination(self, mock_list_all, mock_audit):
        """Test currency list pagination"""
        # Create 30 currencies to test pagination
        currencies = [{'code': f'C{i:02d}', 'name': f'Currency {i}'} for i in range(30)]
        mock_list_all.return_value = currencies

        response = self.client.get(self.url, {'page': 2})

        self.assertEqual(response.status_code, 200)
        # Page 2 should have remaining records


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
        self.assertIn('text/csv', response['Content-Type'])

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
        self.assertIn('text/csv', response['Content-Type'])

        content = response.content.decode('utf-8')
        self.assertIn('NYC', content)
        self.assertIn('2025-12-25', content)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.calendar_service.get_distinct_calendars')
    @patch('reference_data.services.reference_data_service.calendar_service.list_all')
    def test_calendar_date_filter(self, mock_list_all, mock_distinct, mock_audit):
        """Test filtering by date range"""
        mock_list_all.return_value = self.sample_calendars
        mock_distinct.return_value = []

        response = self.client.get(self.url, {
            'start_date': '2025-01-01',
            'end_date': '2025-12-31'
        })

        self.assertEqual(response.status_code, 200)


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
                'counterparty_short_name': 'ABC',
                'counterparty_full_name': 'ABC Bank',
                'm_label': 'ABC001',
                'city': 'New York',
                'country': 'US',
                'is_bank': True,
                'is_broker': False,
                'is_custodian': False,
                'is_issuer': False,
                'is_active': True
            },
            {
                'counterparty_short_name': 'XYZ',
                'counterparty_full_name': 'XYZ Corp',
                'm_label': 'XYZ001',
                'city': 'London',
                'country': 'UK',
                'is_bank': False,
                'is_broker': False,
                'is_custodian': False,
                'is_issuer': False,
                'is_active': True
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
        # Updated to match actual view signature
        mock_list_all.assert_called_once_with(search='ABC', country=None, is_active=True)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.counterparty_service.list_all')
    def test_counterparty_country_filter(self, mock_list_all, mock_audit):
        """Test filtering by country"""
        mock_list_all.return_value = [self.sample_counterparties[0]]

        response = self.client.get(self.url, {'country': 'US'})

        self.assertEqual(response.status_code, 200)
        mock_list_all.assert_called_once_with(search=None, country='US', is_active=True)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.counterparty_service.list_all')
    def test_counterparty_status_filter_inactive(self, mock_list_all, mock_audit):
        """Test filtering by inactive status"""
        mock_list_all.return_value = []

        response = self.client.get(self.url, {'status': 'inactive'})

        self.assertEqual(response.status_code, 200)
        mock_list_all.assert_called_once_with(search=None, country=None, is_active=False)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.counterparty_service.list_all')
    def test_counterparty_status_filter_all(self, mock_list_all, mock_audit):
        """Test filtering by all status"""
        mock_list_all.return_value = self.sample_counterparties

        response = self.client.get(self.url, {'status': 'all'})

        self.assertEqual(response.status_code, 200)
        mock_list_all.assert_called_once_with(search=None, country=None, is_active=None)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.counterparty_service.list_all')
    def test_counterparty_csv_export(self, mock_list_all, mock_audit):
        """Test counterparty CSV export"""
        mock_list_all.return_value = self.sample_counterparties

        response = self.client.get(self.url, {'export': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

        content = response.content.decode('utf-8')
        self.assertIn('ABC', content)
        self.assertIn('XYZ', content)

    @patch('reference_data.views.counterparty_cif_service.get_counterparties_with_multiple_cifs')
    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.counterparty_service.list_all')
    def test_counterparty_multiple_cif_filter(self, mock_list_all, mock_audit, mock_multi_cif):
        """Test filtering counterparties with multiple CIFs"""
        mock_list_all.return_value = self.sample_counterparties
        mock_multi_cif.return_value = ['ABC']

        response = self.client.get(self.url, {'cif_filter': 'multiple'})

        self.assertEqual(response.status_code, 200)
        mock_multi_cif.assert_called_once_with(is_active=True)


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

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.country_service.list_all')
    def test_country_list_handles_exception(self, mock_list_all, mock_audit):
        """Test country list handles exceptions gracefully"""
        mock_list_all.side_effect = Exception('Database error')

        url = reverse('reference_data:country_list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['countries']), 0)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.services.reference_data_service.calendar_service.get_distinct_calendars')
    @patch('reference_data.services.reference_data_service.calendar_service.list_all')
    def test_calendar_list_handles_exception(self, mock_list_all, mock_distinct, mock_audit):
        """Test calendar list handles exceptions gracefully"""
        mock_list_all.side_effect = Exception('Database error')
        mock_distinct.return_value = []

        url = reverse('reference_data:calendar_list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['calendars']), 0)


class CounterpartyDetailViewTestCase(TestCase):
    """Test cases for counterparty detail view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_email'] = 'test@example.com'
        session.save()

        self.sample_counterparty = {
            'counterparty_short_name': 'ABC',
            'counterparty_full_name': 'ABC Bank',
            'm_label': 'ABC001',
            'city': 'New York',
            'country': 'US',
            'is_bank': True,
            'is_active': True,
            'src_system': 'cis'
        }

        self.sample_cifs = [
            {'m_label': 'CIF001', 'country': 'US', 'description': 'Main'},
            {'m_label': 'CIF002', 'country': 'UK', 'description': 'Secondary'}
        ]

    @patch('reference_data.views.counterparty_cif_service.list_cifs_for_counterparty')
    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_detail_success(self, mock_get, mock_cifs):
        """Test counterparty detail view loads successfully"""
        mock_get.return_value = self.sample_counterparty
        mock_cifs.return_value = self.sample_cifs

        url = reverse('reference_data:counterparty_detail', kwargs={'short_name': 'ABC'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reference_data/counterparty_details.html')
        self.assertEqual(response.context['counterparty']['counterparty_short_name'], 'ABC')
        self.assertEqual(response.context['cif_count'], 2)

    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_detail_not_found(self, mock_get):
        """Test counterparty detail redirects when not found"""
        mock_get.return_value = None

        url = reverse('reference_data:counterparty_detail', kwargs={'short_name': 'NOTEXIST'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)  # Redirect

    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_detail_exception(self, mock_get):
        """Test counterparty detail handles exception"""
        mock_get.side_effect = Exception('DB Error')

        url = reverse('reference_data:counterparty_detail', kwargs={'short_name': 'ABC'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)  # Redirect on error


class CounterpartyCreateViewTestCase(TestCase):
    """Test cases for counterparty create view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('reference_data:counterparty_create')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_email'] = 'test@example.com'
        session.save()

    @patch('reference_data.views.country_service.list_all')
    def test_counterparty_create_get(self, mock_countries):
        """Test counterparty create form displays"""
        mock_countries.return_value = [{'code': 'US', 'name': 'United States'}]

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reference_data/counterparty_form.html')

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_service.create_counterparty')
    def test_counterparty_create_success(self, mock_create, mock_audit):
        """Test successful counterparty creation"""
        mock_create.return_value = (True, None)

        response = self.client.post(self.url, {
            'counterparty_short_name': 'NEW',
            'counterparty_full_name': 'New Bank',
            'city': 'NYC',
            'country': 'US'
        })

        self.assertEqual(response.status_code, 302)  # Redirect on success
        mock_create.assert_called_once()
        mock_audit.assert_called_once()

    @patch('reference_data.views.counterparty_service.create_counterparty')
    def test_counterparty_create_validation_failure(self, mock_create):
        """Test counterparty creation validation failure"""
        mock_create.return_value = (False, 'Short name already exists')

        response = self.client.post(self.url, {
            'counterparty_short_name': 'EXISTING',
            'counterparty_full_name': 'Existing Bank'
        })

        self.assertEqual(response.status_code, 200)  # Stays on form

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_cif_service.create_cif')
    @patch('reference_data.views.counterparty_service.create_counterparty')
    def test_counterparty_create_with_cifs(self, mock_create, mock_create_cif, mock_audit):
        """Test counterparty creation with CIFs"""
        mock_create.return_value = (True, None)
        mock_create_cif.return_value = (True, None)

        response = self.client.post(self.url, {
            'counterparty_short_name': 'NEW',
            'counterparty_full_name': 'New Bank',
            'cif_country[]': ['US', 'UK'],
            'cif_isin[]': ['', ''],
            'cif_description[]': ['Main', 'Secondary']
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(mock_create_cif.call_count, 2)


class CounterpartyEditViewTestCase(TestCase):
    """Test cases for counterparty edit view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_email'] = 'test@example.com'
        session.save()

        self.sample_counterparty = {
            'counterparty_short_name': 'ABC',
            'counterparty_full_name': 'ABC Bank',
            'city': 'New York',
            'country': 'US',
            'is_bank': True,
            'is_active': True,
            'src_system': 'cis'
        }

    @patch('reference_data.views.counterparty_cif_service.list_cifs_for_counterparty')
    @patch('reference_data.views.country_service.list_all')
    @patch('reference_data.views.counterparty_service.can_edit_counterparty')
    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_edit_get(self, mock_get, mock_can_edit, mock_countries, mock_cifs):
        """Test counterparty edit form displays"""
        mock_get.return_value = self.sample_counterparty
        mock_can_edit.return_value = True
        mock_countries.return_value = [{'code': 'US', 'name': 'United States'}]
        mock_cifs.return_value = []

        url = reverse('reference_data:counterparty_edit', kwargs={'short_name': 'ABC'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reference_data/counterparty_form.html')
        self.assertTrue(response.context['is_edit'])

    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_edit_not_found(self, mock_get):
        """Test counterparty edit redirects when not found"""
        mock_get.return_value = None

        url = reverse('reference_data:counterparty_edit', kwargs={'short_name': 'NOTEXIST'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    @patch('reference_data.views.counterparty_service.can_edit_counterparty')
    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_edit_not_editable(self, mock_get, mock_can_edit):
        """Test counterparty edit redirects when not editable"""
        mock_get.return_value = {**self.sample_counterparty, 'src_system': 'gmp'}
        mock_can_edit.return_value = False

        url = reverse('reference_data:counterparty_edit', kwargs={'short_name': 'ABC'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_service.update_counterparty')
    @patch('reference_data.views.counterparty_service.can_edit_counterparty')
    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_edit_success(self, mock_get, mock_can_edit, mock_update, mock_audit):
        """Test successful counterparty update"""
        mock_get.return_value = self.sample_counterparty
        mock_can_edit.return_value = True
        mock_update.return_value = (True, None)

        url = reverse('reference_data:counterparty_edit', kwargs={'short_name': 'ABC'})
        response = self.client.post(url, {
            'counterparty_full_name': 'ABC Bank Updated',
            'city': 'Boston',
            'country': 'US'
        })

        self.assertEqual(response.status_code, 302)
        mock_update.assert_called_once()

    @patch('reference_data.views.counterparty_service.update_counterparty')
    @patch('reference_data.views.counterparty_service.can_edit_counterparty')
    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_edit_failure(self, mock_get, mock_can_edit, mock_update):
        """Test counterparty update failure"""
        mock_get.return_value = self.sample_counterparty
        mock_can_edit.return_value = True
        mock_update.return_value = (False, 'Update failed')

        url = reverse('reference_data:counterparty_edit', kwargs={'short_name': 'ABC'})
        response = self.client.post(url, {
            'counterparty_full_name': 'ABC Bank Updated'
        })

        self.assertEqual(response.status_code, 200)  # Stays on form


class CounterpartyDeleteRestoreViewTestCase(TestCase):
    """Test cases for counterparty delete and restore views"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_email'] = 'test@example.com'
        session.save()

    def test_counterparty_delete_get_redirects(self):
        """Test GET to delete redirects"""
        url = reverse('reference_data:counterparty_delete', kwargs={'short_name': 'ABC'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_service.delete_counterparty')
    def test_counterparty_delete_success(self, mock_delete, mock_audit):
        """Test successful counterparty deletion"""
        mock_delete.return_value = (True, None)

        url = reverse('reference_data:counterparty_delete', kwargs={'short_name': 'ABC'})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        mock_delete.assert_called_once()
        mock_audit.assert_called_once()

    @patch('reference_data.views.counterparty_service.delete_counterparty')
    def test_counterparty_delete_failure(self, mock_delete):
        """Test counterparty deletion failure"""
        mock_delete.return_value = (False, 'Already deleted')

        url = reverse('reference_data:counterparty_delete', kwargs={'short_name': 'ABC'})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)  # Still redirects

    @patch('reference_data.views.counterparty_service.delete_counterparty')
    def test_counterparty_delete_exception(self, mock_delete):
        """Test counterparty deletion exception handling"""
        mock_delete.side_effect = Exception('DB Error')

        url = reverse('reference_data:counterparty_delete', kwargs={'short_name': 'ABC'})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

    def test_counterparty_restore_get_redirects(self):
        """Test GET to restore redirects"""
        url = reverse('reference_data:counterparty_restore', kwargs={'short_name': 'ABC'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_service.restore_counterparty')
    def test_counterparty_restore_success(self, mock_restore, mock_audit):
        """Test successful counterparty restore"""
        mock_restore.return_value = (True, None)

        url = reverse('reference_data:counterparty_restore', kwargs={'short_name': 'ABC'})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        mock_restore.assert_called_once()
        mock_audit.assert_called_once()

    @patch('reference_data.views.counterparty_service.restore_counterparty')
    def test_counterparty_restore_failure(self, mock_restore):
        """Test counterparty restore failure"""
        mock_restore.return_value = (False, 'Not deleted')

        url = reverse('reference_data:counterparty_restore', kwargs={'short_name': 'ABC'})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

    @patch('reference_data.views.counterparty_service.restore_counterparty')
    def test_counterparty_restore_exception(self, mock_restore):
        """Test counterparty restore exception handling"""
        mock_restore.side_effect = Exception('DB Error')

        url = reverse('reference_data:counterparty_restore', kwargs={'short_name': 'ABC'})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)


class CounterpartyCIFAjaxViewsTestCase(TestCase):
    """Test cases for CIF AJAX API endpoints"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_email'] = 'test@example.com'
        session.save()

        self.sample_cifs = [
            {'m_label': 'CIF001', 'country': 'US', 'description': 'Main'},
            {'m_label': 'CIF002', 'country': 'UK', 'description': 'Secondary'}
        ]

    @patch('reference_data.views.counterparty_cif_service.list_cifs_for_counterparty')
    def test_cif_list_success(self, mock_list):
        """Test CIF list AJAX endpoint"""
        mock_list.return_value = self.sample_cifs

        url = reverse('reference_data:counterparty_cif_list', kwargs={'short_name': 'ABC'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 2)

    @patch('reference_data.views.counterparty_cif_service.list_cifs_for_counterparty')
    def test_cif_list_exception(self, mock_list):
        """Test CIF list AJAX endpoint exception handling"""
        mock_list.side_effect = Exception('DB Error')

        url = reverse('reference_data:counterparty_cif_list', kwargs={'short_name': 'ABC'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertFalse(data['success'])

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_cif_service.create_cif')
    def test_cif_create_success(self, mock_create, mock_audit):
        """Test CIF create AJAX endpoint"""
        mock_create.return_value = (True, None)

        url = reverse('reference_data:counterparty_cif_create', kwargs={'short_name': 'ABC'})
        response = self.client.post(
            url,
            data='{"m_label": "CIF003", "country": "SG", "description": "New"}',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    @patch('reference_data.views.counterparty_cif_service.create_cif')
    def test_cif_create_failure(self, mock_create):
        """Test CIF create AJAX endpoint failure"""
        mock_create.return_value = (False, 'Validation error')

        url = reverse('reference_data:counterparty_cif_create', kwargs={'short_name': 'ABC'})
        response = self.client.post(
            url,
            data='{"m_label": "", "country": "", "description": ""}',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])

    def test_cif_create_invalid_json(self):
        """Test CIF create AJAX endpoint with invalid JSON"""
        url = reverse('reference_data:counterparty_cif_create', kwargs={'short_name': 'ABC'})
        response = self.client.post(
            url,
            data='invalid json',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('Invalid JSON', data['error'])

    @patch('reference_data.views.counterparty_cif_service.create_cif')
    def test_cif_create_exception(self, mock_create):
        """Test CIF create AJAX endpoint exception handling"""
        mock_create.side_effect = Exception('DB Error')

        url = reverse('reference_data:counterparty_cif_create', kwargs={'short_name': 'ABC'})
        response = self.client.post(
            url,
            data='{"m_label": "CIF003", "country": "SG"}',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 500)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_cif_service.update_cif')
    @patch('reference_data.views.counterparty_cif_service.get_cif')
    def test_cif_update_success(self, mock_get, mock_update, mock_audit):
        """Test CIF update AJAX endpoint"""
        mock_get.return_value = {'m_label': 'CIF001', 'country': 'US', 'description': 'Old'}
        mock_update.return_value = (True, None)

        url = reverse('reference_data:counterparty_cif_update', kwargs={'short_name': 'ABC', 'm_label': 'CIF001'})
        response = self.client.post(
            url,
            data='{"country": "UK", "description": "Updated"}',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    @patch('reference_data.views.counterparty_cif_service.update_cif')
    @patch('reference_data.views.counterparty_cif_service.get_cif')
    def test_cif_update_failure(self, mock_get, mock_update):
        """Test CIF update AJAX endpoint failure"""
        mock_get.return_value = None
        mock_update.return_value = (False, 'Not found')

        url = reverse('reference_data:counterparty_cif_update', kwargs={'short_name': 'ABC', 'm_label': 'NOTEXIST'})
        response = self.client.post(
            url,
            data='{"country": "UK"}',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)

    @patch('reference_data.views.counterparty_cif_service.get_cif')
    def test_cif_update_invalid_json(self, mock_get):
        """Test CIF update AJAX endpoint with invalid JSON"""
        mock_get.return_value = {'m_label': 'CIF001', 'country': 'US'}

        url = reverse('reference_data:counterparty_cif_update', kwargs={'short_name': 'ABC', 'm_label': 'CIF001'})
        response = self.client.post(
            url,
            data='invalid json',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)

    @patch('reference_data.views.counterparty_cif_service.get_cif')
    def test_cif_update_exception(self, mock_get):
        """Test CIF update AJAX endpoint exception handling"""
        mock_get.side_effect = Exception('DB Error')

        url = reverse('reference_data:counterparty_cif_update', kwargs={'short_name': 'ABC', 'm_label': 'CIF001'})
        response = self.client.post(
            url,
            data='{"country": "UK"}',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 500)

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_cif_service.delete_cif')
    def test_cif_delete_success(self, mock_delete, mock_audit):
        """Test CIF delete AJAX endpoint"""
        mock_delete.return_value = (True, None)

        url = reverse('reference_data:counterparty_cif_delete', kwargs={'short_name': 'ABC', 'm_label': 'CIF001'})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    @patch('reference_data.views.counterparty_cif_service.delete_cif')
    def test_cif_delete_failure(self, mock_delete):
        """Test CIF delete AJAX endpoint failure"""
        mock_delete.return_value = (False, 'Already deleted')

        url = reverse('reference_data:counterparty_cif_delete', kwargs={'short_name': 'ABC', 'm_label': 'CIF001'})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)

    @patch('reference_data.views.counterparty_cif_service.delete_cif')
    def test_cif_delete_exception(self, mock_delete):
        """Test CIF delete AJAX endpoint exception handling"""
        mock_delete.side_effect = Exception('DB Error')

        url = reverse('reference_data:counterparty_cif_delete', kwargs={'short_name': 'ABC', 'm_label': 'CIF001'})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 500)


class GetClientIPTestCase(TestCase):
    """Test cases for get_client_ip helper function"""

    def test_get_client_ip_from_forwarded_for(self):
        """Test get_client_ip with X-Forwarded-For header"""
        from reference_data.views import get_client_ip

        class MockRequest:
            META = {'HTTP_X_FORWARDED_FOR': '192.168.1.1, 10.0.0.1'}

        ip = get_client_ip(MockRequest())
        self.assertEqual(ip, '192.168.1.1')

    def test_get_client_ip_from_remote_addr(self):
        """Test get_client_ip with REMOTE_ADDR"""
        from reference_data.views import get_client_ip

        class MockRequest:
            META = {'REMOTE_ADDR': '127.0.0.1'}

        ip = get_client_ip(MockRequest())
        self.assertEqual(ip, '127.0.0.1')


class CounterpartyListErrorHandlingTestCase(TestCase):
    """Additional error handling tests for counterparty list"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('reference_data:counterparty_list')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('reference_data.views.counterparty_service.list_all')
    def test_counterparty_list_exception(self, mock_list):
        """Test counterparty list handles exception"""
        mock_list.side_effect = Exception('Database error')

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['counterparties']), 0)


class CounterpartyCreateExceptionTestCase(TestCase):
    """Test exception handling in counterparty create view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('reference_data:counterparty_create')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_email'] = 'test@example.com'
        session.save()

    @patch('reference_data.views.counterparty_service.create_counterparty')
    def test_counterparty_create_exception(self, mock_create):
        """Test counterparty create handles exception"""
        mock_create.side_effect = Exception('DB Error')

        response = self.client.post(self.url, {
            'counterparty_short_name': 'NEW',
            'counterparty_full_name': 'New Bank'
        })

        self.assertEqual(response.status_code, 200)  # Stays on form

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_cif_service.create_cif')
    @patch('reference_data.views.counterparty_service.create_counterparty')
    def test_counterparty_create_cif_exception(self, mock_create, mock_create_cif, mock_audit):
        """Test counterparty create with CIF exception"""
        mock_create.return_value = (True, None)
        mock_create_cif.side_effect = Exception('CIF Error')

        response = self.client.post(self.url, {
            'counterparty_short_name': 'NEW',
            'counterparty_full_name': 'New Bank',
            'cif_country[]': ['US'],
            'cif_isin[]': [''],
            'cif_description[]': ['Main']
        })

        self.assertEqual(response.status_code, 302)  # Still redirects on success


class CounterpartyEditExceptionTestCase(TestCase):
    """Test exception handling in counterparty edit view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_email'] = 'test@example.com'
        session.save()

        self.sample_counterparty = {
            'counterparty_short_name': 'ABC',
            'counterparty_full_name': 'ABC Bank',
            'city': 'New York',
            'country': 'US',
            'is_bank': True,
            'is_active': True,
            'src_system': 'cis'
        }

    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_edit_exception(self, mock_get):
        """Test counterparty edit handles exception"""
        mock_get.side_effect = Exception('DB Error')

        url = reverse('reference_data:counterparty_edit', kwargs={'short_name': 'ABC'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)  # Redirect on error

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_cif_service.create_cif')
    @patch('reference_data.views.counterparty_service.update_counterparty')
    @patch('reference_data.views.counterparty_service.can_edit_counterparty')
    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_edit_with_cifs(self, mock_get, mock_can_edit, mock_update, mock_create_cif, mock_audit):
        """Test counterparty edit with CIF creation"""
        mock_get.return_value = self.sample_counterparty
        mock_can_edit.return_value = True
        mock_update.return_value = (True, None)
        mock_create_cif.return_value = (True, None)

        url = reverse('reference_data:counterparty_edit', kwargs={'short_name': 'ABC'})
        response = self.client.post(url, {
            'counterparty_full_name': 'ABC Bank Updated',
            'city': 'Boston',
            'country': 'US',
            'cif_country[]': ['UK'],
            'cif_isin[]': [''],
            'cif_description[]': ['New CIF']
        })

        self.assertEqual(response.status_code, 302)
        mock_create_cif.assert_called_once()

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_cif_service.create_cif')
    @patch('reference_data.views.counterparty_service.update_counterparty')
    @patch('reference_data.views.counterparty_service.can_edit_counterparty')
    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_edit_cif_exception(self, mock_get, mock_can_edit, mock_update, mock_create_cif, mock_audit):
        """Test counterparty edit with CIF exception"""
        mock_get.return_value = self.sample_counterparty
        mock_can_edit.return_value = True
        mock_update.return_value = (True, None)
        mock_create_cif.side_effect = Exception('CIF Error')

        url = reverse('reference_data:counterparty_edit', kwargs={'short_name': 'ABC'})
        response = self.client.post(url, {
            'counterparty_full_name': 'ABC Bank Updated',
            'cif_country[]': ['UK'],
            'cif_isin[]': [''],
            'cif_description[]': ['New CIF']
        })

        self.assertEqual(response.status_code, 302)  # Still redirects

    @patch('reference_data.views.audit_log_kudu_repository.log_action')
    @patch('reference_data.views.counterparty_service.update_counterparty')
    @patch('reference_data.views.counterparty_service.can_edit_counterparty')
    @patch('reference_data.views.counterparty_service.get_by_short_name')
    def test_counterparty_edit_with_next_url(self, mock_get, mock_can_edit, mock_update, mock_audit):
        """Test counterparty edit with next URL redirect"""
        mock_get.return_value = self.sample_counterparty
        mock_can_edit.return_value = True
        mock_update.return_value = (True, None)

        url = reverse('reference_data:counterparty_edit', kwargs={'short_name': 'ABC'})
        response = self.client.post(url + '?next=/reference-data/counterparty/', {
            'counterparty_full_name': 'ABC Bank Updated'
        })

        self.assertEqual(response.status_code, 302)


