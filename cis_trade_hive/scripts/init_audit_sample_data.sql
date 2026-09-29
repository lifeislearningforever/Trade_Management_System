-- ============================================
-- Audit Log Sample Data Initialization Script
-- Run this in beeline to populate sample audit log data
-- ============================================

-- Usage:
-- beeline -u jdbc:hive2://localhost:10000/cis -f init_audit_sample_data.sql

-- ============================================
-- Sample Audit Logs - Portfolio Operations
-- ============================================

-- Portfolio Created
INSERT INTO cis.cis_audit_log VALUES (
    NULL,
    '2025-12-25 10:00:00', 'user001', 'john.smith', 'john.smith@example.com',
    'CREATE', 'DATA', 'Created new portfolio TRADING-001',
    'PORTFOLIO', '1', 'Trading Portfolio A',
    NULL, NULL, 'TRADING-001',
    'POST', '/portfolio/create/', '{"name":"Trading Portfolio A","code":"TRADING-001"}',
    'SUCCESS', 200, NULL, NULL,
    'session-abc123', '192.168.1.100', 'Mozilla/5.0',
    'portfolio', 'portfolio_create', 150,
    'portfolio,trading,creation', '{"notes":"Initial setup"}',
    '2025-12-25'
);

-- Portfolio Updated
INSERT INTO cis.cis_audit_log VALUES (
    NULL,
    '2025-12-25 11:30:00', 'user002', 'sarah.johnson', 'sarah.johnson@example.com',
    'UPDATE', 'DATA', 'Updated portfolio status to ACTIVE',
    'PORTFOLIO', '1', 'Trading Portfolio A',
    'status', 'PENDING', 'ACTIVE',
    'PUT', '/portfolio/1/edit/', '{"status":"ACTIVE"}',
    'SUCCESS', 200, NULL, NULL,
    'session-def456', '192.168.1.101', 'Mozilla/5.0',
    'portfolio', 'portfolio_edit', 95,
    'portfolio,status,update', NULL,
    '2025-12-25'
);

-- UDF Value Set
INSERT INTO cis.cis_audit_log VALUES (
    NULL,
    '2025-12-25 12:00:00', 'user001', 'john.smith', 'john.smith@example.com',
    'UPDATE', 'DATA', 'Set UDF account_group to TRADING',
    'UDF', 'portfolio-1-account_group', 'account_group for Portfolio 1',
    'account_group', NULL, 'TRADING',
    'POST', '/udf/values/portfolio/1/', '{"account_group":"TRADING"}',
    'SUCCESS', 200, NULL, NULL,
    'session-abc123', '192.168.1.100', 'Mozilla/5.0',
    'udf', 'set_entity_udf_values', 45,
    'udf,portfolio,account_group', NULL,
    '2025-12-25'
);

-- User Login
INSERT INTO cis.cis_audit_log VALUES (
    NULL,
    '2025-12-25 09:00:00', 'user001', 'john.smith', 'john.smith@example.com',
    'LOGIN', 'AUTH', 'User logged in successfully',
    'USER', 'user001', 'john.smith',
    NULL, NULL, NULL,
    'POST', '/login/', NULL,
    'SUCCESS', 200, NULL, NULL,
    'session-abc123', '192.168.1.100', 'Mozilla/5.0',
    'core', 'login_view', 50,
    'authentication,login', NULL,
    '2025-12-25'
);

-- Portfolio Export
INSERT INTO cis.cis_audit_log VALUES (
    NULL,
    '2025-12-25 14:00:00', 'user002', 'sarah.johnson', 'sarah.johnson@example.com',
    'EXPORT', 'REPORT', 'Exported portfolio list to CSV',
    'PORTFOLIO', NULL, 'Portfolio List',
    NULL, NULL, NULL,
    'GET', '/portfolio/?export=csv', NULL,
    'SUCCESS', 200, NULL, NULL,
    'session-def456', '192.168.1.101', 'Mozilla/5.0',
    'portfolio', 'portfolio_list', 500,
    'export,csv,portfolio', '{"count":25}',
    '2025-12-25'
);

-- Failed Operation
INSERT INTO cis.cis_audit_log VALUES (
    NULL,
    '2025-12-25 15:30:00', 'user003', 'admin', 'admin@example.com',
    'DELETE', 'DATA', 'Attempted to delete active portfolio',
    'PORTFOLIO', '1', 'Trading Portfolio A',
    NULL, NULL, NULL,
    'DELETE', '/portfolio/1/delete/', NULL,
    'FAILURE', 403, 'Cannot delete active portfolio', NULL,
    'session-xyz789', '192.168.1.102', 'Mozilla/5.0',
    'portfolio', 'portfolio_delete', 25,
    'portfolio,delete,failed', NULL,
    '2025-12-25'
);

