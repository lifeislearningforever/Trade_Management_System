"""
Reference Data Repository Tests

Tests for reference data repositories including:
- CurrencyRepository
- CountryRepository
- CalendarRepository
- CounterpartyRepository
- CounterpartyCIFRepository
"""

import pytest
from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock


class ImpalaReferenceRepositoryTestCase(TestCase):
    """Test cases for base ImpalaReferenceRepository"""

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_execute_query_success(self, mock_impala):
        """Test _execute_query returns results"""
        from reference_data.repositories.reference_data_repository import ImpalaReferenceRepository

        mock_impala.execute_query.return_value = [
            {'col1': 'value1'},
            {'col1': 'value2'}
        ]

        repo = ImpalaReferenceRepository()
        result = repo._execute_query("SELECT * FROM test")

        self.assertEqual(len(result), 2)
        mock_impala.execute_query.assert_called_once()

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_execute_query_returns_empty_list_on_none(self, mock_impala):
        """Test _execute_query returns empty list when result is None"""
        from reference_data.repositories.reference_data_repository import ImpalaReferenceRepository

        mock_impala.execute_query.return_value = None

        repo = ImpalaReferenceRepository()
        result = repo._execute_query("SELECT * FROM test")

        self.assertEqual(result, [])

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_execute_query_raises_on_error(self, mock_impala):
        """Test _execute_query raises exception on error"""
        from reference_data.repositories.reference_data_repository import ImpalaReferenceRepository

        mock_impala.execute_query.side_effect = Exception("Database error")

        repo = ImpalaReferenceRepository()

        with self.assertRaises(Exception):
            repo._execute_query("SELECT * FROM test")

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_execute_write_success(self, mock_impala):
        """Test _execute_write returns True on success"""
        from reference_data.repositories.reference_data_repository import ImpalaReferenceRepository

        mock_impala.execute_write.return_value = None

        repo = ImpalaReferenceRepository()
        result = repo._execute_write("INSERT INTO test VALUES (1)")

        self.assertTrue(result)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_execute_write_raises_on_error(self, mock_impala):
        """Test _execute_write raises exception on error"""
        from reference_data.repositories.reference_data_repository import ImpalaReferenceRepository

        mock_impala.execute_write.side_effect = Exception("Write error")

        repo = ImpalaReferenceRepository()

        with self.assertRaises(Exception):
            repo._execute_write("INSERT INTO test VALUES (1)")

    def test_escape_sql_handles_quotes(self):
        """Test _escape_sql escapes single quotes"""
        from reference_data.repositories.reference_data_repository import ImpalaReferenceRepository

        repo = ImpalaReferenceRepository()

        result = repo._escape_sql("O'Brien")
        self.assertEqual(result, "O''Brien")

    def test_escape_sql_handles_none(self):
        """Test _escape_sql handles None values"""
        from reference_data.repositories.reference_data_repository import ImpalaReferenceRepository

        repo = ImpalaReferenceRepository()

        result = repo._escape_sql(None)
        self.assertEqual(result, '')


