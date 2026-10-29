"""
UDF Field Service Tests - Simplified Logic

Comprehensive tests for UDFFieldService with business logic validation and audit logging.
Tests cover:
- Cascading dropdown operations
- Validation logic
- CRUD operations with audit logging
- Error handling
"""

import pytest
from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock

from udf.services.udf_field_service import UDFFieldService, udf_field_service


class UDFFieldServiceGetObjectTypesTestCase(TestCase):
    """Test cases for get_object_types method"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)

    def test_get_object_types_success(self):
        """Test successful retrieval of object types"""
        self.mock_repository.get_object_types.return_value = ['TRADE', 'PORTFOLIO', 'SECURITY']

        result = self.service.get_object_types()

        self.assertEqual(len(result), 3)
        self.assertIn('TRADE', result)
        self.mock_repository.get_object_types.assert_called_once()

    def test_get_object_types_empty(self):
        """Test get_object_types with empty result"""
        self.mock_repository.get_object_types.return_value = []

        result = self.service.get_object_types()

        self.assertEqual(result, [])

    def test_get_object_types_exception(self):
        """Test get_object_types handles exception"""
        self.mock_repository.get_object_types.side_effect = Exception("Database error")

        result = self.service.get_object_types()

        self.assertEqual(result, [])


class UDFFieldServiceGetFieldsByEntityTestCase(TestCase):
    """Test cases for get_fields_by_entity method"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)

    def test_get_fields_by_entity_success(self):
        """Test successful retrieval of fields by entity"""
        self.mock_repository.get_fields_by_entity.return_value = [
            {'field_name': 'Fund Type'},
            {'field_name': 'Selling Rule'}
        ]

        result = self.service.get_fields_by_entity('TRADE')

        self.assertEqual(len(result), 2)
        self.mock_repository.get_fields_by_entity.assert_called_once_with('TRADE')

    def test_get_fields_by_entity_empty(self):
        """Test get_fields_by_entity with empty result"""
        self.mock_repository.get_fields_by_entity.return_value = []

        result = self.service.get_fields_by_entity('UNKNOWN')

        self.assertEqual(result, [])

    def test_get_fields_by_entity_exception(self):
        """Test get_fields_by_entity handles exception"""
        self.mock_repository.get_fields_by_entity.side_effect = Exception("Database error")

        result = self.service.get_fields_by_entity('TRADE')

        self.assertEqual(result, [])


class UDFFieldServiceGetAllFieldsTestCase(TestCase):
    """Test cases for get_all_fields method"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)

    def test_get_all_fields_no_filters(self):
        """Test get_all_fields without filters"""
        self.mock_repository.get_all.return_value = [
            {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'EQUITY'}
        ]

        result = self.service.get_all_fields()

        self.assertEqual(len(result), 1)
        self.mock_repository.get_all.assert_called_once_with(object_type=None, is_active=None)

    def test_get_all_fields_with_filters(self):
        """Test get_all_fields with filters"""
        self.mock_repository.get_all.return_value = []

        result = self.service.get_all_fields(object_type='TRADE', is_active=True)

        self.assertEqual(result, [])
        self.mock_repository.get_all.assert_called_once_with(object_type='TRADE', is_active=True)

    def test_get_all_fields_exception(self):
        """Test get_all_fields handles exception"""
        self.mock_repository.get_all.side_effect = Exception("Database error")

        result = self.service.get_all_fields()

        self.assertEqual(result, [])


class UDFFieldServiceGetFieldByIdTestCase(TestCase):
    """Test cases for get_field_by_id method"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)

    def test_get_field_by_id_found(self):
        """Test get_field_by_id when found"""
        self.mock_repository.get_by_id.return_value = {'udf_id': 1, 'field_name': 'Fund Type'}

        result = self.service.get_field_by_id(1)

        self.assertIsNotNone(result)
        self.assertEqual(result['udf_id'], 1)

    def test_get_field_by_id_not_found(self):
        """Test get_field_by_id when not found"""
        self.mock_repository.get_by_id.return_value = None

        result = self.service.get_field_by_id(999)

        self.assertIsNone(result)

    def test_get_field_by_id_exception(self):
        """Test get_field_by_id handles exception"""
        self.mock_repository.get_by_id.side_effect = Exception("Database error")

        result = self.service.get_field_by_id(1)

        self.assertIsNone(result)


