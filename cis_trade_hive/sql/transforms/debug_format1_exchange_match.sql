-- ============================================================================
-- Debug: Format 1 exchange match for GB0005405286
-- Run in Impala/Hue against gmp_cis database
-- Replace '20260302' with your actual processing_date
-- Replace 'cis_user_sta_adhoc_position_1' with your actual src_id
-- ============================================================================

-- STEP 1: What does the raw source table have for this ISIN?
-- Check exchange_quoted values coming from the uploaded file
SELECT
    src_id,
    processing_date,
    isin_code,
    exchange_quoted,
    counter,
    portfolio,
    quantity_today
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE isin_code = 'GB0005405286'
ORDER BY processing_date DESC
LIMIT 20;

-- ============================================================================

-- STEP 2: What does pos_stage_1_base have after standardize?
-- Check exchange and country_of_exchange after LUT join
SELECT
    row_id,
    isin,
    `exchange`,
    country_of_exchange,
    security_full_name,
    portfolio
FROM pos_stage_1_base
WHERE isin = 'GB0005405286';

-- ============================================================================

-- STEP 3: What securities exist in cis_security for this ISIN?
SELECT
    security_id,
    security_name,
    isin,
    exchange_code,
    country_of_exchange,
    currency_code,
    src_system,
    is_active
FROM gmp_cis.cis_security
WHERE isin = 'GB0005405286'
  AND is_active = true;

-- ============================================================================

-- STEP 4: The full exchange match logic — what does cnt_isin_exchange compute?
-- This mirrors Step 3 exactly for this ISIN
SELECT
    b.row_id,
    b.isin                                          AS upload_isin,
    b.`exchange`                                    AS upload_exchange,
    b.country_of_exchange                           AS upload_country_of_exchange,
    s.security_id,
    s.security_name,
    s.exchange_code                                 AS sec_exchange_code,
    s.country_of_exchange                           AS sec_country_of_exchange,
    -- Condition 1: full exchange vs s.country_of_exchange
    (UPPER(TRIM(b.`exchange`)) = UPPER(TRIM(COALESCE(s.country_of_exchange, ''))))
                                                    AS cond1_exchange_vs_coe,
    -- Condition 2: full exchange vs s.exchange_code
    (UPPER(TRIM(b.`exchange`)) = UPPER(TRIM(COALESCE(s.exchange_code, ''))))
                                                    AS cond2_exchange_vs_ec,
    -- Condition 3: first token of exchange vs s.country_of_exchange
    (UPPER(REGEXP_EXTRACT(TRIM(b.`exchange`), '^(\\S+)', 1)) = UPPER(TRIM(COALESCE(s.country_of_exchange, ''))))
                                                    AS cond3_token_vs_coe,
    -- Condition 4: first token of exchange vs s.exchange_code
    (UPPER(REGEXP_EXTRACT(TRIM(b.`exchange`), '^(\\S+)', 1)) = UPPER(TRIM(COALESCE(s.exchange_code, ''))))
                                                    AS cond4_token_vs_ec,
    -- Condition 5: LUT country_of_exchange vs s.country_of_exchange
    (b.country_of_exchange IS NOT NULL AND TRIM(b.country_of_exchange) != ''
     AND UPPER(TRIM(b.country_of_exchange)) = UPPER(TRIM(COALESCE(s.country_of_exchange, ''))))
                                                    AS cond5_lut_vs_coe,
    -- Condition 6: LUT country_of_exchange vs s.exchange_code
    (b.country_of_exchange IS NOT NULL AND TRIM(b.country_of_exchange) != ''
     AND UPPER(TRIM(b.country_of_exchange)) = UPPER(TRIM(COALESCE(s.exchange_code, ''))))
                                                    AS cond6_lut_vs_ec,
    -- Combined is_exchange_match
    CASE
        WHEN (
            UPPER(TRIM(b.`exchange`)) = UPPER(TRIM(COALESCE(s.country_of_exchange, '')))
            OR UPPER(TRIM(b.`exchange`)) = UPPER(TRIM(COALESCE(s.exchange_code, '')))
            OR UPPER(REGEXP_EXTRACT(TRIM(b.`exchange`), '^(\\S+)', 1)) = UPPER(TRIM(COALESCE(s.country_of_exchange, '')))
            OR UPPER(REGEXP_EXTRACT(TRIM(b.`exchange`), '^(\\S+)', 1)) = UPPER(TRIM(COALESCE(s.exchange_code, '')))
            OR (b.country_of_exchange IS NOT NULL AND TRIM(b.country_of_exchange) != ''
                AND UPPER(TRIM(b.country_of_exchange)) = UPPER(TRIM(COALESCE(s.country_of_exchange, ''))))
            OR (b.country_of_exchange IS NOT NULL AND TRIM(b.country_of_exchange) != ''
                AND UPPER(TRIM(b.country_of_exchange)) = UPPER(TRIM(COALESCE(s.exchange_code, ''))))
        ) THEN 1 ELSE 0
    END                                             AS is_exchange_match,
    -- Window counts
    COUNT(s.security_id) OVER (PARTITION BY b.row_id)
                                                    AS cnt_isin_only,
    SUM(CASE
        WHEN (
            UPPER(TRIM(b.`exchange`)) = UPPER(TRIM(COALESCE(s.country_of_exchange, '')))
            OR UPPER(TRIM(b.`exchange`)) = UPPER(TRIM(COALESCE(s.exchange_code, '')))
            OR UPPER(REGEXP_EXTRACT(TRIM(b.`exchange`), '^(\\S+)', 1)) = UPPER(TRIM(COALESCE(s.country_of_exchange, '')))
            OR UPPER(REGEXP_EXTRACT(TRIM(b.`exchange`), '^(\\S+)', 1)) = UPPER(TRIM(COALESCE(s.exchange_code, '')))
            OR (b.country_of_exchange IS NOT NULL AND TRIM(b.country_of_exchange) != ''
                AND UPPER(TRIM(b.country_of_exchange)) = UPPER(TRIM(COALESCE(s.country_of_exchange, ''))))
            OR (b.country_of_exchange IS NOT NULL AND TRIM(b.country_of_exchange) != ''
                AND UPPER(TRIM(b.country_of_exchange)) = UPPER(TRIM(COALESCE(s.exchange_code, ''))))
        ) THEN 1 ELSE 0
    END) OVER (PARTITION BY b.row_id)              AS cnt_isin_exchange
FROM pos_stage_1_base b
JOIN gmp_cis.cis_security s
    ON s.is_active = true
    AND b.isin = s.isin
WHERE b.isin = 'GB0005405286'
ORDER BY b.row_id, s.security_id;

-- ============================================================================

-- STEP 5: Check the LUT table — does exchange_quoted match exchange_name?
-- Replace 'HKSE' / 'LSE' with the actual exchange_quoted values from Step 1
SELECT
    exchange_name,
    country_name
FROM gmp_cis.cis_exchange_mapping_lut
WHERE UPPER(exchange_name) IN ('HKSE', 'LSE', 'HK', 'GB', 'HK HKSE', 'GB LSE')
ORDER BY exchange_name;

-- ============================================================================

-- STEP 6: What does pos_stage_3_security show for this ISIN?
SELECT
    row_id,
    upload_isin,
    upload_exchange,
    matched_security_id,
    matched_security_name,
    match_type
FROM pos_stage_3_security
WHERE upload_isin = 'GB0005405286';
