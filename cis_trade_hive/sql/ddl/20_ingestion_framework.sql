-- ============================================================================
-- DATA INGESTION FRAMEWORK DDL
-- ============================================================================
-- Creates metadata and reconciliation tables for the ingestion framework
-- All tables use Hive External with Parquet format
-- Database: gmp_cis
-- Created: 2026-02-10
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- HDFS DIRECTORY SETUP
-- ============================================================================
-- Run these commands before creating tables:
-- hdfs dfs -mkdir -p /data/gmp_cis/ingestion/cis_ingestion_config
-- hdfs dfs -mkdir -p /data/gmp_cis/ingestion/cis_ingestion_recon
-- hdfs dfs -chmod 777 /data/gmp_cis/ingestion/cis_ingestion_config
-- hdfs dfs -chmod 777 /data/gmp_cis/ingestion/cis_ingestion_recon
-- ============================================================================


-- ============================================================================
-- TABLE 1: cis_ingestion_config (Metadata Configuration)
-- ============================================================================
-- Stores all file ingestion configurations
-- PK: config_id
-- Used by: generic_file_ingest.py
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_ingestion_config;

CREATE EXTERNAL TABLE gmp_cis.cis_ingestion_config (
    -- Primary Key
    config_id               BIGINT,

    -- Source Configuration
    source_id               STRING,              -- Unique source identifier (e.g., 'GMP_POSITIONS')
    source_name             STRING,              -- Human-readable name
    source_description      STRING,              -- Description of the data source
    source_system           STRING,              -- Source system (GMP, AMS, IMS, CIS)

    -- File Configuration
    file_type               STRING,              -- FILE_TYPE: CSV, TXT, PIPE, FIXED_WIDTH
    file_name_pattern       STRING,              -- Regex pattern (e.g., 'positions_*.csv')
    file_path               STRING,              -- HDFS/local path pattern
    file_encoding           STRING,              -- File encoding (default: UTF-8)
    has_header              BOOLEAN,             -- First row is header (default: TRUE)
    skip_rows               INT,                 -- Rows to skip at beginning
    skip_footer_rows        INT,                 -- Rows to skip at end

    -- Delimiter Configuration
    column_delimiter        STRING,              -- Column separator (default: ',')
    quote_char              STRING,              -- Quote character (default: '"')
    escape_char             STRING,              -- Escape character (default: '\')
    null_string             STRING,              -- String representing NULL

    -- Column Definition (JSON array)
    -- Format: [{"name": "col1", "type": "STRING", "source_position": 0}, ...]
    column_schema           STRING,

    -- Target Configuration
    target_database         STRING,              -- Target database (gmp_cis)
    target_table            STRING,              -- Target table name
    target_location         STRING,              -- HDFS location for Parquet files

    -- Partition Configuration
    partition_columns       STRING,              -- Comma-separated partition cols
    partition_type          STRING,              -- STATIC or DYNAMIC partitioning

    -- Load Mode Configuration
    default_load_mode       STRING,              -- FULL, DELTA, OVERWRITE_PARTITION, MERGE
    primary_key_columns     STRING,              -- Comma-separated PK for delta detection
    watermark_column        STRING,              -- Column for incremental/delta loads

    -- Validation Rules (JSON)
    -- Format: [{"column": "amount", "rule": "NOT_NULL"}, ...]
    validation_rules        STRING,

    -- Transformation Rules (JSON)
    -- Format: [{"column": "date", "transform": "TO_DATE(date, 'yyyyMMdd')"}, ...]
    transformations         STRING,

    -- Scheduling
    schedule_frequency      STRING,              -- HOURLY, DAILY, WEEKLY, MONTHLY, ON_DEMAND
    expected_arrival_time   STRING,              -- Expected file arrival (HH:MM)
    sla_minutes             INT,                 -- SLA in minutes from expected time

    -- Status
    is_active               BOOLEAN,             -- Active flag
    priority                INT,                 -- Processing priority (1=highest)

    -- Audit
    created_by              STRING,
    created_at              STRING,
    updated_by              STRING,
    updated_at              STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/ingestion/cis_ingestion_config'
TBLPROPERTIES (
    'parquet.compression' = 'SNAPPY'
);


-- ============================================================================
-- TABLE 2: cis_ingestion_recon (Reconciliation/Audit)
-- ============================================================================
-- Tracks every ingestion run with detailed metrics
-- Partitioned by: processing_date
-- Used for: Monitoring, auditing, troubleshooting
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_ingestion_recon;

CREATE EXTERNAL TABLE gmp_cis.cis_ingestion_recon (
    -- Primary Key
    recon_id                BIGINT,              -- Unique recon identifier (timestamp-based)

    -- Job Reference
    config_id               BIGINT,              -- FK to cis_ingestion_config
    source_id               STRING,              -- Source identifier
    batch_id                STRING,              -- Unique batch identifier

    -- Run Information
    run_mode                STRING,              -- FULL, DELTA, OVERWRITE_PARTITION, MERGE
    run_environment         STRING,              -- DEV, UAT, PROD
    spark_app_id            STRING,              -- Spark application ID

    -- File Information
    file_name               STRING,              -- Actual file processed
    file_path               STRING,              -- Full path to file
    file_size_bytes         BIGINT,              -- File size in bytes
    file_modified_time      STRING,              -- File last modified timestamp
    file_checksum           STRING,              -- MD5/SHA256 checksum

    -- Record Counts (Source)
    source_total_rows       BIGINT,              -- Total rows in source file
    source_header_rows      INT,                 -- Header rows skipped
    source_footer_rows      INT,                 -- Footer rows skipped
    source_data_rows        BIGINT,              -- Actual data rows

    -- Record Counts (Processing)
    rows_read               BIGINT,              -- Rows successfully read
    rows_parsed             BIGINT,              -- Rows successfully parsed
    rows_validated          BIGINT,              -- Rows passing validation
    rows_transformed        BIGINT,              -- Rows successfully transformed
    rows_rejected           BIGINT,              -- Rows failing validation
    rows_duplicate          BIGINT,              -- Duplicate rows found

    -- Record Counts (Target)
    rows_inserted           BIGINT,              -- New rows inserted
    rows_updated            BIGINT,              -- Existing rows updated (for delta)
    rows_deleted            BIGINT,              -- Rows deleted (for full refresh)
    rows_unchanged          BIGINT,              -- Rows with no changes (for delta)
    target_total_rows       BIGINT,              -- Total rows in target after load

    -- Partition Information
    partitions_processed    STRING,              -- JSON array of processed partitions
    partitions_overwritten  INT,                 -- Number of partitions overwritten

    -- Data Quality Metrics
    null_count_by_column    STRING,              -- JSON: {"col1": 10, "col2": 0}
    validation_errors       STRING,              -- JSON array of validation errors
    data_quality_score      DECIMAL(5,2),        -- 0-100% quality score

    -- Performance Metrics
    start_time              STRING,              -- Job start timestamp
    end_time                STRING,              -- Job end timestamp
    duration_seconds        INT,                 -- Total duration
    read_time_seconds       INT,                 -- Time to read file
    transform_time_seconds  INT,                 -- Time for transformations
    write_time_seconds      INT,                 -- Time to write to target

    -- Spark Metrics
    executor_count          INT,                 -- Number of executors
    total_cores             INT,                 -- Total cores used
    peak_memory_mb          BIGINT,              -- Peak memory usage
    shuffle_bytes           BIGINT,              -- Shuffle data size

    -- Status
    status                  STRING,              -- RUNNING, SUCCESS, PARTIAL, FAILED
    error_message           STRING,              -- Error details if failed
    error_stack_trace       STRING,              -- Full stack trace
    warning_count           INT,                 -- Number of warnings
    warnings                STRING,              -- JSON array of warnings

    -- Reconciliation Checks
    recon_status            STRING,              -- MATCHED, UNMATCHED, PENDING
    recon_notes             STRING,              -- Manual recon notes
    recon_by                STRING,              -- User who verified
    recon_at                STRING,              -- Verification timestamp

    -- Retry Information
    retry_count             INT,                 -- Number of retries
    is_rerun                BOOLEAN,             -- Is this a rerun
    original_batch_id       STRING,              -- Original batch if rerun

    -- Audit
    created_at              STRING,
    created_by              STRING
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/data/gmp_cis/ingestion/cis_ingestion_recon'
TBLPROPERTIES (
    'parquet.compression' = 'SNAPPY'
);


-- ============================================================================
-- SEQUENCE INITIALIZATION
-- ============================================================================

UPSERT INTO gmp_cis.cis_sequence VALUES ('ingestion_config_id', 1000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('ingestion_recon_id', 1000000, 1);


-- ============================================================================
-- SAMPLE CONFIGURATION DATA
-- ============================================================================
-- Example: GMP Daily Positions File

-- Note: Run this INSERT after creating the table
/*
INSERT INTO gmp_cis.cis_ingestion_config VALUES (
    1001,                                    -- config_id
    'GMP_POSITIONS',                         -- source_id
    'GMP Daily Positions',                   -- source_name
    'Daily position file from Global Markets Platform',
    'GMP',                                   -- source_system
    'CSV',                                   -- file_type
    'gmp_positions_{YYYYMMDD}.csv',          -- file_name_pattern
    '/data/incoming/gmp',                    -- file_path
    'UTF-8',                                 -- file_encoding
    TRUE,                                    -- has_header
    0,                                       -- skip_rows
    0,                                       -- skip_footer_rows
    ',',                                     -- column_delimiter
    '"',                                     -- quote_char
    '\\',                                    -- escape_char
    '',                                      -- null_string
    '[
        {"name": "portfolio_id", "type": "STRING", "source_position": 0, "nullable": false},
        {"name": "security_label", "type": "STRING", "source_position": 1, "nullable": false},
        {"name": "isin", "type": "STRING", "source_position": 2},
        {"name": "quantity", "type": "DECIMAL(20,6)", "source_position": 3},
        {"name": "market_value", "type": "DECIMAL(20,6)", "source_position": 4},
        {"name": "price_date", "type": "STRING", "source_position": 5, "format": "yyyyMMdd"}
    ]',                                      -- column_schema
    'gmp_cis',                               -- target_database
    'stg_gmp_positions',                     -- target_table
    '/data/gmp_cis/staging/stg_gmp_positions', -- target_location
    'processing_date,src_system',            -- partition_columns
    'DYNAMIC',                               -- partition_type
    'OVERWRITE_PARTITION',                   -- default_load_mode
    'portfolio_id,security_label,price_date', -- primary_key_columns
    'price_date',                            -- watermark_column
    '[
        {"column": "portfolio_id", "rule": "NOT_NULL"},
        {"column": "security_label", "rule": "NOT_NULL"},
        {"column": "quantity", "rule": "POSITIVE"}
    ]',                                      -- validation_rules
    '[
        {"column": "security_label", "transform": "UPPER(TRIM(security_label))"},
        {"column": "src_system", "transform": "LITERAL(''GMP'')"},
        {"column": "price_date", "transform": "TO_DATE(price_date, ''yyyyMMdd'')"}
    ]',                                      -- transformations
    'DAILY',                                 -- schedule_frequency
    '06:00',                                 -- expected_arrival_time
    60,                                      -- sla_minutes
    TRUE,                                    -- is_active
    5,                                       -- priority
    'SYSTEM',                                -- created_by
    '2026-02-10 00:00:00',                   -- created_at
    NULL,                                    -- updated_by
    NULL                                     -- updated_at
);
*/


-- ============================================================================
-- VERIFICATION
-- ============================================================================

DESCRIBE gmp_cis.cis_ingestion_config;
DESCRIBE gmp_cis.cis_ingestion_recon;

SELECT * FROM gmp_cis.cis_sequence WHERE sequence_name LIKE 'ingestion%';


-- ============================================================================
-- MONITORING QUERIES
-- ============================================================================

-- Daily ingestion summary
/*
SELECT
    source_id,
    processing_date,
    status,
    rows_read,
    rows_validated,
    rows_rejected,
    data_quality_score,
    duration_seconds
FROM gmp_cis.cis_ingestion_recon
WHERE processing_date = CURRENT_DATE()
ORDER BY source_id;
*/

-- Failed jobs
/*
SELECT
    source_id,
    batch_id,
    error_message,
    start_time
FROM gmp_cis.cis_ingestion_recon
WHERE processing_date = CURRENT_DATE()
AND status = 'FAILED';
*/

-- High rejection rate
/*
SELECT
    source_id,
    batch_id,
    rows_rejected,
    rows_read,
    ROUND(rows_rejected * 100.0 / rows_read, 2) as rejection_pct
FROM gmp_cis.cis_ingestion_recon
WHERE processing_date = CURRENT_DATE()
AND rows_rejected > 0
ORDER BY rejection_pct DESC;
*/


-- ============================================================================
-- END OF DDL
-- ============================================================================
