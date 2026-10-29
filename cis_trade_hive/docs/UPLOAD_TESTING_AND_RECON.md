# Upload Module - Testing & Reconciliation Guide

## Document Info
| Field | Value |
|-------|-------|
| **Module** | File Upload / Ingestion |
| **Created** | 2026-03-04 |
| **Status** | For SA Review |

---

## Part 1: Reconciliation Queries

### 1.1 Post-Upload Verification

After uploading a file, run these queries to verify data:

```sql
-- Check record count by processing_date
SELECT
    processing_date,
    src_system,
    COUNT(*) as record_count
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124'
GROUP BY processing_date, src_system;

-- Verify src_system is correct (should be USER_UPLOAD, not 'cis')
SELECT DISTINCT src_system, sub_system, data_cat, data_frq
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124';

-- Sample data check
SELECT *
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124'
LIMIT 10;
```

### 1.2 Compare Source File vs Table

```sql
-- Count records in table
SELECT COUNT(*) as table_count
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124';

-- Should match: Number of data rows in CSV (excluding header)
```

### 1.3 Check for Duplicates

```sql
-- Check for duplicate records (same portfolio + isin + trade_date)
SELECT
    portfolio,
    isin_code,
    trade_date,
    COUNT(*) as cnt
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124'
GROUP BY portfolio, isin_code, trade_date
HAVING COUNT(*) > 1;
```

### 1.4 Verify Overwrite Behavior

```sql
-- After re-uploading same file, count should remain same (not doubled)
SELECT
    processing_date,
    COUNT(*) as record_count,
    MIN(src_id) as src_id_sample
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124'
GROUP BY processing_date;
```

### 1.5 Cross-Table Verification (All User Upload Tables)

```sql
-- Check all user upload tables
SELECT 'position_1' as table_name, processing_date, COUNT(*) as cnt
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124'
GROUP BY processing_date
UNION ALL
SELECT 'position_2' as table_name, processing_date, COUNT(*) as cnt
FROM gmp_cis.cis_user_sta_adhoc_position_2
WHERE processing_date = '20251124'
GROUP BY processing_date
UNION ALL
SELECT 'position_3' as table_name, processing_date, COUNT(*) as cnt
FROM gmp_cis.cis_user_sta_adhoc_position_3
WHERE processing_date = '20251124'
GROUP BY processing_date
UNION ALL
SELECT 'position_4' as table_name, processing_date, COUNT(*) as cnt
FROM gmp_cis.cis_user_sta_adhoc_position_4
WHERE processing_date = '20251124'
GROUP BY processing_date
UNION ALL
SELECT 'position_5' as table_name, processing_date, COUNT(*) as cnt
FROM gmp_cis.cis_user_sta_adhoc_position_5
WHERE processing_date = '20251124'
GROUP BY processing_date;
```

---

## Part 2: Negative Test Cases

### Test Case Matrix

| # | Test Case | Expected Behavior | How to Test |
|---|-----------|-------------------|-------------|
| 1 | Wrong file name (not in cis_datasource_mng) | Error: "No datasource configuration found" | Upload file with random name |
| 2 | Wrong column count | Error: "Column count mismatch" | Upload CSV with missing/extra columns |
| 3 | Wrong column names | Error: "Column mismatch" | Upload CSV with different headers |
| 4 | Empty file | Error: "File is empty" | Upload 0-byte file |
| 5 | Wrong delimiter | Error or data corruption | Upload pipe-delimited as comma-delimited |
| 6 | Wrong file type | Error: "Invalid file type" | Upload .xlsx when expecting .csv |
| 7 | Corrupted file | Error: "Failed to parse file" | Upload binary/corrupted file |
| 8 | Very large file | Timeout or memory error | Upload file > 100MB |
| 9 | Special characters in data | Should escape properly | Upload data with quotes, commas |
| 10 | Unicode/non-ASCII data | Should handle encoding | Upload data with Chinese/Japanese chars |
| 11 | Duplicate upload (same date) | Should overwrite | Upload same file twice |
| 12 | Wrong processing_date format | Error or default to current date | Manual date entry |

---

### 2.1 Test Case: Wrong File Name

**Steps:**
1. Rename `CIS_External_upload_format_1.csv` to `random_file.csv`
2. Try to upload

**Expected:**
- Error message: "No datasource configuration found for file: random_file.csv"
- Status: VALIDATION_FAILED

**Verification Query:**
```sql
SELECT * FROM gmp_cis.cis_file_upload
WHERE file_name = 'random_file.csv'
ORDER BY created_at DESC LIMIT 1;
```

---

### 2.2 Test Case: Wrong Column Count

**Steps:**
1. Create CSV with header: `portfolio,isin_code,quantity` (missing columns)
2. Name it `CIS_External_upload_format_1.csv`
3. Upload

**Expected:**
- Error: "Column count mismatch. Expected: 9, Found: 3"
- Status: VALIDATION_FAILED

---

### 2.3 Test Case: Wrong Column Names

**Steps:**
1. Create CSV with header: `wrong_col1,wrong_col2,wrong_col3,...`
2. Name it `CIS_External_upload_format_1.csv`
3. Upload

**Expected:**
- Error: "Column mismatch. Missing: portfolio, isin_code, ..."
- Status: VALIDATION_FAILED

---

### 2.4 Test Case: Empty File

