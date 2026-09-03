# Audit System - Comprehensive Documentation

## Overview
The CIS Trade Hive audit system provides comprehensive tracking of all actions in the system. It follows SOLID principles for maintainability and extensibility.

## Design Principles (SOLID)

### Single Responsibility Principle
- **AuditEntry**: Only represents audit data
- **AuditLogger**: Only handles logging operations
- **AuditContext**: Only manages audit context
- **HiveAuditLogger**: Only implements Hive-specific logging

### Open/Closed Principle
- Abstract `AuditLogger` interface allows new implementations
- Middleware can be extended (e.g., `SelectiveAuditMiddleware`)
- Easy to add new action types or categories

### Liskov Substitution Principle
- Any `AuditLogger` implementation can be substituted
- `HiveAuditLogger` and `ConsoleAuditLogger` are interchangeable

### Interface Segregation Principle
- Clean interfaces with only necessary methods
- No client forced to depend on unused methods

### Dependency Inversion Principle
- Code depends on `AuditLogger` abstraction, not concrete implementation
- Easy to swap implementations via configuration

## Architecture

```
┌─────────────────────────────────────────┐
│          Application Layer              │
│  (Views, Services, Business Logic)      │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│         Audit Integration Layer         │
│  - audit_action decorator               │
│  - AuditContext context manager         │
│  - audit_change helper                  │
│  - HiveAuditMiddleware                  │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│          Audit Core Layer               │
│  - AuditLogger (interface)              │
│  - HiveAuditLogger (implementation)     │
│  - AuditEntry (data model)              │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│            Hive Database                │
│  Table: cis_audit_log (30 columns)      │
└─────────────────────────────────────────┘
```

## Components

### 1. Hive Table: cis_audit_log

**Location**: `cis` database
**Format**: TEXT (pipe-delimited)
**Columns**: 30 comprehensive audit fields

**Key Fields**:
- `audit_id`: Unique identifier
- `audit_timestamp`: When the action occurred (ISO 8601)
- `username`, `user_id`, `user_email`: User information
- `action_type`: CREATE, READ, UPDATE, DELETE, LOGIN, etc.
- `action_category`: DATA, AUTH, ADMIN, REPORT, SYSTEM, etc.
- `entity_type`: PORTFOLIO, TRADE, UDF, USER, etc.
- `entity_id`, `entity_name`: What was affected
- `field_name`, `old_value`, `new_value`: Change tracking
- `status`: SUCCESS, FAILURE, PARTIAL
- `duration_ms`: Performance tracking

### 2. Core Audit Modules

**Location**: `core/audit/`

**Files**:
- `audit_models.py`: Data models and enums
- `audit_logger.py`: Logger interface and implementations
- `audit_context.py`: Context managers and decorators
- `__init__.py`: Public API exports

### 3. Django Middleware

**Location**: `core/middleware/audit_middleware_hive.py`

**Classes**:
- `HiveAuditMiddleware`: Auto-audit all HTTP requests
- `SelectiveAuditMiddleware`: Audit specific paths only

## Usage Examples

### Example 1: Using the Decorator

```python
from core.audit import audit_action, ActionType, ActionCategory, EntityType

@audit_action(
    ActionType.CREATE,
    ActionCategory.PORTFOLIO,
    "Create new portfolio"
)
def create_portfolio(request, name, currency):
    """Create a new portfolio with automatic audit logging."""
    portfolio = Portfolio(name=name, currency=currency)
    portfolio.save()
    return portfolio
```

### Example 2: Using Context Manager

```python
from core.audit import AuditContext, ActionType, ActionCategory, EntityType

def update_portfolio_status(request, portfolio_id, new_status):
    """Update portfolio status with audit logging."""

    with AuditContext(
        action_type=ActionType.UPDATE,
        action_category=ActionCategory.PORTFOLIO,
        username=request.user.username,
        action_description=f"Update portfolio {portfolio_id} status",
        entity_type=EntityType.PORTFOLIO,
        entity_id=str(portfolio_id)
    ) as audit_ctx:
        # Get portfolio
        portfolio = Portfolio.objects.get(id=portfolio_id)

        # Set entity name
        audit_ctx.set_entity(
            EntityType.PORTFOLIO,
            str(portfolio_id),
            portfolio.name
        )

        # Update status
        portfolio.status = new_status
        portfolio.save()

        # Add metadata
        audit_ctx.add_metadata('previous_status', portfolio.status)
        audit_ctx.add_metadata('new_status', new_status)
```

### Example 3: Tracking Field Changes

