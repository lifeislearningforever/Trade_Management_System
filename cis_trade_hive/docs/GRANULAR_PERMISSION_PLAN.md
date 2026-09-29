# Granular Permission (Resource-Level Access Control) Plan

## Document Info

| Field | Value |
|-------|-------|
| **Document Type** | Design & Implementation Plan |
| **Module** | Core — RBAC / ACL (All Modules) |
| **Created Date** | 2026-06-24 |
| **Last Updated** | 2026-06-24 |
| **Status** | Pending SA / User Approval |
| **Author** | CIS Trade Hive Dev Team |
| **Reviewers** | SA Team, Operations Lead |

---

## 1. Executive Summary

The current RBAC system controls access at the **module level** (e.g., a user can see the entire Trade module or not at all). This plan introduces **resource-level (granular) access control** across all 10 modules so that specific groups can be restricted to individual resources within a module.

Examples:
- **Lookup** — Team A sees only `lut_broker`; Team B sees only `lut_charge_type`
- **Trade / Position / Cash Flow** — Operations team sees only their entity's portfolios
- **Security** — Fixed Income team sees only BOND securities; Equity team sees only EQUITY
- **Market Data** — FX team can upload FX rates but not equity prices
- **Query Builder** — Analysts can query only approved tables; no raw SQL access
- **Reference Data** — SG team sees only SG counterparties and parties

The design uses a **single new Kudu table** (`cis_group_resource_scope`) shared across all modules. It is **backward compatible** — existing group/permission assignments require no changes. Restriction is opt-in: if no scope is configured for a group, it retains full access to the module.

---

## 2. Problem Statement

### 2.1 Current Behaviour

```
Group  ──► Permission (module-level)  ──► Access to ALL resources in that module
```

Example:
- Group `OPS-TEAM` has `lookup-tables-list` READ permission
- Result: they can see and browse **all** 20+ lookup tables

### 2.2 Required Behaviour

```
Group  ──► Permission (module-level)  ──► Scope (specific resources only)
```

Example:
- Group `OPS-TEAM` has `lookup-tables-list` READ, scoped to `lut_broker`, `lut_settlement_type`
- Group `FINANCE-TEAM` has `lookup-tables-list` READ, scoped to `lut_charge_type`, `lut_fee_schedule`
- Group `ADMIN` has `lookup-tables-list` READ, **no scope** → sees all tables

### 2.3 Scope of This Plan

The primary driver is the **Lookup Tables module**, where different teams need access to different tables. The design is generalisable to other modules (Portfolio filter by entity, Query Builder table access, etc.) in future phases.

---

## 3. Current System Architecture

### 3.1 RBAC Tables (as implemented)

| Table | Purpose |
|-------|---------|
| `cis_user_info` | User master (user_id, login, email, is_active) |
| `cis_user_group_info` | Group definitions (group_name, entity, description) |
| `cis_permission_info` | Permission catalogue (permission_name, description) |
| `cis_user_group_mapping_info` | User ↔ Group mapping (many-to-many) |
| `cis_group_permission_map` | Group ↔ Permission mapping (permission_name, mode: READ / READ_WRITE) |

### 3.2 Permission Check Flow (current)

```
HTTP Request
    │
    ▼
PermissionMiddleware
    │   reads URL_PERMISSION_MAP → (permission_name, mode)
    ▼
ACLService.has_permission(user, permission_name)
    │   queries cis_group_permission_map for user's groups
    ▼
Allow / 403 Deny
```

### 3.3 URL Permission Map (Lookup entries)

```python
'lookup:table_list':    ('lookup-tables-list', 'READ'),
'lookup:table_detail':  ('lookup-tables-list', 'READ'),
'lookup:row_create':    ('lookup-tables-edit', 'WRITE'),
'lookup:row_edit':      ('lookup-tables-edit', 'WRITE'),
'lookup:row_delete':    ('lookup-tables-edit', 'WRITE'),
```

---

## 4. Proposed Design

### 4.1 New Table: `cis_group_resource_scope`

A **scope table** that optionally restricts which resources a group can access within a permission.

