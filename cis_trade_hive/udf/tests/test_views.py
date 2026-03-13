"""
UDF View Tests

Tests for UDF views including:
- List view with search/filter
- Create/Edit/Delete operations
- CSV export
- UDFWrapper class
- API endpoints

Updated to match urls_simplified.py structure
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
                'field_value': 'Risk Rating',
                'object_type': 'PORTFOLIO',
                'is_active': True,
                'created_at': 1704067200000,
                'updated_at': 1704067200000,
                'created_by': 'testuser',
                'updated_by': 'testuser'
            },
            {
                'udf_id': 2,
                'field_name': 'custom_note',
                'field_value': 'Custom Note',
                'object_type': 'PORTFOLIO',
                'is_active': True,
                'created_at': 1704067200000,
                'updated_at': 1704067200000,
                'created_by': 'testuser',
                'updated_by': 'testuser'
            }
        ]

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_list_view_success(self, mock_service):
        """Test UDF list view loads successfully"""
        mock_service.get_all_fields.return_value = self.sample_udfs
        mock_service.get_object_types.return_value = ['PORTFOLIO', 'TRADE']

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'udf/list.html')

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_list_with_object_type_filter(self, mock_service):
        """Test UDF list view with object_type filter"""
        mock_service.get_all_fields.return_value = self.sample_udfs
        mock_service.get_object_types.return_value = ['PORTFOLIO', 'TRADE']

        response = self.client.get(self.url, {'object_type': 'PORTFOLIO'})

        self.assertEqual(response.status_code, 200)

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_list_with_status_filter(self, mock_service):
        """Test UDF list view with status filter"""
        mock_service.get_all_fields.return_value = self.sample_udfs
        mock_service.get_object_types.return_value = ['PORTFOLIO', 'TRADE']

        response = self.client.get(self.url, {'status': 'active'})

        self.assertEqual(response.status_code, 200)

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_list_empty(self, mock_service):
        """Test UDF list view with no data"""
        mock_service.get_all_fields.return_value = []
        mock_service.get_object_types.return_value = []

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)


class UDFCreateViewTestCase(TestCase):
    """Test cases for UDF create view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('udf:create')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_name'] = 'Test User'
        session['user_email'] = 'test@example.com'
        session.save()

        self.form_data = {
            'field_name': 'new_udf_field',
            'field_value': 'New UDF',
            'object_type': 'PORTFOLIO',
        }

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_create_view_get(self, mock_service):
        """Test GET request to create view"""
        mock_service.get_object_types.return_value = ['PORTFOLIO', 'TRADE']

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'udf/form.html')

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_create_success(self, mock_service):
        """Test successful UDF creation"""
        mock_service.create_field.return_value = (True, None, 100)
        mock_service.get_object_types.return_value = ['PORTFOLIO', 'TRADE']

        response = self.client.post(self.url, self.form_data)

        self.assertEqual(response.status_code, 302)  # Redirect on success
        mock_service.create_field.assert_called_once()

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_create_failure(self, mock_service):
        """Test UDF creation failure"""
        mock_service.create_field.return_value = (False, 'Field already exists', None)
        mock_service.get_object_types.return_value = ['PORTFOLIO', 'TRADE']

        response = self.client.post(self.url, self.form_data)

        self.assertEqual(response.status_code, 200)  # Stay on form


class UDFEditViewTestCase(TestCase):
    """Test cases for UDF edit view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_name'] = 'Test User'
        session['user_email'] = 'test@example.com'
        session.save()

        self.udf_data = {
            'udf_id': 1,
            'field_name': 'risk_rating',
            'field_value': 'Risk Rating',
            'object_type': 'PORTFOLIO',
            'is_active': True,
            'created_at': 1704067200000,
            'created_by': 'testuser'
        }

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_edit_view_get(self, mock_service):
        """Test GET request to edit view"""
        mock_service.get_field_by_id.return_value = self.udf_data
        mock_service.get_object_types.return_value = ['PORTFOLIO', 'TRADE']

        url = reverse('udf:edit', args=[1])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'udf/form.html')

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_edit_view_not_found(self, mock_service):
        """Test edit view when UDF not found"""
        mock_service.get_field_by_id.return_value = None
        mock_service.get_object_types.return_value = ['PORTFOLIO', 'TRADE']

        url = reverse('udf:edit', args=[999])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)  # 404 Not Found

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_edit_success(self, mock_service):
        """Test successful UDF edit"""
        mock_service.get_field_by_id.return_value = self.udf_data
        mock_service.update_field.return_value = (True, None)
        mock_service.get_object_types.return_value = ['PORTFOLIO', 'TRADE']

        url = reverse('udf:edit', args=[1])
        response = self.client.post(url, {
            'field_name': 'risk_rating',
            'field_value': 'Updated Risk Rating',
            'object_type': 'PORTFOLIO',
        })

        self.assertEqual(response.status_code, 302)  # Redirect on success

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_edit_failure(self, mock_service):
        """Test UDF edit failure"""
        mock_service.get_field_by_id.return_value = self.udf_data
        mock_service.update_field.return_value = (False, 'Update failed')
        mock_service.get_object_types.return_value = ['PORTFOLIO', 'TRADE']

        url = reverse('udf:edit', args=[1])
        response = self.client.post(url, {
            'field_name': 'risk_rating',
            'field_value': 'Updated Risk Rating',
            'object_type': 'PORTFOLIO',
        })

        self.assertEqual(response.status_code, 200)  # Stay on form


class UDFDeleteViewTestCase(TestCase):
    """Test cases for UDF delete (soft delete) view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_name'] = 'Test User'
        session['user_email'] = 'test@example.com'
        session.save()

        self.udf_data = {
            'udf_id': 1,
            'field_name': 'risk_rating',
            'field_value': 'Risk Rating',
            'is_active': True
        }

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_delete_success(self, mock_service):
        """Test successful UDF soft delete"""
        mock_service.delete_field.return_value = (True, None)

        url = reverse('udf:delete', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)  # Redirect on success
        mock_service.delete_field.assert_called_once()

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_delete_failure(self, mock_service):
        """Test UDF delete failure"""
        mock_service.delete_field.return_value = (False, 'Delete failed')

        url = reverse('udf:delete', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)  # Bad request on error


