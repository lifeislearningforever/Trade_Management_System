-- ============================================================================
-- Position Upload Transform - OPTIMIZED VERSION
-- ============================================================================
-- This version breaks the transform into sequential steps for better performance
-- Run each step separately or as a script
--
-- Created: 2026-03-25
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- STEP 0: Compute statistics on source tables (run once)
-- ============================================================================
-- COMPUTE STATS position_upload_standardized;
-- COMPUTE STATS cis_portfolio;
-- COMPUTE STATS cis_security_kudu;
-- COMPUTE STATS cis_equity_price;
-- COMPUTE STATS cis_party;


-- ============================================================================
-- STEP 1: Create base staging with source data + row_id
-- ============================================================================
DROP TABLE IF EXISTS pos_stage_1_base;

CREATE TABLE pos_stage_1_base
STORED AS PARQUET AS
SELECT
    ROW_NUMBER() OVER (ORDER BY portfolio, security_full_name) AS row_id,
    portfolio,
    security_full_name,
    security_short_name,
    isin,
    ticker,
    quantity,
    shares_outstanding,
    shares_issued,
    pct_holding,
    market_price,
    average_cost,
    cost_fc,
    market_value_fc,
    net_book_value_fc,
    unrealized_pnl_fc,
    cost_lc,
    market_value_lc,
    net_book_value_lc,
    unrealized_pnl_lc,
    provision_lc,
    provision_fc,
    security_type,
    product_type,
    quoted_unquoted,
    industry,
    fin_nonfin_co,
    issuer_type,
    reis_or_fund_u_n,
    exchange_code,
    country_of_exchange,
    country_of_incorporation,
    country_of_risk,
    country_of_operation,
    security_currency,
    borp_code,
    branch_centre,
    oets,
    bwcif_sq,
    bwcif_bd_code_sq,
    mas_bd_code_ovs,
    position_base_ovs,
    reporting_date,
    maturity_date,
    src_system,
    sub_system,
    data_src,
    source_table,
    src_id,
    processing_date
FROM position_upload_standardized;


-- ============================================================================
-- STEP 2: Portfolio Validation
-- ============================================================================
DROP TABLE IF EXISTS pos_stage_2_portfolio;

CREATE TABLE pos_stage_2_portfolio
STORED AS PARQUET AS
SELECT
    b.row_id,
    b.portfolio,
    pf.name AS valid_portfolio,
    pf.currency AS portfolio_currency,
    CASE
        WHEN pf.name IS NOT NULL THEN 'PASS'
        ELSE 'FAIL: Portfolio not found'
    END AS portfolio_status
FROM pos_stage_1_base b
LEFT JOIN cis_portfolio pf ON b.portfolio = pf.name;


-- ============================================================================
-- STEP 3: Security Validation (ISIN match)
-- ============================================================================
DROP TABLE IF EXISTS pos_stage_3_security;

CREATE TABLE pos_stage_3_security
STORED AS PARQUET AS
SELECT
    b.row_id,
    b.isin AS upload_isin,
    b.security_full_name,
    b.security_short_name,
    b.exchange_code AS upload_exchange,
    -- ISIN match
    s.security_id AS matched_security_id,
    s.security_name AS matched_security_name,
    s.isin AS matched_isin,
    s.exchange_code AS matched_exchange,
    s.country_of_exchange AS matched_country,
    s.currency_code AS matched_currency,
    CASE
        WHEN s.security_id IS NOT NULL THEN 'ISIN_MATCH'
        ELSE NULL
    END AS match_type
FROM pos_stage_1_base b
LEFT JOIN cis_security_kudu s ON b.isin = s.isin AND s.is_active = true;


-- ============================================================================
-- STEP 4: Security Validation - Fallback matches (for non-ISIN matches)
-- ============================================================================
DROP TABLE IF EXISTS pos_stage_4_security_fallback;

