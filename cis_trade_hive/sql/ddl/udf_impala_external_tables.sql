-- =====================================================
-- UDF Impala External Tables (pointing to Kudu tables)
-- =====================================================

USE gmp_cis;

-- External table for UDF definitions
CREATE EXTERNAL TABLE IF NOT EXISTS cis_udf_definition (
  udf_id BIGINT,
  field_name STRING,
  label STRING,
  description STRING,
  field_type STRING,
  entity_type STRING,
  is_required BOOLEAN,
  is_unique BOOLEAN,
  max_length INT,
  min_value_decimal STRING,
  max_value_decimal STRING,
  display_order INT,
  group_name STRING,
  default_string STRING,
  default_int BIGINT,
  default_decimal STRING,
  default_bool BOOLEAN,
  default_datetime BIGINT,
  is_active BOOLEAN,
  created_by STRING,
  created_at BIGINT,
  updated_by STRING,
  updated_at BIGINT,
  PRIMARY KEY (entity_type, field_name)
)
STORED AS KUDU
TBLPROPERTIES (
  'kudu.table_name' = 'cis_udf_definition_kudu'
);

-- External table for UDF dropdown options
CREATE EXTERNAL TABLE IF NOT EXISTS cis_udf_option (
  udf_id BIGINT,
  option_value STRING,
  display_order INT,
  is_active BOOLEAN,
  created_by STRING,
  created_at BIGINT,
  updated_by STRING,
  updated_at BIGINT,
  PRIMARY KEY (udf_id, option_value)
)
STORED AS KUDU
TBLPROPERTIES (
  'kudu.table_name' = 'cis_udf_option_kudu'
);

-- External table for UDF values (single values)
CREATE EXTERNAL TABLE IF NOT EXISTS cis_udf_value (
  entity_type STRING,
  entity_id BIGINT,
  field_name STRING,
  udf_id BIGINT,
  value_string STRING,
  value_int BIGINT,
  value_decimal STRING,
  value_bool BOOLEAN,
  value_datetime BIGINT,
  is_active BOOLEAN,
  created_by STRING,
  created_at BIGINT,
  updated_by STRING,
  updated_at BIGINT,
  PRIMARY KEY (entity_id, entity_type, field_name)
)
STORED AS KUDU
TBLPROPERTIES (
  'kudu.table_name' = 'cis_udf_value_kudu'
);

-- External table for UDF multi-select values
CREATE EXTERNAL TABLE IF NOT EXISTS cis_udf_value_multi (
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
  PRIMARY KEY (entity_id, entity_type, field_name, option_value)
)
STORED AS KUDU
TBLPROPERTIES (
  'kudu.table_name' = 'cis_udf_value_multi_kudu'
);

-- Verify tables created
SHOW TABLES LIKE 'cis_udf%';