```sql
CREATE TABLE gmp_cis.cis_group_resource_scope (
  scope_id        INT           COMMENT 'Unique scope record ID (primary key)',
  group_name      STRING        COMMENT 'FK → cis_user_group_info.group_name',
  permission_name STRING        COMMENT 'FK → cis_permission_info.permission_name',
  resource_type   STRING        COMMENT 'Resource category: LOOKUP_TABLE | PORTFOLIO | QUERY_TABLE',
  resource_name   STRING        COMMENT 'Specific resource name, or * for all',
  is_active       BOOLEAN       COMMENT 'Soft enable/disable flag',
  created_by      STRING        COMMENT 'Who created this scope entry',
  created_at      TIMESTAMP     COMMENT 'Creation timestamp',
  updated_by      STRING        COMMENT 'Who last updated this entry',
  updated_at      TIMESTAMP     COMMENT 'Last update timestamp'
)
COMMENT 'Resource-level scope restrictions per group+permission'
PRIMARY KEY (scope_id)
PARTITION BY HASH(scope_id) PARTITIONS 4
STORED AS KUDU;
```

### 4.2 Scope Resolution Rules

| Condition | Result |
|-----------|--------|
| No rows exist for `group + permission + resource_type` | **No restriction** — full access (backward compatible) |
| Row exists with `resource_name = '*'` | **No restriction** — explicit wildcard |
| One or more rows with specific `resource_name` values | **Restricted** — only listed resources allowed |

### 4.3 Access Check Flow (proposed)

```
HTTP Request to /lookup/<table_name>/
    │
    ▼
PermissionMiddleware  (unchanged — checks lookup-tables-list READ)
    │
    ▼
LookupTableDetailView.get(table_name)
    │
    ▼
ACLService.get_allowed_resources(user, 'lookup-tables-list', 'LOOKUP_TABLE')
    │
    ├── returns None          → no restriction, proceed
    └── returns {'lut_broker','lut_settlement_type'}
            │
            ├── table_name IN set → proceed
            └── table_name NOT IN set → 403 Forbidden
```

---

## 5. Detailed Design — Component by Component

### 5.1 Database (DDL)

**New file:** `sql/ddl/24_resource_scope_kudu.sql`

- Creates `cis_group_resource_scope` table as above
- No changes to existing ACL tables
- No data migration required

---

### 5.2 ACL Service — New Method

**File:** `core/services/acl_service.py`

```python
def get_allowed_resources(
    self,
    user: User,
    permission_name: str,
    resource_type: str
) -> Optional[Set[str]]:
    """
    Return the set of resource names this user is allowed to access,
    or None if there is no restriction.

    Returns:
        None         — no restriction (full access)
        Set[str]     — explicit allowed set (may be empty if all scopes inactive)
    """
```

**Cache key:** `acl_scope_{user_id}_{permission_name}_{resource_type}` — same 300s TTL as existing permission cache.

**Query:**
```sql
SELECT rs.resource_name
FROM gmp_cis.cis_group_resource_scope rs
JOIN gmp_cis.cis_user_group_mapping_info ug ON rs.group_name = ug.group_name
JOIN gmp_cis.cis_user_info u ON ug.user_id = u.user_id
WHERE u.login = %s
  AND rs.permission_name = %s
  AND rs.resource_type = %s
  AND rs.is_active = TRUE
  AND ug.is_active = TRUE
  AND u.is_active = TRUE
```

---

### 5.3 Lookup Repository — Filtered Discovery

**File:** `lookup/repositories/lookup_kudu_repository.py`

`discover_lookup_tables()` accepts an optional `allowed_tables: Optional[Set[str]]` parameter:

```python
def discover_lookup_tables(
    self,
    allowed_tables: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    # ... existing discovery logic ...
    if allowed_tables is not None:
        tables = [t for t in tables if t['table_name'] in allowed_tables]
    return tables
```

`get_table_info(table_name, allowed_tables)` — returns `None` if `table_name` not in `allowed_tables`.

---

### 5.4 Lookup Views — Enforce Scope

**File:** `lookup/views.py`

```python
class LookupTableListView(View):
    def get(self, request):
        allowed = acl_service.get_allowed_resources(
            request.user, 'lookup-tables-list', 'LOOKUP_TABLE'
        )
        tables = lookup_service.get_all_lookup_tables(allowed_tables=allowed)
        # ... render as before ...

class LookupTableDetailView(View):
    def get(self, request, table_name):
        allowed = acl_service.get_allowed_resources(
            request.user, 'lookup-tables-list', 'LOOKUP_TABLE'
        )
        if allowed is not None and table_name not in allowed:
            raise PermissionDenied("You do not have access to this lookup table.")
        # ... existing logic ...
```

---

### 5.5 RBAC Admin UI — Manage Scopes

**New RBAC admin page:** `Group Detail → Resource Scopes` tab

The existing RBAC admin (at `/core/rbac/`) already manages users, groups, and permission assignments. A new **Resource Scopes** sub-section would be added to the Group edit page:

