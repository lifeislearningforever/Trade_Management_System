"""
Notification sender helpers.

These are called from background threads (AVP worker, ETL service) and from
Django views.  They are deliberately synchronous wrappers around the async
channel layer so they work safely from non-async contexts.

Corner cases handled:
  - Channel layer not configured (CHANNEL_LAYERS missing) → logged, not raised
  - Channel layer temporarily unavailable (Redis down) → logged, not raised
  - Invalid / empty username → silently skipped
  - Worker thread calling async channel_layer → uses async_to_sync
  - Message payload too large → truncated to MAX_PAYLOAD_BYTES
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from asgiref.sync import async_to_sync

from core.notifications.constants import (
    ADMIN_GROUP,
    EVENT_SEVERITY,
    EVT_SYSTEM_ERROR,
    SEV_ERROR,
    user_group,
    role_group,
)

logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 32_768  # 32 KB — guard against oversized messages


def _get_channel_layer():
    """Return the configured channel layer, or None if not available."""
    try:
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            logger.debug('Channel layer is None — CHANNEL_LAYERS not configured.')
        return layer
    except ImportError:
        logger.debug('django-channels not installed — notifications disabled.')
        return None
    except Exception as exc:
        logger.warning('Could not get channel layer: %s', exc)
        return None


def _build_message(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build a standardised notification message dict."""
    message = {
        'type': 'notification.send',      # maps to consumer method
        'event_type': event_type,
        'severity': EVENT_SEVERITY.get(event_type, SEV_ERROR),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'payload': payload,
    }
    # Guard against oversized payloads
    raw = json.dumps(message)
    if len(raw) > MAX_PAYLOAD_BYTES:
        message['payload'] = {
            'truncated': True,
            'original_keys': list(payload.keys()),
        }
        logger.warning(
            'Notification payload for %s exceeded %d bytes — truncated.',
            event_type, MAX_PAYLOAD_BYTES,
        )
    return message


def _send_to_group(group: str, message: Dict[str, Any]) -> bool:
    """
    Send a message to a channel layer group.
    Returns True on success, False on any failure.
    Safe to call from sync (background thread) contexts.
    """
    layer = _get_channel_layer()
    if layer is None:
        return False
    try:
        async_to_sync(layer.group_send)(group, message)
        return True
    except Exception as exc:
        logger.warning('Failed to send notification to group %s: %s', group, exc)
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def notify_user(
    username: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send a notification to a specific user's WebSocket group.

    Args:
        username:   The CIS username (from queued_by / session user_login).
        event_type: One of the EVT_* constants from constants.py.
        payload:    Arbitrary dict with event-specific data.

    Returns:
        True if the message was dispatched to the channel layer successfully.
    """
    if not username or not isinstance(username, str):
        logger.debug('notify_user called with empty/invalid username — skipped.')
        return False

    message = _build_message(event_type, payload or {})
    group = user_group(username)
    ok = _send_to_group(group, message)
    if ok:
        logger.debug('Notification %s → user %s sent.', event_type, username)
    return ok


def notify_role(
    role_name: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send a notification to all users who joined a role-based group.

    Args:
        role_name:  CIS role/group name (e.g. 'ADMIN', 'TRADER', 'APPROVER').
        event_type: One of the EVT_* constants.
        payload:    Arbitrary dict with event-specific data.
    """
    if not role_name or not isinstance(role_name, str):
        return False

    message = _build_message(event_type, payload or {})
    group = role_group(role_name)
    ok = _send_to_group(group, message)
    if ok:
        logger.debug('Notification %s → role %s sent.', event_type, role_name)
    return ok


def notify_admins(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send a notification to all connected admin users.

    Used for: AVP failures, dead-letter queue events, SLA breaches,
    system errors, upload failures affecting all users.
    """
    message = _build_message(event_type, payload or {})
    ok = _send_to_group(ADMIN_GROUP, message)
    if ok:
        logger.debug('Notification %s → admin_all sent.', event_type)
    return ok


def notify_multiple_users(
    usernames: List[str],
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Broadcast to a list of users (e.g. maker + checker for approval events).
    Returns count of successful sends.
    """
    sent = 0
    for username in usernames:
        if notify_user(username, event_type, payload):
            sent += 1
    return sent
