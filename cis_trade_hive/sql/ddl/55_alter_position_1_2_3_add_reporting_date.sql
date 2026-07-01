-- ============================================================================
-- ALTER TABLE: Add reporting_date to position upload tables 1, 2, 3
-- ============================================================================
-- Run this if the tables already exist on the cluster without these columns.
-- Hive ADD COLUMNS is non-destructive — existing data is unaffected.
-- Tables 4 and 5 do NOT need changes.
--
-- Table 1: file header is REPORTING_DATE (pipe-separated), maps to reporting_date
--          position_basis is server-injected as TRADED (not in file)
-- Tables 2, 3: reporting_date column from file
--
-- Run:
--   impala-shell -i localhost:21050 -f sql/ddl/55_alter_position_1_2_3_add_reporting_date.sql
--
-- After running, also run 54_position_upload_datasource_config.sql to update
-- the intake_columns in cis_datasource_mng.
-- ============================================================================

USE gmp_cis;

-- Table 1: add reporting_date (file header is REPORTING_DATE, separator is pipe "|")
-- NOTE: If the column was previously added as trade_date, run this instead:
--   ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_1 CHANGE trade_date reporting_date STRING;
ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_1
    ADD COLUMNS (reporting_date STRING);

-- Table 2: add reporting_date
ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_2
    ADD COLUMNS (reporting_date STRING);

-- Table 3: add reporting_date
ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_3
    ADD COLUMNS (reporting_date STRING);

-- Verify columns after ALTER
DESCRIBE gmp_cis.cis_user_sta_adhoc_position_1;
DESCRIBE gmp_cis.cis_user_sta_adhoc_position_2;
DESCRIBE gmp_cis.cis_user_sta_adhoc_position_3;