```python
from core.audit import audit_change, EntityType

def update_portfolio_manager(request, portfolio_id, new_manager):
    """Update portfolio manager with change audit."""

    portfolio = Portfolio.objects.get(id=portfolio_id)
    old_manager = portfolio.manager

    with audit_change(
        username=request.user.username,
        entity_type=EntityType.PORTFOLIO,
        entity_id=str(portfolio_id),
        field_name='manager',
        old_value=old_manager,
        new_value=new_manager,
        entity_name=portfolio.name
    ):
        portfolio.manager = new_manager
        portfolio.save()
```

### Example 4: Manual Audit Entry

```python
from core.audit import log_audit, AuditEntry, ActionType, ActionCategory, EntityType, AuditStatus

def custom_action(request):
    """Example of manual audit logging."""

    audit_entry = AuditEntry(
        action_type=ActionType.CALCULATE,
        action_category=ActionCategory.PORTFOLIO,
        username=request.user.username,
        user_id=str(request.user.id),
        user_email=request.user.email,
        action_description="Calculate portfolio valuation",
        entity_type=EntityType.PORTFOLIO,
        entity_id="12345",
        entity_name="Global Equity Fund",
        status=AuditStatus.SUCCESS,
        duration_ms=1250,
        metadata={
            'valuation_date': '2025-12-24',
            'total_value': 10000000.50,
            'currency': 'USD'
        }
    )

    log_audit(audit_entry)
```

### Example 5: Django View with Audit

```python
from django.views import View
from core.audit import audit_action, ActionType, ActionCategory

class PortfolioCreateView(View):

    @audit_action(
        ActionType.CREATE,
        ActionCategory.PORTFOLIO,
        "User created portfolio via web interface",
        capture_args=True
    )
    def post(self, request):
        """Create portfolio with automatic audit."""
        name = request.POST.get('name')
        currency = request.POST.get('currency')

        portfolio = Portfolio(name=name, currency=currency)
        portfolio.save()

        return JsonResponse({
            'id': portfolio.id,
            'name': portfolio.name,
            'status': 'created'
        })
```

### Example 6: Batch Audit Logging

```python
from core.audit import get_audit_logger, AuditEntry, ActionType, ActionCategory

def import_portfolios_from_file(request, file_path):
    """Import portfolios with batch audit logging."""

    audit_logger = get_audit_logger()
    audit_entries = []

    # Process file
    for row in read_csv_file(file_path):
        # Create portfolio
        portfolio = Portfolio(**row)
        portfolio.save()

        # Create audit entry
        entry = AuditEntry(
            action_type=ActionType.IMPORT,
            action_category=ActionCategory.PORTFOLIO,
            username=request.user.username,
            action_description=f"Imported portfolio from file",
            entity_type=EntityType.PORTFOLIO,
            entity_id=str(portfolio.id),
            entity_name=portfolio.name,
            status=AuditStatus.SUCCESS
        )

        audit_entries.append(entry)

    # Log all entries in batch
    audit_logger.log_batch(audit_entries)
```

### Example 7: Querying Audit Logs

```python
from core.audit import get_audit_logger

def get_portfolio_history(portfolio_id):
    """Get complete audit history for a portfolio."""

    audit_logger = get_audit_logger()

    # Get entity history
    history = audit_logger.get_entity_history(
        entity_type='PORTFOLIO',
        entity_id=str(portfolio_id),
        limit=100
    )

    return history

def get_user_activity(username, days=7):
    """Get recent activity for a user."""

    audit_logger = get_audit_logger()

    activity = audit_logger.get_user_activity(
        username=username,
        days=days,
        limit=50
    )

    return activity

def get_failed_actions(action_type=None):
    """Get all failed actions."""

    audit_logger = get_audit_logger()

    filters = {'status': 'FAILURE'}
    if action_type:
        filters['action_type'] = action_type

    failed = audit_logger.query(filters, limit=100)

    return failed
```

## Configuration

### Settings.py

```python
# Audit logging configuration
AUDIT_LOGGER_TYPE = 'hive'  # or 'console' for development

# Middleware configuration
MIDDLEWARE = [
    ...
    'core.middleware.audit_middleware_hive.HiveAuditMiddleware',
    # OR for selective auditing:
    # 'core.middleware.audit_middleware_hive.SelectiveAuditMiddleware',
    ...
]
```

## Action Types

```python
class ActionType(Enum):
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
```

## Action Categories

```python
class ActionCategory(Enum):
    DATA = "DATA"
    AUTH = "AUTH"
    ADMIN = "ADMIN"
    REPORT = "REPORT"
    SYSTEM = "SYSTEM"
    PORTFOLIO = "PORTFOLIO"
    TRADE = "TRADE"
    UDF = "UDF"
```

## Entity Types

```python
class EntityType(Enum):
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
```

## Querying Audit Logs in Hive

