-- ============================================================================
-- SIT: Clean gmp_cis Database
-- ============================================================================
-- Description: Drops ALL tables (Kudu native + Hive external) in gmp_cis
--              and then drops the database itself.
--              Run this BEFORE migrating UAT schema into SIT.
--
-- Environment: SIT (Cloudera CML / Impala)
-- Database: gmp_cis
--
-- WARNING: This is DESTRUCTIVE. All data will be lost.
--          Ensure UAT backup/export is complete before running.
--
-- Run with:
--   impala-shell -i <sit-impala-host>:21050 -f 99_sit_clean_gmp_cis.sql
--   OR via beeline/JDBC on Cloudera CML
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- SECTION 1: HIVE EXTERNAL TABLES (drop first — no underlying Kudu storage)
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_equity_price;
DROP TABLE IF EXISTS gmp_cis.gmp_cis_sta_dly_fx_rates;
DROP TABLE IF EXISTS gmp_cis.cis_ingestion_config;
DROP TABLE IF EXISTS gmp_cis.cis_ingestion_recon;

-- ============================================================================
-- SECTION 2: QUEUE / PROCESSING TABLES
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_position_queue;
DROP TABLE IF EXISTS gmp_cis.cis_settlement_queue;
DROP TABLE IF EXISTS gmp_cis.cis_ca_cash_flow_queue;
DROP TABLE IF EXISTS gmp_cis.cis_ca_cash_flow_log;
DROP TABLE IF EXISTS gmp_cis.cis_trade_event_queue;

-- ============================================================================
-- SECTION 3: CORPORATE ACTIONS & CASH FLOW TABLES
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_corporate_actions_history;
DROP TABLE IF EXISTS gmp_cis.cis_corporate_actions;
DROP TABLE IF EXISTS gmp_cis.cis_cash_flow_history;
DROP TABLE IF EXISTS gmp_cis.cis_cash_flow;

-- ============================================================================
-- SECTION 4: POSITION / AVP TABLES
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_trade_position;
DROP TABLE IF EXISTS gmp_cis.cis_trade_lot;

-- ============================================================================
-- SECTION 5: TRADE TABLES
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_trade_history;
DROP TABLE IF EXISTS gmp_cis.cis_trade_note;
DROP TABLE IF EXISTS gmp_cis.cis_trade;

-- ============================================================================
-- SECTION 6: SECURITY TABLES
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_security_history;
DROP TABLE IF EXISTS gmp_cis.cis_security;
DROP TABLE IF EXISTS gmp_cis.cis_equity_price_history;
DROP TABLE IF EXISTS gmp_cis.cis_equity_price_kudu;

-- ============================================================================
-- SECTION 7: PORTFOLIO TABLES
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_portfolio_history;
DROP TABLE IF EXISTS gmp_cis.cis_portfolio;

-- ============================================================================
-- SECTION 8: UDF TABLES
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_udf_value_multi;
DROP TABLE IF EXISTS gmp_cis.cis_udf_value;
DROP TABLE IF EXISTS gmp_cis.cis_udf_option;
DROP TABLE IF EXISTS gmp_cis.cis_udf_definition;
DROP TABLE IF EXISTS gmp_cis.cis_udf_field;

-- ============================================================================
-- SECTION 9: LOOKUP TABLES
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_trade_status_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_broker_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_gl_fund_type_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_gl_cost_centre_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_gl_account_code_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_selling_rule_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_custodian_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_sub_custodian_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_fund_type_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_income_exp_type_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_uobn_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_extension_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_delivery_type_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_income_type_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_split_type_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_reduction_type_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_section_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_revision_code_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_open_close_lookup;
DROP TABLE IF EXISTS gmp_cis.cis_amor_method_lookup;

-- ============================================================================
-- SECTION 10: COUNTERPARTY & REFERENCE DATA TABLES
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_counterparty_kudu;
DROP TABLE IF EXISTS gmp_cis.gmp_cis_sta_dly_fx_rates;
DROP TABLE IF EXISTS gmp_cis.gmp_cis_sta_dly_currency;
DROP TABLE IF EXISTS gmp_cis.gmp_cis_sta_dly_country;
DROP TABLE IF EXISTS gmp_cis.gmp_cis_sta_dly_calendar;

-- ============================================================================
-- SECTION 11: ACL / USER / RBAC TABLES
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_group_permissions;
DROP TABLE IF EXISTS gmp_cis.cis_group;
DROP TABLE IF EXISTS gmp_cis.cis_user_group;
DROP TABLE IF EXISTS gmp_cis.cis_user;
-- RBAC v2 tables (50_rbac_tables_kudu.sql)
DROP TABLE IF EXISTS gmp_cis.cis_group_permission_map;
DROP TABLE IF EXISTS gmp_cis.cis_user_group_mapping_info;
DROP TABLE IF EXISTS gmp_cis.cis_permission_info;
DROP TABLE IF EXISTS gmp_cis.cis_user_group_info;
DROP TABLE IF EXISTS gmp_cis.cis_user_info;

-- ============================================================================
-- SECTION 12: SYSTEM / OPERATIONAL TABLES
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_sequence;
DROP TABLE IF EXISTS gmp_cis.cis_system_date;
DROP TABLE IF EXISTS gmp_cis.cis_file_upload;
DROP TABLE IF EXISTS gmp_cis.cis_audit_log;
DROP TABLE IF EXISTS gmp_cis.cis_help_content;

-- ============================================================================
-- SECTION 13: DROP DATABASE
-- ============================================================================

-- Verify tables are gone before dropping DB
SHOW TABLES IN gmp_cis;

-- Drop the database
DROP DATABASE IF EXISTS gmp_cis;

-- Confirm
SHOW DATABASES;

-- ============================================================================
-- END OF CLEAN SCRIPT
-- ============================================================================
