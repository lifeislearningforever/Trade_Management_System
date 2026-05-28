-- ============================================================================
-- CIS Hive External Tables DDL
-- ============================================================================
-- Purpose  : Mirror every CIS Kudu table as a Hive external PARQUET table
--            partitioned by processing_date.
--            These tables are used as the daily raw landing/archive layer.
--            The application NEVER reads from Hive — only from Kudu.
--
-- Usage (SIT edgenode):
--   impala-shell -i <impala-host>:21050 -d gmp_cis \
--     -f create_hive_external_tables.sql
--
-- Notes:
--   - All tables land under /mrw/cis/hive/<table_name>/
--   - Default partition '20260130' is added after each table is created
--   - Add new daily partitions via:
--       ALTER TABLE <tbl> ADD IF NOT EXISTS
--         PARTITION (processing_date='YYYYMMDD')
--         LOCATION '/mrw/cis/hive/<tbl>/processing_date=YYYYMMDD';
--   - Drop old partitions to keep 90-day rolling window (see cleanup job)
--
-- Kudu → Hive type mapping used throughout:
--   BIGINT        → BIGINT
--   INT           → INT
--   STRING        → STRING
--   BOOLEAN       → BOOLEAN
--   DECIMAL(p,s)  → DECIMAL(p,s)
--   TIMESTAMP     → TIMESTAMP
--   DOUBLE        → DOUBLE
--
-- Created : 2026-04-10
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- STEP 0: Schema introspection (run these first on SIT to verify live columns)
-- ============================================================================
-- Uncomment one at a time to verify the column list before running DROP/CREATE.
--
-- DESCRIBE gmp_cis.cis_trade;
-- DESCRIBE gmp_cis.cis_trade_history;
-- DESCRIBE gmp_cis.cis_trade_note;
-- DESCRIBE gmp_cis.cis_trade_position;
-- DESCRIBE gmp_cis.cis_position_queue;
-- DESCRIBE gmp_cis.cis_settlement_queue;
-- DESCRIBE gmp_cis.cis_portfolio;
-- DESCRIBE gmp_cis.cis_security_kudu;
-- DESCRIBE gmp_cis.cis_counterparty_kudu;
-- DESCRIBE gmp_cis.cis_corporate_actions;
-- DESCRIBE gmp_cis.cis_corporate_actions_history;
-- DESCRIBE gmp_cis.cis_ca_cash_flow_queue;
-- DESCRIBE gmp_cis.cis_cash_flow;
-- DESCRIBE gmp_cis.cis_cash_flow_history;
-- DESCRIBE gmp_cis.cis_equity_price_kudu;
-- DESCRIBE gmp_cis.cis_fx_rate;
-- ============================================================================


