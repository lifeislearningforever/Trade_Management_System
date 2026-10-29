-- ============================================================================
-- Trade Management Module - Kudu Tables DDL
-- ============================================================================
-- Description: Complete DDL for Trade Management module supporting:
--              - Buy, Sell, Add Long, Deliver Long, Reduction Basis, Income,
--                Split Transaction operations
--              - Four-Eyes (Maker-Checker) workflow
--              - Full audit trail with field-level change tracking
--              - UDF (User Defined Fields) integration
--              - Position tracking
--
-- Database: gmp_cis
-- Created: 2026-01-12
-- Version: 1.0
--
-- Tables Created:
--   1. cis_trade           - Main trade table
--   2. cis_trade_history   - Audit trail for trades
--   3. cis_trade_note      - Trade notes/comments
--   4. cis_trade_position  - Versioned position snapshots (replaces cis_trade_details + history)
--
-- Workflow Statuses:
--   MAKER Side:
--     - INITIAL: New trade created (not yet submitted)
--     - MODIFIED: Trade edited (after rejection or before submit)
--     - CANCELLED: Trade cancelled by maker (soft delete)
--
--   CHECKER Side:
--     - PENDING_VALIDATION: Submitted for validation (awaiting checker)
--     - VALIDATED: Approved by checker (ready for settlement)
--     - SETTLED: Final active state (settlement complete)
--
-- Status Flow:
--   Create    -> INITIAL
--   Edit      -> MODIFIED
--   Cancel    -> CANCELLED
--   Submit    -> PENDING_VALIDATION
--   Validate  -> VALIDATED (or CANCELLED if rejected)
--   Settle    -> SETTLED
--
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- TABLE 1: cis_trade (Main Trade Table)
-- ============================================================================
-- Primary table storing all trade types:
--   BUY, SELL, ADD_LONG, DELIVER_LONG, REDUCTION_BASIS, INCOME, SPLIT_TRANSACTION
--
-- Note: trade_id is system-generated (not shown in UI)
-- ============================================================================

DROP TABLE IF EXISTS cis_trade;

