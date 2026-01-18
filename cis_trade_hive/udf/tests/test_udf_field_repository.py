"""
UDF Field Repository Tests - Simplified Logic

Comprehensive tests for UDFFieldRepository with composite primary key schema.
Tests cover:
- Cascading dropdown operations (get_object_types, get_fields_by_entity, get_field_values)
- CRUD operations (create, update, get_by_key, get_all)
- Soft delete and restore operations
- Statistics and helper methods
"""

import pytest
from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime

from udf.repositories.udf_field_repository import (
    UDFFieldRepository,
    UDFFieldRepositoryInterface,
    udf_field_repository
)


class UDFFieldRepositoryEscapeStringTestCase(TestCase):
    """Test cases for string escaping"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    def test_escape_string_normal(self):
        """Test escaping normal string"""
        result = self.repository._escape_string("test value")
        self.assertEqual(result, "test value")

    def test_escape_string_with_quotes(self):
        """Test escaping string with single quotes"""
        result = self.repository._escape_string("test's value")
        self.assertEqual(result, "test\\'s value")

    def test_escape_string_none(self):
        """Test escaping None value"""
        result = self.repository._escape_string(None)
        self.assertEqual(result, "")

    def test_escape_string_multiple_quotes(self):
        """Test escaping multiple single quotes"""
        result = self.repository._escape_string("it's john's test")
        self.assertEqual(result, "it\\'s john\\'s test")


class UDFFieldRepositoryGetObjectTypesTestCase(TestCase):
    """Test cases for get_object_types method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_object_types_success(self, mock_execute):
        """Test successful retrieval of object types"""
        mock_execute.return_value = [
            {'object_type': 'PORTFOLIO'},
            {'object_type': 'SECURITY'},
            {'object_type': 'TRADE'}
        ]

        result = self.repository.get_object_types()

        self.assertEqual(len(result), 3)
        self.assertIn('PORTFOLIO', result)
        self.assertIn('SECURITY', result)
        self.assertIn('TRADE', result)
        mock_execute.assert_called_once()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_object_types_empty(self, mock_execute):
        """Test get_object_types with no results"""
        mock_execute.return_value = []

        result = self.repository.get_object_types()

        self.assertEqual(result, [])

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_object_types_none_result(self, mock_execute):
        """Test get_object_types with None result"""
        mock_execute.return_value = None

        result = self.repository.get_object_types()

        self.assertEqual(result, [])

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_object_types_exception(self, mock_execute):
        """Test get_object_types handles exception"""
        mock_execute.side_effect = Exception("Database error")

        result = self.repository.get_object_types()

        self.assertEqual(result, [])


class UDFFieldRepositoryGetFieldsByEntityTestCase(TestCase):
    """Test cases for get_fields_by_entity method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_fields_by_entity_success(self, mock_execute):
        """Test successful retrieval of fields for entity"""
        mock_execute.return_value = [
            {'field_name': 'Fund Type'},
            {'field_name': 'Selling Rule'},
            {'field_name': 'Risk Rating'}
        ]

        result = self.repository.get_fields_by_entity('TRADE')

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['field_name'], 'Fund Type')
        mock_execute.assert_called_once()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_fields_by_entity_empty(self, mock_execute):
        """Test get_fields_by_entity with no results"""
        mock_execute.return_value = []

        result = self.repository.get_fields_by_entity('UNKNOWN')

        self.assertEqual(result, [])

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_fields_by_entity_none(self, mock_execute):
        """Test get_fields_by_entity with None result"""
        mock_execute.return_value = None

        result = self.repository.get_fields_by_entity('TRADE')

        self.assertEqual(result, [])

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_fields_by_entity_escapes_input(self, mock_execute):
        """Test get_fields_by_entity escapes special characters"""
        mock_execute.return_value = []

        result = self.repository.get_fields_by_entity("TRADE'S TEST")

        # Should not raise error
        self.assertEqual(result, [])

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_fields_by_entity_exception(self, mock_execute):
        """Test get_fields_by_entity handles exception"""
        mock_execute.side_effect = Exception("Query failed")

        result = self.repository.get_fields_by_entity('TRADE')

        self.assertEqual(result, [])


class UDFFieldRepositoryGetFieldValuesTestCase(TestCase):
    """Test cases for get_field_values method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_field_values_success(self, mock_execute):
        """Test successful retrieval of field values"""
        mock_execute.return_value = [
            {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'EQUITY', 'is_active': True},
            {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'FIXED_INCOME', 'is_active': True}
        ]

        result = self.repository.get_field_values('TRADE', 'Fund Type')

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['field_value'], 'EQUITY')
        mock_execute.assert_called_once()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_field_values_empty(self, mock_execute):
        """Test get_field_values with no results"""
        mock_execute.return_value = []

        result = self.repository.get_field_values('TRADE', 'Unknown Field')

        self.assertEqual(result, [])

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_field_values_none(self, mock_execute):
        """Test get_field_values with None result"""
        mock_execute.return_value = None

        result = self.repository.get_field_values('TRADE', 'Fund Type')

        self.assertEqual(result, [])

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_field_values_exception(self, mock_execute):
        """Test get_field_values handles exception"""
        mock_execute.side_effect = Exception("Database error")

        result = self.repository.get_field_values('TRADE', 'Fund Type')

        self.assertEqual(result, [])


