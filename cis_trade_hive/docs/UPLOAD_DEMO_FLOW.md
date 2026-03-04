# File Upload Module - Demo Flow

## Document Info
| Field | Value |
|-------|-------|
| **Module** | File Upload / Ingestion |
| **Created** | 2026-03-04 |
| **Purpose** | Demo Script for Stakeholders |

---

## Overview

The File Upload module allows users to upload CSV files and ingest them into pre-configured Hive external tables. The system is **metadata-driven** using the `cis_datasource_mng` configuration table.

---

## Demo Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FILE UPLOAD DEMO FLOW                                │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │   1. USER    │
    │  Selects     │
    │  CSV File    │
    └──────┬───────┘
           │
           ▼
    ┌──────────────────────────────────────┐
    │  2. VALIDATION                        │
    │  ┌────────────────────────────────┐  │
    │  │ • Check file extension (.csv)  │  │
    │  │ • Check file size (< 100MB)    │  │
    │  │ • Detect delimiter (,|;|\t)    │  │
    │  │ • Parse headers & data rows    │  │
    │  │ • Detect DUPLICATES (warning)  │  │
    │  │ • Match with cis_datasource_mng│  │
    │  └────────────────────────────────┘  │
    └──────────────┬───────────────────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
         ▼                   ▼
    ┌─────────┐        ┌──────────┐
    │ VALID   │        │ INVALID  │
    │ File    │        │ File     │
    └────┬────┘        └────┬─────┘
         │                  │
         ▼                  ▼
    ┌──────────────┐   ┌───────────────┐
    │ 3. PREVIEW   │   │ Show Errors   │
    │ • Schema     │   │ • Wrong cols  │
    │ • Sample data│   │ • Wrong type  │
    │ • Duplicates │   │ • Empty file  │
    │   warning    │   └───────────────┘
    └──────┬───────┘
           │
           ▼
    ┌─────────────────────────────────────┐
    │  4. INGESTION                        │
    │  ┌───────────────────────────────┐  │
    │  │ • Read all rows from file     │  │
    │  │ • DEDUPLICATE (remove dups)   │  │
    │  │ • Add system columns:         │  │
    │  │   - src_id                    │  │
    │  │   - src_system = USER_UPLOAD  │  │
    │  │   - processing_date           │  │
    │  │ • INSERT OVERWRITE partition  │  │
    │  └───────────────────────────────┘  │
    └──────────────┬──────────────────────┘
                   │
                   ▼
    ┌─────────────────────────────────────┐
    │  5. RECONCILIATION                   │
    │  ┌───────────────────────────────┐  │
    │  │ • Source Rows vs Table Count  │  │
    │  │ • Duplicates Removed count    │  │
    │  │ • Duplicate rows in table     │  │
    │  │ • Null key field check        │  │
    │  │ • Data quality checks         │  │
    │  │ • MATCH/MISMATCH status       │  │
    │  └───────────────────────────────┘  │
    └─────────────────────────────────────┘
