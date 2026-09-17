"""
Application-level error handlers.

Registered in config/urls.py as handler400/403/404/500 so that with
DEBUG=False (UAT/PROD) users see a branded message page instead of
Django's bare debug traceback or blank default error page.

Deliberately render standalone templates (templates/errors/*.html) that
do NOT extend base.html — base.html pulls in the sidebar/navbar/ACL
context, any of which failing is exactly the kind of thing that can
cause the 500 in the first place, and a broken error page is worse
than no styling.
"""

import logging

from django.shortcuts import render

logger = logging.getLogger(__name__)


def bad_request(request, exception=None):
    logger.warning("400 Bad Request: %s | path=%s", exception, request.path)
    return render(request, 'errors/400.html', status=400)


def permission_denied(request, exception=None):
    logger.warning("403 Forbidden: %s | path=%s", exception, request.path)
    return render(request, 'errors/403.html', status=403)


def page_not_found(request, exception=None):
    logger.info("404 Not Found: path=%s", request.path)
    return render(request, 'errors/404.html', status=404)


def server_error(request):
    logger.error("500 Server Error: path=%s", request.path, exc_info=True)
    return render(request, 'errors/500.html', status=500)
