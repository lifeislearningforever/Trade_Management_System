-- ============================================================================
-- Security Master Table - Kudu DDL
-- ============================================================================
-- Description: Comprehensive security master data table for CIS Trade Hive
-- Created: 2026-01-02
-- Updated: 2026-02-02 - Restructured with new fields
-- Database: gmp_cis
-- Table: cis_security
-- ============================================================================

-- Drop existing tables if they exist (for recreation)
DROP TABLE IF EXISTS gmp_cis.cis_security;
DROP TABLE IF EXISTS gmp_cis.cis_security_kudu;

-- ============================================================================
-- CREATE KUDU TABLE
-- ============================================================================

CREATE TABLE gmp_cis.cis_security_kudu (
    -- ========================================================================
    -- PRIMARY KEY
    -- ========================================================================
    security_id BIGINT NOT NULL,  -- Auto-generated unique ID (timestamp-based)

    -- ========================================================================
    -- RECORD TYPE
    -- ========================================================================
    record_type STRING,                      -- Record type classification

    -- ========================================================================
    -- CORE IDENTIFICATION FIELDS
    -- ========================================================================
    security_name STRING NOT NULL,           -- Security name/title
    isin STRING,                             -- International Securities Identification Number
    security_description STRING,             -- Detailed description
    issuer STRING,                           -- Issuing entity
    ticker STRING,                           -- Trading symbol

    -- ========================================================================
    -- CLASSIFICATION FIELDS
    -- ========================================================================
    industry STRING,                         -- Industry sector (ENERGY, BIOTECH, etc.)
    security_type STRING,                    -- ETF, COMMON STOCK, PREFERRED STOCK
    investment_type STRING,                  -- FUND, BOND, SHARE
    issuer_type STRING,                      -- TRUST, CORPORATION, GOVERNMENT
    quoted_unquoted STRING,                  -- Quoted or Unquoted

    -- ========================================================================
    -- GEOGRAPHIC FIELDS
    -- ========================================================================
    country_of_incorporation STRING,         -- Incorporation country
    country_of_exchange STRING,              -- Exchange country
    country_of_issue STRING,                 -- Issue country
    exchange_code STRING,                    -- Exchange code

    -- ========================================================================
    -- TRADING & PRICING FIELDS
    -- ========================================================================
    currency_code STRING,                    -- Trading currency (USD, SGD, AUD, etc.)
    price DECIMAL(20, 4),                    -- Current/last price

    -- ========================================================================
    -- NUMERIC/STATISTICAL FIELDS
    -- ========================================================================
    shares_outstanding BIGINT,               -- Number of shares outstanding
    beta DECIMAL(10, 4),                     -- Beta coefficient
    par_value DECIMAL(20, 6),                -- Par value

    -- ========================================================================
    -- SHAREHOLDING FIELDS (Percentages as STRING)
    -- ========================================================================
    pct_hld_entity_1 STRING,                 -- % shareholding entity 1
    pct_hld_entity_2 STRING,                 -- % shareholding entity 2
    pct_hld_entity_3 STRING,                 -- % shareholding entity 3
    pct_hld_entity_aggr STRING,              -- Aggregated shareholding %
    substantial_10_pct STRING,               -- SUBSTANTIAL >10% or NON-SUBSTANTIAL

    -- ========================================================================
    -- REGULATORY & COMPLIANCE FIELDS
    -- ========================================================================
    cels STRING,                            -- CELS field
    pevc_s32_devest STRING,                 -- PEVC S32 devest classification
    s32_representative STRING,              -- S32 representative
    basel_iv_fund STRING,                   -- Basel IV fund classification
    mas_643_entity_type STRING,             -- MAS 643 entity type code
    mas_6d_code STRING,                     -- MAS 6D code
    fin_nonfin_ind STRING,                  -- Financial/Non-financial indicator (FIN, NFIN, SPX)

    -- ========================================================================
    -- MANAGEMENT & OPERATIONAL FIELDS
    -- ========================================================================
    business_unit_head STRING,              -- Business unit head name
    person_in_charge STRING,                -- Person in charge name
    core_noncore STRING,                    -- CORE or NON-CORE
    fund_index_fund STRING,                 -- ACTIVE FUND, INDEX FUND, or blank
    management_limit_classification STRING,  -- UNLIMITED, LIMITED, or blank
    relative_index STRING,                  -- Relative index (SGX, NASDAQ, SET, etc.)

    -- ========================================================================
    -- SYSTEM FIELDS
    -- ========================================================================
    status STRING,                          -- Status of the record
    src_system STRING,                      -- Source system identifier

    -- ========================================================================
    -- AUDIT & METADATA FIELDS
    -- ========================================================================
    is_active BOOLEAN DEFAULT true,         -- Soft delete flag
    created_by STRING NOT NULL,             -- Username who created
    created_at BIGINT NOT NULL,             -- Unix timestamp in milliseconds
    updated_by STRING NOT NULL,             -- Username who last updated
    updated_at BIGINT NOT NULL,             -- Unix timestamp in milliseconds

    -- ========================================================================
    -- PRIMARY KEY CONSTRAINT
    -- ========================================================================
    PRIMARY KEY (security_id)
)
PARTITION BY HASH (security_id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES(
    'kudu.num_tablet_replicas' = '3'
);

-- ============================================================================
-- CREATE IMPALA EXTERNAL TABLE (for querying)
-- ============================================================================

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_security
STORED AS KUDU
TBLPROPERTIES(
  'kudu.table_name' = 'impala::gmp_cis.cis_security_kudu'
);

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check table structure
DESCRIBE gmp_cis.cis_security;

-- Count records
SELECT COUNT(*) as total_securities FROM gmp_cis.cis_security;

-- Sample query
SELECT
    security_name,
    isin,
    security_type,
    currency_code,
    price,
    created_by,
    created_at
FROM gmp_cis.cis_security
LIMIT 5;

-- ============================================================================
-- NOTES
-- ============================================================================
-- 1. security_id is the primary key (timestamp-based milliseconds)
-- 2. All audit fields are mandatory for tracking
-- 3. is_active allows soft delete functionality
-- 4. Decimal precision chosen based on data analysis:
--    - Price: 20,4 (handles large values with 4 decimal places)
--    - Beta: 10,4 (standard beta range with precision)
--    - PAR Value: 20,6 (high precision for par value)
-- 5. Shareholding percentages stored as STRING for flexibility
-- 6. Table is partitioned by security_id hash for performance
-- 7. Removed workflow fields (submitted_for_approval_at, submitted_by, etc.)
-- 8. Added: record_type, pevc_s32_devest, s32_representative
-- 9. Removed: country_of_primary_exchange, price_date, price_source,
--    shareholding_entity_1-3 (DECIMAL), shareholding_aggregated (DECIMAL),
--    bwciif, bwciif_others, approved_s32
-- ============================================================================
