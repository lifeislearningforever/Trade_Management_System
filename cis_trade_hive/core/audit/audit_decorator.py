"""
Audit Decorator for Repository Write Operations

Provides a decorator that automatically creates audit entries for
CREATE, UPDATE, and DELETE operations without blocking the main operation.

Author: CisTrade Team
Last Updated: 2026-01-25
"""

import time
import json
import logging
import threading
from functools import wraps
from typing import Callable, Optional, Any, Dict

logger = logging.getLogger(__name__)

# Thread-local storage for current user context
_thread_local = threading.local()


def set_current_user(username: str, user_id: str = '0'):
    """
    Set current user context for audit logging.
    Call this in middleware or view to establish user context.
    """
    _thread_local.username = username
    _thread_local.user_id = user_id


def get_current_user() -> tuple:
    """Get current user from thread-local storage."""
    username = getattr(_thread_local, 'username', 'SYSTEM')
    user_id = getattr(_thread_local, 'user_id', '0')
    return username, user_id


def audit_write(
    action_type: str,
    entity_type: str,
    get_entity_id: Optional[Callable] = None,
    get_entity_name: Optional[Callable] = None,
    capture_old_value: bool = False
):
    """
    Decorator for repository write methods that automatically creates audit entries.

    Features:
    - Non-blocking: Audit is queued asynchronously
    - Captures old/new values for UPDATE and DELETE
    - Measures operation duration
    - Never fails the main operation even if audit fails

    Args:
        action_type: 'CREATE', 'UPDATE', or 'DELETE'
        entity_type: Entity type (e.g., 'EQUITY_PRICE', 'TRADE', 'PORTFOLIO')
        get_entity_id: Optional function to extract entity ID from (args, kwargs, result)
        get_entity_name: Optional function to extract entity name from (args, kwargs, result)
        capture_old_value: If True, captures existing record before UPDATE/DELETE

    Usage:
        class MyRepository:
            @audit_write('CREATE', 'EQUITY_PRICE',
                         get_entity_id=lambda a, k, r: k.get('data', {}).get('id'))
            def insert(self, data, username='SYSTEM'):
                # ... insert logic
                return True

            @audit_write('UPDATE', 'EQUITY_PRICE',
                         get_entity_id=lambda a, k, r: a[0] if a else None,
                         capture_old_value=True)
            def update(self, entity_id, data, username='SYSTEM'):
                # ... update logic
                return True
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Extract username from kwargs or use current user
            username = kwargs.get('username') or kwargs.get('created_by') or kwargs.get('updated_by')
            if not username:
                username, _ = get_current_user()

            # Capture old value for UPDATE/DELETE operations
            old_value = None
            entity_id = None

            if capture_old_value and action_type in ('UPDATE', 'DELETE'):
                try:
                    # Try to extract entity ID from args
                    if args:
                        entity_id = args[0]  # Usually first arg is ID
                    elif get_entity_id:
                        entity_id = get_entity_id(args, kwargs, None)

                    # Get current record for audit comparison
                    if entity_id and hasattr(self, '_get_record_for_audit'):
                        old_value = self._get_record_for_audit(entity_id)
                    elif entity_id and hasattr(self, 'get_by_id'):
                        old_value = self.get_by_id(entity_id)
                except Exception as e:
                    logger.warning(f"Failed to capture old value for audit: {e}")

            # Execute the actual operation
            start_time = time.time()
            success = False
            error_msg = None
            result = None

            try:
                result = func(self, *args, **kwargs)
                success = bool(result)
            except Exception as e:
                error_msg = str(e)
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)

                # Queue audit entry (fire and forget)
                _queue_audit_entry(
                    action_type=action_type,
                    entity_type=entity_type,
                    entity_id=_extract_value(get_entity_id, args, kwargs, result, entity_id),
                    entity_name=_extract_value(get_entity_name, args, kwargs, result, None),
                    old_value=old_value,
                    new_value=_extract_new_value(action_type, args, kwargs) if success else None,
                    success=success,
                    error_message=error_msg,
                    duration_ms=duration_ms,
                    username=username
                )

            return result
        return wrapper
    return decorator


def _extract_value(
    extractor: Optional[Callable],
    args: tuple,
    kwargs: dict,
    result: Any,
    default: Any
) -> Any:
    """Extract value using provided extractor function."""
    if extractor is None:
        return default

    try:
        return extractor(args, kwargs, result)
    except Exception as e:
        logger.debug(f"Value extraction failed: {e}")
        return default


def _extract_new_value(action_type: str, args: tuple, kwargs: dict) -> Optional[Dict]:
    """Extract new value from operation arguments."""
    try:
        # Look for common data parameter names
        for key in ['data', 'equity_price_data', 'trade_data', 'portfolio_data']:
            if key in kwargs:
                return kwargs[key]

        # For CREATE, first dict-like arg might be data
        if action_type == 'CREATE':
            for arg in args:
                if isinstance(arg, dict):
                    return arg

        # For UPDATE, second arg is often the data
        if action_type == 'UPDATE' and len(args) >= 2:
            if isinstance(args[1], dict):
                return args[1]

        return None

    except Exception:
        return None


def _queue_audit_entry(
    action_type: str,
    entity_type: str,
    entity_id: Any,
    entity_name: Optional[str],
    old_value: Optional[Dict],
    new_value: Optional[Dict],
    success: bool,
    error_message: Optional[str],
    duration_ms: int,
    username: str
):
    """
    Queue audit entry for async processing in a separate thread.
    This function is completely non-blocking - it spawns a daemon thread
    to handle the audit entry and returns immediately.
    """
    def _do_queue():
        try:
            from core.audit.async_audit_queue import async_audit_queue

            # Serialize old/new values
            old_value_str = None
            new_value_str = None

            if old_value:
                try:
                    old_value_str = json.dumps(old_value, default=str)
                except Exception:
                    old_value_str = str(old_value)

            if new_value:
                try:
                    new_value_str = json.dumps(new_value, default=str)
                except Exception:
                    new_value_str = str(new_value)

            # Build audit entry
            audit_data = {
                'action_type': action_type,
                'action_category': 'DATA',
                'entity_type': entity_type,
                'entity_id': str(entity_id) if entity_id else '',
                'entity_name': str(entity_name) if entity_name else '',
                'action_description': _build_description(action_type, entity_type, entity_id, entity_name, success),
                'old_value': old_value_str,
                'new_value': new_value_str,
                'status': 'SUCCESS' if success else 'FAILURE',
                'status_code': 200 if success else 500,
                'duration_ms': duration_ms,
                'username': username,
                'user_id': '0'  # Can be enhanced to include actual user_id
            }

            # Non-blocking enqueue
            queued = async_audit_queue.enqueue(audit_data)

            if queued:
                logger.debug(
                    f"Audit queued: {action_type} {entity_type} "
                    f"#{entity_id} by {username} ({duration_ms}ms)"
                )
            else:
                logger.warning(
                    f"Audit queue full, entry will go to fallback: "
                    f"{action_type} {entity_type} #{entity_id}"
                )

        except Exception as e:
            # Never let audit logging break the main operation
            logger.error(f"Failed to queue audit entry: {e}")

    # Spawn daemon thread to handle audit - returns immediately
    audit_thread = threading.Thread(target=_do_queue, daemon=True)
    audit_thread.start()


def _build_description(
    action_type: str,
    entity_type: str,
    entity_id: Any,
    entity_name: Optional[str],
    success: bool
) -> str:
    """Build human-readable audit description."""
    action_verb = {
        'CREATE': 'Created',
        'UPDATE': 'Updated',
        'DELETE': 'Deleted'
    }.get(action_type, action_type)

    entity_display = entity_type.replace('_', ' ').title()

    if entity_name:
        desc = f"{action_verb} {entity_display}: {entity_name}"
    elif entity_id:
        desc = f"{action_verb} {entity_display} #{entity_id}"
    else:
        desc = f"{action_verb} {entity_display}"

    if not success:
        desc += " (FAILED)"

    return desc


# Helper function for simple audit logging without decorator
def log_audit(
    action_type: str,
    entity_type: str,
    entity_id: Any = None,
    entity_name: str = None,
    old_value: Dict = None,
    new_value: Dict = None,
    success: bool = True,
    error_message: str = None,
    username: str = None
):
    """
    Log an audit entry without using the decorator.

    Useful for complex operations where decorator doesn't fit.

    Args:
        action_type: 'CREATE', 'UPDATE', 'DELETE'
        entity_type: Entity type string
        entity_id: Entity identifier
        entity_name: Entity name/label
        old_value: Previous value (dict)
        new_value: New value (dict)
        success: Whether operation succeeded
        error_message: Error message if failed
        username: User who performed the action
    """
    if username is None:
        username, _ = get_current_user()

    _queue_audit_entry(
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        old_value=old_value,
        new_value=new_value,
        success=success,
        error_message=error_message,
        duration_ms=0,
        username=username
    )
