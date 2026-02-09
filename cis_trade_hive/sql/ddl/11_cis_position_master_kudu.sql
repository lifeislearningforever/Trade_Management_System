-- ============================================================================
-- Position Master Table - Consolidated Positions from Multiple Sources
-- ============================================================================
-- Description: Master position table that consolidates position data from
--              12 different source systems (4 primary sources with 3 sub-tables each):
--              - CIS (internal trades)
--              - GMP (Global Markets Platform)
--              - AMS (Asset Management System)
--              - IMS (Investment Management System)
--
-- Key Features:
--   - Unified view of all positions across systems
--   - Multi-currency support (Local/Base)
--   - Security validation against cis_security master
--   - Source system tracking for audit/reconciliation
--
-- Database: gmp_cis
-- Created: 2026-02-09
-- Version: 1.0
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- TABLE 1: cis_position_master_kudu (Master Position Table)
-- ============================================================================
-- Consolidated position data from all 12 source tables.
-- PK: position_master_id (system-generated)
-- Natural Key: (portfolio_short_name, security_label, valuation_date, src_system)
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_position_master_kudu;

CREATE TABLE gmp_cis.cis_position_master_kudu (
    -- Primary Key (System Generated)
    position_master_id BIGINT NOT NULL,

    -- ========================================
    -- POSITION IDENTITY
    -- ========================================
    -- Natural key for deduplication across sources
    portfolio_short_name STRING NOT NULL,        -- Portfolio identifier
    security_label STRING NOT NULL,              -- Security identifier (matched to cis_security)
    valuation_date STRING NOT NULL,              -- Position as-of date (YYYY-MM-DD)
    src_system STRING NOT NULL,                  -- Source system: CIS, GMP, AMS, IMS

    -- ========================================
    -- SECURITY REFERENCE
    -- ========================================
    isin STRING,                                 -- ISIN code
    security_id BIGINT,                          -- FK to cis_security.security_id (if matched)
    security_name STRING,                        -- Security display name
    security_type STRING,                        -- Equity, Bond, Fund, etc.
    ticker STRING,                               -- Exchange ticker symbol

    -- ========================================
    -- PORTFOLIO REFERENCE
    -- ========================================
    portfolio_full_name STRING,                  -- Full portfolio name
    portfolio_id BIGINT,                         -- FK to cis_portfolio (if matched)
    fund_type STRING,                            -- Fund classification

    -- ========================================
    -- CURRENCY TRACKING
    -- ========================================
    security_currency STRING,                    -- Currency of the security
    portfolio_currency STRING,                   -- Base currency of the portfolio

    -- ========================================
    -- HOLDINGS
    -- ========================================
    quantity DECIMAL(20,6),                      -- Number of units held
    face_value DECIMAL(20,6),                    -- Nominal value per unit
    lots_held INT,                               -- Number of lots

    -- ========================================
    -- COST VALUES
    -- ========================================
    average_cost DECIMAL(20,6),                  -- Weighted average cost per unit
    total_cost DECIMAL(20,6),                    -- Legacy: total cost basis
    cost_value_local DECIMAL(20,6),              -- Cost in security currency
    cost_value_base DECIMAL(20,6),               -- Cost in portfolio currency

    -- ========================================
    -- MARKET VALUES
    -- ========================================
    market_unit_price DECIMAL(20,6),             -- Current market price per unit
    current_price DECIMAL(20,6),                 -- Alias for market_unit_price
    market_value DECIMAL(20,6),                  -- Legacy: qty * current_price
    market_value_local DECIMAL(20,6),            -- Market value in security currency
    market_value_base DECIMAL(20,6),             -- Market value in portfolio currency

    -- ========================================
    -- PROFIT & LOSS
    -- ========================================
    unrealized_pnl DECIMAL(20,6),                -- Legacy: market_value - total_cost
    unrealized_pnl_local DECIMAL(20,6),          -- Unrealized P&L in security currency
    unrealized_pnl_base DECIMAL(20,6),           -- Unrealized P&L in portfolio currency
    realized_pnl DECIMAL(20,6),                  -- Cumulative realized P&L

    -- ========================================
    -- ALLOCATION / RATIO
    -- ========================================
    pct_ratio DECIMAL(10,6),                     -- Percentage of portfolio

    -- ========================================
    -- CLASSIFICATION
    -- ========================================
    country STRING,                              -- Country of security
    asset_class STRING,                          -- Asset class classification
    listing_status STRING,                       -- Listed/Unlisted
    industry STRING,                             -- Industry classification
    sector STRING,                               -- Sector classification

    -- ========================================
    -- CUSTODIAN INFO
    -- ========================================
    custodian STRING,                            -- Primary custodian
    sub_custodian STRING,                        -- Sub-custodian

    -- ========================================
    -- STATUS & FLAGS
    -- ========================================
    status STRING,                               -- OPEN, CLOSED, PENDING
    is_active BOOLEAN,                           -- Active flag
    is_matched BOOLEAN,                          -- True if security matched to cis_security
    match_status STRING,                         -- EXACT, FUZZY, NEW, UNMATCHED

    -- ========================================
    -- SOURCE TRACKING
    -- ========================================
    src_table STRING,                            -- Original source table name
    src_position_id STRING,                      -- Original position ID from source
    src_batch_id STRING,                         -- ETL batch identifier

    -- ========================================
    -- TIMESTAMPS
    -- ========================================
    created_at STRING,                           -- Record creation timestamp
    updated_at STRING,                           -- Last update timestamp
    etl_load_timestamp BIGINT,                   -- ETL load timestamp (epoch ms)

    PRIMARY KEY (position_master_id)
)
PARTITION BY HASH (position_master_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES(
    'kudu.num_tablet_replicas' = '3',
    'kudu.table_name' = 'impala::gmp_cis.cis_position_master_kudu'
);

-- Impala external table for querying
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_position_master
STORED AS KUDU
TBLPROPERTIES(
    'kudu.table_name' = 'impala::gmp_cis.cis_position_master_kudu'
);

-- ============================================================================
-- TABLE 2: cis_position_master_history (Audit Trail)
-- ============================================================================
-- Tracks changes to master positions for audit purposes
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_position_master_history_kudu;

CREATE TABLE gmp_cis.cis_position_master_history_kudu (
    history_id BIGINT NOT NULL,
    position_master_id BIGINT NOT NULL,

    -- Action
    action STRING NOT NULL,                      -- CREATE, UPDATE, DELETE, MERGE

    -- Snapshot of key fields
    portfolio_short_name STRING,
    security_label STRING,
    valuation_date STRING,
    src_system STRING,
    quantity DECIMAL(20,6),
    market_value_base DECIMAL(20,6),

    -- Changes (JSON)
    changes STRING,                              -- JSON diff of changed fields

    -- Metadata
    performed_by STRING,
    performed_at STRING,
    etl_batch_id STRING,

    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES(
    'kudu.num_tablet_replicas' = '3',
    'kudu.table_name' = 'impala::gmp_cis.cis_position_master_history_kudu'
);

-- Impala external table
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_position_master_history
STORED AS KUDU
TBLPROPERTIES(
    'kudu.table_name' = 'impala::gmp_cis.cis_position_master_history_kudu'
);

-- ============================================================================
-- TABLE 3: cis_position_unmatched (Securities Not Found in Master)
-- ============================================================================
-- Holds positions where security_label + isin could not be matched to cis_security.
-- These need manual review or auto-creation in cis_security.
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_position_unmatched_kudu;

CREATE TABLE gmp_cis.cis_position_unmatched_kudu (
    unmatched_id BIGINT NOT NULL,

    -- Source Position Info
    portfolio_short_name STRING NOT NULL,
    security_label STRING NOT NULL,
    isin STRING,
    valuation_date STRING,
    src_system STRING,
    src_table STRING,

    -- Attempted Match Info
    attempted_match_key STRING,                  -- What we tried to match on
    match_attempt_count INT,                     -- Number of match attempts
    last_match_attempt STRING,                   -- Timestamp of last attempt

    -- Security Details (for potential auto-creation)
    security_name STRING,
    security_type STRING,
    currency_code STRING,
    country STRING,
    exchange_code STRING,

    -- Position Data (preserved for later merge)
    quantity DECIMAL(20,6),
    market_value DECIMAL(20,6),
    cost_value DECIMAL(20,6),

    -- Status
    resolution_status STRING,                    -- PENDING, AUTO_CREATED, MANUALLY_RESOLVED, SKIPPED
    resolution_notes STRING,
    resolved_by STRING,
    resolved_at STRING,

    -- ETL Metadata
    created_at STRING,
    etl_batch_id STRING,

    PRIMARY KEY (unmatched_id)
)
PARTITION BY HASH (unmatched_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES(
    'kudu.num_tablet_replicas' = '3',
    'kudu.table_name' = 'impala::gmp_cis.cis_position_unmatched_kudu'
);

-- Impala external table
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_position_unmatched
STORED AS KUDU
TBLPROPERTIES(
    'kudu.table_name' = 'impala::gmp_cis.cis_position_unmatched_kudu'
);

-- ============================================================================
-- SEQUENCE INITIALIZATION
-- ============================================================================

-- Add sequences for new tables
UPSERT INTO gmp_cis.cis_sequence VALUES ('position_master_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('position_master_history_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('position_unmatched_id', 1000000, 1);

-- ============================================================================
-- VERIFICATION
-- ============================================================================

DESCRIBE gmp_cis.cis_position_master;
DESCRIBE gmp_cis.cis_position_master_history;
DESCRIBE gmp_cis.cis_position_unmatched;

SELECT * FROM gmp_cis.cis_sequence WHERE sequence_name LIKE 'position_%';

-- ============================================================================
-- END OF DDL
-- ============================================================================
