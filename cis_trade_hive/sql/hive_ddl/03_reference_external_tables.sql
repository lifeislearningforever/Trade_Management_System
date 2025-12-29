-- ================================================================
-- Hive DDL for Reference Data Tables - External Tables
-- Converted from Excel schema: Reference_Data.xlsx
-- Database: cis
-- Storage: TEXT format (pipe-delimited) pointing to external CSV files
-- Note: External tables - data remains in original location
-- ================================================================

USE cis;

-- Drop existing tables if they exist
DROP TABLE IF EXISTS gmp_cis_sta_dly_calendar;
DROP TABLE IF EXISTS gmp_cis_sta_dly_country;
DROP TABLE IF EXISTS gmp_cis_sta_dly_currency;
DROP TABLE IF EXISTS gmp_cis_sta_dly_counterparty;

-- ================================================================
-- Table: gmp_cis_sta_dly_calendar (100,000 rows)
-- Holiday and calendar data for financial centers
-- ================================================================

CREATE EXTERNAL TABLE gmp_cis_sta_dly_calendar (
  calendar_label       STRING   COMMENT 'Calendar identifier (e.g., AAB, NYB, LNB)',
  calendar_description STRING   COMMENT 'Description of the calendar',
  holiday_date         INT      COMMENT 'Holiday date in YYYYMMDD format'
)
COMMENT 'Financial calendar and holiday data'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE
LOCATION 'file:///Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/reference_csv/gmp_cis_sta_dly_calendar';

-- ================================================================
-- Table: gmp_cis_sta_dly_country (246 rows)
-- Country reference data
-- ================================================================

CREATE EXTERNAL TABLE gmp_cis_sta_dly_country (
  label     STRING   COMMENT 'Two-letter country code',
  full_name STRING   COMMENT 'Full country name'
)
COMMENT 'Country reference data'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE
LOCATION 'file:///Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/reference_csv/gmp_cis_sta_dly_country';

-- ================================================================
-- Table: gmp_cis_sta_dly_currency (178 rows)
-- Currency reference data
-- ================================================================

CREATE EXTERNAL TABLE gmp_cis_sta_dly_currency (
  name                STRING   COMMENT 'Currency short name',
  full_name           STRING   COMMENT 'Full currency name',
  symbol              STRING   COMMENT 'Currency symbol',
  iso_code            STRING   COMMENT 'ISO currency code',
  `precision`         STRING   COMMENT 'Currency precision (e.g., 1/100)',
  calendar            STRING   COMMENT 'Calendar code for this currency',
  spot_schedule       STRING   COMMENT 'Spot settlement schedule',
  `rate_precision`    STRING   COMMENT 'Exchange rate precision'
)
COMMENT 'Currency reference data'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE
LOCATION 'file:///Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/reference_csv/gmp_cis_sta_dly_currency';

-- ================================================================
-- Table: gmp_cis_sta_dly_counterparty (6,385 rows)
-- Counterparty/entity information
-- ================================================================

CREATE EXTERNAL TABLE gmp_cis_sta_dly_counterparty (
  counterparty_name         STRING   COMMENT 'Counterparty identifier/name',
  description               STRING   COMMENT 'Full description',
  salutation                STRING   COMMENT 'Salutation',
  address                   STRING   COMMENT 'Street address',
  city                      STRING   COMMENT 'City',
  country                   STRING   COMMENT 'Country',
  postal_code               STRING   COMMENT 'Postal/ZIP code',
  fax                       STRING   COMMENT 'Fax number',
  telex                     STRING   COMMENT 'Telex number',
  industry                  DOUBLE   COMMENT 'Industry code',
  is_counterparty_broker    STRING   COMMENT 'Is this a broker? (Y/N)',
  is_counterparty_custodian STRING   COMMENT 'Is this a custodian? (Y/N)',
  is_counterparty_issuer    STRING   COMMENT 'Is this an issuer? (Y/N)',
  primary_contact           DOUBLE   COMMENT 'Primary contact ID',
  primary_number            DOUBLE   COMMENT 'Primary phone number',
  other_contact             DOUBLE   COMMENT 'Other contact ID',
  other_number              DOUBLE   COMMENT 'Other phone number',
  custodian_group           DOUBLE   COMMENT 'Custodian group ID',
  broker_group              DOUBLE   COMMENT 'Broker group ID',
  resident_y_n              DOUBLE   COMMENT 'Resident flag'
)
COMMENT 'Counterparty and entity reference data'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE
LOCATION 'file:///Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/reference_csv/gmp_cis_sta_dly_counterparty';

-- ================================================================
-- Show tables
-- ================================================================

SHOW TABLES;
