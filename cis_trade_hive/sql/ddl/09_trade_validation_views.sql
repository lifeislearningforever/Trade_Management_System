-- ============================================================================
-- Trade Validation Views and Helper Queries - Kudu/Impala
-- ============================================================================
-- Description: Views and queries for validating trade data against
--              Portfolio, Security, and Counterparty master tables
--
-- Database: gmp_cis
-- Created: 2026-01-13
-- Version: 1.0
--
-- Validation Rules:
--   1. Portfolio must exist in cis_portfolio (by name)
--   2. Security must exist in cis_security (by security_name)
--   3. Counterparty must exist in cis_counterparty_kudu (by counterparty_short_name)
--   4. All referenced entities must be active (is_active = true)
--   5. All referenced entities must be SETTLED status for trading
--
-- Foreign Key References:
--   cis_trade.portfolio_short_name -> cis_portfolio.name
--   cis_trade.security_label       -> cis_security.security_name
--   cis_trade.counterparty         -> cis_counterparty_kudu.counterparty_short_name
--   cis_trade.broker_name          -> cis_broker_lookup.broker_name
--
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- VIEW 1: Valid Portfolios for Trade Entry
-- ============================================================================
-- Only SETTLED and active portfolios can be used in trades
-- ============================================================================

DROP VIEW IF EXISTS v_valid_portfolios_for_trade;

CREATE VIEW v_valid_portfolios_for_trade AS
SELECT
    name AS portfolio_short_name,
    name AS portfolio_full_name,  -- Using name as both since they're same in current schema
    currency,
    manager,
    status,
    src_system
FROM cis_portfolio
WHERE status = 'SETTLED'
  AND is_active = true;

-- ============================================================================
-- VIEW 2: Valid Securities for Trade Entry
-- ============================================================================
-- Only ACTIVE securities can be traded
-- ============================================================================

DROP VIEW IF EXISTS v_valid_securities_for_trade;

CREATE VIEW v_valid_securities_for_trade AS
SELECT
    security_name AS security_label,
    security_name AS security_full_name,
    security_type,
    isin,
    ticker,
    currency_code,
    price,
    issuer,
    status
FROM cis_security
WHERE status IN ('ACTIVE', 'APPROVED')
  AND is_active = true;

-- ============================================================================
-- VIEW 3: Valid Counterparties for Trade Entry
-- ============================================================================
-- Only active counterparties can be used in trades
-- ============================================================================

DROP VIEW IF EXISTS v_valid_counterparties_for_trade;

CREATE VIEW v_valid_counterparties_for_trade AS
SELECT
    counterparty_short_name,
    counterparty_full_name,
    country,
    is_broker,
    is_custodian,
    is_issuer,
    is_bank
FROM cis_counterparty_kudu
WHERE is_active = true
  AND is_deleted = false;

-- ============================================================================
-- VIEW 4: Valid Brokers for Trade Entry
-- ============================================================================
-- Combines broker lookup with counterparty brokers
-- ============================================================================

DROP VIEW IF EXISTS v_valid_brokers_for_trade;

CREATE VIEW v_valid_brokers_for_trade AS
-- From lookup table
SELECT
    broker_code,
    broker_name,
    broker_type,
    country,
    'LOOKUP' AS source
FROM cis_broker_lookup
WHERE is_active = true

UNION ALL

-- From counterparty table (brokers)
SELECT
    counterparty_short_name AS broker_code,
    counterparty_full_name AS broker_name,
    'COUNTERPARTY' AS broker_type,
    country,
    'COUNTERPARTY' AS source
FROM cis_counterparty_kudu
WHERE is_broker = true
  AND is_active = true
  AND is_deleted = false;

-- ============================================================================
-- VIEW 5: Trade Validation Summary
-- ============================================================================
-- Shows trades with validation status for all references
-- ============================================================================

DROP VIEW IF EXISTS v_trade_validation_status;

