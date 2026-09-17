-- ============================================================================
-- ETL Staging Tables - GMP to CIS Merge
-- ============================================================================
-- Description: Staging tables for GMP ETL data that does NOT contain
--              CIS-generated surrogate keys (e.g., security_id).
--              Data lands here first, then gets merged into target tables.
--
-- Problem:
--   - cis_security_kudu has PK = security_id (BIGINT, CIS-generated)
--   - cis_equity_price_kudu has PK = (currency_code, security_label, price_date)
--   - GMP ETL does NOT send security_id
--   - Equity price PK is natural (no gap), security PK is synthetic (gap)
--
-- Solution:
--   - Land GMP data into staging tables (no surrogate keys required)
--   - Merge into target tables using natural key matching (ISIN for security)
--   - Generate security_id for new records, reuse for existing
--
-- Created: 2026-02-02
-- Database: gmp_cis
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- TABLE 1: STAGING - GMP SECURITY DATA
-- ============================================================================
-- PK: isin (natural key from GMP - no security_id needed)
-- GMP sends all business fields but NOT security_id
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.stg_gmp_security_kudu;

CREATE TABLE gmp_cis.stg_gmp_security_kudu (
    -- Natural Key (what GMP provides)
    isin STRING NOT NULL,                           -- ISIN is the natural match key

    -- Record Type
    record_type STRING,

    -- Core Identification
    security_name STRING,
    security_description STRING,
    issuer STRING,
    ticker STRING,

    -- Classification
    industry STRING,
    security_type STRING,
    investment_type STRING,
    issuer_type STRING,
    quoted_unquoted STRING,

    -- Geographic
    country_of_incorporation STRING,
    country_of_exchange STRING,
    country_of_issue STRING,
    exchange_code STRING,

    -- Trading & Pricing
    currency_code STRING,
    price DECIMAL(20, 4),

    -- Numeric/Statistical
    shares_outstanding BIGINT,
    beta DECIMAL(10, 4),
    par_value DECIMAL(20, 6),

    -- Shareholding (as STRING)
    pct_hld_entity_1 STRING,
    pct_hld_entity_2 STRING,
    pct_hld_entity_3 STRING,
    pct_hld_entity_aggr STRING,
    substantial_10_pct STRING,

    -- Regulatory & Compliance
    cels STRING,
    pevc_s32_devest STRING,
    s32_representative STRING,
    basel_iv_fund STRING,
    mas_643_entity_type STRING,
    mas_6d_code STRING,
    fin_nonfin_ind STRING,

    -- Management & Operational
    business_unit_head STRING,
    person_in_charge STRING,
    core_noncore STRING,
    fund_index_fund STRING,
    management_limit_classification STRING,
    relative_index STRING,

    -- ETL Metadata
    etl_batch_id STRING,                            -- Batch identifier for traceability
    etl_load_timestamp BIGINT,                      -- When this row was loaded into staging

    PRIMARY KEY (isin)
)
PARTITION BY HASH (isin) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES(
    'kudu.num_tablet_replicas' = '3',
    'kudu.table_name' = 'impala::gmp_cis.stg_gmp_security_kudu'
);

-- Impala external table for querying
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_gmp_security
STORED AS KUDU
TBLPROPERTIES(
    'kudu.table_name' = 'impala::gmp_cis.stg_gmp_security_kudu'
);


-- ============================================================================
-- TABLE 2: STAGING - GMP EQUITY PRICE DATA
-- ============================================================================
-- PK: (currency_code, security_label, price_date) - same as target table
-- No ID gap - GMP provides all PK fields naturally
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.stg_gmp_equity_price_kudu;

CREATE TABLE gmp_cis.stg_gmp_equity_price_kudu (
    -- Composite Primary Key (same natural keys as target)
    currency_code STRING NOT NULL,
    security_label STRING NOT NULL,
    price_date STRING NOT NULL,

    -- Business Fields
    isin STRING,
    main_closing_price DECIMAL(18, 6),
    price_timestamp BIGINT,

    -- ETL Metadata
    etl_batch_id STRING,
    etl_load_timestamp BIGINT,

    PRIMARY KEY (currency_code, security_label, price_date)
)
PARTITION BY HASH (currency_code, security_label) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES(
    'kudu.num_tablet_replicas' = '3',
    'kudu.table_name' = 'impala::gmp_cis.stg_gmp_equity_price_kudu'
);

-- Impala external table for querying
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_gmp_equity_price
STORED AS KUDU
TBLPROPERTIES(
    'kudu.table_name' = 'impala::gmp_cis.stg_gmp_equity_price_kudu'
);


-- ============================================================================
-- VERIFICATION
-- ============================================================================

DESCRIBE gmp_cis.stg_gmp_security;
DESCRIBE gmp_cis.stg_gmp_equity_price;

-- ============================================================================
-- DATA FLOW SUMMARY
-- ============================================================================
--
--  GMP ETL System
--       |
--       v
--  +---------------------------+     +-------------------------------+
--  | stg_gmp_security          |     | stg_gmp_equity_price          |
--  | PK: isin                  |     | PK: (currency, security, date)|
--  | (no security_id)          |     | (natural PK = no ID gap)      |
--  +---------------------------+     +-------------------------------+
--       |                                  |
--       | LEFT JOIN on isin                | Direct UPSERT
--       | Generate security_id             | (PK matches target)
--       | for new records                  |
--       v                                  v
--  +---------------------------+     +-------------------------------+
--  | cis_security_kudu         |     | cis_equity_price_kudu         |
--  | PK: security_id (BIGINT)  |     | PK: (currency, security, date)|
--  | src_system = 'GMP'        |     | src_system = 'GMP'            |
--  +---------------------------+     +-------------------------------+
--
-- ============================================================================
