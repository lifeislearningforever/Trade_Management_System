-- ================================================================
-- Verify Reference Data Tables
-- Database: cis
-- ================================================================

USE cis;

-- ================================================================
-- Show all tables
-- ================================================================
SHOW TABLES;

-- ================================================================
-- Sample Data from Each Reference Table
-- ================================================================

SELECT '=== gmp_cis_sta_dly_calendar (sample) ===' as section;
SELECT * FROM gmp_cis_sta_dly_calendar LIMIT 5;

SELECT '=== gmp_cis_sta_dly_country (sample) ===' as section;
SELECT * FROM gmp_cis_sta_dly_country LIMIT 10;

SELECT '=== gmp_cis_sta_dly_currency (sample) ===' as section;
SELECT * FROM gmp_cis_sta_dly_currency LIMIT 10;

SELECT '=== gmp_cis_sta_dly_counterparty (sample) ===' as section;
SELECT counterparty_name, description, country,
       is_counterparty_broker, is_counterparty_custodian, is_counterparty_issuer
FROM gmp_cis_sta_dly_counterparty LIMIT 10;

-- ================================================================
-- Table Information
-- ================================================================

SELECT '=== Table Information ===' as section;
DESCRIBE EXTENDED gmp_cis_sta_dly_calendar;
DESCRIBE EXTENDED gmp_cis_sta_dly_country;
DESCRIBE EXTENDED gmp_cis_sta_dly_currency;
DESCRIBE EXTENDED gmp_cis_sta_dly_counterparty;
