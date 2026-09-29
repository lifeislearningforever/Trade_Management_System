-- ================================================================
-- Manual INSERT Approach - Create Empty ORC Tables and Insert Data
-- Database: cis
-- ================================================================

USE cis;

-- Create empty ORC table for cis_user_group
CREATE TABLE IF NOT EXISTS cis_user_group (
  cis_user_group_id INT,
  name              STRING,
  entity            STRING,
  description       STRING,
  is_deleted        BOOLEAN,
  updated_on        TIMESTAMP,
  updated_by        STRING
)
STORED AS ORC;

-- Try simple INSERT with explicit casting
INSERT INTO TABLE cis_user_group
SELECT
  CAST(cis_user_group_id AS INT),
  CAST(name AS STRING),
  CAST(entity AS STRING),
  CAST(description AS STRING),
  CAST(is_deleted AS BOOLEAN),
  CAST(updated_on AS TIMESTAMP),
  CAST(updated_by AS STRING)
FROM cis_user_group_stage;

-- Verify
SELECT * FROM cis_user_group;
SELECT COUNT(*) as count FROM cis_user_group;
