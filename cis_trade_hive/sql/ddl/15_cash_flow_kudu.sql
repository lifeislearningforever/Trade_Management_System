-- ============================================================================
-- CIS Cash Flow Tables - Kudu DDL
-- ============================================================================
-- Description: DDL for Cash Flow management with Maker-Checker workflow
-- Database: gmp_cis
-- Tables:
--   - cis_cash_flow: Main cash flow records
--   - cis_cash_flow_history: Audit trail for cash flow changes
-- ============================================================================

-- Use gmp_cis database
USE gmp_cis;

-- ============================================================================
-- Main Cash Flow Table
-- ============================================================================

DROP TABLE IF EXISTS cis_cash_flow;

CREATE TABLE cis_cash_flow (
    -- Primary Key
    cf_id BIGINT NOT NULL,

    -- Cash Flow Identification
    cash_flow_number STRING NOT NULL,           -- Format: CF-YYYYMMDD-XXXXX

    -- Portfolio and Security References
    security_label STRING,                      -- FK to cis_security_kudu
    portfolio_short_name STRING NOT NULL,       -- FK to cis_portfolio

    -- Cash Flow Type Information
    cash_flow_type STRING NOT NULL,             -- UDF: DIVIDEND, INTEREST, FEE, COUPON, etc.
    send_receive STRING NOT NULL,               -- UDF: SEND, RECEIVE

    -- Position Flag
    position_updated BOOLEAN DEFAULT FALSE,     -- Whether position was updated

    -- Currency and Amounts
    foreign_ccy STRING,                         -- Foreign currency code
    local_ccy STRING,                           -- Local currency code
    local_ccy_amt DECIMAL(20, 6),               -- Amount in local currency
    foreign_ccy_amt DECIMAL(20, 6),             -- Amount in foreign currency
    flow_amount_local DECIMAL(20, 6),           -- Flow amount in local currency
    dividend_price DECIMAL(20, 6),              -- Dividend price per share

    -- GL Account
    gl_acc_no STRING,                           -- General Ledger Account Number

    -- Source System
    src_system STRING DEFAULT 'CIS',            -- Source system identifier

    -- Important Dates
    payment_date TIMESTAMP,                     -- Payment date
    trade_date TIMESTAMP,                       -- Trade date
    value_date TIMESTAMP,                       -- Value date
    dividend_date TIMESTAMP,                    -- Dividend declaration date
    ex_date TIMESTAMP,                          -- Ex-dividend date
    record_date TIMESTAMP,                      -- Record date

    -- Soft Delete & Active Flags
    is_deleted BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,

    -- Audit Fields
    created_by STRING,
    created_at TIMESTAMP,
    updated_by STRING,
    updated_at TIMESTAMP,

    -- Workflow Status (Maker-Checker)
    status STRING DEFAULT 'INITIAL',            -- INITIAL, MODIFIED, VALIDATED, REJECTED, SETTLED, CANCELLED

    -- Submission
    submitted_by STRING,
    submitted_at TIMESTAMP,

    -- Validation
    validated_by STRING,
    validated_at TIMESTAMP,
    validation_comments STRING,

    -- Settlement
    settled_by STRING,
    settled_at TIMESTAMP,
    settlement_comments STRING,

    -- Cancellation
    cancelled_by STRING,
    cancelled_at TIMESTAMP,
    cancel_reason STRING,

    PRIMARY KEY (cf_id)
)
PARTITION BY HASH (cf_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.num_tablet_replicas' = '1'
);

COMMENT ON TABLE cis_cash_flow IS
'Cash flow records for dividends, interest, fees, coupons, and other monetary flows.
Supports Maker-Checker workflow with validation and settlement tracking.';


-- ============================================================================
-- Cash Flow History Table
-- ============================================================================

DROP TABLE IF EXISTS cis_cash_flow_history;

CREATE TABLE cis_cash_flow_history (
    -- Primary Key
    history_id BIGINT NOT NULL,

    -- Reference to Cash Flow
    cf_id BIGINT NOT NULL,
    cash_flow_number STRING,
    portfolio_short_name STRING,

    -- Action Details
    action STRING,                              -- CREATE, UPDATE, VALIDATE, SETTLE, CANCEL, DELETE
    status STRING,
    changes STRING,                             -- JSON blob of field changes
    comments STRING,

    -- Audit Fields
    performed_by STRING,
    performed_at BIGINT,

    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.num_tablet_replicas' = '1'
);

COMMENT ON TABLE cis_cash_flow_history IS
'Audit history table for cash flows. Tracks all changes with field-level change tracking.';
