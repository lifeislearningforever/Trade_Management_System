"""
Django middleware for automatic audit logging of HTTP requests to Hive.
Follows SOLID principles.

This middleware logs all significant HTTP requests to the Hive audit table.
"""

import time
import logging
from typing import Callable

from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

from ..audit.audit_models import (
    AuditEntry, ActionType, ActionCategory, AuditStatus
)
from ..audit.audit_logger import get_audit_logger

logger = logging.getLogger(__name__)


class HiveAuditMiddleware(MiddlewareMixin):
    """
    Middleware to automatically audit HTTP requests to Hive.
    Follows Single Responsibility Principle.
    """

    def __init__(self, get_response: Callable):
        """
        Initialize middleware.

        Args:
            get_response: Next middleware or view function
        """
        super().__init__(get_response)
        self.get_response = get_response
        self.audit_logger = get_audit_logger()

        # Paths to exclude from auditing (to reduce noise)
        self.excluded_paths = [
            '/static/',
            '/media/',
            '/favicon.ico',
            '/__debug__/',
        ]

        # Methods to audit (exclude OPTIONS, HEAD by default)
        self.audited_methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """
        Process request and response with audit logging.

        Args:
            request: HttpRequest object

        Returns:
            HttpResponse object
        """
        # Check if path should be excluded
        if self._should_exclude(request):
            return self.get_response(request)

        # Check if method should be audited
        if request.method not in self.audited_methods:
            return self.get_response(request)

        # Start timing
        start_time = time.time()

        # Store request start time for duration calculation
        request._audit_start_time = start_time

        # Process request
        response = self.get_response(request)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Create audit entry
        try:
            self._create_audit_entry(request, response, duration_ms)
        except Exception as e:
            logger.error(f"Failed to create audit entry: {str(e)}")
            logger.exception(e)

        return response

    def _should_exclude(self, request: HttpRequest) -> bool:
        """
        Check if request path should be excluded from auditing.

        Args:
            request: HttpRequest object

        Returns:
            bool: True if should be excluded
        """
        path = request.path
        return any(path.startswith(excluded) for excluded in self.excluded_paths)

    def _get_action_type(self, request: HttpRequest) -> ActionType:
        """
        Determine action type from HTTP method.

        Args:
            request: HttpRequest object

        Returns:
            ActionType enum value
        """
        method_mapping = {
            'GET': ActionType.READ,
            'POST': ActionType.CREATE,
            'PUT': ActionType.UPDATE,
            'PATCH': ActionType.UPDATE,
            'DELETE': ActionType.DELETE,
        }
        return method_mapping.get(request.method, ActionType.READ)

    def _get_action_category(self, request: HttpRequest) -> ActionCategory:
        """
        Determine action category from request path.

        Args:
            request: HttpRequest object

        Returns:
            ActionCategory enum value
        """
        path = request.path.lower()

        if '/portfolio/' in path:
            return ActionCategory.PORTFOLIO
        elif '/trade/' in path:
            return ActionCategory.TRADE
        elif '/udf/' in path:
            return ActionCategory.UDF
        elif '/admin/' in path:
            return ActionCategory.ADMIN
        elif '/report/' in path:
            return ActionCategory.REPORT
        elif '/login' in path or '/logout' in path or '/auth/' in path:
            return ActionCategory.AUTH
        else:
            return ActionCategory.DATA

    def _get_status(self, response: HttpResponse) -> AuditStatus:
        """
        Determine audit status from response status code.

        Args:
            response: HttpResponse object

        Returns:
            AuditStatus enum value
        """
        if 200 <= response.status_code < 300:
            return AuditStatus.SUCCESS
        else:
            return AuditStatus.FAILURE

    def _create_audit_entry(self,
                            request: HttpRequest,
                            response: HttpResponse,
                            duration_ms: int):
        """
        Create and log audit entry for the request.

        Args:
            request: HttpRequest object
            response: HttpResponse object
            duration_ms: Request duration in milliseconds
        """
        # Determine action type and category
        action_type = self._get_action_type(request)
        action_category = self._get_action_category(request)

        # Create audit entry from request
        audit_entry = AuditEntry.from_request(
            request,
            action_type=action_type,
            action_category=action_category,
            action_description=f"{request.method} {request.path}",
            status=self._get_status(response),
            status_code=response.status_code,
            duration_ms=duration_ms,
            module_name='http_request',
        )

        # Add error message if failed
        if response.status_code >= 400:
            audit_entry.error_message = f"HTTP {response.status_code}"

        # Log the audit entry (async/non-blocking in production)
        self.audit_logger.log(audit_entry)


class SelectiveAuditMiddleware(HiveAuditMiddleware):
    """
    Selective audit middleware that only audits specific paths.
    Extends HiveAuditMiddleware following Open/Closed Principle.
    """

    def __init__(self, get_response: Callable):
        """
        Initialize selective audit middleware.

        Args:
            get_response: Next middleware or view function
        """
        super().__init__(get_response)

        # Only audit these paths
        self.included_paths = [
            '/portfolio/',
            '/trade/',
            '/udf/',
            '/reference-data/',
        ]

    def _should_exclude(self, request: HttpRequest) -> bool:
        """
        Check if request should be excluded (inverse logic - only include specific paths).

        Args:
            request: HttpRequest object

        Returns:
            bool: True if should be excluded
        """
        path = request.path

        # First check parent exclusions
        if super()._should_exclude(request):
            return True

        # Then check if path is in included list
        return not any(path.startswith(included) for included in self.included_paths)
