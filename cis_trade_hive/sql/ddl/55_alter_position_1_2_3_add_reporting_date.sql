-- ============================================================================
-- ALTER TABLE: Add reporting_date to position upload tables 1, 2, 3
-- ============================================================================
-- Run this if the tables already exist on the cluster without reporting_date.
-- Hive ADD COLUMNS is non-destructive — existing data is unaffected.
-- Tables 4 and 5 do NOT need this (4 has no reporting_date; 5 already has it).
--
-- Run:
--   impala-shell -i localhost:21050 -f sql/ddl/55_alter_position_1_2_3_add_reporting_date.sql
--
-- After running, also run 54_position_upload_datasource_config.sql to update
-- the intake_columns in cis_datasource_mng to include reporting_date.
-- ============================================================================

USE gmp_cis;

-- Add reporting_date to table 1 (before position_basis)
ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_1
    ADD COLUMNS (reporting_date STRING);

-- Add reporting_date to table 2 (before position_basis)
ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_2
    ADD COLUMNS (reporting_date STRING);

-- Add reporting_date to table 3 (before position_basis)
ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_3
    ADD COLUMNS (reporting_date STRING);

-- Verify columns after ALTER
DESCRIBE gmp_cis.cis_user_sta_adhoc_position_1;
DESCRIBE gmp_cis.cis_user_sta_adhoc_position_2;
DESCRIBE gmp_cis.cis_user_sta_adhoc_position_3;
