-- ============================================================================
-- Validation Queries: Post-Merge Data Quality Checks
-- ============================================================================
-- Run after GMP ETL merge to validate data integrity
--
-- Usage: impala-shell -i <host>:21050 -f validate_merge.sql
--
-- Created: 2026-02-02
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- 1. SECURITY TABLE VALIDATION
-- ============================================================================

-- 1a. Record counts by source system
SELECT '1a. Security counts by src_system' AS check_name;
SELECT
    COALESCE(src_system, 'NULL') AS src_system,
    COUNT(*) AS total_records,
    SUM(CASE WHEN is_active = true THEN 1 ELSE 0 END) AS active_records,
    SUM(CASE WHEN is_active = false THEN 1 ELSE 0 END) AS inactive_records
FROM cis_security
GROUP BY src_system
ORDER BY src_system;


-- 1b. Check for duplicate ISINs (should not happen within active records)
SELECT '1b. Duplicate ISINs in active securities' AS check_name;
SELECT
    isin,
    COUNT(*) AS duplicate_count,
    GROUP_CONCAT(CAST(security_id AS STRING), ', ') AS security_ids
FROM cis_security
WHERE is_active = true
  AND isin IS NOT NULL
GROUP BY isin
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC
LIMIT 20;


-- 1c. Staging records that did NOT merge (should be 0 after successful merge)
SELECT '1c. Staging records not merged (orphans)' AS check_name;
SELECT COUNT(*) AS unmerged_staging_count
FROM stg_gmp_security stg
LEFT JOIN cis_security existing
    ON stg.isin = existing.isin
    AND existing.is_active = true
    AND existing.src_system = 'GMP'
WHERE existing.security_id IS NULL;


-- 1d. NULL ISIN check in staging (ISIN is the match key - must not be null)
SELECT '1d. Staging records with NULL ISIN' AS check_name;
SELECT COUNT(*) AS null_isin_count
FROM stg_gmp_security
WHERE isin IS NULL OR TRIM(isin) = '';


-- 1e. Recently merged GMP securities
SELECT '1e. Recently merged GMP securities (top 10)' AS check_name;
SELECT
    security_id,
    security_name,
    isin,
    currency_code,
    src_system,
    updated_at
FROM cis_security
WHERE src_system = 'GMP' AND is_active = true
ORDER BY updated_at DESC
LIMIT 10;


-- ============================================================================
-- 2. EQUITY PRICE TABLE VALIDATION
-- ============================================================================

-- 2a. Record counts by source system
SELECT '2a. Equity price counts by src_system' AS check_name;
SELECT
    COALESCE(src_system, 'NULL') AS src_system,
    COUNT(*) AS total_records,
    SUM(CASE WHEN is_active = true THEN 1 ELSE 0 END) AS active_records
FROM cis_equity_price
GROUP BY src_system
ORDER BY src_system;


-- 2b. Price date range by source system
SELECT '2b. Price date range by src_system' AS check_name;
SELECT
    src_system,
    MIN(price_date) AS earliest_date,
    MAX(price_date) AS latest_date,
    COUNT(DISTINCT price_date) AS unique_dates,
    COUNT(DISTINCT security_label) AS unique_securities
FROM cis_equity_price
WHERE is_active = true
GROUP BY src_system;


-- 2c. Check for orphan prices (prices without matching security)
SELECT '2c. Orphan equity prices (no matching security)' AS check_name;
SELECT
    ep.currency_code,
    ep.security_label,
    ep.price_date,
    ep.main_closing_price,
    ep.src_system
FROM cis_equity_price ep
LEFT JOIN cis_security sec
    ON ep.security_label = sec.security_name
    AND sec.is_active = true
WHERE sec.security_id IS NULL
  AND ep.is_active = true
ORDER BY ep.price_date DESC
LIMIT 20;


-- 2d. NULL or zero price check
SELECT '2d. Records with NULL or zero closing price' AS check_name;
SELECT
    src_system,
    COUNT(*) AS bad_price_count
FROM cis_equity_price
WHERE is_active = true
  AND (main_closing_price IS NULL OR main_closing_price = 0)
GROUP BY src_system;


-- 2e. Recently merged GMP equity prices
SELECT '2e. Recently merged GMP equity prices (top 10)' AS check_name;
SELECT
    currency_code,
    security_label,
    price_date,
    main_closing_price,
    src_system,
    updated_at
FROM cis_equity_price
WHERE src_system = 'GMP' AND is_active = true
ORDER BY updated_at DESC
LIMIT 10;


-- ============================================================================
-- 3. CROSS-TABLE VALIDATION
-- ============================================================================

-- 3a. Securities with prices vs without prices
SELECT '3a. Securities with/without equity prices' AS check_name;
SELECT
    sec.src_system AS security_src,
    COUNT(DISTINCT sec.security_id) AS total_securities,
    COUNT(DISTINCT CASE WHEN ep.security_label IS NOT NULL THEN sec.security_id END) AS with_prices,
    COUNT(DISTINCT CASE WHEN ep.security_label IS NULL THEN sec.security_id END) AS without_prices
FROM cis_security sec
LEFT JOIN (
    SELECT DISTINCT security_label
    FROM cis_equity_price
    WHERE is_active = true
) ep ON sec.security_name = ep.security_label
WHERE sec.is_active = true
GROUP BY sec.src_system;


-- 3b. Summary dashboard
SELECT '3b. Merge summary dashboard' AS check_name;
SELECT
    'Securities' AS table_name,
    COUNT(*) AS total_active,
    SUM(CASE WHEN src_system = 'CIS' THEN 1 ELSE 0 END) AS cis_records,
    SUM(CASE WHEN src_system = 'GMP' THEN 1 ELSE 0 END) AS gmp_records,
    SUM(CASE WHEN src_system IS NULL THEN 1 ELSE 0 END) AS null_src_records
FROM cis_security
WHERE is_active = true

UNION ALL

SELECT
    'Equity Prices' AS table_name,
    COUNT(*) AS total_active,
    SUM(CASE WHEN src_system = 'CIS' THEN 1 ELSE 0 END) AS cis_records,
    SUM(CASE WHEN src_system = 'GMP' THEN 1 ELSE 0 END) AS gmp_records,
    SUM(CASE WHEN src_system IS NULL THEN 1 ELSE 0 END) AS null_src_records
FROM cis_equity_price
WHERE is_active = true;


-- ============================================================================
-- 4. STAGING TABLE STATUS
-- ============================================================================

-- 4a. Staging table record counts (should be 0 after cleanup)
SELECT '4a. Staging table record counts' AS check_name;
SELECT 'stg_gmp_security' AS staging_table, COUNT(*) AS pending_records
FROM stg_gmp_security

UNION ALL

SELECT 'stg_gmp_equity_price' AS staging_table, COUNT(*) AS pending_records
FROM stg_gmp_equity_price;
