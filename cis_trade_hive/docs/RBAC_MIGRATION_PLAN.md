# Role-Based Access Control (RBAC) Migration Plan

## Overview
Migration from current ACL tables to new role-based tables structure.

---

## Current Tables (OLD)

| Table | Purpose | Columns |
|-------|---------|---------|
| `cis_user` | User master | cis_user_id, login, name, entity, email, domain, cis_user_group_id, is_deleted, enabled |
| `cis_user_group` | Group definitions | cis_user_group_id, name, entity, description, is_deleted |
| `cis_group_permissions` | Group → Permission mapping | cis_group_permissions_id, cis_user_group_id, permission, read_write, is_deleted |

**Current Flow:**
```
User → cis_user_group_id → cis_user_group → cis_group_permissions
```

---

## New Tables (TARGET)

| Table | Purpose | Records | Columns |
|-------|---------|---------|---------|
| `cis_user_info` | User master | ~24+ | user_id, login, email, name, default_entity, last_login, is_active, is_deleted, created_on/by, updated_on/by |
| `cis_user_group_info` | Group definitions | 12 | user_group_id, group_name, description, entity, is_active, is_deleted, created_on/by, updated_on/by |
| `cis_permission_info` | Permission definitions | 98 | permission_id, permission_name, entity, description, is_active, is_deleted, created_on/by, updated_on/by |
| `cis_user_group_mapping_info` | User → Group mapping | ~24+ | user_group_mapping_id, user_id, entity, group_name, is_active, is_deleted, created_on/by, updated_on/by |
| `cis_group_permission_map` | Group → Permission mapping | 981 | (Need to create) group_permission_id, group_name, permission_name, entity, mode, description, is_active, is_deleted |

**New Flow:**
```
User (cis_user_info)
  → cis_user_group_mapping_info (user_id → group_name)
  → cis_group_permission_map (group_name → permission_name + mode)
```

---

## Key Differences

| Aspect | OLD | NEW |
|--------|-----|-----|
| User-Group relation | Direct FK (cis_user_group_id) | Mapping table (cis_user_group_mapping_info) |
| Group ID | Integer (cis_user_group_id) | String (group_name: SG-TRADER, SG-TCOE) |
| Permission storage | permission + read_write columns | permission_name + mode (READ/READ_WRITE) |
| Multi-group support | No (1 user = 1 group) | Yes (user can belong to multiple groups) |
| Entity awareness | Basic | Full entity filtering |

---

## Migration Strategy

### Phase 1: Create New Repository (Parallel Operation)
**File:** `core/repositories/acl_repository_v2.py`

Create new repository that queries new tables while keeping old repository functional.

```python
class ACLRepositoryV2:
    """New RBAC repository for cis_user_info, cis_user_group_info, etc."""

    def get_user_by_login(self, login: str) -> Optional[Dict]:
        """Query cis_user_info instead of cis_user"""

    def get_user_groups(self, user_id: str) -> List[Dict]:
        """Get all groups for user from cis_user_group_mapping_info"""

    def get_group_permissions(self, group_name: str) -> List[Dict]:
        """Query cis_group_permission_map for permissions"""

    def has_permission(self, user_id: str, permission: str, mode: str = 'READ') -> bool:
        """Check permission across all user's groups"""
```

### Phase 2: Feature Flag
**File:** `config/settings.py`

```python
# RBAC Version: 'v1' (old tables) or 'v2' (new tables)
RBAC_VERSION = os.environ.get('RBAC_VERSION', 'v1')
```

### Phase 3: Repository Factory
**File:** `core/repositories/acl_repository.py`

```python
def get_acl_repository():
    """Factory to return appropriate ACL repository based on settings."""
    from django.conf import settings

    if getattr(settings, 'RBAC_VERSION', 'v1') == 'v2':
        from .acl_repository_v2 import ACLRepositoryV2
        return ACLRepositoryV2()
    else:
        return ACLRepository()  # Original
```