CREATE TABLE cis_trade (
    -- Primary Key (System Generated - NOT shown in UI)
    trade_id BIGINT NOT NULL,

    -- Trade Type
    -- BUY, SELL, ADD_LONG, DELIVER_LONG, REDUCTION_BASIS, INCOME, SPLIT_TRANSACTION
    trade_type STRING NOT NULL,

    -- Deal Number (User-visible transaction identifier)
    deal_number STRING,

    -- ========================================
    -- BASIC INFORMATION (from Buy_part1.JPG)
    -- ========================================

    -- Portfolio Reference (FK to cis_portfolio.name)
    portfolio_short_name STRING NOT NULL,
    portfolio_full_name STRING,  -- Output: auto-populated from portfolio

    -- Security Reference (FK to cis_security)
    security_label STRING NOT NULL,
    security_full_name STRING,  -- Output: auto-populated from security
    security_type STRING,       -- Output: auto-populated from security

    -- Currency (for filtering securities and auto-filling price)
    currency_code STRING,       -- Currency for the trade (USD, SGD, etc.) - same as security currency
    portfolio_currency STRING,  -- Portfolio's base currency (LC) - auto-populated from portfolio

    -- Trade Status (workflow status, different from trading status)
    trade_status STRING,  -- Dropdown: from UDF Trade Status options

    -- ========================================
    -- DATE & QUANTITY
    -- ========================================
    trade_date STRING NOT NULL,      -- Date of trade execution (YYYY-MM-DD)
    settle_date STRING,              -- Settlement date (YYYY-MM-DD)
    expiry_date STRING,              -- For derivatives

    quantity DECIMAL(20,6),          -- Number of units traded
    face_value DECIMAL(20,6),        -- Nominal value per unit
    lot DECIMAL(20,6),               -- Lot size

    -- ========================================
    -- PRICING & COSTS
    -- ========================================
    price DECIMAL(20,6),             -- Price per unit
    commission DECIMAL(20,6),        -- Broker commission
    accrued_interest DECIMAL(20,6),  -- Calculated: Interest accrued till trade date
    sec_fee DECIMAL(20,6),           -- Regulatory/security fee
    other_charges DECIMAL(20,6),     -- Other charges
    total_amount DECIMAL(20,6),      -- Calculated: Final amount (legacy, same as total_amount_fc)

    -- Multi-Currency Amounts (FC = Foreign/Security Currency, LC = Local/Portfolio Currency)
    -- gross = qty × price (excluding charges); total = gross + charges
    gross_amount_fc DECIMAL(30,8),   -- Gross amount FC: qty × price (no charges) — used for AVP cost basis
    gross_amount_lc DECIMAL(30,8),   -- Gross amount LC: gross_fc × fx_rate (no charges)
    total_amount_fc DECIMAL(30,8),   -- Total amount FC: gross + charges (including commission, fees)
    total_amount_lc DECIMAL(30,8),   -- Total amount LC: total_fc × fx_rate (including charges)

    -- ========================================
    -- AUTO-CALCULATED CHARGES (from Charge LUT)
    -- ========================================
    charge_fee_type STRING,              -- Fee type from charge lookup table
    charge_exchange STRING,              -- Exchange code for charge lookup
    charge_country STRING,               -- Country code for charge lookup
    charge_fee_rule STRING,              -- Fee rule applied
    charge_fee_value DECIMAL(20,6),      -- Fee value from lookup
    calculated_commission DECIMAL(20,6), -- Brokerage Fee (auto-calculated)
    calculated_clearing_fee DECIMAL(20,6), -- Clearing Fee (auto-calculated)
    calculated_trading_fee DECIMAL(20,6),  -- Trading Fee (auto-calculated)
    calculated_gst DECIMAL(20,6),        -- GST (auto-calculated)
    calculated_other_fees DECIMAL(20,6), -- FFP/SGX SI FEE, etc. (auto-calculated)
    total_calculated_charges DECIMAL(20,6), -- Sum of all auto-calculated charges
    charges_auto_calculated BOOLEAN,     -- Flag: true if charges were auto-calculated

    -- ========================================
    -- GL & ACCOUNTING (from Buy_part2.JPG)
    -- ========================================
    open_close_position STRING,      -- Dropdown: Open/Close
    extension STRING,                -- Dropdown: Extension details

    -- Broker Info
    brokers STRING,                  -- Dropdown: List of brokers
    broker_name STRING,              -- Dropdown: Broker name (from another table)

    -- General Ledger
    gl_fund_type STRING,             -- Dropdown: GL fund type
    gl_cost_centre STRING,           -- Dropdown: GL cost centre code
    gl_account_code STRING,          -- Dropdown: GL account code

    -- Contract
    contract_ref STRING,             -- Reference number for contract
    fd_receipt STRING,               -- Fixed deposit receipt

    -- ========================================
    -- FX & DEALING
    -- ========================================
    org_pur_date STRING,             -- Original purchase date (YYYY-MM-DD)
    open_fx_rate DECIMAL(20,6),      -- FX rate at open
    curr_dealing DECIMAL(20,6),      -- Currency dealing
    open_dealing DECIMAL(20,6),      -- Open dealing amount
    input_tax_oth DECIMAL(20,6),     -- Other tax input
    qty_entitled DECIMAL(20,6),      -- Quantity entitled

    -- ========================================
    -- POST-TRADE INFO (Output/Calculated)
    -- ========================================
    selling_rule STRING,             -- Dropdown: Selling rule (from system parameter)
    cash_balance DECIMAL(20,6),      -- Dropdown or calculated
    custodian STRING,                -- Output: Auto from portfolio
    amor_accr_method STRING,         -- Output: Amortisation method
    lots_held DECIMAL(20,6),         -- Output: Number of lots post-trade
    quantity_held DECIMAL(20,6),     -- Calculated: Total quantity post-trade

    -- Remarks
    remarks STRING,                  -- Additional comments

    -- ========================================
    -- USER DEFINED FIELDS (from Trade_udf.JPG)
    -- Stored here for performance; also in cis_udf_value
    -- ========================================
    udf_fund_type STRING,            -- Dropdown: Type of fund (Equity, Bond, etc.)
    udf_section_31_26 STRING,        -- Dropdown: Regulatory section
    udf_sub_custodian STRING,        -- Dropdown: Sub-custodian name
    udf_disclosure_req BOOLEAN,      -- Boolean: Disclosure requirement flag
    udf_counter_pledged BOOLEAN,     -- Boolean: If counterparty pledged
    udf_revision_code STRING,        -- Dropdown: Code for revision tracking
    udf_uobn_uobn_hk STRING,         -- Dropdown: UOBN/UOBN-HK booking number
    udf_income_exp_type STRING,      -- Dropdown: Type of income/expense
    udf_currency_hedge BOOLEAN,      -- Boolean: If currency hedge

    -- ========================================
    -- ADDITIONAL FIELDS (from AFA2DEC7 & 6D01B467 images)
    -- ========================================
    realized_pnl DECIMAL(20,6),      -- Calculated: P&L for sell trades

    -- ========================================
    -- SPECIFIC FIELDS FOR DIFFERENT TRADE TYPES
    -- ========================================

    -- For ADD_LONG
    parent_trade_id BIGINT,          -- Reference to original trade

    -- For DELIVER_LONG
    delivery_type STRING,            -- Transfer, Corporate Action, Settlement
    counterparty STRING,             -- FK to cis_counterparty

    -- For REDUCTION_BASIS
    reduction_type STRING,           -- Return of Capital, Amortization, Write-down
    reduction_amount DECIMAL(20,6),  -- Amount of reduction per unit
    units_affected DECIMAL(20,6),    -- Number of units affected

    -- For INCOME
    income_type STRING,              -- Dividend, Interest, Premium, Distribution
    ex_date STRING,                  -- Ex-dividend date (YYYY-MM-DD)
    record_date STRING,              -- Record date (YYYY-MM-DD)
    pay_date STRING,                 -- Payment date (YYYY-MM-DD)
    amount_per_unit DECIMAL(20,6),   -- Income per unit
    gross_amount DECIMAL(20,6),      -- Calculated: Gross income
    withholding_tax DECIMAL(20,6),   -- WHT amount
    net_amount DECIMAL(20,6),        -- Calculated: Net income

    -- For SPLIT_TRANSACTION
    split_type STRING,               -- Stock Split, Reverse Split, Lot Split
    split_ratio_new INT,             -- New shares (e.g., 2 in 2:1)
    split_ratio_old INT,             -- Old shares (e.g., 1 in 2:1)
    effective_date STRING,           -- Effective date (YYYY-MM-DD)

    -- ========================================
    -- WORKFLOW STATUS (Four-Eyes)
    -- ========================================
    -- Values: INITIAL, MODIFIED, PENDING_VALIDATION, VALIDATED, CANCELLED, SETTLED
    status STRING NOT NULL,
    is_active BOOLEAN,               -- Soft delete flag
    is_deleted BOOLEAN,              -- Soft delete marker

    -- Source System
    src_system STRING,               -- CIS = UI created, GMP = ETL loaded

    -- ========================================
    -- MAKER INFO (who created/modified)
    -- ========================================
    created_by STRING,
    created_at STRING,
    updated_by STRING,
    updated_at STRING,

    -- ========================================
    -- SUBMISSION INFO (Maker submits for validation)
    -- ========================================
    submitted_by STRING,
    submitted_at STRING,

    -- ========================================
    -- VALIDATION INFO (Checker validates)
    -- ========================================
    validated_by STRING,
    validated_at STRING,
    validation_comments STRING,

    -- ========================================
    -- SETTLEMENT INFO (Checker settles/activates)
    -- ========================================
    settled_by STRING,
    settled_at STRING,
    settlement_comments STRING,

    -- ========================================
    -- CANCELLATION INFO
    -- ========================================
    cancelled_by STRING,
    cancelled_at STRING,
    cancel_reason STRING,

    -- ========================================
    -- INTERNAL REFERENCES
    -- ========================================
    internal_ref STRING,             -- Internal tracking number
    external_ref STRING,             -- External/client reference

    PRIMARY KEY (trade_id)
)
PARTITION BY HASH PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- ============================================================================
-- TABLE 2: cis_trade_history (Audit Trail)
-- ============================================================================
-- Tracks ALL changes to trades with field-level detail
-- Supports: old_value, new_value tracking per field
-- ============================================================================

