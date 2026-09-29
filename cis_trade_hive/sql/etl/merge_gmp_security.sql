-- ============================================================================
-- Impala SQL: Merge GMP Security Data into cis_security
-- ============================================================================
-- Updated: 2026-06-02  — registry-based stable ID (replaces truncate-reload)
--
-- Problem solved:
--   Old approach: DELETE all GMP rows → INSERT new rows → new timestamp ID
--   every run.  Downstream systems saw every GMP security as "changed".
--
-- New approach:
--   1. Look up cis_security_id_registry by normalised natural key (ISIN first,
--      fallback to name+exchange, then name alone).
--   2. Known natural key  → reuse the stored stable 12-digit ID.
--   3. New natural key    → allocate next ID from cis_security_id_counter,
--      write to registry, then UPSERT into cis_security.
--   No DELETE of existing rows needed.  CIS rows (src_system='CIS') are never
--   touched because we only UPSERT rows whose security_id came from GMP.
--
-- Prerequisites:
--   - stg_gmp_security populated by upstream ETL
--   - cis_security_id_registry and cis_security_id_counter exist (DDL 64)
--   - Run DDL 64 migration once to back-fill existing IDs
--
-- Run via: impala-shell -i <host>:21050 -f merge_gmp_security.sql
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- STEP 1: Attach natural keys to staging rows
--
-- CRITICAL: same ISIN can appear on multiple exchanges (cross-listed).
--   ANZ Banking Group: ISIN AU000000ANZ3 on ASX (AU) AND on NZX (NZ).
--   These are different instruments. ISIN alone is NOT a unique key.
--   The composite ISIN + exchange_code disambiguates them.
--
-- Priority (first matching rule wins):
--   1. ISIN + exchange_code       → "ISIN_EXCH:<isin>:<exch>"
--   2. ISIN + country_of_exchange → "ISIN_CTY:<isin>:<country>"
--   3. ISIN only                  → "ISIN:<isin>"           (bonds, private)
--   4. name + exchange_code       → "NAME_EXCH:<name>:<exch>"
--   5. name + country_of_exchange → "NAME_CTY:<name>:<country>"
--   6. name only                  → "NAME:<name>"           (last resort)
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmp_cis.stg_gmp_security_with_key
STORED AS PARQUET AS
SELECT
    *,
    CASE
        WHEN isin IS NOT NULL AND TRIM(isin) != ''
             AND exchange_code IS NOT NULL AND TRIM(exchange_code) != ''
            THEN CONCAT('ISIN_EXCH:', UPPER(TRIM(isin)), ':', UPPER(TRIM(exchange_code)))
        WHEN isin IS NOT NULL AND TRIM(isin) != ''
             AND country_of_exchange IS NOT NULL AND TRIM(country_of_exchange) != ''
            THEN CONCAT('ISIN_CTY:', UPPER(TRIM(isin)), ':', UPPER(TRIM(country_of_exchange)))
        WHEN isin IS NOT NULL AND TRIM(isin) != ''
            THEN CONCAT('ISIN:', UPPER(TRIM(isin)))
        WHEN exchange_code IS NOT NULL AND TRIM(exchange_code) != ''
            THEN CONCAT('NAME_EXCH:', UPPER(TRIM(security_name)), ':', UPPER(TRIM(exchange_code)))
        WHEN country_of_exchange IS NOT NULL AND TRIM(country_of_exchange) != ''
            THEN CONCAT('NAME_CTY:', UPPER(TRIM(security_name)), ':', UPPER(TRIM(country_of_exchange)))
        ELSE
            CONCAT('NAME:', UPPER(TRIM(security_name)))
    END AS natural_key,
    CASE
        WHEN isin IS NOT NULL AND TRIM(isin) != ''
             AND exchange_code IS NOT NULL AND TRIM(exchange_code) != ''     THEN 'ISIN_EXCH'
        WHEN isin IS NOT NULL AND TRIM(isin) != ''
             AND country_of_exchange IS NOT NULL AND TRIM(country_of_exchange) != '' THEN 'ISIN_CTY'
        WHEN isin IS NOT NULL AND TRIM(isin) != ''                          THEN 'ISIN'
        WHEN exchange_code IS NOT NULL AND TRIM(exchange_code) != ''        THEN 'NAME_EXCH'
        WHEN country_of_exchange IS NOT NULL AND TRIM(country_of_exchange) != '' THEN 'NAME_CTY'
        ELSE 'NAME'
    END AS key_type
