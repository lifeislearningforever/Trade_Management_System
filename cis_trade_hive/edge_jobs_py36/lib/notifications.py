"""
Django-free stand-in for core.notifications (notify_user / notify_role /
notify_admins / pop_pending), used by position_queue_service.py.

The original sends over a Django Channels WebSocket group, persists to Kudu
as a polling fallback (core/notifications/kudu_store.py), and buffers in an
in-process "pending" queue flushed on the next WS connect. None of the
WS-related paths make sense for a standalone batch job: there is no live
Channels layer and no next request in this process to flush a pending queue
to. This shim keeps only the part that still has value after the process
exits -- persisting to cis_notification -- so the event is still visible
next time someone opens the CIS web UI, and always logs locally regardless
of whether the Kudu write itself succeeds.

core.notifications.constants (event type / severity constants, group-name
helpers) has zero Django dependency and is imported directly from the
original tree rather than duplicated here -- see lib/__init__.py.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.notifications.constants import EVENT_SEVERITY, EVENT_TITLE, SEV_ERROR

from .config import settings
from .impala_connection import impala_manager

logger = logging.getLogger(__name__)

_DATABASE = settings.IMPALA_CONFIG['DATABASE']
_TABLE = '{}.cis_notification'.format(_DATABASE)


def _esc(val) -> str:
    if not val:
        return "''"
    s = str(val).replace('\\', '\\\\').replace("'", "\\'")
    return "'{}'".format(s)


def _persist(username: str, event_type: str, severity: str, title: str,
             message: str, payload: Dict[str, Any]) -> None:
    try:
        notif_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        payload_json = json.dumps(payload or {})[:4000]
        sql = (
            "UPSERT INTO {table} "
            "(notif_id, username, event_type, severity, title, message, payload_json, is_read, created_at) "
            "VALUES ({notif_id}, {username}, {event_type}, {severity}, {title}, {message}, "
            "{payload_json}, false, '{created_at}')"
        ).format(
            table=_TABLE,
            notif_id=_esc(notif_id),
            username=_esc(username),
            event_type=_esc(event_type),
            severity=_esc(severity),
            title=_esc(title),
            message=_esc(message),
            payload_json=_esc(payload_json),
            created_at=created_at,
        )
        impala_manager.execute_write(sql, database=_DATABASE)
    except Exception as exc:
        logger.debug('notifications._persist failed (non-fatal): %s', exc)


def notify_user(username: str, event_type: str,
                 payload: Optional[Dict[str, Any]] = None,
                 persist: bool = True) -> bool:
    if not username or not isinstance(username, str):
        logger.debug('notify_user called with empty/invalid username — skipped.')
        return False
    p = payload or {}
    severity = EVENT_SEVERITY.get(event_type, SEV_ERROR)
    logger.info('[notify_user] %s -> %s: %s', event_type, username, p)
    if persist:
        title = p.get('title') or EVENT_TITLE.get(event_type) or event_type
        message = p.get('message') or p.get('body') or ''
        _persist(username, event_type, severity, title, message, p)
    return True


def notify_role(role_name: str, event_type: str,
                 payload: Optional[Dict[str, Any]] = None) -> bool:
    logger.info('[notify_role] %s -> role %s: %s', event_type, role_name, payload or {})
    return True


def notify_admins(event_type: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    logger.info('[notify_admins] %s: %s', event_type, payload or {})
    return True


def pop_pending(username: str) -> List[Dict[str, Any]]:
    return []