class UDFFieldRepositoryGetAllTestCase(TestCase):
    """Test cases for get_all method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_all_no_filters(self, mock_execute):
        """Test get_all without filters"""
        mock_execute.return_value = [
            {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'EQUITY'},
            {'object_type': 'PORTFOLIO', 'field_name': 'Risk Level', 'field_value': 'HIGH'}
        ]

        result = self.repository.get_all()

        self.assertEqual(len(result), 2)
        mock_execute.assert_called_once()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_all_with_object_type_filter(self, mock_execute):
        """Test get_all with object_type filter"""
        mock_execute.return_value = [
            {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'EQUITY'}
        ]

        result = self.repository.get_all(object_type='TRADE')

        self.assertEqual(len(result), 1)
        mock_execute.assert_called_once()
        # Verify query contains filter
        call_args = mock_execute.call_args[0][0]
        self.assertIn('TRADE', call_args)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_all_with_is_active_true(self, mock_execute):
        """Test get_all with is_active=True filter"""
        mock_execute.return_value = [
            {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'EQUITY', 'is_active': True}
        ]

        result = self.repository.get_all(is_active=True)

        self.assertEqual(len(result), 1)
        call_args = mock_execute.call_args[0][0]
        self.assertIn('is_active = true', call_args)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_all_with_is_active_false(self, mock_execute):
        """Test get_all with is_active=False filter"""
        mock_execute.return_value = [
            {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'EQUITY', 'is_active': False}
        ]

        result = self.repository.get_all(is_active=False)

        self.assertEqual(len(result), 1)
        call_args = mock_execute.call_args[0][0]
        self.assertIn('is_active = false', call_args)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_all_with_both_filters(self, mock_execute):
        """Test get_all with both filters"""
        mock_execute.return_value = []

        result = self.repository.get_all(object_type='TRADE', is_active=True)

        self.assertEqual(result, [])
        call_args = mock_execute.call_args[0][0]
        self.assertIn('TRADE', call_args)
        self.assertIn('is_active = true', call_args)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_all_empty(self, mock_execute):
        """Test get_all with no results"""
        mock_execute.return_value = []

        result = self.repository.get_all()

        self.assertEqual(result, [])

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_all_none(self, mock_execute):
        """Test get_all with None result"""
        mock_execute.return_value = None

        result = self.repository.get_all()

        self.assertEqual(result, [])

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_all_exception(self, mock_execute):
        """Test get_all raises exception"""
        mock_execute.side_effect = Exception("Database error")

        with self.assertRaises(Exception):
            self.repository.get_all()


class UDFFieldRepositoryGetByKeyTestCase(TestCase):
    """Test cases for get_by_key method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_by_key_found(self, mock_execute):
        """Test get_by_key when record found"""
        mock_execute.return_value = [
            {
                'object_type': 'TRADE',
                'field_name': 'Fund Type',
                'field_value': 'EQUITY',
                'is_active': True,
                'created_by': 'admin',
                'created_at': 1234567890,
                'updated_by': 'admin',
                'updated_at': 1234567890
            }
        ]

        result = self.repository.get_by_key('TRADE', 'Fund Type', 'EQUITY')

        self.assertIsNotNone(result)
        self.assertEqual(result['object_type'], 'TRADE')
        self.assertEqual(result['field_value'], 'EQUITY')

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_by_key_not_found(self, mock_execute):
        """Test get_by_key when record not found"""
        mock_execute.return_value = []

        result = self.repository.get_by_key('TRADE', 'Unknown', 'Value')

        self.assertIsNone(result)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_by_key_with_empty_value(self, mock_execute):
        """Test get_by_key with empty field_value (field definition)"""
        mock_execute.return_value = [
            {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': '', 'is_active': True}
        ]

        result = self.repository.get_by_key('TRADE', 'Fund Type', '')

        self.assertIsNotNone(result)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_by_key_with_none_value(self, mock_execute):
        """Test get_by_key with None field_value"""
        mock_execute.return_value = [
            {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': '', 'is_active': True}
        ]

        result = self.repository.get_by_key('TRADE', 'Fund Type', None)

        self.assertIsNotNone(result)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_by_key_exception(self, mock_execute):
        """Test get_by_key raises exception"""
        mock_execute.side_effect = Exception("Database error")

        with self.assertRaises(Exception):
            self.repository.get_by_key('TRADE', 'Fund Type', 'EQUITY')


class UDFFieldRepositoryGetByIdTestCase(TestCase):
    """Test cases for deprecated get_by_id method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    def test_get_by_id_returns_none(self):
        """Test get_by_id returns None (deprecated)"""
        result = self.repository.get_by_id(123)

        self.assertIsNone(result)


class UDFFieldRepositoryCreateTestCase(TestCase):
    """Test cases for create method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_write')
    def test_create_success(self, mock_execute):
        """Test successful field creation"""
        mock_execute.return_value = True

        field_data = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type',
            'field_value': 'EQUITY',
            'created_by': 'admin'
        }

        result = self.repository.create(field_data)

        self.assertTrue(result)
        mock_execute.assert_called_once()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_write')
    def test_create_without_field_value(self, mock_execute):
        """Test creation without field_value (defaults to empty)"""
        mock_execute.return_value = True

        field_data = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type',
            'created_by': 'admin'
        }

        result = self.repository.create(field_data)

        self.assertTrue(result)

    def test_create_missing_object_type(self):
        """Test create fails without object_type"""
        field_data = {
            'field_name': 'Fund Type',
            'created_by': 'admin'
        }

        result = self.repository.create(field_data)

        self.assertFalse(result)

    def test_create_missing_field_name(self):
        """Test create fails without field_name"""
        field_data = {
            'object_type': 'TRADE',
            'created_by': 'admin'
        }

        result = self.repository.create(field_data)

        self.assertFalse(result)

    def test_create_missing_created_by(self):
        """Test create fails without created_by"""
        field_data = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type'
        }

        result = self.repository.create(field_data)

        self.assertFalse(result)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_write')
    def test_create_with_is_active_true(self, mock_execute):
        """Test create with is_active=True"""
        mock_execute.return_value = True

        field_data = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type',
            'field_value': 'EQUITY',
            'is_active': True,
            'created_by': 'admin'
        }

        result = self.repository.create(field_data)

        self.assertTrue(result)
        call_args = mock_execute.call_args[0][0]
        self.assertIn('true', call_args)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_write')
    def test_create_with_is_active_false(self, mock_execute):
        """Test create with is_active=False"""
        mock_execute.return_value = True

        field_data = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type',
            'field_value': 'EQUITY',
            'is_active': False,
            'created_by': 'admin'
        }

        result = self.repository.create(field_data)

        self.assertTrue(result)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_write')
    def test_create_with_numeric_values(self, mock_execute):
        """Test create handles numeric values"""
        mock_execute.return_value = True

        field_data = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type',
            'field_value': 'EQUITY',
            'created_by': 'admin',
            'created_at': 1234567890
        }

        result = self.repository.create(field_data)

        self.assertTrue(result)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_write')
    def test_create_failure(self, mock_execute):
        """Test create returns False on failure"""
        mock_execute.return_value = False

        field_data = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type',
            'field_value': 'EQUITY',
            'created_by': 'admin'
        }

        result = self.repository.create(field_data)

        self.assertFalse(result)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_write')
    def test_create_exception(self, mock_execute):
        """Test create handles exception"""
        mock_execute.side_effect = Exception("Database error")

        field_data = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type',
            'field_value': 'EQUITY',
            'created_by': 'admin'
        }

        result = self.repository.create(field_data)

        self.assertFalse(result)