### Phase 4: DDL for Missing Table
**Table:** `cis_group_permission_map` (981 records)

```sql
CREATE TABLE gmp_cis.cis_group_permission_map (
    group_permission_id STRING,
    group_name STRING,
    permission_name STRING,
    entity STRING,
    mode STRING,  -- READ, READ_WRITE
    description STRING,
    is_active BOOLEAN,
    is_deleted BOOLEAN,
    created_on TIMESTAMP,
    created_by STRING,
    updated_on TIMESTAMP,
    updated_by STRING,
    PRIMARY KEY (group_permission_id)
)
PARTITION BY HASH(group_permission_id) PARTITIONS 4
STORED AS KUDU;
```

---

## Rollback Strategy

### Quick Rollback (< 1 minute)
```bash
# Set environment variable
export RBAC_VERSION=v1

# Restart application
systemctl restart cis_trade_hive
```

### Code Rollback
```bash
# Revert to previous commit
git revert <migration_commit_hash>
git push origin cis_trade_hive
```

### Files to Track for Rollback
| File | Action |
|------|--------|
| `core/repositories/acl_repository.py` | Modified (factory function) |
| `core/repositories/acl_repository_v2.py` | NEW (can delete) |
| `config/settings.py` | Modified (RBAC_VERSION) |
| `sql/ddl/XX_rbac_tables.sql` | NEW (DDL for tables) |

---

## Implementation Order

1. **Create DDL** for `cis_group_permission_map` table
2. **Create** `acl_repository_v2.py` with new table queries
3. **Add** `RBAC_VERSION` setting to config
4. **Modify** `get_acl_repository()` to use factory pattern
5. **Test** with `RBAC_VERSION=v2` in development
6. **Deploy** with `RBAC_VERSION=v1` (old tables still in use)
7. **Switch** to `RBAC_VERSION=v2` after validation
8. **Monitor** for issues, rollback if needed

---

## Column Mapping

### User Table
| OLD (cis_user) | NEW (cis_user_info) |
|----------------|---------------------|
| cis_user_id | user_id |
| login | login |
| name | name |
| entity | default_entity |
| email | email |
| cis_user_group_id | (via cis_user_group_mapping_info) |
| enabled | is_active |
| is_deleted | is_deleted |

### Group Table
| OLD (cis_user_group) | NEW (cis_user_group_info) |
|----------------------|---------------------------|
| cis_user_group_id | user_group_id |
| name | group_name |
| description | description |
| entity | entity |
| is_deleted | is_deleted |

### Permission Mapping
| OLD (cis_group_permissions) | NEW (cis_group_permission_map) |
|-----------------------------|--------------------------------|
| cis_group_permissions_id | group_permission_id |
| cis_user_group_id | group_name (string, not FK) |
| permission | permission_name |
| read_write | mode |
| is_deleted | is_deleted |

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Query performance | Test with full dataset, add indexes |
| Missing permissions | Validate 981 records loaded correctly |
| Multi-group logic | Test users with multiple groups |
| Rollback failure | Maintain old repository untouched |
| Session conflicts | Clear sessions on switch |

---

## Testing Checklist

- [ ] Login with existing user works
- [ ] Permissions correctly evaluated
- [ ] Multi-group users get union of permissions
- [ ] Entity filtering works
- [ ] Rollback to v1 works instantly
- [ ] No performance degradation
- [ ] Audit logging captures correct user info

---

## Timeline

| Phase | Duration | Description |
|-------|----------|-------------|
| 1 | 2 hours | Create DDL and load data |
| 2 | 4 hours | Implement ACLRepositoryV2 |
| 3 | 1 hour | Add feature flag and factory |
| 4 | 2 hours | Testing in development |
| 5 | - | Deploy to UAT/Production |

**Total estimated effort: 9 hours**

---

## How to Use Permissions in Views

### Method 1: @require_permission Decorator (Function-Based Views)