FROM gmp_cis.stg_gmp_security;


-- ============================================================================
-- STEP 2: Upsert known records (natural key already in registry)
--   Reuse the stable security_id — no ID change.
--   Only GMP src_system rows are written; CIS rows in cis_security are
--   untouched because we never send their security_ids here.
-- ============================================================================

UPSERT INTO gmp_cis.cis_security (
    security_id, record_type, security_name, isin, security_description, issuer,
    ticker, industry, security_type, investment_type, issuer_type, quoted_unquoted,
    country_of_incorporation, country_of_exchange, country_of_issue, exchange_code,
    currency_code, price, shares_outstanding, beta, par_value,
    pct_hld_entity_1, pct_hld_entity_2, pct_hld_entity_3, pct_hld_entity_aggr,
    substantial_10_pct, cels, pevc_s32_devest, s32_representative, basel_iv_fund,
    mas_643_entity_type, mas_6d_code, fin_nonfin_ind, business_unit_head,
    person_in_charge, core_noncore, fund_index_fund, management_limit_classification,
    relative_index, src_system, is_active, created_by, created_at, updated_by, updated_at
)
SELECT
    r.security_id,                          -- Stable ID from registry
    stg.record_type, stg.security_name, stg.isin, stg.security_description,
    stg.issuer, stg.ticker, stg.industry, stg.security_type, stg.investment_type,
    stg.issuer_type, stg.quoted_unquoted, stg.country_of_incorporation,
    stg.country_of_exchange, stg.country_of_issue, stg.exchange_code,
    stg.currency_code, stg.price, stg.shares_outstanding, stg.beta, stg.par_value,
    stg.pct_hld_entity_1, stg.pct_hld_entity_2, stg.pct_hld_entity_3,
    stg.pct_hld_entity_aggr, stg.substantial_10_pct, stg.cels, stg.pevc_s32_devest,
    stg.s32_representative, stg.basel_iv_fund, stg.mas_643_entity_type,
    stg.mas_6d_code, stg.fin_nonfin_ind, stg.business_unit_head, stg.person_in_charge,
    stg.core_noncore, stg.fund_index_fund, stg.management_limit_classification,
    stg.relative_index,
    'GMP'                   AS src_system,
    true                    AS is_active,
    'GMP_ETL'               AS created_by,
    UNIX_TIMESTAMP() * 1000 AS created_at,
    'GMP_ETL'               AS updated_by,
    UNIX_TIMESTAMP() * 1000 AS updated_at
FROM gmp_cis.stg_gmp_security_with_key stg
INNER JOIN gmp_cis.cis_security_id_registry r
    ON stg.natural_key = r.natural_key;


-- ============================================================================
-- STEP 3: Allocate IDs for new records (natural key NOT yet in registry)
--   Uses cis_security_id_counter to get the next available 12-digit ID block.
--   ROW_NUMBER() offsets within the batch so each new row gets a unique ID.
-- ============================================================================