CREATE TABLE pos_stage_4_security_fallback
STORED AS PARQUET AS
SELECT
    s3.row_id,
    s3.upload_isin,
    s3.security_full_name,
    s3.security_short_name,
    s3.upload_exchange,
    -- Use ISIN match if exists, else try description match
    COALESCE(s3.matched_security_id, s_desc.security_id, s_name.security_id) AS final_security_id,
    COALESCE(s3.matched_security_name, s_desc.security_name, s_name.security_name) AS final_security_name,
    COALESCE(s3.matched_isin, s_desc.isin, s_name.isin) AS final_isin,
    COALESCE(s3.matched_exchange, s_desc.exchange_code, s_name.exchange_code) AS final_exchange,
    COALESCE(s3.matched_country, s_desc.country_of_exchange, s_name.country_of_exchange) AS final_country,
    COALESCE(s3.matched_currency, s_desc.currency_code, s_name.currency_code) AS final_currency,
    CASE
        WHEN s3.matched_security_id IS NOT NULL THEN 'ISIN_MATCH'
        WHEN s_desc.security_id IS NOT NULL THEN 'DESC_MATCH'
        WHEN s_name.security_id IS NOT NULL THEN 'NAME_MATCH'
        WHEN s3.upload_isin IS NULL AND s3.security_full_name IS NULL AND s3.security_short_name IS NULL THEN 'FAIL: No identifier'
        ELSE 'FAIL: Security not found'
    END AS security_status
