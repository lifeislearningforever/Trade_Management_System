# File Upload & Ingestion

> **Audience:** User, BA, SA, Developer, Support
> **Read time:** ~6 minutes

---

## What Is File Upload?

The File Upload module lets authorised users upload bulk data files into CIS. Instead of entering records one by one, you can upload a CSV (or other format) and the system creates a queryable dataset from it.

Uploaded files are stored on HDFS and made available as Hive external tables — meaning they can be queried with Impala SQL alongside regular CIS tables.

---

## Supported File Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| CSV | `.csv` | Auto-detects delimiter (comma, pipe, tab) |
| TSV | `.tsv` | Tab-separated |
| Parquet | `.parquet` | Binary columnar format — most efficient |
| Excel | `.xlsx`, `.xls` | First sheet is read |
| JSON | `.json` | Array of objects |
| Text | `.txt` | Treated as CSV with auto-delimiter detection |

---

## Upload Flow

```
User selects file
  │
  ▼ Validation
  │   • File format supported?
  │   • File size within limit?
  │   • Encoding valid (UTF-8)?
  │   • File not empty?
  │
  ▼ Schema Detection (first 100 rows)
  │   • Auto-detect delimiter
  │   • Detect header row (yes/no)
  │   • Detect each column's data type
  │   • Count rows and columns
  │
  ▼ Preview shown to user
  │   • First 100 rows displayed
  │   • User confirms column names/types or adjusts
  │
  ▼ Upload confirmed
  │
  ▼ File written to HDFS
  │   Location: /user/cis/uploads/<upload_id>/
  │
  ▼ Hive external table created (if requested)
  │   CREATE EXTERNAL TABLE gmp_cis.upload_<upload_id>
  │   (col1 STRING, col2 DECIMAL, ...)
  │   STORED AS PARQUET
  │   LOCATION '/user/cis/uploads/<upload_id>/'
  │
  ▼ Metadata saved in cis_file_upload (Kudu)
  │   upload_id, file_name, row_count, column_count,
  │   hdfs_path, table_name, status, created_by
  │
  ▼ Data available for querying via Impala
```

---

## cis_file_upload Table

Every upload job creates a record in `cis_file_upload`:

| Column | Description |
|--------|-------------|
| `upload_id` | Unique ID |
| `file_name` | Original filename |
| `file_path` | HDFS path |
| `row_count` | Number of data rows |
| `column_count` | Number of columns |
| `table_name` | Created Hive external table name |
| `status` | PENDING / PROCESSING / COMPLETED / FAILED |
| `created_by` | User who uploaded |
| `created_at` | Upload timestamp |

---

## For Developers: Key Files

| File | Purpose |
|------|---------|
| `upload/services/upload_service.py` | File validation and processing |
| `upload/repositories/upload_kudu_repository.py` | SQL on `cis_file_upload` |
| `upload/repositories/datasource_repository.py` | Data source configuration |
| `upload/views.py` | Upload UI views |
| `sql/ddl/21_file_upload_table.sql` | Upload metadata table DDL |
| `sql/ddl/20_ingestion_framework.sql` | Ingestion metadata and staging DDL |

---

## For Support: Common Issues

| Issue | Check |
|-------|-------|
| Upload fails at validation | Check file format — is it in the supported list? Is it UTF-8 encoded? |
| Schema detection wrong | User can manually adjust column types in the preview step |
| "HDFS write error" | Check HDFS quota and permissions for `/user/cis/uploads/` |
| Hive table not queryable | Check if table creation succeeded — query `cis_file_upload` for status |
| Large file times out | For Parquet files, consider using `hdfs dfs -put` directly and then registering the table manually |
