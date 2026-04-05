-- ============================================================================
-- RBAC (Role-Based Access Control) Tables for CIS Trade Hive
-- ============================================================================
-- Version: 2.0
-- Created: 2026-04-05
-- Description: New RBAC tables to replace legacy cis_user, cis_user_group,
--              and cis_group_permissions tables.
--
-- Tables:
--   1. cis_user_info - User master (replaces cis_user)
--   2. cis_user_group_info - Group definitions (replaces cis_user_group)
--   3. cis_permission_info - Permission definitions (NEW)
--   4. cis_user_group_mapping_info - User to Group mapping (NEW - supports multi-group)
--   5. cis_group_permission_map - Group to Permission mapping (replaces cis_group_permissions)
--
-- Migration Notes:
--   - These tables exist in production (gmp_cis schema)
--   - Only cis_group_permission_map needs to be created
--   - Use RBAC_VERSION=v2 to switch to new tables
-- ============================================================================

-- ============================================================================
-- TABLE 1: cis_user_info (User Master)
-- ============================================================================
-- Note: This table already exists in production. DDL for reference only.
-- Records: ~24+ users
-- ============================================================================

-- DROP TABLE IF EXISTS gmp_cis.cis_user_info;

CREATE TABLE IF NOT EXISTS gmp_cis.cis_user_info (
    user_id STRING COMMENT 'Primary key - unique user identifier',
    login STRING COMMENT 'User login ID (e.g., TMP3RC, UNCSHR)',
    email STRING COMMENT 'User email address',
    name STRING COMMENT 'Full name of user',
    default_entity STRING COMMENT 'Default entity (e.g., UOBS)',
    last_login TIMESTAMP COMMENT 'Last login timestamp',
    is_active BOOLEAN COMMENT 'Whether user is active',
    is_deleted BOOLEAN COMMENT 'Soft delete flag',
    created_on TIMESTAMP COMMENT 'Record creation timestamp',
    created_by STRING COMMENT 'User who created the record',
    updated_on TIMESTAMP COMMENT 'Last update timestamp',
    updated_by STRING COMMENT 'User who last updated the record',
    PRIMARY KEY (user_id)
)
PARTITION BY HASH(user_id) PARTITIONS 4
COMMENT 'User master table for RBAC - stores user information'
STORED AS KUDU;


-- ============================================================================
-- TABLE 2: cis_user_group_info (Group Master)
-- ============================================================================
-- Note: This table already exists in production. DDL for reference only.
-- Records: 12 groups (SG-TRADER, SG-TCOE, CIS-SYSOPS, etc.)
-- ============================================================================

-- DROP TABLE IF EXISTS gmp_cis.cis_user_group_info;

CREATE TABLE IF NOT EXISTS gmp_cis.cis_user_group_info (
    user_group_id STRING COMMENT 'Primary key - unique group identifier',
    group_name STRING COMMENT 'Group name (e.g., SG-TRADER, SG-TCOE, CIS-SYSOPS)',
    description STRING COMMENT 'Group description',
    entity STRING COMMENT 'Entity (e.g., UOBS)',
    is_active BOOLEAN COMMENT 'Whether group is active',
    is_deleted BOOLEAN COMMENT 'Soft delete flag',
    created_on TIMESTAMP COMMENT 'Record creation timestamp',
    created_by STRING COMMENT 'User who created the record',
    updated_on TIMESTAMP COMMENT 'Last update timestamp',
    updated_by STRING COMMENT 'User who last updated the record',
    PRIMARY KEY (user_group_id)
)
PARTITION BY HASH(user_group_id) PARTITIONS 4
COMMENT 'Group master table for RBAC - defines user groups/roles'
STORED AS KUDU;


-- ============================================================================
-- TABLE 3: cis_permission_info (Permission Master)
-- ============================================================================
-- Note: This table already exists in production. DDL for reference only.
-- Records: 98 permissions
-- ============================================================================

-- DROP TABLE IF EXISTS gmp_cis.cis_permission_info;