-- ============================================================================
-- 1. cis_trade
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_trade;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_trade (
    trade_id                    BIGINT,
    trade_number                STRING,
    portfolio_short_name        STRING,
    security_label              STRING,
    trade_type                  STRING,
    quantity                    DECIMAL(30,8),
    price                       DECIMAL(30,8),
    trade_date                  STRING,
    settle_date                 STRING,
    value_date                  STRING,
    maturity_date               STRING,
    status                      STRING,
    counterparty_short_name     STRING,
    broker_short_name           STRING,
    currency                    STRING,
    portfolio_currency          STRING,
    commission                  DECIMAL(30,8),
    sec_fee                     DECIMAL(30,8),
    other_charges               DECIMAL(30,8),
    total_charges               DECIMAL(30,8),
    net_amount                  DECIMAL(30,8),
    gross_amount                DECIMAL(30,8),
    net_amount_lc               DECIMAL(30,8),
    gross_amount_lc             DECIMAL(30,8),
    fx_rate                     DECIMAL(30,8),
    accrued_interest            DECIMAL(30,8),
    accrued_interest_lc         DECIMAL(30,8),
    yield_rate                  DECIMAL(30,8),
    coupon_rate                 DECIMAL(30,8),
    isin                        STRING,
    description                 STRING,
    notes                       STRING,
    internal_reference          STRING,
    external_reference          STRING,
    src_system                  STRING,
    -- Maker-Checker workflow
    submitted_for_approval_at   STRING,
    reviewed_by                 STRING,
    reviewed_at                 STRING,
    reviewed_comments           STRING,
    -- Soft delete / audit
    is_deleted                  BOOLEAN,
    is_active                   BOOLEAN,
    created_by                  STRING,
    created_at                  BIGINT,
    updated_by                  STRING,
    updated_at                  BIGINT
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_trade'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_trade
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_trade/processing_date=20260130';


-- ============================================================================
-- 2. cis_trade_history
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_trade_history;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_trade_history (
    history_id          BIGINT,
    trade_id            BIGINT,
    trade_number        STRING,
    portfolio_short_name STRING,
    action              STRING,
    status              STRING,
    changes             STRING,
    comments            STRING,
    performed_by        STRING,
    performed_at        BIGINT
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_trade_history'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_trade_history
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_trade_history/processing_date=20260130';


-- ============================================================================
-- 3. cis_trade_note
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_trade_note;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_trade_note (
    note_id             BIGINT,
    trade_id            BIGINT,
    trade_number        STRING,
    note_text           STRING,
    note_type           STRING,
    is_deleted          BOOLEAN,
    created_by          STRING,
    created_at          BIGINT,
    updated_by          STRING,
    updated_at          BIGINT
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_trade_note'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_trade_note
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_trade_note/processing_date=20260130';


-- ============================================================================
-- 4. cis_trade_position
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_trade_position;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_trade_position (
    version_id                  BIGINT,
    position_id                 BIGINT,
    position_basis              STRING,
    position_date               STRING,
    trade_date                  STRING,
    settle_date                 STRING,
    portfolio_short_name        STRING,
    security_label              STRING,
    quantity                    DECIMAL(30,8),
    -- Cost (Foreign Currency = Security Currency)
    average_cost_fc             DECIMAL(30,8),
    total_cost_fc               DECIMAL(30,8),
    -- Cost (Local Currency = Portfolio Currency)
    average_cost_lc             DECIMAL(30,8),
    total_cost_lc               DECIMAL(30,8),
    -- P&L (FC)
    realized_pnl_fc             DECIMAL(30,8),
    unrealized_pnl_fc           DECIMAL(30,8),
    -- P&L (LC)
    realized_pnl_lc             DECIMAL(30,8),
    unrealized_pnl_lc           DECIMAL(30,8),
    -- Market Value
    market_price                DECIMAL(30,8),
    market_value_fc             DECIMAL(30,8),
    market_value_lc             DECIMAL(30,8),
    -- Dividends
    dividend_fc                 DECIMAL(30,8),
    dividend_lc                 DECIMAL(30,8),
    -- Trade reference
    trade_id                    BIGINT,
    trade_type                  STRING,
    -- Misc
    lots_held                   INT,
    custodian                   STRING,
    sub_custodian               STRING,
    -- Multi-currency
    security_currency           STRING,
    portfolio_currency          STRING,
    fx_rate                     DECIMAL(30,8),
    -- Status
    status                      STRING,
    is_active                   BOOLEAN,
    is_latest                   BOOLEAN,
    -- Last CA / Cash Flow tracking
    last_ca_id                  BIGINT,
    last_ca_number              STRING,
    last_ca_type                STRING,
    last_ca_date                STRING,
    last_cash_flow_id           BIGINT,
    last_cash_flow_number       STRING,
    last_cash_flow_amount_fc    DECIMAL(30,8),
    last_cash_flow_amount_lc    DECIMAL(30,8),
    -- Uncalled / Pipeline
    uncall_fc                   DECIMAL(30,8),
    uncall_lc                   DECIMAL(30,8),
    pipeline_fc                 DECIMAL(30,8),
    pipeline_lc                 DECIMAL(30,8),
    position_type               STRING,
    -- Audit
    created_by                  STRING,
    created_at                  STRING,
    updated_by                  STRING,
    updated_at                  STRING
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_trade_position'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_trade_position
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_trade_position/processing_date=20260130';


-- ============================================================================
-- 5. cis_position_queue
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_position_queue;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_position_queue (
    queue_id            BIGINT,
    trade_id            BIGINT,
    portfolio_id        STRING,
    security_id         STRING,
    trade_type          STRING,
    quantity            DECIMAL(30,8),
    price               DECIMAL(30,8),
    charges             DECIMAL(30,8),
    settle_date         STRING,
    security_currency   STRING,
    portfolio_currency  STRING,
    isin                STRING,
    security_name       STRING,
    status              STRING,
    retry_count         INT,
    error_message       STRING,
    queued_at           STRING,
    queued_by           STRING,
    processed_at        STRING,
    updated_at          STRING,
    sla_breach          BOOLEAN
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_position_queue'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_position_queue
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_position_queue/processing_date=20260130';


-- ============================================================================
-- 6. cis_settlement_queue
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_settlement_queue;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_settlement_queue (
    queue_id            BIGINT,
    trade_id            BIGINT,
    portfolio_id        STRING,
    security_id         STRING,
    trade_type          STRING,
    quantity            DECIMAL(30,8),
    price               DECIMAL(30,8),
    charges             DECIMAL(30,8),
    settle_date         STRING,
    security_currency   STRING,
    portfolio_currency  STRING,
    isin                STRING,
    security_name       STRING,
    status              STRING,
    retry_count         INT,
    error_message       STRING,
    queued_at           STRING,
    queued_by           STRING,
    processed_at        STRING,
    updated_at          STRING
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_settlement_queue'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_settlement_queue
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_settlement_queue/processing_date=20260130';


-- ============================================================================
-- 7. cis_portfolio
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_portfolio;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_portfolio (
    code                        STRING,
    name                        STRING,
    description                 STRING,
    currency                    STRING,
    manager                     STRING,
    portfolio_client            STRING,
    cash_balance_list           STRING,
    cash_balance                DECIMAL(20,2),
    status                      STRING,
    is_active                   BOOLEAN,
    cost_centre_code            STRING,
    corp_code                   STRING,
    account_group               STRING,
    portfolio_group             STRING,
    report_group                STRING,
    entity_group                STRING,
    revaluation_status          STRING,
    created_by                  STRING,
    created_at                  STRING,
    updated_by                  STRING,
    updated_at                  STRING
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_portfolio'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_portfolio
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_portfolio/processing_date=20260130';


-- ============================================================================
-- 8. cis_security_kudu  (Hive mirror named hive_cis_security for clarity)
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_security;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_security (
    security_id                     BIGINT,
    record_type                     STRING,
    security_name                   STRING,
    isin                            STRING,
    security_description            STRING,
    issuer                          STRING,
    ticker                          STRING,
    industry                        STRING,
    security_type                   STRING,
    investment_type                 STRING,
    issuer_type                     STRING,
    quoted_unquoted                 STRING,
    country_of_incorporation        STRING,
    country_of_exchange             STRING,
    country_of_issue                STRING,
    exchange_code                   STRING,
    currency_code                   STRING,
    price                           DECIMAL(20,4),
    shares_outstanding              BIGINT,
    beta                            DECIMAL(10,4),
    par_value                       DECIMAL(20,6),
    pct_hld_entity_1                STRING,
    pct_hld_entity_2                STRING,
    pct_hld_entity_3                STRING,
    pct_hld_entity_aggr             STRING,
    substantial_10_pct              STRING,
    cels                            STRING,
    pevc_s32_devest                 STRING,
    s32_representative              STRING,
    basel_iv_fund                   STRING,
    mas_643_entity_type             STRING,
    mas_6d_code                     STRING,
    fin_nonfin_ind                  STRING,
    business_unit_head              STRING,
    person_in_charge                STRING,
    core_noncore                    STRING,
    fund_index_fund                 STRING,
    management_limit_classification STRING,
    relative_index                  STRING,
    status                          STRING,
    src_system                      STRING,
    is_active                       BOOLEAN,
    created_by                      STRING,
    created_at                      BIGINT,
    updated_by                      STRING,
    updated_at                      BIGINT
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_security'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_security
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_security/processing_date=20260130';


-- ============================================================================
-- 9. cis_counterparty_kudu
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_counterparty;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_counterparty (
    counterparty_short_name         STRING,
    m_label                         STRING,
    counterparty_full_name          STRING,
    record_type                     STRING,
    address_line_0                  STRING,
    address_line_1                  STRING,
    address_line_2                  STRING,
    address_line_3                  STRING,
    city                            STRING,
    country                         STRING,
    postal_code                     STRING,
    fax_number                      STRING,
    telex_number                    STRING,
    primary_contact                 STRING,
    primary_number                  STRING,
    other_contact                   STRING,
    other_number                    STRING,
    industry                        STRING,
    industry_group                  STRING,
    is_broker                       BOOLEAN,
    is_custodian                    BOOLEAN,
    is_issuer                       BOOLEAN,
    is_bank                         BOOLEAN,
    is_subsidiary                   BOOLEAN,
    is_corporate                    BOOLEAN,
    subsidiary_level                STRING,
    counterparty_grandparent        STRING,
    counterparty_parent             STRING,
    resident_y_n                    STRING,
    mas_industry_code               STRING,
    country_of_incorporation        STRING,
    cels_code                       STRING,
    src_system                      STRING,
    sub_system                      STRING,
    data_cat                        STRING,
    data_frq                        STRING,
    src_id                          STRING,
    is_active                       BOOLEAN,
    is_deleted                      BOOLEAN,
    created_by                      STRING,
    created_at                      TIMESTAMP,
    updated_by                      STRING,
    updated_at                      TIMESTAMP
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_counterparty'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_counterparty
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_counterparty/processing_date=20260130';


-- ============================================================================
-- 10. cis_corporate_actions
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_corporate_actions;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_corporate_actions (
    ca_id                       BIGINT,
    ca_number                   STRING,
    ca_type                     STRING,
    security_name               STRING,
    announcement_date           STRING,
    ex_date                     STRING,
    record_date                 STRING,
    payment_date                STRING,
    effective_date              STRING,
    subscription_start_date     STRING,
    subscription_end_date       STRING,
    price                       DECIMAL(20,6),
    currency                    STRING,
    src_system                  STRING,
    status                      STRING,
    submitted_for_approval_at   STRING,
    reviewed_by                 STRING,
    reviewed_at                 STRING,
    reviewed_comments           STRING,
    is_deleted                  BOOLEAN,
    is_active                   BOOLEAN,
    created_by                  STRING,
    created_at                  BIGINT,
    updated_by                  STRING,
    updated_at                  BIGINT
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_corporate_actions'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_corporate_actions
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_corporate_actions/processing_date=20260130';


-- ============================================================================
-- 11. cis_corporate_actions_history
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_corporate_actions_history;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_corporate_actions_history (
    history_id      BIGINT,
    ca_id           BIGINT,
    ca_number       STRING,
    security_name   STRING,
    action          STRING,
    status          STRING,
    changes         STRING,
    comments        STRING,
    performed_by    STRING,
    performed_at    BIGINT
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_corporate_actions_history'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_corporate_actions_history
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_corporate_actions_history/processing_date=20260130';


-- ============================================================================
-- 12. cis_ca_cash_flow_queue
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_ca_cash_flow_queue;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_ca_cash_flow_queue (
    queue_id            BIGINT,
    ca_id               BIGINT,
    ca_number           STRING,
    ca_type             STRING,
    security_name       STRING,
    ex_date             STRING,
    record_date         STRING,
    payment_date        STRING,
    price               DECIMAL(30,8),
    currency            STRING,
    status              STRING,
    retry_count         BIGINT,
    error_message       STRING,
    cash_flows_created  BIGINT,
    total_amount        DECIMAL(30,8),
    processed_at        BIGINT,
    created_at          BIGINT,
    created_by          STRING
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_ca_cash_flow_queue'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_ca_cash_flow_queue
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_ca_cash_flow_queue/processing_date=20260130';


-- ============================================================================
-- 13. cis_cash_flow
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_cash_flow;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_cash_flow (
    cash_flow_id            BIGINT,
    cash_flow_number        STRING,
    security_label          STRING,
    portfolio_short_name    STRING,
    cash_flow_type          STRING,
    send_receive            STRING,
    position_updated        BOOLEAN,
    foreign_ccy             STRING,
    local_ccy               STRING,
    local_ccy_amt           DECIMAL(30,8),
    foreign_ccy_amt         DECIMAL(30,8),
    flow_amount_local       DECIMAL(30,8),
    dividend_price          DECIMAL(30,8),
    quantity                DECIMAL(30,8),
    fx_rate                 DECIMAL(30,8),
    tax_deducted_fc         DECIMAL(30,8),
    tax_deducted_lc         DECIMAL(30,8),
    other_charges_fc        DECIMAL(30,8),
    gl_acc_no               STRING,
    src_system              STRING,
    ca_id                   BIGINT,
    ca_number               STRING,
    payment_date            STRING,
    trade_date              STRING,
    value_date              STRING,
    dividend_date           STRING,
    ex_date                 STRING,
    record_date             STRING,
    is_deleted              BOOLEAN,
    is_active               BOOLEAN,
    created_by              STRING,
    created_at              TIMESTAMP,
    updated_by              STRING,
    updated_at              TIMESTAMP,
    status                  STRING,
    validated_by            STRING,
    validated_at            TIMESTAMP,
    validation_comments     STRING,
    settled_by              STRING,
    settled_at              TIMESTAMP,
    settlement_comments     STRING,
    cancelled_by            STRING,
    cancelled_at            TIMESTAMP,
    cancel_reason           STRING
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_cash_flow'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_cash_flow
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_cash_flow/processing_date=20260130';


-- ============================================================================
-- 14. cis_cash_flow_history
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_cash_flow_history;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_cash_flow_history (
    history_id              BIGINT,
    cash_flow_id            BIGINT,
    cash_flow_number        STRING,
    portfolio_short_name    STRING,
    action                  STRING,
    status                  STRING,
    changes                 STRING,
    comments                STRING,
    performed_by            STRING,
    performed_at            BIGINT
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_cash_flow_history'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_cash_flow_history
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_cash_flow_history/processing_date=20260130';


-- ============================================================================
-- 15. cis_equity_price_kudu
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_equity_price;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_equity_price (
    currency_code       STRING,
    security_label      STRING,
    price_date          STRING,
    isin                STRING,
    main_closing_price  DECIMAL(18,6),
    price_timestamp     BIGINT,
    src_system          STRING,
    is_active           BOOLEAN,
    created_by          STRING,
    created_at          BIGINT,
    updated_by          STRING,
    updated_at          BIGINT
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_equity_price'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_equity_price
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_equity_price/processing_date=20260130';


-- ============================================================================
-- 16. cis_fx_rate
-- ============================================================================
DROP TABLE IF EXISTS gmp_cis.hive_cis_fx_rate;

CREATE EXTERNAL TABLE gmp_cis.hive_cis_fx_rate (
    rate_id         STRING,
    from_currency   STRING,
    to_currency     STRING,
    rate            DOUBLE,
    inverse_rate    DOUBLE,
    rate_date       STRING,
    effective_date  STRING,
    source          STRING,
    is_active       BOOLEAN,
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP,
    created_by      STRING,
    updated_by      STRING
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/mrw/cis/hive/cis_fx_rate'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.hive_cis_fx_rate
    ADD IF NOT EXISTS PARTITION (processing_date='20260130')
    LOCATION '/mrw/cis/hive/cis_fx_rate/processing_date=20260130';


-- ============================================================================
-- VERIFICATION
-- ============================================================================
-- Run after all tables are created to confirm partition exists.

SHOW TABLES IN gmp_cis LIKE 'hive_cis_*';

SHOW PARTITIONS gmp_cis.hive_cis_trade;
SHOW PARTITIONS gmp_cis.hive_cis_trade_position;
SHOW PARTITIONS gmp_cis.hive_cis_portfolio;
SHOW PARTITIONS gmp_cis.hive_cis_security;
SHOW PARTITIONS gmp_cis.hive_cis_counterparty;
SHOW PARTITIONS gmp_cis.hive_cis_corporate_actions;
SHOW PARTITIONS gmp_cis.hive_cis_cash_flow;
SHOW PARTITIONS gmp_cis.hive_cis_equity_price;
SHOW PARTITIONS gmp_cis.hive_cis_fx_rate;


-- ============================================================================
-- ADD DAILY PARTITION TEMPLATE
-- ============================================================================
-- Run each morning (Control-M) to register the new partition before the ETL
-- loads data.  Replace YYYYMMDD with actual date.
--
-- ALTER TABLE gmp_cis.hive_cis_trade
--     ADD IF NOT EXISTS PARTITION (processing_date='YYYYMMDD')
--     LOCATION '/mrw/cis/hive/cis_trade/processing_date=YYYYMMDD';
--
-- ALTER TABLE gmp_cis.hive_cis_trade_position
--     ADD IF NOT EXISTS PARTITION (processing_date='YYYYMMDD')
--     LOCATION '/mrw/cis/hive/cis_trade_position/processing_date=YYYYMMDD';
--
-- (repeat for each hive_cis_* table)
-- ============================================================================


-- ============================================================================
-- DROP PARTITION > 90 DAYS (rolling cleanup template)
-- ============================================================================
-- Run weekly.  Replace OLD_DATE with the partition to drop.
--
-- ALTER TABLE gmp_cis.hive_cis_trade      DROP IF EXISTS PARTITION (processing_date='OLD_DATE');
-- ALTER TABLE gmp_cis.hive_cis_trade_position DROP IF EXISTS PARTITION (processing_date='OLD_DATE');
-- (repeat for each table)
-- ============================================================================
