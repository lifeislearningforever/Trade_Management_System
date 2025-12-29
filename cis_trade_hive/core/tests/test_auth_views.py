"""
Core Authentication View Tests

Tests for authentication views including:
- Login (success and failure)
- Logout
- Auto-login
- Permission checks
- Session management
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, Mock, MagicMock
from core.repositories.acl_repository import ACLRepository
from core.audit.audit_kudu_repository import AuditLogKuduRepository


class LoginViewTestCase(TestCase):
    """Test cases for login view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('login')

        # Sample ACL user data
        self.sample_auth_data = {
            'user': {
                'cis_user_id': 1,
                'login': 'testuser',
                'name': 'Test User',
                'email': 'test@example.com',
                'cis_user_group_id': 1,
                'is_enabled': True
            },
            'group': {
                'cis_user_group_id': 1,
                'name': 'Test Group',
                'description': 'Test group description'
            },
            'permission_map': {
                'cis-portfolio': 'READ_WRITE',
                'cis-reference-data': 'READ'
            }
        }

    def test_login_view_get(self):
        """Test GET request to login page"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/login.html')

    def test_login_view_already_logged_in_redirects(self):
        """Test logged-in user redirects to dashboard"""
        session = self.client.session
        session['user_login'] = 'testuser'
        session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

    @patch('core.views.auth_views.audit_log_kudu_repository.log_action')
    @patch('core.views.auth_views.get_acl_repository')
    def test_login_success(self, mock_get_acl_repo, mock_audit_log):
        """Test successful login"""
        # Mock ACL repository
        mock_acl = MagicMock()
        mock_acl.authenticate_user.return_value = self.sample_auth_data
        mock_get_acl_repo.return_value = mock_acl

        response = self.client.post(self.url, {'login': 'testuser'})

        # Check redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

        # Verify session data
        self.assertEqual(self.client.session.get('user_login'), 'testuser')
        self.assertEqual(self.client.session.get('user_id'), 1)
        self.assertEqual(self.client.session.get('user_name'), 'Test User')
        self.assertEqual(self.client.session.get('user_email'), 'test@example.com')

        # Verify audit log was called
        mock_audit_log.assert_called_once()
        call_kwargs = mock_audit_log.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'LOGIN')
        self.assertEqual(call_kwargs['status'], 'SUCCESS')

    @patch('core.views.auth_views.audit_log_kudu_repository.log_action')
    @patch('core.views.auth_views.get_acl_repository')
    def test_login_failure_invalid_user(self, mock_get_acl_repo, mock_audit_log):
        """Test failed login with invalid user"""
        # Mock ACL repository returning None
        mock_acl = MagicMock()
        mock_acl.authenticate_user.return_value = None
        mock_get_acl_repo.return_value = mock_acl

        response = self.client.post(self.url, {'login': 'invaliduser'})

        # Should stay on login page
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/login.html')
        self.assertContains(response, 'not found or not enabled')

        # Verify no session was created
        self.assertIsNone(self.client.session.get('user_login'))

        # Verify audit log was called for failure
        mock_audit_log.assert_called_once()
        call_kwargs = mock_audit_log.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'LOGIN')
        self.assertEqual(call_kwargs['status'], 'FAILURE')
        self.assertEqual(call_kwargs['username'], 'invaliduser')

    def test_login_empty_login(self):
        """Test login with empty login field"""
        response = self.client.post(self.url, {'login': ''})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter your login ID')


class LogoutViewTestCase(TestCase):
    """Test cases for logout view"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()
        self.url = reverse('logout')

        # Set up session
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_name'] = 'Test User'
        session['user_email'] = 'test@example.com'
        session.save()

    @patch('core.views.auth_views.audit_log_kudu_repository.log_action')
    def test_logout_success(self, mock_audit_log):
        """Test successful logout"""
        response = self.client.get(self.url)

        # Check redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('login'))

        # Verify session was cleared
        self.assertIsNone(self.client.session.get('user_login'))

        # Verify audit log was called
        mock_audit_log.assert_called_once()
        call_kwargs = mock_audit_log.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'LOGOUT')
        self.assertEqual(call_kwargs['status'], 'SUCCESS')
        self.assertEqual(call_kwargs['username'], 'testuser')


