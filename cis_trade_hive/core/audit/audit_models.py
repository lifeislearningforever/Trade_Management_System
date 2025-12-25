"""
Audit models and enums following SOLID principles.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
import json


class ActionType(Enum):
    """Types of actions that can be audited."""
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EXPORT = "EXPORT"
    IMPORT = "IMPORT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CALCULATE = "CALCULATE"
    REVALUE = "REVALUE"


class ActionCategory(Enum):
    """Categories of actions."""
    DATA = "DATA"
    AUTH = "AUTH"
    ADMIN = "ADMIN"
    REPORT = "REPORT"
    SYSTEM = "SYSTEM"
    PORTFOLIO = "PORTFOLIO"
    TRADE = "TRADE"
    UDF = "UDF"


class AuditStatus(Enum):
    """Status of audited actions."""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"


class EntityType(Enum):
    """Types of entities that can be audited."""
    PORTFOLIO = "PORTFOLIO"
    TRADE = "TRADE"
    UDF = "UDF"
    UDF_VALUE = "UDF_VALUE"
    USER = "USER"
    USER_GROUP = "USER_GROUP"
    PERMISSION = "PERMISSION"
    CURRENCY = "CURRENCY"
    COUNTRY = "COUNTRY"
    COUNTERPARTY = "COUNTERPARTY"
    CALENDAR = "CALENDAR"


@dataclass
class AuditEntry:
    """
    Comprehensive audit entry data model.
    Follows Single Responsibility Principle - only represents audit data.
    """
    # Required fields
    action_type: ActionType
    action_category: ActionCategory
    username: str

    # Optional identification
    audit_id: Optional[int] = None
    audit_timestamp: Optional[str] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None

    # Action details
    action_description: Optional[str] = None

    # Entity information
    entity_type: Optional[EntityType] = None
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None

    # Change tracking
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None

    # Request information
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    request_params: Optional[Dict[str, Any]] = None

    # Result information
    status: AuditStatus = AuditStatus.SUCCESS
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None

    # Context information
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    # Additional metadata
    module_name: Optional[str] = None
    function_name: Optional[str] = None
    duration_ms: Optional[int] = None
    tags: Optional[list] = field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    # Partitioning
    audit_date: Optional[str] = None

    def __post_init__(self):
        """Post-initialization to set defaults."""
        if self.audit_timestamp is None:
            self.audit_timestamp = datetime.utcnow().isoformat()

        if self.audit_date is None:
            self.audit_date = datetime.utcnow().strftime('%Y-%m-%d')

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit entry to dictionary."""
        data = asdict(self)

        # Convert enums to their values
        data['action_type'] = self.action_type.value if self.action_type else None
        data['action_category'] = self.action_category.value if self.action_category else None
        data['status'] = self.status.value if self.status else None
        data['entity_type'] = self.entity_type.value if self.entity_type else None

        # Convert complex fields to JSON strings
        if self.request_params:
            data['request_params'] = json.dumps(self.request_params)

        if self.tags:
            data['tags'] = ','.join(self.tags)

        if self.metadata:
            data['metadata'] = json.dumps(self.metadata)

        return data

    def to_hive_values(self) -> tuple:
        """Convert to tuple for Hive insertion."""
        data = self.to_dict()

        return (
            data.get('audit_id'),
            data.get('audit_timestamp'),
            data.get('user_id'),
            data.get('username'),
            data.get('user_email'),
            data.get('action_type'),
            data.get('action_category'),
            data.get('action_description'),
            data.get('entity_type'),
            data.get('entity_id'),
            data.get('entity_name'),
            data.get('field_name'),
            data.get('old_value'),
            data.get('new_value'),
            data.get('request_method'),
            data.get('request_path'),
            data.get('request_params'),
            data.get('status'),
            data.get('status_code'),
            data.get('error_message'),
            data.get('error_traceback'),
            data.get('session_id'),
            data.get('ip_address'),
            data.get('user_agent'),
            data.get('module_name'),
            data.get('function_name'),
            data.get('duration_ms'),
            data.get('tags'),
            data.get('metadata'),
            data.get('audit_date'),
        )

    @classmethod
    def from_request(cls, request, action_type: ActionType,
                     action_category: ActionCategory, **kwargs):
        """
        Create audit entry from Django request object.

        Args:
            request: Django HttpRequest object
            action_type: Type of action
            action_category: Category of action
            **kwargs: Additional audit entry fields

        Returns:
            AuditEntry instance
        """
        # Extract user information
        username = request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'anonymous'
        user_id = str(request.user.id) if hasattr(request, 'user') and request.user.is_authenticated else None
        user_email = request.user.email if hasattr(request, 'user') and request.user.is_authenticated else None

        # Extract request information
        request_method = request.method
        request_path = request.path

        # Get request parameters
        request_params = {}
        if request.method == 'GET':
            request_params = dict(request.GET.items())
        elif request.method in ['POST', 'PUT', 'PATCH']:
            request_params = dict(request.POST.items())

        # Get session and context info
        session_id = request.session.session_key if hasattr(request, 'session') else None
        ip_address = cls._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT')

        return cls(
            action_type=action_type,
            action_category=action_category,
            username=username,
            user_id=user_id,
            user_email=user_email,
            request_method=request_method,
            request_path=request_path,
            request_params=request_params,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            **kwargs
        )

    @staticmethod
    def _get_client_ip(request) -> Optional[str]:
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
