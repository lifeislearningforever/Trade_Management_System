-- ============================================================================
-- Security Master Table - Kudu DDL (V2 with Workflow Columns)
-- ============================================================================
-- Description: Comprehensive security master data table with Four-Eyes workflow
-- Created: 2026-01-02
-- Updated: 2026-01-02 (Added workflow columns)
-- Database: gmp_cis
-- Table: cis_security
-- ============================================================================

-- Drop existing tables if they exist (for recreation)
DROP TABLE IF EXISTS gmp_cis.cis_security;
DROP TABLE IF EXISTS gmp_cis.cis_security_kudu;

-- ============================================================================
-- CREATE KUDU TABLE WITH WORKFLOW COLUMNS
-- ============================================================================

CREATE TABLE gmp_cis.cis_security_kudu (
    -- ========================================================================
    -- PRIMARY KEY
    -- ========================================================================
    security_id BIGINT NOT NULL,  -- Auto-generated unique ID (timestamp-based)

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
    country_of_primary_exchange STRING,      -- Primary exchange country
    exchange_code STRING,                    -- Exchange code

    -- ========================================================================
    -- TRADING & PRICING FIELDS
    -- ========================================================================
    currency_code STRING,                    -- Trading currency (USD, SGD, AUD, etc.)
    price DECIMAL(20, 4),                    -- Current/last price
    price_date STRING,                       -- Date of price (stored as string for flexibility)
    price_source STRING,                     -- Source of price data

    -- ========================================================================
    -- NUMERIC/STATISTICAL FIELDS
    -- ========================================================================
    shares_outstanding BIGINT,               -- Number of shares outstanding
    beta DECIMAL(10, 4),                     -- Beta coefficient
    par_value DECIMAL(20, 6),                -- Par value

    -- ========================================================================
    -- SHAREHOLDING FIELDS (Percentages)
    -- ========================================================================
    shareholding_entity_1 DECIMAL(10, 4),    -- % shareholding entity 1
    shareholding_entity_2 DECIMAL(10, 4),    -- % shareholding entity 2
    shareholding_entity_3 DECIMAL(10, 4),    -- % shareholding entity 3
    shareholding_aggregated DECIMAL(10, 4),  -- Aggregated shareholding %
    substantial_10_pct STRING,               -- SUBSTANTIAL >10% or NON-SUBSTANTIAL

    -- ========================================================================
    -- REGULATORY & COMPLIANCE FIELDS
    -- ========================================================================
    bwciif BIGINT,                          -- BWCIIF identifier
    bwciif_others BIGINT,                   -- BWCIIF others
    cels STRING,                            -- CELS field
    approved_s32 STRING,                    -- APPROVED S32 or NOT APPROVED
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
    -- WORKFLOW FIELDS (Four-Eyes Principle)
    -- ========================================================================
    status STRING DEFAULT 'DRAFT',          -- DRAFT, PENDING_APPROVAL, APPROVED, ACTIVE, REJECTED, INACTIVE
    submitted_for_approval_at BIGINT,       -- Timestamp when submitted for approval
    submitted_by STRING,                    -- Username who submitted
    reviewed_at BIGINT,                     -- Timestamp when reviewed
    reviewed_by STRING,                     -- Username who reviewed
    review_comments STRING,                 -- Checker's comments

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

-- Sample query with workflow fields
SELECT
    security_id,
    security_name,
    isin,
    security_type,
    currency_code,
    price,
    status,
    created_by,
    created_at
FROM gmp_cis.cis_security
LIMIT 5;

-- Check workflow states
SELECT status, COUNT(*) as count
FROM gmp_cis.cis_security
GROUP BY status;

-- ============================================================================
-- NOTES
-- ============================================================================
-- 1. security_id is the primary key (timestamp-based milliseconds)
-- 2. All audit fields are mandatory for tracking
-- 3. is_active allows soft delete functionality
-- 4. Workflow states:
--    - DRAFT: Initial state when created
--    - PENDING_APPROVAL: Submitted for checker approval
--    - APPROVED: Checker approved (becomes ACTIVE)
--    - ACTIVE: Live security record
--    - REJECTED: Checker rejected
--    - INACTIVE: Soft deleted
-- 5. Four-Eyes Principle: submitted_by != reviewed_by
-- 6. Decimal precision chosen based on data analysis:
--    - Price: 20,4 (handles large values with 4 decimal places)
--    - Beta: 10,4 (standard beta range with precision)
--    - Shareholding: 10,4 (percentage with 4 decimal places)
--    - PAR Value: 20,6 (high precision for par value)
-- 7. String fields used for dates to preserve original format
-- 8. Table is partitioned by security_id hash for performance
-- 9. Total columns: 53 (41 business + 1 ID + 6 workflow + 5 audit)
-- ============================================================================
