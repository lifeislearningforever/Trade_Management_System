-- ============================================================================
-- DDL 62: Widen DECIMAL columns in cis_trade_position from (20,8) to (28,8)
-- ============================================================================
-- Problem:
--   DECIMAL(20,8) allows only 12 integer digits.
--   For HKD positions: total_cost_lc = large_fc_cost * 7.85 can exceed 13 digits.
--   Example: cost_fc = 190,215,329,000  →  cost_lc = 1,493,190,332,650 (13 digits)
--   This caused "Decimal expression overflow" for 24 trades in the migration backfill.
--
-- Fix:
--   Kudu does not support ALTER COLUMN for type changes.
--   Recreate cis_trade_position with DECIMAL(28,8) monetary columns.
--   WARNING: This drops all existing position data — run only on empty table
--   or after backing up data to a temp table.
--
-- Backup approach (run before this script if data exists):
--   CREATE TABLE cis_trade_position_bak AS SELECT * FROM gmp_cis.cis_trade_position;
-- ============================================================================

USE gmp_cis;

-- Step 1: Backup existing data (comment out if table is empty)
-- DROP TABLE IF EXISTS cis_trade_position_bak;
-- CREATE TABLE cis_trade_position_bak
-- PRIMARY KEY (version_id)
-- PARTITION BY HASH(version_id) PARTITIONS 4
-- STORED AS KUDU
-- AS SELECT * FROM gmp_cis.cis_trade_position;

-- Step 2: Drop and recreate with wider DECIMAL
DROP TABLE IF EXISTS cis_trade_position;

CREATE TABLE cis_trade_position (
    version_id                  BIGINT NOT NULL,
    position_id                 BIGINT NOT NULL,
    position_basis              STRING NOT NULL DEFAULT 'TRADE_DATE',
    position_date               STRING NOT NULL,
    trade_date                  STRING,
    settle_date                 STRING,
    portfolio_short_name        STRING NOT NULL,
    security_label              STRING NOT NULL,
    -- DECIMAL(28,8): 20 integer digits — handles large LC values (FC * FX rate)
    quantity                    DECIMAL(28,8),
    average_cost_fc             DECIMAL(28,8),
    total_cost_fc               DECIMAL(28,8),
    average_cost_lc             DECIMAL(28,8),
    total_cost_lc               DECIMAL(28,8),
    realized_pnl_fc             DECIMAL(28,8),
    unrealized_pnl_fc           DECIMAL(28,8),
    realized_pnl_lc             DECIMAL(28,8),
    unrealized_pnl_lc           DECIMAL(28,8),
    market_price                DECIMAL(28,8),
    market_value_fc             DECIMAL(28,8),
    market_value_lc             DECIMAL(28,8),
    dividend_fc                 DECIMAL(28,8),
    dividend_lc                 DECIMAL(28,8),
    trade_id                    BIGINT,
    trade_type                  STRING,
    lots_held                   INT,
    custodian                   STRING,
    sub_custodian               STRING,
    security_currency           STRING,
    portfolio_currency          STRING,
    fx_rate                     DECIMAL(28,8),
    status                      STRING,
    is_active                   BOOLEAN,
    is_latest                   BOOLEAN DEFAULT TRUE,
    last_ca_id                  BIGINT,
    last_ca_number              STRING,
    last_ca_type                STRING,
    last_ca_date                STRING,
    last_cash_flow_id           BIGINT,
    last_cash_flow_number       STRING,
    last_cash_flow_amount_fc    DECIMAL(28,8),
    last_cash_flow_amount_lc    DECIMAL(28,8),
    uncall_fc                   DECIMAL(28,8),
    uncall_lc                   DECIMAL(28,8),
    pipeline_fc                 DECIMAL(28,8),
    pipeline_lc                 DECIMAL(28,8),
    position_type               STRING,
    created_by                  STRING,
    created_at                  STRING,
    updated_by                  STRING,
    updated_at                  STRING,
    PRIMARY KEY (version_id)
)
PARTITION BY HASH (version_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'localhost:7051',
    'kudu.table_name' = 'impala::gmp_cis.cis_trade_position'
);

-- Step 3: Restore from backup (comment out if table was empty)
-- INSERT INTO cis_trade_position SELECT * FROM cis_trade_position_bak;
