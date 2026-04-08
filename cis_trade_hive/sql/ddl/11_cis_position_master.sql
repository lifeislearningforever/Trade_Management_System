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
-- Storage: Hive External Tables with Parquet format
-- Database: gmp_cis
-- Created: 2026-02-09
-- Updated: 2026-02-10 (Converted from Kudu to Hive/Parquet)
-- Version: 2.0
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- HDFS DIRECTORY SETUP (run via hdfs dfs commands before creating tables)
-- ============================================================================
-- hdfs dfs -mkdir -p /data/gmp_cis/cis_position_master
-- hdfs dfs -mkdir -p /data/gmp_cis/cis_position_master_history
-- hdfs dfs -mkdir -p /data/gmp_cis/cis_position_unmatched
-- hdfs dfs -chmod 777 /data/gmp_cis/cis_position_master
-- hdfs dfs -chmod 777 /data/gmp_cis/cis_position_master_history
-- hdfs dfs -chmod 777 /data/gmp_cis/cis_position_unmatched
-- ============================================================================


-- ============================================================================
-- TABLE 1: cis_position_master (Master Position Table)
-- ============================================================================
-- Consolidated position data from all 12 source tables.
-- PK: position_master_id (system-generated)
-- Natural Key: (portfolio_short_name, security_label, valuation_date, src_system)
-- Storage: External Hive table with Parquet format
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_position_master;

