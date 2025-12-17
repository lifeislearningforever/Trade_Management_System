"""
ACL Middleware

Attaches ACL service to request and checks permissions.
"""

import logging
from django.utils.deprecation import MiddlewareMixin
from core.services.acl_service import acl_service

logger = logging.getLogger('acl')


class ACLMiddleware(MiddlewareMixin):
    """
    Middleware to attach ACL information to each request.

    Adds:
    - request.acl_service: ACL service instance
    - request.user_permissions: User's permissions dictionary
    """

    def process_request(self, request):
        """Process incoming request and attach ACL info"""
        # Attach ACL service to request
        request.acl_service = acl_service

        # Get user permissions and attach to request
        if hasattr(request, 'user') and request.user.is_authenticated:
            request.user_permissions = acl_service.get_user_permissions(request.user)
        else:
            request.user_permissions = {}

        return None
