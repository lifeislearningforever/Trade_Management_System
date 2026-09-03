# Users, Roles & Permissions (RBAC)

> **Audience:** Admin, SA, Developer, Support
> **Read time:** ~10 minutes

---

## Plain English

RBAC stands for **Role-Based Access Control**. The idea is simple:

1. Users are assigned to one or more **groups** (e.g. Trader, Checker, Risk)
2. Groups are assigned **permissions** (e.g. `trade-create`, `portfolio-approve`)
3. When a user tries to do something, the system checks if any of their groups have the required permission

If they don't have permission: access is denied and the event is logged.

---

## Roles (Groups)

| Group | What they can do |
|-------|----------------|
| **TRADER** | Create/edit trades and portfolios; view positions and market data |
| **CHECKER** | Approve/reject trades and portfolios; view everything |
| **ADMIN** | All permissions including user management |
| **RISK** | View-only: positions, corporate actions, market data |
| **SUPPORT** | View-only: audit log, trades, positions |
| **BA/SA** | View-only access to most modules for analysis |

Groups can be combined — a user can be both TRADER and CHECKER in different portfolios (but cannot approve their own trades).

---

## Permissions

| Permission | What it controls |
|------------|----------------|
| `trade-create` | Create new trades |
| `trade-read` | View trades |
| `trade-update` | Edit draft/INITIAL trades |
| `trade-delete` | Soft-delete trades |
| `trade-approve` | Validate/approve pending trades |
| `portfolio-create` | Create new portfolios |
| `portfolio-read` | View portfolios |
| `portfolio-update` | Edit draft portfolios |
| `portfolio-delete` | Soft-delete portfolios |
| `portfolio-approve` | Approve pending portfolios |
| `reference-data-create` | Create securities, counterparties, CAs |
| `reference-data-read` | View reference data |
| `reference-data-update` | Edit reference data |
| `reference-data-delete` | Delete reference data |
| `udf-create` | Create UDF field definitions |
| `udf-read` | View UDF fields and values |
| `udf-update` | Edit UDF values |
| `udf-delete` | Delete UDF fields |
| `audit-read` | View audit log |
| `market-data-read` | View FX rates and prices |
| `position-read` | View portfolio positions |
| `position-create` | Manually trigger position recalculation |
| `ca-read` | View corporate actions |
| `ca-create` | Enter corporate actions |
| `ca-process` | Run CA processing |

---

## RBAC Version 2 (Current)

CIS has two versions of RBAC. **V2 is the current, production version.** V1 is legacy (single group per user).

### V2 Tables

| Table | Purpose |
|-------|---------|
| `cis_user_info` | User accounts — login, name, is_active |
| `cis_user_group_info` | Group definitions — group name, description |
| `cis_permission_info` | All available permissions |
| `cis_user_group_mapping_info` | Which user belongs to which group(s) |
| `cis_group_permission_map` | Which group has which permission, with what access mode |

### V2 Data Model

```
cis_user_info
    │ (many-to-many via mapping table)
    │
cis_user_group_mapping_info ─── cis_user_group_info
                                       │ (many-to-many via permission map)
                                       │
                             cis_group_permission_map ─── cis_permission_info
                                       │
                                  access_mode: READ or READ_WRITE
```

### Permission Aggregation Rule

If a user is in multiple groups, permissions are **aggregated**:
- `READ_WRITE > READ` — if any group gives READ_WRITE, the user has READ_WRITE
- Permissions add up — a user gets the union of all groups' permissions

Example:
```
User Alice is in:
  Group TRADER  → trade-create: READ_WRITE, portfolio-read: READ
  Group RISK    → position-read: READ_WRITE

Aggregated permissions for Alice:
  trade-create:   READ_WRITE   (from TRADER)
  portfolio-read: READ         (from TRADER)
  position-read:  READ_WRITE   (from RISK)
```

### Permission Cache