```
Group: OPS-TEAM
├── Permissions (existing tab)
│   ├── lookup-tables-list   READ ✓
│   └── cash-flow-list       READ ✓
│
└── Resource Scopes (new tab)
    ├── Permission: lookup-tables-list  │  Type: LOOKUP_TABLE
    │   ├── lut_broker          ✓ Active
    │   ├── lut_settlement_type ✓ Active
    │   └── [+ Add Table]
    └── (no scope for cash-flow-list → full access)
```

**RBAC Admin URL entries needed:**

```python
'core:rbac_group_scopes':      ('rbac-admin', 'READ'),
'core:rbac_group_scope_add':   ('rbac-admin', 'WRITE'),
'core:rbac_group_scope_remove':('rbac-admin', 'WRITE'),
```

---

## 6. What Changes, What Does Not

### 6.1 Changes Required

| Layer | File | Change |
|-------|------|--------|
| Database | `sql/ddl/24_resource_scope_kudu.sql` | New table `cis_group_resource_scope` |
| ACL Service | `core/services/acl_service.py` | New method `get_allowed_resources()` |
| Lookup Repo | `lookup/repositories/lookup_kudu_repository.py` | Filter by `allowed_tables` param |
| Lookup Service | `lookup/services/lookup_service.py` | Pass `allowed_tables` through |
| Lookup Views | `lookup/views.py` | Call `get_allowed_resources()`, enforce scope |
| RBAC Admin | `core/views_rbac.py` + templates | New scope management UI |
| Permission Map | `core/permissions_map.py` | Add 3 new RBAC scope URL entries |

### 6.2 No Changes Required

| Area | Reason |
|------|--------|
| Existing ACL tables | No schema change — new table is additive |
| All other modules (Trade, Portfolio, etc.) | Unaffected until Phase 2+ |
| Existing group/permission assignments | All continue to work as-is |
| Middleware (`acl_middleware.py`) | No change — scope check is in views, not middleware |
| Login / session handling | No change |

---

## 7. Phased Rollout

### Phase 1 — Lookup Tables (This Plan)

| Step | Task | Owner | Estimate |
|------|------|-------|----------|
| 1.1 | Create DDL `24_resource_scope_kudu.sql` and run on local/UAT | Dev | 0.5d |
| 1.2 | Add `get_allowed_resources()` to ACL service + unit tests | Dev | 1d |
| 1.3 | Filter in Lookup repo/service/views | Dev | 0.5d |
| 1.4 | RBAC Admin UI — scope management tab | Dev | 1.5d |
| 1.5 | UAT testing with real group configs | QA + Ops | 1d |
| **Total** | | | **~4.5 days** |

### Phase 2 — Query Builder Table Restrictions

- `resource_type = 'QUERY_TABLE'`
- Restrict which DB tables a group can query in the query builder
- Same `cis_group_resource_scope` table, no additional DDL

### Phase 3 — Portfolio Entity Scoping (optional)

- `resource_type = 'PORTFOLIO'`
- Certain groups see only portfolios matching their entity (e.g., SG portfolios only)
- Requires integration with portfolio list view and API endpoints

---

## 8. Example Data

### 8.1 Scenario: Three Teams, Different Lookup Access

**Groups and their lookup scope:**

| Group | Tables Allowed |
|-------|---------------|
| `OPS-TEAM` | `lut_broker`, `lut_settlement_type`, `lut_custodian` |
| `FINANCE-TEAM` | `lut_charge_type`, `lut_fee_schedule`, `lut_withholding_tax` |
| `ADMIN` | *(no scope = all tables)* |
| `AUDIT-TEAM` | *(no scope = all tables, read-only via permission)* |

**`cis_group_resource_scope` rows for this scenario:**

```
scope_id | group_name    | permission_name     | resource_type | resource_name
---------|---------------|---------------------|---------------|----------------------
1        | OPS-TEAM      | lookup-tables-list  | LOOKUP_TABLE  | lut_broker
2        | OPS-TEAM      | lookup-tables-list  | LOOKUP_TABLE  | lut_settlement_type
3        | OPS-TEAM      | lookup-tables-list  | LOOKUP_TABLE  | lut_custodian
4        | FINANCE-TEAM  | lookup-tables-list  | LOOKUP_TABLE  | lut_charge_type
5        | FINANCE-TEAM  | lookup-tables-list  | LOOKUP_TABLE  | lut_fee_schedule
6        | FINANCE-TEAM  | lookup-tables-list  | LOOKUP_TABLE  | lut_withholding_tax
```

*(No rows for ADMIN or AUDIT-TEAM → they see all tables)*

### 8.2 What Each User Sees