-- 3a. Write new entries into the registry
--     (natural_key is the PK — safe to UPSERT; CIS rows already have their
--      own natural_key entries from the migration, so they won't be re-added)

UPSERT INTO gmp_cis.cis_security_id_registry (
    natural_key, security_id, key_type, isin, security_name,
    exchange_code, country_of_exchange, src_system, created_by, created_at
)
SELECT
    stg.natural_key,
    -- Allocate: counter.next_id + row_number - 1
    (SELECT next_id FROM gmp_cis.cis_security_id_counter WHERE counter_id = 1)
        + ROW_NUMBER() OVER (ORDER BY stg.natural_key) - 1  AS security_id,
    stg.key_type,
    UPPER(TRIM(stg.isin))           AS isin,
    stg.security_name,
    UPPER(TRIM(stg.exchange_code))  AS exchange_code,
    UPPER(TRIM(stg.country_of_exchange)) AS country_of_exchange,
    'GMP'                           AS src_system,
    'GMP_ETL'                       AS created_by,
    UNIX_TIMESTAMP() * 1000         AS created_at
FROM gmp_cis.stg_gmp_security_with_key stg
LEFT JOIN gmp_cis.cis_security_id_registry r
    ON stg.natural_key = r.natural_key
WHERE r.natural_key IS NULL;    -- Only truly new natural keys


-- 3b. Write the new securities into cis_security using the IDs just registered

UPSERT INTO gmp_cis.cis_security (
    security_id, record_type, security_name, isin, security_description, issuer,
    ticker, industry, security_type, investment_type, issuer_type, quoted_unquoted,
    country_of_incorporation, country_of_exchange, country_of_issue, exchange_code,
    currency_code, price, shares_outstanding, beta, par_value,
    pct_hld_entity_1, pct_hld_entity_2, pct_hld_entity_3, pct_hld_entity_aggr,
    substantial_10_pct, cels, pevc_s32_devest, s32_representative, basel_iv_fund,
    mas_643_entity_type, mas_6d_code, fin_nonfin_ind, business_unit_head,
    person_in_charge, core_noncore, fund_index_fund, management_limit_classification,
    relative_index, src_system, is_active, created_by, created_at, updated_by, updated_at
)
SELECT
    r.security_id,                          -- ID just written to registry in 3a
    stg.record_type, stg.security_name, stg.isin, stg.security_description,
    stg.issuer, stg.ticker, stg.industry, stg.security_type, stg.investment_type,
    stg.issuer_type, stg.quoted_unquoted, stg.country_of_incorporation,
    stg.country_of_exchange, stg.country_of_issue, stg.exchange_code,
    stg.currency_code, stg.price, stg.shares_outstanding, stg.beta, stg.par_value,
    stg.pct_hld_entity_1, stg.pct_hld_entity_2, stg.pct_hld_entity_3,
    stg.pct_hld_entity_aggr, stg.substantial_10_pct, stg.cels, stg.pevc_s32_devest,
    stg.s32_representative, stg.basel_iv_fund, stg.mas_643_entity_type,
    stg.mas_6d_code, stg.fin_nonfin_ind, stg.business_unit_head, stg.person_in_charge,
    stg.core_noncore, stg.fund_index_fund, stg.management_limit_classification,
    stg.relative_index,
    'GMP'                   AS src_system,
    true                    AS is_active,
    'GMP_ETL'               AS created_by,
    UNIX_TIMESTAMP() * 1000 AS created_at,
    'GMP_ETL'               AS updated_by,
    UNIX_TIMESTAMP() * 1000 AS updated_at
FROM gmp_cis.stg_gmp_security_with_key stg
INNER JOIN gmp_cis.cis_security_id_registry r
    ON stg.natural_key = r.natural_key
-- Only the rows we JUST registered (their natural_key was absent before step 3a)
-- We identify them by checking that the registry row was created in this run:
WHERE r.created_by = 'GMP_ETL'
  AND r.created_at >= (UNIX_TIMESTAMP() - 10) * 1000;  -- within last 10 seconds


-- ============================================================================
-- STEP 4: Advance the counter by the number of new securities inserted
-- ============================================================================

UPSERT INTO gmp_cis.cis_security_id_counter (counter_id, next_id, updated_at)
SELECT
    1                        AS counter_id,
    next_id + new_count      AS next_id,
    UNIX_TIMESTAMP() * 1000  AS updated_at
FROM gmp_cis.cis_security_id_counter,
     (SELECT COUNT(*) AS new_count
      FROM gmp_cis.stg_gmp_security_with_key stg
      LEFT JOIN gmp_cis.cis_security_id_registry r
          ON stg.natural_key = r.natural_key
      WHERE r.natural_key IS NULL) new_cnt
WHERE counter_id = 1;


-- ============================================================================
-- STEP 5: Clean up temporary staging table
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.stg_gmp_security_with_key;


-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Records by source after merge
SELECT src_system, COUNT(*) AS cnt
FROM gmp_cis.cis_security
WHERE is_active = true
GROUP BY src_system;

-- Confirm no duplicate security_ids
SELECT security_id, COUNT(*) AS cnt
FROM gmp_cis.cis_security
GROUP BY security_id
HAVING cnt > 1;

-- Latest 10 GMP security IDs — confirm all are 12 digits (100_000_000_001+)
SELECT security_id, isin, security_name, src_system, updated_at
FROM gmp_cis.cis_security
WHERE src_system = 'GMP'
ORDER BY updated_at DESC
LIMIT 10;
