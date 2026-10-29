-- ============================================================================
-- Impala SQL: Merge GMP Equity Price Data into CIS Equity Price Table
-- ============================================================================
-- Alternative to PySpark job - pure Impala SQL approach
--
-- Problem:
--   - GMP sends equity price data
--   - cis_equity_price_kudu PK = (currency_code, security_label, price_date)
--   - This is a NATURAL composite key - GMP provides ALL PK fields
--   - No surrogate key gap (unlike security table)
--
-- Approach:
--   - Simple UPSERT from staging into target
--   - Kudu UPSERT handles both insert (new) and update (existing PK)
--
-- Prerequisites:
--   - Staging table stg_gmp_equity_price populated by ETL
--   - Run via: impala-shell -i <host>:21050 -f merge_gmp_equity_price.sql
--
-- Created: 2026-02-02
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- MERGE: Direct UPSERT (no ID generation needed)
-- ============================================================================
-- PK is natural composite (currency_code, security_label, price_date)
-- GMP provides all three fields - Kudu UPSERT handles insert/update
-- ============================================================================

UPSERT INTO cis_equity_price (
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
)
SELECT
    stg.currency_code,
    stg.security_label,
    stg.price_date,
    stg.isin,
    stg.main_closing_price,
    stg.price_timestamp,
    'GMP' AS src_system,
    true AS is_active,
    'GMP_ETL' AS created_by,
    UNIX_TIMESTAMP() * 1000 AS created_at,
    'GMP_ETL' AS updated_by,
    UNIX_TIMESTAMP() * 1000 AS updated_at
FROM stg_gmp_equity_price stg;


-- ============================================================================
-- POST-MERGE: Clear staging table (optional)
-- ============================================================================
-- Uncomment to truncate staging after successful merge
-- DELETE FROM stg_gmp_equity_price WHERE 1=1;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Count by src_system after merge
SELECT src_system, COUNT(*) AS cnt
FROM cis_equity_price
WHERE is_active = true
GROUP BY src_system;

-- Check recently merged records
SELECT currency_code, security_label, price_date, main_closing_price, src_system
FROM cis_equity_price
WHERE src_system = 'GMP'
ORDER BY price_date DESC, security_label
LIMIT 20;