class UDFFieldRepositoryUpdateTestCase(TestCase):
    """Test cases for update method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_write')
    def test_update_success(self, mock_execute):
        """Test successful field update"""
        mock_execute.return_value = True

        field_data = {
            'is_active': True,
            'updated_by': 'admin',
            'created_by': 'admin',
            'created_at': 1234567890
        }

        result = self.repository.update('TRADE', 'Fund Type', 'EQUITY', field_data)

        self.assertTrue(result)
        mock_execute.assert_called_once()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_write')
    def test_update_with_empty_field_value(self, mock_execute):
        """Test update with empty field_value"""
        mock_execute.return_value = True

        field_data = {
            'is_active': True,
            'updated_by': 'admin',
            'created_by': 'admin'
        }

        result = self.repository.update('TRADE', 'Fund Type', '', field_data)

        self.assertTrue(result)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_write')
    def test_update_failure(self, mock_execute):
        """Test update returns False on failure"""
        mock_execute.return_value = False

        field_data = {'updated_by': 'admin', 'created_by': 'admin'}

        result = self.repository.update('TRADE', 'Fund Type', 'EQUITY', field_data)

        self.assertFalse(result)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_write')
    def test_update_exception(self, mock_execute):
        """Test update handles exception"""
        mock_execute.side_effect = Exception("Database error")

        field_data = {'updated_by': 'admin', 'created_by': 'admin'}

        result = self.repository.update('TRADE', 'Fund Type', 'EQUITY', field_data)

        self.assertFalse(result)


class UDFFieldRepositorySoftDeleteTestCase(TestCase):
    """Test cases for soft_delete method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch.object(UDFFieldRepository, 'create')
    @patch.object(UDFFieldRepository, 'get_by_key')
    def test_soft_delete_success(self, mock_get, mock_create):
        """Test successful soft delete"""
        mock_get.return_value = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type',
            'field_value': 'EQUITY',
            'is_active': True,
            'created_by': 'admin',
            'created_at': 1234567890
        }
        mock_create.return_value = True

        result = self.repository.soft_delete('TRADE', 'Fund Type', 'EQUITY', 'admin')

        self.assertTrue(result)
        mock_create.assert_called_once()
        # Verify is_active is set to False
        call_args = mock_create.call_args[0][0]
        self.assertFalse(call_args['is_active'])

    @patch.object(UDFFieldRepository, 'get_by_key')
    def test_soft_delete_not_found(self, mock_get):
        """Test soft delete when record not found"""
        mock_get.return_value = None

        result = self.repository.soft_delete('TRADE', 'Unknown', 'Value', 'admin')

        self.assertFalse(result)

    @patch.object(UDFFieldRepository, 'create')
    @patch.object(UDFFieldRepository, 'get_by_key')
    def test_soft_delete_failure(self, mock_get, mock_create):
        """Test soft delete when create fails"""
        mock_get.return_value = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type',
            'field_value': 'EQUITY',
            'is_active': True,
            'created_by': 'admin',
            'created_at': 1234567890
        }
        mock_create.return_value = False

        result = self.repository.soft_delete('TRADE', 'Fund Type', 'EQUITY', 'admin')

        self.assertFalse(result)

    @patch.object(UDFFieldRepository, 'get_by_key')
    def test_soft_delete_exception(self, mock_get):
        """Test soft delete handles exception"""
        mock_get.side_effect = Exception("Database error")

        result = self.repository.soft_delete('TRADE', 'Fund Type', 'EQUITY', 'admin')

        self.assertFalse(result)


