-- ================================================================
-- Hive DDL for UDF (User Defined Fields) Tables
-- Converted from Kudu DDL - Simplified Version (Non-Transactional)
-- Database: cis
-- Storage: ORC format
-- ================================================================

USE cis;

-- ================================================================
-- Table: cis_udf_value
-- Purpose: Stores UDF values for entities (single-value fields)
-- Primary Key: (entity_type, entity_id, field_name)
-- ================================================================

CREATE TABLE IF NOT EXISTS cis_udf_value (
  entity_type      STRING          COMMENT 'Type of entity (e.g., PORTFOLIO, TRADE, ORDER)',
  entity_id        BIGINT          COMMENT 'ID of the entity',
  field_name       STRING          COMMENT 'UDF field name',
  udf_id           BIGINT          COMMENT 'Reference to UDF definition',
  value_string     STRING          COMMENT 'String value for text fields',
  value_int        BIGINT          COMMENT 'Integer value for numeric fields',
  value_decimal    DECIMAL(38,10)  COMMENT 'Decimal value for precise numeric fields',
  value_bool       BOOLEAN         COMMENT 'Boolean value for yes/no fields',
  value_datetime   TIMESTAMP       COMMENT 'Timestamp value for date/time fields',
  is_active        BOOLEAN         COMMENT 'Soft delete flag',
  created_by       STRING          COMMENT 'User who created the record',
  created_at       TIMESTAMP       COMMENT 'Creation timestamp',
  updated_by       STRING          COMMENT 'User who last updated the record',
  updated_at       TIMESTAMP       COMMENT 'Last update timestamp'
)
COMMENT 'UDF single-value storage table - Primary Key: (entity_type, entity_id, field_name)'
CLUSTERED BY (entity_type, entity_id) INTO 16 BUCKETS
STORED AS ORC
TBLPROPERTIES (
  'orc.compress'='SNAPPY',
  'orc.create.index'='true'
);


-- ================================================================
-- Table: cis_udf_value_multi
-- Purpose: Stores UDF multi-select values for entities
-- Primary Key: (entity_type, entity_id, field_name, option_value)
-- ================================================================

CREATE TABLE IF NOT EXISTS cis_udf_value_multi (
  entity_type      STRING    COMMENT 'Type of entity',
  entity_id        BIGINT    COMMENT 'ID of the entity',
  field_name       STRING    COMMENT 'UDF field name',
  option_value     STRING    COMMENT 'Selected option value',
  udf_id           BIGINT    COMMENT 'Reference to UDF definition',
  is_active        BOOLEAN   COMMENT 'Soft delete flag',
  created_by       STRING    COMMENT 'User who created the record',
  created_at       TIMESTAMP COMMENT 'Creation timestamp',
  updated_by       STRING    COMMENT 'User who last updated the record',
  updated_at       TIMESTAMP COMMENT 'Last update timestamp'
)
COMMENT 'UDF multi-select value storage table - Primary Key: (entity_type, entity_id, field_name, option_value)'
CLUSTERED BY (entity_type, entity_id) INTO 16 BUCKETS
STORED AS ORC
TBLPROPERTIES (
  'orc.compress'='SNAPPY',
  'orc.create.index'='true'
);


-- ================================================================
-- Table: cis_udf_option
-- Purpose: Stores available options for dropdown/multi-select UDF fields
-- Primary Key: (udf_id, option_value)
-- ================================================================

CREATE TABLE IF NOT EXISTS cis_udf_option (
  udf_id        BIGINT    COMMENT 'Reference to UDF definition',
  option_value  STRING    COMMENT 'Option value/code',
  display_order INT       COMMENT 'Display order in dropdown',
  is_active     BOOLEAN   COMMENT 'Soft delete flag',
  created_by    STRING    COMMENT 'User who created the record',
  created_at    TIMESTAMP COMMENT 'Creation timestamp',
  updated_by    STRING    COMMENT 'User who last updated the record',
  updated_at    TIMESTAMP COMMENT 'Last update timestamp'
)
COMMENT 'UDF dropdown/multi-select options - Primary Key: (udf_id, option_value)'
CLUSTERED BY (udf_id) INTO 8 BUCKETS
STORED AS ORC
TBLPROPERTIES (
  'orc.compress'='SNAPPY',
  'orc.create.index'='true'
);


-- ================================================================
-- Table: cis_udf_definition
-- Purpose: Defines UDF fields and their properties
-- Primary Key: (udf_id)
-- ================================================================

CREATE TABLE IF NOT EXISTS cis_udf_definition (
  udf_id            BIGINT          COMMENT 'Unique identifier for UDF',
  field_name        STRING          COMMENT 'Field name (used in code)',
  label             STRING          COMMENT 'Display label',
  description       STRING          COMMENT 'Field description/help text',
  field_type        STRING          COMMENT 'Data type: STRING, INT, DECIMAL, BOOLEAN, DATETIME, DROPDOWN, MULTISELECT',
  entity_type       STRING          COMMENT 'Entity type this UDF applies to',
  is_required       BOOLEAN         COMMENT 'Is field mandatory',
  is_unique         BOOLEAN         COMMENT 'Must value be unique',
  max_length        INT             COMMENT 'Max length for string fields',
  min_value_decimal DECIMAL(38,10)  COMMENT 'Minimum value for numeric fields',
  max_value_decimal DECIMAL(38,10)  COMMENT 'Maximum value for numeric fields',
  display_order     INT             COMMENT 'Display order in forms',
  group_name        STRING          COMMENT 'Grouping for related fields',
  default_string    STRING          COMMENT 'Default string value',
  default_int       BIGINT          COMMENT 'Default integer value',
  default_decimal   DECIMAL(38,10)  COMMENT 'Default decimal value',
  default_bool      BOOLEAN         COMMENT 'Default boolean value',
  default_datetime  TIMESTAMP       COMMENT 'Default datetime value',
  is_active         BOOLEAN         COMMENT 'Soft delete flag',
  created_by        STRING          COMMENT 'User who created the record',
  created_at        TIMESTAMP       COMMENT 'Creation timestamp',
  updated_by        STRING          COMMENT 'User who last updated the record',
  updated_at        TIMESTAMP       COMMENT 'Last update timestamp'
)
COMMENT 'UDF field definitions - Primary Key: (udf_id)'
CLUSTERED BY (udf_id) INTO 8 BUCKETS
STORED AS ORC
TBLPROPERTIES (
  'orc.compress'='SNAPPY',
  'orc.create.index'='true'
);


-- ================================================================
-- Verification
-- ================================================================

SHOW TABLES;