DROP TABLE IF EXISTS cis_trade_history;

CREATE TABLE cis_trade_history (
    -- Primary Key
    history_id BIGINT NOT NULL,

    -- Trade Reference
    trade_id BIGINT NOT NULL,
    deal_number STRING,

    -- Action
    -- CREATE, UPDATE, SUBMIT, VALIDATE, REJECT, SETTLE, CANCEL, REACTIVATE
    action STRING NOT NULL,

    -- Status at time of action
    old_status STRING,
    new_status STRING,

    -- Field-level changes (JSON)
    -- Format: {"field_name": {"old": "old_value", "new": "new_value"}, ...}
    changes STRING,

    -- Comments
    comments STRING,

    -- Who performed the action
    performed_by STRING NOT NULL,
    performed_at STRING NOT NULL,

    -- Request metadata
    ip_address STRING,
    user_agent STRING,

    PRIMARY KEY (history_id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- ============================================================================
-- TABLE 3: cis_trade_note (Trade Notes)
-- ============================================================================
-- Stores notes/comments attached to trades
-- ============================================================================

DROP TABLE IF EXISTS cis_trade_note;

CREATE TABLE cis_trade_note (
    -- Primary Key
    note_id BIGINT NOT NULL,

    -- Trade Reference
    trade_id BIGINT NOT NULL,

    -- Note Content
    note_type STRING,          -- GENERAL, COMPLIANCE, RISK, SETTLEMENT, OTHER
    note_text STRING,

    -- References
    internal_ref STRING,
    external_ref STRING,

    -- Attachments (store as JSON array of file paths/references)
    attachments STRING,

    -- Metadata
    created_by STRING,
    created_at STRING,
    updated_by STRING,
    updated_at STRING,
    is_active BOOLEAN,

    PRIMARY KEY (note_id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- ============================================================================
-- TABLE 4: cis_trade_position (Versioned Position Snapshots)
-- ============================================================================
-- Tracks positions using a versioned snapshot pattern.
-- Each trade INSERTs a new version row (never UPDATE in place).
-- Latest position = MAX(version_id) per position_id.
-- Replaces both old cis_trade_details and cis_trade_details_history tables.
-- Position created on trade create (not settle).
--
-- CURRENCY NAMING CONVENTION:
--   FC = Foreign Currency = Security Currency (e.g., USD for AAPL)
--   LC = Local Currency = Portfolio Currency (e.g., SGD for Singapore fund)
-- ============================================================================

DROP TABLE IF EXISTS cis_trade_position;

CREATE TABLE cis_trade_position (
    -- Primary Key (auto-increment per snapshot)
    version_id BIGINT NOT NULL,

    -- Position Identity (same across all versions for a portfolio+security+basis)
    position_id BIGINT NOT NULL,

    -- POSITION BASIS: 'TRADED' or 'SETTLED'
    -- Determines when this position record takes effect
    position_basis STRING NOT NULL DEFAULT 'TRADED',

    -- Snapshot date (trade_date or settle_date depending on position_basis)
    position_date STRING NOT NULL,

    -- Reference dates from the trade
    trade_date STRING,                   -- Original trade date
    settle_date STRING,                  -- Original settlement date

    -- Portfolio Reference
    portfolio_short_name STRING NOT NULL,

    -- Security Reference
    security_label STRING NOT NULL,

    -- Position State (8 decimal precision for AVP)
    quantity DECIMAL(30,8),              -- Current holding quantity

    -- Cost in Foreign Currency (FC = Security Currency)
    average_cost_fc DECIMAL(30,8),       -- Weighted average cost (AVP) in FC
    total_cost_fc DECIMAL(30,8),         -- Total cost basis in FC

    -- Cost in Local Currency (LC = Portfolio Currency)
    average_cost_lc DECIMAL(30,8),       -- Weighted average cost (AVP) in LC
    total_cost_lc DECIMAL(30,8),         -- Total cost basis in LC

    -- P&L in Foreign Currency (Security Currency)
    realized_pnl_fc DECIMAL(30,8),       -- Cumulative realized P&L in FC
    unrealized_pnl_fc DECIMAL(30,8),     -- Unrealized P&L in FC (market_value - total_cost)

    -- P&L in Local Currency (Portfolio Currency)
    realized_pnl_lc DECIMAL(30,8),       -- Cumulative realized P&L in LC
    unrealized_pnl_lc DECIMAL(30,8),     -- Unrealized P&L in LC

    -- Market Value
    market_price DECIMAL(30,8),          -- Latest market price in FC
    market_value_fc DECIMAL(30,8),       -- qty * market_price (in FC)
    market_value_lc DECIMAL(30,8),       -- Market value in LC

    -- Dividend Tracking (accumulated from Corporate Actions)
    dividend_fc DECIMAL(30,8),           -- Accumulated dividends in FC
    dividend_lc DECIMAL(30,8),           -- Accumulated dividends in LC

    -- Trade that caused this version
    trade_id BIGINT,
    trade_type STRING,                   -- BUY, SELL

    -- Additional Info
    lots_held INT,
    custodian STRING,
    sub_custodian STRING,

    -- Multi-currency support
    security_currency STRING,            -- Security's trading currency (FC)
    portfolio_currency STRING,           -- Portfolio's base currency (LC)
    fx_rate DECIMAL(30,8),               -- FX rate used (FC to LC)

    -- Status
    status STRING,                       -- OPEN, CLOSED
    is_active BOOLEAN,
    is_latest BOOLEAN DEFAULT TRUE,      -- Latest version for this portfolio+security+basis

    -- Last Corporate Action / Cash Flow tracking
    last_ca_id BIGINT,                   -- Last CA that generated cash flow
    last_ca_number STRING,               -- Last CA number
    last_ca_type STRING,                 -- Last CA type (DIVIDEND, INTEREST, etc.)
    last_ca_date STRING,                 -- Date of last CA (ex_date)
    last_cash_flow_id BIGINT,            -- Last cash flow ID generated from CA
    last_cash_flow_number STRING,        -- Last cash flow number
    last_cash_flow_amount_fc DECIMAL(30,8), -- Amount of last cash flow in FC (foreign_ccy_amt)
    last_cash_flow_amount_lc DECIMAL(30,8), -- Amount of last cash flow in LC (local_ccy_amt)

    -- Metadata
    created_by STRING,
    created_at STRING,
    updated_by STRING,
    updated_at STRING,

    PRIMARY KEY (version_id)
)
PARTITION BY HASH (version_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- ============================================================================
-- TABLE 6: cis_trade_lot (Lot Tracking for FIFO/LIFO)
-- ============================================================================
-- Tracks individual lots for accurate P&L calculation
-- ============================================================================

DROP TABLE IF EXISTS cis_trade_lot;

CREATE TABLE cis_trade_lot (
    -- Primary Key
    lot_id BIGINT NOT NULL,

    -- Position Reference
    position_id BIGINT NOT NULL,
    portfolio_short_name STRING,
    security_label STRING,

    -- Lot Details
    lot_number INT,
    quantity DECIMAL(20,6),
    purchase_price DECIMAL(20,6),
    purchase_date STRING,
    purchase_trade_id BIGINT,

    -- Cost Basis
    cost_basis DECIMAL(20,6),
    adjusted_cost_basis DECIMAL(20,6),   -- After reduction basis adjustments

    -- Status
    status STRING,                        -- OPEN, PARTIALLY_SOLD, CLOSED
    remaining_quantity DECIMAL(20,6),

    -- Timestamps
    created_at STRING,
    updated_at STRING,

    PRIMARY KEY (lot_id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- ============================================================================
-- SEQUENCE TABLE for ID Generation
-- ============================================================================
-- Since Kudu doesn't support auto-increment, we need a sequence table
-- ============================================================================

DROP TABLE IF EXISTS cis_sequence;

CREATE TABLE cis_sequence (
    sequence_name STRING NOT NULL,
    current_value BIGINT,
    increment_by INT,
    PRIMARY KEY (sequence_name)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Initialize sequences
INSERT INTO cis_sequence VALUES ('trade_id', 1000000, 1);
INSERT INTO cis_sequence VALUES ('trade_history_id', 1000000, 1);
INSERT INTO cis_sequence VALUES ('trade_note_id', 1000000, 1);
INSERT INTO cis_sequence VALUES ('position_id', 1000000, 1);
INSERT INTO cis_sequence VALUES ('position_version_id', 1000000, 1);
INSERT INTO cis_sequence VALUES ('lot_id', 1000000, 1);

-- ============================================================================
-- INDEXES (via Impala - informational, not enforced by Kudu)
-- ============================================================================
-- Note: Kudu primary keys are automatically indexed
-- These are recommended secondary indexes if using a different data store

/*
-- Trade indexes
CREATE INDEX idx_trade_portfolio ON cis_trade (portfolio_short_name);
CREATE INDEX idx_trade_security ON cis_trade (security_label);
CREATE INDEX idx_trade_date ON cis_trade (trade_date);
CREATE INDEX idx_trade_status ON cis_trade (status);
CREATE INDEX idx_trade_type ON cis_trade (trade_type);
CREATE INDEX idx_trade_deal_number ON cis_trade (deal_number);

-- Trade history indexes
CREATE INDEX idx_trade_history_trade ON cis_trade_history (trade_id);
CREATE INDEX idx_trade_history_date ON cis_trade_history (performed_at);

-- Trade position indexes
CREATE INDEX idx_trade_position_portfolio ON cis_trade_position (portfolio_short_name);
CREATE INDEX idx_trade_position_security ON cis_trade_position (security_label);
CREATE INDEX idx_trade_position_position_id ON cis_trade_position (position_id);
*/

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- List all created tables
SHOW TABLES LIKE 'cis_trade*';
SHOW TABLES LIKE 'cis_sequence';

-- Check table structures
DESCRIBE cis_trade;
DESCRIBE cis_trade_history;
DESCRIBE cis_trade_note;
DESCRIBE cis_trade_position;
DESCRIBE cis_trade_lot;
DESCRIBE cis_sequence;

-- Check sequences initialized
SELECT * FROM cis_sequence;

-- ============================================================================
-- SAMPLE DATA (for testing - uncomment to run)
-- ============================================================================

/*
-- Sample BUY trade
INSERT INTO cis_trade VALUES (
    1000001,                         -- trade_id
    'BUY',                           -- trade_type
    'DEAL-2024-001',                 -- deal_number
    'UOB-SG-TRADING',                -- portfolio_short_name
    'UOB Singapore Trading Account', -- portfolio_full_name
    'AAPL',                          -- security_label
    'Apple Inc.',                    -- security_full_name
    'EQUITY',                        -- security_type
    'CONFIRMED',                     -- trade_status
    '2024-01-15',                    -- trade_date
    '2024-01-17',                    -- settle_date
    NULL,                            -- expiry_date
    100,                             -- quantity
    1,                               -- face_value
    100,                             -- lot
    150.50,                          -- price
    25.00,                           -- commission
    0,                               -- accrued_interest
    2.50,                            -- sec_fee
    0,                               -- other_charges
    15077.50,                        -- total_amount
    'OPEN',                          -- open_close_position
    NULL,                            -- extension
    'BROKER-001',                    -- brokers
    'Goldman Sachs',                 -- broker_name
    'EQUITY',                        -- gl_fund_type
    'CC-001',                        -- gl_cost_centre
    'ACC-001',                       -- gl_account_code
    'CONTRACT-001',                  -- contract_ref
    NULL,                            -- fd_receipt
    '2024-01-15',                    -- org_pur_date
    1.0,                             -- open_fx_rate
    15077.50,                        -- curr_dealing
    15077.50,                        -- open_dealing
    0,                               -- input_tax_oth
    100,                             -- qty_entitled
    'FIFO',                          -- selling_rule
    100000.00,                       -- cash_balance
    'DBS',                           -- custodian
    'STD',                           -- amor_accr_method
    1,                               -- lots_held
    100,                             -- quantity_held
    'Initial buy order',            -- remarks
    'Equity',                        -- udf_fund_type
    NULL,                            -- udf_section_31_26
    'SUB-CUST-001',                  -- udf_sub_custodian
    false,                           -- udf_disclosure_req
    false,                           -- udf_counter_pledged
    NULL,                            -- udf_revision_code
    'UOBN-SG-001',                   -- udf_uobn_uobn_hk
    'TRADING',                       -- udf_income_exp_type
    false,                           -- udf_currency_hedge
    NULL,                            -- realized_pnl
    NULL,                            -- parent_trade_id
    NULL,                            -- delivery_type
    NULL,                            -- counterparty
    NULL,                            -- reduction_type
    NULL,                            -- reduction_amount
    NULL,                            -- units_affected
    NULL,                            -- income_type
    NULL,                            -- ex_date
    NULL,                            -- record_date
    NULL,                            -- pay_date
    NULL,                            -- amount_per_unit
    NULL,                            -- gross_amount
    NULL,                            -- withholding_tax
    NULL,                            -- net_amount
    NULL,                            -- split_type
    NULL,                            -- split_ratio_new
    NULL,                            -- split_ratio_old
    NULL,                            -- effective_date
    'INITIAL',                       -- status
    true,                            -- is_active
    false,                           -- is_deleted
    'CIS',                           -- src_system
    'john.doe',                      -- created_by
    '2024-01-15 10:30:00',           -- created_at
    'john.doe',                      -- updated_by
    '2024-01-15 10:30:00',           -- updated_at
    NULL,                            -- submitted_by
    NULL,                            -- submitted_at
    NULL,                            -- validated_by
    NULL,                            -- validated_at
    NULL,                            -- validation_comments
    NULL,                            -- settled_by
    NULL,                            -- settled_at
    NULL,                            -- settlement_comments
    NULL,                            -- cancelled_by
    NULL,                            -- cancelled_at
    NULL,                            -- cancel_reason
    'INT-REF-001',                   -- internal_ref
    'EXT-REF-001'                    -- external_ref
);
*/

-- ============================================================================
-- END OF DDL
-- ============================================================================