| User | Group | Lookup Table List Shows |
|------|-------|------------------------|
| alice | OPS-TEAM | lut_broker, lut_settlement_type, lut_custodian |
| bob | FINANCE-TEAM | lut_charge_type, lut_fee_schedule, lut_withholding_tax |
| carol | ADMIN | All 20+ lut_* tables |
| dave (OPS + FINANCE multi-group) | Both | Union: lut_broker + lut_settlement_type + lut_custodian + lut_charge_type + lut_fee_schedule + lut_withholding_tax |

---

## 9. Security Considerations

| Concern | How It Is Addressed |
|---------|---------------------|
| Direct URL access to restricted table | `table_detail` view checks scope before serving data — 403 returned even if URL is typed directly |
| API endpoint abuse | `lookup:api_table` also checks scope in view layer |
| Cache poisoning | Scope cache is keyed by `user_id + permission + resource_type` — no cross-user leakage |
| Privilege escalation | Only users with `rbac-admin` WRITE can manage scopes (same gate as all RBAC admin actions) |
| Empty scope set | If a group has scope rows but all are `is_active = FALSE`, user sees nothing (explicit deny) — ops team must add at least one active row or remove all rows to restore full access |
| Multi-group users | Scope is the **union** of all allowed resources across groups — more groups = more access, never less |

---

## 10. Granular Access — All Modules

This section maps every module in the system to its granular access dimensions, the `resource_type` value used in `cis_group_resource_scope`, and real-world team scenarios.

The **single scope table** covers all modules — no additional DDL per module is needed.

---

### 10.1 Module Coverage Summary

| Module | Granular Dimension | `resource_type` | Phase |
|--------|--------------------|-----------------|-------|
| Lookup Tables | Specific `lut_*` tables | `LOOKUP_TABLE` | 1 |
| Trade / Position / Cash Flow | Portfolio name | `PORTFOLIO` | 2 |
| Security Master | Security type (`EQUITY`, `BOND`, etc.) | `SECURITY_TYPE` | 2 |
| Market Data | Sub-module (`FX_RATE`, `EQUITY_PRICE`) | `MARKET_DATA_TYPE` | 3 |
| Reference Data — Counterparty / Party | Entity / country | `PARTY_ENTITY` | 3 |
| Reference Data — Corporate Actions | Entity | `CORP_ACTION_ENTITY` | 3 |
| Upload | Upload type / template category | `UPLOAD_TYPE` | 3 |
| Query Builder | Allowed DB tables | `QUERY_TABLE` | 2 |
| UDF | Object type (`TRADE`, `PORTFOLIO`, etc.) | `UDF_OBJECT_TYPE` | 4 |
| Portfolio Module | Portfolio name or entity | `PORTFOLIO` | 2 |
| Audit Log | Entity / module filter | `AUDIT_MODULE` | 4 |

---

### 10.2 Trade / Position / Cash Flow — Portfolio Scope

**Dimension:** `portfolio_short_name`
**resource_type:** `PORTFOLIO`

**Business scenario:**
- SG Operations team should only see trades for SG portfolios (`SG-PORT-01`, `SG-PORT-02`)
- HK Operations team should only see trades for HK portfolios (`HK-PORT-01`)
- Fund managers see only their own portfolios

**What gets restricted:**
| View | Restriction |
|------|------------|
| Trade List | Only trades where `portfolio_short_name IN (allowed set)` |
| Trade Detail | 403 if portfolio not in allowed set |
| Position List | Only positions for allowed portfolios |
| Cash Flow List | Only cash flows for allowed portfolios |
| Trade Create | Portfolio picker only shows allowed portfolios |
| Cash Flow Create | Portfolio picker only shows allowed portfolios |

**Scope example data:**

```
group_name   | permission_name | resource_type | resource_name
-------------|-----------------|---------------|---------------
SG-OPS       | trade-list      | PORTFOLIO     | SG-PORT-01
SG-OPS       | trade-list      | PORTFOLIO     | SG-PORT-02
HK-OPS       | trade-list      | PORTFOLIO     | HK-PORT-01
FUND-MGR-A   | trade-list      | PORTFOLIO     | FUND-A-GROWTH
FUND-MGR-A   | trade-list      | PORTFOLIO     | FUND-A-INCOME
```

**Implementation note:** The Trade, Position, and Cash Flow repositories already accept `portfolios: List[str]` as a filter parameter. The scope check plugs directly into the existing filter — minimal code change.

---

### 10.3 Security Master — Security Type Scope

**Dimension:** `security_type`
**resource_type:** `SECURITY_TYPE`

