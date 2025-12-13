"""
Audit Logging Middleware
Automatically logs user actions to the audit trail
"""

from django.utils.deprecation import MiddlewareMixin
from django.urls import resolve
from .models import AuditLog
import json


class AuditLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to automatically log user actions
    """

    # Actions that don't need logging
    EXCLUDED_PATHS = [
        '/static/',
        '/media/',
        '/admin/jsi18n/',
        '/__debug__/',
    ]

    # Read-only actions (GET, HEAD, OPTIONS)
    READ_ACTIONS = ['GET', 'HEAD', 'OPTIONS']

    def process_response(self, request, response):
        """Log the request after processing"""

        # Skip if user is not authenticated
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return response

        # Skip excluded paths
        path = request.path
        if any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS):
            return response

        # Skip AJAX requests for now (can be enabled later)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return response

        # Determine action type based on method
        method = request.method
        action = self._get_action_type(method, path, response)

        # Only log significant actions
        if action:
            try:
                # Get resolved URL pattern
                resolved = resolve(path)
                view_name = resolved.view_name or 'unknown'

                # Build description
                description = self._build_description(method, path, view_name, response)

                # Determine category from URL
                category = self._get_category(path)

                # Log the action
                AuditLog.log_action(
                    user=request.user,
                    action=action,
                    description=description,
                    category=category,
                    ip_address=self._get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                    request_method=method,
                    request_path=path[:500],
                    success=(200 <= response.status_code < 400)
                )
            except Exception as e:
                # Don't break the request if audit logging fails
                print(f"Audit logging error: {e}")

        return response

    def _get_action_type(self, method, path, response):
        """Determine action type from request method and path"""

        # Login/Logout (handle first, before filtering)
        if '/login' in path:
            if method == 'POST' and response.status_code in [200, 302]:
                return 'LOGIN'
            return None  # Skip GET on login page

        if '/logout' in path:
            return 'LOGOUT'

        # Skip read-only GET requests for all other pages
        if method in self.READ_ACTIONS:
            return None

        # CRUD operations (POST, PUT, PATCH, DELETE)
        if method == 'POST':
            if '/create' in path:
                return 'CREATE'
            elif '/submit' in path:
                return 'SUBMIT'
            elif '/approve' in path:
                return 'APPROVE'
            elif '/reject' in path:
                return 'REJECT'
            elif '/edit' in path:
                return 'UPDATE'
            elif '/delete' in path:
                return 'DELETE'
            else:
                # Generic POST action
                return 'CREATE'
        elif method == 'PUT' or method == 'PATCH':
            return 'UPDATE'
        elif method == 'DELETE':
            return 'DELETE'

        return None

    def _build_description(self, method, path, view_name, response):
        """Build human-readable description"""

        if '/login' in path:
            return 'User logged in'
        if '/logout' in path:
            return 'User logged out'

        # Extract module from path (orders, portfolio, etc.)
        parts = path.strip('/').split('/')
        module = parts[0] if parts else 'unknown'

        # Extract UUID if present (for specific record actions)
        record_id = None
        for part in parts:
            if len(part) == 36 and '-' in part:  # UUID format
                record_id = part[:8]  # Short version
                break

        if 'create' in path:
            return f'Created new {module.rstrip("s")} record'
        elif 'edit' in path:
            return f'Edited {module.rstrip("s")} {record_id or "record"}'
        elif 'delete' in path:
            return f'Deleted {module.rstrip("s")} {record_id or "record"}'
        elif 'submit' in path:
            return f'Submitted {module.rstrip("s")} {record_id or "record"} for approval'
        elif 'approve' in path:
            return f'Approved {module.rstrip("s")} {record_id or "record"}'
        elif 'reject' in path:
            return f'Rejected {module.rstrip("s")} {record_id or "record"}'

        return f'{method} {module} - {view_name}'

    def _get_category(self, path):
        """Extract category from path"""

        if '/orders/' in path:
            return 'orders'
        elif '/portfolio/' in path:
            return 'portfolio'
        elif '/reference/' in path:
            return 'reference_data'
        elif '/udf/' in path:
            return 'udf'
        elif '/accounts/' in path or '/login' in path or '/logout' in path:
            return 'accounts'

        return 'system'

    def _get_client_ip(self, request):
        """Get client IP address"""

        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')

        return ip[:45] if ip else ''
