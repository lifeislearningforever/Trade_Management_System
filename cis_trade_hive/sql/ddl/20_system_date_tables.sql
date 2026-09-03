-- ============================================================================
-- System Date Table for CIS Trade Hive
-- ============================================================================
-- Purpose: Store system date from GMP upstream (MRC_PC_DATE.txt)
--
-- Date Logic:
--   - report_date: Date from GMP file (T-1)
--   - processing_date: Same as report_date
--   - system_date: report_date + 1 (actual business date T)
--
-- Author: CIS Trade Hive Team
-- Created: 2026-04-08
-- ============================================================================

-- Use the GMP CIS database
USE gmp_cis;

-- ============================================================================
-- System Date Table (from GMP upstream MRC_PC_DATE.txt)
-- ============================================================================
-- This table is updated daily by ETL process that reads MRC_PC_DATE.txt
-- Only one active row should exist (latest file date)

CREATE TABLE IF NOT EXISTS gmp_cis.cis_system_date (
    -- Primary key
    date_id BIGINT PRIMARY KEY,

    -- Date fields
    system_date STRING COMMENT 'Business date T (file_date + 1), format YYYYMMDD',
    report_date STRING COMMENT 'Report date T-1 (from GMP file), format YYYYMMDD',
    processing_date STRING COMMENT 'Processing date (same as report_date), format YYYYMMDD',

    -- Source tracking
    source_file STRING COMMENT 'Source file name (e.g., MRC_PC_DATE.txt)',
    file_date_raw STRING COMMENT 'Raw date string from file',

    -- Status
    is_active BOOLEAN DEFAULT true COMMENT 'Only one row should be active',
    is_business_day BOOLEAN DEFAULT true COMMENT 'Whether system_date is a business day',

    -- Audit fields
    loaded_by STRING COMMENT 'ETL job or user who loaded this',
    loaded_at BIGINT COMMENT 'Timestamp when loaded (epoch ms)',
    created_at BIGINT COMMENT 'Record creation timestamp (epoch ms)',
    updated_at BIGINT COMMENT 'Record update timestamp (epoch ms)'
)
PARTITION BY HASH(date_id) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.table_name' = 'cis_system_date',
    'kudu.num_tablet_replicas' = '1'
);

-- ============================================================================
-- Sample Data: Insert initial system date (for testing)
-- In production, this would be loaded by ETL from MRC_PC_DATE.txt
-- ============================================================================

-- Example: If GMP file contains 20260407 (report date T-1)
-- Then system_date = 20260408 (business date T)
UPSERT INTO gmp_cis.cis_system_date (
    date_id, system_date, report_date, processing_date,
    source_file, file_date_raw,
    is_active, is_business_day,
    loaded_by, loaded_at, created_at, updated_at
) VALUES (
    1, '20260408', '20260407', '20260407',
    'MRC_PC_DATE.txt', '20260407',
    true, true,
    'SYSTEM', UNIX_TIMESTAMP() * 1000, UNIX_TIMESTAMP() * 1000, UNIX_TIMESTAMP() * 1000
);

-- ============================================================================
-- Verification Queries
-- ============================================================================

-- Check current system date
-- SELECT * FROM gmp_cis.cis_system_date WHERE is_active = true;