class CurrencyRepositoryTestCase(TestCase):
    """Test cases for CurrencyRepository"""

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_list_all_returns_mapped_currencies(self, mock_impala):
        """Test list_all returns properly mapped currency data"""
        from reference_data.repositories.reference_data_repository import CurrencyRepository

        mock_impala.execute_query.return_value = [
            {'iso_code': 'USD', 'name': 'US Dollar', 'full_name': 'United States Dollar',
             'symbol': '$', 'precision': 2, 'rate_precision': 4, 'calendar': 'NYC', 'spot_schedule': 'T+2'}
        ]

        repo = CurrencyRepository()
        result = repo.list_all()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['code'], 'USD')
        self.assertEqual(result[0]['name'], 'US Dollar')
        self.assertEqual(result[0]['decimal_places'], 2)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_list_all_with_search(self, mock_impala):
        """Test list_all with search parameter"""
        from reference_data.repositories.reference_data_repository import CurrencyRepository

        mock_impala.execute_query.return_value = [
            {'iso_code': 'USD', 'name': 'US Dollar', 'full_name': 'United States Dollar'}
        ]

        repo = CurrencyRepository()
        result = repo.list_all(search='USD')

        # Verify search term is in query
        call_args = mock_impala.execute_query.call_args[0][0]
        self.assertIn('usd', call_args.lower())

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_by_code_returns_currency(self, mock_impala):
        """Test get_by_code returns specific currency"""
        from reference_data.repositories.reference_data_repository import CurrencyRepository

        mock_impala.execute_query.return_value = [
            {'iso_code': 'USD', 'name': 'US Dollar', 'full_name': 'United States Dollar',
             'symbol': '$', 'precision': 2, 'rate_precision': 4, 'calendar': 'NYC', 'spot_schedule': 'T+2'}
        ]

        repo = CurrencyRepository()
        result = repo.get_by_code('USD')

        self.assertIsNotNone(result)
        self.assertEqual(result['code'], 'USD')

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_by_code_returns_none_when_not_found(self, mock_impala):
        """Test get_by_code returns None when not found"""
        from reference_data.repositories.reference_data_repository import CurrencyRepository

        mock_impala.execute_query.return_value = []

        repo = CurrencyRepository()
        result = repo.get_by_code('XXX')

        self.assertIsNone(result)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_active_currencies(self, mock_impala):
        """Test get_active_currencies returns all currencies"""
        from reference_data.repositories.reference_data_repository import CurrencyRepository

        mock_impala.execute_query.return_value = [
            {'iso_code': 'USD', 'name': 'US Dollar'},
            {'iso_code': 'EUR', 'name': 'Euro'}
        ]

        repo = CurrencyRepository()
        result = repo.get_active_currencies()

        self.assertEqual(len(result), 2)


class CountryRepositoryTestCase(TestCase):
    """Test cases for CountryRepository"""

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_list_all_returns_countries(self, mock_impala):
        """Test list_all returns country data"""
        from reference_data.repositories.reference_data_repository import CountryRepository

        mock_impala.execute_query.return_value = [
            {'label': 'US', 'full_name': 'United States'},
            {'label': 'UK', 'full_name': 'United Kingdom'}
        ]

        repo = CountryRepository()
        result = repo.list_all()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['code'], 'US')
        self.assertEqual(result[0]['name'], 'United States')

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_list_all_with_search(self, mock_impala):
        """Test list_all with search parameter"""
        from reference_data.repositories.reference_data_repository import CountryRepository

        mock_impala.execute_query.return_value = [
            {'label': 'US', 'full_name': 'United States'}
        ]

        repo = CountryRepository()
        result = repo.list_all(search='United')

        call_args = mock_impala.execute_query.call_args[0][0]
        self.assertIn('united', call_args.lower())

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_by_code_returns_country(self, mock_impala):
        """Test get_by_code returns specific country"""
        from reference_data.repositories.reference_data_repository import CountryRepository

        mock_impala.execute_query.return_value = [
            {'label': 'US', 'full_name': 'United States'}
        ]

        repo = CountryRepository()
        result = repo.get_by_code('US')

        self.assertIsNotNone(result)
        self.assertEqual(result['label'], 'US')

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_by_code_returns_none_when_not_found(self, mock_impala):
        """Test get_by_code returns None when not found"""
        from reference_data.repositories.reference_data_repository import CountryRepository

        mock_impala.execute_query.return_value = []

        repo = CountryRepository()
        result = repo.get_by_code('XX')

        self.assertIsNone(result)


