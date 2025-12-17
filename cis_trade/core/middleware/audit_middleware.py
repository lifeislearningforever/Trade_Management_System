"""
Audit Middleware

Automatically logs all significant requests to the audit log.
"""

import logging
import json
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from core.models import AuditLog

logger = logging.getLogger('audit')


class AuditMiddleware(MiddlewareMixin):
    """
    Middleware to automatically audit significant requests.

    Logs:
    - POST, PUT, PATCH, DELETE requests (data modifications)
    - Admin actions
    - Authentication events
    """

    # Methods that should be audited
    AUDIT_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']

    # Paths to exclude from auditing
    EXCLUDE_PATHS = [
        '/static/',
        '/media/',
        '/admin/jsi18n/',
        '/__debug__/',
    ]

    def should_audit(self, request):
        """Determine if this request should be audited"""
        if not settings.AUDIT_LOG_ENABLED:
            return False

        # Check if path should be excluded
        for exclude_path in self.EXCLUDE_PATHS:
            if request.path.startswith(exclude_path):
                return False

        # Audit modification methods
        if request.method in self.AUDIT_METHODS:
            return True

        # Audit authentication endpoints
        if '/login/' in request.path or '/logout/' in request.path:
            return True

        return False

    def process_response(self, request, response):
        """Process response and create audit log if needed"""
        if not self.should_audit(request):
            return response

        try:
            # Get client IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0]
            else:
                ip_address = request.META.get('REMOTE_ADDR')

            # Get user agent
            user_agent = request.META.get('HTTP_USER_AGENT', '')

            # Determine action based on method and path
            action = self._determine_action(request, response)

            # Create audit log
            AuditLog.log_action(
                action=action,
                user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
                object_type='HTTP_REQUEST',
                object_id=request.path,
                object_repr=f"{request.method} {request.path}",
                description=f"{request.method} request to {request.path}",
                ip_address=ip_address,
                user_agent=user_agent[:500],  # Truncate to fit
                request_path=request.path,
                request_method=request.method,
                severity='INFO' if response.status_code < 400 else 'WARNING',
                additional_data={
                    'status_code': response.status_code,
                    'content_type': response.get('Content-Type', ''),
                }
            )

        except Exception as e:
            # Don't let audit logging break the application
            logger.error(f"Failed to create audit log: {str(e)}")

        return response

    def _determine_action(self, request, response):
        """Determine the action type based on request details"""
        if '/login/' in request.path:
            return 'LOGIN'
        elif '/logout/' in request.path:
            return 'LOGOUT'
        elif request.method == 'POST':
            return 'CREATE'
        elif request.method in ['PUT', 'PATCH']:
            return 'UPDATE'
        elif request.method == 'DELETE':
            return 'DELETE'
        else:
            return 'READ'