**Business scenario:**
- Fixed Income team sees only `BOND`, `T-BILL`, `SUKUK`
- Equity team sees only `EQUITY`, `ETF`, `REIT`
- Fund Admin sees all security types

**What gets restricted:**
| View | Restriction |
|------|------------|
| Security List | Only securities where `security_type IN (allowed set)` |
| Security Detail | 403 if security type not allowed |
| Security Create | Security type dropdown limited to allowed types |
| Trade Create — Security picker | Only shows securities of allowed types |

**Scope example data:**

```
group_name   | permission_name  | resource_type | resource_name
-------------|------------------|---------------|---------------
FI-TEAM      | securities-list  | SECURITY_TYPE | BOND
FI-TEAM      | securities-list  | SECURITY_TYPE | T-BILL
FI-TEAM      | securities-list  | SECURITY_TYPE | SUKUK
EQ-TEAM      | securities-list  | SECURITY_TYPE | EQUITY
EQ-TEAM      | securities-list  | SECURITY_TYPE | ETF
EQ-TEAM      | securities-list  | SECURITY_TYPE | REIT
```

**Additional dimension (optional):** Scope by `exchange_code` or `currency_code` for more granularity (e.g., SGX-listed securities only).

---

### 10.4 Market Data — Sub-Module Scope

**Dimension:** Market data type
**resource_type:** `MARKET_DATA_TYPE`

**Business scenario:**
- FX Team can view and upload FX rates only
- Equity Pricing Team can view and upload equity prices only
- Market Data Admin has access to both

**Current permission map:**
```
market_data:fx_rate_list      → fx-rates-list
market_data:equity_price_list → equity-prices-list
market_data:equity_price_create → equity-prices-create
```

Market Data already has **separate permissions per sub-module** (`fx-rates-list` vs `equity-prices-list`), so this is handled by assigning the right permission to each group — **no scope table needed** for this module today.

> **Note to SA:** If a team needs access to both FX and equity pages but should only *upload* one type, the current split permissions already cover this. Scope table becomes relevant only if you need further restriction within a sub-module (e.g., FX rates for specific currency pairs only — `resource_type = FX_CURRENCY_PAIR`).

---

### 10.5 Reference Data — Counterparty / Party Scope

**Dimension:** `entity` or `country_code`
**resource_type:** `PARTY_ENTITY`

**Business scenario:**
- SG team sees only SG-entity counterparties and parties
- HK team sees only HK-entity records
- Global Ops sees all counterparties

**What gets restricted:**
| View | Restriction |
|------|------------|
| Counterparty List | Filter by `entity IN (allowed set)` |
| Party List | Filter by `entity IN (allowed set)` |
| Counterparty / Party Detail | 403 if entity not in allowed set |
| Counterparty Create | Entity field pre-filled/locked to allowed entities |

**Scope example data:**

```
group_name   | permission_name | resource_type | resource_name
-------------|-----------------|---------------|---------------
SG-REF-TEAM  | parties-list    | PARTY_ENTITY  | SG
SG-REF-TEAM  | parties-list    | PARTY_ENTITY  | SGP
HK-REF-TEAM  | parties-list    | PARTY_ENTITY  | HK
HK-REF-TEAM  | parties-list    | PARTY_ENTITY  | HKG
```

---

### 10.6 Reference Data — Corporate Actions Scope

**Dimension:** `entity` or `security_type`
**resource_type:** `CORP_ACTION_ENTITY`

**Business scenario:**
- FI team sees corporate actions for bond securities only
- Equity team sees corporate actions for equity securities only

Scope example mirrors §10.3 and §10.5 — uses same `cis_group_resource_scope` table with `resource_type = CORP_ACTION_ENTITY`.

---

### 10.7 Upload Module — Upload Type Scope

**Dimension:** Upload template category
**resource_type:** `UPLOAD_TYPE`

**Business scenario:**
- FX team can only upload `FX_RATE` templates
- Equity team can only upload `EQUITY_PRICE` templates
- Data Ops can upload any template type

**Scope example data:**

```
group_name   | permission_name | resource_type | resource_name
-------------|-----------------|---------------|---------------
FX-TEAM      | upload-list     | UPLOAD_TYPE   | FX_RATE
EQ-TEAM      | upload-list     | UPLOAD_TYPE   | EQUITY_PRICE
```

**Implementation note:** The upload `template_type` or `category` column in the upload records table is used as the resource name.

---

### 10.8 Query Builder — Table-Level Scope

**Dimension:** DB table name
**resource_type:** `QUERY_TABLE`

