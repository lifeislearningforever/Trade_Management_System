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

-- DROP TABLE IF EXISTS cis_cash_flow;

CREATE TABLE IF NOT EXISTS cis_cash_flow (
    -- Primary Key
    cash_flow_id BIGINT NOT NULL,

    -- Cash Flow Identification
    cash_flow_number STRING,                    -- Format: CF-YYYYMMDD-XXXXX

    -- Portfolio and Security References
    security_label STRING,                      -- FK to cis_security_kudu
    portfolio_short_name STRING,                -- FK to cis_portfolio

    -- Cash Flow Type Information
    cash_flow_type STRING,                      -- UDF: DIVIDEND, INTEREST, FEE, COUPON, etc.
    send_receive STRING,                        -- UDF: SEND, RECEIVE

    -- Position Flag
    position_updated BOOLEAN DEFAULT FALSE,     -- Whether position was updated

    -- Currency and Amounts
    foreign_ccy STRING,                         -- Foreign currency code (Security currency)
    local_ccy STRING,                           -- Local currency code (Portfolio currency)
    local_ccy_amt DECIMAL(20, 8),               -- Amount in local currency
    foreign_ccy_amt DECIMAL(20, 8),             -- Amount in foreign currency
    flow_amount_local DECIMAL(20, 8),           -- Flow amount in local currency
    dividend_price DECIMAL(20, 8),              -- Dividend price per share
    quantity DECIMAL(20, 8),                    -- Quantity held at ex-date (for CA cash flows)
    fx_rate DECIMAL(20, 8),                     -- FX rate used for LC conversion

    -- Tax and Charges
    tax_deducted_fc DECIMAL(20, 8),             -- Tax deducted in foreign currency
    tax_deducted_lc DECIMAL(20, 8),             -- Tax deducted in local currency
    other_charges_fc DECIMAL(20, 8),            -- Other charges in foreign currency

    -- GL Account
    gl_acc_no STRING,                           -- General Ledger Account Number

    -- Source System
    src_system STRING DEFAULT 'CIS',            -- Source system identifier: CIS (manual), CA (corporate action)

    -- Corporate Action Reference (for CA-generated cash flows)
    ca_id BIGINT,                               -- Reference to cis_corporate_action
    ca_number STRING,                           -- CA number for audit trail

    -- Important Dates
    payment_date STRING,                        -- Payment date (YYYY-MM-DD)
    trade_date STRING,                          -- Trade date (YYYY-MM-DD)
    value_date STRING,                          -- Value date (YYYY-MM-DD)
    dividend_date STRING,                       -- Dividend declaration date (YYYY-MM-DD)
    ex_date STRING,                             -- Ex-dividend date (YYYY-MM-DD)
    record_date STRING,                         -- Record date (YYYY-MM-DD)

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

    PRIMARY KEY (cash_flow_id)
)
PARTITION BY HASH (cash_flow_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.num_tablet_replicas' = '1'
);


-- ============================================================================
-- Cash Flow History Table
-- ============================================================================

-- DROP TABLE IF EXISTS cis_cash_flow_history;

CREATE TABLE IF NOT EXISTS cis_cash_flow_history (
    -- Primary Key
    history_id BIGINT NOT NULL,

    -- Reference to Cash Flow
    cash_flow_id BIGINT NOT NULL,
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