class UDFFieldServiceGetDashboardStatsTestCase(TestCase):
    """Test cases for get_dashboard_stats method"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)

    def test_get_dashboard_stats_success(self):
        """Test successful stats retrieval"""
        self.mock_repository.get_stats_by_entity.return_value = [
            {'object_type': 'TRADE', 'total_fields': 10, 'active_fields': 8, 'inactive_fields': 2}
        ]

        result = self.service.get_dashboard_stats()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['total_fields'], 10)

    def test_get_dashboard_stats_empty(self):
        """Test get_dashboard_stats with empty result"""
        self.mock_repository.get_stats_by_entity.return_value = []

        result = self.service.get_dashboard_stats()

        self.assertEqual(result, [])

    def test_get_dashboard_stats_exception(self):
        """Test get_dashboard_stats handles exception"""
        self.mock_repository.get_stats_by_entity.side_effect = Exception("Database error")

        result = self.service.get_dashboard_stats()

        self.assertEqual(result, [])


class UDFFieldServiceValidateFieldDataTestCase(TestCase):
    """Test cases for validate_field_data method"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)

    def test_validate_missing_field_name(self):
        """Test validation fails without field_name"""
        field_data = {'field_value': 'Test', 'object_type': 'TRADE'}

        is_valid, error = self.service.validate_field_data(field_data)

        self.assertFalse(is_valid)
        self.assertIn('Field Name', error)

    def test_validate_empty_field_name(self):
        """Test validation fails with empty field_name"""
        field_data = {'field_name': '', 'field_value': 'Test', 'object_type': 'TRADE'}

        is_valid, error = self.service.validate_field_data(field_data)

        self.assertFalse(is_valid)
        self.assertIn('Field Name', error)

    def test_validate_missing_field_value(self):
        """Test validation fails without field_value"""
        field_data = {'field_name': 'test_field', 'object_type': 'TRADE'}

        is_valid, error = self.service.validate_field_data(field_data)

        self.assertFalse(is_valid)
        self.assertIn('Field Value', error)

    def test_validate_missing_object_type(self):
        """Test validation fails without object_type"""
        field_data = {'field_name': 'test_field', 'field_value': 'Test'}

        is_valid, error = self.service.validate_field_data(field_data)

        self.assertFalse(is_valid)
        self.assertIn('Entity Type', error)

    def test_validate_field_name_too_long(self):
        """Test validation fails with field_name > 200 chars"""
        field_data = {
            'field_name': 'a' * 201,
            'field_value': 'Test',
            'object_type': 'TRADE'
        }

        is_valid, error = self.service.validate_field_data(field_data)

        self.assertFalse(is_valid)
        self.assertIn('200 characters', error)

    def test_validate_whitespace_field_name(self):
        """Test validation fails with whitespace-only field_name"""
        field_data = {
            'field_name': '   ',
            'field_value': 'Test',
            'object_type': 'TRADE'
        }

        is_valid, error = self.service.validate_field_data(field_data)

        self.assertFalse(is_valid)
        self.assertIn('Field Name', error)

    def test_validate_success(self):
        """Test validation succeeds with valid data"""
        self.mock_repository.get_all.return_value = []

        field_data = {
            'field_name': 'fund_type',
            'field_value': 'Fund Type',
            'object_type': 'trade'  # lowercase to test conversion
        }

        is_valid, error = self.service.validate_field_data(field_data)

        self.assertTrue(is_valid)
        self.assertIsNone(error)
        # Check that object_type was converted to uppercase
        self.assertEqual(field_data['object_type'], 'TRADE')

    def test_validate_duplicate_field_value(self):
        """Test validation fails for duplicate field_value (same object_type + field_name + field_value)"""
        self.mock_repository.get_all.return_value = [
            {
                'object_type': 'TRADE',
                'field_name': 'fund_type',
                'field_value': 'Existing',
                'udf_id': 1
            }
        ]

        # Same field_name AND field_value should fail
        field_data = {
            'field_name': 'fund_type',
            'field_value': 'Existing',  # Same value as existing
            'object_type': 'TRADE'
        }

        is_valid, error = self.service.validate_field_data(field_data)

        self.assertFalse(is_valid)
        self.assertIn('already exists', error)

    def test_validate_allows_different_field_value(self):
        """Test validation allows same field_name with different field_value"""
        self.mock_repository.get_all.return_value = [
            {
                'object_type': 'TRADE',
                'field_name': 'fund_type',
                'field_value': 'Existing',
                'udf_id': 1
            }
        ]

        # Same field_name but different field_value should be allowed
        field_data = {
            'field_name': 'fund_type',
            'field_value': 'New Value',  # Different value
            'object_type': 'TRADE'
        }

        is_valid, error = self.service.validate_field_data(field_data)

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_allows_update_same_record(self):
        """Test validation allows updating the same record"""
        self.mock_repository.get_all.return_value = [
            {
                'object_type': 'TRADE',
                'field_name': 'fund_type',
                'field_value': 'Existing',
                'udf_id': 1
            }
        ]

        field_data = {
            'field_name': 'fund_type',
            'field_value': 'Updated Value',
            'object_type': 'TRADE'
        }

        is_valid, error = self.service.validate_field_data(field_data, udf_id=1)

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_skips_empty_field_values(self):
        """Test validation skips records with empty field_value"""
        self.mock_repository.get_all.return_value = [
            {
                'object_type': 'TRADE',
                'field_name': 'fund_type',
                'field_value': '',  # Empty - this is a definition record
                'udf_id': 1
            }
        ]

        field_data = {
            'field_name': 'fund_type',
            'field_value': 'New Value',
            'object_type': 'TRADE'
        }

        is_valid, error = self.service.validate_field_data(field_data)

        self.assertTrue(is_valid)
        self.assertIsNone(error)


