-- ============================================================================
-- System Date Tables for CIS Trade Hive
-- ============================================================================
-- Purpose: Store system date from GMP upstream and configuration overrides
--
-- Tables:
--   1. cis_system_date - Stores GMP file date (MRC_PC_DATE.txt)
--   2. cis_system_config - Configuration overrides (date override, EOD lock, etc.)
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
-- 1. System Date Table (from GMP upstream MRC_PC_DATE.txt)
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
-- 2. System Configuration Table (for overrides and settings)
-- ============================================================================
-- Stores application-wide configuration including date overrides

CREATE TABLE IF NOT EXISTS gmp_cis.cis_system_config (
    -- Primary key
    config_key STRING PRIMARY KEY COMMENT 'Unique config key (e.g., SYSTEM_DATE_OVERRIDE)',

    -- Configuration values
    config_value STRING COMMENT 'The configuration value',
    config_type STRING COMMENT 'Data type: DATE, BOOLEAN, STRING, INTEGER',

    -- Metadata
    description STRING COMMENT 'Human readable description',
    category STRING COMMENT 'Category: SYSTEM_DATE, EOD, SECURITY, etc.',

    -- Status
    is_active BOOLEAN DEFAULT true COMMENT 'Enable/disable this config',

    -- Validation
    valid_from STRING COMMENT 'Config valid from date (YYYYMMDD)',
    valid_to STRING COMMENT 'Config valid until date (YYYYMMDD), NULL = no expiry',

    -- Audit fields
    created_by STRING,
    created_at BIGINT,
    updated_by STRING,
    updated_at BIGINT
)
PARTITION BY HASH(config_key) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.table_name' = 'cis_system_config',
    'kudu.num_tablet_replicas' = '1'
);

-- ============================================================================
-- 3. System Date History Table (audit trail)
-- ============================================================================
-- Tracks all changes to system date (GMP loads and overrides)

CREATE TABLE IF NOT EXISTS gmp_cis.cis_system_date_history (
    -- Primary key
    history_id BIGINT PRIMARY KEY,

    -- Reference
    date_id BIGINT COMMENT 'Reference to cis_system_date.date_id',

    -- Action
    action STRING COMMENT 'Action: LOAD, OVERRIDE, CLEAR_OVERRIDE, EOD_LOCK, EOD_UNLOCK',

    -- Date values at time of action
    system_date STRING,
    report_date STRING,
    processing_date STRING,

    -- Override details (if applicable)
    override_date STRING COMMENT 'The override date if action=OVERRIDE',
    override_reason STRING COMMENT 'Reason for override',

    -- Who and when
    performed_by STRING,
    performed_at BIGINT,

    -- Additional context
    ip_address STRING,
    user_agent STRING,
    notes STRING
)
PARTITION BY HASH(history_id) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.table_name' = 'cis_system_date_history',
    'kudu.num_tablet_replicas' = '1'
);

-- ============================================================================
-- 4. User Session Override Table (per-user date override)
-- ============================================================================
-- Allows individual users to override system date for their session

CREATE TABLE IF NOT EXISTS gmp_cis.cis_user_date_override (
    -- Primary key (composite: user + session)
    override_id BIGINT PRIMARY KEY,

    -- User identification
    username STRING NOT NULL COMMENT 'User login',
    session_id STRING COMMENT 'Session ID (optional, for session-specific override)',

    -- Override values
    override_date STRING NOT NULL COMMENT 'The overridden system date (YYYYMMDD)',
    override_reason STRING COMMENT 'Reason for override',

    -- Status
    is_active BOOLEAN DEFAULT true,

    -- Validity
    valid_until BIGINT COMMENT 'Override expires at this timestamp (epoch ms)',

    -- Audit
    created_by STRING,
    created_at BIGINT,
    updated_at BIGINT
)
PARTITION BY HASH(override_id) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.table_name' = 'cis_user_date_override',
    'kudu.num_tablet_replicas' = '1'
);

-- ============================================================================
-- Insert Default Configuration
-- ============================================================================

-- Global date override config (disabled by default)
UPSERT INTO gmp_cis.cis_system_config (
    config_key, config_value, config_type, description, category,
    is_active, valid_from, valid_to,
    created_by, created_at, updated_by, updated_at
) VALUES (
    'SYSTEM_DATE_OVERRIDE', NULL, 'DATE',
    'Global system date override (YYYYMMDD). When set, all users use this date instead of GMP file date.',
    'SYSTEM_DATE',
    false, NULL, NULL,
    'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- EOD lock config
UPSERT INTO gmp_cis.cis_system_config (
    config_key, config_value, config_type, description, category,
    is_active, valid_from, valid_to,
    created_by, created_at, updated_by, updated_at
) VALUES (
    'EOD_LOCK', 'false', 'BOOLEAN',
    'End of Day lock. When true, system date cannot be changed and trading may be restricted.',
    'SYSTEM_DATE',
    true, NULL, NULL,
    'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- Allow user override config
UPSERT INTO gmp_cis.cis_system_config (
    config_key, config_value, config_type, description, category,
    is_active, valid_from, valid_to,
    created_by, created_at, updated_by, updated_at
) VALUES (
    'ALLOW_USER_DATE_OVERRIDE', 'true', 'BOOLEAN',
    'Allow individual users to override system date for their session.',
    'SYSTEM_DATE',
    true, NULL, NULL,
    'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- Max days back for override
UPSERT INTO gmp_cis.cis_system_config (
    config_key, config_value, config_type, description, category,
    is_active, valid_from, valid_to,
    created_by, created_at, updated_by, updated_at
) VALUES (
    'MAX_OVERRIDE_DAYS_BACK', '30', 'INTEGER',
    'Maximum number of days back a user can set system date override.',
    'SYSTEM_DATE',
    true, NULL, NULL,
    'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- Max days forward for override
UPSERT INTO gmp_cis.cis_system_config (
    config_key, config_value, config_type, description, category,
    is_active, valid_from, valid_to,
    created_by, created_at, updated_by, updated_at
) VALUES (
    'MAX_OVERRIDE_DAYS_FORWARD', '5', 'INTEGER',
    'Maximum number of days forward a user can set system date override.',
    'SYSTEM_DATE',
    true, NULL, NULL,
    'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
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

-- Check configuration
-- SELECT * FROM gmp_cis.cis_system_config WHERE category = 'SYSTEM_DATE';

-- Check user overrides
-- SELECT * FROM gmp_cis.cis_user_date_override WHERE is_active = true;
