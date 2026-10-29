-- ================================================================
-- Hive DDL for ACL Tables - Simple Version (No Bucketing)
-- Converted from Excel schema: ACL_TABLES.xlsx
-- Database: cis
-- Storage: ORC format with SNAPPY compression
-- Note: Simplified for easier data loading
-- ================================================================

USE cis;

-- Drop existing bucketed tables
DROP TABLE IF EXISTS cis_user;
DROP TABLE IF EXISTS cis_user_group;
DROP TABLE IF EXISTS cis_permission;
DROP TABLE IF EXISTS cis_group_permissions;

-- ================================================================
-- Table: cis_user_group
-- ================================================================

CREATE TABLE cis_user_group (
  cis_user_group_id INT,
  name              STRING,
  entity            STRING,
  description       STRING,
  is_deleted        BOOLEAN,
  updated_on        TIMESTAMP,
  updated_by        STRING
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='SNAPPY');

-- ================================================================
-- Table: cis_user
-- ================================================================

CREATE TABLE cis_user (
  cis_user_id       INT,
  login             STRING,
  name              STRING,
  entity            STRING,
  email             STRING,
  domain            STRING,
  cis_user_group_id INT,
  is_deleted        BOOLEAN,
  enabled           BOOLEAN,
  last_login        TIMESTAMP,
  created_on        TIMESTAMP,
  created_by        STRING,
  updated_on        TIMESTAMP,
  updated_by        STRING
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='SNAPPY');

-- ================================================================
-- Table: cis_permission
-- ================================================================

CREATE TABLE cis_permission (
  cis_permission_id INT,
  permission        STRING,
  description       STRING,
  is_deleted        BOOLEAN,
  updated_on        TIMESTAMP,
  updated_by        STRING
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='SNAPPY');

-- ================================================================
-- Table: cis_group_permissions
-- ================================================================

CREATE TABLE cis_group_permissions (
  cis_group_permissions_id INT,
  cis_user_group_id        INT,
  permission               STRING,
  read_write               STRING,
  is_deleted               BOOLEAN,
  updated_on               TIMESTAMP,
  updated_by               STRING
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='SNAPPY');

SHOW TABLES;
