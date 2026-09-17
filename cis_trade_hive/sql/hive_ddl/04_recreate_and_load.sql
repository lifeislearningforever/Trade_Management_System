-- ================================================================
-- Recreate ORC Tables and Load Data from Staging Tables
-- Database: cis
-- ================================================================

USE cis;

-- Drop and recreate ORC tables
DROP TABLE IF EXISTS cis_user_group;
DROP TABLE IF EXISTS cis_user;
DROP TABLE IF EXISTS cis_permission;
DROP TABLE IF EXISTS cis_group_permissions;

-- ================================================================
-- Recreate Tables as ORC (Simplified - no custom properties)
-- ================================================================

CREATE TABLE cis_user_group
STORED AS ORC
AS SELECT * FROM cis_user_group_stage;

CREATE TABLE cis_user
STORED AS ORC
AS SELECT * FROM cis_user_stage;

CREATE TABLE cis_permission
STORED AS ORC
AS SELECT * FROM cis_permission_stage;

CREATE TABLE cis_group_permissions
STORED AS ORC
AS SELECT * FROM cis_group_permissions_stage;

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

SELECT * FROM cis_user_group;
SELECT * FROM cis_user LIMIT 5;
SELECT * FROM cis_permission LIMIT 5;
SELECT * FROM cis_group_permissions LIMIT 10;