```

---

## Step-by-Step Demo Script

### Pre-requisites

1. **Datasource Configuration exists** in `cis_datasource_mng`:
   ```sql
   SELECT source_name, target_table, separator, intake_columns
   FROM gmp_cis.cis_datasource_mng
   WHERE source_name LIKE '%External_upload%';
   ```

2. **Target table exists** (e.g., `cis_user_sta_adhoc_position_1`)

3. **Sample CSV files** ready:
   - `CIS_External_upload_format_1.csv` (valid, 11 rows)
   - `CIS_External_upload_format_1_with_duplicates.csv` (14 rows, 3 duplicates)
   - `wrong_file.csv` (wrong filename - not configured)
   - `CIS_External_upload_format_1_bad_columns.csv` (wrong column names)

---

### Demo Scenario 1: Happy Path (Valid File)

**Objective:** Show successful upload and ingestion

1. **Navigate to Upload List**
   - URL: `/upload/`
   - Show statistics cards (Total, Pending, Completed, Failed)

2. **Click "Upload File"**
   - URL: `/upload/create/`

3. **Select File**
   - Choose `CIS_External_upload_format_1.csv`
   - System automatically:
     - Detects file type: CSV
     - Detects delimiter: comma
     - Parses 11 data rows
     - Matches with datasource config

4. **Show Preview Screen**
   - URL: `/upload/{id}/preview/`
   - Display:
     - File info (size, rows, columns)
     - Schema (column names, types)
     - Sample data (first 10 rows)
     - Target table: `cis_user_sta_adhoc_position_1`
     - Processing date from HDFS

5. **Click "Ingest to Hive"**
   - System:
     - Reads all rows
     - Adds system columns
     - Executes INSERT OVERWRITE
   - Success message: "Successfully ingested 11 rows"

6. **Show Detail Page with Reconciliation**
   - URL: `/upload/{id}/`
   - Reconciliation section shows:
     - Source File Rows: 11
     - Table Records: 11
     - Status: ✓ Match
     - Data Quality Checks: All Pass

---

### Demo Scenario 2: Duplicate Handling

**Objective:** Show duplicate detection and removal

1. **Upload File with Duplicates**
   - Choose `CIS_External_upload_format_1_with_duplicates.csv`
   - File has 14 rows (11 unique + 3 duplicates)

2. **Validation Warning**
   - System shows: "Found 3 duplicate row(s) in source file"

3. **Preview Screen**
   - Shows warning badge about duplicates

4. **Ingest**
   - System:
     - Removes 3 duplicates
     - Inserts 11 unique rows
   - Success: "Ingested 11 rows (3 duplicate rows removed from source)"

5. **Reconciliation**
   - Source File Rows: 14 (original)
   - Table Records: 11 (after dedup)
   - Duplicates Removed: 3
   - Status: ✓ Match (correct behavior)

---

### Demo Scenario 3: Overwrite Mode (Default)

**Objective:** Show partition overwrite behavior

1. **First Upload**
   - Upload `CIS_External_upload_format_1.csv` with processing_date=20260304
   - Keep default mode: **Overwrite**
   - Result: 11 rows in table

2. **Verify in Database**
   ```sql
   SELECT COUNT(*) FROM gmp_cis.cis_user_sta_adhoc_position_1
   WHERE processing_date = '20260304';
   -- Returns: 11
   ```

3. **Second Upload (Same Date, Overwrite)**
   - Upload same file again
   - Keep mode: **Overwrite**
   - System uses INSERT OVERWRITE

4. **Verify No Duplication**
   ```sql
   SELECT COUNT(*) FROM gmp_cis.cis_user_sta_adhoc_position_1
   WHERE processing_date = '20260304';
   -- Still returns: 11 (not 22) - data was replaced
   ```

---

### Demo Scenario 3b: Append Mode (Delta Load)

**Objective:** Show append behavior for incremental data

1. **First Upload (Base Data)**
   - Upload `CIS_External_upload_format_1.csv` (11 rows)
   - Mode: **Overwrite** (to start fresh)
   - Result: 11 rows in table

2. **Verify Base Data**
   ```sql
   SELECT COUNT(*) FROM gmp_cis.cis_user_sta_adhoc_position_1
   WHERE processing_date = '20260304';
   -- Returns: 11
   ```

3. **Second Upload (Delta Data, Append)**
   - Upload `CIS_External_upload_format_1_delta.csv` (5 new rows)
   - **Select: Append Mode**
   - System uses INSERT INTO

4. **Verify Data Added**
   ```sql
   SELECT COUNT(*) FROM gmp_cis.cis_user_sta_adhoc_position_1
   WHERE processing_date = '20260304';
   -- Returns: 16 (11 + 5)
   ```

5. **Explain UI**
   - Show toggle buttons: Overwrite (red) vs Append (green)
   - Show confirmation message for each mode

---

### Demo Scenario 4: Negative Case - Wrong Filename

**Objective:** Show validation error for unconfigured file

1. **Upload `wrong_file.csv`**

2. **System Response**
   - Error: "No datasource configuration found for file: wrong_file.csv"
   - Status: VALIDATION_FAILED

3. **Explain**
   - File must match `source_name` in `cis_datasource_mng`

---

### Demo Scenario 5: Negative Case - Wrong Columns

**Objective:** Show column mismatch error

1. **Upload `CIS_External_upload_format_1_bad_columns.csv`**
   - File has columns: `col1, col2, col3` (wrong names)

2. **System Response**
   - Error: "Column mismatch. Missing: portfolio, isin_code, ..."
   - Status: VALIDATION_FAILED

---

### Demo Scenario 6: Data Quality Check

**Objective:** Show reconciliation catches issues

1. **Upload file with null key fields**

2. **After Ingestion, Reconciliation Shows**
   - Null/Empty Key Fields: 2 (red warning)
   - Data Quality Check: "No null/empty key fields" - ✗ Fail

---

## Key Features Highlight

| Feature | Description |
|---------|-------------|
| **Metadata-Driven** | File → datasource config → target table (automatic) |
| **Duplicate Detection** | Warns during validation, removes before insert |
| **Overwrite/Append Mode** | User chooses to replace or add to existing data |
| **Reconciliation** | Source vs Table comparison with quality checks |
| **Refresh Button** | Real-time recon data without page reload |

---

## Ingestion Modes

### Overwrite Mode (Default)
- Replaces ALL existing data for the same `processing_date`
- Use when re-uploading corrected data
- Uses `INSERT OVERWRITE PARTITION`

### Append Mode
- Adds new rows to existing data (delta load)
- Use for incremental data uploads
- Uses `INSERT INTO PARTITION`
- Duplicates within the uploaded file are still removed

```
┌─────────────────────────────────────────────────────────────┐
│                    INGESTION MODE                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────┐              ┌─────────────┐              │
│   │  OVERWRITE  │              │   APPEND    │              │
│   │  (Default)  │              │  (Delta)    │              │
│   └──────┬──────┘              └──────┬──────┘              │
│          │                            │                      │
│          ▼                            ▼                      │
│   ┌─────────────┐              ┌─────────────┐              │
│   │ DELETE old  │              │ KEEP old    │              │
│   │ INSERT new  │              │ INSERT new  │              │
│   └─────────────┘              └─────────────┘              │
│                                                              │
│   Result: ONLY new data        Result: OLD + NEW data       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Technical Architecture

