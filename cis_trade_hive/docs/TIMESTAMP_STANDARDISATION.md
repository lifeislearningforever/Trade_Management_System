# Timestamp Column Standardisation — gmp_cis

**Ticket:** DATE_STD_001  
**Status:** Code changes merged — DB migration pending  
**Date:** 2026-05-05  

---

## Decision

All audit/metadata timestamp columns (`created_at`, `updated_at`, `submitted_at`, `validated_at`, `settled_at`, `performed_at`, `reviewed_at`, `changed_at`, `loaded_at`) are standardised to:

```
STRING   'YYYY-MM-DD HH:MM:SS'
```

Business dates and partition dates are **not changed**:

| Column category | Type | Format | Example |
|---|---|---|---|
| Audit timestamps | `STRING` | `YYYY-MM-DD HH:MM:SS` | `2026-05-05 14:30:00` |
| Business dates | `STRING` | `YYYY-MM-DD` | `2026-05-05` |
| Partition/ETL dates | `STRING` | `YYYYMMDD` | `20260505` |
| Millisecond PKs (`trade_id`, `event_id`, `history_id`) | `BIGINT` | Unix ms | `1746432600000` |

---

## Why STRING (not TIMESTAMP or BIGINT)

1. **Python code already writes STRING** — every repository uses `datetime.now().strftime('%Y-%m-%d %H:%M:%S')`. BIGINT and TIMESTAMP tables were the outliers.
2. **Kudu TIMESTAMP has a timezone trap** — stored as UTC micros but Impala interprets in the JVM timezone. Silent off-by-hours bugs when cluster timezone ≠ app server.
3. **BIGINT is opaque** — requires `from_unixtime(col/1000)` in every query and report.
4. **STRING is portable** — identical behaviour across Docker, SIT, UAT, PROD. Sorts correctly in `YYYY-MM-DD HH:MM:SS` format.

---

## Tables Requiring DB Migration

### Group 1 — BIGINT → STRING

| Table | Columns migrated |
|---|---|
| `cis_equity_price_kudu` | `price_timestamp`, `created_at`, `updated_at` |
| `cis_equity_price_history` | `changed_at`, `price_timestamp` |
| `cis_security_kudu` | `created_at`, `updated_at`, `submitted_for_approval_at`, `reviewed_at` |
| `cis_corporate_action` | `created_at`, `updated_at`, `performed_at` |
| `cis_system_date` | `loaded_at`, `created_at`, `updated_at` |

Conversion expression used:
```sql
from_unixtime(CAST(col AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
```

### Group 2 — TIMESTAMP → STRING

| Table | Columns migrated |
|---|---|
| `cis_party` | `created_at`, `updated_at` |
| `cis_user` | `created_at`, `updated_at` |
| `cis_user_group` | `created_at`, `updated_at` |
| `cis_group_permissions` | `created_at`, `updated_at` |
| `cis_cash_flow` | `created_at`, `updated_at`, `validated_at`, `settled_at`, `cancelled_at` |
| `cis_file_upload` | `created_at`, `updated_at` |

Conversion expression used:
```sql
from_timestamp(col, 'yyyy-MM-dd HH:mm:ss')
```

> **Note:** Run TIMESTAMP→STRING migration **on the CML cluster** (not local Docker) to ensure timezone conversion produces the correct local time. Spot-check 5–10 rows before and after each rename.

---

## Migration Steps (per table)

Kudu does not support `ALTER COLUMN` type changes. Each table follows this sequence:

```sql
-- 1. Create new table (DDL in sql/ddl/56_standardise_timestamp_columns.sql)
CREATE TABLE gmp_cis.<table>_new LIKE gmp_cis.<table>;
ALTER TABLE gmp_cis.<table>_new ALTER COLUMN created_at STRING, ...;

-- 2. Copy + convert data
INSERT INTO gmp_cis.<table>_new SELECT ..., from_unixtime(...) AS created_at ... FROM gmp_cis.<table>;

-- 3. Validate row counts match
SELECT COUNT(*) FROM gmp_cis.<table>;
SELECT COUNT(*) FROM gmp_cis.<table>_new;

-- 4. Spot-check values
SELECT created_at FROM gmp_cis.<table>_new LIMIT 5;

-- 5. Rename (brief downtime window)
ALTER TABLE gmp_cis.<table>     RENAME TO gmp_cis.<table>_bak;
ALTER TABLE gmp_cis.<table>_new RENAME TO gmp_cis.<table>;

-- 6. Smoke test the application

-- 7. Drop backup (only after smoke test passes)
DROP TABLE gmp_cis.<table>_bak;
```

**Recommended order** (lowest risk first):

1. `cis_user_group` — small table, low traffic
2. `cis_group_permissions` — small table, low traffic
3. `cis_user` — moderate traffic
4. `cis_party` — moderate traffic
5. `cis_file_upload` — upload module only
6. `cis_cash_flow` — test cash flow screens after
7. `cis_corporate_action` — test CA screens after
8. `cis_system_date` — ETL dependency, migrate during off-peak
9. `cis_security_kudu` — high traffic, do last in Group 1
10. `cis_equity_price_kudu` + `cis_equity_price_history` — together, test price screens after

---

## Code Changes Already Merged

### `market_data/repositories/equity_price_hive_repository.py`

- Added `_ts_to_display(value)` helper that handles STRING, BIGINT ms, and TIMESTAMP objects — safe before and after migration
- Replaced 9 occurrences of `datetime.fromtimestamp(col / 1000)` with `_ts_to_display(col)`
- Replaced 4 occurrences of `int(time.time() * 1000)` for audit columns with `datetime.now().strftime('%Y-%m-%d %H:%M:%S')`
- `history_id` (PK) still uses BIGINT ms — intentional

### `templates/auth/profile.html` line 133

- `{{ portfolio.created_at|date:"Y-m-d" }}` → `{{ portfolio.created_at|default:"-" }}`
- Django's `|date:` filter requires a datetime object; STRING renders correctly with `|default:"-"`

### `templates/udf/udf_value_history.html` line 42

- `{{ record.created_at|date:"Y-m-d H:i:s" }}` → `{{ record.created_at|default:"-" }}`

---

## No Changes Required

These components are unaffected:

| Component | Reason |
|---|---|
| All business logic (AVP, trade calc, settlement) | Uses `trade_date`, `position_date` — already STRING |
| Maker-checker workflow | Status transitions use `status` field, not timestamps |
| Trade/position repositories | Already write STRING timestamps |
| Portfolio repository | Already writes STRING timestamps |
| 75% of templates | Use `\|default:"-"` — render any type as string |
| JavaScript date handling | Already treats all dates as strings |
| WHERE / ORDER BY on `created_at` | STRING `YYYY-MM-DD HH:MM:SS` sorts correctly lexicographically |

---

## DDL File

`sql/ddl/56_standardise_timestamp_columns.sql`

Contains full CREATE + INSERT + commented RENAME/DROP statements for all 11 tables. The rename commands are intentionally commented out — uncomment and run them after validating row counts and spot-checking values.

---

## Rollback Plan

Each old table is preserved as `<table>_bak` until explicitly dropped.  
To roll back a specific table:

```sql
ALTER TABLE gmp_cis.<table>     RENAME TO gmp_cis.<table>_new_failed;
ALTER TABLE gmp_cis.<table>_bak RENAME TO gmp_cis.<table>;
DROP TABLE gmp_cis.<table>_new_failed;
```

No application code rollback needed — `_ts_to_display()` handles both old (BIGINT/TIMESTAMP) and new (STRING) formats simultaneously.
