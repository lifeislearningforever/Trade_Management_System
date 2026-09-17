"""
Tests for core middleware: ACLMiddleware and PermissionMiddleware.
"""

from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory

from core.middleware.acl_middleware import ACLMiddleware


class ACLMiddlewareTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = ACLMiddleware(get_response=lambda r: None)

    @patch('core.middleware.acl_middleware.acl_service')
    def test_attaches_acl_service_to_request(self, mock_acl_service):
        request = self.factory.get('/')
        request.user = MagicMock(is_authenticated=False)
        self.middleware.process_request(request)
        self.assertEqual(request.acl_service, mock_acl_service)

    @patch('core.middleware.acl_middleware.acl_service')
    def test_unauthenticated_user_gets_empty_permissions(self, mock_acl_service):
        request = self.factory.get('/')
        request.user = MagicMock(is_authenticated=False)
        self.middleware.process_request(request)
        self.assertEqual(request.user_permissions, {})

    @patch('core.middleware.acl_middleware.acl_service')
    def test_authenticated_user_gets_permissions(self, mock_acl_service):
        mock_acl_service.get_user_permissions.return_value = {'can_view': True}
        request = self.factory.get('/')
        request.user = MagicMock(is_authenticated=True)
        self.middleware.process_request(request)
        self.assertEqual(request.user_permissions, {'can_view': True})
        mock_acl_service.get_user_permissions.assert_called_once_with(request.user)

    @patch('core.middleware.acl_middleware.acl_service')
    def test_process_request_returns_none(self, mock_acl_service):
        request = self.factory.get('/')
        request.user = MagicMock(is_authenticated=False)
        result = self.middleware.process_request(request)
        self.assertIsNone(result)
