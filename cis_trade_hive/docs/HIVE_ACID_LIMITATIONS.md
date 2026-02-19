# Hive ACID Table Limitations & Workarounds

This document tracks known limitations when working with Hive Managed Tables with ACID (ORC + SNAPPY) and their workarounds.

---

## Overview

**Environment:**
- Hive Managed Tables with full ACID support
- ORC file format with SNAPPY compression
- Bucketed tables (CLUSTERED BY with 4 buckets)
- Execution Engine: MapReduce for transactional operations

**Database:** `gmp_cis`

---

## Known Limitations

### 1. GROUP BY Fails on ACID Tables

**Issue:** `GROUP BY` queries fail with server-side errors on transactional (ACID) tables.

**Error:**
```
TExecuteStatementResp(status=TStatus(statusCode=3,
  infoMessages=['Server-side error; please check HS2 logs.'],
  errorMessage='Error running query'))
```

**Example Failing Query:**
```sql
SELECT object_type
FROM cis_udf_field
WHERE object_type IS NOT NULL
  AND is_active = true
GROUP BY object_type
```

**Workaround:** Remove `GROUP BY` and deduplicate in Python:
```python
# Instead of GROUP BY in SQL, do this:
query = """
    SELECT object_type
    FROM cis_udf_field
    WHERE object_type IS NOT NULL
      AND is_active = true
"""
results = hive_manager.execute_query(query, database='gmp_cis')

# Deduplicate in Python
object_types = list(set(
    row['object_type'] for row in (results or [])
    if row.get('object_type') and str(row['object_type']).strip()
))
object_types.sort()
```

**Affected Files:**
- `udf/repositories/udf_field_repository.py` - `get_object_types()`

---

### 2. DISTINCT Fails on ACID Tables

**Issue:** `SELECT DISTINCT` queries fail similarly to `GROUP BY`.

**Example Failing Query:**
```sql
SELECT DISTINCT field_name
FROM cis_udf_field
WHERE object_type = 'PORTFOLIO'
  AND is_active = true
```

**Workaround:** Remove `DISTINCT` and deduplicate in Python:
```python
query = """
    SELECT field_name
    FROM cis_udf_field
    WHERE object_type = 'PORTFOLIO'
      AND is_active = true
"""
results = hive_manager.execute_query(query, database='gmp_cis')

# Deduplicate using set
unique_field_names = set()
for row in (results or []):
    field_name = row.get('field_name')
    if field_name and str(field_name).strip():
        unique_field_names.add(field_name)

fields = [{'field_name': fn} for fn in unique_field_names]
fields.sort(key=lambda x: x.get('field_name', ''))
```

**Affected Files:**
- `udf/repositories/udf_field_repository.py` - `get_fields_by_entity()`

---

### 3. ORDER BY Fails on ACID Tables

**Issue:** `ORDER BY` clause fails on transactional tables.

**Example Failing Query:**
```sql
SELECT * FROM cis_portfolio
WHERE deleted_at IS NULL
ORDER BY portfolio_name
```

**Workaround:** Sort results in Python:
```python
query = """
    SELECT * FROM cis_portfolio
    WHERE deleted_at IS NULL
"""
results = hive_manager.execute_query(query, database='gmp_cis')

# Sort in Python
results.sort(key=lambda x: x.get('portfolio_name', ''))
```

**Affected Files:**
- Most repository files that need sorted results

---

### 4. UPSERT Not Supported (Use DELETE + INSERT)

**Issue:** Hive ACID doesn't support `UPSERT` or `MERGE` statements in all configurations.

**Workaround:** Use explicit DELETE followed by INSERT:
```python
# Delete existing record
delete_query = f"""
    DELETE FROM cis_udf_field
    WHERE field_id = '{field_id}'
"""
hive_manager.execute_write(delete_query, database='gmp_cis')

# Insert new/updated record
insert_query = f"""
    INSERT INTO cis_udf_field (field_id, field_name, ...)
    VALUES ('{field_id}', '{field_name}', ...)
"""
hive_manager.execute_write(insert_query, database='gmp_cis')
```

---

### 5. Aggregation Functions May Fail

**Issue:** Some aggregation functions (`COUNT`, `SUM`, `AVG`) may fail on ACID tables.

**Example Failing Query:**
```sql
SELECT object_type, COUNT(*) as total
FROM cis_udf_field
GROUP BY object_type
```

