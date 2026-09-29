"""
Reference Data Service Tests

Tests for reference data services including:
- CurrencyService
- CountryService
- CalendarService
- CounterpartyService
"""

import pytest
from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock
from datetime import date


class CurrencyServiceTestCase(TestCase):
    """Test cases for CurrencyService"""

    def setUp(self):
        """Set up test data"""
        self.sample_currencies = [
            {
                'iso_code': 'USD',
                'name': 'US Dollar',
                'full_name': 'United States Dollar',
                'symbol': '$',
                'precision': 2,
                'rate_precision': 4,
                'calendar': 'NYC',
                'spot_schedule': 'T+2'
            },
            {
                'iso_code': 'EUR',
                'name': 'Euro',
                'full_name': 'European Euro',
                'symbol': '€',
                'precision': 2,
                'rate_precision': 4,
                'calendar': 'EUR',
                'spot_schedule': 'T+2'
            }
        ]

    @patch('reference_data.services.reference_data_service.currency_repository')
    def test_list_all_returns_currencies(self, mock_repo):
        """Test list_all returns mapped currency data"""
        from reference_data.services.reference_data_service import CurrencyService

        mock_repo.list_all.return_value = [
            {'code': 'USD', 'name': 'US Dollar', 'full_name': 'United States Dollar'},
            {'code': 'EUR', 'name': 'Euro', 'full_name': 'European Euro'}
        ]

        service = CurrencyService()
        service.repository = mock_repo

        result = service.list_all()

        self.assertEqual(len(result), 2)
        mock_repo.list_all.assert_called_once_with(search=None)

    @patch('reference_data.services.reference_data_service.currency_repository')
    def test_list_all_with_search(self, mock_repo):
        """Test list_all with search parameter"""
        from reference_data.services.reference_data_service import CurrencyService

        mock_repo.list_all.return_value = [
            {'code': 'USD', 'name': 'US Dollar'}
        ]

        service = CurrencyService()
        service.repository = mock_repo

        result = service.list_all(search='USD')

        mock_repo.list_all.assert_called_once_with(search='USD')

    @patch('reference_data.services.reference_data_service.currency_repository')
    def test_get_by_code_returns_currency(self, mock_repo):
        """Test get_by_code returns specific currency"""
        from reference_data.services.reference_data_service import CurrencyService

        mock_repo.get_by_code.return_value = {
            'iso_code': 'USD',
            'name': 'US Dollar',
            'full_name': 'United States Dollar',
            'symbol': '$',
            'precision': 2,
            'rate_precision': 4,
            'calendar': 'NYC',
            'spot_schedule': 'T+2'
        }

        service = CurrencyService()
        service.repository = mock_repo

        result = service.get_by_code('USD')

        self.assertIsNotNone(result)
        self.assertEqual(result['code'], 'USD')
        mock_repo.get_by_code.assert_called_once_with('USD')

    @patch('reference_data.services.reference_data_service.currency_repository')
    def test_get_by_code_returns_none_when_not_found(self, mock_repo):
        """Test get_by_code returns None when currency not found"""
        from reference_data.services.reference_data_service import CurrencyService

        mock_repo.get_by_code.return_value = None

        service = CurrencyService()
        service.repository = mock_repo

        result = service.get_by_code('XXX')

        self.assertIsNone(result)

    @patch('reference_data.services.reference_data_service.currency_repository')
    def test_get_active_currencies(self, mock_repo):
        """Test get_active_currencies returns list"""
        from reference_data.services.reference_data_service import CurrencyService

        mock_repo.list_all.return_value = [
            {'code': 'USD', 'name': 'US Dollar'},
            {'code': 'EUR', 'name': 'Euro'}
        ]

        service = CurrencyService()
        service.repository = mock_repo

        result = service.get_active_currencies()

        self.assertEqual(len(result), 2)


