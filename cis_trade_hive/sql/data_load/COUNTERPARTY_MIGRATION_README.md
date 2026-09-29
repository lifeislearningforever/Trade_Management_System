# Counterparty Data Migration to Kudu

## Overview

This migration replaces the Hive staging table `gmp_cis_sta_dly_counterparty` with a Kudu table `cis_counterparty_kudu` that has a **stable primary key** for Django application compatibility.

---

## Problem Statement

### **Before (Hive Table):**
```sql
Table: gmp_cis_sta_dly_counterparty
- Partitioned by: processing_date (YYYYMMDD)
- Primary Key: Implicit (counterparty_short_name + processing_date)
- Problem: Key changes daily when ETL runs!
```

**Impact on Django Application:**
```python
# Today
counterparty_id = ('AFFIN BK-KL', '20250107')  ← Application references this

# Tomorrow (after ETL)
counterparty_id = ('AFFIN BK-KL', '20250108')  ← Reference breaks! ❌
```

### **After (Kudu Table):**
```sql
Table: cis_counterparty_kudu
- Primary Key: counterparty_short_name (stable, never changes!)
- processing_date: Just audit metadata (not part of PK)
- ETL: UPSERT (UPDATE if exists, INSERT if new)
```

**Django Application:**
```python
# Always references by stable key
counterparty_id = 'AFFIN BK-KL'  ← Works forever! ✅
```

---

## Schema Changes

### **New Columns:**

| Column | Type | Description |
|--------|------|-------------|
| `m_label` | STRING | CIF number from issuer data (75% matched) |
| `is_broker` | BOOLEAN | Converted from Y/N → TRUE/FALSE |
| `is_custodian` | BOOLEAN | Converted from Y/N → TRUE/FALSE |
| `is_issuer` | BOOLEAN | Converted from Y/N → TRUE/FALSE |
| `is_bank` | BOOLEAN | Converted from Y/N → TRUE/FALSE |
| `is_subsidiary` | BOOLEAN | Converted from Y/N → TRUE/FALSE |
| `is_corporate` | BOOLEAN | Converted from Y/N → TRUE/FALSE |
| `is_active` | BOOLEAN | Soft delete flag |
| `is_deleted` | BOOLEAN | Soft delete flag |
| `created_by` | STRING | Audit trail |
| `created_at` | TIMESTAMP | Audit trail |
| `updated_by` | STRING | Audit trail |
| `updated_at` | TIMESTAMP | Audit trail |

### **Key Design Decisions:**

✅ **Single Primary Key:** `counterparty_short_name` (stable forever)
✅ **Boolean Conversion:** Y/N strings → TRUE/FALSE for proper typing
✅ **M-Label (CIF):** Added from issuer reference data (4,907 matched, 1,628 without)
✅ **Soft Delete:** `is_deleted` flag instead of hard deletes
✅ **Audit Trail:** Track who/when created/updated records
✅ **Hash Partitioning:** 8 partitions for horizontal scalability

---

## Data Processing

### **Source Files:**

1. **counterparty.csv** (6,535 rows)
   - Government/sovereign counterparties
   - Source: `gmp_cis_sta_dly_counterparty`

2. **gmpcisissuercif 2.txt** (5,955 rows)
   - Corporate issuers with CIF numbers
   - Format: `record_type|CIF_number|counterparty_name|country|isin`

3. **counterparty_with_mlabel.csv** (6,535 rows) ← **Generated**
   - Merged data with `m_label` column
   - 4,907 matched (75.1%)
   - 1,628 unmatched (24.9% - mostly sovereign entities)

### **Data Transformation:**

```python
# Y/N → Boolean
'Y' → TRUE
'N' → FALSE
'' → FALSE

# Empty strings → NULL
'' → NULL

# SQL escaping
"O'BRIEN BANK" → "O''BRIEN BANK"
```

---

## Files Created

```
sql/
├── ddl/
│   └── cis_counterparty_kudu.sql          # Table DDL
├── data_load/
│   ├── load_counterparty_to_kudu.py       # Python generator
│   ├── insert_counterparty_data.sql       # 6,535 UPSERT statements
│   ├── load_counterparty.sh               # Execution script
│   └── COUNTERPARTY_MIGRATION_README.md   # This file
└── sample_data/
    └── counterparty_with_mlabel.csv       # Merged data
```

---

## Installation Steps

### **Step 1: Generate SQL (Already Done)**

```bash
cd /path/to/project
python3 sql/data_load/load_counterparty_to_kudu.py
```

**Output:**
- ✅ `insert_counterparty_data.sql` created (6,535 UPSERT statements)

### **Step 2: Create Table & Load Data**

#### **Option A: Automated (Recommended)**

```bash
# Set Impala connection (if not default)
export IMPALA_HOST=your-impala-host
export IMPALA_PORT=21050

# Run the load script
./sql/data_load/load_counterparty.sh
```

#### **Option B: Manual**