CREATE VIEW v_trade_validation_status AS
SELECT
    t.trade_id,
    t.deal_number,
    t.trade_type,
    t.portfolio_short_name,
    t.security_label,
    t.counterparty,
    t.status AS trade_status,

    -- Portfolio Validation
    CASE WHEN p.name IS NOT NULL THEN 'VALID' ELSE 'INVALID' END AS portfolio_valid,
    p.status AS portfolio_status,

    -- Security Validation
    CASE WHEN s.security_name IS NOT NULL THEN 'VALID' ELSE 'INVALID' END AS security_valid,
    s.status AS security_status,

    -- Counterparty Validation (only if counterparty is specified)
    CASE
        WHEN t.counterparty IS NULL OR t.counterparty = '' THEN 'N/A'
        WHEN c.counterparty_short_name IS NOT NULL THEN 'VALID'
        ELSE 'INVALID'
    END AS counterparty_valid,

    -- Overall Validation
    CASE
        WHEN p.name IS NOT NULL
         AND s.security_name IS NOT NULL
         AND (t.counterparty IS NULL OR t.counterparty = '' OR c.counterparty_short_name IS NOT NULL)
        THEN 'VALID'
        ELSE 'INVALID'
    END AS overall_valid

FROM cis_trade t
LEFT JOIN cis_portfolio p
    ON t.portfolio_short_name = p.name
    AND p.status = 'SETTLED'
    AND p.is_active = true
LEFT JOIN cis_security s
    ON t.security_label = s.security_name
    AND s.status IN ('ACTIVE', 'APPROVED')
    AND s.is_active = true
LEFT JOIN cis_counterparty_kudu c
    ON t.counterparty = c.counterparty_short_name
    AND c.is_active = true
    AND c.is_deleted = false;

-- ============================================================================
-- VALIDATION QUERIES (for application use)
-- ============================================================================

-- ============================================================================
-- Query 1: Check if Portfolio exists and is valid for trading
-- ============================================================================
-- Parameters: :portfolio_name
-- Returns: 1 if valid, 0 if invalid

/*
SELECT
    CASE
        WHEN COUNT(*) > 0 THEN 1
        ELSE 0
    END AS is_valid
FROM cis_portfolio
WHERE name = :portfolio_name
  AND status = 'SETTLED'
  AND is_active = true;
*/

-- ============================================================================
-- Query 2: Check if Security exists and is valid for trading
-- ============================================================================
-- Parameters: :security_name
-- Returns: 1 if valid, 0 if invalid

/*
SELECT
    CASE
        WHEN COUNT(*) > 0 THEN 1
        ELSE 0
    END AS is_valid
FROM cis_security
WHERE security_name = :security_name
  AND status IN ('ACTIVE', 'APPROVED')
  AND is_active = true;
*/

-- ============================================================================
-- Query 3: Check if Counterparty exists and is valid
-- ============================================================================
-- Parameters: :counterparty_name
-- Returns: 1 if valid, 0 if invalid

/*
SELECT
    CASE
        WHEN COUNT(*) > 0 THEN 1
        ELSE 0
    END AS is_valid
FROM cis_counterparty_kudu
WHERE counterparty_short_name = :counterparty_name
  AND is_active = true
  AND is_deleted = false;
*/

-- ============================================================================
-- Query 4: Get Portfolio details for auto-population
-- ============================================================================
-- Parameters: :portfolio_name
-- Returns: Portfolio details to populate trade form

/*
SELECT
    name AS portfolio_short_name,
    name AS portfolio_full_name,
    currency,
    manager,
    cash_balance
FROM cis_portfolio
WHERE name = :portfolio_name
  AND status = 'SETTLED'
  AND is_active = true;
*/

-- ============================================================================
-- Query 5: Get Security details for auto-population
-- ============================================================================
-- Parameters: :security_name
-- Returns: Security details to populate trade form

/*
SELECT
    security_name AS security_label,
    security_name AS security_full_name,
    security_type,
    isin,
    ticker,
    currency_code,
    price AS current_price,
    issuer
FROM cis_security
WHERE security_name = :security_name
  AND status IN ('ACTIVE', 'APPROVED')
  AND is_active = true;
*/