class CountryServiceTestCase(TestCase):
    """Test cases for CountryService"""

    @patch('reference_data.services.reference_data_service.country_repository')
    def test_list_all_returns_countries(self, mock_repo):
        """Test list_all returns country data"""
        from reference_data.services.reference_data_service import CountryService

        mock_repo.list_all.return_value = [
            {'code': 'US', 'name': 'United States'},
            {'code': 'UK', 'name': 'United Kingdom'}
        ]

        service = CountryService()
        service.repository = mock_repo

        result = service.list_all()

        self.assertEqual(len(result), 2)
        mock_repo.list_all.assert_called_once_with(search=None)

    @patch('reference_data.services.reference_data_service.country_repository')
    def test_list_all_with_search(self, mock_repo):
        """Test list_all with search parameter"""
        from reference_data.services.reference_data_service import CountryService

        mock_repo.list_all.return_value = [
            {'code': 'US', 'name': 'United States'}
        ]

        service = CountryService()
        service.repository = mock_repo

        result = service.list_all(search='United')

        mock_repo.list_all.assert_called_once_with(search='United')

    @patch('reference_data.services.reference_data_service.country_repository')
    def test_get_by_code_returns_country(self, mock_repo):
        """Test get_by_code returns specific country"""
        from reference_data.services.reference_data_service import CountryService

        mock_repo.get_by_code.return_value = {
            'label': 'US',
            'full_name': 'United States'
        }

        service = CountryService()
        service.repository = mock_repo

        result = service.get_by_code('US')

        self.assertIsNotNone(result)
        self.assertEqual(result['code'], 'US')

    @patch('reference_data.services.reference_data_service.country_repository')
    def test_get_by_code_returns_none_when_not_found(self, mock_repo):
        """Test get_by_code returns None when country not found"""
        from reference_data.services.reference_data_service import CountryService

        mock_repo.get_by_code.return_value = None

        service = CountryService()
        service.repository = mock_repo

        result = service.get_by_code('XX')

        self.assertIsNone(result)


class CalendarServiceTestCase(TestCase):
    """Test cases for CalendarService"""

    @patch('reference_data.services.reference_data_service.calendar_repository')
    def test_list_all_returns_calendars(self, mock_repo):
        """Test list_all returns calendar data"""
        from reference_data.services.reference_data_service import CalendarService

        mock_repo.list_all.return_value = [
            {'calendar_label': 'NYC', 'calendar_description': 'New York', 'holiday_date': '2025-12-25'},
            {'calendar_label': 'LON', 'calendar_description': 'London', 'holiday_date': '2025-12-25'}
        ]

        service = CalendarService()
        service.repository = mock_repo

        result = service.list_all()

        self.assertEqual(len(result), 2)

    @patch('reference_data.services.reference_data_service.calendar_repository')
    def test_list_all_with_calendar_label_filter(self, mock_repo):
        """Test list_all with calendar label filter"""
        from reference_data.services.reference_data_service import CalendarService

        mock_repo.list_all.return_value = [
            {'calendar_label': 'NYC', 'calendar_description': 'New York', 'holiday_date': '2025-12-25'}
        ]

        service = CalendarService()
        service.repository = mock_repo

        result = service.list_all(calendar_label='NYC')

        mock_repo.list_all.assert_called_once_with(calendar_label='NYC', search=None)

    @patch('reference_data.services.reference_data_service.calendar_repository')
    def test_get_distinct_calendars(self, mock_repo):
        """Test get_distinct_calendars returns list of labels"""
        from reference_data.services.reference_data_service import CalendarService

        mock_repo.get_distinct_calendars.return_value = ['NYC', 'LON', 'TOK']

        service = CalendarService()
        service.repository = mock_repo

        result = service.get_distinct_calendars()

        self.assertEqual(len(result), 3)
        self.assertIn('NYC', result)

    @patch('reference_data.services.reference_data_service.calendar_repository')
    def test_get_holidays_for_calendar(self, mock_repo):
        """Test get_holidays_for_calendar returns holidays"""
        from reference_data.services.reference_data_service import CalendarService

        mock_repo.get_holidays_for_calendar.return_value = [
            {'calendar_label': 'NYC', 'holiday_date': '2025-12-25'},
            {'calendar_label': 'NYC', 'holiday_date': '2025-01-01'}
        ]

        service = CalendarService()
        service.repository = mock_repo

        result = service.get_holidays_for_calendar('NYC')

        self.assertEqual(len(result), 2)


