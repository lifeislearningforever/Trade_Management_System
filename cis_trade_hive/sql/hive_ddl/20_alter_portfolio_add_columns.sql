-- ================================================================
-- ALTER TABLE DDL for Portfolio - Add New Columns
-- Database: gmp_cis
-- Date: 2026-02-27
-- Description: Adding new columns as per business requirements:
--   - entity: Entity name
--   - business_line: Business line
--   - investment_type: Investment type
--   - branch_code: Branch code (already exists, ensure it's present)
--   - desk_head: Desk head (from UDF dropdown)
--   - portfolio_owner: Portfolio owner
--   - closure_date: Closure date
--   - country: Country (from country table dropdown)
-- ================================================================

USE gmp_cis;

-- ================================================================
-- Add new columns to cis_portfolio table
-- Note: ALTER TABLE ADD COLUMNS in Hive appends columns at the end
-- ================================================================

-- Add entity column
ALTER TABLE cis_portfolio ADD COLUMNS (
    entity STRING COMMENT 'Entity name'
);

-- Add business_line column
ALTER TABLE cis_portfolio ADD COLUMNS (
    business_line STRING COMMENT 'Business line'
);

-- Add investment_type column
ALTER TABLE cis_portfolio ADD COLUMNS (
    investment_type STRING COMMENT 'Investment type'
);

-- Add desk_head column (dropdown from UDF - Head of Desk)
ALTER TABLE cis_portfolio ADD COLUMNS (
    desk_head STRING COMMENT 'Desk head (from UDF dropdown)'
);

-- Add portfolio_owner column
ALTER TABLE cis_portfolio ADD COLUMNS (
    portfolio_owner STRING COMMENT 'Portfolio owner'
);

-- Add closure_date column
ALTER TABLE cis_portfolio ADD COLUMNS (
    closure_date STRING COMMENT 'Closure date (YYYY-MM-DD format)'
);

-- Add country column (dropdown from gmp_cis_sta_dly_country table)
ALTER TABLE cis_portfolio ADD COLUMNS (
    country STRING COMMENT 'Country code (from country table)'
);

-- ================================================================
-- Verify new columns
-- ================================================================
DESCRIBE cis_portfolio;

-- ================================================================
-- Sample query to verify
-- ================================================================
SELECT name, entity, business_line, investment_type, branch_code,
       desk_head, portfolio_owner, closure_date, country
FROM cis_portfolio
LIMIT 5;