-- ============================================================================
-- Query 6: Get Counterparty details for auto-population
-- ============================================================================
-- Parameters: :counterparty_name
-- Returns: Counterparty details

/*
SELECT
    counterparty_short_name,
    counterparty_full_name,
    country,
    is_broker,
    is_custodian
FROM cis_counterparty_kudu
WHERE counterparty_short_name = :counterparty_name
  AND is_active = true
  AND is_deleted = false;
*/

-- ============================================================================
-- Query 7: Validate entire trade before insert
-- ============================================================================
-- Parameters: :portfolio_name, :security_name, :counterparty_name (optional)
-- Returns: Validation result with details

/*
SELECT
    -- Portfolio Validation
    (SELECT COUNT(*) FROM cis_portfolio
     WHERE name = :portfolio_name
       AND status = 'SETTLED'
       AND is_active = true) AS portfolio_exists,

    -- Security Validation
    (SELECT COUNT(*) FROM cis_security
     WHERE security_name = :security_name
       AND status IN ('ACTIVE', 'APPROVED')
       AND is_active = true) AS security_exists,

    -- Counterparty Validation (if provided)
    CASE
        WHEN :counterparty_name IS NULL OR :counterparty_name = '' THEN 1
        ELSE (SELECT COUNT(*) FROM cis_counterparty_kudu
              WHERE counterparty_short_name = :counterparty_name
                AND is_active = true
                AND is_deleted = false)
    END AS counterparty_exists;
*/

-- ============================================================================
-- Query 8: Get current trade detail for SELL validation
-- ============================================================================
-- Parameters: :portfolio_name, :security_name
-- Returns: Current trade detail quantity (cannot sell more than held)

/*
SELECT
    COALESCE(quantity, 0) AS current_quantity,
    COALESCE(average_cost, 0) AS average_cost,
    status
FROM cis_trade_details
WHERE portfolio_short_name = :portfolio_name
  AND security_label = :security_name
  AND status = 'OPEN'
  AND is_active = true;
*/

-- ============================================================================
-- DROPDOWN DATA QUERIES
-- ============================================================================

-- ============================================================================
-- Query 9: Get all valid portfolios for dropdown
-- ============================================================================

/*
SELECT
    name AS value,
    name AS label,
    currency,
    manager
FROM cis_portfolio
WHERE status = 'SETTLED'
  AND is_active = true
ORDER BY name;
*/

-- ============================================================================
-- Query 10: Get all valid securities for dropdown (with search)
-- ============================================================================
-- Parameters: :search_term (optional)

/*
SELECT
    security_name AS value,
    CONCAT(security_name, ' (', COALESCE(ticker, isin, ''), ')') AS label,
    security_type,
    currency_code
FROM cis_security
WHERE status IN ('ACTIVE', 'APPROVED')
  AND is_active = true
  AND (
      :search_term IS NULL
      OR security_name LIKE CONCAT('%', :search_term, '%')
      OR ticker LIKE CONCAT('%', :search_term, '%')
      OR isin LIKE CONCAT('%', :search_term, '%')
  )
ORDER BY security_name
LIMIT 50;
*/

-- ============================================================================
-- Query 11: Get all valid counterparties for dropdown
-- ============================================================================

/*
SELECT
    counterparty_short_name AS value,
    CONCAT(counterparty_full_name, ' (', counterparty_short_name, ')') AS label,
    country
FROM cis_counterparty_kudu
WHERE is_active = true
  AND is_deleted = false
ORDER BY counterparty_short_name;
*/

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check views created
SHOW TABLES LIKE 'v_*';

-- Test valid portfolios view
SELECT * FROM v_valid_portfolios_for_trade LIMIT 5;

-- Test valid securities view
SELECT * FROM v_valid_securities_for_trade LIMIT 5;

-- Test valid counterparties view
SELECT * FROM v_valid_counterparties_for_trade LIMIT 5;

-- ============================================================================
-- END OF VALIDATION VIEWS
-- ============================================================================
