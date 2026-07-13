-- =============================================================================
-- Daily ETL: cis_equity_price (Kudu) → hive_cis_equity_price (Hive)
-- =============================================================================
--
-- Purpose:
--   For each daily run (processing_date = YYYYMMDD), write exactly ONE record
--   per security into hive_cis_equity_price.
--
-- Rules:
--   1. DEDUPLICATE: cis_equity_price may have multiple rows per
--      (security_label, price_date) — e.g. GMP + CIS edits.
--      Take the single latest by price_timestamp DESC.
--
--   2. LATEST AVAILABLE: For each security, take the record whose price_date
--      is the most recent date <= processing_date (YYYY-MM-DD form).
--      This means: if a price exists for today → use it.
--                  if no price for today → carry forward the last known price.
--
--   3. CARRY-FORWARD (gap-fill): If security ABC last had a price on 27-Apr
--      and the job runs on 28th, 29th, 30th with no new prices, the 27-Apr
--      price is written into every missing partition with the original
--      price_date preserved (so downstream knows when the price was set).
--
-- Parameters (replace before running):
--   ${processing_date}     — run date as YYYYMMDD, e.g. 20260430
--   ${processing_date_fmt} — same date as YYYY-MM-DD, e.g. 2026-04-30
--
-- Usage:
--   impala-shell -i <host>:21050 \
--     --var=processing_date=20260430 \
--     --var=processing_date_fmt=2026-04-30 \
--     -f sql/etl/equity_price_hive_copy_job.sql
--
-- =============================================================================

USE gmp_cis;

-- =============================================================================
-- STEP 1 — Verify source row counts before writing
-- =============================================================================

SELECT
    price_date,
    src_system,
    COUNT(*) AS raw_rows
FROM gmp_cis.cis_equity_price
WHERE is_active = true
  AND CAST(REPLACE(price_date, '-', '') AS INT) <= CAST('${processing_date}' AS INT)
GROUP BY price_date, src_system
ORDER BY price_date DESC, src_system
LIMIT 30;


-- =============================================================================
-- STEP 2 — Preview: one latest record per security (before writing)
-- =============================================================================
-- Shows what will be written for processing_date = ${processing_date_fmt}

SELECT
    currency_code,
    security_label,
    price_date,
    main_closing_price,
    src_system,
    price_timestamp
FROM (
    -- Step A: deduplicate within each (security_label, price_date)
    -- Multiple rows can exist if both GMP and CIS edited the same date.
    -- Take the single latest by price_timestamp.
    SELECT
        currency_code,
        security_label,
        price_date,
        isin,
        main_closing_price,
        price_timestamp,
        src_system,
        is_active,
        created_by,
        created_at,
        updated_by,
        updated_at,
        ROW_NUMBER() OVER (
            PARTITION BY security_label, price_date
            ORDER BY price_timestamp DESC
        ) AS rn_dedup
    FROM gmp_cis.cis_equity_price
    WHERE is_active = true
      AND CAST(REPLACE(price_date, '-', '') AS INT) <= CAST('${processing_date}' AS INT)
) deduped
WHERE rn_dedup = 1
-- Step B: among deduplicated rows, pick the most recent price_date per security
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY security_label
    ORDER BY price_date DESC, price_timestamp DESC
) = 1
ORDER BY security_label
LIMIT 50;


-- =============================================================================
-- STEP 3 — Add partition for today's processing_date
-- =============================================================================

ALTER TABLE gmp_cis.hive_cis_equity_price
    ADD IF NOT EXISTS PARTITION (processing_date='${processing_date}')
    LOCATION '/mrw/cis/hive/cis_equity_price/processing_date=${processing_date}';


-- =============================================================================
-- STEP 4 — Write: one latest record per security into today's partition
-- =============================================================================
-- Uses INSERT OVERWRITE so the job is safe to re-run (idempotent).

INSERT OVERWRITE TABLE gmp_cis.hive_cis_equity_price
PARTITION (processing_date='${processing_date}')
SELECT
    currency_code,
    security_label,
    price_date,          -- original price_date preserved (shows when price was set)
    isin,
    main_closing_price,
    price_timestamp,
    src_system,
    is_active,
    created_by,
    created_at,
    updated_by,
    updated_at
FROM (
    -- Step A: deduplicate — one row per (security_label, price_date)
    SELECT
        currency_code,
        security_label,
        price_date,
        isin,
        main_closing_price,
        price_timestamp,
        src_system,
        is_active,
        created_by,
        created_at,
        updated_by,
        updated_at,
        ROW_NUMBER() OVER (
            PARTITION BY security_label, price_date
            ORDER BY price_timestamp DESC
        ) AS rn_dedup
    FROM gmp_cis.cis_equity_price
    WHERE is_active = true
      AND CAST(REPLACE(price_date, '-', '') AS INT) <= CAST('${processing_date}' AS INT)
) deduped
WHERE rn_dedup = 1
-- Step B: among all deduplicated dates, pick the most recent per security (carry-forward)
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY security_label
    ORDER BY price_date DESC, price_timestamp DESC
) = 1;


-- =============================================================================
-- STEP 5 — Verify inserted rows
-- =============================================================================

SELECT
    src_system,
    COUNT(*) AS securities_written,
    MIN(price_date) AS oldest_price_date,
    MAX(price_date) AS newest_price_date
FROM gmp_cis.hive_cis_equity_price
WHERE processing_date = '${processing_date}'
GROUP BY src_system
ORDER BY src_system;


-- =============================================================================
-- STEP 6 — Spot-check carry-forward: securities whose price_date < processing_date
-- =============================================================================
-- These are the ones that were gap-filled (no price for today, last known carried)

SELECT
    security_label,
    currency_code,
    price_date AS last_known_price_date,
    main_closing_price,
    src_system,
    DATEDIFF(TO_DATE('${processing_date_fmt}'), TO_DATE(price_date)) AS days_carried_forward
FROM gmp_cis.hive_cis_equity_price
WHERE processing_date = '${processing_date}'
  AND price_date < '${processing_date_fmt}'
ORDER BY days_carried_forward DESC, security_label
LIMIT 30;
