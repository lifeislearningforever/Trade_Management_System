-- Kudu Table Definitions for CIS Database
-- Generated from Hive tables on 2025-12-25 23:27:04
--
-- This file contains Kudu table equivalents for all Hive tables in the cis database.
-- Kudu tables are optimized for fast random access and updates.
--
-- Usage:
--   Run this script using Impala (not Hive):
--   impala-shell -f cis_hive_to_kudu_tables.sql
--
-- Or run via beeline with Impala JDBC:
--   beeline -u "jdbc:impala://localhost:21050/cis" -f cis_hive_to_kudu_tables.sql
--

-- Switch to cis database
USE cis;

-- Kudu table for cis_audit_log
CREATE TABLE IF NOT EXISTS cis_audit_log_kudu (
  audit_id INT64 NOT NULL,
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
  status_code INT32,
  error_message STRING,
  error_traceback STRING,
  session_id STRING,
  ip_address STRING,
  user_agent STRING,
  module_name STRING,
  function_name STRING,
  duration_ms INT64,
  tags STRING,
  metadata STRING,
  audit_date STRING,
  PRIMARY KEY (audit_id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'cis_audit_log_kudu'
);


-- Kudu table for cis_group_permissions
CREATE TABLE IF NOT EXISTS cis_group_permissions_kudu (
  cis_group_permissions_id INT32 NOT NULL,
  cis_user_group_id INT32,
  permission STRING,
  read_write STRING,
  is_deleted BOOL,
  updated_on UNIXTIME_MICROS,
  updated_by STRING,
  PRIMARY KEY (cis_group_permissions_id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'cis_group_permissions_kudu'
);


-- Kudu table for cis_permission
CREATE TABLE IF NOT EXISTS cis_permission_kudu (
  cis_permission_id INT32 NOT NULL,
  permission STRING,
  description STRING,
  is_deleted BOOL,
  updated_on UNIXTIME_MICROS,
  updated_by STRING,
  PRIMARY KEY (cis_permission_id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'cis_permission_kudu'
);


-- Kudu table for cis_portfolio
CREATE TABLE IF NOT EXISTS cis_portfolio_kudu (
  name STRING NOT NULL,
  description STRING,
  currency STRING,
  manager STRING,
  portfolio_client STRING,
  cash_balance_list STRING,
  cash_balance STRING,
  status STRING,
  cost_centre_code STRING,
  corp_code STRING,
  account_group STRING,
  portfolio_group STRING,
  report_group STRING,
  entity_group STRING,
  revaluation_status STRING,
  created_at STRING,
  updated_at STRING,
  PRIMARY KEY (name)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'cis_portfolio_kudu'
);


-- Kudu table for cis_udf_definition
CREATE TABLE IF NOT EXISTS cis_udf_definition_kudu (
  udf_id INT64,
  field_name STRING NOT NULL,
  label STRING,
  description STRING,
  field_type STRING,
  entity_type STRING NOT NULL,
  is_required BOOL,
  is_unique BOOL,
  max_length INT32,
  min_value_decimal STRING,
  max_value_decimal STRING,
  display_order INT32,
  group_name STRING,
  default_string STRING,
  default_int INT64,
  default_decimal STRING,
  default_bool BOOL,
  default_datetime UNIXTIME_MICROS,
  is_active BOOL,
  created_by STRING,
  created_at UNIXTIME_MICROS,
  updated_by STRING,
  updated_at UNIXTIME_MICROS,
  PRIMARY KEY (entity_type, field_name)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'cis_udf_definition_kudu'
);


-- Kudu table for cis_udf_option
CREATE TABLE IF NOT EXISTS cis_udf_option_kudu (
  udf_id INT64 NOT NULL,
  option_value STRING NOT NULL,
  display_order INT32,
  is_active BOOL,
  created_by STRING,
  created_at UNIXTIME_MICROS,
  updated_by STRING,
  updated_at UNIXTIME_MICROS,
  PRIMARY KEY (udf_id, option_value)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'cis_udf_option_kudu'
);


-- Kudu table for cis_udf_value
CREATE TABLE IF NOT EXISTS cis_udf_value_kudu (
  entity_type STRING NOT NULL,
  entity_id INT64 NOT NULL,
  field_name STRING NOT NULL,
  udf_id INT64,
  value_string STRING,
  value_int INT64,
  value_decimal STRING,
  value_bool BOOL,
  value_datetime UNIXTIME_MICROS,
  is_active BOOL,
  created_by STRING,
  created_at UNIXTIME_MICROS,
  updated_by STRING,
  updated_at UNIXTIME_MICROS,
  PRIMARY KEY (entity_id, entity_type, field_name)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'cis_udf_value_kudu'
);


-- Kudu table for cis_udf_value_multi
CREATE TABLE IF NOT EXISTS cis_udf_value_multi_kudu (
  entity_type STRING NOT NULL,
  entity_id INT64 NOT NULL,
  field_name STRING NOT NULL,
  option_value STRING NOT NULL,
  udf_id INT64,
  is_active BOOL,
  created_by STRING,
  created_at UNIXTIME_MICROS,
  updated_by STRING,
  updated_at UNIXTIME_MICROS,
  PRIMARY KEY (entity_id, entity_type, field_name, option_value)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'cis_udf_value_multi_kudu'
);


-- Kudu table for cis_user
CREATE TABLE IF NOT EXISTS cis_user_kudu (
  cis_user_id INT32 NOT NULL,
  login STRING,
  name STRING,
  entity STRING,
  email STRING,
  domain STRING,
  cis_user_group_id INT32,
  is_deleted BOOL,
  enabled BOOL,
  last_login UNIXTIME_MICROS,
  created_on UNIXTIME_MICROS,
  created_by STRING,
  updated_on UNIXTIME_MICROS,
  updated_by STRING,
  PRIMARY KEY (cis_user_id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'cis_user_kudu'
);


-- Kudu table for cis_user_group
CREATE TABLE IF NOT EXISTS cis_user_group_kudu (
  cis_user_group_id INT32 NOT NULL,
  name STRING,
  entity STRING,
  description STRING,
  is_deleted BOOL,
  updated_on UNIXTIME_MICROS,
  updated_by STRING,
  PRIMARY KEY (cis_user_group_id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'cis_user_group_kudu'
);


-- Kudu table for gmp_cis_sta_dly_calendar
CREATE TABLE IF NOT EXISTS gmp_cis_sta_dly_calendar_kudu (
  calendar_label STRING NOT NULL,
  calendar_description STRING,
  holiday_date INT32 NOT NULL,
  PRIMARY KEY (calendar_label, holiday_date)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'gmp_cis_sta_dly_calendar_kudu'
);


-- Kudu table for gmp_cis_sta_dly_counterparty
CREATE TABLE IF NOT EXISTS gmp_cis_sta_dly_counterparty_kudu (
  counterparty_name STRING NOT NULL,
  description STRING,
  salutation STRING,
  address STRING,
  city STRING,
  country STRING,
  postal_code STRING,
  fax STRING,
  telex STRING,
  industry DOUBLE,
  is_counterparty_broker STRING,
  is_counterparty_custodian STRING,
  is_counterparty_issuer STRING,
  primary_contact DOUBLE,
  primary_number DOUBLE,
  other_contact DOUBLE,
  other_number DOUBLE,
  custodian_group DOUBLE,
  broker_group DOUBLE,
  resident_y_n DOUBLE,
  PRIMARY KEY (counterparty_name)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'gmp_cis_sta_dly_counterparty_kudu'
);


-- Kudu table for gmp_cis_sta_dly_country
CREATE TABLE IF NOT EXISTS gmp_cis_sta_dly_country_kudu (
  label STRING NOT NULL,
  full_name STRING,
  PRIMARY KEY (label)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'gmp_cis_sta_dly_country_kudu'
);


-- Kudu table for gmp_cis_sta_dly_currency
CREATE TABLE IF NOT EXISTS gmp_cis_sta_dly_currency_kudu (
  name STRING,
  full_name STRING,
  symbol STRING,
  iso_code STRING NOT NULL,
  precision STRING,
  calendar STRING,
  spot_schedule STRING,
  rate_precision STRING,
  PRIMARY KEY (iso_code)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'gmp_cis_sta_dly_currency_kudu'
);


-- Kudu table for test_insert_simple
CREATE TABLE IF NOT EXISTS test_insert_simple_kudu (
  id INT32 NOT NULL,
  name STRING,
  PRIMARY KEY (id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = 'test_insert_simple_kudu'
);


