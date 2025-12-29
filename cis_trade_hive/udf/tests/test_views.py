"""
UDF View Tests

Tests for UDF views including:
- List view with search/filter
- Detail view
- Create/Edit/Delete operations
- CSV export
- UDFWrapper class
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, Mock, MagicMock


class UDFListViewTestCase(TestCase):
    """Test cases for UDF list view"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()
        self.url = reverse('udf:list')

        # Set up session
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_name'] = 'Test User'
        session['user_email'] = 'test@example.com'
        session.save()

        # Sample UDF data
        self.sample_udfs = [
            {
                'udf_id': 1,
                'field_name': 'risk_rating',
                'label': 'Risk Rating',
                'description': 'Portfolio risk rating',
                'field_type': 'DROPDOWN',
                'entity_type': 'PORTFOLIO',
                'is_required': True,
                'is_active': True,
                'display_order': 1,
                'dropdown_options': 'Low,Medium,High',
                'created_at': '2025-12-27 10:00:00',
                'updated_at': '2025-12-27 10:00:00',
                'created_by': 'testuser',
                'updated_by': 'testuser'
            },
            {
                'udf_id': 2,
                'field_name': 'custom_note',
                'label': 'Custom Note',
                'description': 'Custom notes',
                'field_type': 'TEXT',
                'entity_type': 'PORTFOLIO',
                'is_required': False,
                'is_active': True,
                'display_order': 2,
                'max_length': 500,
                'created_at': '2025-12-27 10:00:00',
                'updated_at': '2025-12-27 10:00:00',
                'created_by': 'testuser',
                'updated_by': 'testuser'
            }
        ]

    @patch('udf.views.audit_log_kudu_repository.log_action')
    @patch('udf.views.udf_definition_repository.get_all_definitions')
    def test_udf_list_view_success(self, mock_get_all, mock_audit):
        """Test UDF list view loads successfully"""
        mock_get_all.return_value = self.sample_udfs

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'udf/udf_list.html')
        self.assertIn('page_obj', response.context)

        # Verify audit log was called
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'VIEW')
        self.assertEqual(call_kwargs['entity_type'], 'UDF')

    @patch('udf.views.audit_log_kudu_repository.log_action')
    @patch('udf.views.udf_definition_repository.get_all_definitions')
    def test_udf_list_search(self, mock_get_all, mock_audit):
        """Test UDF search functionality"""
        mock_get_all.return_value = [self.sample_udfs[0]]

        response = self.client.get(self.url, {'search': 'risk'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('search', response.context)

    @patch('udf.views.audit_log_kudu_repository.log_action')
    @patch('udf.views.udf_definition_repository.get_all_definitions')
    def test_udf_list_entity_type_filter(self, mock_get_all, mock_audit):
        """Test filtering by entity type"""
        mock_get_all.return_value = self.sample_udfs

        response = self.client.get(self.url, {'entity_type': 'PORTFOLIO'})

        self.assertEqual(response.status_code, 200)

    @patch('udf.views.audit_log_kudu_repository.log_action')
    @patch('udf.views.udf_definition_repository.get_all_definitions')
    def test_udf_csv_export(self, mock_get_all, mock_audit):
        """Test CSV export functionality"""
        mock_get_all.return_value = self.sample_udfs

        response = self.client.get(self.url, {'export': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])

        # Check CSV content
        content = response.content.decode('utf-8')
        self.assertIn('risk_rating', content)
        self.assertIn('custom_note', content)

        # Verify export was logged (only EXPORT, no VIEW)
        self.assertEqual(mock_audit.call_count, 1)  # EXPORT only
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'EXPORT')


class UDFDetailViewTestCase(TestCase):
    """Test cases for UDF detail view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.udf_data = {
            'udf_id': 1,
            'field_name': 'risk_rating',
            'label': 'Risk Rating',
            'description': 'Portfolio risk rating',
            'field_type': 'DROPDOWN',
            'entity_type': 'PORTFOLIO',
            'is_required': True,
            'is_active': True,
            'dropdown_options': 'Low,Medium,High',
            'created_at': '2025-12-27 10:00:00',
            'updated_at': '2025-12-27 10:00:00',
            'created_by': 'testuser',
            'updated_by': 'testuser'
        }

    @patch('udf.views.audit_log_kudu_repository.log_action')
    @patch('udf.views.udf_definition_repository.get_definition_by_name')
    def test_udf_detail_view_success(self, mock_get_udf, mock_audit):
        """Test UDF detail view loads successfully"""
        mock_get_udf.return_value = self.udf_data

        url = reverse('udf:detail', args=['risk_rating'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'udf/udf_detail.html')
        self.assertIn('udf', response.context)

        # Verify correct UDF was retrieved
        mock_get_udf.assert_called_once_with('risk_rating')

    @patch('udf.views.audit_log_kudu_repository.log_action')
    @patch('udf.views.udf_definition_repository.get_definition_by_name')
    def test_udf_detail_not_found(self, mock_get_udf, mock_audit):
        """Test detail view with non-existent UDF"""
        mock_get_udf.return_value = None

        url = reverse('udf:detail', args=['nonexistent'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)


class UDFCreateViewTestCase(TestCase):
    """Test cases for UDF create view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('udf:create')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.form_data = {
            'field_name': 'new_udf_field',
            'label': 'New UDF',
            'description': 'Test UDF',
            'field_type': 'TEXT',
            'entity_type': 'PORTFOLIO',
            'is_required': False,
            'is_active': True,
            'display_order': 10,
            'max_length': 255
        }

    def test_udf_create_view_get(self):
        """Test GET request to create view"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'udf/udf_form.html')
        self.assertIn('field_type_choices', response.context)
        self.assertIn('entity_type_choices', response.context)

    @patch('udf.views.audit_log_kudu_repository.log_action')
    @patch('udf.views.udf_definition_repository.insert_definition')
    def test_udf_create_success(self, mock_insert, mock_audit):
        """Test successful UDF creation"""
        mock_insert.return_value = True

        response = self.client.post(self.url, self.form_data)

        self.assertEqual(response.status_code, 302)
        mock_insert.assert_called_once()

        # Verify audit log
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'CREATE')
        self.assertEqual(call_kwargs['entity_type'], 'UDF')

    @patch('udf.views.udf_definition_repository.insert_definition')
    def test_udf_create_duplicate_field_name(self, mock_insert):
        """Test creating UDF with duplicate field name"""
        mock_insert.return_value = False

        response = self.client.post(self.url, self.form_data)

        # Should show error message
        self.assertEqual(response.status_code, 200)
        # Check for error in messages or context


class UDFEditViewTestCase(TestCase):
    """Test cases for UDF edit view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.udf_data = {
            'udf_id': 1,
            'field_name': 'risk_rating',
            'label': 'Risk Rating',
            'description': 'Portfolio risk rating',
            'field_type': 'DROPDOWN',
            'entity_type': 'PORTFOLIO',
            'is_required': True,
            'is_active': True,
            'dropdown_options': 'Low,Medium,High',
            'created_at': '2025-12-27 10:00:00',
            'created_by': 'testuser'
        }

    @patch('udf.views.udf_definition_repository.get_definition_by_name')
    def test_udf_edit_view_get(self, mock_get_udf):
        """Test GET request to edit view"""
        mock_get_udf.return_value = self.udf_data

        url = reverse('udf:edit', args=['risk_rating'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'udf/udf_form.html')
        self.assertIn('udf', response.context)

    @patch('udf.views.audit_log_kudu_repository.log_action')
    @patch('udf.views.udf_definition_repository.update_definition')
    @patch('udf.views.udf_definition_repository.get_definition_by_name')
    def test_udf_edit_success(self, mock_get, mock_update, mock_audit):
        """Test successful UDF edit"""
        mock_get.return_value = self.udf_data
        mock_update.return_value = True

        url = reverse('udf:edit', args=['risk_rating'])
        response = self.client.post(url, {
            'field_name': 'risk_rating',
            'label': 'Updated Risk Rating',
            'description': 'Updated description',
            'field_type': 'DROPDOWN',
            'entity_type': 'PORTFOLIO',
            'is_required': True,
            'is_active': True,
            'dropdown_options': 'Low,Medium,High,Critical',
            'display_order': 1
        })

        self.assertEqual(response.status_code, 302)
        mock_update.assert_called_once()

        # Verify audit log
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'UPDATE')


class UDFDeleteViewTestCase(TestCase):
    """Test cases for UDF delete (soft delete) view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.udf_data = {
            'udf_id': 1,
            'field_name': 'risk_rating',
            'label': 'Risk Rating',
            'is_active': True
        }

    @patch('udf.views.audit_log_kudu_repository.log_action')
    @patch('udf.views.udf_definition_repository.delete_definition')
    @patch('udf.views.udf_definition_repository.get_definition_by_name')
    def test_udf_delete_success(self, mock_get, mock_delete, mock_audit):
        """Test successful UDF soft delete"""
        mock_get.return_value = self.udf_data
        mock_delete.return_value = True

        url = reverse('udf:delete', args=['risk_rating'])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        mock_delete.assert_called_once_with(1)

        # Verify audit log
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'DELETE')


class UDFWrapperTestCase(TestCase):
    """Test cases for UDFWrapper class"""

    def test_wrapper_initialization(self):
        """Test UDFWrapper initialization"""
        from udf.views import UDFWrapper

        data = {
            'udf_id': 1,
            'field_name': 'risk_rating',
            'label': 'Risk Rating',
            'description': 'Portfolio risk rating',
            'field_type': 'DROPDOWN',
            'entity_type': 'PORTFOLIO',
            'is_required': True,
            'is_active': True,
            'dropdown_options': 'Low,Medium,High',
            'created_at': '2025-12-27 10:00:00',
            'updated_at': '2025-12-27 10:00:00'
        }

        wrapper = UDFWrapper(data, index=0)

        self.assertEqual(wrapper.udf_id, 1)
        self.assertEqual(wrapper.field_name, 'risk_rating')
        self.assertEqual(wrapper.field_type, 'DROPDOWN')
        self.assertTrue(wrapper.is_required)
        self.assertTrue(wrapper.is_active)

    def test_wrapper_get_field_type_display(self):
        """Test get_field_type_display method"""
        from udf.views import UDFWrapper

        data = {'field_name': 'test', 'field_type': 'DROPDOWN', 'udf_id': 1}
        wrapper = UDFWrapper(data)

        self.assertEqual(wrapper.get_field_type_display(), 'Dropdown')

    def test_wrapper_get_entity_type_display(self):
        """Test get_entity_type_display method"""
        from udf.views import UDFWrapper

        data = {'field_name': 'test', 'entity_type': 'PORTFOLIO', 'udf_id': 1}
        wrapper = UDFWrapper(data)

        self.assertEqual(wrapper.get_entity_type_display(), 'Portfolio')

    def test_wrapper_dropdown_options_property(self):
        """Test dropdown_options property stores value as-is"""
        from udf.views import UDFWrapper

        # Test with string value
        data = {
            'field_name': 'test',
            'dropdown_options': 'Low,Medium,High',
            'udf_id': 1
        }
        wrapper = UDFWrapper(data)

        options = wrapper.dropdown_options
        self.assertIsInstance(options, str)
        self.assertEqual(options, 'Low,Medium,High')

    def test_wrapper_missing_fields(self):
        """Test UDFWrapper handles missing fields"""
        from udf.views import UDFWrapper

        minimal_data = {
            'udf_id': 1,
            'field_name': 'test_field'
        }

        wrapper = UDFWrapper(minimal_data, index=0)

        self.assertEqual(wrapper.field_name, 'test_field')
        # Missing fields should default to empty strings or defaults
        self.assertEqual(wrapper.label, '')
        self.assertEqual(wrapper.description, '')
        self.assertIsNone(wrapper.min_value)


class UDFURLTestCase(TestCase):
    """Test cases for URL routing"""

    def test_udf_list_url_resolves(self):
        """Test UDF list URL resolves correctly"""
        url = reverse('udf:list')
        self.assertEqual(url, '/udf/')

    def test_udf_detail_url_resolves(self):
        """Test UDF detail URL resolves correctly"""
        url = reverse('udf:detail', args=['risk_rating'])
        self.assertEqual(url, '/udf/risk_rating/')

    def test_udf_create_url_resolves(self):
        """Test UDF create URL resolves correctly"""
        url = reverse('udf:create')
        self.assertEqual(url, '/udf/create/')

    def test_udf_edit_url_resolves(self):
        """Test UDF edit URL resolves correctly"""
        url = reverse('udf:edit', args=['risk_rating'])
        self.assertEqual(url, '/udf/risk_rating/edit/')

    def test_udf_delete_url_resolves(self):
        """Test UDF delete URL resolves correctly"""
        url = reverse('udf:delete', args=['risk_rating'])
        self.assertEqual(url, '/udf/risk_rating/delete/')
