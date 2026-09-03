-- Diagnose why 6 of 751 Format 1 upload rows FAIL security matching despite
-- a matching security name existing in cis_security.
--
-- Root-cause theory: Format 1's STANDARDIZE_SELECT always sets
-- security_short_name and ticker to NULL, so Tier 1 (the only tier that
-- matches against cis_security.security_name) can never fire for Format 1.
-- The only remaining tiers are ISIN+country (Tier 2) and full-name-vs-
-- security_description (Tiers 4/8) -- note: security_description, NOT
-- security_name. If a security's security_name matches the uploaded
-- "Counter" value but its security_description is blank/different, and the
-- row's ISIN/exchange don't resolve cleanly via Tier 2, Format 1 has no
-- path left to match it.
--
-- Substitute {SRC_ID} / {PROCESSING_DATE} before running.

-- =============================================================================
-- STEP 1: The failing rows themselves (from position_upload_staging, if it
-- still exists from that run) -- shows what the matcher actually saw.
-- =============================================================================
SELECT portfolio, security_full_name, isin, upload_exchange AS exchange_quoted,
       resolved_country, final_isin, security_status, security_match_method,
       overall_status
FROM gmp_cis.position_upload_staging
WHERE src_id = '{SRC_ID}'
  AND processing_date = '{PROCESSING_DATE}'
  AND overall_status NOT LIKE 'VALID%'
ORDER BY portfolio, security_full_name;

-- =============================================================================
-- STEP 2: For one of those failing rows, find the security you believe
-- SHOULD have matched, and compare all 3 fields the tiers check against.
-- =============================================================================
SELECT security_id, security_name, security_description, isin, ticker,
       exchange_code, country_of_exchange, is_active
FROM gmp_cis.cis_security
WHERE UPPER(TRIM(security_name)) LIKE UPPER('%{SECURITY_NAME_FRAGMENT}%')
   OR UPPER(TRIM(security_description)) LIKE UPPER('%{SECURITY_NAME_FRAGMENT}%')
   OR isin = '{ISIN}';

-- =============================================================================
-- STEP 3: Was the exchange_quoted value from the file even mappable to a
-- country at all? If this returns 0 rows, resolved_country is NULL for
-- that row, which knocks out every country-gated tier (2, 3, 4, 5) at once.
-- =============================================================================
SELECT *
FROM gmp_cis.cis_exchange_mapping_lut
WHERE UPPER(TRIM(exchange_name)) = UPPER('{EXCHANGE_QUOTED_VALUE}');

-- =============================================================================
-- STEP 4: Live capture for the confirmed reset-to-0 case (UOB KH PTE LTD /
-- BAKRIE TELECOM + BAKRIELAND DEVT, position_date 2026-03-03, type INT).
--
-- position_upload_staging is DROP+CREATE on every ETL run (like
-- pos_stage_1_base, pos_stage_4_security_fallback, etc.), so it only ever
-- reflects the MOST RECENT run and gets wiped by the next one. Re-trigger
-- this upload's ETL run, then immediately run this query before any other
-- position upload runs on the system.
-- =============================================================================
SELECT portfolio, security_full_name, isin, upload_exchange AS exchange_quoted,
       resolved_country, final_security_id, final_isin,
       security_status, security_match_method, overall_status, quantity_status, final_quantity
FROM gmp_cis.position_upload_staging
WHERE portfolio = 'UOB KH PTE LTD'
  AND security_full_name IN ('BAKRIE TELECOM', 'BAKRIELAND DEVT');