class CalendarRepositoryTestCase(TestCase):
    """Test cases for CalendarRepository"""

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_list_all_returns_calendars(self, mock_impala):
        """Test list_all returns calendar data"""
        from reference_data.repositories.reference_data_repository import CalendarRepository

        mock_impala.execute_query.return_value = [
            {'calendar_label': 'NYC', 'calendar_description': 'New York', 'holiday_date': '2025-12-25'},
            {'calendar_label': 'LON', 'calendar_description': 'London', 'holiday_date': '2025-12-25'}
        ]

        repo = CalendarRepository()
        result = repo.list_all()

        self.assertEqual(len(result), 2)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_list_all_with_calendar_label(self, mock_impala):
        """Test list_all filters by calendar label"""
        from reference_data.repositories.reference_data_repository import CalendarRepository

        mock_impala.execute_query.return_value = [
            {'calendar_label': 'NYC', 'calendar_description': 'New York', 'holiday_date': '2025-12-25'}
        ]

        repo = CalendarRepository()
        result = repo.list_all(calendar_label='NYC')

        call_args = mock_impala.execute_query.call_args[0][0]
        self.assertIn("calendar_label = 'NYC'", call_args)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_list_all_with_search(self, mock_impala):
        """Test list_all with search parameter"""
        from reference_data.repositories.reference_data_repository import CalendarRepository

        mock_impala.execute_query.return_value = [
            {'calendar_label': 'NYC', 'calendar_description': 'New York', 'holiday_date': '2025-12-25'}
        ]

        repo = CalendarRepository()
        result = repo.list_all(search='York')

        call_args = mock_impala.execute_query.call_args[0][0]
        self.assertIn('york', call_args.lower())

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_distinct_calendars(self, mock_impala):
        """Test get_distinct_calendars returns list of labels"""
        from reference_data.repositories.reference_data_repository import CalendarRepository

        mock_impala.execute_query.return_value = [
            {'calendar_label': 'NYC'},
            {'calendar_label': 'LON'},
            {'calendar_label': 'TOK'}
        ]

        repo = CalendarRepository()
        result = repo.get_distinct_calendars()

        self.assertEqual(len(result), 3)
        self.assertIn('NYC', result)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_holidays_for_calendar(self, mock_impala):
        """Test get_holidays_for_calendar returns holidays"""
        from reference_data.repositories.reference_data_repository import CalendarRepository

        mock_impala.execute_query.return_value = [
            {'calendar_label': 'NYC', 'holiday_date': '2025-12-25'},
            {'calendar_label': 'NYC', 'holiday_date': '2025-01-01'}
        ]

        repo = CalendarRepository()
        result = repo.get_holidays_for_calendar('NYC')

        self.assertEqual(len(result), 2)


