"""
Kudu-backed notification store.

Persists notifications to gmp_cis.cis_notification so they survive
Gunicorn worker boundaries (InMemoryChannelLayer is per-process).

The JS client polls /api/notifications/poll/ every 15 s as a fallback
alongside the WebSocket stream.  Only unread rows are returned; they are
marked read on the next poll.  Rows older than 24 h are not returned
(they will be garbage-collected by a management command later).
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

DATABASE  = 'gmp_cis'
TABLE     = 'cis_notification'
FULL_TABLE = f'{DATABASE}.{TABLE}'


def _esc(val: str) -> str:
    if not val:
        return "''"
    s = str(val).replace('\\', '\\\\').replace("'", "\\'")
    return f"'{s}'"


_table_ensured = False


def _ensure_table() -> None:
    """Create cis_notification if it doesn't exist yet. Runs once per process."""
    global _table_ensured
    if _table_ensured:
        return
    try:
        from core.repositories.impala_connection import impala_manager
        impala_manager.execute_write(
            f"""
            CREATE TABLE IF NOT EXISTS {FULL_TABLE} (
                notif_id     STRING NOT NULL,
                username     STRING NOT NULL,
                event_type   STRING,
                severity     STRING,
                title        STRING,
                message      STRING,
                payload_json STRING,
                is_read      BOOLEAN DEFAULT FALSE,
                created_at   TIMESTAMP,
                PRIMARY KEY (notif_id)
            )
            PARTITION BY HASH(notif_id) PARTITIONS 4
            STORED AS KUDU
            TBLPROPERTIES ('kudu.num_tablet_servers' = '1')
            """,
            database=DATABASE
        )
        _table_ensured = True
    except Exception as exc:
        logger.debug('_ensure_table failed (non-fatal): %s', exc)


def store(username: str, event_type: str, severity: str,
          title: str, message: str, payload: Dict[str, Any]) -> bool:
    """Write one notification row to Kudu. Fire-and-forget; never raises."""
    _ensure_table()
    try:
        from core.repositories.impala_connection import impala_manager
        notif_id   = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        payload_json = json.dumps(payload or {})[:4000]

        sql = (
            f"UPSERT INTO {FULL_TABLE} "
            f"(notif_id, username, event_type, severity, title, message, payload_json, is_read, created_at) "
            f"VALUES ("
            f"{_esc(notif_id)}, {_esc(username)}, {_esc(event_type)}, "
            f"{_esc(severity)}, {_esc(title)}, {_esc(message)}, "
            f"{_esc(payload_json)}, false, '{created_at}'"
            f")"
        )
        impala_manager.execute_write(sql, database=DATABASE)
        return True
    except Exception as exc:
        logger.debug('kudu_store.store failed (non-fatal): %s', exc)
        return False


def poll_unread(username: str, since_minutes: int = 60) -> List[Dict[str, Any]]:
    """
    Return unread notifications for username created in the last since_minutes.
    Marks them read immediately after fetching.
    """
    _ensure_table()
    try:
        from core.repositories.impala_connection import impala_manager
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
                  ).strftime('%Y-%m-%d %H:%M:%S')

        rows = impala_manager.execute_query(
            f"""
            SELECT notif_id, event_type, severity, title, message, payload_json, created_at
            FROM {FULL_TABLE}
            WHERE username = {_esc(username)}
              AND is_read  = false
              AND created_at >= '{cutoff}'
            ORDER BY created_at ASC
            """,
            database=DATABASE
        )
        if not rows:
            return []

        # Mark all fetched rows as read
        ids = ', '.join(_esc(r['notif_id']) for r in rows)
        impala_manager.execute_write(
            f"UPDATE {FULL_TABLE} SET is_read = true "
            f"WHERE username = {_esc(username)} AND notif_id IN ({ids})",
            database=DATABASE
        )
        result = []
        for r in rows:
            payload = {}
            try:
                payload = json.loads(r.get('payload_json') or '{}')
            except Exception:
                pass
            result.append({
                'event_type': r.get('event_type', ''),
                'severity':   r.get('severity', 'info'),
                'title':      r.get('title', ''),
                'message':    r.get('message', ''),
                'payload':    payload,
                'timestamp':  str(r.get('created_at', '')),
            })
        return result
    except Exception as exc:
        logger.debug('kudu_store.poll_unread failed (non-fatal): %s', exc)
        return []