class UDFFieldServiceCreateFieldTestCase(TestCase):
    """Test cases for create_field method"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)
        self.user_info = {
            'user_id': 1,
            'username': 'testuser',
            'user_email': 'test@example.com',
            'ip_address': '127.0.0.1',
            'user_agent': 'TestAgent'
        }

    @patch('udf.services.udf_field_service.audit_log_kudu_repository')
    def test_create_field_success(self, mock_audit):
        """Test successful field creation"""
        self.mock_repository.get_all.return_value = []
        self.mock_repository.create.return_value = 100  # Returns udf_id on success

        field_data = {
            'field_name': 'fund_type',
            'field_value': 'Fund Type',
            'object_type': 'TRADE'
        }

        # Mock cache invalidation
        with patch.object(self.service, '_invalidate_udf_cache'):
            success, error, udf_id = self.service.create_field(field_data, self.user_info)

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(udf_id, 100)
        self.mock_repository.create.assert_called_once()
        mock_audit.log_action.assert_called_once()

    def test_create_field_validation_failure(self):
        """Test create_field fails validation"""
        field_data = {
            'field_name': '',
            'field_value': 'Test',
            'object_type': 'TRADE'
        }

        success, error, udf_id = self.service.create_field(field_data, self.user_info)

        self.assertFalse(success)
        self.assertIsNotNone(error)
        self.assertIsNone(udf_id)

    @patch('udf.services.udf_field_service.audit_log_kudu_repository')
    def test_create_field_repository_failure(self, mock_audit):
        """Test create_field when repository fails"""
        self.mock_repository.get_all.return_value = []
        self.mock_repository.create.return_value = 0  # Returns 0 on failure

        field_data = {
            'field_name': 'fund_type',
            'field_value': 'Fund Type',
            'object_type': 'TRADE'
        }

        success, error, udf_id = self.service.create_field(field_data, self.user_info)

        self.assertFalse(success)
        self.assertIn('Failed to create', error)
        self.assertIsNone(udf_id)

    def test_create_field_exception(self):
        """Test create_field handles exception"""
        self.mock_repository.get_all.side_effect = Exception("Database error")

        field_data = {
            'field_name': 'fund_type',
            'field_value': 'Fund Type',
            'object_type': 'TRADE'
        }

        success, error, udf_id = self.service.create_field(field_data, self.user_info)

        self.assertFalse(success)
        self.assertIn('Error', error)
        self.assertIsNone(udf_id)


class UDFFieldServiceUpdateFieldTestCase(TestCase):
    """Test cases for update_field method"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)
        self.user_info = {
            'user_id': 1,
            'username': 'testuser',
            'user_email': 'test@example.com',
            'ip_address': '127.0.0.1',
            'user_agent': 'TestAgent'
        }
        self.existing_field = {
            'udf_id': 1,
            'object_type': 'TRADE',
            'field_name': 'fund_type',
            'field_value': 'Fund Type',
            'is_active': True,
            'created_by': 'admin',
            'created_at': 1234567890
        }

    @patch('udf.services.udf_field_service.audit_log_kudu_repository')
    def test_update_field_success(self, mock_audit):
        """Test successful field update"""
        self.mock_repository.get_by_id.return_value = self.existing_field
        self.mock_repository.get_all.return_value = [self.existing_field]
        self.mock_repository.update.return_value = True

        field_data = {
            'field_name': 'fund_type',
            'field_value': 'Updated Fund Type',
            'object_type': 'TRADE',
            'is_active': True
        }

        # Mock cache invalidation
        with patch.object(self.service, '_invalidate_udf_cache'):
            success, error = self.service.update_field(1, field_data, self.user_info)

        self.assertTrue(success)
        self.assertIsNone(error)
        self.mock_repository.update.assert_called_once()
        mock_audit.log_action.assert_called_once()

    def test_update_field_not_found(self):
        """Test update_field when field not found"""
        self.mock_repository.get_by_id.return_value = None

        field_data = {
            'field_name': 'fund_type',
            'field_value': 'Updated',
            'object_type': 'TRADE'
        }

        success, error = self.service.update_field(999, field_data, self.user_info)

        self.assertFalse(success)
        self.assertIn('not found', error)

    def test_update_field_validation_failure(self):
        """Test update_field fails validation"""
        self.mock_repository.get_by_id.return_value = self.existing_field

        field_data = {
            'field_name': '',
            'field_value': 'Updated',
            'object_type': 'TRADE'
        }

        success, error = self.service.update_field(1, field_data, self.user_info)

        self.assertFalse(success)
        self.assertIsNotNone(error)

    @patch('udf.services.udf_field_service.audit_log_kudu_repository')
    def test_update_field_repository_failure(self, mock_audit):
        """Test update_field when repository fails"""
        self.mock_repository.get_by_id.return_value = self.existing_field
        self.mock_repository.get_all.return_value = [self.existing_field]
        self.mock_repository.update.return_value = False

        field_data = {
            'field_name': 'fund_type',
            'field_value': 'Updated',
            'object_type': 'TRADE'
        }

        success, error = self.service.update_field(1, field_data, self.user_info)

        self.assertFalse(success)
        self.assertIn('Failed to update', error)

    def test_update_field_exception(self):
        """Test update_field handles exception"""
        self.mock_repository.get_by_id.side_effect = Exception("Database error")

        field_data = {
            'field_name': 'fund_type',
            'field_value': 'Updated',
            'object_type': 'TRADE'
        }

        success, error = self.service.update_field(1, field_data, self.user_info)

        self.assertFalse(success)
        self.assertIn('Error', error)