```bash
# 1. Create table
impala-shell -i <host>:21050 -k --ssl -f sql/ddl/cis_counterparty_kudu.sql

# 2. Load data (takes ~5-10 minutes for 6535 records)
impala-shell -i <host>:21050 -k --ssl -f sql/data_load/insert_counterparty_data.sql

# 3. Verify
impala-shell -i <host>:21050 -k --ssl -q "USE gmp_cis; SELECT COUNT(*) FROM cis_counterparty_kudu;"
```

### **Step 3: Update Django Repository**

Edit: `reference_data/repositories/reference_data_repository.py`

**Before:**
```python
class CounterpartyRepository(ImpalaReferenceRepository):
    TABLE_NAME = 'gmp_cis_sta_dly_counterparty'
```

**After:**
```python
class CounterpartyRepository(ImpalaReferenceRepository):
    TABLE_NAME = 'cis_counterparty_kudu'
```

### **Step 4: Test Application**

```bash
# Start Django server
python manage.py runserver

# Test counterparty list
curl http://localhost:8000/reference-data/counterparty/

# Verify m_label column present
# Verify boolean fields (is_bank, is_broker, etc.)
```

---

## Data Validation

### **Verify Record Count:**

```sql
USE gmp_cis;

-- Should return 6535
SELECT COUNT(*) as total_records FROM cis_counterparty_kudu;
```

### **Verify M-Label Matching:**

```sql
-- Should return 4907 (75.1%)
SELECT COUNT(*) as with_mlabel
FROM cis_counterparty_kudu
WHERE m_label IS NOT NULL AND m_label != '';

-- Should return 1628 (24.9%)
SELECT COUNT(*) as without_mlabel
FROM cis_counterparty_kudu
WHERE m_label IS NULL OR m_label = '';
```

### **Verify Boolean Conversion:**

```sql
-- Check banks (should have is_bank = TRUE)
SELECT counterparty_short_name, is_bank, is_broker, is_issuer
FROM cis_counterparty_kudu
WHERE is_bank = TRUE
LIMIT 10;
```

### **Sample Data Check:**

```sql
-- AFFIN BK should have m_label = '1483'
SELECT counterparty_short_name, m_label, country, is_bank
FROM cis_counterparty_kudu
WHERE counterparty_short_name = 'AFFIN BK-KL';

-- Expected Result:
-- AFFIN BK-KL | 1483 | Malaysia | TRUE
```

---

## ETL Process (Future)

### **Daily ETL with UPSERT:**

```sql
-- Kudu UPSERT = UPDATE if exists, INSERT if new
UPSERT INTO gmp_cis.cis_counterparty_kudu (
    counterparty_short_name,
    counterparty_full_name,
    city, country,
    is_bank, is_broker,
    processing_date,
    updated_by, updated_at
) VALUES (
    'NEW_BANK',
    'New Bank Corporation',
    'Singapore', 'Singapore',
    TRUE, FALSE,
    '20250108',
    'ETL_SYSTEM', NOW()
);
```

**Key Point:** Primary key `counterparty_short_name` never changes!

---

## Benefits

### **For Django Application:**

✅ **Stable References:** Counterparty IDs never change
✅ **Proper Types:** Boolean fields instead of Y/N strings
✅ **Fast Lookups:** Single column primary key
✅ **CIF Integration:** M-label links to issuer data
✅ **Audit Trail:** Track all changes

### **For Data Quality:**

✅ **No Duplicates:** Primary key enforcement
✅ **Soft Deletes:** Data never lost
✅ **Type Safety:** Boolean validation
✅ **Referential Integrity:** Kudu constraints

### **For Performance:**

✅ **Hash Partitioning:** 8 partitions for parallelism
✅ **Indexes:** m_label and country for fast filtering
✅ **UPSERT:** Fast updates (no delete+insert)

---

## Rollback Plan

If issues occur, you can restore the old Hive table:

```sql
-- Recreate old Hive table (from backup or original DDL)
CREATE EXTERNAL TABLE gmp_cis_sta_dly_counterparty ...

-- Update Django repository back to old table name
TABLE_NAME = 'gmp_cis_sta_dly_counterparty'
```

---

## Troubleshooting

### **Issue: Table creation fails**

```bash
# Check if Kudu service is running
impala-shell -q "SHOW TABLES IN gmp_cis;"

# Check Kudu master address in DDL
'kudu.master_addresses' = 'kudu-master:7051'
```

### **Issue: Data load is slow**

```bash
# Use batch mode (already implemented)
# 6535 records should take ~5-10 minutes

# Monitor progress
tail -f /var/log/impala/impala-server.log
```

### **Issue: Duplicate key errors**

```sql
-- Check for duplicates in source data
SELECT counterparty_short_name, COUNT(*) as cnt
FROM (SELECT * FROM counterparty_csv_staging)
GROUP BY counterparty_short_name
HAVING COUNT(*) > 1;
```

---

## Support

For questions or issues:
1. Check this README
2. Review DDL file: `sql/ddl/cis_counterparty_kudu.sql`
3. Check data load script: `sql/data_load/load_counterparty_to_kudu.py`
4. Contact: Development Team

---

**Migration Date:** 2025-01-07
**Version:** 1.0
**Author:** Claude Code
