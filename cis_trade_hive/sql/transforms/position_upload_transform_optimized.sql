-- ============================================================================
-- Position Upload Transform - OPTIMIZED VERSION (STRICT VALIDATION)
-- ============================================================================
-- This version enforces strict validation rules:
--   1. Portfolio MUST exist in cis_portfolio - otherwise FAIL
--   2. Security MUST have at least one identifier (ISIN, full_name, or short_name)
--   3. Exchange MUST NOT be NULL - otherwise FAIL
--   4. Only records passing ALL validations proceed to next step
--
-- Created: 2026-03-25
-- Updated: 2026-04-02 - Strict validation rules per Rule.xlsx
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
FROM gmp_cis.position_upload_standardized;


-- ============================================================================
-- STEP 2: Portfolio Validation (STRICT - MUST MATCH)
-- ============================================================================
-- Rule: Check portfolio against gmp_cis.cis_portfolio.name
--       If fail, entry FAILS (strict validation)
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
        ELSE 'FAIL: Portfolio not found in cis_portfolio'
    END AS portfolio_status
FROM pos_stage_1_base b
LEFT JOIN cis_portfolio pf ON b.portfolio = pf.name;

-- Log portfolio validation results
SELECT 'Portfolio Validation' AS step,
       portfolio_status,
       COUNT(*) AS cnt
FROM pos_stage_2_portfolio
GROUP BY portfolio_status;


-- ============================================================================
-- STEP 3: Security Validation (ISIN match) - Only for records with valid portfolio
-- ============================================================================
-- Rule: First try ISIN match against cis_security.isin
--       Check for multiple ISINs in master data (should fail if duplicate)
--       Only process records that PASSED portfolio validation
DROP TABLE IF EXISTS pos_stage_3_security;

-- First, identify ISINs that have multiple active records in cis_security_kudu
DROP TABLE IF EXISTS pos_stage_3_duplicate_isins;

CREATE TABLE pos_stage_3_duplicate_isins
STORED AS PARQUET AS
SELECT isin, COUNT(*) AS isin_count
FROM cis_security_kudu
WHERE is_active = true
  AND isin IS NOT NULL
  AND TRIM(isin) != ''
GROUP BY isin
HAVING COUNT(*) > 1;

-- Now do security matching with duplicate check
CREATE TABLE pos_stage_3_security
STORED AS PARQUET AS
SELECT
    b.row_id,
    b.isin AS upload_isin,
    b.security_full_name,
    b.security_short_name,
    b.exchange_code AS upload_exchange,
    p2.portfolio_status,
    -- Check for duplicate ISINs in master
    dup.isin_count AS duplicate_isin_count,
    -- ISIN match (only if NOT duplicate)
    CASE WHEN dup.isin IS NULL THEN s.security_id ELSE NULL END AS matched_security_id,
    CASE WHEN dup.isin IS NULL THEN s.security_name ELSE NULL END AS matched_security_name,
    CASE WHEN dup.isin IS NULL THEN s.isin ELSE NULL END AS matched_isin,
    CASE WHEN dup.isin IS NULL THEN s.exchange_code ELSE NULL END AS matched_exchange,
    CASE WHEN dup.isin IS NULL THEN s.country_of_exchange ELSE NULL END AS matched_country,
    CASE WHEN dup.isin IS NULL THEN s.currency_code ELSE NULL END AS matched_currency,
    CASE
        WHEN dup.isin IS NOT NULL THEN 'FAIL: Multiple ISINs found in master'
        WHEN s.security_id IS NOT NULL THEN 'ISIN_MATCH'
        WHEN b.isin IS NULL OR TRIM(b.isin) = '' THEN 'NO_ISIN'
        ELSE 'ISIN_NO_MATCH'
    END AS match_type
FROM pos_stage_1_base b
JOIN pos_stage_2_portfolio p2 ON b.row_id = p2.row_id
-- Check for duplicate ISINs
LEFT JOIN pos_stage_3_duplicate_isins dup ON b.isin = dup.isin
-- Only proceed with records that passed portfolio validation
LEFT JOIN cis_security_kudu s
    ON b.isin = s.isin
    AND s.is_active = true
    AND b.isin IS NOT NULL  -- Only join if ISIN is not null
    AND TRIM(b.isin) != ''  -- And not empty string