**Business scenario:**
- Analysts can query only approved tables (`cis_trade`, `cis_portfolio`, `lut_*`)
- FI team can also query `cis_security` filtered to bonds
- No group except `ADMIN` can see `cis_audit_log` or `cis_user_info` via Query Builder

**What gets restricted:**
| Feature | Restriction |
|---------|------------|
| Table picker in Query Builder | Only shows allowed tables |
| Query execution | Rejects queries referencing tables outside allowed set |
| SQL Editor (admin mode) | Separate `query-builder-admin` permission — not scope-controlled |
| Saved report templates | User can only load templates that reference allowed tables |

**Scope example data:**

```
group_name   | permission_name    | resource_type | resource_name
-------------|--------------------|---------------|---------------
ANALYST      | query-builder-run  | QUERY_TABLE   | cis_trade
ANALYST      | query-builder-run  | QUERY_TABLE   | cis_portfolio
ANALYST      | query-builder-run  | QUERY_TABLE   | cis_security
FI-ANALYST   | query-builder-run  | QUERY_TABLE   | cis_trade
FI-ANALYST   | query-builder-run  | QUERY_TABLE   | cis_security
FI-ANALYST   | query-builder-run  | QUERY_TABLE   | cis_cash_flow
```

**Security note:** SQL injection risk is already mitigated by the Query Builder's parameterised query pattern. The scope check adds a whitelist validation on top — if a table name is not in the allowed set, the query is rejected before it reaches Impala.

---

### 10.9 UDF — Object Type Scope

**Dimension:** `object_type` (`TRADE`, `PORTFOLIO`, `CASH_FLOW`, `SECURITY`, etc.)
**resource_type:** `UDF_OBJECT_TYPE`

**Business scenario:**
- Trade Ops team can only manage UDFs for `TRADE` and `CASH_FLOW` object types
- Portfolio Admin manages UDFs for `PORTFOLIO` only
- UDF Admin manages all object types

**Scope example data:**

```
group_name     | permission_name | resource_type    | resource_name
---------------|-----------------|------------------|---------------
TRADE-OPS      | udf-list        | UDF_OBJECT_TYPE  | TRADE
TRADE-OPS      | udf-list        | UDF_OBJECT_TYPE  | CASH_FLOW
PORTFOLIO-ADMIN| udf-list        | UDF_OBJECT_TYPE  | PORTFOLIO
```

---

### 10.10 Portfolio Module — Portfolio Scope

**Dimension:** `portfolio_short_name`
**resource_type:** `PORTFOLIO`

Same `PORTFOLIO` resource_type as Trade (§10.2). Shared scope rows apply to both modules automatically — a group's portfolio scope applies consistently across Trade, Position, Cash Flow, and the Portfolio module itself.

**What gets restricted:**
| View | Restriction |
|------|------------|
| Portfolio List | Only allowed portfolios shown |
| Portfolio Detail | 403 if not in allowed set |
| Portfolio Create | N/A — creator's entity pre-scoped |
| Pending Approvals | Only pending items for allowed portfolios |

---

### 10.11 Audit Log — Module / Entity Filter

**Dimension:** Module name or entity
**resource_type:** `AUDIT_MODULE`

**Business scenario:**
- Compliance team can read audit logs for Trade and Portfolio modules only
- Full audit access remains `rbac-admin` territory

**Scope example data:**

```
group_name   | permission_name  | resource_type | resource_name
-------------|------------------|---------------|---------------
COMPLIANCE   | audit-logs-read  | AUDIT_MODULE  | trade
COMPLIANCE   | audit-logs-read  | AUDIT_MODULE  | portfolio
COMPLIANCE   | audit-logs-read  | AUDIT_MODULE  | cash_flow
```

---

### 10.12 Complete `resource_type` Reference

| `resource_type` | Modules Using It | Scopes What |
|-----------------|-----------------|-------------|
| `LOOKUP_TABLE` | Lookup | Specific `lut_*` table names |
| `PORTFOLIO` | Trade, Position, Cash Flow, Portfolio | `portfolio_short_name` |
| `SECURITY_TYPE` | Security, Trade (picker) | `security_type` value |
| `PARTY_ENTITY` | Counterparty, Party | `entity` value |
| `CORP_ACTION_ENTITY` | Corporate Actions | `entity` value |
| `UPLOAD_TYPE` | Upload | Template category/type |
| `QUERY_TABLE` | Query Builder | DB table name |
| `UDF_OBJECT_TYPE` | UDF | `object_type` value |
| `AUDIT_MODULE` | Audit Log | Module/app name |
| `FX_CURRENCY_PAIR` | Market Data (future) | Currency pair e.g. `USDSGD` |