CREATE EXTERNAL TABLE gmp_cis.cis_position_master (
    -- Primary Key (System Generated)
    position_master_id BIGINT,

    -- ========================================
    -- POSITION IDENTITY
    -- ========================================
    -- Natural key for deduplication across sources
    portfolio_short_name STRING,              -- Portfolio identifier
    security_label STRING,                    -- Security identifier (matched to cis_security)
    valuation_date STRING,                    -- Position as-of date (YYYY-MM-DD)
    src_system STRING,                        -- Source system: CIS, GMP, AMS, IMS

    -- ========================================
    -- SECURITY REFERENCE
    -- ========================================
    isin STRING,                              -- ISIN code
    security_id BIGINT,                       -- FK to cis_security.security_id (if matched)
    security_name STRING,                     -- Security display name
    security_type STRING,                     -- Equity, Bond, Fund, etc.
    ticker STRING,                            -- Exchange ticker symbol

    -- ========================================
    -- PORTFOLIO REFERENCE
    -- ========================================
    portfolio_full_name STRING,               -- Full portfolio name
    portfolio_id BIGINT,                      -- FK to cis_portfolio (if matched)
    fund_type STRING,                         -- Fund classification

    -- ========================================
    -- CURRENCY TRACKING
    -- ========================================
    security_currency STRING,                 -- Currency of the security
    portfolio_currency STRING,                -- Base currency of the portfolio

    -- ========================================
    -- HOLDINGS
    -- ========================================
    quantity DECIMAL(20,6),                   -- Number of units held
    face_value DECIMAL(20,6),                 -- Nominal value per unit
    lots_held INT,                            -- Number of lots

    -- ========================================
    -- COST VALUES
    -- ========================================
    average_cost DECIMAL(20,6),               -- Weighted average cost per unit
    total_cost DECIMAL(20,6),                 -- Legacy: total cost basis
    cost_value_local DECIMAL(20,6),           -- Cost in security currency
    cost_value_base DECIMAL(20,6),            -- Cost in portfolio currency

    -- ========================================
    -- MARKET VALUES
    -- ========================================
    market_unit_price DECIMAL(20,6),          -- Current market price per unit
    current_price DECIMAL(20,6),              -- Alias for market_unit_price
    market_value DECIMAL(20,6),               -- Legacy: qty * current_price
    market_value_local DECIMAL(20,6),         -- Market value in security currency
    market_value_base DECIMAL(20,6),          -- Market value in portfolio currency

    -- ========================================
    -- PROFIT & LOSS
    -- ========================================
    unrealized_pnl DECIMAL(20,6),             -- Legacy: market_value - total_cost
    unrealized_pnl_local DECIMAL(20,6),       -- Unrealized P&L in security currency
    unrealized_pnl_base DECIMAL(20,6),        -- Unrealized P&L in portfolio currency
    realized_pnl DECIMAL(20,6),               -- Cumulative realized P&L

    -- ========================================
    -- ALLOCATION / RATIO
    -- ========================================
    pct_ratio DECIMAL(10,6),                  -- Percentage of portfolio

    -- ========================================
    -- CLASSIFICATION
    -- ========================================
    country STRING,                           -- Country of security
    asset_class STRING,                       -- Asset class classification
    listing_status STRING,                    -- Listed/Unlisted
    industry STRING,                          -- Industry classification
    sector STRING,                            -- Sector classification

    -- ========================================
    -- CUSTODIAN INFO
    -- ========================================
    custodian STRING,                         -- Primary custodian
    sub_custodian STRING,                     -- Sub-custodian

    -- ========================================
    -- STATUS & FLAGS
    -- ========================================
    status STRING,                            -- OPEN, CLOSED, PENDING
    is_active BOOLEAN,                        -- Active flag
    is_matched BOOLEAN,                       -- True if security matched to cis_security
    match_status STRING,                      -- EXACT, FUZZY, NEW, UNMATCHED

    -- ========================================
    -- UNCALLED CAPITAL (PE/VC)
    -- ========================================
    uncall_fc DECIMAL(20,6),                  -- Uncalled amount in Foreign Currency
    uncall_lc DECIMAL(20,6),                  -- Uncalled amount in Local Currency

    -- ========================================
    -- PIPELINE (Pending trades/commitments)
    -- ========================================
    pipeline_fc DECIMAL(20,6),                -- Pipeline amount in Foreign Currency
    pipeline_lc DECIMAL(20,6),                -- Pipeline amount in Local Currency

    -- ========================================
    -- POSITION CLASSIFICATION
    -- ========================================
    position_type STRING,                     -- LONG, SHORT, COMMITTED, PIPELINE, HEDGE, SYNTHETIC

    -- ========================================
    -- SOURCE TRACKING
    -- ========================================
    src_table STRING,                         -- Original source table name
    src_position_id STRING,                   -- Original position ID from source
    src_batch_id STRING,                      -- ETL batch identifier

    -- ========================================
    -- TIMESTAMPS
    -- ========================================
    created_at STRING,                        -- Record creation timestamp
    updated_at STRING,                        -- Last update timestamp
    etl_load_timestamp BIGINT                 -- ETL load timestamp (epoch ms)
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/cis_position_master'
TBLPROPERTIES (
    'parquet.compression' = 'SNAPPY'
);


-- ============================================================================
-- TABLE 2: cis_position_master_history (Audit Trail)
-- ============================================================================
-- Tracks changes to master positions for audit purposes
-- Storage: External Hive table with Parquet format
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_position_master_history;

CREATE EXTERNAL TABLE gmp_cis.cis_position_master_history (
    history_id BIGINT,
    position_master_id BIGINT,

    -- Action
    action STRING,                            -- CREATE, UPDATE, DELETE, MERGE

    -- Snapshot of key fields
    portfolio_short_name STRING,
    security_label STRING,
    valuation_date STRING,
    src_system STRING,
    quantity DECIMAL(20,6),
    market_value_base DECIMAL(20,6),

    -- Changes (JSON)
    changes STRING,                           -- JSON diff of changed fields

    -- Metadata
    performed_by STRING,
    performed_at STRING,
    etl_batch_id STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/cis_position_master_history'
TBLPROPERTIES (
    'parquet.compression' = 'SNAPPY'
);


-- ============================================================================
-- TABLE 3: cis_position_unmatched (Securities Not Found in Master)
-- ============================================================================
-- Holds positions where security_label + isin could not be matched to cis_security.
-- These need manual review or auto-creation in cis_security.
-- Storage: External Hive table with Parquet format
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_position_unmatched;

CREATE EXTERNAL TABLE gmp_cis.cis_position_unmatched (
    unmatched_id BIGINT,

    -- Source Position Info
    portfolio_short_name STRING,
    security_label STRING,
    isin STRING,
    valuation_date STRING,
    src_system STRING,
    src_table STRING,

    -- Attempted Match Info
    attempted_match_key STRING,               -- What we tried to match on
    match_attempt_count INT,                  -- Number of match attempts
    last_match_attempt STRING,                -- Timestamp of last attempt

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
    resolution_status STRING,                 -- PENDING, AUTO_CREATED, MANUALLY_RESOLVED, SKIPPED
    resolution_notes STRING,
    resolved_by STRING,
    resolved_at STRING,

    -- ETL Metadata
    created_at STRING,
    etl_batch_id STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/cis_position_unmatched'
TBLPROPERTIES (
    'parquet.compression' = 'SNAPPY'
);


-- ============================================================================
-- SEQUENCE INITIALIZATION (for Kudu-based sequence table)
-- ============================================================================

-- Add sequences for new tables (sequences still use Kudu for atomic increments)
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
-- NOTES ON HIVE/PARQUET STORAGE
-- ============================================================================
-- 1. Unlike Kudu, Parquet tables do not support UPSERT operations.
--    Use INSERT OVERWRITE or MERGE statements for updates.
--
-- 2. For incremental loads, consider using:
--    - Partitioned tables (e.g., PARTITIONED BY (valuation_date))
--    - Delta Lake or Apache Iceberg for ACID transactions
--
-- 3. The ETL job (merge_position_master.py) handles:
--    - Reading existing data
--    - Merging with new staging data
--    - Writing back as a complete dataset
--
-- 4. Parquet advantages:
--    - Columnar storage for efficient analytics
--    - Compression (SNAPPY) reduces storage
--    - Schema evolution support
--    - Wide ecosystem compatibility (Spark, Hive, Impala, etc.)
-- ============================================================================


-- ============================================================================
-- END OF DDL
-- ============================================================================
