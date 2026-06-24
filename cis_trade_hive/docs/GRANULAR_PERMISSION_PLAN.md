# Granular Permission (Resource-Level Access Control) Plan

## Document Info

| Field | Value |
|-------|-------|
| **Document Type** | Design & Implementation Plan |
| **Module** | Core — RBAC / ACL |
| **Created Date** | 2026-06-24 |
| **Status** | Pending SA / User Approval |
| **Author** | CIS Trade Hive Dev Team |
| **Reviewers** | SA Team, Operations Lead |

---

## 1. Executive Summary

The current RBAC system controls access at the **module level** (e.g., a user can see the entire Lookup module or not at all). This plan introduces **resource-level (row-level) access control** so that specific groups can be restricted to individual resources within a module — for example, Team A sees only `lut_broker` and `lut_settlement_type`, while Team B sees only `lut_charge_type`.

The design is **backward compatible** — existing group/permission assignments require no changes. Restriction is opt-in: if no scope is configured for a group, it retains full access to the module.

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

## 10. Open Questions (For SA / User Review)

The following decisions require stakeholder input before implementation begins:

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| Q1 | Should `lookup-tables-edit` (row write) also be scope-controlled? | (a) Yes — same scope table, (b) No — edit access follows list access | **(a)** — edit and list should be consistent |
| Q2 | When a user has both OPS-TEAM and FINANCE-TEAM, should they see the **union** of scoped tables, or only the intersection? | (a) Union (more permissive), (b) Intersection (more restrictive) | **(a) Union** — standard RBAC principle; if you belong to both groups you get combined access |
| Q3 | Should restricted tables be **hidden** from the list, or **shown greyed-out with a lock icon**? | (a) Hidden — simpler UX, (b) Shown greyed-out — users know they exist but lack access | **(a) Hidden** — less confusing for end users |
| Q4 | Who can manage scopes in production — only RBAC Admins, or also a designated Ops Lead role? | (a) Only `rbac-admin` WRITE, (b) New `scope-admin` permission | **(a) rbac-admin** — avoids permission sprawl at this stage |
| Q5 | Should scope records be **audited** in `cis_audit_log`? | (a) Yes — full audit trail, (b) No — RBAC admin changes are not audited today | **(a) Yes** — scope changes are security-relevant |
| Q6 | Phase 2 — Query Builder: should table restrictions be by **exact table name** or by **table name prefix** (e.g., `lut_*`)? | (a) Exact name only, (b) Prefix/wildcard support | **(a) Exact** for Phase 1; wildcard can be added if operationally needed |

---

## 11. Acceptance Criteria

### Functional
- [ ] A user in a scoped group sees **only** their allowed lookup tables on the list page
- [ ] Direct URL access to a restricted table returns **403 Forbidden** (not a blank page or empty result)
- [ ] A user in a non-scoped group (ADMIN) continues to see **all** lookup tables unchanged
- [ ] A user in **two groups** with different scopes sees the **union** of both scopes
- [ ] An RBAC Admin can add/remove scope entries via the UI without writing SQL
- [ ] Removing all scope entries for a group restores full access (no scope = no restriction)

### Non-Functional
- [ ] Scope check adds **< 50ms** to page load (cached after first call within session)
- [ ] No regression in existing module-level permission checks
- [ ] All scope management actions are written to `cis_audit_log`
- [ ] Unit tests cover: no-scope (full access), scoped (restricted), multi-group union, 403 on direct access

---

## 12. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Ops team accidentally locks themselves out of all lookup tables | Low | Medium | Superuser flag bypasses all scope checks; also show warning in UI when removing last active scope entry for a group |
| Cache staleness after scope change | Low | Low | RBAC admin UI triggers `acl_service.clear_user_cache()` on any scope change |
| Performance impact of additional Kudu query | Low | Low | Scope result is cached per user per permission; adds one query only on first page load or cache miss |
| Scope table grows very large | Very Low | Very Low | Kudu handles millions of rows; partition by `scope_id` hash keeps queries fast |

---

## 13. Sign-Off

| Role | Name | Decision | Date |
|------|------|----------|------|
| System Architect | | ☐ Approved / ☐ Revisions Needed | |
| Operations Lead | | ☐ Approved / ☐ Revisions Needed | |
| QA Lead | | ☐ Approved / ☐ Revisions Needed | |
| Dev Lead | | ☐ Approved / ☐ Revisions Needed | |

**Notes / Revision Comments:**

> _(Sign-off notes go here)_

---

## Appendix A — Current Permission Catalogue (Lookup-Related)

| permission_name | Description | Current Assignees |
|----------------|-------------|-------------------|
| `lookup-tables-list` | View lookup tables and browse rows | All teams |
| `lookup-tables-edit` | Add, edit, delete rows in lookup tables | Ops, Admin |

---

## Appendix B — Glossary

| Term | Definition |
|------|-----------|
| **RBAC** | Role-Based Access Control — permissions assigned to groups, groups assigned to users |
| **Resource-level scope** | An additional restriction within a permission that limits access to named resources (specific tables, portfolios, etc.) |
| **Scope** | One row in `cis_group_resource_scope` binding a group, permission, and resource name |
| **Backward compatible** | Existing behaviour unchanged; new feature is opt-in via scope table data |
| **Union rule** | When a user belongs to multiple groups, they get access to resources allowed by **any** of their groups |
| **Wildcard (`*`)** | A scope entry with `resource_name = '*'` means the group is explicitly unrestricted for that permission |