---

## 11. Open Questions (For SA / User Review)

The following decisions require stakeholder input before implementation begins:

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| Q1 | Should write permissions (edit/create/delete) also be scope-controlled, or only read (list/view)? | (a) Scope applies to both read and write, (b) Scope applies to read only — write follows existing group permission | **(a)** — a user scoped to SG portfolios should not be able to create a trade for an HK portfolio |
| Q2 | When a user belongs to multiple groups with different scopes, should they see the **union** or **intersection**? | (a) Union — more permissive, (b) Intersection — more restrictive | **(a) Union** — standard RBAC principle |
| Q3 | Should restricted resources be **hidden** or **shown greyed-out with a lock icon**? | (a) Hidden — cleaner UX, (b) Shown greyed-out — users aware they exist | **(a) Hidden** — less confusing; greyed-out can be added in a later pass |
| Q4 | Who manages scopes in production? | (a) Only `rbac-admin` WRITE (current admin team), (b) New `scope-admin` permission for a wider Ops Lead group | **(a) rbac-admin** — avoids permission sprawl at this stage |
| Q5 | Should scope changes be audited in `cis_audit_log`? | (a) Yes — full audit trail, (b) No | **(a) Yes** — scope changes are security-relevant |
| Q6 | Query Builder — should table restrictions use exact table names or support wildcards (e.g. `lut_*`)? | (a) Exact names only, (b) Prefix/wildcard | **(a) Exact** for Phase 1; wildcard can follow |
| Q7 | For the Portfolio scope — should it apply across **all modules simultaneously** (Trade + Position + Cash Flow + Portfolio list) from a single scope row, or be configured per module? | (a) Single `PORTFOLIO` scope applies everywhere, (b) Separate scope per module | **(a) Single scope** — `resource_type = PORTFOLIO` is checked by every module that uses portfolio as a dimension; avoids duplication |
| Q8 | Which modules should be in **Phase 1** of implementation? | Prioritise based on operational urgency | Suggested order: Lookup → Portfolio/Trade → Security → Query Builder → Others |

---

## 12. Acceptance Criteria

### Functional (Phase 1 — Lookup)
- [ ] A user in a scoped group sees **only** their allowed lookup tables on the list page
- [ ] Direct URL access to a restricted table returns **403 Forbidden**
- [ ] A user with no scope configured continues to see **all** lookup tables
- [ ] A user in two groups with different scopes sees the **union** of both scopes
- [ ] An RBAC Admin can add/remove scope entries via the UI without writing SQL
- [ ] Removing all scope entries for a group restores full access

### Functional (Phase 2 — Trade / Portfolio / Security)
- [ ] Trade list shows only portfolios the user's group is scoped to
- [ ] Direct URL to a trade outside allowed portfolio returns **403**
- [ ] Security list filters by allowed security types
- [ ] Trade create — portfolio picker and security picker honour scope
- [ ] Cash Flow list and Position list honour the same `PORTFOLIO` scope as Trade

### Non-Functional
- [ ] Scope check adds **< 50ms** to page load (cached, 300s TTL)
- [ ] No regression in existing module-level permission checks
- [ ] All scope management actions written to `cis_audit_log`
- [ ] Unit tests cover: no-scope (full access), scoped (restricted), multi-group union, 403 on direct access, cache invalidation on scope change

---

## 13. Phased Rollout (Updated)

| Phase | Modules | `resource_type(s)` | Estimate |
|-------|---------|-------------------|----------|
| **Phase 1** | Lookup Tables | `LOOKUP_TABLE` | 4.5 days |
| **Phase 2** | Trade, Position, Cash Flow, Portfolio, Security | `PORTFOLIO`, `SECURITY_TYPE` | 5 days |
| **Phase 3** | Reference Data, Corporate Actions, Upload, Query Builder | `PARTY_ENTITY`, `CORP_ACTION_ENTITY`, `UPLOAD_TYPE`, `QUERY_TABLE` | 4 days |
| **Phase 4** | UDF, Audit Log | `UDF_OBJECT_TYPE`, `AUDIT_MODULE` | 2 days |
| **RBAC Admin UI** | Scope management UI (covers all phases) | — | 2 days |
| **Total** | All 10 modules | — | **~17.5 days** |

Phase 1 and RBAC Admin UI can run in parallel. Phases 2–4 are independent and can be prioritised by operational urgency.

---

