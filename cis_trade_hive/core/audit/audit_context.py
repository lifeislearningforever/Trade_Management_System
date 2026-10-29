"""
Audit context manager and decorator for easy audit logging.
Follows SOLID principles and makes audit logging seamless.
"""

from contextlib import contextmanager
from functools import wraps
from typing import Optional, Callable, Any
import time
import traceback
import logging

from .audit_models import AuditEntry, ActionType, ActionCategory, AuditStatus, EntityType
from .audit_logger import get_audit_logger

logger = logging.getLogger(__name__)


class AuditContext:
    """
    Context manager for tracking actions with automatic audit logging.
    Follows Single Responsibility Principle.
    """

    def __init__(self,
                 action_type: ActionType,
                 action_category: ActionCategory,
                 username: str,
                 action_description: Optional[str] = None,
                 entity_type: Optional[EntityType] = None,
                 entity_id: Optional[str] = None,
                 entity_name: Optional[str] = None,
                 **kwargs):
        """
        Initialize audit context.

        Args:
            action_type: Type of action
            action_category: Category of action
            username: Username performing the action
            action_description: Description of the action
            entity_type: Type of entity being acted upon
            entity_id: ID of the entity
            entity_name: Name of the entity
            **kwargs: Additional audit entry fields
        """
        self.action_type = action_type
        self.action_category = action_category
        self.username = username
        self.action_description = action_description
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.entity_name = entity_name
        self.extra_fields = kwargs

        self.start_time = None
        self.end_time = None
        self.status = AuditStatus.SUCCESS
        self.error_message = None
        self.error_traceback = None
        self.audit_logger = get_audit_logger()

    def __enter__(self):
        """Enter context - start timing."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - log audit entry."""
        self.end_time = time.time()
        duration_ms = int((self.end_time - self.start_time) * 1000)

        # Determine status
        if exc_type is not None:
            self.status = AuditStatus.FAILURE
            self.error_message = str(exc_val)
            self.error_traceback = ''.join(traceback.format_tb(exc_tb))

        # Create audit entry
        audit_entry = AuditEntry(
            action_type=self.action_type,
            action_category=self.action_category,
            username=self.username,
            action_description=self.action_description,
            entity_type=self.entity_type,
            entity_id=self.entity_id,
            entity_name=self.entity_name,
            status=self.status,
            error_message=self.error_message,
            error_traceback=self.error_traceback,
            duration_ms=duration_ms,
            **self.extra_fields
        )

        # Log the audit entry
        try:
            self.audit_logger.log(audit_entry)
        except Exception as e:
            logger.error(f"Failed to log audit entry: {str(e)}")

        # Don't suppress exceptions
        return False

    def set_entity(self, entity_type: EntityType, entity_id: str, entity_name: Optional[str] = None):
        """
        Set entity information during the context.

        Args:
            entity_type: Type of entity
            entity_id: ID of the entity
            entity_name: Optional name of the entity
        """
        self.entity_type = entity_type
        self.entity_id = entity_id
        if entity_name:
            self.entity_name = entity_name

    def add_metadata(self, key: str, value: Any):
        """
        Add metadata during the context.

        Args:
            key: Metadata key
            value: Metadata value
        """
        if 'metadata' not in self.extra_fields:
            self.extra_fields['metadata'] = {}
        self.extra_fields['metadata'][key] = value


def audit_action(action_type: ActionType,
                 action_category: ActionCategory,
                 action_description: Optional[str] = None,
                 entity_type: Optional[EntityType] = None,
                 capture_args: bool = False):
    """
    Decorator for automatic audit logging of functions.

    Args:
        action_type: Type of action
        action_category: Category of action
        action_description: Description of the action
        entity_type: Type of entity (if applicable)
        capture_args: Whether to capture function arguments in metadata

    Usage:
        @audit_action(ActionType.CREATE, ActionCategory.PORTFOLIO, "Create portfolio")
        def create_portfolio(name, currency):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to extract username from first argument (often 'request' or 'self')
            username = 'system'
            request = None

            if args:
                first_arg = args[0]
                # Check if it's a Django request object
                if hasattr(first_arg, 'user'):
                    request = first_arg
                    username = first_arg.user.username if first_arg.user.is_authenticated else 'anonymous'
                # Check if it's a Django view instance (self)
                elif hasattr(first_arg, 'request'):
                    request = first_arg.request
                    username = request.user.username if request.user.is_authenticated else 'anonymous'

            # Prepare metadata
            metadata = {
                'function_name': func.__name__,
                'module_name': func.__module__,
            }

            if capture_args:
                metadata['args'] = str(args[1:]) if args else str(args)  # Skip first arg (self/request)
                metadata['kwargs'] = str(kwargs)

            # Create context
            with AuditContext(
                action_type=action_type,
                action_category=action_category,
                username=username,
                action_description=action_description or f"{func.__name__}",
                entity_type=entity_type,
                function_name=func.__name__,
                module_name=func.__module__,
                metadata=metadata
            ) as ctx:
                # Execute function
                result = func(*args, **kwargs)

                # Try to extract entity information from result
                if result and isinstance(result, dict):
                    if 'id' in result and entity_type:
                        ctx.set_entity(entity_type, str(result['id']), result.get('name'))

                return result

        return wrapper

    return decorator


@contextmanager
def audit_change(username: str,
                 entity_type: EntityType,
                 entity_id: str,
                 field_name: str,
                 old_value: Any,
                 new_value: Any,
                 entity_name: Optional[str] = None):
    """
    Context manager for auditing field changes.

    Args:
        username: Username making the change
        entity_type: Type of entity being changed
        entity_id: ID of the entity
        field_name: Name of the field being changed
        old_value: Original value
        new_value: New value
        entity_name: Optional name of the entity

    Usage:
        with audit_change('john', EntityType.PORTFOLIO, '123', 'status', 'Active', 'Inactive'):
            portfolio.status = 'Inactive'
            portfolio.save()
    """
    audit_logger = get_audit_logger()
    start_time = time.time()

    try:
        yield

        # Success - log the change
        duration_ms = int((time.time() - start_time) * 1000)

        audit_entry = AuditEntry(
            action_type=ActionType.UPDATE,
            action_category=ActionCategory.DATA,
            username=username,
            action_description=f"Updated {field_name} on {entity_type.value}",
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            field_name=field_name,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            status=AuditStatus.SUCCESS,
            duration_ms=duration_ms
        )

        audit_logger.log(audit_entry)

    except Exception as e:
        # Failure - log the attempt
        duration_ms = int((time.time() - start_time) * 1000)

        audit_entry = AuditEntry(
            action_type=ActionType.UPDATE,
            action_category=ActionCategory.DATA,
            username=username,
            action_description=f"Failed to update {field_name} on {entity_type.value}",
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            field_name=field_name,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            status=AuditStatus.FAILURE,
            error_message=str(e),
            error_traceback=traceback.format_exc(),
            duration_ms=duration_ms
        )

        audit_logger.log(audit_entry)
        raise


def log_audit(audit_entry: AuditEntry) -> bool:
    """
    Simple helper to log an audit entry.

    Args:
        audit_entry: AuditEntry to log

    Returns:
        bool: True if successful, False otherwise
    """
    audit_logger = get_audit_logger()
    return audit_logger.log(audit_entry)