WHERE p2.portfolio_status = 'PASS';  -- STRICT: Only process valid portfolios


-- ============================================================================
-- STEP 4: Security Validation - Fallback matches (for non-ISIN matches)
-- ============================================================================
-- Rule: If ISIN fails (or duplicate), check security_full_name against cis_security.security_description
--       If still fails, check security_short_name against security_name
--       If isin, security_full_name and security_short_name are ALL null -> FAIL
--       If Multiple ISINs found -> FAIL
DROP TABLE IF EXISTS pos_stage_4_security_fallback;

CREATE TABLE pos_stage_4_security_fallback
STORED AS PARQUET AS
SELECT
    s3.row_id,
    s3.upload_isin,
    s3.security_full_name,
    s3.security_short_name,
    s3.upload_exchange,
    s3.portfolio_status,
    s3.match_type AS isin_match_type,
    -- Use ISIN match if exists (and not duplicate), else try description match, then name match
    COALESCE(s3.matched_security_id, s_desc.security_id, s_name.security_id) AS final_security_id,
    COALESCE(s3.matched_security_name, s_desc.security_name, s_name.security_name) AS final_security_name,
    COALESCE(s3.matched_isin, s_desc.isin, s_name.isin) AS final_isin,
    COALESCE(s3.matched_exchange, s_desc.exchange_code, s_name.exchange_code) AS final_exchange,
    COALESCE(s3.matched_country, s_desc.country_of_exchange, s_name.country_of_exchange) AS final_country,
    COALESCE(s3.matched_currency, s_desc.currency_code, s_name.currency_code) AS final_currency,
    -- Determine match method
    CASE
        WHEN s3.matched_security_id IS NOT NULL THEN 'ISIN_MATCH'
        WHEN s_desc.security_id IS NOT NULL THEN 'FULLNAME_MATCH'
        WHEN s_name.security_id IS NOT NULL THEN 'SHORTNAME_MATCH'
        ELSE NULL
    END AS match_method,
    -- Security status with all failure cases
    CASE
        -- FAIL: Multiple ISINs found in master data
        WHEN s3.match_type = 'FAIL: Multiple ISINs found in master'
            THEN 'FAIL: Multiple ISINs found'
        -- PASS: ISIN matched
        WHEN s3.matched_security_id IS NOT NULL THEN 'ISIN_MATCH'
        -- PASS: Full name matched (security_description)
        WHEN s_desc.security_id IS NOT NULL THEN 'FULLNAME_MATCH'
        -- PASS: Short name matched (security_name)
        WHEN s_name.security_id IS NOT NULL THEN 'SHORTNAME_MATCH'
        -- FAIL: All identifiers null
        WHEN (s3.upload_isin IS NULL OR TRIM(s3.upload_isin) = '')
             AND (s3.security_full_name IS NULL OR TRIM(s3.security_full_name) = '')
             AND (s3.security_short_name IS NULL OR TRIM(s3.security_short_name) = '')
            THEN 'FAIL: No identifier (isin, security_full_name, security_short_name all null)'
        -- NOT FOUND: No ISIN, fullname and short name no match -> Create new security
        ELSE 'NOT_FOUND: Create new security'
    END AS security_status