class UDFFieldRepositoryRestoreTestCase(TestCase):
    """Test cases for restore method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch.object(UDFFieldRepository, 'create')
    @patch.object(UDFFieldRepository, 'get_by_key')
    def test_restore_success(self, mock_get, mock_create):
        """Test successful restore"""
        mock_get.return_value = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type',
            'field_value': 'EQUITY',
            'is_active': False,
            'created_by': 'admin',
            'created_at': 1234567890
        }
        mock_create.return_value = True

        result = self.repository.restore('TRADE', 'Fund Type', 'EQUITY', 'admin')

        self.assertTrue(result)
        mock_create.assert_called_once()
        # Verify is_active is set to True
        call_args = mock_create.call_args[0][0]
        self.assertTrue(call_args['is_active'])

    @patch.object(UDFFieldRepository, 'get_by_key')
    def test_restore_not_found(self, mock_get):
        """Test restore when record not found"""
        mock_get.return_value = None

        result = self.repository.restore('TRADE', 'Unknown', 'Value', 'admin')

        self.assertFalse(result)

    @patch.object(UDFFieldRepository, 'create')
    @patch.object(UDFFieldRepository, 'get_by_key')
    def test_restore_failure(self, mock_get, mock_create):
        """Test restore when create fails"""
        mock_get.return_value = {
            'object_type': 'TRADE',
            'field_name': 'Fund Type',
            'field_value': 'EQUITY',
            'is_active': False,
            'created_by': 'admin',
            'created_at': 1234567890
        }
        mock_create.return_value = False

        result = self.repository.restore('TRADE', 'Fund Type', 'EQUITY', 'admin')

        self.assertFalse(result)

    @patch.object(UDFFieldRepository, 'get_by_key')
    def test_restore_exception(self, mock_get):
        """Test restore handles exception"""
        mock_get.side_effect = Exception("Database error")

        result = self.repository.restore('TRADE', 'Fund Type', 'EQUITY', 'admin')

        self.assertFalse(result)


class UDFFieldRepositoryGetStatsByEntityTestCase(TestCase):
    """Test cases for get_stats_by_entity method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_stats_by_entity_success(self, mock_execute):
        """Test successful stats retrieval"""
        mock_execute.return_value = [
            {'object_type': 'TRADE', 'total_fields': 10, 'active_fields': 8, 'inactive_fields': 2},
            {'object_type': 'PORTFOLIO', 'total_fields': 5, 'active_fields': 5, 'inactive_fields': 0}
        ]

        result = self.repository.get_stats_by_entity()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['total_fields'], 10)

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_stats_by_entity_empty(self, mock_execute):
        """Test get_stats_by_entity with no results"""
        mock_execute.return_value = []

        result = self.repository.get_stats_by_entity()

        self.assertEqual(result, [])

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_stats_by_entity_none(self, mock_execute):
        """Test get_stats_by_entity with None result"""
        mock_execute.return_value = None

        result = self.repository.get_stats_by_entity()

        self.assertEqual(result, [])

    @patch('udf.repositories.udf_field_repository.impala_manager.execute_query')
    def test_get_stats_by_entity_exception(self, mock_execute):
        """Test get_stats_by_entity raises exception"""
        mock_execute.side_effect = Exception("Database error")

        with self.assertRaises(Exception):
            self.repository.get_stats_by_entity()


