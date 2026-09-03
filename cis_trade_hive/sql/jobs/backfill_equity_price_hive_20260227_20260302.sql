-- =============================================================================
-- ONE-TIME BACKFILL: Copy cis_equity_price → hive_cis_equity_price
--
-- Source  : gmp_cis.cis_equity_price  (Kudu)
-- Target  : gmp_cis.hive_cis_equity_price  (Hive external, partitioned by processing_date)
--
-- Logic   : For each security_label, take the latest available price:
--             1st choice — price_date = 2026-03-02  (2nd March)
--             Fallback   — price_date = 2026-02-27  (27th Feb)
--           Only one record per security_label in the output.
--
-- Usage:
--   impala-shell -i localhost:21050 -f sql/jobs/backfill_equity_price_hive_20260227_20260302.sql
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1 — Verify source counts before inserting
-- ─────────────────────────────────────────────────────────────────────────────
SELECT price_date, COUNT(*) AS record_count
FROM gmp_cis.cis_equity_price
WHERE price_date IN ('2026-02-27', '2026-03-02')
GROUP BY price_date
ORDER BY price_date;


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2 — Preview: one latest record per security_label
--          2026-03-02 wins; fallback to 2026-02-27 if no March record
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    currency_code,
    security_label,
    price_date,
    main_closing_price,
    src_system
FROM (
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
            PARTITION BY security_label
            ORDER BY price_date DESC
        ) AS rn
    FROM gmp_cis.cis_equity_price
    WHERE price_date IN ('2026-02-27', '2026-03-02')
) ranked
WHERE rn = 1
ORDER BY security_label
LIMIT 50;


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3 — Add partition for the processing_date in hive_cis_equity_price
--          Use today's date as processing_date (YYYYMMDD)
--          Replace 20260629 with the actual run date if different
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE gmp_cis.hive_cis_equity_price
    ADD IF NOT EXISTS PARTITION (processing_date='20260629')
    LOCATION '/mrw/cis/hive/cis_equity_price/processing_date=20260629';


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 4 — Insert into hive_cis_equity_price
--          One latest record per security_label (2026-03-02 preferred, 2026-02-27 fallback)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO gmp_cis.hive_cis_equity_price
    PARTITION (processing_date='20260629')
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
    updated_at
FROM (
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
            PARTITION BY security_label
            ORDER BY price_date DESC
        ) AS rn
    FROM gmp_cis.cis_equity_price
    WHERE price_date IN ('2026-02-27', '2026-03-02')
) ranked
WHERE rn = 1;


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 5 — Verify inserted rows
-- ─────────────────────────────────────────────────────────────────────────────
SELECT price_date, COUNT(*) AS inserted_count
FROM gmp_cis.hive_cis_equity_price
WHERE processing_date = '20260629'
GROUP BY price_date
ORDER BY price_date;