**Steps:**
1. Create empty file `CIS_External_upload_format_1.csv`
2. Upload

**Expected:**
- Error: "File is empty"
- Status: VALIDATION_FAILED

---

### 2.5 Test Case: Wrong Delimiter

**Steps:**
1. Create pipe-delimited file: `col1|col2|col3`
2. Name as `CIS_External_upload_format_1.csv` (expects comma)
3. Upload

**Expected:**
- Validation may pass but data will be corrupted
- All data in single column

**Verification:**
```sql
-- Check if data looks correct
SELECT portfolio, isin_code, quantity_today
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = 'YYYYMMDD'
LIMIT 5;
-- If wrong delimiter, portfolio will contain entire row
```

---

### 2.6 Test Case: Special Characters

**Test Data:**
```csv
portfolio,client_num,exchange_quoted,isin_code,counter,quantity_yesterday,movement,quantity_today,trade_date
"O'Brien Fund",123,"NYSE","US123",Test's Counter,100,0,100,20251124
"Fund, LLC",456,"SGX","SG456","Counter, Inc",200,0,200,20251124
```

**Expected:**
- Should handle quotes and commas properly
- Data should be escaped correctly

**Verification:**
```sql
SELECT portfolio, counter
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE portfolio LIKE '%Brien%' OR portfolio LIKE '%LLC%';
```

---

### 2.7 Test Case: Duplicate Upload (Overwrite)

**Steps:**
1. Upload `CIS_External_upload_format_1.csv` with 11 records
2. Verify: 11 records in table
3. Upload same file again
4. Verify: Still 11 records (not 22)

**Verification:**
```sql
SELECT COUNT(*) FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124';
-- Should be 11, not 22
```

---

## Part 3: Data Quality Checks

### 3.1 Null/Empty Value Check

```sql
-- Check for null or empty required fields
SELECT
    'portfolio' as field, COUNT(*) as null_count
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124'
  AND (portfolio IS NULL OR portfolio = '')
UNION ALL
SELECT
    'isin_code' as field, COUNT(*) as null_count
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124'
  AND (isin_code IS NULL OR isin_code = '');
```

### 3.2 Data Type Validation

```sql
-- Check numeric fields have valid values
SELECT portfolio, quantity_yesterday, quantity_today
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124'
  AND (
    NOT REGEXP_LIKE(quantity_yesterday, '^-?[0-9]+\.?[0-9]*$')
    OR NOT REGEXP_LIKE(quantity_today, '^-?[0-9]+\.?[0-9]*$')
  );
```

### 3.3 Business Rule Validation

```sql
-- Check quantity_today = quantity_yesterday + movement
SELECT
    portfolio,
    isin_code,
    CAST(quantity_yesterday AS DECIMAL(20,2)) as qty_yest,
    CAST(movement AS DECIMAL(20,2)) as mvmt,
    CAST(quantity_today AS DECIMAL(20,2)) as qty_today,
    CAST(quantity_yesterday AS DECIMAL(20,2)) + CAST(movement AS DECIMAL(20,2)) as expected_today
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124'
  AND CAST(quantity_today AS DECIMAL(20,2)) !=
      CAST(quantity_yesterday AS DECIMAL(20,2)) + CAST(movement AS DECIMAL(20,2));
```

---

## Part 4: Cleanup Queries

### 4.1 Delete Test Data

```sql
-- Delete specific partition (use with caution!)
ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_1
DROP IF EXISTS PARTITION (processing_date='20251124');

-- Or delete specific records
DELETE FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20251124'
  AND src_system = 'cis';  -- Only delete old 'cis' records
```

### 4.2 Refresh Table Metadata

```sql
-- After any manual changes
INVALIDATE METADATA gmp_cis.cis_user_sta_adhoc_position_1;
REFRESH gmp_cis.cis_user_sta_adhoc_position_1;
```

---

## Part 5: Upload Status Tracking

### 5.1 Check Upload History

```sql
SELECT
    upload_id,
    file_name,
    status,
    row_count,
    target_table_name,
    created_at,
    error_message
FROM gmp_cis.cis_file_upload
ORDER BY created_at DESC
LIMIT 20;
```

### 5.2 Failed Uploads Analysis

```sql
SELECT
    file_name,
    status,
    error_message,
    created_at
FROM gmp_cis.cis_file_upload
WHERE status IN ('FAILED', 'VALIDATION_FAILED')
ORDER BY created_at DESC;
```

---

## Part 6: Datasource Configuration Check

### 6.1 View All Configured Datasources

```sql
SELECT
    source_id,
    source_name,
    target_table,
    separator,
    header,
    intake_columns
FROM gmp_cis.cis_datasource_mng
ORDER BY source_name;
```

### 6.2 Verify Specific Datasource

```sql
SELECT *
FROM gmp_cis.cis_datasource_mng
WHERE source_name = 'CIS_External_upload_format_1.csv';
```

---

## Sign-Off

| Test Type | Tester | Date | Status |
|-----------|--------|------|--------|
| Positive Cases | | | |
| Negative Cases | | | |
| Reconciliation | | | |
| Data Quality | | | |

---

## Notes

1. All queries use `processing_date = '20251124'` as example - replace with actual date
2. Table names are for USER_UPLOAD (position_1 to position_5)
3. For AMS_STREET tables, use `gmp_cis_sta_dly_*` table names
4. Always run INVALIDATE METADATA after manual data changes
