"""
Context Processors

Make common variables available to all templates.
"""

from django.conf import settings


def acl_context(request):
    """
    Add ACL-related context to templates.

    Makes user permissions available as template variables.
    """
    context = {
        'user_permissions': getattr(request, 'user_permissions', {}),
        'acl_enabled': settings.ACL_ENABLED,
    }
    return context


def app_context(request):
    """
    Add application-wide context to templates.

    Makes app name, version, and other metadata available.
    """
    context = {
        'app_name': settings.APP_NAME,
        'app_version': settings.APP_VERSION,
        'app_description': settings.APP_DESCRIPTION,
        'maker_checker_enabled': settings.MAKER_CHECKER_ENABLED,
    }
    return context
