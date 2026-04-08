# RBAC V2 — User Access Rights Query Checks

Source: `core/repositories/acl_repository_v2.py`  
Active when: `RBAC_VERSION=v2` (default in `config/settings.py`)

---

## Overview

On every login (and on cache miss during a request), RBAC v2 runs **5 checks in sequence**
across 4 Kudu tables to determine whether a user is valid and what they are allowed to do.

---

## Query 1 — Is this user valid and active?

**Method:** `get_user_by_login(login, entity)`  
**Table:** `cis_user_info`

```sql
SELECT user_id, login, email, name, default_entity, last_login,
       is_active, is_deleted, created_on, created_by, updated_on, updated_by
FROM cis_user_info
WHERE UPPER(login) = 'TMP3RC'
  AND is_active = true
  AND is_deleted = false
-- AND UPPER(default_entity) = 'UOBS'   (only if entity param passed)
LIMIT 1
```

**Gate:** User must exist, be active (`is_active=true`), and not soft-deleted (`is_deleted=false`).  
No match → `authenticate_user()` returns `None` → login denied immediately.

---

## Query 2 — What groups does this user belong to?

**Method:** `get_user_groups(user_id, entity)`  
**Tables:** `cis_user_group_mapping_info` JOIN `cis_user_group_info`

```sql
SELECT ugm.user_group_mapping_id AS mapping_id,
       ugm.group_name,
       ugm.entity,
       ugi.description AS group_description
FROM cis_user_group_mapping_info ugm
LEFT JOIN cis_user_group_info ugi
    ON ugm.group_name = ugi.group_name
   AND ugm.entity = ugi.entity
WHERE ugm.user_id = '1773384561790'
  AND ugm.is_active = true
  AND ugm.is_deleted = false
-- AND UPPER(ugm.entity) = 'UOBS'   (only if entity param passed)
ORDER BY ugm.group_name
```

**Gate:** User must have at least one active, non-deleted group mapping.  
No groups → user logs in with zero permissions (not denied, but can do nothing).  
Multi-group: a user can belong to many groups — all are returned and used in Query 3.

---

## Query 3 — What permissions does each group have?

**Method:** `get_group_permissions(group_name, entity)`  
**Table:** `cis_group_permission_map`  
**Runs once per group** the user belongs to.

```sql
SELECT permission_name, mode, description
FROM cis_group_permission_map
WHERE group_name = 'SG-TRADER'
  AND is_active = true
  AND is_deleted = false
-- AND UPPER(entity) = 'UOBS'   (only if entity param passed)
ORDER BY permission_name
```

**Aggregation rule (highest privilege wins):**

```
User in SG-TRADER  → trade-create: READ
User in CIS-OPS    → trade-create: READ_WRITE
Final result       → trade-create: READ_WRITE   ← READ_WRITE always wins
```

Result is a flat dict:
```python
{
    'trade-create':   'READ_WRITE',
    'trade-list':     'READ',
    'trade-approve':  'READ_WRITE',
    'portfolio-view': 'READ',
    ...
}
```

---

## Query 4 — Runtime permission check (per request)

**Method:** `has_permission(user_id, permission, required_mode, entity)`  
**No additional DB query** if user data is in cache (300s TTL).

```python
# Access level logic
if required_mode == 'READ':
    return user_mode in ('READ', 'READ_WRITE')   # READ_WRITE implies READ
elif required_mode in ('WRITE', 'READ_WRITE'):
    return user_mode == 'READ_WRITE'             # Must have explicit WRITE
```

**Usage in views/services:**
```python
if acl_repo.has_permission(user_id, 'trade-create', 'READ_WRITE'):
    # allow trade creation
```

---

## Query 5 — Entity scope filter (applied to all queries)

All queries accept an optional `entity` parameter (e.g., `'UOBS'`).  
When passed, it adds `AND UPPER(entity) = 'UOBS'` to every query.

This means the same login can have **different groups and permissions in different entities** —
access is always entity-scoped.

Entity is resolved in this order:
1. Explicitly passed `entity` param
2. User's `default_entity` from `cis_user_info`

---

## Full Authentication Flow

```
login('TMP3RC')
    │
    ├─ Check cache (key: "user:TMP3RC") → hit? return cached auth_data
    │
    ├─ Query 1: cis_user_info
    │     is_active=true, is_deleted=false → get user_id, default_entity
    │
    ├─ Query 2: cis_user_group_mapping_info + cis_user_group_info
    │     user_id match, is_active=true, is_deleted=false → [SG-TRADER, CIS-OPS]
    │
    ├─ Query 3 (×N groups): cis_group_permission_map
    │     group_name match, is_active=true, is_deleted=false
    │     → aggregate: READ_WRITE wins over READ
    │
    ├─ Store in cache (TTL: 300s)
    │
    └─ Return auth_data:
           user         → user record
           groups       → list of group dicts
           group_names  → ['SG-TRADER', 'CIS-OPS']
           permissions  → raw list (all perms from all groups)
           permission_map → {'trade-create': 'READ_WRITE', ...}
```

---

## Summary Table

| Check | Table | Key WHERE conditions |
|-------|-------|----------------------|
| User valid | `cis_user_info` | `is_active=true`, `is_deleted=false`, login match |
| Group membership | `cis_user_group_mapping_info` | `is_active=true`, `is_deleted=false`, `user_id` match |
| Group details | `cis_user_group_info` | Joined on `group_name + entity` |
| Permissions per group | `cis_group_permission_map` | `is_active=true`, `is_deleted=false`, `group_name` match |
| Entity scope | All tables | `UPPER(entity) = '<ENTITY>'` on every query |

---

## Tables Used (v2 only)

| Table | Purpose |
|-------|---------|
| `cis_user_info` | User master — login, email, name, entity, active flag |
| `cis_user_group_info` | Group definitions — group_name, entity, description |
| `cis_user_group_mapping_info` | User ↔ Group mappings (multi-group support) |
| `cis_group_permission_map` | Group ↔ Permission mappings with mode (READ / READ_WRITE) |

---

## Caching

- **Cache key:** `user:<LOGIN_UPPER>` (e.g., `user:TMP3RC`)
- **TTL:** 300 seconds (5 minutes)
- **Scope:** Per `ACLRepositoryV2` instance (in-memory, not distributed)
- **Invalidation:** `acl_repo.clear_cache('TMP3RC')` or `acl_repo.clear_cache()` for all

---

*Generated: 2026-04-09*  
*Source file: `core/repositories/acl_repository_v2.py`*
