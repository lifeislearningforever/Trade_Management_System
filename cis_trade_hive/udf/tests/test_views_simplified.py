"""
UDF Simplified Views Tests

Comprehensive tests for UDF simplified views including:
- Dashboard view with statistics
- List view with filters
- Create/Edit/Delete operations
- Restore functionality
- API endpoints for cascading dropdowns
- Helper functions
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, Mock, MagicMock


class GetUserInfoFromRequestTestCase(TestCase):
    """Test cases for get_user_info_from_request helper"""

    def test_get_user_info_with_session(self):
        """Test extracting user info from session"""
        from udf.views_simplified import get_user_info_from_request

        mock_request = Mock()
        mock_session = MagicMock()
        mock_session.get.side_effect = lambda key, default='': {
            'user_id': 1,
            'user_login': 'testuser',
            'user_email': 'test@example.com'
        }.get(key, default)
        mock_request.session = mock_session
        mock_request.META = {
            'REMOTE_ADDR': '127.0.0.1',
            'HTTP_USER_AGENT': 'TestAgent'
        }

        result = get_user_info_from_request(mock_request)

        self.assertEqual(result['username'], 'testuser')
        self.assertEqual(result['ip_address'], '127.0.0.1')

    def test_get_user_info_empty_session(self):
        """Test extracting user info from empty session uses defaults"""
        from udf.views_simplified import get_user_info_from_request

        mock_request = Mock()
        mock_session = MagicMock()
        # Simulate missing keys - session.get will use the default
        mock_session.get.side_effect = lambda key, default='': default
        mock_request.session = mock_session
        mock_request.META = {}

        result = get_user_info_from_request(mock_request)

        self.assertEqual(result['username'], 'anonymous')
        self.assertEqual(result['user_id'], 0)
        self.assertEqual(result['ip_address'], '')


class UDFDashboardViewTestCase(TestCase):
    """Test cases for UDF dashboard view"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()
        self.url = reverse('udf:dashboard')

        # Set up session
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_email'] = 'test@example.com'
        session.save()

    @patch('udf.views_simplified.udf_field_service')
    def test_dashboard_success(self, mock_service):
        """Test dashboard loads successfully"""
        mock_service.get_dashboard_stats.return_value = [
            {'object_type': 'TRADE', 'total_fields': 10, 'active_fields': 8, 'inactive_fields': 2}
        ]
        mock_service.get_object_types.return_value = ['TRADE']

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'udf/dashboard.html')
        self.assertIn('stats', response.context)

    @patch('udf.views_simplified.udf_field_service')
    def test_dashboard_with_unmatched_object_types(self, mock_service):
        """Test dashboard handles object types without stats"""
        mock_service.get_dashboard_stats.return_value = []  # No stats
        mock_service.get_object_types.return_value = ['TRADE', 'PORTFOLIO']

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        # Should have default stats for each object type
        stats = response.context['stats']
        self.assertEqual(len(stats), 2)
        self.assertEqual(stats[0]['total_fields'], 0)

    @patch('udf.views_simplified.udf_field_service')
    def test_dashboard_exception(self, mock_service):
        """Test dashboard handles exception"""
        mock_service.get_dashboard_stats.side_effect = Exception("Database error")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 500)
        self.assertIn('Error', response.content.decode())


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
        session.save()

        self.sample_fields = [
            {
                'udf_id': 1,
                'object_type': 'TRADE',
                'field_name': 'Fund Type',
                'field_value': 'EQUITY',
                'is_active': True
            },
            {
                'udf_id': 2,
                'object_type': 'TRADE',
                'field_name': 'Selling Rule',
                'field_value': 'FIFO',
                'is_active': True
            }
        ]

    @patch('udf.views_simplified.udf_field_service')
    def test_list_success(self, mock_service):
        """Test list view loads successfully"""
        mock_service.get_all_fields.return_value = self.sample_fields
        mock_service.get_object_types.return_value = ['TRADE', 'PORTFOLIO']

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'udf/list.html')
        self.assertIn('fields', response.context)
        self.assertEqual(len(response.context['fields']), 2)

    @patch('udf.views_simplified.udf_field_service')
    def test_list_with_object_type_filter(self, mock_service):
        """Test list view with object_type filter"""
        mock_service.get_all_fields.return_value = [self.sample_fields[0]]
        mock_service.get_object_types.return_value = ['TRADE', 'PORTFOLIO']

        response = self.client.get(self.url, {'object_type': 'TRADE', 'status': 'active'})

        self.assertEqual(response.status_code, 200)
        mock_service.get_all_fields.assert_called_with(object_type='TRADE', is_active=True)

    @patch('udf.views_simplified.udf_field_service')
    def test_list_with_field_name_filter(self, mock_service):
        """Test list view with field_name filter"""
        mock_service.get_all_fields.return_value = self.sample_fields
        mock_service.get_object_types.return_value = ['TRADE']

        response = self.client.get(self.url, {'field_name': 'Fund Type', 'status': 'active'})

        self.assertEqual(response.status_code, 200)
        # Only fields matching field_name should be shown
        fields = response.context['fields']
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]['field_name'], 'Fund Type')

    @patch('udf.views_simplified.udf_field_service')
    def test_list_with_active_status_filter(self, mock_service):
        """Test list view with status=active filter (default)"""
        mock_service.get_all_fields.return_value = self.sample_fields
        mock_service.get_object_types.return_value = ['TRADE']

        # 'active' is the default status, so explicitly set it
        response = self.client.get(self.url)  # default is active

        self.assertEqual(response.status_code, 200)
        mock_service.get_all_fields.assert_called_with(object_type=None, is_active=True)

    @patch('udf.views_simplified.udf_field_service')
    def test_list_with_inactive_status_filter(self, mock_service):
        """Test list view with status=inactive filter"""
        mock_service.get_all_fields.return_value = []
        mock_service.get_object_types.return_value = ['TRADE']

        response = self.client.get(self.url, {'status': 'inactive'})

        self.assertEqual(response.status_code, 200)
        mock_service.get_all_fields.assert_called_with(object_type=None, is_active=False)

    @patch('udf.views_simplified.udf_field_service')
    def test_list_with_all_status_filter(self, mock_service):
        """Test list view with status=all filter"""
        mock_service.get_all_fields.return_value = self.sample_fields
        mock_service.get_object_types.return_value = ['TRADE']

        response = self.client.get(self.url, {'status': 'all'})

        self.assertEqual(response.status_code, 200)
        mock_service.get_all_fields.assert_called_with(object_type=None, is_active=None)

    @patch('udf.views_simplified.udf_field_service')
    def test_list_exception(self, mock_service):
        """Test list view handles exception"""
        mock_service.get_all_fields.side_effect = Exception("Database error")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 500)


