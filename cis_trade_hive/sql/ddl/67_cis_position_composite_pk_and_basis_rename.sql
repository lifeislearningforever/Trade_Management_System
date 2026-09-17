-- ============================================================================
-- DDL 67: cis_position — composite PK + position_basis rename
-- ============================================================================
--
-- Two changes applied together (both require table recreation in Kudu):
--
-- 1. PRIMARY KEY change: (position_id) → (position_id, position_type)
--    Reason: SOD, INT, EOD, CORR coexist as separate rows on the same
--    position_date. They share a position_id (same natural key → same hash)
--    and are distinguished by position_type.  A single-column PK on
--    position_id would collapse them to one row.
--
-- 2. position_basis values renamed:
--    TRADE_DATE  → TRADED
--    SETTLE_DATE → SETTLED
--    Reason: shorter, cleaner, consistent with financial industry convention.
--    Applied to: cis_position, cis_trade_position, cis_position_queue,
--                cis_settlement_queue
--
-- 3. position_id is now a DETERMINISTIC hash of the natural key:
--    fnv_hash(portfolio | security_label | position_basis | position_date | src_system)
--    → same natural key always produces the same position_id
--    → re-running any writer for the same date is idempotent via UPSERT
--    → INT, EOD, SOD for same natural key share one position_id; position_type
--      is the differentiator in the composite PK
--
-- Database: gmp_cis
-- Created: 2026-07-01
-- Run order: after DDL 66
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- STEP 1: Recreate cis_position with composite PK (position_id, position_type)
-- ============================================================================
-- Kudu does not support ALTER PRIMARY KEY, so we recreate via rename.

-- 1A. Create replacement table
CREATE TABLE IF NOT EXISTS cis_position_v2 (
    position_id             BIGINT NOT NULL,
    position_type           STRING NOT NULL,   -- SOD | INT | EOD | CORR
    version_id              BIGINT NOT NULL,   -- timestamp of last write (audit)
    portfolio               STRING NOT NULL,
    security_label          STRING NOT NULL,
    position_basis          STRING NOT NULL,   -- TRADED | SETTLED
    position_date           STRING NOT NULL,
    src_system              STRING,
    processing_date         STRING,
    quantity                DECIMAL(30,8),
    average_cost_fc         DECIMAL(30,8),
    cost_fc                 DECIMAL(30,8),
    average_cost_lc         DECIMAL(30,8),
    cost_lc                 DECIMAL(30,8),
    market_value_fc         DECIMAL(30,8),
    market_value_lc         DECIMAL(30,8),
    net_book_value_fc       DECIMAL(30,8),
    net_book_value_lc       DECIMAL(30,8),
    unrealized_pnl_fc       DECIMAL(30,8),
    unrealized_pnl_lc       DECIMAL(30,8),
    realized_pnl_fc         DECIMAL(30,8),
    realized_pnl_lc         DECIMAL(30,8),
    provision_fc            DECIMAL(30,8),
    provision_lc            DECIMAL(30,8),
    dividend_fc             DECIMAL(30,8),
    dividend_lc             DECIMAL(30,8),
    uncall_fc               DECIMAL(30,8),
    uncall_lc               DECIMAL(30,8),
    pipeline_fc             DECIMAL(30,8),
    pipeline_lc             DECIMAL(30,8),
    isin                    STRING,
    source_table            STRING,
    processing_timestamp    STRING,
    is_latest               BOOLEAN,
    PRIMARY KEY (position_id, position_type)
)
PARTITION BY HASH(position_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 1B. Migrate data — rename basis values, keep all rows
INSERT INTO cis_position_v2
SELECT
    position_id,
    COALESCE(position_type, 'INT')                          AS position_type,
    version_id,
    portfolio,
    security_label,
    CASE position_basis
        WHEN 'TRADE_DATE'  THEN 'TRADED'
        WHEN 'SETTLE_DATE' THEN 'SETTLED'
        ELSE COALESCE(position_basis, 'TRADED')
    END                                                     AS position_basis,
    position_date,
    src_system,
    processing_date,
    quantity,
    average_cost_fc,
    cost_fc,
    average_cost_lc,
    cost_lc,
    market_value_fc,
    market_value_lc,
    net_book_value_fc,
    net_book_value_lc,
    unrealized_pnl_fc,
    unrealized_pnl_lc,
    realized_pnl_fc,
    realized_pnl_lc,
    provision_fc,
    provision_lc,
    dividend_fc,
    dividend_lc,
    uncall_fc,
    uncall_lc,
    pipeline_fc,
    pipeline_lc,
    isin,
    source_table,
    processing_timestamp,
    COALESCE(is_latest, true)                               AS is_latest
FROM cis_position;

-- 1C. Swap tables (manual step — requires brief maintenance window)
-- ALTER TABLE cis_position RENAME TO cis_position_old;
-- ALTER TABLE cis_position_v2 RENAME TO cis_position;

-- ============================================================================
-- STEP 2: Rename position_basis values in cis_trade_position
-- ============================================================================
-- Kudu UPDATE requires fetching and re-upserting rows by primary key (version_id).
-- Run the following queries in sequence from impala-shell or a migration script.

-- Preview counts first:
SELECT position_basis, COUNT(*) FROM cis_trade_position GROUP BY position_basis;

-- Rename TRADE_DATE → TRADED in cis_trade_position
-- (Run via Python migration script — see scripts/migrate_position_basis.py)

-- ============================================================================
-- STEP 3: Rename position_basis values in queue tables
-- ============================================================================
SELECT position_basis, COUNT(*) FROM cis_position_queue   GROUP BY position_basis;
SELECT position_basis, COUNT(*) FROM cis_settlement_queue GROUP BY position_basis;

-- Run via scripts/migrate_position_basis.py (batch UPSERT by queue_id)

-- ============================================================================
-- STEP 4: Verify
-- ============================================================================
-- After migration and table swap:

SELECT position_type, position_basis, COUNT(*) AS rows, SUM(CASE WHEN is_latest THEN 1 ELSE 0 END) AS latest
FROM gmp_cis.cis_position
GROUP BY position_type, position_basis
ORDER BY position_type, position_basis;

-- Should show zero legacy values:
SELECT COUNT(*) AS legacy_basis_rows
FROM gmp_cis.cis_position
WHERE position_basis IN ('TRADE_DATE', 'SETTLE_DATE');

-- ============================================================================
-- NOTES
-- ============================================================================
-- The composite PK (position_id, position_type) means:
--   UPSERT by (position_id, position_type) replaces the matching row.
--   Rows with same position_id but different position_type coexist.
--
-- position_id is now a deterministic hash:
--   fnv_hash(portfolio|security_label|position_basis|position_date|src_system)
--   Python equivalent: position_id_service.position_id(...)
--
-- version_id is always a new timestamp on each write — it is NOT part of the
-- PK and serves only as an audit timestamp for "when was this row last written".