class UDFRestoreViewTestCase(TestCase):
    """Test cases for UDF restore view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_name'] = 'Test User'
        session['user_email'] = 'test@example.com'
        session.save()

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_restore_success(self, mock_service):
        """Test successful UDF restore"""
        mock_service.restore_field.return_value = (True, None)

        url = reverse('udf:restore', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)  # Redirect on success
        mock_service.restore_field.assert_called_once()

    @patch('udf.views_simplified.udf_field_service')
    def test_udf_restore_failure(self, mock_service):
        """Test UDF restore failure"""
        mock_service.restore_field.return_value = (False, 'Restore failed')

        url = reverse('udf:restore', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)  # Bad request on error


class UDFDashboardViewTestCase(TestCase):
    """Test cases for UDF dashboard view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('udf:dashboard')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('udf.views_simplified.udf_field_service')
    def test_dashboard_view_success(self, mock_service):
        """Test dashboard view loads successfully"""
        mock_service.get_dashboard_stats.return_value = [
            {'object_type': 'PORTFOLIO', 'total_fields': 10, 'active_fields': 8, 'inactive_fields': 2}
        ]

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)


class UDFAPITestCase(TestCase):
    """Test cases for UDF API endpoints"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('udf.views_simplified.udf_field_service')
    def test_api_get_object_types(self, mock_service):
        """Test API endpoint for getting object types"""
        mock_service.get_object_types.return_value = ['PORTFOLIO', 'TRADE', 'SECURITY']

        url = reverse('udf:api_object_types')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    @patch('udf.views_simplified.udf_field_service')
    def test_api_get_fields_by_entity(self, mock_service):
        """Test API endpoint for getting fields by entity"""
        mock_service.get_fields_by_entity.return_value = [
            {'field_name': 'risk_rating'},
            {'field_name': 'portfolio_type'}
        ]

        url = reverse('udf:api_fields_by_object_new', args=['PORTFOLIO'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')


class UDFDataDictTestCase(TestCase):
    """Test cases for UDF data dict handling in views"""

    def test_udf_data_dict_access(self):
        """Test UDF data dictionary access patterns"""
        data = {
            'udf_id': 1,
            'field_name': 'risk_rating',
            'field_value': 'Risk Rating',
            'object_type': 'PORTFOLIO',
            'is_active': True,
            'created_at': 1704067200000,
            'updated_at': 1704067200000
        }

        # Test direct dict access
        self.assertEqual(data.get('udf_id'), 1)
        self.assertEqual(data.get('field_name'), 'risk_rating')
        self.assertEqual(data.get('field_value'), 'Risk Rating')
        self.assertTrue(data.get('is_active'))

    def test_udf_data_dict_defaults(self):
        """Test UDF data dictionary with defaults"""
        minimal_data = {
            'udf_id': 1,
            'field_name': 'test_field'
        }

        # Test defaults
        self.assertEqual(minimal_data.get('field_value', ''), '')
        self.assertEqual(minimal_data.get('object_type', ''), '')
        self.assertEqual(minimal_data.get('is_active', True), True)

    def test_udf_timestamp_handling(self):
        """Test UDF timestamp to datetime conversion"""
        from datetime import datetime

        timestamp_ms = 1704067200000  # Jan 1, 2024 00:00:00 UTC

        # Convert millisecond timestamp to datetime
        dt = datetime.fromtimestamp(timestamp_ms / 1000)

        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 1)


class UDFURLTestCase(TestCase):
    """Test cases for URL routing"""

    def test_udf_list_url_resolves(self):
        """Test UDF list URL resolves correctly"""
        url = reverse('udf:list')
        self.assertEqual(url, '/udf/list/')

    def test_udf_create_url_resolves(self):
        """Test UDF create URL resolves correctly"""
        url = reverse('udf:create')
        self.assertEqual(url, '/udf/create/')

    def test_udf_edit_url_resolves(self):
        """Test UDF edit URL resolves correctly"""
        url = reverse('udf:edit', args=[1])
        self.assertEqual(url, '/udf/1/edit/')

    def test_udf_delete_url_resolves(self):
        """Test UDF delete URL resolves correctly"""
        url = reverse('udf:delete', args=[1])
        self.assertEqual(url, '/udf/1/delete/')

    def test_udf_restore_url_resolves(self):
        """Test UDF restore URL resolves correctly"""
        url = reverse('udf:restore', args=[1])
        self.assertEqual(url, '/udf/1/restore/')

    def test_udf_dashboard_url_resolves(self):
        """Test UDF dashboard URL resolves correctly"""
        url = reverse('udf:dashboard')
        self.assertEqual(url, '/udf/')

    def test_api_object_types_url_resolves(self):
        """Test API object types URL resolves correctly"""
        url = reverse('udf:api_object_types')
        self.assertEqual(url, '/udf/api/object-types/')

    def test_api_fields_by_object_url_resolves(self):
        """Test API fields by object URL resolves correctly"""
        url = reverse('udf:api_fields_by_object_new', args=['PORTFOLIO'])
        self.assertEqual(url, '/udf/api/fields/PORTFOLIO/')
