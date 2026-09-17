"""
Permission Middleware
=====================
Centralised URL-level permission enforcement based on core/permissions_map.py.

Flow per request:
  1. resolver_match is None (404 / bad path)  → pass through (let Django handle it)
  2. URL name in EXEMPT_URL_NAMES             → pass through
  3. User not logged in                       → redirect to login
  4. SKIP_PERMISSION_CHECKS = True            → pass through (dev mode)
  5. URL not in URL_PERMISSION_MAP            → 403 if DEFAULT_DENY else pass through
  6. URL in map — simple tuple (perm, mode)   → check against session permissions
  7. URL in map — dict per HTTP method        → look up method, then check
     └─ method not in dict                   → pass through (e.g. OPTIONS, HEAD)

Corner cases handled:
  - resolver_match None           : guarded at step 1
  - Public/auth URLs              : EXEMPT_URL_NAMES whitelist
  - GET read / POST write split   : per-method dict in URL_PERMISSION_MAP
  - AJAX API endpoints            : explicit entries, inherit READ from parent module
  - New URL missing from map      : DEFAULT_DENY blocks with 403
  - Superuser / RBAC admin URLs   : explicit entries in map like any other module
  - SKIP_PERMISSION_CHECKS        : full bypass for dev/test
  - JsonResponse for API denials  : detects AJAX requests and returns JSON 403
  - Audit logging on denial       : async log to cis_audit_log
"""

import logging
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

from core.permissions_map import EXEMPT_URL_NAMES, URL_PERMISSION_MAP, DEFAULT_DENY

logger = logging.getLogger('permission_middleware')


def _is_ajax(request) -> bool:
    """Detect AJAX / API requests to return JSON instead of HTML on denial."""
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.path.startswith('/api/')
        or '/api/' in request.path
        or request.headers.get('Accept', '').startswith('application/json')
    )


def _deny(request, message: str, status: int = 403):
    """Return appropriate denial response — JSON for API/AJAX, HTML otherwise."""
    if _is_ajax(request):
        return JsonResponse({'error': message, 'status': status}, status=status)
    return HttpResponse(
        f"<h2>Access Denied</h2><p>{message}</p>"
        f"<p><a href='/dashboard/'>Back to Dashboard</a></p>",
        status=status,
        content_type='text/html',
    )


def _audit_denial(request, permission: str, mode: str):
    """Fire-and-forget audit log for permission denials."""
    try:
        from core.audit.audit_kudu_repository import audit_log_kudu_repository
        audit_log_kudu_repository.log_action(
            user_id=str(request.session.get('user_id', '0')),
            username=request.session.get('user_login', 'anonymous'),
            user_email=request.session.get('user_email', ''),
            action_type='ACCESS_DENIED',
            entity_type='AUTH',
            entity_name='PermissionMiddleware',
            entity_id=permission,
            action_description=(
                f"Access denied: requires {permission!r} {mode}. "
                f"Path={request.path} Method={request.method}"
            ),
            request_method=request.method,
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='FAILURE',
        )
    except Exception as e:
        logger.error(f"Audit log error in PermissionMiddleware: {e}")


def _check_permission(session_perms: dict, permission: str, mode: str) -> bool:
    """
    Check session permission map against required permission + mode.
    READ  → user_mode in (READ, WRITE)
    WRITE → user_mode must be WRITE
    """
    user_mode = session_perms.get(permission)
    if user_mode is None:
        return False
    if mode == 'READ':
        return user_mode in ('READ', 'WRITE')
    return user_mode == 'WRITE'


class PermissionMiddleware(MiddlewareMixin):
    """
    Middleware that enforces URL-level permissions from core/permissions_map.py.
    Must be placed AFTER SessionMiddleware in MIDDLEWARE list.
    """

    def process_request(self, request):
        # ------------------------------------------------------------------
        # Step 1: resolver_match may be None for unknown paths
        # ------------------------------------------------------------------
        if not hasattr(request, 'resolver_match') or request.resolver_match is None:
            return None  # Let Django's 404 handler take over

        match = request.resolver_match

        # Build the fully-qualified URL name (e.g. 'trade:list')
        app_name = match.app_name or match.namespace or ''
        url_name = match.url_name or ''
        full_name = f'{app_name}:{url_name}' if app_name else url_name

        # ------------------------------------------------------------------
        # Step 2: Exempt URLs always pass through
        # ------------------------------------------------------------------
        if full_name in EXEMPT_URL_NAMES or url_name in EXEMPT_URL_NAMES:
            return None

        # ------------------------------------------------------------------
        # Step 3: Login check
        # ------------------------------------------------------------------
        if not request.session.get('user_login'):
            # Preserve the intended destination for post-login redirect
            next_url = request.get_full_path()
            return redirect(f'/login/?next={next_url}')

        # ------------------------------------------------------------------
        # Step 4: Dev bypass
        # ------------------------------------------------------------------
        if getattr(settings, 'SKIP_PERMISSION_CHECKS', False):
            logger.debug(f"DEV MODE: skipping permission check for {full_name}")
            return None

        # ------------------------------------------------------------------
        # Step 5: URL not in map → default deny or allow
        # ------------------------------------------------------------------
        if full_name not in URL_PERMISSION_MAP:
            if DEFAULT_DENY:
                logger.warning(
                    f"PermissionMiddleware: {full_name!r} not in URL_PERMISSION_MAP "
                    f"— blocked by DEFAULT_DENY (user={request.session.get('user_login')})"
                )
                return _deny(
                    request,
                    f"This page has no permission declaration. "
                    f"Add '{full_name}' to core/permissions_map.py.",
                )
            return None

        # ------------------------------------------------------------------
        # Step 6 & 7: Resolve the required permission
        # ------------------------------------------------------------------
        rule = URL_PERMISSION_MAP[full_name]
        session_perms = request.session.get('user_permissions', {})

        if isinstance(rule, dict):
            # Per-method rule
            method_rule = rule.get(request.method.upper())
            if method_rule is None:
                # Method not declared — pass through (e.g. HEAD, OPTIONS)
                return None
            permission, mode = method_rule
        else:
            permission, mode = rule

        # ------------------------------------------------------------------
        # Permission check
        # ------------------------------------------------------------------
        if _check_permission(session_perms, permission, mode):
            return None  # Granted

        # Denied
        logger.info(
            f"PermissionMiddleware DENIED {full_name!r} "
            f"(requires {permission!r} {mode}, "
            f"user={request.session.get('user_login')!r})"
        )
        _audit_denial(request, permission, mode)
        return _deny(
            request,
            f"You need '{permission}' ({mode}) permission to access this page.",
        )