### Recent Activity
```sql
SELECT audit_timestamp, username, action_type, entity_type, entity_name, status
FROM cis_audit_log
WHERE audit_date >= '2025-12-01'
ORDER BY audit_timestamp DESC
LIMIT 100;
```

### User Activity
```sql
SELECT audit_timestamp, action_type, action_category, entity_type, status
FROM cis_audit_log
WHERE username = 'john.doe'
  AND audit_date >= '2025-12-17'
ORDER BY audit_timestamp DESC;
```

### Failed Actions
```sql
SELECT audit_timestamp, username, action_type, entity_type, error_message
FROM cis_audit_log
WHERE status = 'FAILURE'
  AND audit_date >= '2025-12-01';
```

### Portfolio Changes
```sql
SELECT audit_timestamp, username, field_name, old_value, new_value
FROM cis_audit_log
WHERE entity_type = 'PORTFOLIO'
  AND entity_id = '12345'
  AND action_type = 'UPDATE'
ORDER BY audit_timestamp DESC;
```

### Performance Analysis
```sql
SELECT action_type,
       AVG(duration_ms) as avg_duration,
       MAX(duration_ms) as max_duration,
       MIN(duration_ms) as min_duration
FROM cis_audit_log
WHERE audit_date >= '2025-12-01'
GROUP BY action_type;
```

## Best Practices

### 1. Use Appropriate Action Types
```python
# DO: Use specific action types
audit_entry.action_type = ActionType.REVALUE  # For portfolio revaluation

# DON'T: Use generic types
audit_entry.action_type = ActionType.UPDATE  # Too generic
```

### 2. Provide Meaningful Descriptions
```python
# DO: Clear, actionable descriptions
action_description = "Updated portfolio SGD-EQUITY manager from John to Jane"

# DON'T: Vague descriptions
action_description = "Updated portfolio"
```

### 3. Track Field-Level Changes
```python
# DO: Use audit_change for field updates
with audit_change(username, EntityType.PORTFOLIO, id, 'status', 'Active', 'Inactive'):
    portfolio.status = 'Inactive'

# DON'T: Just log the action without details
AuditEntry(action_type=ActionType.UPDATE, ...)
```

### 4. Include Context in Metadata
```python
# DO: Add relevant metadata
audit_entry.metadata = {
    'request_id': request_id,
    'batch_id': batch_id,
    'source_file': 'portfolios.csv',
    'row_number': 42
}
```

### 5. Handle Errors Gracefully
```python
# DO: Audit failures with details
try:
    process_portfolio()
except Exception as e:
    audit_entry.status = AuditStatus.FAILURE
    audit_entry.error_message = str(e)
    audit_entry.error_traceback = traceback.format_exc()
    log_audit(audit_entry)
    raise
```

## Testing

### Unit Test Example
```python
from core.audit import AuditEntry, ActionType, ActionCategory, HiveAuditLogger

def test_audit_logging():
    """Test audit entry creation and logging."""
    logger = HiveAuditLogger()

    entry = AuditEntry(
        action_type=ActionType.CREATE,
        action_category=ActionCategory.PORTFOLIO,
        username='test_user',
        action_description='Test audit entry',
        entity_type=EntityType.PORTFOLIO,
        entity_id='test_123'
    )

    result = logger.log(entry)
    assert result == True
```

## Maintenance

### Archiving Old Audit Logs
```sql
-- Create archive table for old logs
CREATE TABLE cis_audit_log_archive
AS SELECT * FROM cis_audit_log
WHERE audit_date < '2025-01-01';

-- Delete archived records
-- Note: Be cautious with this operation
INSERT OVERWRITE TABLE cis_audit_log
SELECT * FROM cis_audit_log
WHERE audit_date >= '2025-01-01';
```

### Monitoring Audit System Health
```sql
-- Check recent audit activity
SELECT audit_date, COUNT(*) as log_count
FROM cis_audit_log
WHERE audit_date >= '2025-12-01'
GROUP BY audit_date
ORDER BY audit_date DESC;

-- Check for gaps in auditing
SELECT DISTINCT audit_date
FROM cis_audit_log
WHERE audit_date BETWEEN '2025-12-01' AND '2025-12-24'
ORDER BY audit_date;
```

## Summary

The audit system provides:
- ✓ Comprehensive tracking of all system actions
- ✓ SOLID principles for maintainability
- ✓ Multiple integration patterns (decorator, context manager, manual)
- ✓ Automatic HTTP request auditing via middleware
- ✓ Performance tracking with duration metrics
- ✓ Detailed error tracking with stack traces
- ✓ Flexible querying capabilities
- ✓ Extensible design for future requirements

---
**Created**: 2025-12-24
**Database**: cis
**Table**: cis_audit_log
**Status**: ✓ Production Ready
