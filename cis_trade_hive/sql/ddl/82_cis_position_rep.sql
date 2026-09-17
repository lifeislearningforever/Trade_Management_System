-- DDL Migration 82: cis_position_rep — EOD Position Datamart
--
-- Purpose:
--   Reporting/datamart copy of cis_position, containing only EOD rows.
--   Partitioned by position_date so each date's snapshot is independently
--   overwritten without touching other dates.
--
-- Design:
--   - Source: cis_position WHERE position_type = 'EOD' AND is_latest = true
--   - One row per (portfolio, security_label, position_basis, src_system)
--     per position_date.
--   - Populated by: refresh_positions (or a dedicated publish step) via
--     INSERT OVERWRITE PARTITION(position_date = '...') — atomic and idempotent.
--   - Consumers: BI/reporting tools, Impala queries, dashboards.
--
-- Run on server:
--   impala-shell -i <host>:21050 -f 82_cis_position_rep.sql
-- ---------------------------------------------------------------------------

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_position_rep (
    -- Identity
    position_id             BIGINT          COMMENT 'Matches cis_position.position_id for the EOD row',
    version_id              BIGINT          COMMENT 'Timestamp when refresh_positions wrote this EOD row',
    portfolio               STRING          NOT NULL,
    security_label          STRING          NOT NULL,
    position_basis          STRING          NOT NULL    COMMENT 'TRADED or SETTLED',
    src_system              STRING                      COMMENT 'CIS | GMP | AMSICEQ | USER_UPLOAD',
    processing_date         STRING                      COMMENT 'YYYYMMDD — date the EOD job ran',
    processing_timestamp    STRING                      COMMENT 'Datetime the EOD job ran',
    isin                    STRING,
    source_table            STRING,

    -- Quantity & Cost (foreign-currency)
    quantity                DECIMAL(30,8),
    average_cost_fc         DECIMAL(30,8),
    cost_fc                 DECIMAL(30,8),
    market_value_fc         DECIMAL(30,8),
    net_book_value_fc       DECIMAL(30,8),
    unrealized_pnl_fc       DECIMAL(30,8),
    realized_pnl_fc         DECIMAL(30,8),
    provision_fc            DECIMAL(30,8),
    dividend_fc             DECIMAL(30,8),
    uncall_fc               DECIMAL(30,8),
    pipeline_fc             DECIMAL(30,8),

    -- Local-currency equivalents
    average_cost_lc         DECIMAL(30,8),
    cost_lc                 DECIMAL(30,8),
    market_value_lc         DECIMAL(30,8),
    net_book_value_lc       DECIMAL(30,8),
    unrealized_pnl_lc       DECIMAL(30,8),
    realized_pnl_lc         DECIMAL(30,8),
    provision_lc            DECIMAL(30,8),
    dividend_lc             DECIMAL(30,8),
    uncall_lc               DECIMAL(30,8),
    pipeline_lc             DECIMAL(30,8)
)
COMMENT 'EOD position datamart — one row per portfolio/security/basis/src_system per report date'
PARTITIONED BY (
    position_date STRING COMMENT 'Report date YYYY-MM-DD — matches cis_position.position_date'
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/cis_position_rep';

-- Reload partitions after backfill if needed:
-- MSCK REPAIR TABLE gmp_cis.cis_position_rep;