FROM pos_stage_3_security s3
-- Description/Fullname match (only if ISIN didn't match or upload had no ISIN, and not duplicate)
LEFT JOIN cis_security_kudu s_desc
    ON s3.security_full_name = s_desc.security_description
    AND s_desc.is_active = true
    AND s3.matched_security_id IS NULL
    AND s3.match_type != 'FAIL: Multiple ISINs found in master'
    AND s3.security_full_name IS NOT NULL
    AND TRIM(s3.security_full_name) != ''
-- Short name match (only if ISIN and description didn't match)
LEFT JOIN cis_security_kudu s_name
    ON s3.security_short_name = s_name.security_name
    AND s_name.is_active = true
    AND s3.matched_security_id IS NULL
    AND s_desc.security_id IS NULL
    AND s3.match_type != 'FAIL: Multiple ISINs found in master'
    AND s3.security_short_name IS NOT NULL
    AND TRIM(s3.security_short_name) != '';

-- Log security validation results
SELECT 'Security Validation' AS step,
       security_status,
       COUNT(*) AS cnt
FROM pos_stage_4_security_fallback
GROUP BY security_status;


-- ============================================================================
-- STEP 5: Price Lookup (only for records that passed security validation)
-- ============================================================================
-- Rule: Using isin, check cis_equity_price.main_closing_price for price_date = reporting_date
--       If not null, use it. Otherwise use uploaded market_price.
DROP TABLE IF EXISTS pos_stage_5_price;

CREATE TABLE pos_stage_5_price
STORED AS PARQUET AS
SELECT
    b.row_id,
    b.isin,
    b.reporting_date,
    b.market_price AS upload_market_price,
    ep.main_closing_price,
    -- Treat price = 0 as NULL (omit zero prices)
    CASE
        WHEN ep.main_closing_price IS NOT NULL AND ep.main_closing_price != 0
            THEN ep.main_closing_price
        WHEN b.market_price IS NOT NULL AND b.market_price != 0
            THEN b.market_price
        ELSE NULL
    END AS final_market_price,
    CASE
        WHEN ep.main_closing_price IS NOT NULL AND ep.main_closing_price != 0
            THEN 'PASS: Using cis_equity_price'
        WHEN b.market_price IS NOT NULL AND b.market_price != 0
            THEN 'PASS: Using uploaded'
        WHEN ep.main_closing_price = 0 OR b.market_price = 0
            THEN 'WARN: Price is zero (omitted)'
        ELSE 'WARN: No price'
    END AS price_status
FROM pos_stage_1_base b
JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
LEFT JOIN (
    SELECT isin, price_date, main_closing_price,
           ROW_NUMBER() OVER (PARTITION BY isin, price_date ORDER BY price_timestamp DESC) AS rn
    FROM cis_equity_price
    WHERE is_active = true
      AND main_closing_price IS NOT NULL
      AND main_closing_price != 0  -- Exclude zero prices from source
) ep ON b.isin = ep.isin AND b.reporting_date = ep.price_date AND ep.rn = 1
-- Only process records that passed security validation (not FAIL status)
WHERE p4.security_status NOT LIKE 'FAIL%';


-- ============================================================================
-- STEP 5B: Insert NEW securities into cis_security_kudu
-- ============================================================================
-- Rule: For records where security was not found but has valid identifiers,
--       AND exchange is NOT NULL, create new security records
-- STRICT: Only create if exchange_code is NOT NULL

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
    NULL AS issuer,
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
WHERE p4.security_status = 'NOT_FOUND: Create new security'
  -- STRICT: Exchange must NOT be null
  AND b.exchange_code IS NOT NULL
  AND TRIM(b.exchange_code) != ''
  -- Must have quantity
  AND (b.quantity IS NOT NULL OR b.cost_fc IS NOT NULL);

-- Log how many securities were created
SELECT 'New Securities Created' AS action, COUNT(*) AS cnt
FROM pos_stage_1_base b
JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
WHERE p4.security_status = 'NOT_FOUND: Create new security'
  AND b.exchange_code IS NOT NULL
  AND TRIM(b.exchange_code) != ''
  AND (b.quantity IS NOT NULL OR b.cost_fc IS NOT NULL);


-- ============================================================================
-- STEP 6: Final Staging with STRICT validations
-- ============================================================================
-- STRICT RULES:
--   1. Portfolio MUST exist -> INVALID if not found
--   2. Security identifiers -> INVALID if all null
--   3. Exchange -> INVALID if null
--   4. Quantity -> INVALID if both quantity and cost_fc are null
DROP TABLE IF EXISTS position_upload_staging;

CREATE TABLE position_upload_staging
STORED AS PARQUET AS
SELECT
    b.*,
    -- Portfolio validation (from records that passed)
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
    -- Exchange validation (STRICT: must not be null)
    CASE
        WHEN b.exchange_code IS NULL OR TRIM(b.exchange_code) = '' THEN 'FAIL: Exchange is null'
        ELSE 'PASS'
    END AS exchange_status,
    -- Calculated fields (treat 0 as NULL for market_value_fc)
    CASE
        WHEN b.market_value_fc IS NOT NULL AND b.market_value_fc != 0
            THEN b.market_value_fc
        WHEN b.quantity IS NOT NULL AND p5.final_market_price IS NOT NULL
            THEN b.quantity * p5.final_market_price
        ELSE NULL
    END AS final_market_value_fc,
    CASE
        WHEN b.net_book_value_fc IS NOT NULL THEN b.net_book_value_fc
        WHEN b.cost_fc IS NOT NULL THEN b.cost_fc - COALESCE(b.provision_fc, 0)
        ELSE NULL
    END AS final_net_book_value_fc,
    -- OVERALL STATUS (STRICT VALIDATION)
    -- Order of checks:
    --   1. Security no identifier -> INVALID
    --   2. Exchange null -> INVALID
    --   3. Quantity null -> INVALID
    --   4. Security not found but exchange valid -> VALID (new security created)
    --   5. All checks pass -> VALID
    CASE
        -- Security: No identifier at all
        WHEN p4.security_status LIKE 'FAIL: No identifier%'
            THEN 'INVALID: No security identifier'
        -- Exchange is null - cannot proceed
        WHEN b.exchange_code IS NULL OR TRIM(b.exchange_code) = ''
            THEN 'INVALID: Exchange is null'
        -- Quantity validation
        WHEN b.quantity IS NULL AND b.cost_fc IS NULL
            THEN 'INVALID: No quantity'
        -- Security not found but we created it (exchange is valid at this point)
        WHEN p4.security_status = 'NOT_FOUND: Create new security'
            THEN 'VALID: New security created'
        -- Security matched (ISIN, description/fullname, or short name)
        WHEN p4.security_status IN ('ISIN_MATCH', 'FULLNAME_MATCH', 'SHORTNAME_MATCH', 'DESC_MATCH', 'NAME_MATCH')
            THEN 'VALID'
        -- Any other security failure
        WHEN p4.security_status LIKE 'FAIL%'
            THEN 'INVALID: ' || p4.security_status
        -- Default valid
        ELSE 'VALID'
    END AS overall_status
FROM pos_stage_1_base b
-- INNER JOIN: Only include records that passed portfolio validation
JOIN pos_stage_2_portfolio p2 ON b.row_id = p2.row_id AND p2.portfolio_status = 'PASS'
JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
LEFT JOIN pos_stage_5_price p5 ON b.row_id = p5.row_id;


-- ============================================================================
-- STEP 6B: Create table for FAILED records (for reporting/review)
-- ============================================================================
DROP TABLE IF EXISTS position_upload_failed;

CREATE TABLE position_upload_failed
STORED AS PARQUET AS
SELECT
    b.*,
    -- Failed portfolio records
    CASE
        WHEN p2.portfolio_status LIKE 'FAIL%' THEN p2.portfolio_status
        ELSE NULL
    END AS portfolio_fail_reason,
    -- Failed security records (from base, not stage 4 which only has valid portfolios)
    CASE
        WHEN (b.isin IS NULL OR TRIM(b.isin) = '')
             AND (b.security_full_name IS NULL OR TRIM(b.security_full_name) = '')
             AND (b.security_short_name IS NULL OR TRIM(b.security_short_name) = '')
            THEN 'FAIL: No security identifier'
        ELSE NULL
    END AS security_fail_reason,
    -- Exchange validation
    CASE
        WHEN b.exchange_code IS NULL OR TRIM(b.exchange_code) = ''
            THEN 'FAIL: Exchange is null'
        ELSE NULL
    END AS exchange_fail_reason,
    -- Quantity validation
    CASE
        WHEN b.quantity IS NULL AND b.cost_fc IS NULL
            THEN 'FAIL: No quantity'
        ELSE NULL
    END AS quantity_fail_reason,
    -- Overall failure reason
    CASE
        WHEN p2.portfolio_status LIKE 'FAIL%' THEN 'PORTFOLIO_NOT_FOUND'
        WHEN (b.isin IS NULL OR TRIM(b.isin) = '')
             AND (b.security_full_name IS NULL OR TRIM(b.security_full_name) = '')
             AND (b.security_short_name IS NULL OR TRIM(b.security_short_name) = '')
            THEN 'NO_SECURITY_IDENTIFIER'
        WHEN b.exchange_code IS NULL OR TRIM(b.exchange_code) = ''
            THEN 'EXCHANGE_NULL'
        WHEN b.quantity IS NULL AND b.cost_fc IS NULL
            THEN 'NO_QUANTITY'
        ELSE 'OTHER'
    END AS fail_category
FROM pos_stage_1_base b
LEFT JOIN pos_stage_2_portfolio p2 ON b.row_id = p2.row_id
WHERE
    -- Portfolio failed
    p2.portfolio_status LIKE 'FAIL%'
    -- OR no security identifier
    OR ((b.isin IS NULL OR TRIM(b.isin) = '')
        AND (b.security_full_name IS NULL OR TRIM(b.security_full_name) = '')
        AND (b.security_short_name IS NULL OR TRIM(b.security_short_name) = ''))
    -- OR exchange null
    OR (b.exchange_code IS NULL OR TRIM(b.exchange_code) = '')
    -- OR no quantity
    OR (b.quantity IS NULL AND b.cost_fc IS NULL);

-- Log failed records summary
SELECT 'Failed Records by Category' AS report, fail_category, COUNT(*) AS cnt
FROM position_upload_failed
GROUP BY fail_category
ORDER BY cnt DESC;


-- ============================================================================
-- STEP 7: Insert valid records into cis_position
-- ============================================================================
-- Only records with overall_status = 'VALID' or 'VALID: New security created'

-- Note: uncall_fc/lc, pipeline_fc/lc are not present in the upload source file.
--       Defaulting to 0. position_type defaults to 'LONG'.
--       If future upload files include these columns, map them here.

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
    average_cost_fc,
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
    average_cost_lc,
    source_table,
    processing_timestamp,
    uncall_fc,
    uncall_lc,
    pipeline_fc,
    pipeline_lc,
    position_type
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
    CAST(final_quantity          AS DECIMAL(30,8)) AS quantity,
    CAST(average_cost            AS DECIMAL(30,8)) AS average_cost_fc,
    CAST(cost_fc                 AS DECIMAL(30,8)) AS cost_fc,
    CAST(final_market_value_fc   AS DECIMAL(30,8)) AS market_value_fc,
    CAST(final_net_book_value_fc AS DECIMAL(30,8)) AS net_book_value_fc,
    CAST(unrealized_pnl_fc       AS DECIMAL(30,8)) AS unrealized_pnl_fc,
    CAST(cost_lc                 AS DECIMAL(30,8)) AS cost_lc,
    CAST(market_value_lc         AS DECIMAL(30,8)) AS market_value_lc,
    CAST(net_book_value_lc       AS DECIMAL(30,8)) AS net_book_value_lc,
    CAST(unrealized_pnl_lc       AS DECIMAL(30,8)) AS unrealized_pnl_lc,
    CAST(provision_lc            AS DECIMAL(30,8)) AS provision_lc,
    CAST(provision_fc            AS DECIMAL(30,8)) AS provision_fc,
    CAST(0                       AS DECIMAL(30,8)) AS dividend_fc,
    CAST(0                       AS DECIMAL(30,8)) AS dividend_lc,
    CAST(0                       AS DECIMAL(30,8)) AS realized_pnl_fc,
    CAST(0                       AS DECIMAL(30,8)) AS realized_pnl_lc,
    COALESCE(final_isin, isin)                     AS isin,
    CAST(0                       AS DECIMAL(30,8)) AS average_cost_lc,
    source_table                                   AS source_table,
    from_unixtime(unix_timestamp(), 'yyyy-MM-dd HH:mm:ss') AS processing_timestamp,
    CAST(0                       AS DECIMAL(30,8)) AS uncall_fc,
    CAST(0                       AS DECIMAL(30,8)) AS uncall_lc,
    CAST(0                       AS DECIMAL(30,8)) AS pipeline_fc,
    CAST(0                       AS DECIMAL(30,8)) AS pipeline_lc,
    'LONG'                                         AS position_type
FROM position_upload_staging
WHERE overall_status LIKE 'VALID%';


-- ============================================================================
-- STEP 7B: Write Upload Report to Hive external table (ALL records - Pass + Fail)
-- ============================================================================
-- Writes into gmp_cis.position_upload_report (partitioned by src_id, processing_date).
-- One row per uploaded row. Extra columns: row_status, fail_reason, step results.
-- Django CSV download reads directly from this table.
--
-- Report columns: all original upload columns + row_status (PASS/FAIL) + fail_reason
-- ============================================================================
INSERT INTO TABLE gmp_cis.position_upload_report
PARTITION (src_id, processing_date)
-- VALID records
SELECT
    b.portfolio,
    COALESCE(b.security_full_name, b.security_short_name, b.isin) AS security_full_name,
    b.security_short_name,
    b.isin,
    b.ticker,
    CAST(b.quantity AS STRING),
    CAST(b.shares_outstanding AS STRING),
    CAST(b.shares_issued AS STRING),
    CAST(b.pct_holding AS STRING),
    CAST(b.market_price AS STRING),
    CAST(b.average_cost AS STRING),
    CAST(b.cost_fc AS STRING),
    CAST(b.market_value_fc AS STRING),
    CAST(b.net_book_value_fc AS STRING),
    CAST(b.unrealized_pnl_fc AS STRING),
    CAST(b.provision_fc AS STRING),
    CAST(b.cost_lc AS STRING),
    CAST(b.market_value_lc AS STRING),
    CAST(b.net_book_value_lc AS STRING),
    CAST(b.unrealized_pnl_lc AS STRING),
    CAST(b.provision_lc AS STRING),
    b.security_type,
    b.product_type,
    b.quoted_unquoted,
    b.industry,
    b.fin_nonfin_co,
    b.issuer_type,
    b.reis_or_fund_u_n                  AS reits_or_fund_y_n,
    b.exchange_code,
    b.country_of_exchange,
    b.country_of_incorporation,
    b.country_of_risk,
    b.country_of_operation,
    b.security_currency,
    b.borp_code                         AS corp_code,
    b.branch_centre                     AS branch_code,
    b.oets                              AS cost_centre,
    b.bwcif_sq                          AS cels,
    b.bwcif_bd_code_sq                  AS bwcif_sg,
    b.mas_bd_code_ovs                   AS bwcif_ovs,
    NULL                                AS mas_6d_code_sg,
    NULL                                AS mas_6d_code_ovs,
    b.position_base_ovs                 AS position_basis,
    b.reporting_date,
    b.maturity_date,
    b.src_system,
    b.source_table,
    -- Validation result columns
    'PASS'                              AS row_status,
    CASE
        WHEN s.overall_status = 'VALID: New security created'
            THEN 'New security created. ' || COALESCE(s.price_status, '')
        WHEN s.price_status LIKE 'WARN%'
            THEN s.price_status
        ELSE NULL
    END                                 AS fail_reason,
    s.portfolio_status,
    s.security_status,
    s.price_status,
    s.quantity_status,
    s.exchange_status,
    CAST(s.final_security_id AS STRING) AS matched_security_id,
    s.matched_security_name,
    -- partition columns last
    b.src_id,
    b.processing_date
FROM pos_stage_1_base b
JOIN position_upload_staging s ON b.row_id = s.row_id
WHERE s.overall_status LIKE 'VALID%'

UNION ALL

-- INVALID records (passed portfolio but failed other validations)
SELECT
    b.portfolio,
    COALESCE(b.security_full_name, b.security_short_name, b.isin),
    b.security_short_name,
    b.isin,
    b.ticker,
    CAST(b.quantity AS STRING),
    CAST(b.shares_outstanding AS STRING),
    CAST(b.shares_issued AS STRING),
    CAST(b.pct_holding AS STRING),
    CAST(b.market_price AS STRING),
    CAST(b.average_cost AS STRING),
    CAST(b.cost_fc AS STRING),
    CAST(b.market_value_fc AS STRING),
    CAST(b.net_book_value_fc AS STRING),
    CAST(b.unrealized_pnl_fc AS STRING),
    CAST(b.provision_fc AS STRING),
    CAST(b.cost_lc AS STRING),
    CAST(b.market_value_lc AS STRING),
    CAST(b.net_book_value_lc AS STRING),
    CAST(b.unrealized_pnl_lc AS STRING),
    CAST(b.provision_lc AS STRING),
    b.security_type, b.product_type, b.quoted_unquoted,
    b.industry, b.fin_nonfin_co, b.issuer_type, b.reis_or_fund_u_n,
    b.exchange_code, b.country_of_exchange, b.country_of_incorporation,
    b.country_of_risk, b.country_of_operation, b.security_currency,
    b.borp_code, b.branch_centre, b.oets, b.bwcif_sq,
    b.bwcif_bd_code_sq, b.mas_bd_code_ovs, NULL, NULL,
    b.position_base_ovs, b.reporting_date, b.maturity_date,
    b.src_system, b.source_table,
    'FAIL'                              AS row_status,
    s.overall_status                    AS fail_reason,
    s.portfolio_status,
    s.security_status,
    s.price_status,
    s.quantity_status,
    s.exchange_status,
    NULL                                AS matched_security_id,
    NULL                                AS matched_security_name,
    b.src_id,
    b.processing_date
FROM pos_stage_1_base b
JOIN position_upload_staging s ON b.row_id = s.row_id
WHERE s.overall_status LIKE 'INVALID%'

UNION ALL

-- FAIL: Portfolio not found (never reached staging)
SELECT
    b.portfolio,
    COALESCE(b.security_full_name, b.security_short_name, b.isin),
    b.security_short_name, b.isin, b.ticker,
    CAST(b.quantity AS STRING), CAST(b.shares_outstanding AS STRING),
    CAST(b.shares_issued AS STRING), CAST(b.pct_holding AS STRING),
    CAST(b.market_price AS STRING), CAST(b.average_cost AS STRING),
    CAST(b.cost_fc AS STRING), CAST(b.market_value_fc AS STRING),
    CAST(b.net_book_value_fc AS STRING), CAST(b.unrealized_pnl_fc AS STRING),
    CAST(b.provision_fc AS STRING), CAST(b.cost_lc AS STRING),
    CAST(b.market_value_lc AS STRING), CAST(b.net_book_value_lc AS STRING),
    CAST(b.unrealized_pnl_lc AS STRING), CAST(b.provision_lc AS STRING),
    b.security_type, b.product_type, b.quoted_unquoted,
    b.industry, b.fin_nonfin_co, b.issuer_type, b.reis_or_fund_u_n,
    b.exchange_code, b.country_of_exchange, b.country_of_incorporation,
    b.country_of_risk, b.country_of_operation, b.security_currency,
    b.borp_code, b.branch_centre, b.oets, b.bwcif_sq,
    b.bwcif_bd_code_sq, b.mas_bd_code_ovs, NULL, NULL,
    b.position_base_ovs, b.reporting_date, b.maturity_date,
    b.src_system, b.source_table,
    'FAIL'                                              AS row_status,
    'Step 1: Portfolio not found in cis_portfolio'      AS fail_reason,
    p2.portfolio_status,
    NULL, NULL, NULL, NULL, NULL, NULL,
    b.src_id,
    b.processing_date
FROM pos_stage_1_base b
JOIN pos_stage_2_portfolio p2 ON b.row_id = p2.row_id
WHERE p2.portfolio_status LIKE 'FAIL%';

-- Repair partitions so Impala can see new data
INVALIDATE METADATA gmp_cis.position_upload_report;

-- Report summary
SELECT 'REPORT SUMMARY' AS info;
SELECT row_status, COUNT(*) AS cnt
FROM gmp_cis.position_upload_report
WHERE processing_date = '${processing_date}'
GROUP BY row_status;

SELECT 'FAILED ROWS BY REASON' AS info;
SELECT fail_reason, COUNT(*) AS cnt
FROM gmp_cis.position_upload_report
WHERE processing_date = '${processing_date}'
  AND row_status = 'FAIL'
GROUP BY fail_reason
ORDER BY cnt DESC
ORDER BY cnt DESC;


-- ============================================================================
-- STEP 8: Summary Statistics (STRICT VALIDATION)
-- ============================================================================

SELECT '=== POSITION UPLOAD SUMMARY (STRICT VALIDATION) ===' AS report, '' AS status, 0 AS cnt
UNION ALL
SELECT '---' AS report, '---' AS status, 0 AS cnt
UNION ALL
SELECT 'Total Records in Upload' AS report, '', COUNT(*) FROM pos_stage_1_base
UNION ALL
SELECT '---' AS report, '---' AS status, 0 AS cnt
UNION ALL
SELECT 'STEP 1: Portfolio Validation' AS report, '', 0
UNION ALL
SELECT '  Portfolios Matched', 'PASS', COUNT(*) FROM pos_stage_2_portfolio WHERE portfolio_status = 'PASS'
UNION ALL
SELECT '  Portfolios NOT Found', 'FAIL', COUNT(*) FROM pos_stage_2_portfolio WHERE portfolio_status LIKE 'FAIL%'
UNION ALL
SELECT '---' AS report, '---' AS status, 0 AS cnt
UNION ALL
SELECT 'STEP 2: Security Validation (after portfolio filter)' AS report, '', 0
UNION ALL
SELECT '  ISIN Match', 'ISIN_MATCH', COUNT(*) FROM pos_stage_4_security_fallback WHERE security_status = 'ISIN_MATCH'
UNION ALL
SELECT '  Description Match', 'DESC_MATCH', COUNT(*) FROM pos_stage_4_security_fallback WHERE security_status = 'DESC_MATCH'
UNION ALL
SELECT '  Name Match', 'NAME_MATCH', COUNT(*) FROM pos_stage_4_security_fallback WHERE security_status = 'NAME_MATCH'
UNION ALL
SELECT '  New Security Created', 'NOT_FOUND', COUNT(*) FROM pos_stage_4_security_fallback WHERE security_status = 'NOT_FOUND: Create new security'
UNION ALL
SELECT '  No Identifier (FAIL)', 'FAIL', COUNT(*) FROM pos_stage_4_security_fallback WHERE security_status LIKE 'FAIL: No identifier%'
UNION ALL
SELECT '---' AS report, '---' AS status, 0 AS cnt
UNION ALL
SELECT 'FINAL RESULTS' AS report, '', 0
UNION ALL
SELECT '  Valid Records Inserted', 'VALID', COUNT(*) FROM position_upload_staging WHERE overall_status LIKE 'VALID%'
UNION ALL
SELECT '  Invalid Records', 'INVALID', COUNT(*) FROM position_upload_staging WHERE overall_status LIKE 'INVALID%'
UNION ALL
SELECT '---' AS report, '---' AS status, 0 AS cnt
UNION ALL
SELECT 'FAILED RECORDS BY CATEGORY' AS report, '', 0
UNION ALL
SELECT '  Portfolio Not Found', 'PORTFOLIO', COALESCE((SELECT COUNT(*) FROM position_upload_failed WHERE fail_category = 'PORTFOLIO_NOT_FOUND'), 0)
UNION ALL
SELECT '  No Security Identifier', 'SECURITY', COALESCE((SELECT COUNT(*) FROM position_upload_failed WHERE fail_category = 'NO_SECURITY_IDENTIFIER'), 0)
UNION ALL
SELECT '  Exchange Null', 'EXCHANGE', COALESCE((SELECT COUNT(*) FROM position_upload_failed WHERE fail_category = 'EXCHANGE_NULL'), 0)
UNION ALL
SELECT '  No Quantity', 'QUANTITY', COALESCE((SELECT COUNT(*) FROM position_upload_failed WHERE fail_category = 'NO_QUANTITY'), 0);


-- ============================================================================
-- CLEANUP intermediate tables (optional - keep for debugging)
-- ============================================================================
-- DROP TABLE IF EXISTS pos_stage_1_base;
-- DROP TABLE IF EXISTS pos_stage_2_portfolio;
-- DROP TABLE IF EXISTS pos_stage_3_security;
-- DROP TABLE IF EXISTS pos_stage_4_security_fallback;
-- DROP TABLE IF EXISTS pos_stage_5_price;


-- ============================================================================
-- END
-- ============================================================================
