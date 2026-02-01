-- ============================================================================
-- Impala SQL: Merge GMP Security Data into CIS Security Table
-- ============================================================================
-- Alternative to PySpark job - pure Impala SQL approach
--
-- Problem:
--   - GMP sends security data without security_id (surrogate key)
--   - cis_security_kudu requires security_id as PK (BIGINT)
--   - Must match on natural key (ISIN) for existing records
--   - Must generate security_id for new records
--
-- Approach: Two-step merge
--   Step 1: UPSERT existing records (INNER JOIN on isin -> reuse security_id)
--   Step 2: UPSERT new records (LEFT JOIN WHERE NULL -> generate security_id)
--
-- Prerequisites:
--   - Staging table stg_gmp_security populated by ETL
--   - Run via: impala-shell -i <host>:21050 -f merge_gmp_security.sql
--
-- Created: 2026-02-02
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- STEP 1: UPDATE EXISTING RECORDS
-- ============================================================================
-- Records where ISIN already exists in cis_security
-- Reuse the existing security_id (preserves PK identity)
-- ============================================================================

UPSERT INTO cis_security (
    security_id,
    security_name,
    isin,
    security_description,
    issuer,
    ticker,
    industry,
    security_type,
    investment_type,
    issuer_type,
    quoted_unquoted,
    country_of_incorporation,
    country_of_exchange,
    country_of_issue,
    country_of_primary_exchange,
    exchange_code,
    currency_code,
    price,
    price_date,
    price_source,
    shares_outstanding,
    beta,
    par_value,
    shareholding_entity_1,
    shareholding_entity_2,
    shareholding_entity_3,
    shareholding_aggregated,
    substantial_10_pct,
    bwciif,
    bwciif_others,
    cels,
    approved_s32,
    basel_iv_fund,
    mas_643_entity_type,
    mas_6d_code,
    fin_nonfin_ind,
    business_unit_head,
    person_in_charge,
    core_noncore,
    fund_index_fund,
    management_limit_classification,
    relative_index,
    src_system,
    is_active,
    created_by,
    created_at,
    updated_by,
    updated_at
)
SELECT
    existing.security_id,              -- Reuse existing security_id
    stg.security_name,
    stg.isin,
    stg.security_description,
    stg.issuer,
    stg.ticker,
    stg.industry,
    stg.security_type,
    stg.investment_type,
    stg.issuer_type,
    stg.quoted_unquoted,
    stg.country_of_incorporation,
    stg.country_of_exchange,
    stg.country_of_issue,
    stg.country_of_primary_exchange,
    stg.exchange_code,
    stg.currency_code,
    stg.price,
    stg.price_date,
    stg.price_source,
    stg.shares_outstanding,
    stg.beta,
    stg.par_value,
    stg.shareholding_entity_1,
    stg.shareholding_entity_2,
    stg.shareholding_entity_3,
    stg.shareholding_aggregated,
    stg.substantial_10_pct,
    stg.bwciif,
    stg.bwciif_others,
    stg.cels,
    stg.approved_s32,
    stg.basel_iv_fund,
    stg.mas_643_entity_type,
    stg.mas_6d_code,
    stg.fin_nonfin_ind,
    stg.business_unit_head,
    stg.person_in_charge,
    stg.core_noncore,
    stg.fund_index_fund,
    stg.management_limit_classification,
    stg.relative_index,
    'GMP' AS src_system,
    true AS is_active,
    'GMP_ETL' AS created_by,
    UNIX_TIMESTAMP() * 1000 AS created_at,
    'GMP_ETL' AS updated_by,
    UNIX_TIMESTAMP() * 1000 AS updated_at
FROM stg_gmp_security stg
INNER JOIN cis_security existing
    ON stg.isin = existing.isin
    AND existing.is_active = true;


-- ============================================================================
-- STEP 2: INSERT NEW RECORDS (no existing ISIN match)
-- ============================================================================
-- Records where ISIN does NOT exist in cis_security
-- Generate new security_id using timestamp + row_number
-- ============================================================================

-- Generate IDs using a subquery with row_number()
-- Base ID = current unix timestamp in milliseconds
-- Each new record gets base_id + row_number to ensure uniqueness
UPSERT INTO cis_security (
    security_id,
    security_name,
    isin,
    security_description,
    issuer,
    ticker,
    industry,
    security_type,
    investment_type,
    issuer_type,
    quoted_unquoted,
    country_of_incorporation,
    country_of_exchange,
    country_of_issue,
    country_of_primary_exchange,
    exchange_code,
    currency_code,
    price,
    price_date,
    price_source,
    shares_outstanding,
    beta,
    par_value,
    shareholding_entity_1,
    shareholding_entity_2,
    shareholding_entity_3,
    shareholding_aggregated,
    substantial_10_pct,
    bwciif,
    bwciif_others,
    cels,
    approved_s32,
    basel_iv_fund,
    mas_643_entity_type,
    mas_6d_code,
    fin_nonfin_ind,
    business_unit_head,
    person_in_charge,
    core_noncore,
    fund_index_fund,
    management_limit_classification,
    relative_index,
    src_system,
    is_active,
    created_by,
    created_at,
    updated_by,
    updated_at
)
SELECT
    -- Generate unique security_id: base_timestamp_ms + row_number
    (UNIX_TIMESTAMP() * 1000) + ROW_NUMBER() OVER (ORDER BY stg.isin) AS security_id,
    stg.security_name,
    stg.isin,
    stg.security_description,
    stg.issuer,
    stg.ticker,
    stg.industry,
    stg.security_type,
    stg.investment_type,
    stg.issuer_type,
    stg.quoted_unquoted,
    stg.country_of_incorporation,
    stg.country_of_exchange,
    stg.country_of_issue,
    stg.country_of_primary_exchange,
    stg.exchange_code,
    stg.currency_code,
    stg.price,
    stg.price_date,
    stg.price_source,
    stg.shares_outstanding,
    stg.beta,
    stg.par_value,
    stg.shareholding_entity_1,
    stg.shareholding_entity_2,
    stg.shareholding_entity_3,
    stg.shareholding_aggregated,
    stg.substantial_10_pct,
    stg.bwciif,
    stg.bwciif_others,
    stg.cels,
    stg.approved_s32,
    stg.basel_iv_fund,
    stg.mas_643_entity_type,
    stg.mas_6d_code,
    stg.fin_nonfin_ind,
    stg.business_unit_head,
    stg.person_in_charge,
    stg.core_noncore,
    stg.fund_index_fund,
    stg.management_limit_classification,
    stg.relative_index,
    'GMP' AS src_system,
    true AS is_active,
    'GMP_ETL' AS created_by,
    UNIX_TIMESTAMP() * 1000 AS created_at,
    'GMP_ETL' AS updated_by,
    UNIX_TIMESTAMP() * 1000 AS updated_at
FROM stg_gmp_security stg
LEFT JOIN cis_security existing
    ON stg.isin = existing.isin
    AND existing.is_active = true
WHERE existing.security_id IS NULL;


-- ============================================================================
-- POST-MERGE: Clear staging table (optional)
-- ============================================================================
-- Uncomment to truncate staging after successful merge
-- DELETE FROM stg_gmp_security WHERE 1=1;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Count by src_system after merge
SELECT src_system, COUNT(*) AS cnt
FROM cis_security
WHERE is_active = true
GROUP BY src_system;

-- Check recently merged records
SELECT security_id, isin, security_name, src_system, updated_at
FROM cis_security
WHERE src_system = 'GMP'
ORDER BY updated_at DESC
LIMIT 20;