## 14. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Ops team accidentally loses access to their own portfolios | Low | Medium | Superuser bypasses all scope checks; UI warns when removing last active scope for a group |
| Cache staleness after scope change | Low | Low | RBAC admin triggers `acl_service.clear_user_cache()` on any scope change |
| Performance — additional Kudu query per page | Low | Low | Scope cached per `user_id + permission + resource_type`; single query on first load only |
| Scope table grows large (many groups × many resources) | Very Low | Very Low | Kudu handles millions of rows efficiently; hash-partitioned on `scope_id` |
| Inconsistency between modules for same `PORTFOLIO` scope | Low | Medium | Resolved by Q7 decision: single `PORTFOLIO` type applies across all modules via shared ACL service method |
| Query Builder bypass via SQL editor | Low | High | SQL editor is behind separate `query-builder-admin` permission (admin-only); scope only applies to the visual query builder |

---

## 15. Sign-Off

| Role | Name | Decision | Date |
|------|------|----------|------|
| System Architect | | ☐ Approved / ☐ Revisions Needed | |
| Operations Lead | | ☐ Approved / ☐ Revisions Needed | |
| QA Lead | | ☐ Approved / ☐ Revisions Needed | |
| Dev Lead | | ☐ Approved / ☐ Revisions Needed | |

**Notes / Revision Comments:**

> _(Sign-off notes go here)_

---

## Appendix A — Current Permission Catalogue (All Modules)

| permission_name | Module | Description |
|----------------|--------|-------------|
| `lookup-tables-list` | Lookup | View and browse lookup tables |
| `lookup-tables-edit` | Lookup | Add, edit, delete rows in lookup tables |
| `trade-list` | Trade | View trade list and dashboard |
| `trade-view` | Trade | View trade detail |
| `trade-create` | Trade | Create new trades |
| `trade-edit` | Trade | Edit and delete trades |
| `trade-approval` | Trade | Validate, settle, cancel trades (checker) |
| `position-list` | Trade | View position list |
| `cash-flow-list` | Trade | View cash flow list and detail |
| `cash-flow-create` | Trade | Create and edit cash flows |
| `cash-flow-approval` | Trade | Approve cash flows (checker) |
| `portfolio-list` | Portfolio | View portfolio list |
| `portfolio-view` | Portfolio | View portfolio detail |
| `portfolio-create` | Portfolio | Create portfolios |
| `portfolio-edit` | Portfolio | Edit portfolios |
| `portfolio-approval` | Portfolio | Approve portfolios (checker) |
| `securities-list` | Security | View security list and detail |
| `securities-create` | Security | Create and edit securities |
| `fx-rates-list` | Market Data | View FX rates |
| `equity-prices-list` | Market Data | View equity prices |
| `equity-prices-create` | Market Data | Upload equity prices |
| `market-data-dashboard` | Market Data | View market data dashboard |
| `parties-list` | Reference Data | View counterparties and parties |
| `parties-create` | Reference Data | Create and edit counterparties/parties |
| `corp-action-list` | Reference Data | View corporate actions |
| `corp-action-create` | Reference Data | Create and edit corporate actions |
| `currencies-list` | Reference Data | View currencies |
| `countries-list` | Reference Data | View countries |
| `calendars-list` | Reference Data | View calendars |
| `upload-list` | Upload | View, create, and manage file uploads |
| `query-builder-run` | Query Builder | Run saved query templates |
| `query-builder-manage` | Query Builder | Save and delete query templates |
| `query-builder-admin` | Query Builder | Raw SQL editor (admin only) |
| `udf-list` | UDF | View UDF definitions |
| `udf-create` | UDF | Create and edit UDF definitions |
| `audit-logs-read` | Core | View audit log |
| `rbac-admin` | Core | Manage users, groups, permissions, and scopes |

---

## Appendix B — Glossary

| Term | Definition |
|------|-----------|
| **RBAC** | Role-Based Access Control — permissions assigned to groups, groups assigned to users |
| **Resource-level scope** | An additional restriction within a permission that limits access to named resources |
| **Scope** | One row in `cis_group_resource_scope` binding a group, permission, resource_type, and resource_name |
| **resource_type** | Category of the resource being scoped (e.g., `PORTFOLIO`, `SECURITY_TYPE`, `LOOKUP_TABLE`) |
| **Backward compatible** | Existing behaviour unchanged; new feature is opt-in — no scope rows = no restriction |
| **Union rule** | When a user belongs to multiple groups, they get access to resources allowed by **any** of their groups |
| **Wildcard (`*`)** | A scope entry with `resource_name = '*'` means the group is explicitly unrestricted for that permission |
| **Phase** | A delivery increment; each phase targets specific modules using the same underlying DDL |