```python
from core.views.auth_views import require_login, require_permission

# READ permission - user can view
@require_login
@require_permission('portfolio-list', 'READ')
def portfolio_list(request):
    """List all portfolios - requires READ access"""
    portfolios = portfolio_service.list_all()
    return render(request, 'portfolio/list.html', {'portfolios': portfolios})

# WRITE permission - user can create/edit
@require_login
@require_permission('portfolio-create', 'READ_WRITE')
def portfolio_create(request):
    """Create portfolio - requires WRITE access"""
    if request.method == 'POST':
        # Create portfolio logic
        pass
    return render(request, 'portfolio/create.html')

# Multiple permissions check
@require_login
@require_permission('trade-approval', 'READ_WRITE')
def trade_approve(request, trade_id):
    """Approve trade - requires WRITE access to trade-approval"""
    pass
```

### Method 2: Manual Permission Check in View

```python
from core.views.auth_views import require_login

@require_login
def portfolio_detail(request, portfolio_name):
    """View with conditional actions based on permissions"""

    # Get user's permission map from session
    permission_map = request.session.get('user_permissions', {})

    # Check specific permissions
    can_edit = permission_map.get('portfolio-edit') in ['WRITE', 'READ_WRITE']
    can_delete = permission_map.get('portfolio-delete') in ['WRITE', 'READ_WRITE']
    can_approve = permission_map.get('portfolio-approval') in ['WRITE', 'READ_WRITE']

    portfolio = portfolio_service.get_by_name(portfolio_name)

    return render(request, 'portfolio/detail.html', {
        'portfolio': portfolio,
        'can_edit': can_edit,
        'can_delete': can_delete,
        'can_approve': can_approve,
    })
```

### Method 3: Permission Check in Templates

```html
<!-- In template, use passed context variables -->
{% if can_edit %}
    <a href="{% url 'portfolio:edit' portfolio.name %}" class="btn btn-primary">
        <i class="bi bi-pencil"></i> Edit
    </a>
{% endif %}

{% if can_delete %}
    <button type="button" class="btn btn-danger" data-bs-toggle="modal" data-bs-target="#deleteModal">
        <i class="bi bi-trash"></i> Delete
    </button>
{% endif %}

{% if can_approve and portfolio.status == 'PENDING_APPROVAL' %}
    <button type="button" class="btn btn-success">
        <i class="bi bi-check-circle"></i> Approve
    </button>
{% endif %}
```

### Method 4: Helper Function for Permission Checks

```python
# In core/services/permission_service.py

def has_permission(request, permission_name: str, mode: str = 'READ') -> bool:
    """
    Check if current user has specified permission.

    Args:
        request: HttpRequest object
        permission_name: Permission name (e.g., 'portfolio-edit')
        mode: 'READ', 'WRITE', or 'READ_WRITE'

    Returns:
        bool: True if user has permission
    """
    permission_map = request.session.get('user_permissions', {})
    user_access = permission_map.get(permission_name)

    if mode == 'READ':
        return user_access in ['READ', 'WRITE', 'READ_WRITE']
    elif mode == 'WRITE':
        return user_access in ['WRITE', 'READ_WRITE']
    elif mode == 'READ_WRITE':
        return user_access == 'READ_WRITE'

    return False

def get_user_permissions(request) -> dict:
    """Get all permissions for current user."""
    return request.session.get('user_permissions', {})

# Usage in view
from core.services.permission_service import has_permission

@require_login
def trade_list(request):
    can_create = has_permission(request, 'trade-create', 'WRITE')
    can_approve = has_permission(request, 'trade-approval', 'WRITE')

    return render(request, 'trade/list.html', {
        'can_create': can_create,
        'can_approve': can_approve,
    })
```

---

## Permission Naming Convention (98 Permissions)

Based on the PERMISSION_MASTER data:

