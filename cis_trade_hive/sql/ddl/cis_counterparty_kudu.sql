-- ============================================================================
-- CIS Counterparty Kudu Table - Stable Primary Key for Django Application
-- ============================================================================
-- Purpose: Replace gmp_cis_sta_dly_counterparty with application-friendly Kudu table
-- Primary Key: counterparty_short_name (stable, no daily changes)
-- Author: Claude Code
-- Date: 2025-01-07
-- ============================================================================

USE gmp_cis;

-- Drop old Hive staging table (replaced by Kudu)
DROP TABLE IF EXISTS gmp_cis_sta_dly_counterparty;

-- Drop existing Kudu table if exists
DROP TABLE IF EXISTS cis_counterparty_kudu;

-- Create new Kudu table with stable primary key
CREATE TABLE cis_counterparty_kudu (
    -- Primary Key (Stable - Never changes!)
    counterparty_short_name STRING NOT NULL,       -- Natural key from source system

    -- CIF/M-Label (from issuer reference data)
    m_label STRING,                                 -- CIF number for corporates (75% matched)

    -- Core Counterparty Information
    counterparty_full_name STRING,
    record_type STRING,

    -- Address Information
    address_line_0 STRING,
    address_line_1 STRING,
    address_line_2 STRING,
    address_line_3 STRING,
    city STRING,
    country STRING,
    postal_code STRING,

    -- Contact Information
    fax_number STRING,
    telex_number STRING,
    primary_contact STRING,
    primary_number STRING,
    other_contact STRING,
    other_number STRING,

    -- Classification
    industry STRING,
    industry_group STRING,

    -- Boolean Flags (Converted from Y/N strings)
    is_broker BOOLEAN DEFAULT FALSE,
    is_custodian BOOLEAN DEFAULT FALSE,
    is_issuer BOOLEAN DEFAULT FALSE,
    is_bank BOOLEAN DEFAULT FALSE,
    is_subsidiary BOOLEAN DEFAULT FALSE,
    is_corporate BOOLEAN DEFAULT FALSE,

    -- Hierarchy
    subsidiary_level STRING,
    counterparty_grandparent STRING,
    counterparty_parent STRING,

    -- Regulatory
    resident_y_n STRING,
    mas_industry_code STRING,
    country_of_incorporation STRING,
    cels_code STRING,

    -- Source System Metadata
    src_system STRING,
    sub_system STRING,
    data_cat STRING,
    data_frq STRING,
    src_id STRING,

    -- ETL Metadata (NOT part of primary key!)
    processing_date STRING,                        -- Latest ETL run date

    -- Audit Fields
    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_by STRING,
    created_at TIMESTAMP DEFAULT now(),
    updated_by STRING,
    updated_at TIMESTAMP DEFAULT now(),

    PRIMARY KEY (counterparty_short_name)          -- Single, stable primary key
)
PARTITION BY HASH (counterparty_short_name) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.num_tablet_replicas' = '3',
    'kudu.master_addresses' = 'kudu-master:7051'
);

-- Create index on m_label for fast CIF lookups
CREATE INDEX idx_counterparty_mlabel ON cis_counterparty_kudu (m_label);

-- Create index on country for filtering
CREATE INDEX idx_counterparty_country ON cis_counterparty_kudu (country);

-- ============================================================================
-- IMPORTANT NOTES:
-- ============================================================================
-- 1. PRIMARY KEY is counterparty_short_name (never changes)
-- 2. Django application references by counterparty_short_name
-- 3. ETL should do UPSERT (UPDATE if exists, INSERT if new)
-- 4. processing_date is just audit metadata, not part of PK
-- 5. m_label (CIF number) is optional - 75% of records have it
-- 6. Boolean flags converted from Y/N strings to proper BOOLEAN
-- ============================================================================

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON TABLE cis_counterparty_kudu TO ROLE analyst_role;
GRANT ALL ON TABLE cis_counterparty_kudu TO ROLE admin_role;