```
┌────────────────┐    ┌─────────────────┐    ┌──────────────────┐
│   Django UI    │───▶│  Upload Service │───▶│ Impala/Hive      │
│  (Templates)   │    │  (Validation,   │    │ (External Table) │
│                │    │   Dedup, Insert)│    │                  │
└────────────────┘    └─────────────────┘    └──────────────────┘
        │                     │
        │                     ▼
        │             ┌─────────────────┐
        │             │ cis_datasource  │
        │             │     _mng        │
        │             │ (Config Table)  │
        │             └─────────────────┘
        │
        ▼
┌────────────────┐
│ cis_file_upload│
│ (Tracking Table)│
└────────────────┘
```

---

## SQL Queries for Demo

### Check Datasource Config
```sql
SELECT source_id, source_name, target_table, separator
FROM gmp_cis.cis_datasource_mng
WHERE source_name LIKE 'CIS_External%'
ORDER BY source_name;
```

### Verify Uploaded Data
```sql
SELECT processing_date, src_system, COUNT(*) as cnt
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20260304'
GROUP BY processing_date, src_system;
```

### Check for Duplicates in Table
```sql
SELECT portfolio, isin_code, trade_date, COUNT(*) as cnt
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '20260304'
GROUP BY portfolio, isin_code, trade_date
HAVING COUNT(*) > 1;
```

### Check Upload History
```sql
SELECT upload_id, file_name, status, row_count, created_at
FROM gmp_cis.cis_file_upload
ORDER BY created_at DESC
LIMIT 10;
```

---

## Demo Checklist

| # | Step | Status |
|---|------|--------|
| 1 | Show upload list with stats | ☐ |
| 2 | Upload valid file | ☐ |
| 3 | Show preview with schema | ☐ |
| 4 | Ingest to Hive | ☐ |
| 5 | Show reconciliation (Match) | ☐ |
| 6 | Upload file with duplicates | ☐ |
| 7 | Show duplicate warning | ☐ |
| 8 | Show duplicates removed in recon | ☐ |
| 9 | Re-upload same date (overwrite) | ☐ |
| 10 | Verify no data duplication | ☐ |
| 11 | Upload wrong filename | ☐ |
| 12 | Show validation error | ☐ |
| 13 | Explain metadata-driven flow | ☐ |

---

## Q&A Preparation

**Q: What happens if I upload the same file twice?**
A: It depends on the mode you select:
- **Overwrite mode** (default): Data is replaced, not appended
- **Append mode**: Data is added to existing records

**Q: When should I use Append mode?**
A: Use Append mode for delta/incremental loads - when you want to add new data without removing existing records for the same processing_date.

**Q: How are duplicates handled?**
A: Duplicates are detected during validation (warning) and removed before insertion. Only unique rows are inserted.

**Q: How do I know if upload was successful?**
A: The reconciliation section shows Match/Mismatch status comparing source rows vs table records.

**Q: Can I upload any CSV file?**
A: No, the file must be configured in `cis_datasource_mng` table with matching source_name.

**Q: What columns are added automatically?**
A: `src_id`, `src_system`, `sub_system`, `data_cat`, `data_frq`, `processing_date`

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-04 | Claude | Initial version |