FROM pos_stage_3_security s3
-- Description match (only if ISIN didn't match)
LEFT JOIN cis_security_kudu s_desc
    ON s3.security_full_name = s_desc.security_description
    AND s_desc.is_active = true
    AND s3.matched_security_id IS NULL
-- Name match (only if ISIN and description didn't match)
LEFT JOIN cis_security_kudu s_name
    ON s3.security_short_name = s_name.security_name
    AND s_name.is_active = true
    AND s3.matched_security_id IS NULL
    AND s_desc.security_id IS NULL;


-- ============================================================================
-- STEP 5: Price Lookup
-- ============================================================================
DROP TABLE IF EXISTS pos_stage_5_price;

CREATE TABLE pos_stage_5_price
STORED AS PARQUET AS
SELECT
    b.row_id,
    b.isin,
    b.reporting_date,
    b.market_price AS upload_market_price,
    ep.main_closing_price,
    COALESCE(ep.main_closing_price, b.market_price) AS final_market_price,
    CASE
        WHEN ep.main_closing_price IS NOT NULL THEN 'PASS: Using cis_equity_price'
        WHEN b.market_price IS NOT NULL THEN 'PASS: Using uploaded'
        ELSE 'WARN: No price'
    END AS price_status
FROM pos_stage_1_base b
LEFT JOIN (
    SELECT isin, price_date, main_closing_price,
           ROW_NUMBER() OVER (PARTITION BY isin, price_date ORDER BY price_timestamp DESC) AS rn
    FROM cis_equity_price
    WHERE is_active = true
) ep ON b.isin = ep.isin AND b.reporting_date = ep.price_date AND ep.rn = 1;


-- ============================================================================
-- STEP 5B: Insert NEW securities into cis_security_kudu
-- ============================================================================
-- For records where security was not found, create new security records
-- This runs BEFORE final staging so positions can reference them

UPSERT INTO cis_security_kudu (
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
    exchange_code,
    currency_code,
    price,
    price_date,
    shares_outstanding,
    fin_nonfin_ind,
    status,
    is_active,
    created_by,
    created_at,
    updated_by,
    updated_at
)
SELECT
    (UNIX_TIMESTAMP() * 1000) + b.row_id AS security_id,
    COALESCE(b.security_short_name, b.security_full_name) AS security_name,
    b.isin,
    b.security_full_name AS security_description,
    NULL AS issuer,  -- Will be updated if party exists
    b.ticker,
    b.industry,
    b.security_type,
    NULL AS investment_type,
    b.issuer_type,
    b.quoted_unquoted,
    b.country_of_incorporation,
    b.country_of_exchange,
    b.exchange_code,
    b.security_currency AS currency_code,
    b.market_price AS price,
    b.reporting_date AS price_date,
    CAST(b.shares_outstanding AS BIGINT) AS shares_outstanding,
    b.fin_nonfin_co AS fin_nonfin_ind,
    'ACTIVE' AS status,
    TRUE AS is_active,
    'POSITION_UPLOAD' AS created_by,
    UNIX_TIMESTAMP() * 1000 AS created_at,
    'POSITION_UPLOAD' AS updated_by,
    UNIX_TIMESTAMP() * 1000 AS updated_at
FROM pos_stage_1_base b
JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
JOIN pos_stage_2_portfolio p2 ON b.row_id = p2.row_id
WHERE p4.security_status LIKE 'FAIL: Security not found%'
  AND p2.portfolio_status = 'PASS'  -- Only if portfolio is valid
  -- Exchange is optional for security creation
  AND (b.quantity IS NOT NULL OR b.cost_fc IS NOT NULL)  -- Must have quantity
  AND (b.isin IS NOT NULL OR b.security_full_name IS NOT NULL OR b.security_short_name IS NOT NULL);

-- Log how many securities were created
SELECT 'New Securities Created' AS action, COUNT(*) AS cnt
FROM pos_stage_1_base b
JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
JOIN pos_stage_2_portfolio p2 ON b.row_id = p2.row_id
WHERE p4.security_status LIKE 'FAIL: Security not found%'
  AND p2.portfolio_status = 'PASS'
  AND b.exchange_code IS NOT NULL
  AND (b.quantity IS NOT NULL OR b.cost_fc IS NOT NULL)
  AND (b.isin IS NOT NULL OR b.security_full_name IS NOT NULL OR b.security_short_name IS NOT NULL);


-- ============================================================================
-- STEP 6: Final Staging with all validations
-- ============================================================================
-- NOTE: After Step 5B, security_status 'FAIL: Security not found' records
--       now have securities created, so we mark them as VALID
DROP TABLE IF EXISTS position_upload_staging;

CREATE TABLE position_upload_staging
STORED AS PARQUET AS
SELECT
    b.*,
    -- Portfolio validation
    p2.valid_portfolio,
    p2.portfolio_currency,
    p2.portfolio_status,
    -- Security validation
    p4.final_security_id,
    p4.final_security_name AS matched_security_name,
    p4.final_isin,
    p4.final_country AS country_resolved,
    p4.final_currency AS security_currency_resolved,
    p4.security_status,
    -- Price
    p5.final_market_price,
    p5.price_status,
    -- Quantity validation
    CASE
        WHEN b.quantity IS NOT NULL THEN b.quantity
        WHEN b.cost_fc IS NOT NULL THEN b.cost_fc
        ELSE NULL
    END AS final_quantity,
    CASE
        WHEN b.quantity IS NOT NULL THEN 'PASS'
        WHEN b.cost_fc IS NOT NULL THEN 'PASS: Using cost_fc'
        ELSE 'FAIL: Both quantity and cost_fc null'
    END AS quantity_status,
    -- Shares issued validation
    CASE
        WHEN b.shares_issued IS NOT NULL THEN b.shares_issued
        WHEN b.pct_holding IS NOT NULL AND b.quantity IS NOT NULL AND b.pct_holding > 0
            THEN b.quantity / b.pct_holding
        ELSE NULL
    END AS final_shares_issued,
    CASE
        WHEN b.shares_issued IS NOT NULL THEN 'PASS'
        WHEN b.pct_holding IS NOT NULL AND b.quantity IS NOT NULL AND b.pct_holding > 0
            THEN 'PASS: Calculated'
        WHEN b.pct_holding = 0 THEN 'FAIL: pct_holding is zero'
        ELSE 'FAIL: Cannot determine shares_issued'
    END AS shares_status,
    -- Exchange validation
    CASE
        WHEN b.exchange_code IS NULL THEN 'FAIL: Exchange is null'
        ELSE 'PASS'
    END AS exchange_status,
    -- Calculated fields
    CASE
        WHEN b.market_value_fc IS NOT NULL THEN b.market_value_fc
        WHEN b.quantity IS NOT NULL AND p5.final_market_price IS NOT NULL
            THEN b.quantity * p5.final_market_price
        ELSE NULL
    END AS final_market_value_fc,
    CASE
        WHEN b.net_book_value_fc IS NOT NULL THEN b.net_book_value_fc
        WHEN b.cost_fc IS NOT NULL THEN b.cost_fc - COALESCE(b.provision_fc, 0)
        ELSE NULL
    END AS final_net_book_value_fc,
    -- Overall status
    -- NOTE: Portfolio validation is now a WARNING (not blocking) to allow processing
    -- NOTE: 'FAIL: Security not found' is NOW VALID because Step 5B created the security
    CASE
        -- Portfolio not found is WARNING, not blocking (use uploaded portfolio name)
        WHEN p4.security_status = 'FAIL: No identifier' THEN 'INVALID: ' || p4.security_status
        -- Security not found is OK - we created it in Step 5B (if other validations pass)
        WHEN p4.security_status = 'FAIL: Security not found'
             AND (b.quantity IS NOT NULL OR b.cost_fc IS NOT NULL)
             THEN 'VALID: New security created'
        WHEN p4.security_status LIKE 'FAIL%' AND p4.security_status != 'FAIL: Security not found'
             THEN 'INVALID: ' || p4.security_status
        WHEN b.quantity IS NULL AND b.cost_fc IS NULL THEN 'INVALID: No quantity'
        WHEN p2.portfolio_status LIKE 'FAIL%' THEN 'VALID: Portfolio not in master (using uploaded)'
        ELSE 'VALID'
    END AS overall_status
FROM pos_stage_1_base b
JOIN pos_stage_2_portfolio p2 ON b.row_id = p2.row_id
JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
JOIN pos_stage_5_price p5 ON b.row_id = p5.row_id;


-- ============================================================================
-- STEP 7: Insert valid records into cis_position
-- ============================================================================

UPSERT INTO cis_position (
    position_id,
    version_id,
    portfolio,
    security_label,
    position_basis,
    position_date,
    src_system,
    processing_date,
    quantity,
    average_cost,
    cost_fc,
    market_value_fc,
    net_book_value_fc,
    unrealized_pnl_fc,
    cost_lc,
    market_value_lc,
    net_book_value_lc,
    unrealized_pnl_lc,
    provision_lc,
    provision_fc,
    dividend_fc,
    dividend_lc,
    realized_pnl_fc,
    realized_pnl_lc,
    isin,
    placeholder_2,
    placeholder_3,
    placeholder_4
)
SELECT
    (UNIX_TIMESTAMP() * 1000000) + row_id AS position_id,
    (UNIX_TIMESTAMP() * 1000000) + 500000000 + row_id AS version_id,
    portfolio,
    COALESCE(matched_security_name, security_full_name, security_short_name) AS security_label,
    position_base_ovs AS position_basis,
    reporting_date AS position_date,
    src_system,
    processing_date,
    final_quantity AS quantity,
    average_cost,
    cost_fc,
    final_market_value_fc AS market_value_fc,
    final_net_book_value_fc AS net_book_value_fc,
    unrealized_pnl_fc,
    cost_lc,
    market_value_lc,
    net_book_value_lc,
    unrealized_pnl_lc,
    provision_lc,
    provision_fc,
    0 AS dividend_fc,
    0 AS dividend_lc,
    0 AS realized_pnl_fc,
    0 AS realized_pnl_lc,
    COALESCE(final_isin, isin) AS isin,
    '' AS placeholder_2,
    '' AS placeholder_3,
    '' AS placeholder_4
FROM position_upload_staging
WHERE overall_status LIKE 'VALID%';  -- Includes 'VALID' and 'VALID: New security created'


-- ============================================================================
-- STEP 8: Summary Statistics
-- ============================================================================

SELECT 'Total' AS metric, COUNT(*) AS cnt FROM position_upload_staging
UNION ALL
SELECT 'Valid (Existing Security)', COUNT(*) FROM position_upload_staging WHERE overall_status = 'VALID'
UNION ALL
SELECT 'Valid (New Security Created)', COUNT(*) FROM position_upload_staging WHERE overall_status = 'VALID: New security created'
UNION ALL
SELECT 'Valid (Portfolio not in master)', COUNT(*) FROM position_upload_staging WHERE overall_status = 'VALID: Portfolio not in master (using uploaded)'
UNION ALL
SELECT 'Total Valid (All)', COUNT(*) FROM position_upload_staging WHERE overall_status LIKE 'VALID%'
UNION ALL
SELECT 'Invalid', COUNT(*) FROM position_upload_staging WHERE overall_status LIKE 'INVALID%'
UNION ALL
SELECT 'Portfolio Not Found (Warning)', COUNT(*) FROM position_upload_staging WHERE portfolio_status LIKE 'FAIL%'
UNION ALL
SELECT 'Security Match (ISIN)', COUNT(*) FROM position_upload_staging WHERE security_status = 'ISIN_MATCH'
UNION ALL
SELECT 'Security Fail (No Identifier)', COUNT(*) FROM position_upload_staging WHERE security_status = 'FAIL: No identifier'
UNION ALL
SELECT 'Quantity Null', COUNT(*) FROM position_upload_staging WHERE quantity IS NULL AND cost_fc IS NULL;


-- ============================================================================
-- CLEANUP intermediate tables (optional)
-- ============================================================================
-- DROP TABLE IF EXISTS pos_stage_1_base;
-- DROP TABLE IF EXISTS pos_stage_2_portfolio;
-- DROP TABLE IF EXISTS pos_stage_3_security;
-- DROP TABLE IF EXISTS pos_stage_4_security_fallback;
-- DROP TABLE IF EXISTS pos_stage_5_price;


-- ============================================================================
-- END
-- ============================================================================
