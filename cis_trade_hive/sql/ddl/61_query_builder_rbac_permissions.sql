-- ============================================================================
-- Query Builder RBAC Permissions
-- ============================================================================
-- Run after 52_rbac_seed_permissions.sql
-- Adds 3 permissions + maps them to CIS-SYSOPS (full access) and
-- SG-TRADER (run-only, no admin).
--
-- After running: log out and log back in for session to pick up new perms.
-- ============================================================================


-- ============================================================================
-- SECTION 1: cis_permission_info — 3 query-builder permissions
-- ============================================================================

UPSERT INTO gmp_cis.cis_permission_info
(permission_id, permission_name, entity, description, is_active, is_deleted, created_on, created_by, updated_on, updated_by)
VALUES
('36', 'query-builder-run',    'UOBS', 'Run queries and export results in Query Builder',       true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('37', 'query-builder-manage', 'UOBS', 'Save and delete report templates in Query Builder',     true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('38', 'query-builder-admin',  'UOBS', 'Access raw SQL editor in Query Builder (admin only)',   true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM');


-- ============================================================================
-- SECTION 2: cis_group_permission_map — CIS-SYSOPS (full access)
-- ============================================================================

UPSERT INTO gmp_cis.cis_group_permission_map
(group_permission_id, group_name, permission_name, entity, mode, description, is_active, is_deleted, created_on, created_by, updated_on, updated_by)
VALUES
('55', 'CIS-SYSOPS', 'query-builder-run',    'UOBS', 'READ_WRITE', 'Full Query Builder access',      true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('56', 'CIS-SYSOPS', 'query-builder-manage', 'UOBS', 'READ_WRITE', 'Manage Query Builder templates', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('57', 'CIS-SYSOPS', 'query-builder-admin',  'UOBS', 'READ_WRITE', 'Query Builder SQL editor',       true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM');


-- ============================================================================
-- SECTION 3: cis_group_permission_map — SG-TRADER (run + save, no SQL editor)
-- ============================================================================

UPSERT INTO gmp_cis.cis_group_permission_map
(group_permission_id, group_name, permission_name, entity, mode, description, is_active, is_deleted, created_on, created_by, updated_on, updated_by)
VALUES
('58', 'SG-TRADER', 'query-builder-run',    'UOBS', 'READ', 'Run queries in Query Builder',          true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('59', 'SG-TRADER', 'query-builder-manage', 'UOBS', 'WRITE', 'Save report templates',                true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM');


-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT permission_id, permission_name, description
FROM gmp_cis.cis_permission_info
WHERE permission_name LIKE 'query-builder%'
ORDER BY permission_id;

SELECT group_name, permission_name, mode
FROM gmp_cis.cis_group_permission_map
WHERE permission_name LIKE 'query-builder%'
  AND is_active = true AND is_deleted = false
ORDER BY group_name, permission_name;
