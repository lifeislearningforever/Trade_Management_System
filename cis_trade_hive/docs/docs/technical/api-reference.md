# API Reference

Quick reference for service and repository methods.

## Portfolio Service

**Location**: `portfolio/services/portfolio_service.py`

### Core Methods

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `create_portfolio()` | user, data | Portfolio | Create new portfolio in Draft |
| `update_portfolio()` | portfolio, user, data | Portfolio | Update Draft/Rejected only |
| `submit_for_approval()` | portfolio, user | Portfolio | Submit Draft → Pending |
| `approve_portfolio()` | portfolio, user, comments | Portfolio | Approve → Active |
| `reject_portfolio()` | portfolio, user, comments | Portfolio | Reject with reason |
| `close_portfolio()` | code, user_id, username, email, reason | bool | Close Active → Inactive |
| `reactivate_portfolio()` | code, user_id, username, email, comments | bool | Reactivate Inactive → Active |

### Query Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `list_portfolios(status, search, currency)` | QuerySet | Filter portfolios |
| `get_pending_approvals()` | QuerySet | Pending items |
| `get_portfolio_by_id(id)` | Portfolio | Get by ID |
| `get_portfolio_by_code(code)` | Portfolio | Get by code |

## Portfolio Repository

**Location**: `portfolio/repositories/portfolio_hive_repository.py`

### Methods

```python
get_all_portfolios(limit=100, status=None, search=None, currency=None) -> List[Dict]
get_portfolio_by_code(code: str) -> Optional[Dict]
update_portfolio_status(code, status, is_active, updated_by) -> bool
insert_portfolio_history(code, action, status, changes, comments, performed_by) -> bool
```

## Audit Repository

**Location**: `core/audit/audit_kudu_repository.py`

```python
log_action(user_id, username, user_email, action_type, entity_type,
           entity_id, entity_name, action_description, request_method, status) -> bool
```

## Help Repository

**Location**: `core/repositories/help_repository.py`

```python
get_help_content(module, page, section=None) -> List[Dict]
get_all_help() -> List[Dict]
```

## Usage Examples

### Create Portfolio
```python
from portfolio.services import PortfolioService

portfolio = PortfolioService.create_portfolio(
    user=request.user,
    data={
        'code': 'PF001',
        'name': 'Test Portfolio',
        'currency': 'USD',
        'manager': 'John Smith'
    }
)
```

### Query Portfolios
```python
portfolios = PortfolioService.list_portfolios(
    status='Active',
    search='USD',
    currency='USD'
)
```

### Log Audit
```python
from core.audit.audit_kudu_repository import audit_log_kudu_repository

audit_log_kudu_repository.log_action(
    user_id='123',
    username='jsmith',
    user_email='jsmith@company.com',
    action_type='CREATE',
    entity_type='PORTFOLIO',
    entity_id='PF001',
    entity_name='Test Portfolio',
    action_description='Created portfolio PF001',
    request_method='POST',
    status='SUCCESS'
)
```

---

For complete implementation details, see [Architecture](architecture.md) and [Database Schema](database-schema.md).
