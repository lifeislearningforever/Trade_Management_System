-- ================================================================
-- Load ACL Data from CSV Files into Hive Tables
-- Database: cis
-- ================================================================

USE cis;

-- ================================================================
-- Load cis_user_group (1 row)
-- ================================================================
LOAD DATA LOCAL INPATH '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/acl_csv/cis_user_group.csv'
OVERWRITE INTO TABLE cis_user_group;

-- ================================================================
-- Load cis_user (3 rows)
-- ================================================================
LOAD DATA LOCAL INPATH '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/acl_csv/cis_user.csv'
OVERWRITE INTO TABLE cis_user;

-- ================================================================
-- Load cis_permission (7 rows)
-- ================================================================
LOAD DATA LOCAL INPATH '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/acl_csv/cis_permission.csv'
OVERWRITE INTO TABLE cis_permission;

-- ================================================================
-- Load cis_group_permissions (30 rows)
-- ================================================================
LOAD DATA LOCAL INPATH '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/acl_csv/cis_group_permissions.csv'
OVERWRITE INTO TABLE cis_group_permissions;

-- ================================================================
-- Verify data loaded successfully
-- ================================================================
SELECT 'cis_user_group' as table_name, COUNT(*) as row_count FROM cis_user_group
UNION ALL
SELECT 'cis_user' as table_name, COUNT(*) as row_count FROM cis_user
UNION ALL
SELECT 'cis_permission' as table_name, COUNT(*) as row_count FROM cis_permission
UNION ALL
SELECT 'cis_group_permissions' as table_name, COUNT(*) as row_count FROM cis_group_permissions;
