-- ============================================================================
-- ALTER TABLE: Add trade_date to position upload table 1
--              Add reporting_date to position upload tables 2 and 3
-- ============================================================================
-- Run this if the tables already exist on the cluster without these columns.
-- Hive ADD COLUMNS is non-destructive — existing data is unaffected.
-- Tables 4 and 5 do NOT need changes.
--
-- Table 1: column is trade_date (matches CSV header "Trade_Date", pipe-separated)
-- Tables 2, 3: column is reporting_date (confirm actual CSV headers before running)
--
-- Run:
--   impala-shell -i localhost:21050 -f sql/ddl/55_alter_position_1_2_3_add_reporting_date.sql
--
-- After running, also run 54_position_upload_datasource_config.sql to update
-- the intake_columns in cis_datasource_mng.
-- ============================================================================

USE gmp_cis;

-- Table 1: add trade_date (CSV header is "Trade_Date", separator is pipe "|")
ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_1
    ADD COLUMNS (trade_date STRING);

-- Table 2: add reporting_date (verify actual CSV header name before running)
ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_2
    ADD COLUMNS (reporting_date STRING);

-- Table 3: add reporting_date (verify actual CSV header name before running)
ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_3
    ADD COLUMNS (reporting_date STRING);

-- Verify columns after ALTER
DESCRIBE gmp_cis.cis_user_sta_adhoc_position_1;
DESCRIBE gmp_cis.cis_user_sta_adhoc_position_2;
DESCRIBE gmp_cis.cis_user_sta_adhoc_position_3;