class CounterpartyRepositoryTestCase(TestCase):
    """Test cases for CounterpartyRepository"""

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_list_all_returns_counterparties(self, mock_impala):
        """Test list_all returns counterparty data"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_query.return_value = [
            {'counterparty_short_name': 'ABC', 'counterparty_full_name': 'ABC Bank', 'country': 'US'},
            {'counterparty_short_name': 'XYZ', 'counterparty_full_name': 'XYZ Corp', 'country': 'UK'}
        ]

        repo = CounterpartyRepository()
        result = repo.list_all()

        self.assertEqual(len(result), 2)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_list_all_with_search(self, mock_impala):
        """Test list_all with search filter"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_query.return_value = [
            {'counterparty_short_name': 'ABC', 'counterparty_full_name': 'ABC Bank'}
        ]

        repo = CounterpartyRepository()
        result = repo.list_all(search='ABC')

        call_args = mock_impala.execute_query.call_args[0][0]
        self.assertIn('abc', call_args.lower())

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_list_all_with_country_filter(self, mock_impala):
        """Test list_all with country filter"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_query.return_value = [
            {'counterparty_short_name': 'ABC', 'counterparty_full_name': 'ABC Bank', 'country': 'US'}
        ]

        repo = CounterpartyRepository()
        result = repo.list_all(country='US')

        call_args = mock_impala.execute_query.call_args[0][0]
        self.assertIn("country = 'US'", call_args)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_list_all_with_is_active_filter(self, mock_impala):
        """Test list_all with is_active filter"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_query.return_value = []

        repo = CounterpartyRepository()
        result = repo.list_all(is_active=True)

        call_args = mock_impala.execute_query.call_args[0][0]
        self.assertIn('is_active = TRUE', call_args)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_by_short_name(self, mock_impala):
        """Test get_by_short_name returns counterparty"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_query.return_value = [
            {'counterparty_short_name': 'ABC', 'counterparty_full_name': 'ABC Bank'}
        ]

        repo = CounterpartyRepository()
        result = repo.get_by_short_name('ABC')

        self.assertIsNotNone(result)
        self.assertEqual(result['counterparty_short_name'], 'ABC')

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_by_short_name_returns_none_when_not_found(self, mock_impala):
        """Test get_by_short_name returns None when not found"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_query.return_value = []

        repo = CounterpartyRepository()
        result = repo.get_by_short_name('NOTEXIST')

        self.assertIsNone(result)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_distinct_countries(self, mock_impala):
        """Test get_distinct_countries returns list"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_query.return_value = [
            {'country': 'US'},
            {'country': 'UK'},
            {'country': 'SG'}
        ]

        repo = CounterpartyRepository()
        result = repo.get_distinct_countries()

        self.assertEqual(len(result), 3)
        self.assertIn('US', result)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_create_counterparty(self, mock_impala):
        """Test create inserts counterparty"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_write.return_value = None

        repo = CounterpartyRepository()
        result = repo.create({
            'counterparty_short_name': 'NEW',
            'counterparty_full_name': 'New Bank',
            'country': 'US',
            'is_active': True,
            'is_deleted': False
        })

        self.assertTrue(result)
        mock_impala.execute_write.assert_called_once()

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_create_counterparty_failure(self, mock_impala):
        """Test create returns False on failure"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_write.side_effect = Exception("Insert failed")

        repo = CounterpartyRepository()
        result = repo.create({'counterparty_short_name': 'NEW'})

        self.assertFalse(result)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_update_counterparty(self, mock_impala):
        """Test update uses UPSERT"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_write.return_value = None

        repo = CounterpartyRepository()
        result = repo.update('ABC', {'counterparty_full_name': 'ABC Bank Updated'})

        self.assertTrue(result)
        mock_impala.execute_write.assert_called_once()

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_soft_delete(self, mock_impala):
        """Test soft_delete sets is_active=False, is_deleted=True"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_write.return_value = None

        repo = CounterpartyRepository()
        result = repo.soft_delete('ABC', 'testuser')

        self.assertTrue(result)
        call_args = mock_impala.execute_write.call_args[0][0]
        self.assertIn('FALSE as is_active', call_args)
        self.assertIn('TRUE as is_deleted', call_args)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_soft_delete_failure(self, mock_impala):
        """Test soft_delete returns False on failure"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_write.side_effect = Exception("Delete failed")

        repo = CounterpartyRepository()
        result = repo.soft_delete('ABC', 'testuser')

        self.assertFalse(result)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_restore(self, mock_impala):
        """Test restore sets is_active=True, is_deleted=False"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_write.return_value = None

        repo = CounterpartyRepository()
        result = repo.restore('ABC', 'testuser')

        self.assertTrue(result)
        call_args = mock_impala.execute_write.call_args[0][0]
        self.assertIn('TRUE as is_active', call_args)
        self.assertIn('FALSE as is_deleted', call_args)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_restore_failure(self, mock_impala):
        """Test restore returns False on failure"""
        from reference_data.repositories.reference_data_repository import CounterpartyRepository

        mock_impala.execute_write.side_effect = Exception("Restore failed")

        repo = CounterpartyRepository()
        result = repo.restore('ABC', 'testuser')

        self.assertFalse(result)


class CounterpartyCIFRepositoryTestCase(TestCase):
    """Test cases for CounterpartyCIFRepository"""

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_by_counterparty(self, mock_impala):
        """Test get_by_counterparty returns CIFs"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_query.return_value = [
            {'counterparty_short_name': 'ABC', 'm_label': 'CIF001', 'country': 'US'},
            {'counterparty_short_name': 'ABC', 'm_label': 'CIF002', 'country': 'UK'}
        ]

        repo = CounterpartyCIFRepository()
        result = repo.get_by_counterparty('ABC')

        self.assertEqual(len(result), 2)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_by_counterparty_with_active_filter(self, mock_impala):
        """Test get_by_counterparty with is_active filter"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_query.return_value = []

        repo = CounterpartyCIFRepository()
        result = repo.get_by_counterparty('ABC', is_active=True)

        call_args = mock_impala.execute_query.call_args[0][0]
        self.assertIn('is_active = TRUE', call_args)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_by_cif_key(self, mock_impala):
        """Test get_by_cif_key returns specific CIF"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_query.return_value = [
            {'counterparty_short_name': 'ABC', 'm_label': 'CIF001', 'country': 'US'}
        ]

        repo = CounterpartyCIFRepository()
        result = repo.get_by_cif_key('ABC', 'CIF001', 'US')

        self.assertIsNotNone(result)
        self.assertEqual(result['m_label'], 'CIF001')

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_by_cif_key_returns_none_when_not_found(self, mock_impala):
        """Test get_by_cif_key returns None when not found"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_query.return_value = []

        repo = CounterpartyCIFRepository()
        result = repo.get_by_cif_key('ABC', 'NOTEXIST', 'US')

        self.assertIsNone(result)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_create_cif(self, mock_impala):
        """Test create inserts CIF"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_write.return_value = True

        repo = CounterpartyCIFRepository()
        result = repo.create({
            'counterparty_short_name': 'ABC',
            'm_label': 'CIF001',
            'country': 'US',
            'is_active': True,
            'is_deleted': False
        })

        self.assertTrue(result)
        mock_impala.execute_write.assert_called_once()

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_update_cif(self, mock_impala):
        """Test update CIF"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_write.return_value = True

        repo = CounterpartyCIFRepository()
        result = repo.update('ABC', 'CIF001', 'US', {'description': 'Updated'})

        self.assertTrue(result)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_soft_delete_cif(self, mock_impala):
        """Test soft_delete CIF"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_write.return_value = True

        repo = CounterpartyCIFRepository()
        result = repo.soft_delete('ABC', 'CIF001', 'US', 'testuser')

        self.assertTrue(result)
        call_args = mock_impala.execute_write.call_args[0][0]
        self.assertIn('FALSE as is_active', call_args)
        self.assertIn('TRUE as is_deleted', call_args)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_restore_cif(self, mock_impala):
        """Test restore CIF"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_write.return_value = True

        repo = CounterpartyCIFRepository()
        result = repo.restore('ABC', 'CIF001', 'US', 'testuser')

        self.assertTrue(result)
        call_args = mock_impala.execute_write.call_args[0][0]
        self.assertIn('TRUE as is_active', call_args)
        self.assertIn('FALSE as is_deleted', call_args)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_delete_all_for_counterparty(self, mock_impala):
        """Test delete_all_for_counterparty"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_write.return_value = True

        repo = CounterpartyCIFRepository()
        result = repo.delete_all_for_counterparty('ABC', 'testuser')

        self.assertTrue(result)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_cif_counts(self, mock_impala):
        """Test get_cif_counts returns counts per counterparty"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_query.return_value = [
            {'counterparty_short_name': 'ABC', 'cif_count': 3},
            {'counterparty_short_name': 'XYZ', 'cif_count': 1}
        ]

        repo = CounterpartyCIFRepository()
        result = repo.get_cif_counts()

        self.assertEqual(result['ABC'], 3)
        self.assertEqual(result['XYZ'], 1)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_cif_counts_with_active_filter(self, mock_impala):
        """Test get_cif_counts with is_active filter"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_query.return_value = []

        repo = CounterpartyCIFRepository()
        result = repo.get_cif_counts(is_active=True)

        call_args = mock_impala.execute_query.call_args[0][0]
        self.assertIn('is_active = TRUE', call_args)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_counterparties_with_multiple_cifs(self, mock_impala):
        """Test get_counterparties_with_multiple_cifs returns list"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_query.return_value = [
            {'counterparty_short_name': 'ABC', 'cif_count': 3},
            {'counterparty_short_name': 'DEF', 'cif_count': 2}
        ]

        repo = CounterpartyCIFRepository()
        result = repo.get_counterparties_with_multiple_cifs()

        self.assertEqual(len(result), 2)
        self.assertIn('ABC', result)

    @patch('reference_data.repositories.reference_data_repository.impala_manager')
    def test_get_counterparties_with_multiple_cifs_with_active_filter(self, mock_impala):
        """Test get_counterparties_with_multiple_cifs with is_active filter"""
        from reference_data.repositories.counterparty_cif_repository import CounterpartyCIFRepository

        mock_impala.execute_query.return_value = []

        repo = CounterpartyCIFRepository()
        result = repo.get_counterparties_with_multiple_cifs(is_active=True)

        call_args = mock_impala.execute_query.call_args[0][0]
        self.assertIn('is_active = TRUE', call_args)