CREATE TABLE IF NOT EXISTS gmp_cis.cis_permission_info (
    permission_id STRING COMMENT 'Primary key - unique permission identifier',
    permission_name STRING COMMENT 'Permission name (e.g., trade-create, portfolio-view)',
    entity STRING COMMENT 'Entity (e.g., UOBS)',
    description STRING COMMENT 'Permission description',
    is_active BOOLEAN COMMENT 'Whether permission is active',
    is_deleted BOOLEAN COMMENT 'Soft delete flag',
    created_on TIMESTAMP COMMENT 'Record creation timestamp',
    created_by STRING COMMENT 'User who created the record',
    updated_on TIMESTAMP COMMENT 'Last update timestamp',
    updated_by STRING COMMENT 'User who last updated the record',
    PRIMARY KEY (permission_id)
)
PARTITION BY HASH(permission_id) PARTITIONS 4
COMMENT 'Permission master table for RBAC - defines available permissions'
STORED AS KUDU;


-- ============================================================================
-- TABLE 4: cis_user_group_mapping_info (User to Group Mapping)
-- ============================================================================
-- Note: This table already exists in production. DDL for reference only.
-- Records: ~24+ mappings (supports users belonging to multiple groups)
-- ============================================================================

-- DROP TABLE IF EXISTS gmp_cis.cis_user_group_mapping_info;

CREATE TABLE IF NOT EXISTS gmp_cis.cis_user_group_mapping_info (
    user_group_mapping_id STRING COMMENT 'Primary key - unique mapping identifier',
    user_id STRING COMMENT 'Foreign key to cis_user_info.user_id',
    entity STRING COMMENT 'Entity (e.g., UOBS)',
    group_name STRING COMMENT 'Group name (e.g., SG-TRADER) - references cis_user_group_info.group_name',
    is_active BOOLEAN COMMENT 'Whether mapping is active',
    is_deleted BOOLEAN COMMENT 'Soft delete flag',
    created_on TIMESTAMP COMMENT 'Record creation timestamp',
    created_by STRING COMMENT 'User who created the record',
    updated_on TIMESTAMP COMMENT 'Last update timestamp',
    updated_by STRING COMMENT 'User who last updated the record',
    PRIMARY KEY (user_group_mapping_id)
)
PARTITION BY HASH(user_group_mapping_id) PARTITIONS 4
COMMENT 'User to Group mapping table - allows users to belong to multiple groups'
STORED AS KUDU;


-- ============================================================================
-- TABLE 5: cis_group_permission_map (Group to Permission Mapping)
-- ============================================================================
-- Records: 981 mappings
-- This is the main table that needs to be created/populated
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_group_permission_map;

CREATE TABLE gmp_cis.cis_group_permission_map (
    group_permission_id STRING COMMENT 'Primary key - unique mapping identifier',
    group_name STRING COMMENT 'Group name (e.g., SG-TRADER, CIS-SYSOPS)',
    permission_name STRING COMMENT 'Permission name (e.g., trade-create, portfolio-view)',
    entity STRING COMMENT 'Entity (e.g., UOBS)',
    mode STRING COMMENT 'Access mode: READ or READ_WRITE',
    description STRING COMMENT 'Description of permission for this group',
    is_active BOOLEAN COMMENT 'Whether mapping is active',
    is_deleted BOOLEAN COMMENT 'Soft delete flag',
    created_on TIMESTAMP COMMENT 'Record creation timestamp',
    created_by STRING COMMENT 'User who created the record',
    updated_on TIMESTAMP COMMENT 'Last update timestamp',
    updated_by STRING COMMENT 'User who last updated the record',
    PRIMARY KEY (group_permission_id)
)
PARTITION BY HASH(group_permission_id) PARTITIONS 4
COMMENT 'Group to Permission mapping table - defines what each group can do'
STORED AS KUDU;

-- Create index for faster lookups (if supported)
-- Note: Kudu doesn't support secondary indexes, but we optimize with partitioning


-- ============================================================================
-- SAMPLE DATA FOR TESTING (Docker Environment)
-- ============================================================================