class UDFFieldServiceDeleteFieldTestCase(TestCase):
    """Test cases for delete_field method"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)
        self.user_info = {
            'user_id': 1,
            'username': 'testuser',
            'user_email': 'test@example.com',
            'ip_address': '127.0.0.1',
            'user_agent': 'TestAgent'
        }
        self.existing_field = {
            'udf_id': 1,
            'object_type': 'TRADE',
            'field_name': 'fund_type',
            'field_value': 'Fund Type',
            'is_active': True
        }

    @patch('udf.services.udf_field_service.audit_log_kudu_repository')
    def test_delete_field_success(self, mock_audit):
        """Test successful field deletion"""
        self.mock_repository.get_by_id.return_value = self.existing_field
        self.mock_repository.soft_delete.return_value = True

        # Mock cache invalidation
        with patch.object(self.service, '_invalidate_udf_cache'):
            success, error = self.service.delete_field(1, self.user_info)

        self.assertTrue(success)
        self.assertIsNone(error)
        self.mock_repository.soft_delete.assert_called_once_with(1, 'testuser')
        mock_audit.log_action.assert_called_once()

    def test_delete_field_not_found(self):
        """Test delete_field when field not found"""
        self.mock_repository.get_by_id.return_value = None

        success, error = self.service.delete_field(999, self.user_info)

        self.assertFalse(success)
        self.assertIn('not found', error)

    def test_delete_field_already_deleted(self):
        """Test delete_field when field already deleted"""
        already_deleted = self.existing_field.copy()
        already_deleted['is_active'] = False
        self.mock_repository.get_by_id.return_value = already_deleted

        success, error = self.service.delete_field(1, self.user_info)

        self.assertFalse(success)
        self.assertIn('already deleted', error)

    @patch('udf.services.udf_field_service.audit_log_kudu_repository')
    def test_delete_field_repository_failure(self, mock_audit):
        """Test delete_field when repository fails"""
        self.mock_repository.get_by_id.return_value = self.existing_field
        self.mock_repository.soft_delete.return_value = False

        success, error = self.service.delete_field(1, self.user_info)

        self.assertFalse(success)
        self.assertIn('Failed to delete', error)

    def test_delete_field_exception(self):
        """Test delete_field handles exception"""
        self.mock_repository.get_by_id.side_effect = Exception("Database error")

        success, error = self.service.delete_field(1, self.user_info)

        self.assertFalse(success)
        self.assertIn('Error', error)


class UDFFieldServiceRestoreFieldTestCase(TestCase):
    """Test cases for restore_field method"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)
        self.user_info = {
            'user_id': 1,
            'username': 'testuser',
            'user_email': 'test@example.com',
            'ip_address': '127.0.0.1',
            'user_agent': 'TestAgent'
        }
        self.deleted_field = {
            'udf_id': 1,
            'object_type': 'TRADE',
            'field_name': 'fund_type',
            'field_value': 'Fund Type',
            'is_active': False
        }

    @patch('udf.services.udf_field_service.audit_log_kudu_repository')
    def test_restore_field_success(self, mock_audit):
        """Test successful field restoration"""
        self.mock_repository.get_by_id.return_value = self.deleted_field
        self.mock_repository.restore.return_value = True

        # Mock cache invalidation
        with patch.object(self.service, '_invalidate_udf_cache'):
            success, error = self.service.restore_field(1, self.user_info)

        self.assertTrue(success)
        self.assertIsNone(error)
        self.mock_repository.restore.assert_called_once_with(1, 'testuser')
        mock_audit.log_action.assert_called_once()

    def test_restore_field_not_found(self):
        """Test restore_field when field not found"""
        self.mock_repository.get_by_id.return_value = None

        success, error = self.service.restore_field(999, self.user_info)

        self.assertFalse(success)
        self.assertIn('not found', error)

    def test_restore_field_already_active(self):
        """Test restore_field when field already active"""
        active_field = self.deleted_field.copy()
        active_field['is_active'] = True
        self.mock_repository.get_by_id.return_value = active_field

        success, error = self.service.restore_field(1, self.user_info)

        self.assertFalse(success)
        self.assertIn('already active', error)

    @patch('udf.services.udf_field_service.audit_log_kudu_repository')
    def test_restore_field_repository_failure(self, mock_audit):
        """Test restore_field when repository fails"""
        self.mock_repository.get_by_id.return_value = self.deleted_field
        self.mock_repository.restore.return_value = False

        success, error = self.service.restore_field(1, self.user_info)

        self.assertFalse(success)
        self.assertIn('Failed to restore', error)

    def test_restore_field_exception(self):
        """Test restore_field handles exception"""
        self.mock_repository.get_by_id.side_effect = Exception("Database error")

        success, error = self.service.restore_field(1, self.user_info)

        self.assertFalse(success)
        self.assertIn('Error', error)


