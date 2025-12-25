-- ================================================================
-- Hive DDL for ACL (Access Control List) Tables
-- Converted from Excel schema: ACL_TABLES.xlsx
-- Database: cis
-- Storage: ORC format with SNAPPY compression
-- ================================================================

USE cis;

-- ================================================================
-- Table: cis_user
-- Purpose: User information and authentication
-- Primary Key: (cis_user_id)
-- ================================================================

CREATE TABLE IF NOT EXISTS cis_user (
  cis_user_id       INT           COMMENT 'Unique user identifier',
  login             STRING        COMMENT 'User login ID (e.g., TMP4UG)',
  name              STRING        COMMENT 'Full name of the user',
  entity            STRING        COMMENT 'Organization/Entity (e.g., UOBS)',
  email             STRING        COMMENT 'User email address',
  domain            STRING        COMMENT 'Domain name (e.g., NTSGPDOM)',
  cis_user_group_id INT           COMMENT 'Foreign key to cis_user_group',
  is_deleted        BOOLEAN       COMMENT 'Soft delete flag',
  enabled           BOOLEAN       COMMENT 'Is user account active',
  last_login        TIMESTAMP     COMMENT 'Last login timestamp',
  created_on        TIMESTAMP     COMMENT 'Creation timestamp',
  created_by        STRING        COMMENT 'User who created this record',
  updated_on        TIMESTAMP     COMMENT 'Last update timestamp',
  updated_by        STRING        COMMENT 'User who last updated this record'
)
COMMENT 'User information and authentication - Primary Key: (cis_user_id)'
CLUSTERED BY (cis_user_id) INTO 8 BUCKETS
STORED AS ORC
TBLPROPERTIES (
  'orc.compress'='SNAPPY',
  'orc.create.index'='true'
);


-- ================================================================
-- Table: cis_user_group
-- Purpose: User groups for role-based access control
-- Primary Key: (cis_user_group_id)
-- ================================================================

CREATE TABLE IF NOT EXISTS cis_user_group (
  cis_user_group_id INT           COMMENT 'Unique user group identifier',
  name              STRING        COMMENT 'Group name (e.g., CIS-DEV)',
  entity            STRING        COMMENT 'Organization/Entity',
  description       STRING        COMMENT 'Group description',
  is_deleted        BOOLEAN       COMMENT 'Soft delete flag',
  updated_on        TIMESTAMP     COMMENT 'Last update timestamp',
  updated_by        STRING        COMMENT 'User who last updated this record'
)
COMMENT 'User groups for RBAC - Primary Key: (cis_user_group_id)'
CLUSTERED BY (cis_user_group_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
  'orc.compress'='SNAPPY',
  'orc.create.index'='true'
);


-- ================================================================
-- Table: cis_permission
-- Purpose: Available permissions in the system
-- Primary Key: (cis_permission_id)
-- ================================================================

CREATE TABLE IF NOT EXISTS cis_permission (
  cis_permission_id INT           COMMENT 'Unique permission identifier',
  permission        STRING        COMMENT 'Permission name (e.g., cis-report, cis-trade)',
  description       STRING        COMMENT 'Permission description',
  is_deleted        BOOLEAN       COMMENT 'Soft delete flag',
  updated_on        TIMESTAMP     COMMENT 'Last update timestamp',
  updated_by        STRING        COMMENT 'User who last updated this record'
)
COMMENT 'Available system permissions - Primary Key: (cis_permission_id)'
CLUSTERED BY (cis_permission_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
  'orc.compress'='SNAPPY',
  'orc.create.index'='true'
);


-- ================================================================
-- Table: cis_group_permissions
-- Purpose: Maps user groups to permissions with access levels
-- Primary Key: (cis_group_permissions_id)
-- Foreign Keys: cis_user_group_id, permission
-- ================================================================

CREATE TABLE IF NOT EXISTS cis_group_permissions (
  cis_group_permissions_id INT           COMMENT 'Unique mapping identifier',
  cis_user_group_id        INT           COMMENT 'Foreign key to cis_user_group',
  permission               STRING        COMMENT 'Permission name',
  read_write               STRING        COMMENT 'Access level: READ, WRITE, READ_WRITE',
  is_deleted               BOOLEAN       COMMENT 'Soft delete flag',
  updated_on               TIMESTAMP     COMMENT 'Last update timestamp',
  updated_by               STRING        COMMENT 'User who last updated this record'
)
COMMENT 'Group-to-permission mapping - Primary Key: (cis_group_permissions_id)'
CLUSTERED BY (cis_user_group_id) INTO 8 BUCKETS
STORED AS ORC
TBLPROPERTIES (
  'orc.compress'='SNAPPY',
  'orc.create.index'='true'
);


-- ================================================================
-- Verification
-- ================================================================

SHOW TABLES;

-- ================================================================
-- Notes:
-- ================================================================
-- 1. All timestamps are stored as TIMESTAMP type (nanosecond precision in Hive)
-- 2. Primary keys documented in comments (enforce at application layer)
-- 3. Foreign keys documented in comments (enforce at application layer)
-- 4. Soft delete pattern using is_deleted flag
-- 5. Audit trail with updated_on and updated_by
-- 6. Bucketing strategy for distributed storage and query optimization
-- ================================================================
