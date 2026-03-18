-- ============================================================================
-- CIS Cash Flow Tables - Kudu DDL
-- ============================================================================
-- Description: DDL for Cash Flow management with Maker-Checker workflow
-- Database: gmp_cis
-- Tables:
--   - cis_cash_flow: Main cash flow records
--   - cis_cash_flow_history: Audit trail for cash flow changes
-- ============================================================================

-- Drop existing tables if they exist
DROP TABLE IF EXISTS gmp_cis.cis_cash_flow_history;
DROP TABLE IF EXISTS gmp_cis.cis_cash_flow;

-- ============================================================================
-- Main Cash Flow Table
-- ============================================================================
CREATE TABLE gmp_cis.cis_cash_flow (
    -- Primary Key
    cf_id BIGINT NOT NULL,

    -- Cash Flow Identification
    cf_number STRING NOT NULL,                    -- Format: CF-YYYYMMDD-XXXXX

    -- Portfolio and Security References
    portfolio_short_name STRING NOT NULL,         -- FK to cis_portfolio
    security_name STRING,                         -- FK to cis_security_kudu (optional)

    -- Cash Flow Type Information
    cash_flow_type STRING NOT NULL,               -- UDF: DIVIDEND, INTEREST, FEE, COUPON, etc.
    send_receive STRING NOT NULL,                 -- UDF: SEND, RECEIVE
    cash_flow_status STRING,                      -- UDF: PENDING, SETTLED, CANCELLED

    -- Important Dates
    value_date STRING,                            -- Value date (YYYY-MM-DD)
    payment_date STRING,                          -- Payment date (YYYY-MM-DD)
    dividend_date STRING,                         -- Dividend declaration date
    ex_date STRING,                               -- Ex-dividend date
    record_date STRING,                           -- Record date

    -- GL Account
    gl_acc_no STRING,                             -- General Ledger Account Number

    -- Local Currency Amounts
    local_ccy STRING,                             -- Local currency code (e.g., USD, EUR)
    local_amount DECIMAL(20, 8),                  -- Amount in local currency
    flow_amount_local DECIMAL(20, 8),             -- Flow amount in local currency

    -- Foreign Currency Amounts
    foreign_ccy STRING,                           -- Foreign currency code
    foreign_ccy_amount DECIMAL(20, 8),            -- Amount in foreign currency

    -- Source System
    src_system STRING DEFAULT 'CIS',              -- Source system identifier

    -- Workflow Status (Maker-Checker)
    status STRING DEFAULT 'INITIAL',              -- INITIAL, MODIFIED, APPROVED, REJECTED

    -- Soft Delete
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at STRING,
    deleted_by STRING,

    -- Audit Fields - Creator (Maker)
    created_by STRING NOT NULL,
    created_by_id BIGINT,
    created_by_email STRING,
    created_at STRING NOT NULL,

    -- Audit Fields - Last Modifier
    updated_by STRING,
    updated_by_id BIGINT,
    updated_by_email STRING,
    updated_at STRING,

    -- Audit Fields - Reviewer (Checker)
    reviewed_by STRING,
    reviewed_by_id BIGINT,
    reviewed_by_email STRING,
    reviewed_at STRING,
    reviewed_comments STRING,

    -- Primary Key
    PRIMARY KEY (cf_id)
)
PARTITION BY HASH(cf_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.table_name' = 'cis_cash_flow',
    'kudu.num_tablet_replicas' = '1'
);

-- ============================================================================
-- Cash Flow History Table (Audit Trail)
-- ============================================================================
CREATE TABLE gmp_cis.cis_cash_flow_history (
    -- Primary Key
    history_id BIGINT NOT NULL,
    cf_id BIGINT NOT NULL,                        -- FK to cis_cash_flow

    -- Action Information
    action STRING NOT NULL,                       -- CREATE, UPDATE, APPROVE, REJECT, DELETE, RESTORE
    status STRING,                                -- Status at time of action

    -- Performer Information
    performed_by STRING NOT NULL,
    performed_by_id BIGINT,
    performed_by_email STRING,
    performed_at STRING NOT NULL,

    -- Change Details
    comments STRING,                              -- Action comments
    old_values STRING,                            -- JSON of previous values (for updates)
    new_values STRING,                            -- JSON of new values (for updates)

    -- Primary Key
    PRIMARY KEY (history_id)
)
PARTITION BY HASH(history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.table_name' = 'cis_cash_flow_history',
    'kudu.num_tablet_replicas' = '1'
);

-- ============================================================================
-- Indexes (Kudu secondary indexes for common queries)
-- ============================================================================
-- Note: Kudu doesn't support traditional indexes like MySQL/PostgreSQL.
-- Query optimization is achieved through partition pruning and column predicates.

-- ============================================================================
-- Sample Data (Optional - for development/testing)
-- ============================================================================
-- UPSERT INTO gmp_cis.cis_cash_flow (
--     cf_id, cf_number, portfolio_short_name, security_name,
--     cash_flow_type, send_receive, cash_flow_status,
--     value_date, payment_date, local_ccy, local_amount,
--     src_system, status, is_deleted,
--     created_by, created_by_id, created_at
-- ) VALUES (
--     1, 'CF-20260318-00001', 'GROWTH_FUND', 'AAPL',
--     'DIVIDEND', 'RECEIVE', 'PENDING',
--     '2026-03-20', '2026-03-25', 'USD', 1500.00,
--     'CIS', 'INITIAL', FALSE,
--     'admin', 1, '2026-03-18 10:00:00'
-- );

-- ============================================================================
-- Grant Permissions (adjust as needed for your environment)
-- ============================================================================
-- GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gmp_cis.cis_cash_flow TO ROLE cis_app_role;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gmp_cis.cis_cash_flow_history TO ROLE cis_app_role;
-- GRANT SELECT ON TABLE gmp_cis.cis_cash_flow TO ROLE cis_readonly_role;
-- GRANT SELECT ON TABLE gmp_cis.cis_cash_flow_history TO ROLE cis_readonly_role;

-- ============================================================================
-- Verification Queries
-- ============================================================================
-- DESCRIBE gmp_cis.cis_cash_flow;
-- DESCRIBE gmp_cis.cis_cash_flow_history;
-- SELECT COUNT(*) FROM gmp_cis.cis_cash_flow;
-- SELECT COUNT(*) FROM gmp_cis.cis_cash_flow_history;
