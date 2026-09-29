-- ================================================================
-- Finalize ACL Tables - Use TEXT Format (Staging Tables as Production)
-- Database: cis
-- ================================================================

USE cis;

-- Drop any existing ORC tables
DROP TABLE IF EXISTS cis_user_group;
DROP TABLE IF EXISTS cis_user;
DROP TABLE IF EXISTS cis_permission;
DROP TABLE IF EXISTS cis_group_permissions;

-- Rename staging tables to production names
ALTER TABLE cis_user_group_stage RENAME TO cis_user_group;
ALTER TABLE cis_user_stage RENAME TO cis_user;
ALTER TABLE cis_permission_stage RENAME TO cis_permission;
ALTER TABLE cis_group_permissions_stage RENAME TO cis_group_permissions;

-- ================================================================
-- Verify Final Tables
-- ================================================================

SHOW TABLES;

SELECT '=== Row Counts ===' as section;
SELECT 'cis_user_group' as table_name, COUNT(*) as row_count FROM cis_user_group
UNION ALL
SELECT 'cis_user' as table_name, COUNT(*) as row_count FROM cis_user
UNION ALL
SELECT 'cis_permission' as table_name, COUNT(*) as row_count FROM cis_permission
UNION ALL
SELECT 'cis_group_permissions' as table_name, COUNT(*) as row_count FROM cis_group_permissions;

SELECT '=== Sample Data: cis_user_group ===' as section;
SELECT * FROM cis_user_group;

SELECT '=== Sample Data: cis_user ===' as section;
SELECT * FROM cis_user;

SELECT '=== Sample Data: cis_permission ===' as section;
SELECT * FROM cis_permission;

SELECT '=== Sample Data: cis_group_permissions (first 10) ===' as section;
SELECT * FROM cis_group_permissions LIMIT 10;