class UDFFieldRepositoryAddFieldDefinitionTestCase(TestCase):
    """Test cases for add_field_definition helper method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch.object(UDFFieldRepository, 'create')
    def test_add_field_definition_success(self, mock_create):
        """Test successful field definition creation"""
        mock_create.return_value = True

        result = self.repository.add_field_definition('TRADE', 'Fund Type', 'admin')

        self.assertTrue(result)
        mock_create.assert_called_once()
        call_args = mock_create.call_args[0][0]
        self.assertEqual(call_args['field_value'], '')
        self.assertEqual(call_args['object_type'], 'TRADE')

    @patch.object(UDFFieldRepository, 'create')
    def test_add_field_definition_failure(self, mock_create):
        """Test field definition creation failure"""
        mock_create.return_value = False

        result = self.repository.add_field_definition('TRADE', 'Fund Type', 'admin')

        self.assertFalse(result)


class UDFFieldRepositoryAddFieldValueTestCase(TestCase):
    """Test cases for add_field_value helper method"""

    def setUp(self):
        """Set up test repository"""
        self.repository = UDFFieldRepository()

    @patch.object(UDFFieldRepository, 'create')
    def test_add_field_value_success(self, mock_create):
        """Test successful field value creation"""
        mock_create.return_value = True

        result = self.repository.add_field_value('TRADE', 'Fund Type', 'EQUITY', 'admin')

        self.assertTrue(result)
        mock_create.assert_called_once()
        call_args = mock_create.call_args[0][0]
        self.assertEqual(call_args['field_value'], 'EQUITY')

    def test_add_field_value_empty_raises_error(self):
        """Test add_field_value raises error for empty value"""
        with self.assertRaises(ValueError):
            self.repository.add_field_value('TRADE', 'Fund Type', '', 'admin')

    def test_add_field_value_none_raises_error(self):
        """Test add_field_value raises error for None value"""
        with self.assertRaises(ValueError):
            self.repository.add_field_value('TRADE', 'Fund Type', None, 'admin')


class UDFFieldRepositoryConstantsTestCase(TestCase):
    """Test cases for repository constants"""

    def test_database_constant(self):
        """Test DATABASE constant"""
        self.assertEqual(UDFFieldRepository.DATABASE, 'gmp_cis')

    def test_table_name_constant(self):
        """Test TABLE_NAME constant"""
        self.assertEqual(UDFFieldRepository.TABLE_NAME, 'cis_udf_field')


class UDFFieldRepositorySingletonTestCase(TestCase):
    """Test cases for singleton instance"""

    def test_singleton_instance_exists(self):
        """Test singleton instance is available"""
        self.assertIsNotNone(udf_field_repository)
        self.assertIsInstance(udf_field_repository, UDFFieldRepository)

    def test_singleton_implements_interface(self):
        """Test singleton implements interface"""
        self.assertIsInstance(udf_field_repository, UDFFieldRepositoryInterface)
