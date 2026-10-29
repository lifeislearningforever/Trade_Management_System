-- ============================================================================
-- DDL 63: Widen DECIMAL columns in cis_position from (18,4)/(18,6) to (30,8)
-- ============================================================================
-- Problem:
--   DECIMAL(18,4) allows only 14 integer digits.
--   For HKD positions: cost_lc = large_fc_cost * 7.85 can exceed 14 digits.
--   Example: cost_fc = 190,215,329,000  →  cost_lc = 1,493,190,332,650 (13 digits)
--   DECIMAL(18,6) allows only 12 integer digits — even tighter overflow risk.
--   These caused "Decimal expression overflow" when syncing from cis_trade_position.
--
-- Fix:
--   Kudu does not support ALTER COLUMN for type changes.
--   Recreate cis_position with DECIMAL(30,8) monetary columns.
--   WARNING: This drops all existing position data — run only on empty table
--   or after backing up data to a temp table.
--
-- Backup approach (run before this script if data exists):
--   CREATE TABLE cis_position_bak AS SELECT * FROM gmp_cis.cis_position;
-- ============================================================================

USE gmp_cis;

-- Step 1: Backup existing data (comment out if table is empty)
-- DROP TABLE IF EXISTS cis_position_bak;
-- CREATE TABLE cis_position_bak
-- PRIMARY KEY (position_id)
-- PARTITION BY HASH(position_id) PARTITIONS 4
-- STORED AS KUDU
-- AS SELECT * FROM gmp_cis.cis_position;

-- Step 2: Drop and recreate with wider DECIMAL
DROP TABLE IF EXISTS cis_position;

CREATE TABLE cis_position (
    position_id         BIGINT NOT NULL,
    version_id          BIGINT,

    -- Position Identity
    portfolio           STRING,
    security_label      STRING,
    position_basis      STRING,
    position_date       STRING,
    src_system          STRING,
    processing_date     STRING,

    -- Holdings — DECIMAL(30,8): 22 integer digits; safe for all large LC values
    quantity            DECIMAL(30,8),

    -- Cost in Foreign Currency (Security Currency)
    average_cost_fc     DECIMAL(30,8),
    cost_fc             DECIMAL(30,8),

    -- Market Value in Foreign Currency
    market_value_fc     DECIMAL(30,8),
    net_book_value_fc   DECIMAL(30,8),
    unrealized_pnl_fc   DECIMAL(30,8),

    -- Cost in Local Currency (Portfolio Currency)
    average_cost_lc     DECIMAL(30,8),
    cost_lc             DECIMAL(30,8),

    -- Market Value in Local Currency
    market_value_lc     DECIMAL(30,8),
    net_book_value_lc   DECIMAL(30,8),
    unrealized_pnl_lc   DECIMAL(30,8),

    -- Provision
    provision_fc        DECIMAL(30,8),
    provision_lc        DECIMAL(30,8),

    -- Dividend (from Corporate Actions)
    dividend_fc         DECIMAL(30,8),
    dividend_lc         DECIMAL(30,8),

    -- Realized P&L
    realized_pnl_fc     DECIMAL(30,8),
    realized_pnl_lc     DECIMAL(30,8),

    -- Reference
    isin                STRING,
    source_table        STRING,
    processing_timestamp STRING,

    -- Uncalled Capital (PE/VC)
    uncall_fc           DECIMAL(30,8),
    uncall_lc           DECIMAL(30,8),

    -- Pipeline (pending trades/commitments)
    pipeline_fc         DECIMAL(30,8),
    pipeline_lc         DECIMAL(30,8),

    -- Position Classification
    position_type       STRING,

    PRIMARY KEY (position_id)
)
PARTITION BY HASH (position_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Step 3: Restore from backup (comment out if table was empty)
-- INSERT INTO cis_position SELECT * FROM cis_position_bak;
