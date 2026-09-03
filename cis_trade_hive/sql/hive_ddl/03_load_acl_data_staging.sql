-- ================================================================
-- Load ACL Data from CSV Files into Hive Tables (Using Staging Tables)
-- Database: cis
-- Strategy: Create text-based staging tables -> Load CSV -> Insert into ORC tables
-- ================================================================

USE cis;

-- ================================================================
-- Create Staging Tables (Text Format with Pipe Delimiter)
-- ================================================================

-- Drop staging tables if they exist
DROP TABLE IF EXISTS cis_user_group_stage;
DROP TABLE IF EXISTS cis_user_stage;
DROP TABLE IF EXISTS cis_permission_stage;
DROP TABLE IF EXISTS cis_group_permissions_stage;

-- Staging table for cis_user_group
CREATE TABLE cis_user_group_stage (
  cis_user_group_id INT,
  name              STRING,
  entity            STRING,
  description       STRING,
  is_deleted        BOOLEAN,
  updated_on        TIMESTAMP,
  updated_by        STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE;

-- Staging table for cis_user
CREATE TABLE cis_user_stage (
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
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE;

-- Staging table for cis_permission
CREATE TABLE cis_permission_stage (
  cis_permission_id INT,
  permission        STRING,
  description       STRING,
  is_deleted        BOOLEAN,
  updated_on        TIMESTAMP,
  updated_by        STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE;

-- Staging table for cis_group_permissions
CREATE TABLE cis_group_permissions_stage (
  cis_group_permissions_id INT,
  cis_user_group_id        INT,
  permission               STRING,
  read_write               STRING,
  is_deleted               BOOLEAN,
  updated_on               TIMESTAMP,
  updated_by               STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE;

-- ================================================================
-- Load CSV Data into Staging Tables
-- ================================================================

LOAD DATA LOCAL INPATH '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/acl_csv/cis_user_group.csv'
OVERWRITE INTO TABLE cis_user_group_stage;

LOAD DATA LOCAL INPATH '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/acl_csv/cis_user.csv'
OVERWRITE INTO TABLE cis_user_stage;

LOAD DATA LOCAL INPATH '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/acl_csv/cis_permission.csv'
OVERWRITE INTO TABLE cis_permission_stage;

LOAD DATA LOCAL INPATH '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/acl_csv/cis_group_permissions.csv'
OVERWRITE INTO TABLE cis_group_permissions_stage;

-- ================================================================
-- Insert from Staging Tables into ORC Tables
-- ================================================================

INSERT OVERWRITE TABLE cis_user_group
SELECT * FROM cis_user_group_stage;

INSERT OVERWRITE TABLE cis_user
SELECT * FROM cis_user_stage;

INSERT OVERWRITE TABLE cis_permission
SELECT * FROM cis_permission_stage;

INSERT OVERWRITE TABLE cis_group_permissions
SELECT * FROM cis_group_permissions_stage;

-- ================================================================
-- Verify Data Loaded Successfully
-- ================================================================

SELECT 'cis_user_group' as table_name, COUNT(*) as row_count FROM cis_user_group
UNION ALL
SELECT 'cis_user' as table_name, COUNT(*) as row_count FROM cis_user
UNION ALL
SELECT 'cis_permission' as table_name, COUNT(*) as row_count FROM cis_permission
UNION ALL
SELECT 'cis_group_permissions' as table_name, COUNT(*) as row_count FROM cis_group_permissions;

-- ================================================================
-- Sample Data Check
-- ================================================================

SELECT '=== cis_user_group ===' as section;
SELECT * FROM cis_user_group LIMIT 5;

SELECT '=== cis_user ===' as section;
SELECT * FROM cis_user LIMIT 5;

SELECT '=== cis_permission ===' as section;
SELECT * FROM cis_permission LIMIT 5;

SELECT '=== cis_group_permissions ===' as section;
SELECT * FROM cis_group_permissions LIMIT 5;

-- ================================================================
-- Cleanup Staging Tables (Optional - Uncomment to remove)
-- ================================================================

-- DROP TABLE IF EXISTS cis_user_group_stage;
-- DROP TABLE IF EXISTS cis_user_stage;
-- DROP TABLE IF EXISTS cis_permission_stage;
-- DROP TABLE IF EXISTS cis_group_permissions_stage;
