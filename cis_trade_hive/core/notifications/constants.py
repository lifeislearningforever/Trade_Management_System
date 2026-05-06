"""
Notification event types and channel group name helpers.

Group naming convention:
  user_{username}        — notifications for a specific user
  role_{role_name}       — notifications for all users in a role/group
  admin_all              — broadcast to all admin users
"""

# ── Event types ──────────────────────────────────────────────────────────────

# AVP / position queue
EVT_AVP_QUEUED      = 'avp_queued'
EVT_AVP_PROCESSING  = 'avp_processing'
EVT_AVP_COMPLETED   = 'avp_completed'
EVT_AVP_FAILED      = 'avp_failed'
EVT_AVP_DEAD_LETTER = 'avp_dead_letter'
EVT_AVP_SLA_BREACH  = 'avp_sla_breach'

# Upload / ETL pipeline
EVT_UPLOAD_STARTED   = 'upload_started'
EVT_UPLOAD_STEP      = 'upload_step'
EVT_UPLOAD_COMPLETED = 'upload_completed'
EVT_UPLOAD_FAILED    = 'upload_failed'

# Trade lifecycle
EVT_TRADE_CREATED   = 'trade_created'
EVT_TRADE_APPROVED  = 'trade_approved'
EVT_TRADE_REJECTED  = 'trade_rejected'
EVT_TRADE_SETTLED   = 'trade_settled'

# System
EVT_SYSTEM_ERROR    = 'system_error'
EVT_PING            = 'ping'
EVT_PONG            = 'pong'

# Severity levels (used by the UI to colour toasts)
SEV_INFO    = 'info'
SEV_SUCCESS = 'success'
SEV_WARNING = 'warning'
SEV_ERROR   = 'error'

# Default severity per event type
EVENT_SEVERITY = {
    EVT_AVP_QUEUED:      SEV_INFO,
    EVT_AVP_PROCESSING:  SEV_INFO,
    EVT_AVP_COMPLETED:   SEV_SUCCESS,
    EVT_AVP_FAILED:      SEV_ERROR,
    EVT_AVP_DEAD_LETTER: SEV_ERROR,
    EVT_AVP_SLA_BREACH:  SEV_WARNING,
    EVT_UPLOAD_STARTED:  SEV_INFO,
    EVT_UPLOAD_STEP:     SEV_INFO,
    EVT_UPLOAD_COMPLETED: SEV_SUCCESS,
    EVT_UPLOAD_FAILED:   SEV_ERROR,
    EVT_TRADE_CREATED:   SEV_INFO,
    EVT_TRADE_APPROVED:  SEV_SUCCESS,
    EVT_TRADE_REJECTED:  SEV_WARNING,
    EVT_TRADE_SETTLED:   SEV_SUCCESS,
    EVT_SYSTEM_ERROR:    SEV_ERROR,
}

# Channel group names
ADMIN_GROUP = 'admin_all'


def user_group(username: str) -> str:
    """Channel group name for a specific user. Sanitises username."""
    safe = ''.join(c if c.isalnum() or c in ('-', '_', '.') else '_' for c in username)
    return f'user_{safe}'


def role_group(role_name: str) -> str:
    """Channel group name for a role/permission group."""
    safe = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in role_name)
    return f'role_{safe}'
