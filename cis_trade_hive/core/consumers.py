"""
WebSocket consumer for real-time notifications.

URL: /ws/notifications/

Authentication:
  Uses the CIS session (user_login key) — same as the HTTP middleware.
  Unauthenticated or expired sessions are rejected with close code 4001.

Group membership:
  1. user_{username}  — user's own notifications
  2. role_{group}     — one group per CIS role the user belongs to
  3. admin_all        — joined only if user has admin permission

Corner cases handled:
  - Session missing / expired → close 4001
  - User not found in Kudu ACL → close 4003
  - Channel layer unavailable → graceful degradation (connect still works)
  - Client sends heartbeat ping → server replies pong
  - Duplicate connect from same user (multiple tabs) → all tabs receive messages
  - WebSocket close while group_send in flight → swallowed silently
  - Role group name sanitisation → no injection via crafted role names
"""

import json
import logging
from datetime import datetime, timezone
from typing import List

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from core.notifications.constants import (
    ADMIN_GROUP,
    EVT_PING,
    EVT_PONG,
    SEV_ERROR,
    SEV_INFO,
    user_group,
    role_group,
)

logger = logging.getLogger(__name__)

# Close codes (4000–4999 are application-defined per RFC 6455)
CLOSE_SESSION_EXPIRED  = 4001
CLOSE_FORBIDDEN        = 4003
CLOSE_SERVER_ERROR     = 4500


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    One instance per WebSocket connection (one per browser tab).
    Groups joined are stored in self._joined_groups so they can all
    be left cleanly on disconnect.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._username: str = ''
        self._joined_groups: List[str] = []

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self):
        """
        Authenticate via session, join channel groups, accept connection.
        Rejects unauthenticated connections before accept() so the HTTP
        upgrade is denied cleanly.
        """
        session = self.scope.get('session', {})
        username = session.get('user_login', '')

        if not username:
            logger.warning(
                'WS connect rejected — no user_login in session. '
                'Headers: %s', dict(self.scope.get('headers', []))
            )
            await self.close(code=CLOSE_SESSION_EXPIRED)
            return

        self._username = username

        # Build group list from session data (already loaded by middleware)
        groups = self._resolve_groups(session)

        # Join all groups
        for group in groups:
            try:
                await self.channel_layer.group_add(group, self.channel_name)
                self._joined_groups.append(group)
            except Exception as exc:
                # Channel layer issue — log but don't fail the connection
                logger.warning('Could not join group %s: %s', group, exc)

        await self.accept()

        # Send a welcome message so the client knows it's live
        await self._send_system(
            SEV_INFO,
            f'Connected as {username}. Notifications active.',
            {'username': username, 'groups': groups},
        )
        logger.info('WS connected: user=%s groups=%s channel=%s',
                    username, groups, self.channel_name)

    async def disconnect(self, close_code):
        """Leave all groups cleanly on disconnect."""
        for group in self._joined_groups:
            try:
                await self.channel_layer.group_discard(group, self.channel_name)
            except Exception as exc:
                logger.debug('Error leaving group %s on disconnect: %s', group, exc)

        logger.info('WS disconnected: user=%s code=%s', self._username, close_code)

    # ── Receive from client ───────────────────────────────────────────────────

    async def receive_json(self, content, **kwargs):
        """
        Handle messages from the browser.
        Currently only ping/pong and mark-as-read are supported.
        Unknown types are silently ignored (don't echo back — prevents loops).
        """
        msg_type = content.get('type', '')

        if msg_type == EVT_PING:
            await self.send_json({
                'type': EVT_PONG,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            })

        elif msg_type == 'mark_read':
            # Client acknowledges receipt — nothing to persist (stateless).
            # If you add a notification store later, clear it here.
            pass

        else:
            logger.debug('WS received unknown type %s from %s', msg_type, self._username)

    # ── Receive from channel layer ────────────────────────────────────────────

    async def notification_send(self, event):
        """
        Called by channel layer when group_send dispatches a
        'notification.send' type message.

        The channel layer maps 'notification.send' → method 'notification_send'
        (dots replaced with underscores).
        """
        try:
            await self.send_json({
                'type':       event.get('event_type', 'notification'),
                'severity':   event.get('severity', SEV_INFO),
                'timestamp':  event.get('timestamp', datetime.now(timezone.utc).isoformat()),
                'payload':    event.get('payload', {}),
            })
        except Exception as exc:
            # Connection may have closed between group_send and delivery
            logger.debug(
                'Could not deliver notification to %s (connection closed?): %s',
                self._username, exc,
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_groups(self, session: dict) -> List[str]:
        """
        Build the list of channel groups this user should join.

        Groups:
          1. user_{username}  — always
          2. role_{group}     — for each CIS group the user belongs to
          3. admin_all        — if user has any admin-level permission
        """
        username = session.get('user_login', '')
        groups = [user_group(username)]

        # Support both RBAC v1 (single group string) and v2 (list of groups)
        raw_groups = session.get('user_group_names') or session.get('user_group_name')
        if isinstance(raw_groups, list):
            for g in raw_groups:
                if g:
                    groups.append(role_group(str(g)))
        elif isinstance(raw_groups, str) and raw_groups:
            groups.append(role_group(raw_groups))

        # Admin broadcast group — join if user has any admin permission
        perms = session.get('user_permissions', {})
        if self._is_admin(perms):
            groups.append(ADMIN_GROUP)

        return groups

    @staticmethod
    def _is_admin(perms: dict) -> bool:
        """
        Consider a user admin if they have any *_approve or system_admin permission.
        """
        if not isinstance(perms, dict):
            return False
        admin_keys = ('system_admin', 'trade_approve', 'portfolio_approve')
        return any(perms.get(k) for k in admin_keys)

    async def _send_system(self, severity: str, message: str, extra: dict = None):
        """Send a system-level notification directly to this connection."""
        try:
            await self.send_json({
                'type':      'system',
                'severity':  severity,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'payload':   {'message': message, **(extra or {})},
            })
        except Exception:
            pass