**Workaround:** Fetch all rows and aggregate in Python:
```python
from collections import Counter

query = "SELECT object_type FROM cis_udf_field WHERE is_active = true"
results = hive_manager.execute_query(query, database='gmp_cis')

# Count in Python
counts = Counter(row['object_type'] for row in results if row.get('object_type'))
# Result: {'PORTFOLIO': 10, 'TRADE': 5, ...}
```

---

### 6. Subqueries May Have Issues

**Issue:** Complex subqueries sometimes fail on ACID tables.

**Workaround:** Break into multiple queries:
```python
# Instead of:
# SELECT * FROM table1 WHERE id IN (SELECT id FROM table2 WHERE ...)

# Do this:
query1 = "SELECT id FROM table2 WHERE ..."
results1 = hive_manager.execute_query(query1, database='gmp_cis')
ids = [r['id'] for r in results1]

if ids:
    ids_str = ','.join(f"'{id}'" for id in ids)
    query2 = f"SELECT * FROM table1 WHERE id IN ({ids_str})"
    results2 = hive_manager.execute_query(query2, database='gmp_cis')
```

---

### 7. Boolean Comparison Syntax

**Issue:** Boolean comparisons must use `= true` or `= false`, not just the column name.

**Correct:**
```sql
SELECT * FROM cis_udf_field WHERE is_active = true
```

**Incorrect (may fail):**
```sql
SELECT * FROM cis_udf_field WHERE is_active
```

---

### 8. NULL Handling in WHERE Clause

**Issue:** `IS NULL` and `IS NOT NULL` work, but comparing with `= NULL` fails silently.

**Correct:**
```sql
SELECT * FROM cis_portfolio WHERE deleted_at IS NULL
```

**Incorrect:**
```sql
SELECT * FROM cis_portfolio WHERE deleted_at = NULL  -- Returns no rows!
```

---

## Best Practices for Hive ACID Tables

### 1. Always Use Python for Complex Operations
- Sorting (ORDER BY)
- Deduplication (DISTINCT, GROUP BY)
- Aggregation (COUNT, SUM, AVG)
- Complex filtering

### 2. Keep Queries Simple
```python
# Good: Simple SELECT with WHERE
query = """
    SELECT field_id, object_type, field_name, is_active
    FROM cis_udf_field
    WHERE object_type = 'PORTFOLIO'
      AND is_active = true
"""

# Bad: Complex query with multiple clauses
query = """
    SELECT object_type, COUNT(*) as total
    FROM cis_udf_field
    WHERE is_active = true
    GROUP BY object_type
    ORDER BY total DESC
"""
```

### 3. Provide Fallback Defaults
```python
def get_object_types(self) -> List[str]:
    try:
        # Try to fetch from database
        results = hive_manager.execute_query(query, database='gmp_cis')
        return [r['object_type'] for r in results]
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        # Return sensible defaults on failure
        return ['PORTFOLIO', 'TRADE', 'SECURITY', 'COUNTERPARTY']
```

### 4. Use Transactions for Write Operations
```python
# For critical writes, verify success
try:
    hive_manager.execute_write(insert_query, database='gmp_cis')
    # Verify the insert worked
    result = hive_manager.execute_query(verify_query, database='gmp_cis')
    if not result:
        raise Exception("Insert verification failed")
except Exception as e:
    logger.error(f"Write failed: {str(e)}")
    raise
```

---

## Hive Configuration for ACID

Required settings in `hive-site.xml` or set via `SET` commands:

```sql
SET hive.support.concurrency=true;
SET hive.enforce.bucketing=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.txn.manager=org.apache.hadoop.hive.ql.lockmgr.DbTxnManager;
SET hive.compactor.initiator.on=true;
SET hive.compactor.worker.threads=1;
SET hive.execution.engine=mr;  -- MapReduce for transactional ops
```

---

## Changelog

| Date | Issue | Workaround | Files Affected |
|------|-------|------------|----------------|
| 2026-02-20 | GROUP BY fails | Deduplicate in Python | `udf_field_repository.py` |
| 2026-02-20 | DISTINCT fails | Use set() in Python | `udf_field_repository.py` |
| 2026-02-20 | ORDER BY fails | Sort in Python | Multiple repositories |

---

## References

- [Apache Hive ACID Documentation](https://cwiki.apache.org/confluence/display/Hive/Hive+Transactions)
- [Hive ORC File Format](https://orc.apache.org/)
- Project CLAUDE.md for database configuration
