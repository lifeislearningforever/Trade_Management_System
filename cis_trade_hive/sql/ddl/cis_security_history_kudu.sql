-- ============================================================================
-- Security History Table - Kudu DDL
-- ============================================================================
-- Description: Audit trail for all security changes and workflow actions
-- Created: 2026-01-02
-- Database: gmp_cis
-- Table: cis_security_history
-- ============================================================================

-- Drop existing tables if they exist (for recreation)
DROP TABLE IF EXISTS gmp_cis.cis_security_history;
DROP TABLE IF EXISTS gmp_cis.cis_security_history_kudu;

-- ============================================================================
-- CREATE KUDU TABLE
-- ============================================================================

CREATE TABLE gmp_cis.cis_security_history_kudu (
    -- ========================================================================
    -- PRIMARY KEY
    -- ========================================================================
    history_id BIGINT NOT NULL,             -- Unique history record ID (timestamp-based)

    -- ========================================================================
    -- SECURITY REFERENCE
    -- ========================================================================
    security_id BIGINT NOT NULL,            -- Reference to security
    security_name STRING,                    -- Security name (denormalized for reporting)
    isin STRING,                            -- ISIN (denormalized for reporting)

    -- ========================================================================
    -- ACTION DETAILS
    -- ========================================================================
    action STRING NOT NULL,                 -- CREATE, UPDATE, SUBMIT, APPROVE, REJECT, CLOSE, REACTIVATE
    status STRING,                          -- Status after action
    changes STRING,                         -- JSON string of field changes {"field": {"old": "val1", "new": "val2"}}
    comments STRING,                        -- User comments (required for APPROVE/REJECT)

    -- ========================================================================
    -- USER & TIMESTAMP
    -- ========================================================================
    performed_by STRING NOT NULL,          -- Username who performed action
    performed_at BIGINT NOT NULL,          -- Unix timestamp in milliseconds

    -- ========================================================================
    -- PRIMARY KEY CONSTRAINT
    -- ========================================================================
    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES(
    'kudu.num_tablet_replicas' = '3'
);

-- ============================================================================
-- CREATE IMPALA EXTERNAL TABLE (for querying)
-- ============================================================================

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_security_history
STORED AS KUDU
TBLPROPERTIES(
  'kudu.table_name' = 'impala::gmp_cis.cis_security_history_kudu'
);

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check table structure
DESCRIBE gmp_cis.cis_security_history;

-- Count history records
SELECT COUNT(*) as total_history_records FROM gmp_cis.cis_security_history;

-- Sample query
SELECT
    history_id,
    security_id,
    security_name,
    action,
    status,
    performed_by,
    performed_at
FROM gmp_cis.cis_security_history
ORDER BY performed_at DESC
LIMIT 10;

-- History by action type
SELECT action, COUNT(*) as count
FROM gmp_cis.cis_security_history
GROUP BY action;

-- ============================================================================
-- NOTES
-- ============================================================================
-- 1. history_id is the primary key (timestamp-based milliseconds)
-- 2. Every security action creates a history record
-- 3. Action types:
--    - CREATE: Security created
--    - UPDATE: Security modified
--    - SUBMIT: Submitted for approval
--    - APPROVE: Checker approved
--    - REJECT: Checker rejected
--    - CLOSE: Security closed (soft delete)
--    - REACTIVATE: Security reactivated
-- 4. changes field stores JSON string of what changed
-- 5. comments field is mandatory for APPROVE/REJECT actions
-- 6. Denormalized security_name and isin for easier reporting
-- 7. Partitioned by history_id hash for performance
-- 8. Provides complete audit trail for compliance
-- ============================================================================
