
-- Kudu DDL for UDF Values
CREATE TABLE IF NOT EXISTS cis.cis_udf_value (
  entity_type      STRING          NOT NULL,
  entity_id        BIGINT          NOT NULL,
  field_name       STRING          NOT NULL,
  udf_id           BIGINT          NOT NULL,
  value_string     STRING          NULL,
  value_int        BIGINT          NULL,
  value_decimal    DECIMAL(38,10)  NULL,
  value_bool       BOOLEAN         NULL,
  value_datetime   TIMESTAMP       NULL,
  is_active        BOOLEAN         NOT NULL DEFAULT TRUE,
  created_by       STRING          NOT NULL,
  created_at       TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  updated_by       STRING          NOT NULL,
  updated_at       TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (entity_type, entity_id, field_name)
)
PARTITION BY HASH (entity_type, entity_id) PARTITIONS 16
STORED AS KUDU;

-- Kudu DDL for UDF Multi-Select Values
CREATE TABLE IF NOT EXISTS cis.cis_udf_value_multi (
  entity_type      STRING    NOT NULL,
  entity_id        BIGINT    NOT NULL,
  field_name       STRING    NOT NULL,
  option_value     STRING    NOT NULL,
  udf_id           BIGINT    NOT NULL,
  is_active        BOOLEAN   NOT NULL DEFAULT TRUE,
  created_by       STRING    NOT NULL,
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  updated_by       STRING    NOT NULL,
  updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (entity_type, entity_id, field_name, option_value)
)
PARTITION BY HASH (entity_type, entity_id) PARTITIONS 16
STORED AS KUDU;

-- Kudu DDL for UDF Options
CREATE TABLE IF NOT EXISTS cis.cis_udf_option (
  udf_id        BIGINT    NOT NULL,
  option_value  STRING    NOT NULL,
  display_order INT       NOT NULL DEFAULT 0,
  is_active     BOOLEAN   NOT NULL DEFAULT TRUE,
  created_by    STRING    NOT NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  updated_by    STRING    NOT NULL,
  updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (udf_id, option_value)
)
PARTITION BY HASH (udf_id) PARTITIONS 8
STORED AS KUDU;

-- Optional: Definitions (if moving to Kudu)
CREATE TABLE IF NOT EXISTS cis.cis_udf_definition (
  udf_id            BIGINT          NOT NULL,
  field_name        STRING          NOT NULL,
  label             STRING          NOT NULL,
  description       STRING          NULL,
  field_type        STRING          NOT NULL,
  entity_type       STRING          NOT NULL,
  is_required       BOOLEAN         NOT NULL DEFAULT FALSE,
  is_unique         BOOLEAN         NOT NULL DEFAULT FALSE,
  max_length        INT             NULL,
  min_value_decimal DECIMAL(38,10)  NULL,
  max_value_decimal DECIMAL(38,10)  NULL,
  display_order     INT             NOT NULL DEFAULT 0,
  group_name        STRING          NULL,
  default_string    STRING          NULL,
  default_int       BIGINT          NULL,
  default_decimal   DECIMAL(38,10)  NULL,
  default_bool      BOOLEAN         NULL,
  default_datetime  TIMESTAMP       NULL,
  is_active         BOOLEAN         NOT NULL DEFAULT TRUE,
  created_by        STRING          NOT NULL,
  created_at        TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  updated_by        STRING          NOT NULL,
  updated_at        TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (udf_id)
)
PARTITION BY HASH (udf_id) PARTITIONS 8
STORED AS KUDU;