class CounterpartyServiceTestCase(TestCase):
    """Test cases for CounterpartyService"""

    def setUp(self):
        """Set up test data"""
        self.sample_counterparty = {
            'counterparty_short_name': 'ABC',
            'counterparty_full_name': 'ABC Bank',
            'm_label': 'ABC001',
            'city': 'New York',
            'country': 'US',
            'is_bank': True,
            'is_active': True,
            'is_deleted': False,
            'src_system': 'cis'
        }

        self.user_info = {
            'username': 'testuser',
            'user_id': '1',
            'user_email': 'test@example.com'
        }

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_list_all_returns_counterparties(self, mock_repo):
        """Test list_all returns counterparty data"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.list_all.return_value = [self.sample_counterparty]

        service = CounterpartyService()
        service.repository = mock_repo

        result = service.list_all()

        self.assertEqual(len(result), 1)
        mock_repo.list_all.assert_called_once_with(search=None, country=None, is_active=None)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_list_all_with_filters(self, mock_repo):
        """Test list_all with search and country filters"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.list_all.return_value = [self.sample_counterparty]

        service = CounterpartyService()
        service.repository = mock_repo

        result = service.list_all(search='ABC', country='US', is_active=True)

        mock_repo.list_all.assert_called_once_with(search='ABC', country='US', is_active=True)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_get_by_short_name(self, mock_repo):
        """Test get_by_short_name returns counterparty"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = self.sample_counterparty

        service = CounterpartyService()
        service.repository = mock_repo

        result = service.get_by_short_name('ABC')

        self.assertIsNotNone(result)
        self.assertEqual(result['counterparty_short_name'], 'ABC')

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_get_distinct_countries(self, mock_repo):
        """Test get_distinct_countries returns list"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_distinct_countries.return_value = ['US', 'UK', 'SG']

        service = CounterpartyService()
        service.repository = mock_repo

        result = service.get_distinct_countries()

        self.assertEqual(len(result), 3)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_validate_counterparty_missing_short_name(self, mock_repo):
        """Test validation fails when short_name is missing"""
        from reference_data.services.reference_data_service import CounterpartyService

        service = CounterpartyService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_counterparty({})

        self.assertFalse(is_valid)
        self.assertIn('short name is required', error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_validate_counterparty_duplicate_on_create(self, mock_repo):
        """Test validation fails for duplicate on create"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = self.sample_counterparty

        service = CounterpartyService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_counterparty(
            {'counterparty_short_name': 'ABC'},
            is_update=False
        )

        self.assertFalse(is_valid)
        self.assertIn('already exists', error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_validate_counterparty_short_name_too_long(self, mock_repo):
        """Test validation fails when short_name exceeds max length"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = None

        service = CounterpartyService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_counterparty(
            {'counterparty_short_name': 'A' * 101}
        )

        self.assertFalse(is_valid)
        self.assertIn('100 characters', error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_validate_counterparty_full_name_too_long(self, mock_repo):
        """Test validation fails when full_name exceeds max length"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = None

        service = CounterpartyService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_counterparty(
            {'counterparty_short_name': 'ABC', 'counterparty_full_name': 'A' * 256}
        )

        self.assertFalse(is_valid)
        self.assertIn('255 characters', error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_validate_counterparty_success(self, mock_repo):
        """Test validation succeeds for valid data"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = None

        service = CounterpartyService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_counterparty(
            {'counterparty_short_name': 'ABC', 'counterparty_full_name': 'ABC Bank'}
        )

        self.assertTrue(is_valid)
        self.assertIsNone(error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_create_counterparty_success(self, mock_repo):
        """Test successful counterparty creation"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = None
        mock_repo.create.return_value = True

        service = CounterpartyService()
        service.repository = mock_repo

        success, error_msg = service.create_counterparty(
            {'counterparty_short_name': 'NEW', 'counterparty_full_name': 'New Bank'},
            self.user_info
        )

        self.assertTrue(success)
        self.assertIsNone(error_msg)
        mock_repo.create.assert_called_once()

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_create_counterparty_validation_failure(self, mock_repo):
        """Test counterparty creation fails on validation"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = self.sample_counterparty

        service = CounterpartyService()
        service.repository = mock_repo

        success, error_msg = service.create_counterparty(
            {'counterparty_short_name': 'ABC'},
            self.user_info
        )

        self.assertFalse(success)
        self.assertIn('already exists', error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_can_edit_counterparty_cis_source(self, mock_repo):
        """Test can_edit returns True for CIS source"""
        from reference_data.services.reference_data_service import CounterpartyService

        service = CounterpartyService()
        service.repository = mock_repo

        result = service.can_edit_counterparty({'src_system': 'cis'})

        self.assertTrue(result)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_can_edit_counterparty_gmp_source(self, mock_repo):
        """Test can_edit returns False for GMP source"""
        from reference_data.services.reference_data_service import CounterpartyService

        service = CounterpartyService()
        service.repository = mock_repo

        result = service.can_edit_counterparty({'src_system': 'gmp'})

        self.assertFalse(result)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_update_counterparty_success(self, mock_repo):
        """Test successful counterparty update"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = {**self.sample_counterparty, 'src_system': 'cis'}
        mock_repo.update.return_value = True

        service = CounterpartyService()
        service.repository = mock_repo

        success, error_msg = service.update_counterparty(
            'ABC',
            {'counterparty_full_name': 'ABC Bank Updated'},
            self.user_info
        )

        self.assertTrue(success)
        self.assertIsNone(error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_update_counterparty_not_found(self, mock_repo):
        """Test update fails when counterparty not found"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = None

        service = CounterpartyService()
        service.repository = mock_repo

        success, error_msg = service.update_counterparty(
            'NOTEXIST',
            {'counterparty_full_name': 'Test'},
            self.user_info
        )

        self.assertFalse(success)
        self.assertIn('not found', error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_update_counterparty_not_editable(self, mock_repo):
        """Test update fails for non-CIS source"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = {**self.sample_counterparty, 'src_system': 'gmp'}

        service = CounterpartyService()
        service.repository = mock_repo

        success, error_msg = service.update_counterparty(
            'ABC',
            {'counterparty_full_name': 'Test'},
            self.user_info
        )

        self.assertFalse(success)
        self.assertIn('Cannot edit', error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_delete_counterparty_success(self, mock_repo):
        """Test successful soft delete"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = {**self.sample_counterparty, 'is_deleted': False}
        mock_repo.soft_delete.return_value = True

        service = CounterpartyService()
        service.repository = mock_repo

        success, error_msg = service.delete_counterparty('ABC', self.user_info)

        self.assertTrue(success)
        self.assertIsNone(error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_delete_counterparty_not_found(self, mock_repo):
        """Test delete fails when not found"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = None

        service = CounterpartyService()
        service.repository = mock_repo

        success, error_msg = service.delete_counterparty('NOTEXIST', self.user_info)

        self.assertFalse(success)
        self.assertIn('not found', error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_delete_counterparty_already_deleted(self, mock_repo):
        """Test delete fails when already deleted"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = {**self.sample_counterparty, 'is_deleted': True}

        service = CounterpartyService()
        service.repository = mock_repo

        success, error_msg = service.delete_counterparty('ABC', self.user_info)

        self.assertFalse(success)
        self.assertIn('already deleted', error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_restore_counterparty_success(self, mock_repo):
        """Test successful restore"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = {**self.sample_counterparty, 'is_deleted': True}
        mock_repo.restore.return_value = True

        service = CounterpartyService()
        service.repository = mock_repo

        success, error_msg = service.restore_counterparty('ABC', self.user_info)

        self.assertTrue(success)
        self.assertIsNone(error_msg)

    @patch('reference_data.services.reference_data_service.counterparty_repository')
    def test_restore_counterparty_not_deleted(self, mock_repo):
        """Test restore fails when not deleted"""
        from reference_data.services.reference_data_service import CounterpartyService

        mock_repo.get_by_short_name.return_value = {**self.sample_counterparty, 'is_deleted': False}

        service = CounterpartyService()
        service.repository = mock_repo

        success, error_msg = service.restore_counterparty('ABC', self.user_info)

        self.assertFalse(success)
        self.assertIn('is not deleted', error_msg)


class CounterpartyCIFServiceTestCase(TestCase):
    """Test cases for CounterpartyCIFService"""

    def setUp(self):
        """Set up test data"""
        self.sample_cif = {
            'counterparty_short_name': 'ABC',
            'm_label': 'ABC_US_1_123456',
            'country': 'US',
            'description': 'Main account',
            'is_active': True,
            'is_deleted': False
        }

        self.user_info = {
            'username': 'testuser',
            'user_id': '1',
            'user_email': 'test@example.com'
        }

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_list_cifs_for_counterparty(self, mock_repo):
        """Test list_cifs_for_counterparty returns CIF data"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_counterparty.return_value = [self.sample_cif]

        service = CounterpartyCIFService()
        service.repository = mock_repo

        result = service.list_cifs_for_counterparty('ABC')

        self.assertEqual(len(result), 1)
        mock_repo.get_by_counterparty.assert_called_once_with('ABC', None)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_list_cifs_for_counterparty_with_active_filter(self, mock_repo):
        """Test list_cifs_for_counterparty with is_active filter"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_counterparty.return_value = [self.sample_cif]

        service = CounterpartyCIFService()
        service.repository = mock_repo

        result = service.list_cifs_for_counterparty('ABC', is_active=True)

        mock_repo.get_by_counterparty.assert_called_once_with('ABC', True)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_get_cif(self, mock_repo):
        """Test get_cif returns specific CIF"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = self.sample_cif

        service = CounterpartyCIFService()
        service.repository = mock_repo

        result = service.get_cif('ABC', 'ABC_US_1_123456')

        self.assertIsNotNone(result)
        self.assertEqual(result['m_label'], 'ABC_US_1_123456')

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_get_cif_not_found(self, mock_repo):
        """Test get_cif returns None when not found"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = None

        service = CounterpartyCIFService()
        service.repository = mock_repo

        result = service.get_cif('ABC', 'NOTEXIST')

        self.assertIsNone(result)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_generate_cif_m_label(self, mock_repo):
        """Test _generate_cif_m_label generates unique label"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_counterparty.return_value = [
            {'counterparty_short_name': 'ABC', 'country': 'US'},
            {'counterparty_short_name': 'ABC', 'country': 'US'}
        ]

        service = CounterpartyCIFService()
        service.repository = mock_repo

        m_label = service._generate_cif_m_label('ABC', 'US')

        self.assertTrue(m_label.startswith('ABC_US_3_'))
        self.assertLessEqual(len(m_label), 50)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_generate_cif_m_label_long_name_truncated(self, mock_repo):
        """Test _generate_cif_m_label truncates to 50 chars"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_counterparty.return_value = []

        service = CounterpartyCIFService()
        service.repository = mock_repo

        # Use very long counterparty name
        long_name = 'A' * 40
        m_label = service._generate_cif_m_label(long_name, 'VERYLONGCOUNTRY')

        self.assertLessEqual(len(m_label), 50)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_validate_cif_missing_counterparty(self, mock_repo):
        """Test validation fails when counterparty is missing"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        service = CounterpartyCIFService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_cif({})

        self.assertFalse(is_valid)
        self.assertIn('Counterparty short name is required', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_validate_cif_missing_country(self, mock_repo):
        """Test validation fails when country is missing"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        service = CounterpartyCIFService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_cif({'counterparty_short_name': 'ABC'})

        self.assertFalse(is_valid)
        self.assertIn('Country is required', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_validate_cif_missing_m_label_for_update(self, mock_repo):
        """Test validation fails when m_label missing for update"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        service = CounterpartyCIFService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_cif(
            {'counterparty_short_name': 'ABC', 'country': 'US'},
            is_update=True
        )

        self.assertFalse(is_valid)
        self.assertIn('M-Label', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_validate_cif_m_label_too_long(self, mock_repo):
        """Test validation fails when m_label exceeds max length"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        service = CounterpartyCIFService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_cif(
            {'counterparty_short_name': 'ABC', 'country': 'US', 'm_label': 'A' * 51},
            is_update=True
        )

        self.assertFalse(is_valid)
        self.assertIn('50 characters', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_validate_cif_country_too_long(self, mock_repo):
        """Test validation fails when country exceeds max length"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        service = CounterpartyCIFService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_cif(
            {'counterparty_short_name': 'ABC', 'country': 'A' * 101}
        )

        self.assertFalse(is_valid)
        self.assertIn('Country must be 100 characters', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_validate_cif_description_too_long(self, mock_repo):
        """Test validation fails when description exceeds max length"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        service = CounterpartyCIFService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_cif(
            {'counterparty_short_name': 'ABC', 'country': 'US', 'description': 'A' * 501}
        )

        self.assertFalse(is_valid)
        self.assertIn('Description must be 500 characters', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_validate_cif_success(self, mock_repo):
        """Test validation succeeds for valid data"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        service = CounterpartyCIFService()
        service.repository = mock_repo

        is_valid, error_msg = service.validate_cif(
            {'counterparty_short_name': 'ABC', 'country': 'US', 'description': 'Test'}
        )

        self.assertTrue(is_valid)
        self.assertIsNone(error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_create_cif_success(self, mock_repo):
        """Test successful CIF creation"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_counterparty.return_value = []
        mock_repo.create.return_value = True

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.create_cif(
            {'counterparty_short_name': 'ABC', 'country': 'US'},
            self.user_info
        )

        self.assertTrue(success)
        self.assertIsNone(error_msg)
        mock_repo.create.assert_called_once()

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_create_cif_validation_failure(self, mock_repo):
        """Test CIF creation fails on validation"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.create_cif(
            {'counterparty_short_name': ''},
            self.user_info
        )

        self.assertFalse(success)
        self.assertIn('required', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_create_cif_db_failure(self, mock_repo):
        """Test CIF creation fails on database error"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_counterparty.return_value = []
        mock_repo.create.return_value = False

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.create_cif(
            {'counterparty_short_name': 'ABC', 'country': 'US'},
            self.user_info
        )

        self.assertFalse(success)
        self.assertIn('Failed to create', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_update_cif_success(self, mock_repo):
        """Test successful CIF update"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = self.sample_cif
        mock_repo.update.return_value = True

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.update_cif(
            'ABC', 'ABC_US_1_123456',
            {'country': 'UK', 'description': 'Updated'},
            self.user_info
        )

        self.assertTrue(success)
        self.assertIsNone(error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_update_cif_not_found(self, mock_repo):
        """Test update fails when CIF not found"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = None

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.update_cif(
            'ABC', 'NOTEXIST',
            {'description': 'Updated'},
            self.user_info
        )

        self.assertFalse(success)
        self.assertIn('not found', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_update_cif_validation_failure(self, mock_repo):
        """Test update fails on validation"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = self.sample_cif

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.update_cif(
            'ABC', 'ABC_US_1_123456',
            {'country': 'A' * 101},
            self.user_info
        )

        self.assertFalse(success)
        self.assertIn('Country must be 100 characters', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_update_cif_db_failure(self, mock_repo):
        """Test update fails on database error"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = self.sample_cif
        mock_repo.update.return_value = False

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.update_cif(
            'ABC', 'ABC_US_1_123456',
            {'country': 'US', 'description': 'Updated'},
            self.user_info
        )

        self.assertFalse(success)
        self.assertIn('Failed to update', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_delete_cif_success(self, mock_repo):
        """Test successful CIF deletion"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = {**self.sample_cif, 'is_deleted': False}
        mock_repo.soft_delete.return_value = True

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.delete_cif('ABC', 'ABC_US_1_123456', self.user_info)

        self.assertTrue(success)
        self.assertIsNone(error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_delete_cif_not_found(self, mock_repo):
        """Test delete fails when not found"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = None

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.delete_cif('ABC', 'NOTEXIST', self.user_info)

        self.assertFalse(success)
        self.assertIn('not found', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_delete_cif_already_deleted(self, mock_repo):
        """Test delete fails when already deleted"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = {**self.sample_cif, 'is_deleted': True}

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.delete_cif('ABC', 'ABC_US_1_123456', self.user_info)

        self.assertFalse(success)
        self.assertIn('already deleted', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_delete_cif_db_failure(self, mock_repo):
        """Test delete fails on database error"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = {**self.sample_cif, 'is_deleted': False}
        mock_repo.soft_delete.return_value = False

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.delete_cif('ABC', 'ABC_US_1_123456', self.user_info)

        self.assertFalse(success)
        self.assertIn('Failed to delete', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_restore_cif_success(self, mock_repo):
        """Test successful CIF restore"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = {**self.sample_cif, 'is_deleted': True}
        mock_repo.restore.return_value = True

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.restore_cif('ABC', 'ABC_US_1_123456', self.user_info)

        self.assertTrue(success)
        self.assertIsNone(error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_restore_cif_not_found(self, mock_repo):
        """Test restore fails when not found"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = None

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.restore_cif('ABC', 'NOTEXIST', self.user_info)

        self.assertFalse(success)
        self.assertIn('not found', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_restore_cif_not_deleted(self, mock_repo):
        """Test restore fails when not deleted"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = {**self.sample_cif, 'is_deleted': False}

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.restore_cif('ABC', 'ABC_US_1_123456', self.user_info)

        self.assertFalse(success)
        self.assertIn('is not deleted', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_restore_cif_db_failure(self, mock_repo):
        """Test restore fails on database error"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_by_cif_key.return_value = {**self.sample_cif, 'is_deleted': True}
        mock_repo.restore.return_value = False

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.restore_cif('ABC', 'ABC_US_1_123456', self.user_info)

        self.assertFalse(success)
        self.assertIn('Failed to restore', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_delete_all_for_counterparty_success(self, mock_repo):
        """Test successful delete all CIFs for counterparty"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.delete_all_for_counterparty.return_value = True

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.delete_all_for_counterparty('ABC', self.user_info)

        self.assertTrue(success)
        self.assertIsNone(error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_delete_all_for_counterparty_failure(self, mock_repo):
        """Test delete all fails on database error"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.delete_all_for_counterparty.return_value = False

        service = CounterpartyCIFService()
        service.repository = mock_repo

        success, error_msg = service.delete_all_for_counterparty('ABC', self.user_info)

        self.assertFalse(success)
        self.assertIn('Failed to delete', error_msg)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_get_cif_counts(self, mock_repo):
        """Test get_cif_counts returns dictionary"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_cif_counts.return_value = {'ABC': 3, 'XYZ': 2}

        service = CounterpartyCIFService()
        service.repository = mock_repo

        result = service.get_cif_counts()

        self.assertEqual(result['ABC'], 3)
        self.assertEqual(result['XYZ'], 2)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_get_cif_counts_with_filter(self, mock_repo):
        """Test get_cif_counts with is_active filter"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_cif_counts.return_value = {'ABC': 2}

        service = CounterpartyCIFService()
        service.repository = mock_repo

        result = service.get_cif_counts(is_active=True)

        mock_repo.get_cif_counts.assert_called_once_with(True)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_get_counterparties_with_multiple_cifs(self, mock_repo):
        """Test get_counterparties_with_multiple_cifs returns list"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_counterparties_with_multiple_cifs.return_value = ['ABC', 'XYZ']

        service = CounterpartyCIFService()
        service.repository = mock_repo

        result = service.get_counterparties_with_multiple_cifs()

        self.assertEqual(len(result), 2)
        self.assertIn('ABC', result)

    @patch('reference_data.services.counterparty_cif_service.counterparty_cif_repository')
    def test_get_counterparties_with_multiple_cifs_filter(self, mock_repo):
        """Test get_counterparties_with_multiple_cifs with filter"""
        from reference_data.services.counterparty_cif_service import CounterpartyCIFService

        mock_repo.get_counterparties_with_multiple_cifs.return_value = ['ABC']

        service = CounterpartyCIFService()
        service.repository = mock_repo

        result = service.get_counterparties_with_multiple_cifs(is_active=True)

        mock_repo.get_counterparties_with_multiple_cifs.assert_called_once_with(True)