class UDFCreateViewTestCase(TestCase):
    """Test cases for UDF create view"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()
        self.url = reverse('udf:create')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('udf.views_simplified.udf_field_service')
    def test_create_get_form(self, mock_service):
        """Test GET request to create view"""
        mock_service.get_object_types.return_value = ['TRADE', 'PORTFOLIO']

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'udf/form.html')
        self.assertEqual(response.context['form_action'], 'create')

    @patch('udf.views_simplified.udf_field_service')
    def test_create_get_form_prepopulated(self, mock_service):
        """Test GET request with prepopulation parameters"""
        mock_service.get_object_types.return_value = ['TRADE', 'PORTFOLIO']

        response = self.client.get(self.url, {'object_type': 'TRADE', 'field_name': 'Fund Type'})

        self.assertEqual(response.status_code, 200)
        field_data = response.context['field_data']
        self.assertEqual(field_data['object_type'], 'TRADE')
        self.assertEqual(field_data['field_name'], 'Fund Type')

    @patch('udf.views_simplified.udf_field_service')
    def test_create_post_success(self, mock_service):
        """Test successful field creation"""
        mock_service.get_object_types.return_value = ['TRADE']
        mock_service.create_field.return_value = (True, None, 100)

        response = self.client.post(self.url, {
            'object_type': 'TRADE',
            'field_name': 'fund_type',
            'field_value': 'Fund Type'
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('udf:list'))

    @patch('udf.views_simplified.udf_field_service')
    def test_create_post_validation_failure(self, mock_service):
        """Test field creation with validation error"""
        mock_service.get_object_types.return_value = ['TRADE']
        mock_service.create_field.return_value = (False, 'Field Name is required', None)

        response = self.client.post(self.url, {
            'object_type': 'TRADE',
            'field_name': '',
            'field_value': 'Test'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)

    @patch('udf.views_simplified.udf_field_service')
    def test_create_post_exception(self, mock_service):
        """Test field creation handles exception"""
        mock_service.get_object_types.return_value = ['TRADE']
        mock_service.create_field.side_effect = Exception("Database error")

        response = self.client.post(self.url, {
            'object_type': 'TRADE',
            'field_name': 'test',
            'field_value': 'Test'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)


class UDFEditViewTestCase(TestCase):
    """Test cases for UDF edit view"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.existing_field = {
            'udf_id': 1,
            'object_type': 'TRADE',
            'field_name': 'fund_type',
            'field_value': 'Fund Type',
            'is_active': True
        }

    @patch('udf.views_simplified.udf_field_service')
    def test_edit_get_form(self, mock_service):
        """Test GET request to edit view"""
        mock_service.get_field_by_id.return_value = self.existing_field
        mock_service.get_object_types.return_value = ['TRADE', 'PORTFOLIO']

        url = reverse('udf:edit', args=[1])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'udf/form.html')
        self.assertEqual(response.context['form_action'], 'edit')
        self.assertEqual(response.context['field_data'], self.existing_field)

    @patch('udf.views_simplified.udf_field_service')
    def test_edit_get_not_found(self, mock_service):
        """Test edit view with non-existent field"""
        mock_service.get_field_by_id.return_value = None

        url = reverse('udf:edit', args=[999])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    @patch('udf.views_simplified.udf_field_service')
    def test_edit_post_success(self, mock_service):
        """Test successful field edit"""
        mock_service.get_field_by_id.return_value = self.existing_field
        mock_service.get_object_types.return_value = ['TRADE']
        mock_service.update_field.return_value = (True, None)

        url = reverse('udf:edit', args=[1])
        response = self.client.post(url, {
            'object_type': 'TRADE',
            'field_name': 'fund_type',
            'field_value': 'Updated Fund Type',
            'is_active': 'on'
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('udf:list'))

    @patch('udf.views_simplified.udf_field_service')
    def test_edit_post_validation_failure(self, mock_service):
        """Test field edit with validation error"""
        mock_service.get_field_by_id.return_value = self.existing_field
        mock_service.get_object_types.return_value = ['TRADE']
        mock_service.update_field.return_value = (False, 'Validation error')

        url = reverse('udf:edit', args=[1])
        response = self.client.post(url, {
            'object_type': 'TRADE',
            'field_name': '',
            'field_value': 'Test'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)

    @patch('udf.views_simplified.udf_field_service')
    def test_edit_post_exception(self, mock_service):
        """Test field edit handles exception"""
        mock_service.get_field_by_id.return_value = self.existing_field
        mock_service.get_object_types.return_value = ['TRADE']
        mock_service.update_field.side_effect = Exception("Database error")

        url = reverse('udf:edit', args=[1])
        response = self.client.post(url, {
            'object_type': 'TRADE',
            'field_name': 'test',
            'field_value': 'Test'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)


class UDFDeleteViewTestCase(TestCase):
    """Test cases for UDF delete view"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('udf.views_simplified.udf_field_service')
    def test_delete_success(self, mock_service):
        """Test successful field deletion"""
        mock_service.delete_field.return_value = (True, None)

        url = reverse('udf:delete', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('udf:list'))

    @patch('udf.views_simplified.udf_field_service')
    def test_delete_failure(self, mock_service):
        """Test field deletion failure"""
        mock_service.delete_field.return_value = (False, 'Field not found')

        url = reverse('udf:delete', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        self.assertIn('Field not found', response.content.decode())

    @patch('udf.views_simplified.udf_field_service')
    def test_delete_exception(self, mock_service):
        """Test delete handles exception"""
        mock_service.delete_field.side_effect = Exception("Database error")

        url = reverse('udf:delete', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 500)

    def test_delete_get_not_allowed(self):
        """Test GET request to delete is not allowed"""
        url = reverse('udf:delete', args=[1])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)


class UDFRestoreViewTestCase(TestCase):
    """Test cases for UDF restore view"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('udf.views_simplified.udf_field_service')
    def test_restore_success(self, mock_service):
        """Test successful field restoration"""
        mock_service.restore_field.return_value = (True, None)

        url = reverse('udf:restore', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('udf:list'))

    @patch('udf.views_simplified.udf_field_service')
    def test_restore_failure(self, mock_service):
        """Test field restoration failure"""
        mock_service.restore_field.return_value = (False, 'Field not found')

        url = reverse('udf:restore', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        self.assertIn('Field not found', response.content.decode())

    @patch('udf.views_simplified.udf_field_service')
    def test_restore_exception(self, mock_service):
        """Test restore handles exception"""
        mock_service.restore_field.side_effect = Exception("Database error")

        url = reverse('udf:restore', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 500)

    def test_restore_get_not_allowed(self):
        """Test GET request to restore is not allowed"""
        url = reverse('udf:restore', args=[1])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)


class APIGetObjectTypesTestCase(TestCase):
    """Test cases for API get_object_types endpoint"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()
        self.url = reverse('udf:api_object_types')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('udf.views_simplified.udf_field_service')
    def test_api_get_object_types_success(self, mock_service):
        """Test successful API response for object types"""
        mock_service.get_object_types.return_value = ['TRADE', 'PORTFOLIO', 'SECURITY']

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['object_types']), 3)

    @patch('udf.views_simplified.udf_field_service')
    def test_api_get_object_types_empty(self, mock_service):
        """Test API response with empty object types"""
        mock_service.get_object_types.return_value = []

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['object_types'], [])

    @patch('udf.views_simplified.udf_field_service')
    def test_api_get_object_types_exception(self, mock_service):
        """Test API handles exception"""
        mock_service.get_object_types.side_effect = Exception("Database error")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertFalse(data['success'])

    def test_api_get_object_types_post_not_allowed(self):
        """Test POST request not allowed"""
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 405)


class APIGetFieldsByEntityTestCase(TestCase):
    """Test cases for API get_fields_by_entity endpoint"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('udf.views_simplified.udf_field_service')
    def test_api_get_fields_success(self, mock_service):
        """Test successful API response for fields by entity"""
        mock_service.get_fields_by_entity.return_value = [
            {'field_name': 'Fund Type'},
            {'field_name': 'Selling Rule'}
        ]

        url = reverse('udf:api_fields_by_object_new', args=['TRADE'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['fields']), 2)

    @patch('udf.views_simplified.udf_field_service')
    def test_api_get_fields_uppercase_conversion(self, mock_service):
        """Test API converts object_type to uppercase"""
        mock_service.get_fields_by_entity.return_value = []

        url = reverse('udf:api_fields_by_object_new', args=['trade'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        mock_service.get_fields_by_entity.assert_called_with('TRADE')

    @patch('udf.views_simplified.udf_field_service')
    def test_api_get_fields_exception(self, mock_service):
        """Test API handles exception"""
        mock_service.get_fields_by_entity.side_effect = Exception("Database error")

        url = reverse('udf:api_fields_by_object_new', args=['TRADE'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertFalse(data['success'])


class LegacyAPIGetFieldsByEntityTestCase(TestCase):
    """Test cases for legacy API endpoint"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('udf.views_simplified.udf_field_service')
    def test_legacy_api_get_fields_success(self, mock_service):
        """Test successful legacy API response"""
        mock_service.get_all_fields.return_value = [
            {'object_type': 'TRADE', 'field_name': 'Fund Type', 'field_value': 'EQUITY'}
        ]

        url = reverse('udf:api_fields_by_object', args=['TRADE'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    @patch('udf.views_simplified.udf_field_service')
    def test_legacy_api_uppercase_conversion(self, mock_service):
        """Test legacy API converts object_type to uppercase"""
        mock_service.get_all_fields.return_value = []

        url = reverse('udf:api_fields_by_object', args=['portfolio'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        mock_service.get_all_fields.assert_called_with(object_type='PORTFOLIO', is_active=True)

    @patch('udf.views_simplified.udf_field_service')
    def test_legacy_api_exception(self, mock_service):
        """Test legacy API handles exception"""
        mock_service.get_all_fields.side_effect = Exception("Database error")

        url = reverse('udf:api_fields_by_object', args=['TRADE'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertFalse(data['success'])


class UDFURLRoutingTestCase(TestCase):
    """Test cases for URL routing"""

    def test_dashboard_url(self):
        """Test dashboard URL resolves correctly"""
        url = reverse('udf:dashboard')
        self.assertEqual(url, '/udf/')

    def test_list_url(self):
        """Test list URL resolves correctly"""
        url = reverse('udf:list')
        self.assertEqual(url, '/udf/list/')

    def test_create_url(self):
        """Test create URL resolves correctly"""
        url = reverse('udf:create')
        self.assertEqual(url, '/udf/create/')

    def test_edit_url(self):
        """Test edit URL resolves correctly"""
        url = reverse('udf:edit', args=[1])
        self.assertEqual(url, '/udf/1/edit/')

    def test_delete_url(self):
        """Test delete URL resolves correctly"""
        url = reverse('udf:delete', args=[1])
        self.assertEqual(url, '/udf/1/delete/')

    def test_restore_url(self):
        """Test restore URL resolves correctly"""
        url = reverse('udf:restore', args=[1])
        self.assertEqual(url, '/udf/1/restore/')

    def test_api_object_types_url(self):
        """Test API object types URL resolves correctly"""
        url = reverse('udf:api_object_types')
        self.assertEqual(url, '/udf/api/object-types/')

    def test_api_fields_by_object_new_url(self):
        """Test new API fields URL resolves correctly"""
        url = reverse('udf:api_fields_by_object_new', args=['TRADE'])
        self.assertEqual(url, '/udf/api/fields/TRADE/')

    def test_legacy_api_fields_url(self):
        """Test legacy API fields URL resolves correctly"""
        url = reverse('udf:api_fields_by_object', args=['TRADE'])
        self.assertEqual(url, '/udf/api/TRADE/fields/')


class UDFViewAuthenticationTestCase(TestCase):
    """Test cases for view authentication"""

    def setUp(self):
        """Set up test client without session"""
        self.client = Client()

    def test_dashboard_requires_login(self):
        """Test dashboard requires login"""
        url = reverse('udf:dashboard')
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_list_requires_login(self):
        """Test list view requires login"""
        url = reverse('udf:list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    def test_create_requires_login(self):
        """Test create view requires login"""
        url = reverse('udf:create')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    def test_edit_requires_login(self):
        """Test edit view requires login"""
        url = reverse('udf:edit', args=[1])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    def test_delete_requires_login(self):
        """Test delete view requires login"""
        url = reverse('udf:delete', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

    def test_restore_requires_login(self):
        """Test restore view requires login"""
        url = reverse('udf:restore', args=[1])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

    def test_api_object_types_requires_login(self):
        """Test API object types requires login"""
        url = reverse('udf:api_object_types')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    def test_api_fields_requires_login(self):
        """Test API fields requires login"""
        url = reverse('udf:api_fields_by_object_new', args=['TRADE'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
