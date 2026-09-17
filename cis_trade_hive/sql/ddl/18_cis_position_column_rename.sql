-- ============================================================================
-- CIS Position Table - Column Rename for FC/LC Clarity
-- ============================================================================
-- Description: Renames columns in cis_position (gold/master position table)
--              to follow the FC/LC naming convention:
--              - FC = Foreign Currency = Security Currency
--              - LC = Local Currency = Portfolio Currency
--
-- Changes:
--   average_cost   → average_cost_fc  (average cost in security currency)
--   placeholder_2  → average_cost_lc  (average cost in portfolio currency)
--
-- Database: gmp_cis
-- Table: cis_position
-- Created: 2026-03-31
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- OPTION 1: ALTER TABLE (if supported by your Kudu/Impala version)
-- ============================================================================
-- Note: Kudu supports ALTER TABLE ... CHANGE COLUMN for renaming
-- Run these statements one at a time

-- Rename average_cost to average_cost_fc
ALTER TABLE cis_position CHANGE COLUMN average_cost average_cost_fc DECIMAL(30,8);

-- Rename placeholder_2 to average_cost_lc
ALTER TABLE cis_position CHANGE COLUMN placeholder_2 average_cost_lc DECIMAL(30,8);

-- ============================================================================
-- VERIFICATION
-- ============================================================================
DESCRIBE cis_position;

-- Verify data is intact
SELECT
    position_id,
    portfolio,
    security_label,
    quantity,
    average_cost_fc,
    average_cost_lc,
    cost_fc,
    cost_lc
FROM cis_position
LIMIT 5;


-- ============================================================================
-- OPTION 2: RECREATE TABLE (if ALTER not supported or safer approach)
-- ============================================================================
-- If ALTER TABLE CHANGE COLUMN is not supported, use this approach:
-- 1. Create new table with correct column names
-- 2. Copy data from old table
-- 3. Drop old table
-- 4. Rename new table
--
-- WARNING: This will require downtime. Schedule during maintenance window.
-- ============================================================================

/*
-- Step 1: Create new table with correct column names
DROP TABLE IF EXISTS cis_position_new;

CREATE TABLE cis_position_new (
    position_id BIGINT,
    version_id BIGINT,
    portfolio STRING,
    security_label STRING,
    position_basis STRING,
    position_date STRING,
    src_system STRING,
    processing_date STRING,

    -- Holdings
    quantity DECIMAL(30,8),

    -- Cost - FC (Foreign/Security Currency)
    average_cost_fc DECIMAL(30,8),       -- Renamed from average_cost
    cost_fc DECIMAL(30,8),

    -- Market Value - FC
    market_value_fc DECIMAL(30,8),
    net_book_value_fc DECIMAL(30,8),
    unrealized_pnl_fc DECIMAL(30,8),

    -- Cost - LC (Local/Portfolio Currency)
    average_cost_lc DECIMAL(30,8),       -- Renamed from placeholder_2
    cost_lc DECIMAL(30,8),

    -- Market Value - LC
    market_value_lc DECIMAL(30,8),
    net_book_value_lc DECIMAL(30,8),
    unrealized_pnl_lc DECIMAL(30,8),

    -- Provision
    provision_fc DECIMAL(30,8),
    provision_lc DECIMAL(30,8),

    -- Dividend
    dividend_fc DECIMAL(30,8),
    dividend_lc DECIMAL(30,8),

    -- Realized P&L
    realized_pnl_fc DECIMAL(30,8),
    realized_pnl_lc DECIMAL(30,8),

    -- Reference
    isin STRING,

    source_table STRING,
    processing_timestamp STRING,

    PRIMARY KEY (position_id)
)
PARTITION BY HASH(position_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Step 2: Copy data from old table to new table
INSERT INTO cis_position_new
SELECT
    position_id,
    version_id,
    portfolio,
    security_label,
    position_basis,
    position_date,
    src_system,
    processing_date,
    quantity,
    average_cost,          -- Will become average_cost_fc
    cost_fc,
    market_value_fc,
    net_book_value_fc,
    unrealized_pnl_fc,
    placeholder_2,         -- Will become average_cost_lc
    cost_lc,
    market_value_lc,
    net_book_value_lc,
    unrealized_pnl_lc,
    provision_fc,
    provision_lc,
    dividend_fc,
    dividend_lc,
    realized_pnl_fc,
    realized_pnl_lc,
    isin,
    placeholder_3,  -- maps to source_table in new schema
    placeholder_4   -- maps to processing_timestamp in new schema
FROM cis_position;

-- Step 3: Verify data copied correctly
SELECT COUNT(*) FROM cis_position;
SELECT COUNT(*) FROM cis_position_new;

-- Step 4: Drop old table and rename new table
-- WARNING: Only run after verifying data!
DROP TABLE cis_position;
ALTER TABLE cis_position_new RENAME TO cis_position;

-- Step 5: Verify final table
DESCRIBE cis_position;
SELECT * FROM cis_position LIMIT 5;
*/


-- ============================================================================
-- COLUMN MAPPING REFERENCE
-- ============================================================================
-- Old Name          | New Name           | Description
-- ------------------|--------------------|---------------------------------
-- average_cost      | average_cost_fc    | Avg cost in Security Currency
-- placeholder_2     | average_cost_lc    | Avg cost in Portfolio Currency
-- placeholder_3     | source_table       | Source table name for the position row
-- cost_fc           | cost_fc            | Total cost in Security Currency (unchanged)
-- cost_lc           | cost_lc            | Total cost in Portfolio Currency (unchanged)
-- market_value_fc   | market_value_fc    | Market value in Security Currency (unchanged)
-- market_value_lc   | market_value_lc    | Market value in Portfolio Currency (unchanged)
-- ============================================================================


-- ============================================================================
-- ALTER TABLE: rename placeholder_3 → source_table in live cis_position table
-- Run this once against the live Kudu table via Impala shell.
-- ============================================================================
-- ALTER TABLE gmp_cis.cis_position CHANGE COLUMN placeholder_3 source_table STRING;


-- ============================================================================
-- END OF DDL
-- ============================================================================