class AutoLoginTestCase(TestCase):
    """Test cases for auto-login functionality"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('auto_login')

        self.sample_auth_data = {
            'user': {
                'cis_user_id': 2,
                'login': 'TMP3RC',
                'name': 'PRAKASH HOSALLI',
                'email': 'prakash.hosalli1@uobgroup.com',
                'cis_user_group_id': 1,
                'is_enabled': True
            },
            'group': {
                'cis_user_group_id': 1,
                'name': 'Admin',
                'description': 'Administrator group'
            },
            'permission_map': {
                'cis-portfolio': 'READ_WRITE'
            }
        }

    @patch('core.views.auth_views.audit_log_kudu_repository.log_action')
    @patch('core.views.auth_views.get_acl_repository')
    def test_auto_login_success(self, mock_get_acl_repo, mock_audit_log):
        """Test successful auto-login"""
        # Mock ACL repository
        mock_acl = MagicMock()
        mock_acl.authenticate_user.return_value = self.sample_auth_data
        mock_get_acl_repo.return_value = mock_acl

        response = self.client.get(self.url)

        # Check redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

        # Verify session data
        self.assertEqual(self.client.session.get('user_login'), 'TMP3RC')
        self.assertEqual(self.client.session.get('user_id'), 2)

        # Verify audit log was called
        mock_audit_log.assert_called_once()
        call_kwargs = mock_audit_log.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'LOGIN')
        self.assertEqual(call_kwargs['entity_name'], 'Auto-Login')

    @patch('core.views.auth_views.get_acl_repository')
    def test_auto_login_failure(self, mock_get_acl_repo):
        """Test failed auto-login"""
        # Mock ACL repository returning None
        mock_acl = MagicMock()
        mock_acl.authenticate_user.return_value = None
        mock_get_acl_repo.return_value = mock_acl

        response = self.client.get(self.url)

        # Should return error response
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, 'Auto-login failed', status_code=500)


class RequireLoginDecoratorTestCase(TestCase):
    """Test cases for @require_login decorator"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        # Use dashboard as test endpoint (requires login)
        self.url = reverse('dashboard')

    def test_require_login_redirects_when_not_logged_in(self):
        """Test that unauthenticated users are redirected to login"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('login'))

    def test_require_login_allows_access_when_logged_in(self):
        """Test that authenticated users can access protected views"""
        # Set up session
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_name'] = 'Test User'
        session['user_email'] = 'test@example.com'
        session.save()

        response = self.client.get(self.url)

        # Should allow access (not redirect to login)
        self.assertEqual(response.status_code, 200)


class RequirePermissionDecoratorTestCase(TestCase):
    """Test cases for @require_permission decorator"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()

        # Set up session with permissions
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_name'] = 'Test User'
        session['user_email'] = 'test@example.com'
        session['user_permissions'] = {
            'cis-portfolio': 'READ',
            'cis-reference-data': 'READ_WRITE'
        }
        session.save()

    @patch('core.views.auth_views.audit_log_kudu_repository.log_action')
    def test_permission_denied_logged(self, mock_audit_log):
        """Test that permission denials are logged to audit"""
        from django.test import override_settings

        with override_settings(SKIP_PERMISSION_CHECKS=False):
            # Try to access portfolio create (needs WRITE permission)
            # Using a view that doesn't exist, just to test the decorator
            from django.http import HttpResponse
            from core.views.auth_views import require_permission

            @require_permission('cis-portfolio', 'WRITE')
            def test_view(request):
                return HttpResponse('Success')

            # Create a mock request
            from django.test import RequestFactory
            factory = RequestFactory()
            request = factory.get('/test/')
            request.session = self.client.session

            response = test_view(request)

            # Should deny access
            self.assertEqual(response.status_code, 403)
            self.assertIn(b'Access denied', response.content)

            # Verify audit log was called
            mock_audit_log.assert_called_once()
            call_kwargs = mock_audit_log.call_args[1]
            self.assertEqual(call_kwargs['action_type'], 'ACCESS_DENIED')
            self.assertEqual(call_kwargs['status'], 'FAILURE')


@pytest.mark.django_db
class SessionManagementTestCase(TestCase):
    """Test cases for session management"""

    def test_session_data_persistence(self):
        """Test that session data persists across requests"""
        client = Client()

        # Set session data
        session = client.session
        session['user_login'] = 'testuser'
        session['test_data'] = 'test_value'
        session.save()

        # Make another request
        response = client.get(reverse('dashboard'))

        # Session data should persist
        self.assertEqual(client.session.get('user_login'), 'testuser')
        self.assertEqual(client.session.get('test_data'), 'test_value')

    def test_logout_clears_all_session_data(self):
        """Test that logout clears all session data"""
        client = Client()

        # Set multiple session values
        session = client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['custom_data'] = 'custom_value'
        session.save()

        # Logout
        with patch('core.views.auth_views.audit_log_kudu_repository.log_action'):
            client.get(reverse('logout'))

        # All session data should be cleared
        self.assertIsNone(client.session.get('user_login'))
        self.assertIsNone(client.session.get('user_id'))
        self.assertIsNone(client.session.get('custom_data'))
