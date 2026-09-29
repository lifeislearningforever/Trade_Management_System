"""
Notification poll endpoint — cross-worker fallback for WebSocket delivery.

GET /api/notifications/poll/
  Returns unread notifications for the current user from cis_notification (Kudu).
  Marks them read on the server.  The JS client calls this every 15 s when the
  WebSocket is connected but notifications may be stuck on another Gunicorn worker
  (InMemoryChannelLayer doesn't share state across processes).
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def poll_notifications(request):
    username = request.session.get('user_login', '')
    if not username:
        return JsonResponse({'notifications': []})

    try:
        from core.notifications.kudu_store import poll_unread
        notifications = poll_unread(username, since_minutes=60)
    except Exception as exc:
        logger.debug('poll_notifications error: %s', exc)
        notifications = []

    return JsonResponse({'notifications': notifications})
