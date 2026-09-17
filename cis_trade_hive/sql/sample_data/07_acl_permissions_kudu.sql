-- =====================================================
-- Sample ACL Data for Kudu/Impala
-- Role-Based Access Control Configuration
-- =====================================================

-- Note: This is for Kudu/Impala database
-- Execute in Impala shell connected to gmp_cis database

-- Sample Users
INSERT INTO cis_user (user_id, username, login, name, email, domain, entity, cis_user_group_id, is_active, is_deleted, enabled, created_at)
VALUES
(1, 'admin', 'admin', 'System Administrator', 'admin@cistrade.com', 'CISTRADE', 'HQ', 1, TRUE, FALSE, TRUE, NOW()),
(2, 'maker1', 'maker1', 'John Doe', 'maker1@cistrade.com', 'CISTRADE', 'Trading', 2, TRUE, FALSE, TRUE, NOW()),
(3, 'maker2', 'maker2', 'Jane Smith', 'maker2@cistrade.com', 'CISTRADE', 'Trading', 2, TRUE, FALSE, TRUE, NOW()),
(4, 'checker1', 'checker1', 'Mike Johnson', 'checker1@cistrade.com', 'CISTRADE', 'Operations', 3, TRUE, FALSE, TRUE, NOW()),
(5, 'checker2', 'checker2', 'Sarah Williams', 'checker2@cistrade.com', 'CISTRADE', 'Operations', 3, TRUE, FALSE, TRUE, NOW()),
(6, 'viewer1', 'viewer1', 'Bob Brown', 'viewer1@cistrade.com', 'CISTRADE', 'Reporting', 4, TRUE, FALSE, TRUE, NOW());

-- Groups
INSERT INTO cis_group (group_id, group_name, description, is_active, is_deleted, created_at)
VALUES
(1, 'Administrators', 'System administrators with full access', TRUE, FALSE, NOW()),
(2, 'Makers', 'Users who can create and modify records', TRUE, FALSE, NOW()),
(3, 'Checkers', 'Users who can approve or reject records', TRUE, FALSE, NOW()),
(4, 'Viewers', 'Users with read-only access', TRUE, FALSE, NOW());

-- User Group Assignments
INSERT INTO cis_user_group (group_id, user_id, group_name, description, is_active, is_deleted, created_at)
VALUES
(1, 1, 'Administrators', 'Admin user', TRUE, FALSE, NOW()),
(2, 2, 'Makers', 'Maker user', TRUE, FALSE, NOW()),
(2, 3, 'Makers', 'Maker user', TRUE, FALSE, NOW()),
(3, 4, 'Checkers', 'Checker user', TRUE, FALSE, NOW()),
(3, 5, 'Checkers', 'Checker user', TRUE, FALSE, NOW()),
(4, 6, 'Viewers', 'Viewer user', TRUE, FALSE, NOW());

-- Permissions for Administrators (Full Access)
INSERT INTO cis_group_permissions (permission_id, group_id, permission_name, can_view, can_create, can_edit, can_delete, can_approve, read_write, is_active, is_deleted, created_at)
VALUES
(1, 1, 'portfolio', TRUE, TRUE, TRUE, TRUE, TRUE, 'READ_WRITE', TRUE, FALSE, NOW()),
(2, 1, 'udf', TRUE, TRUE, TRUE, TRUE, TRUE, 'READ_WRITE', TRUE, FALSE, NOW()),
(3, 1, 'currency', TRUE, TRUE, TRUE, TRUE, FALSE, 'READ_WRITE', TRUE, FALSE, NOW()),
(4, 1, 'country', TRUE, TRUE, TRUE, TRUE, FALSE, 'READ_WRITE', TRUE, FALSE, NOW()),
(5, 1, 'calendar', TRUE, TRUE, TRUE, TRUE, FALSE, 'READ_WRITE', TRUE, FALSE, NOW()),
(6, 1, 'counterparty', TRUE, TRUE, TRUE, TRUE, FALSE, 'READ_WRITE', TRUE, FALSE, NOW()),
(7, 1, 'audit_log', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW());

-- Permissions for Makers (Create/Edit, No Approve)
INSERT INTO cis_group_permissions (permission_id, group_id, permission_name, can_view, can_create, can_edit, can_delete, can_approve, read_write, is_active, is_deleted, created_at)
VALUES
(10, 2, 'portfolio', TRUE, TRUE, TRUE, FALSE, FALSE, 'READ_WRITE', TRUE, FALSE, NOW()),
(11, 2, 'udf', TRUE, TRUE, TRUE, FALSE, FALSE, 'READ_WRITE', TRUE, FALSE, NOW()),
(12, 2, 'currency', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(13, 2, 'country', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(14, 2, 'calendar', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(15, 2, 'counterparty', TRUE, TRUE, TRUE, FALSE, FALSE, 'READ_WRITE', TRUE, FALSE, NOW());

-- Permissions for Checkers (Approve, No Create/Edit)
INSERT INTO cis_group_permissions (permission_id, group_id, permission_name, can_view, can_create, can_edit, can_delete, can_approve, read_write, is_active, is_deleted, created_at)
VALUES
(20, 3, 'portfolio', TRUE, FALSE, FALSE, FALSE, TRUE, 'READ', TRUE, FALSE, NOW()),
(21, 3, 'udf', TRUE, FALSE, FALSE, FALSE, TRUE, 'READ', TRUE, FALSE, NOW()),
(22, 3, 'currency', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(23, 3, 'country', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(24, 3, 'calendar', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(25, 3, 'counterparty', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(26, 3, 'audit_log', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW());

-- Permissions for Viewers (Read-Only)
INSERT INTO cis_group_permissions (permission_id, group_id, permission_name, can_view, can_create, can_edit, can_delete, can_approve, read_write, is_active, is_deleted, created_at)
VALUES
(30, 4, 'portfolio', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(31, 4, 'udf', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(32, 4, 'currency', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(33, 4, 'country', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(34, 4, 'calendar', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW()),
(35, 4, 'counterparty', TRUE, FALSE, FALSE, FALSE, FALSE, 'READ', TRUE, FALSE, NOW());

-- Permission Summary:
--
-- Administrators: Full access to everything
-- Makers: Can create/edit portfolios, UDFs, counterparties; view-only for reference data
-- Checkers: Can approve/reject pending items; view-only otherwise
-- Viewers: Read-only access to all data