Permissions are cached per user for **5 minutes**. If a user's permissions are changed, it takes up to 5 minutes to take effect (or until the user logs in again).

---

## RBAC V1 (Legacy)

V1 is still in the codebase for backward compatibility. It uses:
- `cis_user` — user accounts
- `cis_user_group` — single group per user (FK)
- `cis_group` — group definitions
- `cis_group_permissions` — group-permission mapping

V1 limitation: **one group per user**. That's why V2 was built.

Switch between V1 and V2 via environment variable: `RBAC_VERSION=v1` or `RBAC_VERSION=v2`.

---

## How Authentication Works

CIS does not use Active Directory or SSO (currently). Authentication is checked against the Kudu user tables directly:

```
User enters username + password
  │
  ▼ ACLService.authenticate(username, password)
  │
  ▼ ACLRepository queries cis_user_info (V2) or cis_user (V1)
  │   SELECT * FROM gmp_cis.cis_user_info
  │   WHERE user_login = 'alice' AND is_active = true
  │
  ▼ Password validated (hashed comparison)
  │
  ▼ Django session created
  │
  ▼ User permissions loaded and cached (5 minutes)
  │
  ▼ Redirect to dashboard
```

---

## How Authorisation Is Enforced

Every page and action is protected at two levels:

**Level 1: URL-level (middleware)**
```
permission_middleware.py runs on EVERY request
  → Looks up the URL pattern in PERMISSION_MAP
  → Checks if user has required permission
  → If no: 403 Forbidden, logged to cis_audit_log
```

**Level 2: Template-level**
```
In HTML templates, action buttons are conditionally shown:
{% if user_permissions.trade_approve %}
    <button>Validate Trade</button>
{% endif %}
```

**Level 3: Service-level (business rules)**
```
Services have explicit checks:
if trade.created_by == request.user.username:
    raise PermissionDenied("Cannot approve your own trade")
```

---

## Four-Eyes Enforcement (Within RBAC)

The Four-Eyes rule is enforced in the service layer, not RBAC:
- A user with `trade-approve` permission still cannot approve a trade they created
- This is checked by comparing `trade.created_by` against the approving user
- Same logic applies to portfolios

---

## For Admins: Adding a New User

Currently done directly in Kudu via impala-shell or a management command:

```sql
-- V2: Add user
UPSERT INTO gmp_cis.cis_user_info
(user_id, user_login, user_name, email, is_active, created_at)
VALUES (gen_uuid(), 'alice', 'Alice Smith', 'alice@company.com', true, now());

-- Assign to a group
UPSERT INTO gmp_cis.cis_user_group_mapping_info
(mapping_id, user_id, group_id, is_active)
VALUES (gen_uuid(), '<alice_user_id>', '<trader_group_id>', true);
```

---

## For Developers: Key Files

| File | Purpose |
|------|---------|
| `core/repositories/acl_repository_v2.py` | RBAC V2 — permission loading and caching |
| `core/repositories/acl_repository.py` | RBAC V1 (legacy) |
| `core/services/acl_service.py` | Auth + permission checking API |
| `core/middleware/permission_middleware.py` | URL-level permission enforcement |
| `sql/ddl/50_rbac_tables_kudu.sql` | V2 table DDL |
| `sql/ddl/52_rbac_seed_permissions.sql` | Seed all permission definitions |
| `sql/ddl/05_acl_tables_kudu.sql` | V1 table DDL |

---

## For Support: Common Issues

| Issue | Check |
|-------|-------|
| User gets 403 on a page | Check their group assignments in `cis_user_group_mapping_info` |
| User can't see Validate button | Check if they have `trade-approve` permission in their groups |
| Permissions changed but user still has old access | 5-minute cache — wait or have them log out and back in |
| User not found at login | Check `cis_user_info` — is `is_active = true`? Is `user_login` spelled correctly? |
| User in wrong group | Update `cis_user_group_mapping_info` — set old mapping `is_active = false`, add new row |