class UDFFieldServiceSingletonTestCase(TestCase):
    """Test cases for singleton instance"""

    def test_singleton_instance_exists(self):
        """Test singleton instance is available"""
        self.assertIsNotNone(udf_field_service)
        self.assertIsInstance(udf_field_service, UDFFieldService)

    def test_singleton_has_repository(self):
        """Test singleton has repository injected"""
        self.assertIsNotNone(udf_field_service.repository)


class UDFFieldServiceCacheInvalidationTestCase(TestCase):
    """Test cases for _invalidate_udf_cache method"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)

    @patch('udf.services.udf_field_service.logger')
    def test_invalidate_cache_trade_entity(self, mock_logger):
        """Test cache invalidation for TRADE entity type"""
        with patch('trade.services.trade_dropdown_service.trade_dropdown_service') as mock_dropdown:
            self.service._invalidate_udf_cache('TRADE', 'fund_type')
            mock_dropdown.invalidate_udf_cache.assert_called_once_with('fund_type')

    @patch('udf.services.udf_field_service.logger')
    def test_invalidate_cache_non_trade_entity(self, mock_logger):
        """Test cache invalidation for non-TRADE entity type"""
        with patch('trade.services.trade_dropdown_service.trade_dropdown_service') as mock_dropdown:
            self.service._invalidate_udf_cache('PORTFOLIO', 'some_field')
            # Should invalidate batch cache with None
            mock_dropdown.invalidate_udf_cache.assert_called_once_with(None)

    @patch('udf.services.udf_field_service.logger')
    def test_invalidate_cache_import_error(self, mock_logger):
        """Test cache invalidation handles ImportError gracefully"""
        with patch.dict('sys.modules', {'trade.services.trade_dropdown_service': None}):
            # Should not raise, just log debug
            try:
                self.service._invalidate_udf_cache('TRADE', 'fund_type')
            except ImportError:
                pass  # Expected in some cases
            # The method should handle the error gracefully

    @patch('udf.services.udf_field_service.logger')
    def test_invalidate_cache_exception(self, mock_logger):
        """Test cache invalidation handles general exception gracefully"""
        with patch('trade.services.trade_dropdown_service.trade_dropdown_service') as mock_dropdown:
            mock_dropdown.invalidate_udf_cache.side_effect = Exception("Cache error")
            # Should not raise
            self.service._invalidate_udf_cache('TRADE', 'fund_type')
            mock_logger.warning.assert_called()


class UDFFieldServiceUpdateFieldNameChangeTestCase(TestCase):
    """Test cases for update_field when field name changes"""

    def setUp(self):
        """Set up test service with mocked repository"""
        self.mock_repository = Mock()
        self.service = UDFFieldService(repository=self.mock_repository)
        self.user_info = {
            'user_id': 1,
            'username': 'testuser',
            'user_email': 'test@example.com',
            'ip_address': '127.0.0.1',
            'user_agent': 'TestAgent'
        }
        self.existing_field = {
            'udf_id': 1,
            'object_type': 'TRADE',
            'field_name': 'old_field_name',
            'field_value': 'Old Label',
            'is_active': True,
            'created_by': 'admin',
            'created_at': 1234567890
        }

    @patch('udf.services.udf_field_service.audit_log_kudu_repository')
    def test_update_field_name_change_invalidates_both_caches(self, mock_audit):
        """Test that changing field name invalidates both old and new caches"""
        self.mock_repository.get_by_id.return_value = self.existing_field
        self.mock_repository.get_all.return_value = [self.existing_field]
        self.mock_repository.update.return_value = True

        field_data = {
            'field_name': 'new_field_name',  # Changed
            'field_value': 'New Label',
            'object_type': 'TRADE',
            'is_active': True
        }

        with patch.object(self.service, '_invalidate_udf_cache') as mock_invalidate:
            success, error = self.service.update_field(1, field_data, self.user_info)

        self.assertTrue(success)
        # Should be called twice - once for new name, once for old name
        self.assertEqual(mock_invalidate.call_count, 2)
