"""
UDF Repository Tests

Tests for UDF repository operations.
"""

import pytest
from django.test import TestCase
from unittest.mock import patch, Mock


class UDFRepositoryTestCase(TestCase):
    """Test cases for UDF repositories"""

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_all_definitions(self, mock_execute):
        """Test fetching all UDF definitions"""
        from udf.repositories.udf_hive_repository import udf_definition_repository

        mock_execute.return_value = [
            {'udf_id': 1, 'field_name': 'risk_rating', 'field_type': 'DROPDOWN'},
            {'udf_id': 2, 'field_name': 'custom_note', 'field_type': 'TEXT'}
        ]

        result = udf_definition_repository.get_all_definitions()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['field_name'], 'risk_rating')

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_active_definitions(self, mock_execute):
        """Test fetching active UDF definitions"""
        from udf.repositories.udf_hive_repository import udf_definition_repository

        mock_execute.return_value = [
            {'udf_id': 1, 'field_name': 'risk_rating', 'is_active': True}
        ]

        result = udf_definition_repository.get_active_definitions()

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['is_active'])

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_definition_by_name(self, mock_execute):
        """Test fetching UDF definition by name"""
        from udf.repositories.udf_hive_repository import udf_definition_repository

        mock_execute.return_value = [
            {'udf_id': 1, 'field_name': 'risk_rating', 'field_type': 'DROPDOWN'}
        ]

        result = udf_definition_repository.get_definition_by_name('risk_rating')

        self.assertIsNotNone(result)
        self.assertEqual(result['field_name'], 'risk_rating')

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_insert_definition(self, mock_execute):
        """Test inserting new UDF definition"""
        from udf.repositories.udf_hive_repository import udf_definition_repository

        mock_execute.return_value = True

        udf_data = {
            'field_name': 'new_field',
            'label': 'New Field',
            'field_type': 'TEXT',
            'entity_type': 'PORTFOLIO'
        }

        result = udf_definition_repository.insert_definition(udf_data)

        self.assertTrue(result)
        mock_execute.assert_called_once()

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_update_definition(self, mock_execute):
        """Test updating UDF definition"""
        from udf.repositories.udf_hive_repository import udf_definition_repository

        mock_execute.return_value = True

        udf_data = {
            'label': 'Updated Label',
            'description': 'Updated description'
        }

        result = udf_definition_repository.update_definition(1, udf_data)

        self.assertTrue(result)
        mock_execute.assert_called_once()

    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    def test_delete_definition(self, mock_execute):
        """Test soft deleting UDF definition"""
        from udf.repositories.udf_hive_repository import udf_definition_repository

        mock_execute.return_value = True

        result = udf_definition_repository.delete_definition(1)

        self.assertTrue(result)
        mock_execute.assert_called_once()
