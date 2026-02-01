-- ============================================================================
-- CIS Trade Hive - Complete Kudu DDL for Docker Environment
-- ============================================================================
-- Description: All Kudu tables for the CIS Trade Hive application
-- Environment: Docker (localhost:21050 for Impala, localhost:7051 for Kudu)
-- Database: gmp_cis
-- Created: 2026-01-24
--
-- Run with: impala-shell -i localhost:21050 -f 00_all_kudu_tables_docker.sql
-- ============================================================================

-- Create database if not exists
CREATE DATABASE IF NOT EXISTS gmp_cis;
USE gmp_cis;

-- ============================================================================
-- SECTION 1: CORE/ACL TABLES
-- ============================================================================

-- 1.1 Audit Log Table
DROP TABLE IF EXISTS cis_audit_log;
CREATE TABLE cis_audit_log (
  audit_id BIGINT NOT NULL,
  audit_timestamp STRING,
  user_id STRING,
  username STRING,
  user_email STRING,
  action_type STRING,
  action_category STRING,
  action_description STRING,
  entity_type STRING,
  entity_id STRING,
  entity_name STRING,
  field_name STRING,
  old_value STRING,
  new_value STRING,
  request_method STRING,
  request_path STRING,
  request_params STRING,
  status STRING,
  status_code INT,
  error_message STRING,
  error_traceback STRING,
  session_id STRING,
  ip_address STRING,
  user_agent STRING,
  module_name STRING,
  function_name STRING,
  duration_ms BIGINT,
  tags STRING,
  `metadata` STRING,
  audit_date STRING,
  PRIMARY KEY (audit_id)
)
PARTITION BY HASH (audit_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 1.2 User Table
DROP TABLE IF EXISTS cis_user;
CREATE TABLE cis_user (
    user_id BIGINT NOT NULL,
    username STRING,
    login STRING,
    name STRING,
    email STRING,
    domain STRING,
    entity STRING,
    cis_user_group_id BIGINT,
    is_active BOOLEAN,
    is_deleted BOOLEAN,
    enabled BOOLEAN,
    last_login BIGINT,
    created_on BIGINT,
    created_by STRING,
    updated_on BIGINT,
    updated_by STRING,
    PRIMARY KEY (user_id)
)
PARTITION BY HASH (user_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 1.3 User Group Table
DROP TABLE IF EXISTS cis_user_group;
CREATE TABLE cis_user_group (
    group_id BIGINT NOT NULL,
    user_id BIGINT,
    group_name STRING,
    description STRING,
    is_active BOOLEAN,
    is_deleted BOOLEAN,
    created_at BIGINT,
    updated_at BIGINT,
    PRIMARY KEY (group_id)
)
PARTITION BY HASH (group_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 1.4 Group Table
DROP TABLE IF EXISTS cis_group;
CREATE TABLE cis_group (
    group_id BIGINT NOT NULL,
    group_name STRING,
    description STRING,
    is_active BOOLEAN,
    is_deleted BOOLEAN,
    created_at BIGINT,
    updated_at BIGINT,
    PRIMARY KEY (group_id)
)
PARTITION BY HASH (group_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 1.5 Group Permissions Table
DROP TABLE IF EXISTS cis_group_permissions;
CREATE TABLE cis_group_permissions (
    permission_id BIGINT NOT NULL,
    group_id BIGINT,
    permission_name STRING,
    can_view BOOLEAN,
    can_create BOOLEAN,
    can_edit BOOLEAN,
    can_delete BOOLEAN,
    can_approve BOOLEAN,
    object_id STRING,
    read_write STRING,
    is_active BOOLEAN,
    is_deleted BOOLEAN,
    created_at BIGINT,
    updated_at BIGINT,
    PRIMARY KEY (permission_id)
)
PARTITION BY HASH (permission_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- ============================================================================
-- SECTION 2: REFERENCE DATA TABLES
-- ============================================================================

-- 2.1 Currency Table
DROP TABLE IF EXISTS gmp_cis_sta_dly_currency;
CREATE TABLE gmp_cis_sta_dly_currency (
  iso_code STRING NOT NULL,
  name STRING,
  full_name STRING,
  symbol STRING,
  precision_val STRING,
  calendar STRING,
  spot_schedule STRING,
  rate_precision STRING,
  PRIMARY KEY (iso_code)
)
PARTITION BY HASH (iso_code) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 2.2 Country Table
DROP TABLE IF EXISTS gmp_cis_sta_dly_country;
CREATE TABLE gmp_cis_sta_dly_country (
  label STRING NOT NULL,
  full_name STRING,
  PRIMARY KEY (label)
)
PARTITION BY HASH (label) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 2.3 Calendar Table
DROP TABLE IF EXISTS gmp_cis_sta_dly_calendar;
CREATE TABLE gmp_cis_sta_dly_calendar (
  calendar_id BIGINT NOT NULL,
  calendar_label STRING,
  calendar_description STRING,
  holiday_date STRING,
  PRIMARY KEY (calendar_id)
)
PARTITION BY HASH (calendar_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 2.4 Counterparty Table
DROP TABLE IF EXISTS cis_counterparty_kudu;
CREATE TABLE cis_counterparty_kudu (
    counterparty_short_name STRING NOT NULL,
    m_label STRING,
    counterparty_full_name STRING,
    record_type STRING,
    address_line_0 STRING,
    address_line_1 STRING,
    address_line_2 STRING,
    address_line_3 STRING,
    city STRING,
    country STRING,
    postal_code STRING,
    fax_number STRING,
    telex_number STRING,
    primary_contact STRING,
    primary_number STRING,
    other_contact STRING,
    other_number STRING,
    industry STRING,
    industry_group STRING,
    is_broker BOOLEAN,
    is_custodian BOOLEAN,
    is_issuer BOOLEAN,
    is_bank BOOLEAN,
    is_subsidiary BOOLEAN,
    is_corporate BOOLEAN,
    subsidiary_level STRING,
    counterparty_grandparent STRING,
    counterparty_parent STRING,
    resident_y_n STRING,
    mas_industry_code STRING,
    country_of_incorporation STRING,
    cels_code STRING,
    src_system STRING,
    sub_system STRING,
    data_cat STRING,
    data_frq STRING,
    src_id STRING,
    processing_date STRING,
    is_active BOOLEAN,
    is_deleted BOOLEAN,
    created_by STRING,
    created_at BIGINT,
    updated_by STRING,
    updated_at BIGINT,
    PRIMARY KEY (counterparty_short_name)
)
PARTITION BY HASH (counterparty_short_name) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- ============================================================================
-- SECTION 3: PORTFOLIO TABLES
-- ============================================================================

-- 3.1 Portfolio Table (with Maker-Checker workflow)
DROP TABLE IF EXISTS cis_portfolio;
CREATE TABLE cis_portfolio (
  name STRING NOT NULL,
  description STRING,
  currency STRING,
  manager STRING,
  portfolio_client STRING,
  cash_balance STRING,
  cost_centre_code STRING,
  corp_code STRING,
  account_group STRING,
  portfolio_group STRING,
  report_group STRING,
  entity_group STRING,
  revaluation_status STRING,
  src_system STRING,
  status STRING,
  is_active BOOLEAN,
  created_by STRING,
  created_at STRING,
  updated_by STRING,
  updated_at STRING,
  submitted_by STRING,
  submitted_at STRING,
  validated_by STRING,
  validated_at STRING,
  validation_comments STRING,
  settled_by STRING,
  settled_at STRING,
  settlement_comments STRING,
  cancelled_by STRING,
  cancelled_at STRING,
  cancel_reason STRING,
  PRIMARY KEY (name)
)
PARTITION BY HASH (name) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 3.2 Portfolio History Table
DROP TABLE IF EXISTS cis_portfolio_history;
CREATE TABLE cis_portfolio_history (
  history_id BIGINT NOT NULL,
  portfolio_name STRING,
  action STRING,
  old_status STRING,
  new_status STRING,
  changes STRING,
  comments STRING,
  performed_by STRING,
  performed_at STRING,
  ip_address STRING,
  user_agent STRING,
  PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- ============================================================================
-- SECTION 4: SECURITY TABLES
-- ============================================================================

-- 4.1 Security Master Table
DROP TABLE IF EXISTS cis_security;
CREATE TABLE cis_security (
    security_id BIGINT NOT NULL,
    security_name STRING,
    isin STRING,
    security_description STRING,
    issuer STRING,
    ticker STRING,
    industry STRING,
    security_type STRING,
    investment_type STRING,
    issuer_type STRING,
    quoted_unquoted STRING,
    country_of_incorporation STRING,
    country_of_exchange STRING,
    country_of_issue STRING,
    country_of_primary_exchange STRING,
    exchange_code STRING,
    currency_code STRING,
    price DECIMAL(20, 4),
    price_date STRING,
    price_source STRING,
    shares_outstanding BIGINT,
    beta DECIMAL(10, 4),
    par_value DECIMAL(20, 6),
    shareholding_entity_1 DECIMAL(10, 4),
    shareholding_entity_2 DECIMAL(10, 4),
    shareholding_entity_3 DECIMAL(10, 4),
    shareholding_aggregated DECIMAL(10, 4),
    substantial_10_pct STRING,
    bwciif BIGINT,
    bwciif_others BIGINT,
    cels STRING,
    approved_s32 STRING,
    basel_iv_fund STRING,
    mas_643_entity_type STRING,
    mas_6d_code STRING,
    fin_nonfin_ind STRING,
    business_unit_head STRING,
    person_in_charge STRING,
    core_noncore STRING,
    fund_index_fund STRING,
    management_limit_classification STRING,
    relative_index STRING,
    is_active BOOLEAN,
    created_by STRING,
    created_at BIGINT,
    updated_by STRING,
    updated_at BIGINT,
    PRIMARY KEY (security_id)
)
PARTITION BY HASH (security_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 4.2 Security History Table
DROP TABLE IF EXISTS cis_security_history;
CREATE TABLE cis_security_history (
    history_id BIGINT NOT NULL,
    security_id BIGINT,
    security_name STRING,
    isin STRING,
    action STRING,
    status STRING,
    changes STRING,
    comments STRING,
    performed_by STRING,
    performed_at BIGINT,
    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- ============================================================================
-- SECTION 5: TRADE TABLES
-- ============================================================================

-- 5.1 Main Trade Table
DROP TABLE IF EXISTS cis_trade;
CREATE TABLE cis_trade (
    trade_id BIGINT NOT NULL,
    trade_type STRING,
    deal_number STRING,
    portfolio_short_name STRING,
    portfolio_full_name STRING,
    security_label STRING,
    security_full_name STRING,
    security_type STRING,
    trade_status STRING,
    trade_date STRING,
    settle_date STRING,
    expiry_date STRING,
    quantity DECIMAL(20,6),
    face_value DECIMAL(20,6),
    lot DECIMAL(20,6),
    price DECIMAL(20,6),
    commission DECIMAL(20,6),
    accrued_interest DECIMAL(20,6),
    sec_fee DECIMAL(20,6),
    other_charges DECIMAL(20,6),
    total_amount DECIMAL(20,6),
    open_close_position STRING,
    extension STRING,
    brokers STRING,
    broker_name STRING,
    gl_fund_type STRING,
    gl_cost_centre STRING,
    gl_account_code STRING,
    contract_ref STRING,
    fd_receipt STRING,
    org_pur_date STRING,
    open_fx_rate DECIMAL(20,6),
    curr_dealing DECIMAL(20,6),
    open_dealing DECIMAL(20,6),
    input_tax_oth DECIMAL(20,6),
    qty_entitled DECIMAL(20,6),
    selling_rule STRING,
    cash_balance DECIMAL(20,6),
    custodian STRING,
    amor_accr_method STRING,
    lots_held DECIMAL(20,6),
    quantity_held DECIMAL(20,6),
    remarks STRING,
    udf_fund_type STRING,
    udf_section_31_26 STRING,
    udf_sub_custodian STRING,
    udf_disclosure_req BOOLEAN,
    udf_counter_pledged BOOLEAN,
    udf_revision_code STRING,
    udf_uobn_uobn_hk STRING,
    udf_income_exp_type STRING,
    udf_currency_hedge BOOLEAN,
    realized_pnl DECIMAL(20,6),
    parent_trade_id BIGINT,
    delivery_type STRING,
    counterparty STRING,
    reduction_type STRING,
    reduction_amount DECIMAL(20,6),
    units_affected DECIMAL(20,6),
    income_type STRING,
    ex_date STRING,
    record_date STRING,
    pay_date STRING,
    amount_per_unit DECIMAL(20,6),
    gross_amount DECIMAL(20,6),
    withholding_tax DECIMAL(20,6),
    net_amount DECIMAL(20,6),
    split_type STRING,
    split_ratio_new INT,
    split_ratio_old INT,
    effective_date STRING,
    status STRING,
    is_active BOOLEAN,
    is_deleted BOOLEAN,
    src_system STRING,
    created_by STRING,
    created_at STRING,
    updated_by STRING,
    updated_at STRING,
    submitted_by STRING,
    submitted_at STRING,
    validated_by STRING,
    validated_at STRING,
    validation_comments STRING,
    settled_by STRING,
    settled_at STRING,
    settlement_comments STRING,
    cancelled_by STRING,
    cancelled_at STRING,
    cancel_reason STRING,
    internal_ref STRING,
    external_ref STRING,
    PRIMARY KEY (trade_id)
)
PARTITION BY HASH (trade_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 5.2 Trade History Table
DROP TABLE IF EXISTS cis_trade_history;
CREATE TABLE cis_trade_history (
    history_id BIGINT NOT NULL,
    trade_id BIGINT,
    deal_number STRING,
    action STRING,
    old_status STRING,
    new_status STRING,
    changes STRING,
    comments STRING,
    performed_by STRING,
    performed_at STRING,
    ip_address STRING,
    user_agent STRING,
    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 5.3 Trade Note Table
DROP TABLE IF EXISTS cis_trade_note;
CREATE TABLE cis_trade_note (
    note_id BIGINT NOT NULL,
    trade_id BIGINT,
    note_type STRING,
    note_text STRING,
    internal_ref STRING,
    external_ref STRING,
    attachments STRING,
    created_by STRING,
    created_at STRING,
    updated_by STRING,
    updated_at STRING,
    is_active BOOLEAN,
    PRIMARY KEY (note_id)
)
PARTITION BY HASH (note_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 5.4 Trade Position Table (Versioned Snapshots - replaces cis_trade_details + history)
DROP TABLE IF EXISTS cis_trade_position;
CREATE TABLE cis_trade_position (
    version_id BIGINT NOT NULL,
    position_id BIGINT NOT NULL,
    position_date STRING NOT NULL,
    portfolio_short_name STRING NOT NULL,
    security_label STRING NOT NULL,
    quantity DECIMAL(20,6),
    average_cost DECIMAL(20,6),
    total_cost DECIMAL(20,6),
    realized_pnl DECIMAL(20,6),
    current_price DECIMAL(20,6),
    market_value DECIMAL(20,6),
    unrealized_pnl DECIMAL(20,6),
    trade_id BIGINT,
    trade_type STRING,
    lots_held INT,
    custodian STRING,
    sub_custodian STRING,
    status STRING,
    is_active BOOLEAN,
    created_by STRING,
    created_at STRING,
    PRIMARY KEY (version_id)
)
PARTITION BY HASH (version_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 5.5 Trade Lot Table
DROP TABLE IF EXISTS cis_trade_lot;
CREATE TABLE cis_trade_lot (
    lot_id BIGINT NOT NULL,
    position_id BIGINT,
    portfolio_short_name STRING,
    security_label STRING,
    lot_number INT,
    quantity DECIMAL(20,6),
    purchase_price DECIMAL(20,6),
    purchase_date STRING,
    purchase_trade_id BIGINT,
    cost_basis DECIMAL(20,6),
    adjusted_cost_basis DECIMAL(20,6),
    status STRING,
    remaining_quantity DECIMAL(20,6),
    created_at STRING,
    updated_at STRING,
    PRIMARY KEY (lot_id)
)
PARTITION BY HASH (lot_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 5.7 Sequence Table (for ID generation)
DROP TABLE IF EXISTS cis_sequence;
CREATE TABLE cis_sequence (
    sequence_name STRING NOT NULL,
    current_value BIGINT,
    increment_by INT,
    PRIMARY KEY (sequence_name)
)
PARTITION BY HASH (sequence_name) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- Initialize sequences
UPSERT INTO cis_sequence VALUES ('trade_id', 1000000, 1);
UPSERT INTO cis_sequence VALUES ('trade_history_id', 1000000, 1);
UPSERT INTO cis_sequence VALUES ('trade_note_id', 1000000, 1);
UPSERT INTO cis_sequence VALUES ('position_id', 1000000, 1);
UPSERT INTO cis_sequence VALUES ('position_version_id', 1000000, 1);
UPSERT INTO cis_sequence VALUES ('lot_id', 1000000, 1);
UPSERT INTO cis_sequence VALUES ('audit_id', 1000000, 1);
UPSERT INTO cis_sequence VALUES ('security_id', 1000000, 1);
UPSERT INTO cis_sequence VALUES ('portfolio_history_id', 1000000, 1);

-- ============================================================================
-- SECTION 6: MARKET DATA TABLES
-- ============================================================================

-- 6.1 Equity Price Table (Versioned - composite PK includes price_date)
-- Each (currency_code, security_label, price_date) is a unique row.
-- Multiple prices per security supported (one per date).
-- Latest price = ORDER BY price_date DESC, price_timestamp DESC LIMIT 1
DROP TABLE IF EXISTS cis_equity_price;
DROP TABLE IF EXISTS cis_equity_price_kudu;
CREATE TABLE cis_equity_price_kudu (
    -- Composite Primary Key fields (currency + security + date)
    currency_code STRING NOT NULL,
    security_label STRING NOT NULL,
    price_date STRING NOT NULL,

    -- Business Fields
    isin STRING,
    main_closing_price DECIMAL(18, 6),
    price_timestamp BIGINT,
    src_system STRING DEFAULT 'CIS',

    -- Audit Fields
    is_active BOOLEAN DEFAULT true,
    created_by STRING NOT NULL,
    created_at BIGINT NOT NULL,
    updated_by STRING,
    updated_at BIGINT,

    PRIMARY KEY (currency_code, security_label, price_date)
)
PARTITION BY HASH (currency_code, security_label) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- Create alias view for backward compatibility
CREATE EXTERNAL TABLE IF NOT EXISTS cis_equity_price
STORED AS KUDU
TBLPROPERTIES(
    'kudu.table_name' = 'impala::gmp_cis.cis_equity_price_kudu'
);

-- 6.2 FX Rates Table
DROP TABLE IF EXISTS gmp_cis_sta_dly_fx_rates;
CREATE TABLE gmp_cis_sta_dly_fx_rates (
    fx_rate_id BIGINT NOT NULL,
    base_currency STRING,
    quote_currency STRING,
    rate_date STRING,
    bid_rate DECIMAL(20, 10),
    ask_rate DECIMAL(20, 10),
    mid_rate DECIMAL(20, 10),
    rate_type STRING,
    source STRING,
    is_active BOOLEAN,
    created_at BIGINT,
    updated_at BIGINT,
    PRIMARY KEY (fx_rate_id)
)
PARTITION BY HASH (fx_rate_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- ============================================================================
-- SECTION 7: UDF TABLES
-- ============================================================================

-- 7.1 UDF Definition Table
DROP TABLE IF EXISTS cis_udf_definition;
CREATE TABLE cis_udf_definition (
  udf_id BIGINT NOT NULL,
  field_name STRING,
  label STRING,
  description STRING,
  field_type STRING,
  entity_type STRING,
  is_required BOOLEAN,
  is_unique BOOLEAN,
  max_length INT,
  min_value_decimal DECIMAL(38,10),
  max_value_decimal DECIMAL(38,10),
  display_order INT,
  group_name STRING,
  default_string STRING,
  default_int BIGINT,
  default_decimal DECIMAL(38,10),
  default_bool BOOLEAN,
  default_datetime BIGINT,
  is_active BOOLEAN,
  created_by STRING,
  created_at BIGINT,
  updated_by STRING,
  updated_at BIGINT,
  PRIMARY KEY (udf_id)
)
PARTITION BY HASH (udf_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 7.2 UDF Option Table
DROP TABLE IF EXISTS cis_udf_option;
CREATE TABLE cis_udf_option (
  option_id BIGINT NOT NULL,
  udf_id BIGINT,
  option_value STRING,
  display_order INT,
  is_active BOOLEAN,
  created_by STRING,
  created_at BIGINT,
  updated_by STRING,
  updated_at BIGINT,
  PRIMARY KEY (option_id)
)
PARTITION BY HASH (option_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 7.3 UDF Value Table
DROP TABLE IF EXISTS cis_udf_value;
CREATE TABLE cis_udf_value (
  value_id BIGINT NOT NULL,
  entity_type STRING,
  entity_id BIGINT,
  field_name STRING,
  udf_id BIGINT,
  value_string STRING,
  value_int BIGINT,
  value_decimal DECIMAL(38,10),
  value_bool BOOLEAN,
  value_datetime BIGINT,
  is_active BOOLEAN,
  created_by STRING,
  created_at BIGINT,
  updated_by STRING,
  updated_at BIGINT,
  PRIMARY KEY (value_id)
)
PARTITION BY HASH (value_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 7.4 UDF Value Multi Table (for multi-select)
DROP TABLE IF EXISTS cis_udf_value_multi;
CREATE TABLE cis_udf_value_multi (
  multi_value_id BIGINT NOT NULL,
  entity_type STRING,
  entity_id BIGINT,
  field_name STRING,
  option_value STRING,
  udf_id BIGINT,
  is_active BOOLEAN,
  created_by STRING,
  created_at BIGINT,
  updated_by STRING,
  updated_at BIGINT,
  PRIMARY KEY (multi_value_id)
)
PARTITION BY HASH (multi_value_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 7.5 UDF Field Table
DROP TABLE IF EXISTS cis_udf_field;
CREATE TABLE cis_udf_field (
  field_id BIGINT NOT NULL,
  entity_type STRING,
  object_type STRING,
  field_name STRING,
  label STRING,
  is_active BOOLEAN,
  display_order INT,
  created_by STRING,
  created_at BIGINT,
  updated_by STRING,
  updated_at BIGINT,
  PRIMARY KEY (field_id)
)
PARTITION BY HASH (field_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- ============================================================================
-- SECTION 8: TRADE LOOKUP TABLES
-- ============================================================================

-- 8.1 Trade Status Lookup
DROP TABLE IF EXISTS cis_trade_status_lookup;
CREATE TABLE cis_trade_status_lookup (
    status_code STRING NOT NULL,
    status_name STRING,
    description STRING,
    display_order INT,
    is_active BOOLEAN,
    PRIMARY KEY (status_code)
)
PARTITION BY HASH (status_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.2 Broker Lookup
DROP TABLE IF EXISTS cis_broker_lookup;
CREATE TABLE cis_broker_lookup (
    broker_code STRING NOT NULL,
    broker_name STRING,
    broker_type STRING,
    country STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (broker_code)
)
PARTITION BY HASH (broker_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.3 GL Fund Type Lookup
DROP TABLE IF EXISTS cis_gl_fund_type_lookup;
CREATE TABLE cis_gl_fund_type_lookup (
    fund_type_code STRING NOT NULL,
    fund_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (fund_type_code)
)
PARTITION BY HASH (fund_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.4 GL Cost Centre Lookup
DROP TABLE IF EXISTS cis_gl_cost_centre_lookup;
CREATE TABLE cis_gl_cost_centre_lookup (
    cost_centre_code STRING NOT NULL,
    cost_centre_name STRING,
    department STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (cost_centre_code)
)
PARTITION BY HASH (cost_centre_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.5 GL Account Code Lookup
DROP TABLE IF EXISTS cis_gl_account_code_lookup;
CREATE TABLE cis_gl_account_code_lookup (
    account_code STRING NOT NULL,
    account_name STRING,
    account_type STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (account_code)
)
PARTITION BY HASH (account_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.6 Selling Rule Lookup
DROP TABLE IF EXISTS cis_selling_rule_lookup;
CREATE TABLE cis_selling_rule_lookup (
    rule_code STRING NOT NULL,
    rule_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (rule_code)
)
PARTITION BY HASH (rule_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.7 Custodian Lookup
DROP TABLE IF EXISTS cis_custodian_lookup;
CREATE TABLE cis_custodian_lookup (
    custodian_code STRING NOT NULL,
    custodian_name STRING,
    country STRING,
    custodian_type STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (custodian_code)
)
PARTITION BY HASH (custodian_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.8 Sub-Custodian Lookup
DROP TABLE IF EXISTS cis_sub_custodian_lookup;
CREATE TABLE cis_sub_custodian_lookup (
    sub_custodian_code STRING NOT NULL,
    sub_custodian_name STRING,
    parent_custodian STRING,
    country STRING,
    market STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (sub_custodian_code)
)
PARTITION BY HASH (sub_custodian_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.9 Fund Type Lookup
DROP TABLE IF EXISTS cis_fund_type_lookup;
CREATE TABLE cis_fund_type_lookup (
    fund_type_code STRING NOT NULL,
    fund_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (fund_type_code)
)
PARTITION BY HASH (fund_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.10 Income/Expense Type Lookup
DROP TABLE IF EXISTS cis_income_exp_type_lookup;
CREATE TABLE cis_income_exp_type_lookup (
    type_code STRING NOT NULL,
    type_name STRING,
    category STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (type_code)
)
PARTITION BY HASH (type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.11 UOBN Lookup
DROP TABLE IF EXISTS cis_uobn_lookup;
CREATE TABLE cis_uobn_lookup (
    uobn_code STRING NOT NULL,
    uobn_name STRING,
    region STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (uobn_code)
)
PARTITION BY HASH (uobn_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.12 Extension Lookup
DROP TABLE IF EXISTS cis_extension_lookup;
CREATE TABLE cis_extension_lookup (
    extension_code STRING NOT NULL,
    extension_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (extension_code)
)
PARTITION BY HASH (extension_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.13 Delivery Type Lookup
DROP TABLE IF EXISTS cis_delivery_type_lookup;
CREATE TABLE cis_delivery_type_lookup (
    delivery_type_code STRING NOT NULL,
    delivery_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (delivery_type_code)
)
PARTITION BY HASH (delivery_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.14 Income Type Lookup
DROP TABLE IF EXISTS cis_income_type_lookup;
CREATE TABLE cis_income_type_lookup (
    income_type_code STRING NOT NULL,
    income_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (income_type_code)
)
PARTITION BY HASH (income_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.15 Split Type Lookup
DROP TABLE IF EXISTS cis_split_type_lookup;
CREATE TABLE cis_split_type_lookup (
    split_type_code STRING NOT NULL,
    split_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (split_type_code)
)
PARTITION BY HASH (split_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.16 Reduction Type Lookup
DROP TABLE IF EXISTS cis_reduction_type_lookup;
CREATE TABLE cis_reduction_type_lookup (
    reduction_type_code STRING NOT NULL,
    reduction_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (reduction_type_code)
)
PARTITION BY HASH (reduction_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.17 Section Lookup
DROP TABLE IF EXISTS cis_section_lookup;
CREATE TABLE cis_section_lookup (
    section_code STRING NOT NULL,
    section_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (section_code)
)
PARTITION BY HASH (section_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.18 Revision Code Lookup
DROP TABLE IF EXISTS cis_revision_code_lookup;
CREATE TABLE cis_revision_code_lookup (
    revision_code STRING NOT NULL,
    revision_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (revision_code)
)
PARTITION BY HASH (revision_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.19 Open/Close Lookup
DROP TABLE IF EXISTS cis_open_close_lookup;
CREATE TABLE cis_open_close_lookup (
    position_code STRING NOT NULL,
    position_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (position_code)
)
PARTITION BY HASH (position_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- 8.20 Amortisation Method Lookup
DROP TABLE IF EXISTS cis_amor_method_lookup;
CREATE TABLE cis_amor_method_lookup (
    method_code STRING NOT NULL,
    method_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (method_code)
)
PARTITION BY HASH (method_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');

-- ============================================================================
-- SECTION 9: LOOKUP TABLE SEED DATA
-- ============================================================================

-- Trade Status Seed Data
UPSERT INTO cis_trade_status_lookup VALUES ('PENDING', 'Pending', 'Trade is pending execution', 1, true);
UPSERT INTO cis_trade_status_lookup VALUES ('CONFIRMED', 'Confirmed', 'Trade is confirmed', 2, true);
UPSERT INTO cis_trade_status_lookup VALUES ('MATCHED', 'Matched', 'Trade matched with counterparty', 3, true);
UPSERT INTO cis_trade_status_lookup VALUES ('SETTLED', 'Settled', 'Trade is settled', 4, true);
UPSERT INTO cis_trade_status_lookup VALUES ('FAILED', 'Failed', 'Trade failed', 5, true);
UPSERT INTO cis_trade_status_lookup VALUES ('CANCELLED', 'Cancelled', 'Trade cancelled', 6, true);

-- Broker Seed Data
UPSERT INTO cis_broker_lookup VALUES ('GS', 'Goldman Sachs', 'PRIME', 'US', true, 1);
UPSERT INTO cis_broker_lookup VALUES ('MS', 'Morgan Stanley', 'PRIME', 'US', true, 2);
UPSERT INTO cis_broker_lookup VALUES ('JPM', 'JP Morgan', 'PRIME', 'US', true, 3);
UPSERT INTO cis_broker_lookup VALUES ('UBS', 'UBS', 'PRIME', 'CH', true, 4);
UPSERT INTO cis_broker_lookup VALUES ('HSBC', 'HSBC', 'PRIME', 'UK', true, 5);
UPSERT INTO cis_broker_lookup VALUES ('DBS', 'DBS Bank', 'EXECUTING', 'SG', true, 6);
UPSERT INTO cis_broker_lookup VALUES ('OCBC', 'OCBC Bank', 'EXECUTING', 'SG', true, 7);
UPSERT INTO cis_broker_lookup VALUES ('UOB', 'UOB Bank', 'EXECUTING', 'SG', true, 8);

-- GL Fund Type Seed Data
UPSERT INTO cis_gl_fund_type_lookup VALUES ('TRADING', 'Trading Book', 'Trading book positions', true, 1);
UPSERT INTO cis_gl_fund_type_lookup VALUES ('BANKING', 'Banking Book', 'Banking book positions', true, 2);
UPSERT INTO cis_gl_fund_type_lookup VALUES ('INVESTMENT', 'Investment Book', 'Investment portfolio', true, 3);
UPSERT INTO cis_gl_fund_type_lookup VALUES ('HEDGE', 'Hedge Book', 'Hedging positions', true, 4);

-- Selling Rule Seed Data
UPSERT INTO cis_selling_rule_lookup VALUES ('FIFO', 'First In First Out', 'Sell oldest lots first', true, 1);
UPSERT INTO cis_selling_rule_lookup VALUES ('LIFO', 'Last In First Out', 'Sell newest lots first', true, 2);
UPSERT INTO cis_selling_rule_lookup VALUES ('WAVG', 'Weighted Average', 'Use weighted average cost', true, 3);
UPSERT INTO cis_selling_rule_lookup VALUES ('SPEC', 'Specific Identification', 'Specify which lots to sell', true, 4);

-- Custodian Seed Data
UPSERT INTO cis_custodian_lookup VALUES ('DBS', 'DBS Bank', 'SG', 'LOCAL', true, 1);
UPSERT INTO cis_custodian_lookup VALUES ('SCB', 'Standard Chartered', 'SG', 'GLOBAL', true, 2);
UPSERT INTO cis_custodian_lookup VALUES ('CITI', 'Citibank', 'US', 'GLOBAL', true, 3);
UPSERT INTO cis_custodian_lookup VALUES ('HSBC', 'HSBC', 'HK', 'GLOBAL', true, 4);

-- Open/Close Seed Data
UPSERT INTO cis_open_close_lookup VALUES ('OPEN', 'Open', 'Opening new position', true, 1);
UPSERT INTO cis_open_close_lookup VALUES ('CLOSE', 'Close', 'Closing existing position', true, 2);

-- Amortisation Method Seed Data
UPSERT INTO cis_amor_method_lookup VALUES ('STD', 'Standard', 'Standard method', true, 1);
UPSERT INTO cis_amor_method_lookup VALUES ('EFF_INT', 'Effective Interest', 'Effective interest method', true, 2);
UPSERT INTO cis_amor_method_lookup VALUES ('STRAIGHT', 'Straight Line', 'Straight line method', true, 3);
UPSERT INTO cis_amor_method_lookup VALUES ('NONE', 'None', 'No amortisation', true, 4);

-- Income Type Seed Data
UPSERT INTO cis_income_type_lookup VALUES ('DIVIDEND', 'Dividend', 'Cash dividend', true, 1);
UPSERT INTO cis_income_type_lookup VALUES ('STOCK_DIV', 'Stock Dividend', 'Stock dividend', true, 2);
UPSERT INTO cis_income_type_lookup VALUES ('INTEREST', 'Interest', 'Bond interest/coupon', true, 3);
UPSERT INTO cis_income_type_lookup VALUES ('PREMIUM', 'Premium', 'Option premium', true, 4);
UPSERT INTO cis_income_type_lookup VALUES ('DISTRIBUTION', 'Distribution', 'Fund distribution', true, 5);

-- Split Type Seed Data
UPSERT INTO cis_split_type_lookup VALUES ('STOCK_SPLIT', 'Stock Split', 'Forward stock split', true, 1);
UPSERT INTO cis_split_type_lookup VALUES ('REVERSE_SPLIT', 'Reverse Split', 'Reverse stock split', true, 2);
UPSERT INTO cis_split_type_lookup VALUES ('LOT_SPLIT', 'Lot Split', 'Split position into lots', true, 3);
UPSERT INTO cis_split_type_lookup VALUES ('BONUS_ISSUE', 'Bonus Issue', 'Bonus share issue', true, 4);

-- Reduction Type Seed Data
UPSERT INTO cis_reduction_type_lookup VALUES ('RETURN_CAPITAL', 'Return of Capital', 'Return of capital distribution', true, 1);
UPSERT INTO cis_reduction_type_lookup VALUES ('AMORTIZATION', 'Amortization', 'Bond premium amortization', true, 2);
UPSERT INTO cis_reduction_type_lookup VALUES ('WRITEDOWN', 'Write-down', 'Impairment write-down', true, 3);
UPSERT INTO cis_reduction_type_lookup VALUES ('PARTIAL_REDEMP', 'Partial Redemption', 'Partial redemption', true, 4);

-- Delivery Type Seed Data
UPSERT INTO cis_delivery_type_lookup VALUES ('TRANSFER', 'Transfer', 'Portfolio to portfolio transfer', true, 1);
UPSERT INTO cis_delivery_type_lookup VALUES ('CORP_ACTION', 'Corporate Action', 'Due to corporate action', true, 2);
UPSERT INTO cis_delivery_type_lookup VALUES ('SETTLEMENT', 'Settlement', 'Settlement delivery', true, 3);
UPSERT INTO cis_delivery_type_lookup VALUES ('REDEMPTION', 'Redemption', 'Fund redemption', true, 4);

-- ============================================================================
-- SECTION 10: SAMPLE REFERENCE DATA
-- ============================================================================

-- Sample Currencies
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('SGD', 'SGD', 'Singapore Dollar', '$', '2', 'SGX', 'T+2', '4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('USD', 'USD', 'US Dollar', '$', '2', 'NYSE', 'T+2', '4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('EUR', 'EUR', 'Euro', '€', '2', 'EUR', 'T+2', '4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('GBP', 'GBP', 'British Pound', '£', '2', 'LSE', 'T+2', '4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('JPY', 'JPY', 'Japanese Yen', '¥', '0', 'TSE', 'T+2', '4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('HKD', 'HKD', 'Hong Kong Dollar', 'HK$', '2', 'HKEX', 'T+2', '4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('AUD', 'AUD', 'Australian Dollar', 'A$', '2', 'ASX', 'T+2', '4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('CNY', 'CNY', 'Chinese Yuan', '¥', '2', 'SSE', 'T+1', '4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('MYR', 'MYR', 'Malaysian Ringgit', 'RM', '2', 'KLSE', 'T+2', '4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('THB', 'THB', 'Thai Baht', '฿', '2', 'SET', 'T+2', '4');

-- Sample Countries
UPSERT INTO gmp_cis_sta_dly_country VALUES ('SG', 'Singapore');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('US', 'United States');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('UK', 'United Kingdom');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('JP', 'Japan');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('HK', 'Hong Kong');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('AU', 'Australia');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('CN', 'China');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('MY', 'Malaysia');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('TH', 'Thailand');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('ID', 'Indonesia');

-- Sample User (Admin)
UPSERT INTO cis_user VALUES (1, 'admin', 'admin', 'System Administrator', 'admin@cistrade.com', 'LOCAL', 'SYSTEM', 1, true, false, true, 0, 1706097600000, 'SYSTEM', 1706097600000, 'SYSTEM');

-- Sample User Group
UPSERT INTO cis_user_group VALUES (1, 1, 'ADMIN', 'Administrator Group', true, false, 1706097600000, 1706097600000);

-- Sample Group
UPSERT INTO cis_group VALUES (1, 'ADMIN', 'Administrator Group', true, false, 1706097600000, 1706097600000);

-- Sample Permissions for Admin
UPSERT INTO cis_group_permissions VALUES (1, 1, 'ALL', true, true, true, true, true, '*', 'READ_WRITE', true, false, 1706097600000, 1706097600000);

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- List all tables
SHOW TABLES;

-- Check table counts
SELECT 'cis_audit_log' as table_name, COUNT(*) as row_count FROM cis_audit_log
UNION ALL SELECT 'cis_user', COUNT(*) FROM cis_user
UNION ALL SELECT 'gmp_cis_sta_dly_currency', COUNT(*) FROM gmp_cis_sta_dly_currency
UNION ALL SELECT 'gmp_cis_sta_dly_country', COUNT(*) FROM gmp_cis_sta_dly_country
UNION ALL SELECT 'cis_sequence', COUNT(*) FROM cis_sequence;

-- ============================================================================
-- END OF DDL
-- ============================================================================