-- Sample Users
UPSERT INTO gmp_cis.cis_user_info VALUES
('1', 'TMP3RC', 'prakash.hosalli1@uobgroup.com', 'PRAKASH HOSALLI', 'UOBS', NULL, true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('2', 'ADMIN', 'admin@uobgroup.com', 'System Admin', 'UOBS', NULL, true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM');

-- Sample Groups
UPSERT INTO gmp_cis.cis_user_group_info VALUES
('1', 'SG-TRADER', 'Singapore Trading Team', 'UOBS', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('2', 'SG-TCOE', 'Singapore Trade Center of Excellence', 'UOBS', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('3', 'CIS-SYSOPS', 'CIS System Operations - Full Access', 'UOBS', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM');

-- Sample Permissions
UPSERT INTO gmp_cis.cis_permission_info VALUES
('1', 'trade-list', 'UOBS', 'View trade list', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('2', 'trade-view', 'UOBS', 'View trade details', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('3', 'trade-create', 'UOBS', 'Create new trades', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('4', 'trade-edit', 'UOBS', 'Edit existing trades', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('5', 'trade-delete', 'UOBS', 'Delete trades', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('6', 'trade-approval', 'UOBS', 'Approve/reject trades', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('7', 'portfolio-list', 'UOBS', 'View portfolio list', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('8', 'portfolio-view', 'UOBS', 'View portfolio details', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('9', 'portfolio-create', 'UOBS', 'Create new portfolios', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('10', 'portfolio-edit', 'UOBS', 'Edit portfolios', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM');

-- Sample User-Group Mappings
UPSERT INTO gmp_cis.cis_user_group_mapping_info VALUES
('1', '1', 'UOBS', 'SG-TRADER', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('2', '2', 'UOBS', 'CIS-SYSOPS', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM');

-- Sample Group-Permission Mappings
UPSERT INTO gmp_cis.cis_group_permission_map VALUES
-- SG-TRADER: Can view and create trades
('1', 'SG-TRADER', 'trade-list', 'UOBS', 'READ', 'View trade list', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('2', 'SG-TRADER', 'trade-view', 'UOBS', 'READ', 'View trade details', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('3', 'SG-TRADER', 'trade-create', 'UOBS', 'READ_WRITE', 'Create trades', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('4', 'SG-TRADER', 'portfolio-list', 'UOBS', 'READ', 'View portfolios', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('5', 'SG-TRADER', 'portfolio-view', 'UOBS', 'READ', 'View portfolio details', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
-- CIS-SYSOPS: Full access to everything
('6', 'CIS-SYSOPS', 'trade-list', 'UOBS', 'READ_WRITE', 'Full trade access', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('7', 'CIS-SYSOPS', 'trade-view', 'UOBS', 'READ_WRITE', 'Full trade access', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('8', 'CIS-SYSOPS', 'trade-create', 'UOBS', 'READ_WRITE', 'Full trade access', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('9', 'CIS-SYSOPS', 'trade-edit', 'UOBS', 'READ_WRITE', 'Full trade access', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('10', 'CIS-SYSOPS', 'trade-delete', 'UOBS', 'READ_WRITE', 'Full trade access', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('11', 'CIS-SYSOPS', 'trade-approval', 'UOBS', 'READ_WRITE', 'Full trade access', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('12', 'CIS-SYSOPS', 'portfolio-list', 'UOBS', 'READ_WRITE', 'Full portfolio access', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('13', 'CIS-SYSOPS', 'portfolio-view', 'UOBS', 'READ_WRITE', 'Full portfolio access', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('14', 'CIS-SYSOPS', 'portfolio-create', 'UOBS', 'READ_WRITE', 'Full portfolio access', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('15', 'CIS-SYSOPS', 'portfolio-edit', 'UOBS', 'READ_WRITE', 'Full portfolio access', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM');


-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Count records in each table
SELECT 'cis_user_info' as table_name, COUNT(*) as record_count FROM gmp_cis.cis_user_info;
SELECT 'cis_user_group_info' as table_name, COUNT(*) as record_count FROM gmp_cis.cis_user_group_info;
SELECT 'cis_permission_info' as table_name, COUNT(*) as record_count FROM gmp_cis.cis_permission_info;
SELECT 'cis_user_group_mapping_info' as table_name, COUNT(*) as record_count FROM gmp_cis.cis_user_group_mapping_info;
SELECT 'cis_group_permission_map' as table_name, COUNT(*) as record_count FROM gmp_cis.cis_group_permission_map;

-- Get user with their groups and permissions
SELECT
    u.login,
    u.name,
    ugm.group_name,
    gpm.permission_name,
    gpm.mode
FROM gmp_cis.cis_user_info u
JOIN gmp_cis.cis_user_group_mapping_info ugm ON u.user_id = ugm.user_id
JOIN gmp_cis.cis_group_permission_map gpm ON ugm.group_name = gpm.group_name
WHERE u.is_active = true
  AND u.is_deleted = false
  AND ugm.is_active = true
  AND ugm.is_deleted = false
  AND gpm.is_active = true
  AND gpm.is_deleted = false
ORDER BY u.login, ugm.group_name, gpm.permission_name;
