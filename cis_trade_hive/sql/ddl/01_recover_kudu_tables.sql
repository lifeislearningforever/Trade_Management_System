-- ============================================================================
-- Recover Kudu Tables - Register existing Kudu tables with Impala
-- ============================================================================
-- This script creates EXTERNAL tables in Impala pointing to existing Kudu tables
-- Run this when Kudu tables exist but Impala metadata is lost
-- ============================================================================

USE gmp_cis;

-- Core Tables
CREATE EXTERNAL TABLE IF NOT EXISTS cis_audit_log STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_audit_log');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_user STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_user');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_user_group STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_user_group');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_group_permissions STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_group_permissions');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_permission STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_permission');

-- Reference Data Tables
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis_sta_dly_currency STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.gmp_cis_sta_dly_currency');

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis_sta_dly_country STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.gmp_cis_sta_dly_country');

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis_sta_dly_calendar STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.gmp_cis_sta_dly_calendar');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_counterparty_kudu STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_counterparty_kudu');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_counterparty_cif_kudu STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_counterparty_cif_kudu');

-- Portfolio Tables
CREATE EXTERNAL TABLE IF NOT EXISTS cis_portfolio STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_portfolio');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_portfolio_history STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_portfolio_history');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_portfolio_backup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_portfolio_backup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_portfolio_backup_20260111 STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_portfolio_backup_20260111');

-- Security Tables
CREATE EXTERNAL TABLE IF NOT EXISTS cis_security STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_security');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_security_kudu STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_security_kudu');

-- Trade Tables
CREATE EXTERNAL TABLE IF NOT EXISTS cis_trade STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_trade');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_trade_history STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_trade_history');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_trade_note STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_trade_note');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_trade_lot STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_trade_lot');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_sequence STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_sequence');

-- Position Tables
CREATE EXTERNAL TABLE IF NOT EXISTS cis_position STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_position');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_position_history STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_position_history');

-- Market Data Tables
CREATE EXTERNAL TABLE IF NOT EXISTS cis_equity_price STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_equity_price_kudu');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_equity_price_history STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_equity_price_history');

-- UDF Tables
CREATE EXTERNAL TABLE IF NOT EXISTS cis_udf_field_kudu STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_udf_field_kudu');

-- Lookup Tables
CREATE EXTERNAL TABLE IF NOT EXISTS cis_trade_status_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_trade_status_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_broker_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_broker_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_gl_fund_type_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_gl_fund_type_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_gl_cost_centre_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_gl_cost_centre_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_gl_account_code_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_gl_account_code_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_selling_rule_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_selling_rule_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_custodian_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_custodian_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_sub_custodian_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_sub_custodian_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_fund_type_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_fund_type_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_income_exp_type_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_income_exp_type_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_uobn_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_uobn_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_extension_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_extension_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_delivery_type_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_delivery_type_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_income_type_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_income_type_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_split_type_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_split_type_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_reduction_type_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_reduction_type_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_section_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_section_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_revision_code_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_revision_code_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_open_close_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_open_close_lookup');

CREATE EXTERNAL TABLE IF NOT EXISTS cis_amor_method_lookup STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_amor_method_lookup');

-- Test table
CREATE EXTERNAL TABLE IF NOT EXISTS test_kudu_simple STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.test_kudu_simple');

-- Verify
SHOW TABLES;
