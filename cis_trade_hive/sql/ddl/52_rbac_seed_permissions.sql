-- ============================================================================
-- RBAC Seed Data: Full Permission Set
-- ============================================================================
-- Version: 1.0
-- Created: 2026-04-10
-- Description: Complete permission definitions from permissions_map.py
--              and CIS-SYSOPS / SG-TRADER group mappings.
--
-- Run this after 50_rbac_tables_kudu.sql to populate all permissions.
-- Note: IDs 1-10 are reserved by 50_rbac_tables_kudu.sql sample data.
--       This file uses IDs 11+ for permissions and 16+ for group-perm map.
--
-- After running: log out and log back in for session to pick up new perms.
-- ============================================================================


-- ============================================================================
-- SECTION 1: cis_permission_info — Full permission set
-- ============================================================================
-- IDs 1–10 already exist in sample data (trade/portfolio permissions).
-- This UPSERT covers all permissions from permissions_map.py including rbac-admin.
-- Safe to re-run: UPSERT updates existing rows without error.
-- ============================================================================

UPSERT INTO gmp_cis.cis_permission_info
(permission_id, permission_name, entity, description, is_active, is_deleted, created_on, created_by, updated_on, updated_by)
VALUES
-- Core / System
('11', 'audit-logs-read',        'UOBS', 'View system audit logs',                              true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('12', 'rbac-admin',             'UOBS', 'Full RBAC administration (users, groups, permissions)', true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Portfolio (IDs 7-10 already in sample; add remaining)
('13', 'portfolio-approval',     'UOBS', 'Approve or reject portfolios',                        true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Trade (IDs 1-6 already in sample; add remaining)
('14', 'position-list',          'UOBS', 'View trade positions / AVP',                          true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('15', 'cash-flow-list',         'UOBS', 'View cash flows',                                     true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('16', 'cash-flow-create',       'UOBS', 'Create and edit cash flows',                          true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('17', 'cash-flow-approval',     'UOBS', 'Approve or reject cash flows',                        true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Market Data
('18', 'market-data-dashboard',  'UOBS', 'View market data dashboard',                          true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('19', 'fx-rates-list',          'UOBS', 'View FX rates',                                       true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('20', 'equity-prices-list',     'UOBS', 'View equity prices',                                  true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('21', 'equity-prices-create',   'UOBS', 'Create and edit equity prices',                       true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Reference Data
('22', 'currencies-list',        'UOBS', 'View currencies',                                     true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('23', 'countries-list',         'UOBS', 'View countries',                                      true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('24', 'calendars-list',         'UOBS', 'View trading calendars',                              true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('25', 'parties-list',           'UOBS', 'View counterparties and parties',                     true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('26', 'parties-create',         'UOBS', 'Create and edit counterparties and parties',          true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('27', 'corp-action-list',       'UOBS', 'View corporate actions',                              true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('28', 'corp-action-create',     'UOBS', 'Create and edit corporate actions',                   true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Securities
('29', 'securities-list',        'UOBS', 'View security master',                                true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('30', 'securities-create',      'UOBS', 'Create and edit securities',                          true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- UDF
('31', 'udf-list',               'UOBS', 'View user-defined fields',                            true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('32', 'udf-create',             'UOBS', 'Create and edit user-defined fields',                 true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- File Upload
('33', 'upload-list',            'UOBS', 'View and manage file uploads',                        true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Lookup Tables
('34', 'lookup-tables-list',     'UOBS', 'View lookup/reference tables',                        true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('35', 'lookup-tables-edit',     'UOBS', 'Add, edit, delete rows in lookup tables',             true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM');


-- ============================================================================
-- SECTION 2: cis_group_permission_map — CIS-SYSOPS (superuser full access)
-- ============================================================================
-- IDs 1-15 already exist in sample data (SG-TRADER + partial CIS-SYSOPS).
-- This adds the missing permissions for CIS-SYSOPS.
-- ============================================================================

UPSERT INTO gmp_cis.cis_group_permission_map
(group_permission_id, group_name, permission_name, entity, mode, description, is_active, is_deleted, created_on, created_by, updated_on, updated_by)
VALUES
-- CIS-SYSOPS: existing in sample (1-15) are trade/portfolio READ_WRITE
-- Adding all remaining permissions for CIS-SYSOPS

-- Core / RBAC Admin
('16', 'CIS-SYSOPS', 'audit-logs-read',       'UOBS', 'READ_WRITE', 'Full audit log access',         true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('17', 'CIS-SYSOPS', 'rbac-admin',            'UOBS', 'READ_WRITE', 'Full RBAC administration',      true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Portfolio (portfolio-approval missing from sample)
('18', 'CIS-SYSOPS', 'portfolio-approval',    'UOBS', 'READ_WRITE', 'Full portfolio access',         true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Trade extras
('19', 'CIS-SYSOPS', 'position-list',         'UOBS', 'READ_WRITE', 'Full position access',          true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('20', 'CIS-SYSOPS', 'cash-flow-list',        'UOBS', 'READ_WRITE', 'Full cash flow access',         true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('21', 'CIS-SYSOPS', 'cash-flow-create',      'UOBS', 'READ_WRITE', 'Full cash flow access',         true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('22', 'CIS-SYSOPS', 'cash-flow-approval',    'UOBS', 'READ_WRITE', 'Full cash flow access',         true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Market Data
('23', 'CIS-SYSOPS', 'market-data-dashboard', 'UOBS', 'READ_WRITE', 'Full market data access',       true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('24', 'CIS-SYSOPS', 'fx-rates-list',         'UOBS', 'READ_WRITE', 'Full FX rates access',          true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('25', 'CIS-SYSOPS', 'equity-prices-list',    'UOBS', 'READ_WRITE', 'Full equity prices access',     true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('26', 'CIS-SYSOPS', 'equity-prices-create',  'UOBS', 'READ_WRITE', 'Full equity prices access',     true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Reference Data
('27', 'CIS-SYSOPS', 'currencies-list',       'UOBS', 'READ_WRITE', 'Full reference data access',    true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('28', 'CIS-SYSOPS', 'countries-list',        'UOBS', 'READ_WRITE', 'Full reference data access',    true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('29', 'CIS-SYSOPS', 'calendars-list',        'UOBS', 'READ_WRITE', 'Full reference data access',    true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('30', 'CIS-SYSOPS', 'parties-list',          'UOBS', 'READ_WRITE', 'Full parties access',           true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('31', 'CIS-SYSOPS', 'parties-create',        'UOBS', 'READ_WRITE', 'Full parties access',           true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('32', 'CIS-SYSOPS', 'corp-action-list',      'UOBS', 'READ_WRITE', 'Full corp actions access',      true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('33', 'CIS-SYSOPS', 'corp-action-create',    'UOBS', 'READ_WRITE', 'Full corp actions access',      true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Securities
('34', 'CIS-SYSOPS', 'securities-list',       'UOBS', 'READ_WRITE', 'Full securities access',        true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('35', 'CIS-SYSOPS', 'securities-create',     'UOBS', 'READ_WRITE', 'Full securities access',        true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- UDF
('36', 'CIS-SYSOPS', 'udf-list',              'UOBS', 'READ_WRITE', 'Full UDF access',               true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('37', 'CIS-SYSOPS', 'udf-create',            'UOBS', 'READ_WRITE', 'Full UDF access',               true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Upload
('38', 'CIS-SYSOPS', 'upload-list',           'UOBS', 'READ_WRITE', 'Full upload access',            true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Lookup Tables
('39', 'CIS-SYSOPS', 'lookup-tables-list',    'UOBS', 'READ_WRITE', 'Full lookup tables access',     true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('40', 'CIS-SYSOPS', 'lookup-tables-edit',    'UOBS', 'READ_WRITE', 'Full lookup tables access',     true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM');


-- ============================================================================
-- SECTION 3: cis_group_permission_map — SG-TRADER (standard trader access)
-- ============================================================================
-- IDs 1-5 already exist for SG-TRADER in sample data.
-- Adding the standard set a trader would need.
-- ============================================================================

UPSERT INTO gmp_cis.cis_group_permission_map
(group_permission_id, group_name, permission_name, entity, mode, description, is_active, is_deleted, created_on, created_by, updated_on, updated_by)
VALUES
-- Trade (full trade workflow)
('41', 'SG-TRADER', 'trade-edit',             'UOBS', 'READ_WRITE', 'Edit trades',                   true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('42', 'SG-TRADER', 'trade-approval',         'UOBS', 'READ',       'View pending approvals',        true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('43', 'SG-TRADER', 'trade-view',             'UOBS', 'READ',       'View trade details',            true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Positions & Cash Flows (read-only for traders)
('44', 'SG-TRADER', 'position-list',          'UOBS', 'READ',       'View positions',                true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('45', 'SG-TRADER', 'cash-flow-list',         'UOBS', 'READ',       'View cash flows',               true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Market Data (read-only)
('46', 'SG-TRADER', 'market-data-dashboard',  'UOBS', 'READ',       'View market data',              true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('47', 'SG-TRADER', 'fx-rates-list',          'UOBS', 'READ',       'View FX rates',                 true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('48', 'SG-TRADER', 'equity-prices-list',     'UOBS', 'READ',       'View equity prices',            true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Reference Data (read-only)
('49', 'SG-TRADER', 'currencies-list',        'UOBS', 'READ',       'View currencies',               true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('50', 'SG-TRADER', 'countries-list',         'UOBS', 'READ',       'View countries',                true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),
('51', 'SG-TRADER', 'parties-list',           'UOBS', 'READ',       'View parties',                  true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Securities (read-only)
('52', 'SG-TRADER', 'securities-list',        'UOBS', 'READ',       'View securities',               true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- UDF (read-only)
('53', 'SG-TRADER', 'udf-list',               'UOBS', 'READ',       'View UDF fields',               true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM'),

-- Lookup (read-only)
('54', 'SG-TRADER', 'lookup-tables-list',     'UOBS', 'READ',       'View lookup tables',            true, false, NOW(), 'SYSTEM', NOW(), 'SYSTEM');


-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check all permissions are loaded
SELECT COUNT(*) as total_permissions FROM gmp_cis.cis_permission_info WHERE is_deleted = false;

-- Confirm rbac-admin exists
SELECT * FROM gmp_cis.cis_permission_info WHERE permission_name = 'rbac-admin';

-- Check CIS-SYSOPS has rbac-admin mapped
SELECT * FROM gmp_cis.cis_group_permission_map
WHERE group_name = 'CIS-SYSOPS' AND permission_name = 'rbac-admin';

-- Full permission list for CIS-SYSOPS
SELECT permission_name, mode
FROM gmp_cis.cis_group_permission_map
WHERE group_name = 'CIS-SYSOPS' AND is_active = true AND is_deleted = false
ORDER BY permission_name;

-- Full permission list for SG-TRADER
SELECT permission_name, mode
FROM gmp_cis.cis_group_permission_map
WHERE group_name = 'SG-TRADER' AND is_active = true AND is_deleted = false
ORDER BY permission_name;

-- Validate: any permissions in permissions_map.py not yet in cis_permission_info?
-- (Should return 0 rows after running this script)
SELECT DISTINCT permission_name FROM gmp_cis.cis_group_permission_map
WHERE is_deleted = false
  AND permission_name NOT IN (
      SELECT permission_name FROM gmp_cis.cis_permission_info WHERE is_deleted = false
  );