-- Reference Data Viewed
INSERT INTO cis.cis_audit_log VALUES (
    NULL,
    '2025-12-25 16:00:00', 'user001', 'john.smith', 'john.smith@example.com',
    'VIEW', 'DATA', 'Viewed counterparty list',
    'COUNTERPARTY', NULL, 'Counterparty List',
    NULL, NULL, NULL,
    'GET', '/reference-data/counterparty/', '{"search":"india"}',
    'SUCCESS', 200, NULL, NULL,
    'session-abc123', '192.168.1.100', 'Mozilla/5.0',
    'reference_data', 'counterparty_list', 850,
    'reference,counterparty,view', NULL,
    '2025-12-25'
);

-- System Admin Action
INSERT INTO cis.cis_audit_log VALUES (
    NULL,
    '2025-12-25 17:00:00', 'admin', 'admin', 'admin@example.com',
    'UPDATE', 'ADMIN', 'Updated user permissions',
    'USER', 'user002', 'sarah.johnson',
    'permissions', 'VIEW_PORTFOLIO', 'VIEW_PORTFOLIO,EDIT_PORTFOLIO',
    'PUT', '/admin/users/user002/', '{"permissions":["VIEW_PORTFOLIO","EDIT_PORTFOLIO"]}',
    'SUCCESS', 200, NULL, NULL,
    'session-admin', '192.168.1.1', 'Mozilla/5.0',
    'core', 'update_user_permissions', 120,
    'admin,permissions,user', NULL,
    '2025-12-25'
);

-- ============================================
-- Sample Audit Logs - Previous Days
-- ============================================

-- Day -1: Portfolio operations
INSERT INTO cis.cis_audit_log VALUES (
    NULL,
    '2025-12-24 10:00:00', 'user001', 'john.smith', 'john.smith@example.com',
    'CREATE', 'DATA', 'Created portfolio INVEST-002',
    'PORTFOLIO', '2', 'Investment Portfolio B',
    NULL, NULL, 'INVEST-002',
    'POST', '/portfolio/create/', NULL,
    'SUCCESS', 200, NULL, NULL,
    'session-abc123', '192.168.1.100', 'Mozilla/5.0',
    'portfolio', 'portfolio_create', 140,
    'portfolio,investment', NULL,
    '2025-12-24'
);

-- Day -2: UDF operations
INSERT INTO cis.cis_audit_log VALUES (
    NULL,
    '2025-12-23 14:00:00', 'admin', 'admin', 'admin@example.com',
    'CREATE', 'ADMIN', 'Created new UDF definition: risk_rating',
    'UDF', '3', 'risk_rating',
    NULL, NULL, NULL,
    'POST', '/udf/create/', NULL,
    'SUCCESS', 200, NULL, NULL,
    'session-admin', '192.168.1.1', 'Mozilla/5.0',
    'udf', 'udf_create', 75,
    'udf,definition,risk', NULL,
    '2025-12-23'
);

-- Day -7: Weekly operations
INSERT INTO cis.cis_audit_log VALUES (
    NULL,
    '2025-12-18 09:00:00', 'user001', 'john.smith', 'john.smith@example.com',
    'VIEW', 'REPORT', 'Generated weekly portfolio report',
    'PORTFOLIO', NULL, 'Weekly Report',
    NULL, NULL, NULL,
    'GET', '/reports/portfolio/weekly/', NULL,
    'SUCCESS', 200, NULL, NULL,
    'session-abc123', '192.168.1.100', 'Mozilla/5.0',
    'reports', 'weekly_report', 2500,
    'report,weekly,portfolio', '{"portfolios":25}',
    '2025-12-18'
);

-- ============================================
-- Verification Queries
-- ============================================

-- Total audit logs
SELECT COUNT(*) as total_logs FROM cis.cis_audit_log;

-- Logs by action type
SELECT action_type, COUNT(*) as count
FROM cis.cis_audit_log
GROUP BY action_type;

-- Logs by entity type
SELECT entity_type, COUNT(*) as count
FROM cis.cis_audit_log
GROUP BY entity_type;

-- Logs by status
SELECT status, COUNT(*) as count
FROM cis.cis_audit_log
GROUP BY status;

-- Recent logs
SELECT
    audit_timestamp,
    username,
    action_type,
    entity_type,
    action_description,
    status
FROM cis.cis_audit_log
ORDER BY audit_timestamp DESC
LIMIT 10;

-- Failed operations
SELECT
    audit_timestamp,
    username,
    action_type,
    entity_type,
    action_description,
    error_message
FROM cis.cis_audit_log
WHERE status = 'FAILURE';
