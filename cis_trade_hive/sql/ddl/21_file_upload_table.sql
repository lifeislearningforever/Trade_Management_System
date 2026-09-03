-- ============================================================
-- File Upload Table DDL
-- Apache Kudu table for tracking file uploads and Hive ingestion
-- ============================================================

-- Drop table if exists (for recreation)
-- DROP TABLE IF EXISTS gmp_cis.cis_file_upload;

-- Create cis_file_upload table
CREATE TABLE IF NOT EXISTS gmp_cis.cis_file_upload (
    upload_id STRING,
    file_name STRING,
    original_file_name STRING,
    file_path STRING,
    hdfs_path STRING,
    file_type STRING,
    mime_type STRING,
    file_size BIGINT,
    `encoding` STRING,
    delimiter STRING,
    has_header BOOLEAN,
    row_count INT,
    column_count INT,
    schema_json STRING,
    sample_data_json STRING,
    validation_errors_json STRING,
    status STRING,
    target_table_name STRING,
    target_database STRING,
    description STRING,
    is_deleted BOOLEAN DEFAULT false,
    created_by STRING,
    created_at TIMESTAMP,
    updated_by STRING,
    updated_at TIMESTAMP,
    PRIMARY KEY (upload_id)
)
PARTITION BY HASH(upload_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'localhost:7051',
    'kudu.table_name' = 'cis_file_upload'
);

-- Verify table creation
DESCRIBE gmp_cis.cis_file_upload;

-- Sample status values:
-- PENDING - File uploaded, awaiting validation
-- VALIDATING - File validation in progress
-- VALIDATED - File validated successfully, ready for ingestion
-- VALIDATION_FAILED - File validation failed
-- INGESTING - Ingesting to Hive external table
-- COMPLETED - Successfully ingested to Hive
-- FAILED - Ingestion failed
-- CANCELLED - Upload cancelled by user

-- Example: List all uploads
-- SELECT * FROM gmp_cis.cis_file_upload WHERE deleted_at IS NULL ORDER BY created_at DESC;

-- Example: Get upload statistics
-- SELECT status, COUNT(*) as count FROM gmp_cis.cis_file_upload WHERE deleted_at IS NULL GROUP BY status;
