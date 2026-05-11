-- ============================================================================
-- Corporate Actions Tables DDL for Apache Kudu
-- Database: gmp_cis
--
-- Tables:
--   1. cis_corporate_actions - Main corporate action records
--   2. cis_corporate_actions_history - Audit history for corporate actions
--
-- Features:
--   - Maker-Checker workflow support
--   - Soft delete (is_deleted flag)
--   - Full audit trail
--   - UDF-based CA types
-- ============================================================================

-- Use gmp_cis database
USE gmp_cis;

-- ============================================================================
-- Table: cis_corporate_actions
-- Main corporate action records table
-- ============================================================================

DROP TABLE IF EXISTS cis_corporate_actions;

CREATE TABLE cis_corporate_actions (
    -- Primary Key
    ca_id BIGINT COMMENT 'Corporate Action ID - Primary Key (timestamp-based)',

    -- Business Fields
    ca_number STRING COMMENT 'Corporate Action Number (format: CA-YYYYMMDD-XXXXX)',
    ca_type STRING COMMENT 'Corporate Action Type (from UDF: DIVIDEND, STOCK_SPLIT, etc.)',
    security_name STRING COMMENT 'Security label/name from cis_security (comma-separated for multiple)',
    -- Note: portfolio_name removed - CA applies to security level, cash flows created for all portfolios holding the security

    -- Key Dates
    announcement_date STRING COMMENT 'Announcement/Declaration Date (YYYY-MM-DD)',
    ex_date STRING COMMENT 'Ex-Dividend/Ex-Date (YYYY-MM-DD)',
    record_date STRING COMMENT 'Record Date (YYYY-MM-DD)',
    payment_date STRING COMMENT 'Payment/Distribution Date (YYYY-MM-DD)',
    effective_date STRING COMMENT 'Effective Date (YYYY-MM-DD)',

    -- Subscription Period (for rights issues, etc.)
    subscription_start_date STRING COMMENT 'Subscription Start Date (YYYY-MM-DD)',
    subscription_end_date STRING COMMENT 'Subscription End Date (YYYY-MM-DD)',

    -- Price Information
    price DECIMAL(20, 6) COMMENT 'Price/Rate/Ratio for the corporate action',
    currency STRING COMMENT 'Currency code (e.g., USD, SGD)',

    -- Source System
    src_system STRING COMMENT 'Source System: CIS for manual entry, GMP for imported',

    -- Maker-Checker Workflow
    status STRING COMMENT 'Workflow Status: INITIAL, MODIFIED, VALIDATED, REJECTED',
    submitted_for_approval_at STRING COMMENT 'Timestamp when submitted for approval',
    reviewed_by STRING COMMENT 'Username of reviewer',
    reviewed_at STRING COMMENT 'Timestamp of review',
    reviewed_comments STRING COMMENT 'Review comments',

    -- Soft Delete & Active Flags
    is_deleted BOOLEAN COMMENT 'Soft delete flag (true = deleted)',
    is_active BOOLEAN COMMENT 'Active flag (true = active)',

    -- Audit Fields
    created_by STRING COMMENT 'Username who created the record',
    created_at BIGINT COMMENT 'Creation timestamp (epoch milliseconds)',
    updated_by STRING COMMENT 'Username who last updated the record',
    updated_at BIGINT COMMENT 'Last update timestamp (epoch milliseconds)',

    PRIMARY KEY (ca_id)
)
PARTITION BY HASH (ca_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.num_tablet_replicas' = '1'
);

-- Add index-like optimization via hash on frequently queried columns
-- Note: Kudu doesn't support traditional indexes; use hash partitioning

COMMENT ON TABLE cis_corporate_actions IS
'Corporate Actions master table storing dividends, stock splits, mergers, and other corporate events.
Supports Maker-Checker workflow with status tracking. Source: CIS (manual) or GMP (imported).';


-- ============================================================================
-- Table: cis_corporate_actions_history
-- Audit history for corporate actions
-- ============================================================================

DROP TABLE IF EXISTS cis_corporate_actions_history;

CREATE TABLE cis_corporate_actions_history (
    -- Primary Key
    history_id STRING COMMENT 'History record ID - Primary Key (YYYYMMDDHHMMSS_<hex8>)',

    -- Reference to Corporate Action
    ca_id BIGINT COMMENT 'Foreign key to cis_corporate_actions',
    ca_number STRING COMMENT 'CA Number (denormalized for readability)',
    security_name STRING COMMENT 'Security name (denormalized for readability)',

    -- Action Details
    action STRING COMMENT 'Action type: CREATE, UPDATE, VALIDATE, REJECT, DELETE, RESTORE',
    status STRING COMMENT 'Status after action',
    changes STRING COMMENT 'JSON blob of field changes: {"field": {"old": x, "new": y}}',
    comments STRING COMMENT 'User comments for this action',

    -- Audit Fields
    performed_by STRING COMMENT 'Username who performed the action',
    performed_at STRING COMMENT 'Timestamp when action was performed (YYYY-MM-DD HH:MM:SS)',

    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.num_tablet_replicas' = '1'
);

COMMENT ON TABLE cis_corporate_actions_history IS
'Audit history table for corporate actions. Tracks all changes including create, update,
validate, reject, delete, and restore actions with full field-level change tracking.';


-- ============================================================================
-- Sample Data for Testing (Optional)
-- ============================================================================

-- Insert sample corporate action
-- UPSERT INTO cis_corporate_actions (
--     ca_id, ca_number, ca_type, security_name,
--     announcement_date, ex_date, record_date, payment_date, effective_date,
--     subscription_start_date, subscription_end_date,
--     price, currency, src_system, status,
--     is_deleted, is_active, created_by, created_at, updated_by, updated_at
-- ) VALUES (
--     1710000000001, 'CA-20260317-00001', 'DIVIDEND', 'AAPL - APPLE INC',
--     '2026-03-10', '2026-03-15', '2026-03-16', '2026-03-20', '2026-03-20',
--     NULL, NULL,
--     0.25, 'USD', 'CIS', 'INITIAL',
--     false, true, 'admin', 1710000000001, 'admin', 1710000000001
-- );


-- ============================================================================
-- Verification Queries
-- ============================================================================

-- Check table exists and structure
-- DESCRIBE cis_corporate_actions;
-- DESCRIBE cis_corporate_actions_history;

-- Check record count
-- SELECT COUNT(*) as total_count FROM cis_corporate_actions;
-- SELECT COUNT(*) as history_count FROM cis_corporate_actions_history;

-- Check by status
-- SELECT status, COUNT(*) as count
-- FROM cis_corporate_actions
-- WHERE is_deleted = false OR is_deleted IS NULL
-- GROUP BY status;