| Module | Permissions | Mode Options |
|--------|-------------|--------------|
| **Portfolio** | portfolio-list, portfolio-view, portfolio-create, portfolio-edit, portfolio-delete, portfolio-download, portfolio-approval | READ, READ_WRITE |
| **Trade** | trade-list, trade-view, trade-create, trade-edit, trade-delete, trade-download, trade-approval | READ, READ_WRITE |
| **Position** | position-list, position-view, position-create, position-edit, position-delete, position-download, position-approval | READ, READ_WRITE |
| **Securities** | securities-list, securities-view, securities-create, securities-edit, securities-delete, securities-download, securities-approval | READ, READ_WRITE |
| **Parties** | parties-list, parties-view, parties-create, parties-edit, parties-delete, parties-download | READ, READ_WRITE |
| **UDF** | udf-list, udf-view, udf-create, udf-edit, udf-delete, udf-download, udf-approval | READ, READ_WRITE |
| **Cash Flow** | cash-flow-list, cash-flow-view, cash-flow-create, cash-flow-edit, cash-flow-approval | READ, READ_WRITE |
| **Corp Actions** | corp-action-list, corp-action-view, corp-action-create, corp-action-edit, corp-action-approval | READ, READ_WRITE |
| **Reference Data** | currencies-list, currencies-view, countries-list, countries-view, calendars-list, calendars-view, calendars-edit | READ, READ_WRITE |
| **Market Data** | equity-prices-list, equity-prices-view, equity-prices-create, equity-prices-edit, fx-rates-list, fx-rates-view | READ, READ_WRITE |
| **Reports** | online-reports-list, online-reports-view, market-data-dashboard | READ |
| **Admin** | audit-logs-read, documentation-read, lookup-tables-list, lookup-tables-edit | READ, READ_WRITE |

---

## Example: Applying Permissions to Trade Views

```python
# trade/views.py

from core.views.auth_views import require_login, require_permission

@require_login
@require_permission('trade-list', 'READ')
def trade_list(request):
    """List trades - READ permission required"""
    permission_map = request.session.get('user_permissions', {})

    context = {
        'trades': trade_service.list_all(),
        'can_create': permission_map.get('trade-create') in ['WRITE', 'READ_WRITE'],
        'can_approve': permission_map.get('trade-approval') in ['WRITE', 'READ_WRITE'],
    }
    return render(request, 'trade/trade_list.html', context)


@require_login
@require_permission('trade-create', 'READ_WRITE')
def trade_create(request):
    """Create trade - WRITE permission required"""
    # Only users with trade-create WRITE access can reach here
    pass


@require_login
@require_permission('trade-view', 'READ')
def trade_detail(request, trade_id):
    """View trade details - READ permission required"""
    permission_map = request.session.get('user_permissions', {})

    trade = trade_service.get_by_id(trade_id)

    context = {
        'trade': trade,
        'can_edit': permission_map.get('trade-edit') in ['WRITE', 'READ_WRITE'],
        'can_delete': permission_map.get('trade-delete') in ['WRITE', 'READ_WRITE'],
        'can_approve': (
            permission_map.get('trade-approval') in ['WRITE', 'READ_WRITE']
            and trade.get('status') == 'PENDING_APPROVAL'
            and trade.get('created_by') != request.session.get('user_login')  # Four-eyes
        ),
    }
    return render(request, 'trade/trade_detail.html', context)


@require_login
@require_permission('trade-approval', 'READ_WRITE')
def trade_approve(request, trade_id):
    """Approve trade - WRITE permission + Four-eyes check"""
    trade = trade_service.get_by_id(trade_id)

    # Four-eyes principle: Cannot approve own trade
    if trade.get('created_by') == request.session.get('user_login'):
        return HttpResponse("Cannot approve your own trade", status=403)

    if request.method == 'POST':
        trade_service.approve(trade_id, request.session.get('user_login'))
        return redirect('trade:list')

    return render(request, 'trade/trade_approve.html', {'trade': trade})
```

---

## Contact

For rollback or issues:
- Set `RBAC_VERSION=v1` in environment
- Restart application
- No database changes needed for rollback
