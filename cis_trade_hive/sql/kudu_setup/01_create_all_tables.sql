-- ============================================================================
-- CIS Trade Hive — Complete Kudu DDL (Environment-Independent)
-- ============================================================================
-- Description : Single-file setup for all Kudu tables in gmp_cis.
--               kudu.master_addresses is templated with {{KUDU_MASTERS}}.
--               Substitute before running:
--
--               Docker  : localhost:7051
--               CML/Prod: <cloudera-kudu-master>:7051
--
-- Run via the bundled runner (recommended):
--   python sql/kudu_setup/run_setup.py --env docker
--   python sql/kudu_setup/run_setup.py --env cml --kudu-masters host1:7051,host2:7051
--
-- Run manually (after substitution):
--   sed 's/{{KUDU_MASTERS}}/localhost:7051/g' 01_create_all_tables.sql > /tmp/setup.sql
--   impala-shell -i localhost:21050 -f /tmp/setup.sql
--
-- Tables created (39 Kudu tables + sequences):
--   Section 1 : Core / ACL / RBAC (9 tables)
--   Section 2 : Reference data — currency, country, calendar, counterparty (4 tables)
--   Section 3 : Portfolio (2 tables)
--   Section 4 : Security master (2 tables)
--   Section 5 : Trade (7 tables — trade, history, note, position, queues, event queue)
--   Section 6 : Market data — equity price, FX rates (3 tables)
--   Section 7 : UDF (5 tables)
--   Section 8 : Trade lookup tables (18 tables)
--   Section 9 : Corporate actions + cash flow (6 tables)
--   Section 10: Upload / datasource (2 tables)
--   Section 11: System date / help content (2 tables)
--   Section 12: Sequences + seed data
-- ============================================================================

-- ============================================================================
-- DATABASE
-- ============================================================================

CREATE DATABASE IF NOT EXISTS gmp_cis;
USE gmp_cis;

-- ============================================================================
-- SECTION 1: CORE / ACL / RBAC
-- ============================================================================

-- 1.1  Audit Log
CREATE TABLE IF NOT EXISTS cis_audit_log (
    audit_id         BIGINT NOT NULL,
    audit_timestamp  STRING,
    user_id          STRING,
    username         STRING,
    user_email       STRING,
    action_type      STRING,
    action_category  STRING,
    action_description STRING,
    entity_type      STRING,
    entity_id        STRING,
    entity_name      STRING,
    field_name       STRING,
    old_value        STRING,
    new_value        STRING,
    request_method   STRING,
    request_path     STRING,
    request_params   STRING,
    status           STRING,
    status_code      INT,
    error_message    STRING,
    error_traceback  STRING,
    session_id       STRING,
    ip_address       STRING,
    user_agent       STRING,
    module_name      STRING,
    function_name    STRING,
    duration_ms      BIGINT,
    tags             STRING,
    `metadata`       STRING,
    audit_date       STRING,
    PRIMARY KEY (audit_id)
)
PARTITION BY HASH (audit_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 1.2  Legacy User (ACL v1 — kept for backward compat)
CREATE TABLE IF NOT EXISTS cis_user (
    user_id            BIGINT NOT NULL,
    username           STRING,
    login              STRING,
    name               STRING,
    email              STRING,
    domain             STRING,
    entity             STRING,
    cis_user_group_id  BIGINT,
    is_active          BOOLEAN,
    is_deleted         BOOLEAN,
    enabled            BOOLEAN,
    last_login         BIGINT,
    created_on         BIGINT,
    created_by         STRING,
    updated_on         BIGINT,
    updated_by         STRING,
    PRIMARY KEY (user_id)
)
PARTITION BY HASH (user_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 1.3  Legacy User Group (ACL v1)
CREATE TABLE IF NOT EXISTS cis_user_group (
    group_id    BIGINT NOT NULL,
    user_id     BIGINT,
    group_name  STRING,
    description STRING,
    is_active   BOOLEAN,
    is_deleted  BOOLEAN,
    created_at  BIGINT,
    updated_at  BIGINT,
    PRIMARY KEY (group_id)
)
PARTITION BY HASH (group_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 1.4  Legacy Group (ACL v1)
CREATE TABLE IF NOT EXISTS cis_group (
    group_id    BIGINT NOT NULL,
    group_name  STRING,
    description STRING,
    is_active   BOOLEAN,
    is_deleted  BOOLEAN,
    created_at  BIGINT,
    updated_at  BIGINT,
    PRIMARY KEY (group_id)
)
PARTITION BY HASH (group_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 1.5  Legacy Group Permissions (ACL v1)
CREATE TABLE IF NOT EXISTS cis_group_permissions (
    permission_id   BIGINT NOT NULL,
    group_id        BIGINT,
    permission_name STRING,
    can_view        BOOLEAN,
    can_create      BOOLEAN,
    can_edit        BOOLEAN,
    can_delete      BOOLEAN,
    can_approve     BOOLEAN,
    object_id       STRING,
    read_write      STRING,
    is_active       BOOLEAN,
    is_deleted      BOOLEAN,
    created_at      BIGINT,
    updated_at      BIGINT,
    PRIMARY KEY (permission_id)
)
PARTITION BY HASH (permission_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 1.6  RBAC v2 — User Info
CREATE TABLE IF NOT EXISTS cis_user_info (
    user_id        STRING NOT NULL,
    login          STRING,
    email          STRING,
    name           STRING,
    default_entity STRING,
    last_login     TIMESTAMP,
    is_active      BOOLEAN,
    is_deleted     BOOLEAN,
    created_on     TIMESTAMP,
    created_by     STRING,
    updated_on     TIMESTAMP,
    updated_by     STRING,
    PRIMARY KEY (user_id)
)
PARTITION BY HASH (user_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 1.7  RBAC v2 — User Group Info
CREATE TABLE IF NOT EXISTS cis_user_group_info (
    user_group_id STRING NOT NULL,
    group_name    STRING,
    description   STRING,
    entity        STRING,
    is_active     BOOLEAN,
    is_deleted    BOOLEAN,
    created_on    TIMESTAMP,
    created_by    STRING,
    updated_on    TIMESTAMP,
    updated_by    STRING,
    PRIMARY KEY (user_group_id)
)
PARTITION BY HASH (user_group_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 1.8  RBAC v2 — Permission Info
CREATE TABLE IF NOT EXISTS cis_permission_info (
    permission_id   STRING NOT NULL,
    permission_name STRING,
    entity          STRING,
    description     STRING,
    is_active       BOOLEAN,
    is_deleted      BOOLEAN,
    created_on      TIMESTAMP,
    created_by      STRING,
    updated_on      TIMESTAMP,
    updated_by      STRING,
    PRIMARY KEY (permission_id)
)
PARTITION BY HASH (permission_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 1.9  RBAC v2 — User-Group Mapping
CREATE TABLE IF NOT EXISTS cis_user_group_mapping_info (
    user_group_mapping_id STRING NOT NULL,
    user_id               STRING,
    entity                STRING,
    group_name            STRING,
    is_active             BOOLEAN,
    is_deleted            BOOLEAN,
    created_on            TIMESTAMP,
    created_by            STRING,
    updated_on            TIMESTAMP,
    updated_by            STRING,
    PRIMARY KEY (user_group_mapping_id)
)
PARTITION BY HASH (user_group_mapping_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 1.10 RBAC v2 — Group-Permission Map
CREATE TABLE IF NOT EXISTS cis_group_permission_map (
    group_permission_id STRING NOT NULL,
    group_name          STRING,
    permission_name     STRING,
    entity              STRING,
    mode                STRING,
    description         STRING,
    is_active           BOOLEAN,
    is_deleted          BOOLEAN,
    created_on          TIMESTAMP,
    created_by          STRING,
    updated_on          TIMESTAMP,
    updated_by          STRING,
    PRIMARY KEY (group_permission_id)
)
PARTITION BY HASH (group_permission_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- ============================================================================
-- SECTION 2: REFERENCE DATA
-- ============================================================================

-- 2.1  Currency
CREATE TABLE IF NOT EXISTS gmp_cis_sta_dly_currency (
    iso_code       STRING NOT NULL,
    name           STRING,
    full_name      STRING,
    symbol         STRING,
    precision_val  STRING,
    calendar       STRING,
    spot_schedule  STRING,
    rate_precision STRING,
    PRIMARY KEY (iso_code)
)
PARTITION BY HASH (iso_code) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 2.2  Country
CREATE TABLE IF NOT EXISTS gmp_cis_sta_dly_country (
    label     STRING NOT NULL,
    full_name STRING,
    PRIMARY KEY (label)
)
PARTITION BY HASH (label) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 2.3  Calendar
CREATE TABLE IF NOT EXISTS gmp_cis_sta_dly_calendar (
    calendar_id          BIGINT NOT NULL,
    calendar_label       STRING,
    calendar_description STRING,
    holiday_date         STRING,
    PRIMARY KEY (calendar_id)
)
PARTITION BY HASH (calendar_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 2.4  Counterparty
CREATE TABLE IF NOT EXISTS cis_counterparty_kudu (
    counterparty_short_name  STRING NOT NULL,
    m_label                  STRING,
    counterparty_full_name   STRING,
    record_type              STRING,
    address_line_0           STRING,
    address_line_1           STRING,
    address_line_2           STRING,
    address_line_3           STRING,
    city                     STRING,
    country                  STRING,
    postal_code              STRING,
    fax_number               STRING,
    telex_number             STRING,
    primary_contact          STRING,
    primary_number           STRING,
    other_contact            STRING,
    other_number             STRING,
    industry                 STRING,
    industry_group           STRING,
    is_broker                BOOLEAN,
    is_custodian             BOOLEAN,
    is_issuer                BOOLEAN,
    is_bank                  BOOLEAN,
    is_subsidiary            BOOLEAN,
    is_corporate             BOOLEAN,
    subsidiary_level         STRING,
    counterparty_grandparent STRING,
    counterparty_parent      STRING,
    resident_y_n             STRING,
    mas_industry_code        STRING,
    country_of_incorporation STRING,
    cels_code                STRING,
    src_system               STRING,
    sub_system               STRING,
    data_cat                 STRING,
    data_frq                 STRING,
    src_id                   STRING,
    processing_date          STRING,
    is_active                BOOLEAN,
    is_deleted               BOOLEAN,
    created_by               STRING,
    created_at               BIGINT,
    updated_by               STRING,
    updated_at               BIGINT,
    PRIMARY KEY (counterparty_short_name)
)
PARTITION BY HASH (counterparty_short_name) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- ============================================================================
-- SECTION 3: PORTFOLIO
-- ============================================================================

-- 3.1  Portfolio
CREATE TABLE IF NOT EXISTS cis_portfolio (
    name                 STRING NOT NULL,
    description          STRING,
    currency             STRING,
    manager              STRING,
    portfolio_client     STRING,
    cash_balance         STRING,
    cost_centre_code     STRING,
    corp_code            STRING,
    account_group        STRING,
    portfolio_group      STRING,
    report_group         STRING,
    entity_group         STRING,
    revaluation_status   STRING,
    src_system           STRING,
    status               STRING,
    is_active            BOOLEAN,
    created_by           STRING,
    created_at           STRING,
    updated_by           STRING,
    updated_at           STRING,
    submitted_by         STRING,
    submitted_at         STRING,
    validated_by         STRING,
    validated_at         STRING,
    validation_comments  STRING,
    settled_by           STRING,
    settled_at           STRING,
    settlement_comments  STRING,
    cancelled_by         STRING,
    cancelled_at         STRING,
    cancel_reason        STRING,
    PRIMARY KEY (name)
)
PARTITION BY HASH (name) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 3.2  Portfolio History
CREATE TABLE IF NOT EXISTS cis_portfolio_history (
    history_id     BIGINT NOT NULL,
    portfolio_name STRING,
    action         STRING,
    old_status     STRING,
    new_status     STRING,
    changes        STRING,
    comments       STRING,
    performed_by   STRING,
    performed_at   STRING,
    ip_address     STRING,
    user_agent     STRING,
    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- ============================================================================
-- SECTION 4: SECURITY MASTER
-- ============================================================================

-- 4.1  Security Master (Kudu-native)
CREATE TABLE IF NOT EXISTS cis_security_kudu (
    security_id                     BIGINT NOT NULL,
    security_name                   STRING NOT NULL,
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
    country_of_primary_exchange     STRING,
    exchange_code                   STRING,
    currency_code                   STRING,
    price                           DECIMAL(20, 4),
    price_date                      STRING,
    price_source                    STRING,
    shares_outstanding              BIGINT,
    beta                            DECIMAL(10, 4),
    par_value                       DECIMAL(20, 6),
    shareholding_entity_1           DECIMAL(10, 4),
    shareholding_entity_2           DECIMAL(10, 4),
    shareholding_entity_3           DECIMAL(10, 4),
    shareholding_aggregated         DECIMAL(10, 4),
    substantial_10_pct              STRING,
    bwciif                          BIGINT,
    bwciif_others                   BIGINT,
    cels                            STRING,
    approved_s32                    STRING,
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
    status                          STRING DEFAULT 'DRAFT',
    submitted_for_approval_at       BIGINT,
    submitted_by                    STRING,
    reviewed_at                     BIGINT,
    reviewed_by                     STRING,
    review_comments                 STRING,
    is_active                       BOOLEAN DEFAULT true,
    created_by                      STRING NOT NULL,
    created_at                      BIGINT NOT NULL,
    updated_by                      STRING NOT NULL,
    updated_at                      BIGINT NOT NULL,
    PRIMARY KEY (security_id)
)
PARTITION BY HASH (security_id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 4.2  Security History
CREATE TABLE IF NOT EXISTS cis_security_history (
    history_id   BIGINT NOT NULL,
    security_id  BIGINT,
    security_name STRING,
    isin         STRING,
    action       STRING,
    status       STRING,
    changes      STRING,
    comments     STRING,
    performed_by STRING,
    performed_at BIGINT,
    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- ============================================================================
-- SECTION 5: TRADE
-- ============================================================================

-- 5.1  Trade
CREATE TABLE IF NOT EXISTS cis_trade (
    trade_id              BIGINT NOT NULL,
    trade_type            STRING,
    deal_number           STRING,
    portfolio_short_name  STRING,
    portfolio_full_name   STRING,
    security_label        STRING,
    security_full_name    STRING,
    security_type         STRING,
    trade_status          STRING,
    trade_date            STRING,
    settle_date           STRING,
    expiry_date           STRING,
    quantity              DECIMAL(20,6),
    face_value            DECIMAL(20,6),
    lot                   DECIMAL(20,6),
    price                 DECIMAL(20,6),
    commission            DECIMAL(20,6),
    accrued_interest      DECIMAL(20,6),
    sec_fee               DECIMAL(20,6),
    other_charges         DECIMAL(20,6),
    total_amount          DECIMAL(20,6),
    open_close_position   STRING,
    extension             STRING,
    brokers               STRING,
    broker_name           STRING,
    gl_fund_type          STRING,
    gl_cost_centre        STRING,
    gl_account_code       STRING,
    contract_ref          STRING,
    fd_receipt            STRING,
    org_pur_date          STRING,
    open_fx_rate          DECIMAL(20,6),
    curr_dealing          DECIMAL(20,6),
    open_dealing          DECIMAL(20,6),
    input_tax_oth         DECIMAL(20,6),
    qty_entitled          DECIMAL(20,6),
    selling_rule          STRING,
    cash_balance          DECIMAL(20,6),
    custodian             STRING,
    amor_accr_method      STRING,
    lots_held             DECIMAL(20,6),
    quantity_held         DECIMAL(20,6),
    remarks               STRING,
    udf_fund_type         STRING,
    udf_section_31_26     STRING,
    udf_sub_custodian     STRING,
    udf_disclosure_req    BOOLEAN,
    udf_counter_pledged   BOOLEAN,
    udf_revision_code     STRING,
    udf_uobn_uobn_hk      STRING,
    udf_income_exp_type   STRING,
    udf_currency_hedge    BOOLEAN,
    realized_pnl          DECIMAL(20,6),
    parent_trade_id       BIGINT,
    delivery_type         STRING,
    counterparty          STRING,
    reduction_type        STRING,
    reduction_amount      DECIMAL(20,6),
    units_affected        DECIMAL(20,6),
    income_type           STRING,
    ex_date               STRING,
    record_date           STRING,
    pay_date              STRING,
    amount_per_unit       DECIMAL(20,6),
    gross_amount          DECIMAL(20,6),
    withholding_tax       DECIMAL(20,6),
    net_amount            DECIMAL(20,6),
    split_type            STRING,
    split_ratio_new       INT,
    split_ratio_old       INT,
    effective_date        STRING,
    status                STRING,
    is_active             BOOLEAN,
    is_deleted            BOOLEAN,
    src_system            STRING,
    created_by            STRING,
    created_at            STRING,
    updated_by            STRING,
    updated_at            STRING,
    submitted_by          STRING,
    submitted_at          STRING,
    validated_by          STRING,
    validated_at          STRING,
    validation_comments   STRING,
    settled_by            STRING,
    settled_at            STRING,
    settlement_comments   STRING,
    cancelled_by          STRING,
    cancelled_at          STRING,
    cancel_reason         STRING,
    internal_ref          STRING,
    external_ref          STRING,
    PRIMARY KEY (trade_id)
)
PARTITION BY HASH (trade_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 5.2  Trade History
CREATE TABLE IF NOT EXISTS cis_trade_history (
    history_id   BIGINT NOT NULL,
    trade_id     BIGINT,
    deal_number  STRING,
    action       STRING,
    old_status   STRING,
    new_status   STRING,
    changes      STRING,
    comments     STRING,
    performed_by STRING,
    performed_at STRING,
    ip_address   STRING,
    user_agent   STRING,
    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 5.3  Trade Note
CREATE TABLE IF NOT EXISTS cis_trade_note (
    note_id      BIGINT NOT NULL,
    trade_id     BIGINT,
    note_type    STRING,
    note_text    STRING,
    internal_ref STRING,
    external_ref STRING,
    attachments  STRING,
    created_by   STRING,
    created_at   STRING,
    updated_by   STRING,
    updated_at   STRING,
    is_active    BOOLEAN,
    PRIMARY KEY (note_id)
)
PARTITION BY HASH (note_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 5.4  Trade Position (AVP versioned snapshots)
--      Includes all columns from DDL 13 + ALTERs 10, 21, 22, 24
CREATE TABLE IF NOT EXISTS cis_trade_position (
    version_id                  BIGINT NOT NULL,
    position_id                 BIGINT NOT NULL,
    position_basis              STRING NOT NULL DEFAULT 'TRADE_DATE',
    position_date               STRING NOT NULL,
    trade_date                  STRING,
    settle_date                 STRING,
    portfolio_short_name        STRING NOT NULL,
    security_label              STRING NOT NULL,
    quantity                    DECIMAL(20,8),
    average_cost_fc             DECIMAL(20,8),
    total_cost_fc               DECIMAL(20,8),
    average_cost_lc             DECIMAL(20,8),
    total_cost_lc               DECIMAL(20,8),
    realized_pnl_fc             DECIMAL(20,8),
    unrealized_pnl_fc           DECIMAL(20,8),
    realized_pnl_lc             DECIMAL(20,8),
    unrealized_pnl_lc           DECIMAL(20,8),
    market_price                DECIMAL(20,8),
    market_value_fc             DECIMAL(20,8),
    market_value_lc             DECIMAL(20,8),
    dividend_fc                 DECIMAL(20,8),
    dividend_lc                 DECIMAL(20,8),
    trade_id                    BIGINT,
    trade_type                  STRING,
    lots_held                   INT,
    custodian                   STRING,
    sub_custodian               STRING,
    security_currency           STRING,
    portfolio_currency          STRING,
    fx_rate                     DECIMAL(20,8),
    status                      STRING,
    is_active                   BOOLEAN,
    is_latest                   BOOLEAN DEFAULT TRUE,
    last_ca_id                  BIGINT,
    last_ca_number              STRING,
    last_ca_type                STRING,
    last_ca_date                STRING,
    last_cash_flow_id           BIGINT,
    last_cash_flow_number       STRING,
    last_cash_flow_amount_fc    DECIMAL(20,8),
    last_cash_flow_amount_lc    DECIMAL(20,8),
    -- Uncalled capital (from ALTER 21)
    uncall_fc                   DECIMAL(20,8),
    uncall_lc                   DECIMAL(20,8),
    -- Pipeline (from ALTER 21)
    pipeline_fc                 DECIMAL(20,8),
    pipeline_lc                 DECIMAL(20,8),
    -- Commitment (from ALTER 24)
    commit_fc                   DECIMAL(20,8),
    commit_lc                   DECIMAL(20,8),
    -- Provision (from ALTER 24)
    provision_fc                DECIMAL(20,8),
    provision_lc                DECIMAL(20,8),
    position_type               STRING,
    created_by                  STRING,
    created_at                  STRING,
    updated_by                  STRING,
    updated_at                  STRING,
    PRIMARY KEY (version_id)
)
PARTITION BY HASH (version_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 5.5  Position Queue (includes ALTER 22 columns)
CREATE TABLE IF NOT EXISTS cis_position_queue (
    queue_id          BIGINT NOT NULL,
    trade_id          BIGINT,
    portfolio_id      STRING,
    security_id       STRING,
    trade_type        STRING,
    quantity          DECIMAL(20,8),
    price             DECIMAL(20,8),
    charges           DECIMAL(20,8),
    settle_date       STRING,
    security_currency STRING,
    portfolio_currency STRING,
    isin              STRING,
    security_name     STRING,
    status            STRING,
    retry_count       INT,
    error_message     STRING,
    queued_at         STRING,
    queued_by         STRING,
    processed_at      STRING,
    updated_at        STRING,
    sla_breach        BOOLEAN,
    processing_date   STRING,
    -- from ALTER 22
    position_basis    STRING,
    position_date     STRING,
    PRIMARY KEY (queue_id)
)
PARTITION BY HASH (queue_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 5.6  Settlement Queue (includes ALTER 22 columns)
CREATE TABLE IF NOT EXISTS cis_settlement_queue (
    queue_id           BIGINT NOT NULL,
    trade_id           BIGINT,
    portfolio_id       STRING,
    security_id        STRING,
    trade_type         STRING,
    quantity           DECIMAL(20,8),
    price              DECIMAL(20,8),
    charges            DECIMAL(20,8),
    settle_date        STRING,
    security_currency  STRING,
    portfolio_currency STRING,
    isin               STRING,
    security_name      STRING,
    status             STRING,
    retry_count        INT,
    error_message      STRING,
    queued_at          STRING,
    queued_by          STRING,
    processed_at       STRING,
    updated_at         STRING,
    processing_date    STRING,
    -- from ALTER 22
    position_basis     STRING,
    position_date      STRING,
    PRIMARY KEY (queue_id)
)
PARTITION BY HASH (queue_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 5.7  Trade Event Queue (includes ALTER 23: processing_started_at)
CREATE TABLE IF NOT EXISTS cis_trade_event_queue (
    event_id              BIGINT NOT NULL,
    trade_id              BIGINT NOT NULL,
    deal_number           STRING,
    event_type            STRING NOT NULL,
    event_data            STRING,
    status                STRING NOT NULL,
    retry_count           INT DEFAULT 0,
    error_message         STRING,
    created_by            STRING,
    created_at            STRING,
    processing_started_at STRING,
    processed_at          STRING,
    PRIMARY KEY (event_id)
)
PARTITION BY HASH (event_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 5.8  Sequence Table
CREATE TABLE IF NOT EXISTS cis_sequence (
    sequence_name  STRING NOT NULL,
    current_value  BIGINT,
    increment_by   INT,
    PRIMARY KEY (sequence_name)
)
PARTITION BY HASH (sequence_name) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- ============================================================================
-- SECTION 6: MARKET DATA
-- ============================================================================

-- 6.1  Equity Price (Kudu — composite PK)
CREATE TABLE IF NOT EXISTS cis_equity_price_kudu (
    currency_code       STRING NOT NULL,
    security_label      STRING NOT NULL,
    price_date          STRING NOT NULL,
    isin                STRING,
    main_closing_price  DECIMAL(18, 6),
    price_timestamp     BIGINT,
    src_system          STRING DEFAULT 'CIS',
    is_active           BOOLEAN DEFAULT true,
    created_by          STRING NOT NULL,
    created_at          BIGINT NOT NULL,
    updated_by          STRING,
    updated_at          BIGINT,
    PRIMARY KEY (currency_code, security_label, price_date)
)
PARTITION BY HASH (currency_code, security_label) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 6.2  Equity Price History
CREATE TABLE IF NOT EXISTS cis_equity_price_history (
    history_id         BIGINT NOT NULL,
    currency_code      STRING NOT NULL,
    security_label     STRING NOT NULL,
    price_date         STRING NOT NULL,
    isin               STRING,
    main_closing_price DECIMAL(18, 6),
    price_timestamp    BIGINT,
    src_system         STRING,
    changed_by         STRING NOT NULL,
    changed_at         BIGINT NOT NULL,
    change_type        STRING,
    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 6.3  FX Rates
CREATE TABLE IF NOT EXISTS gmp_cis_sta_dly_fx_rates (
    fx_rate_id     BIGINT NOT NULL,
    base_currency  STRING,
    quote_currency STRING,
    rate_date      STRING,
    bid_rate       DECIMAL(20, 10),
    ask_rate       DECIMAL(20, 10),
    mid_rate       DECIMAL(20, 10),
    rate_type      STRING,
    source         STRING,
    is_active      BOOLEAN,
    created_at     BIGINT,
    updated_at     BIGINT,
    PRIMARY KEY (fx_rate_id)
)
PARTITION BY HASH (fx_rate_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- ============================================================================
-- SECTION 7: UDF (User-Defined Fields)
-- ============================================================================

-- 7.1  UDF Definition
CREATE TABLE IF NOT EXISTS cis_udf_definition (
    udf_id            BIGINT NOT NULL,
    field_name        STRING,
    label             STRING,
    description       STRING,
    field_type        STRING,
    entity_type       STRING,
    is_required       BOOLEAN,
    is_unique         BOOLEAN,
    max_length        INT,
    min_value_decimal DECIMAL(38,10),
    max_value_decimal DECIMAL(38,10),
    display_order     INT,
    group_name        STRING,
    default_string    STRING,
    default_int       BIGINT,
    default_decimal   DECIMAL(38,10),
    default_bool      BOOLEAN,
    default_datetime  BIGINT,
    is_active         BOOLEAN,
    created_by        STRING,
    created_at        BIGINT,
    updated_by        STRING,
    updated_at        BIGINT,
    PRIMARY KEY (udf_id)
)
PARTITION BY HASH (udf_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 7.2  UDF Option
CREATE TABLE IF NOT EXISTS cis_udf_option (
    option_id     BIGINT NOT NULL,
    udf_id        BIGINT,
    option_value  STRING,
    display_order INT,
    is_active     BOOLEAN,
    created_by    STRING,
    created_at    BIGINT,
    updated_by    STRING,
    updated_at    BIGINT,
    PRIMARY KEY (option_id)
)
PARTITION BY HASH (option_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 7.3  UDF Value
CREATE TABLE IF NOT EXISTS cis_udf_value (
    value_id       BIGINT NOT NULL,
    entity_type    STRING,
    entity_id      BIGINT,
    field_name     STRING,
    udf_id         BIGINT,
    value_string   STRING,
    value_int      BIGINT,
    value_decimal  DECIMAL(38,10),
    value_bool     BOOLEAN,
    value_datetime BIGINT,
    is_active      BOOLEAN,
    created_by     STRING,
    created_at     BIGINT,
    updated_by     STRING,
    updated_at     BIGINT,
    PRIMARY KEY (value_id)
)
PARTITION BY HASH (value_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 7.4  UDF Value Multi (multi-select)
CREATE TABLE IF NOT EXISTS cis_udf_value_multi (
    multi_value_id BIGINT NOT NULL,
    entity_type    STRING,
    entity_id      BIGINT,
    field_name     STRING,
    option_value   STRING,
    udf_id         BIGINT,
    is_active      BOOLEAN,
    created_by     STRING,
    created_at     BIGINT,
    updated_by     STRING,
    updated_at     BIGINT,
    PRIMARY KEY (multi_value_id)
)
PARTITION BY HASH (multi_value_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 7.5  UDF Field
CREATE TABLE IF NOT EXISTS cis_udf_field (
    field_id      BIGINT NOT NULL,
    entity_type   STRING,
    object_type   STRING,
    field_name    STRING,
    label         STRING,
    is_active     BOOLEAN,
    display_order INT,
    created_by    STRING,
    created_at    BIGINT,
    updated_by    STRING,
    updated_at    BIGINT,
    PRIMARY KEY (field_id)
)
PARTITION BY HASH (field_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- ============================================================================
-- SECTION 8: TRADE LOOKUP TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS cis_trade_status_lookup (
    status_code   STRING NOT NULL,
    status_name   STRING,
    description   STRING,
    display_order INT,
    is_active     BOOLEAN,
    PRIMARY KEY (status_code)
)
PARTITION BY HASH (status_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_broker_lookup (
    broker_code   STRING NOT NULL,
    broker_name   STRING,
    broker_type   STRING,
    country       STRING,
    is_active     BOOLEAN,
    display_order INT,
    PRIMARY KEY (broker_code)
)
PARTITION BY HASH (broker_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_gl_fund_type_lookup (
    fund_type_code STRING NOT NULL,
    fund_type_name STRING,
    description    STRING,
    is_active      BOOLEAN,
    display_order  INT,
    PRIMARY KEY (fund_type_code)
)
PARTITION BY HASH (fund_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_gl_cost_centre_lookup (
    cost_centre_code STRING NOT NULL,
    cost_centre_name STRING,
    department       STRING,
    is_active        BOOLEAN,
    display_order    INT,
    PRIMARY KEY (cost_centre_code)
)
PARTITION BY HASH (cost_centre_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_gl_account_code_lookup (
    account_code  STRING NOT NULL,
    account_name  STRING,
    account_type  STRING,
    description   STRING,
    is_active     BOOLEAN,
    display_order INT,
    PRIMARY KEY (account_code)
)
PARTITION BY HASH (account_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_selling_rule_lookup (
    rule_code     STRING NOT NULL,
    rule_name     STRING,
    description   STRING,
    is_active     BOOLEAN,
    display_order INT,
    PRIMARY KEY (rule_code)
)
PARTITION BY HASH (rule_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_custodian_lookup (
    custodian_code  STRING NOT NULL,
    custodian_name  STRING,
    country         STRING,
    custodian_type  STRING,
    is_active       BOOLEAN,
    display_order   INT,
    PRIMARY KEY (custodian_code)
)
PARTITION BY HASH (custodian_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_sub_custodian_lookup (
    sub_custodian_code STRING NOT NULL,
    sub_custodian_name STRING,
    parent_custodian   STRING,
    country            STRING,
    market             STRING,
    is_active          BOOLEAN,
    display_order      INT,
    PRIMARY KEY (sub_custodian_code)
)
PARTITION BY HASH (sub_custodian_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_fund_type_lookup (
    fund_type_code STRING NOT NULL,
    fund_type_name STRING,
    description    STRING,
    is_active      BOOLEAN,
    display_order  INT,
    PRIMARY KEY (fund_type_code)
)
PARTITION BY HASH (fund_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_income_exp_type_lookup (
    type_code     STRING NOT NULL,
    type_name     STRING,
    category      STRING,
    description   STRING,
    is_active     BOOLEAN,
    display_order INT,
    PRIMARY KEY (type_code)
)
PARTITION BY HASH (type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_uobn_lookup (
    uobn_code     STRING NOT NULL,
    uobn_name     STRING,
    region        STRING,
    description   STRING,
    is_active     BOOLEAN,
    display_order INT,
    PRIMARY KEY (uobn_code)
)
PARTITION BY HASH (uobn_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_extension_lookup (
    extension_code STRING NOT NULL,
    extension_name STRING,
    description    STRING,
    is_active      BOOLEAN,
    display_order  INT,
    PRIMARY KEY (extension_code)
)
PARTITION BY HASH (extension_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_delivery_type_lookup (
    delivery_type_code STRING NOT NULL,
    delivery_type_name STRING,
    description        STRING,
    is_active          BOOLEAN,
    display_order      INT,
    PRIMARY KEY (delivery_type_code)
)
PARTITION BY HASH (delivery_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_income_type_lookup (
    income_type_code STRING NOT NULL,
    income_type_name STRING,
    description      STRING,
    is_active        BOOLEAN,
    display_order    INT,
    PRIMARY KEY (income_type_code)
)
PARTITION BY HASH (income_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_split_type_lookup (
    split_type_code STRING NOT NULL,
    split_type_name STRING,
    description     STRING,
    is_active       BOOLEAN,
    display_order   INT,
    PRIMARY KEY (split_type_code)
)
PARTITION BY HASH (split_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_reduction_type_lookup (
    reduction_type_code STRING NOT NULL,
    reduction_type_name STRING,
    description         STRING,
    is_active           BOOLEAN,
    display_order       INT,
    PRIMARY KEY (reduction_type_code)
)
PARTITION BY HASH (reduction_type_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_section_lookup (
    section_code  STRING NOT NULL,
    section_name  STRING,
    description   STRING,
    is_active     BOOLEAN,
    display_order INT,
    PRIMARY KEY (section_code)
)
PARTITION BY HASH (section_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_revision_code_lookup (
    revision_code  STRING NOT NULL,
    revision_name  STRING,
    description    STRING,
    is_active      BOOLEAN,
    display_order  INT,
    PRIMARY KEY (revision_code)
)
PARTITION BY HASH (revision_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_open_close_lookup (
    position_code STRING NOT NULL,
    position_name STRING,
    description   STRING,
    is_active     BOOLEAN,
    display_order INT,
    PRIMARY KEY (position_code)
)
PARTITION BY HASH (position_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

CREATE TABLE IF NOT EXISTS cis_amor_method_lookup (
    method_code   STRING NOT NULL,
    method_name   STRING,
    description   STRING,
    is_active     BOOLEAN,
    display_order INT,
    PRIMARY KEY (method_code)
)
PARTITION BY HASH (method_code) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- ============================================================================
-- SECTION 9: CORPORATE ACTIONS + CASH FLOW
-- ============================================================================

-- 9.1  Corporate Actions
CREATE TABLE IF NOT EXISTS cis_corporate_actions (
    ca_id                      BIGINT NOT NULL,
    ca_number                  STRING,
    ca_type                    STRING,
    security_name              STRING,
    announcement_date          STRING,
    ex_date                    STRING,
    record_date                STRING,
    payment_date               STRING,
    effective_date             STRING,
    subscription_start_date    STRING,
    subscription_end_date      STRING,
    price                      DECIMAL(20, 6),
    currency                   STRING,
    src_system                 STRING,
    status                     STRING,
    submitted_for_approval_at  STRING,
    reviewed_by                STRING,
    reviewed_at                STRING,
    reviewed_comments          STRING,
    is_deleted                 BOOLEAN,
    is_active                  BOOLEAN,
    created_by                 STRING,
    created_at                 BIGINT,
    updated_by                 STRING,
    updated_at                 BIGINT,
    PRIMARY KEY (ca_id)
)
PARTITION BY HASH (ca_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 9.2  Corporate Actions History
CREATE TABLE IF NOT EXISTS cis_corporate_actions_history (
    history_id   BIGINT NOT NULL,
    ca_id        BIGINT,
    ca_number    STRING,
    security_name STRING,
    action       STRING,
    status       STRING,
    changes      STRING,
    comments     STRING,
    performed_by STRING,
    performed_at BIGINT,
    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 9.3  Cash Flow
CREATE TABLE IF NOT EXISTS cis_cash_flow (
    cash_flow_id         BIGINT NOT NULL,
    cash_flow_number     STRING,
    security_label       STRING,
    portfolio_short_name STRING,
    cash_flow_type       STRING,
    send_receive         STRING,
    position_updated     BOOLEAN DEFAULT FALSE,
    foreign_ccy          STRING,
    local_ccy            STRING,
    local_ccy_amt        DECIMAL(20, 8),
    foreign_ccy_amt      DECIMAL(20, 8),
    flow_amount_local    DECIMAL(20, 8),
    dividend_price       DECIMAL(20, 8),
    quantity             DECIMAL(20, 8),
    fx_rate              DECIMAL(20, 8),
    tax_deducted_fc      DECIMAL(20, 8),
    tax_deducted_lc      DECIMAL(20, 8),
    other_charges_fc     DECIMAL(20, 8),
    gl_acc_no            STRING,
    src_system           STRING DEFAULT 'CIS',
    ca_id                BIGINT,
    ca_number            STRING,
    payment_date         STRING,
    trade_date           STRING,
    value_date           STRING,
    dividend_date        STRING,
    ex_date              STRING,
    record_date          STRING,
    is_deleted           BOOLEAN DEFAULT FALSE,
    is_active            BOOLEAN DEFAULT TRUE,
    created_by           STRING,
    created_at           TIMESTAMP,
    updated_by           STRING,
    updated_at           TIMESTAMP,
    status               STRING DEFAULT 'INITIAL',
    validated_by         STRING,
    validated_at         TIMESTAMP,
    validation_comments  STRING,
    settled_by           STRING,
    settled_at           TIMESTAMP,
    settlement_comments  STRING,
    cancelled_by         STRING,
    cancelled_at         TIMESTAMP,
    cancel_reason        STRING,
    PRIMARY KEY (cash_flow_id)
)
PARTITION BY HASH (cash_flow_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 9.4  Cash Flow History
CREATE TABLE IF NOT EXISTS cis_cash_flow_history (
    history_id           BIGINT NOT NULL,
    cash_flow_id         BIGINT NOT NULL,
    cash_flow_number     STRING,
    portfolio_short_name STRING,
    action               STRING,
    status               STRING,
    changes              STRING,
    comments             STRING,
    performed_by         STRING,
    performed_at         BIGINT,
    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 9.5  CA Cash Flow Queue
CREATE TABLE IF NOT EXISTS cis_ca_cash_flow_queue (
    queue_id          BIGINT NOT NULL,
    ca_id             BIGINT NOT NULL,
    ca_number         STRING,
    ca_type           STRING NOT NULL,
    security_name     STRING NOT NULL,
    ex_date           STRING,
    record_date       STRING,
    payment_date      STRING,
    price             DECIMAL(20,8),
    currency          STRING,
    status            STRING DEFAULT 'PENDING',
    retry_count       BIGINT DEFAULT 0,
    error_message     STRING,
    cash_flows_created BIGINT DEFAULT 0,
    total_amount      DECIMAL(20,8),
    processed_at      BIGINT,
    created_at        BIGINT NOT NULL,
    created_by        STRING,
    PRIMARY KEY (queue_id)
)
PARTITION BY HASH (queue_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 9.6  CA Cash Flow Log
CREATE TABLE IF NOT EXISTS cis_ca_cash_flow_log (
    log_id               BIGINT NOT NULL,
    queue_id             BIGINT NOT NULL,
    ca_id                BIGINT NOT NULL,
    cash_flow_id         BIGINT,
    portfolio_short_name STRING NOT NULL,
    security_label       STRING NOT NULL,
    quantity             DECIMAL(20,8),
    amount               DECIMAL(20,8),
    currency             STRING,
    status               STRING DEFAULT 'SUCCESS',
    error_message        STRING,
    created_at           BIGINT NOT NULL,
    PRIMARY KEY (log_id)
)
PARTITION BY HASH (log_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- ============================================================================
-- SECTION 10: UPLOAD / DATASOURCE CONFIG
-- ============================================================================

-- 10.1  File Upload
CREATE TABLE IF NOT EXISTS cis_file_upload (
    upload_id              STRING NOT NULL,
    file_name              STRING,
    original_file_name     STRING,
    file_path              STRING,
    hdfs_path              STRING,
    file_type              STRING,
    mime_type              STRING,
    file_size              BIGINT,
    `encoding`             STRING,
    delimiter              STRING,
    has_header             BOOLEAN,
    row_count              INT,
    column_count           INT,
    schema_json            STRING,
    sample_data_json       STRING,
    validation_errors_json STRING,
    status                 STRING,
    target_table_name      STRING,
    target_database        STRING,
    description            STRING,
    is_deleted             BOOLEAN DEFAULT false,
    created_by             STRING,
    created_at             TIMESTAMP,
    updated_by             STRING,
    updated_at             TIMESTAMP,
    PRIMARY KEY (upload_id)
)
PARTITION BY HASH (upload_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 10.2  Datasource Management Config
CREATE TABLE IF NOT EXISTS cis_datasource_mng (
    source_id       STRING NOT NULL,
    source_name     STRING,
    target_table    STRING,
    separator       STRING,
    header          STRING,
    no_of_skip_line STRING,
    intake_columns  STRING,
    src_system      STRING,
    sub_system      STRING,
    data_cat        STRING,
    data_frq        STRING,
    PRIMARY KEY (source_id)
)
PARTITION BY HASH (source_id) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- ============================================================================
-- SECTION 11: SYSTEM TABLES
-- ============================================================================

-- 11.1  System Date
CREATE TABLE IF NOT EXISTS cis_system_date (
    date_id         BIGINT NOT NULL,
    system_date     STRING,
    report_date     STRING,
    processing_date STRING,
    source_file     STRING,
    file_date_raw   STRING,
    is_active       BOOLEAN DEFAULT true,
    is_business_day BOOLEAN DEFAULT true,
    loaded_by       STRING,
    loaded_at       BIGINT,
    created_at      BIGINT,
    updated_at      BIGINT,
    PRIMARY KEY (date_id)
)
PARTITION BY HASH (date_id) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- 11.2  Help Content
CREATE TABLE IF NOT EXISTS cis_help_content (
    id            STRING NOT NULL,
    module        STRING,
    page          STRING,
    section       STRING,
    title         STRING,
    content       STRING,
    user_type     STRING,
    is_active     BOOLEAN DEFAULT true,
    display_order INT DEFAULT 0,
    created_at    TIMESTAMP,
    updated_at    TIMESTAMP,
    created_by    STRING,
    updated_by    STRING,
    PRIMARY KEY (id)
)
PARTITION BY HASH (id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = '{{KUDU_MASTERS}}');

-- ============================================================================
-- SECTION 12: SEQUENCES + SEED DATA
-- ============================================================================

-- Sequences (idempotent — UPSERT will not overwrite if value has advanced)
UPSERT INTO cis_sequence VALUES ('trade_id',             1000000, 1);
UPSERT INTO cis_sequence VALUES ('trade_history_id',     1000000, 1);
UPSERT INTO cis_sequence VALUES ('trade_note_id',        1000000, 1);
UPSERT INTO cis_sequence VALUES ('position_id',          1000000, 1);
UPSERT INTO cis_sequence VALUES ('position_version_id',  1000000, 1);
UPSERT INTO cis_sequence VALUES ('lot_id',               1000000, 1);
UPSERT INTO cis_sequence VALUES ('audit_id',             1000000, 1);
UPSERT INTO cis_sequence VALUES ('security_id',          1000000, 1);
UPSERT INTO cis_sequence VALUES ('portfolio_history_id', 1000000, 1);
UPSERT INTO cis_sequence VALUES ('trade_event_id',       1000000, 1);
UPSERT INTO cis_sequence VALUES ('position_queue_id',    1000000, 1);
UPSERT INTO cis_sequence VALUES ('settlement_queue_id',  1000000, 1);
UPSERT INTO cis_sequence VALUES ('cash_flow_id',         1000000, 1);
UPSERT INTO cis_sequence VALUES ('cash_flow_history_id', 1000000, 1);
UPSERT INTO cis_sequence VALUES ('ca_id',                1000000, 1);
UPSERT INTO cis_sequence VALUES ('ca_history_id',        1000000, 1);
UPSERT INTO cis_sequence VALUES ('ca_queue_id',          1000000, 1);
UPSERT INTO cis_sequence VALUES ('ca_log_id',            1000000, 1);
UPSERT INTO cis_sequence VALUES ('ingestion_config_id',  1000,    1);
UPSERT INTO cis_sequence VALUES ('ingestion_recon_id',   1000000, 1);

-- Reference data seed (currencies)
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('SGD','SGD','Singapore Dollar','$','2','SGX','T+2','4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('USD','USD','US Dollar','$','2','NYSE','T+2','4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('EUR','EUR','Euro','€','2','EUR','T+2','4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('GBP','GBP','British Pound','£','2','LSE','T+2','4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('JPY','JPY','Japanese Yen','¥','0','TSE','T+2','4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('HKD','HKD','Hong Kong Dollar','HK$','2','HKEX','T+2','4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('AUD','AUD','Australian Dollar','A$','2','ASX','T+2','4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('CNY','CNY','Chinese Yuan','¥','2','SSE','T+1','4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('MYR','MYR','Malaysian Ringgit','RM','2','KLSE','T+2','4');
UPSERT INTO gmp_cis_sta_dly_currency VALUES ('THB','THB','Thai Baht','฿','2','SET','T+2','4');

-- Reference data seed (countries)
UPSERT INTO gmp_cis_sta_dly_country VALUES ('SG','Singapore');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('US','United States');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('UK','United Kingdom');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('JP','Japan');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('HK','Hong Kong');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('AU','Australia');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('CN','China');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('MY','Malaysia');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('TH','Thailand');
UPSERT INTO gmp_cis_sta_dly_country VALUES ('ID','Indonesia');

-- Lookup seed data
UPSERT INTO cis_trade_status_lookup VALUES ('PENDING','Pending','Trade is pending execution',1,true);
UPSERT INTO cis_trade_status_lookup VALUES ('CONFIRMED','Confirmed','Trade is confirmed',2,true);
UPSERT INTO cis_trade_status_lookup VALUES ('SETTLED','Settled','Trade is settled',4,true);
UPSERT INTO cis_trade_status_lookup VALUES ('FAILED','Failed','Trade failed',5,true);
UPSERT INTO cis_trade_status_lookup VALUES ('CANCELLED','Cancelled','Trade cancelled',6,true);

UPSERT INTO cis_selling_rule_lookup VALUES ('FIFO','First In First Out','Sell oldest lots first',true,1);
UPSERT INTO cis_selling_rule_lookup VALUES ('LIFO','Last In First Out','Sell newest lots first',true,2);
UPSERT INTO cis_selling_rule_lookup VALUES ('WAVG','Weighted Average','Use weighted average cost',true,3);

UPSERT INTO cis_open_close_lookup VALUES ('OPEN','Open','Opening new position',true,1);
UPSERT INTO cis_open_close_lookup VALUES ('CLOSE','Close','Closing existing position',true,2);

UPSERT INTO cis_amor_method_lookup VALUES ('STD','Standard','Standard method',true,1);
UPSERT INTO cis_amor_method_lookup VALUES ('EFF_INT','Effective Interest','Effective interest method',true,2);
UPSERT INTO cis_amor_method_lookup VALUES ('STRAIGHT','Straight Line','Straight line method',true,3);
UPSERT INTO cis_amor_method_lookup VALUES ('NONE','None','No amortisation',true,4);

-- RBAC v2 seed — admin user + CIS-SYSOPS group with full access
UPSERT INTO cis_user_info VALUES ('1','admin','admin@cistrade.com','System Admin','UOBS',NULL,true,false,NOW(),'SYSTEM',NOW(),'SYSTEM');
UPSERT INTO cis_user_group_info VALUES ('1','CIS-SYSOPS','CIS System Operations - Full Access','UOBS',true,false,NOW(),'SYSTEM',NOW(),'SYSTEM');
UPSERT INTO cis_user_group_mapping_info VALUES ('1','1','UOBS','CIS-SYSOPS',true,false,NOW(),'SYSTEM',NOW(),'SYSTEM');

-- Equity price datasource config
UPSERT INTO cis_datasource_mng (source_id,source_name,target_table,separator,header,no_of_skip_line,intake_columns,src_system,sub_system,data_cat,data_frq)
VALUES ('CIS_EQUITY_PRICE','cisEquPriceUpload.csv','cis_equity_price',',','true','0','price_date,security_label,closing_price,shares_outstanding,market_value','CIS','user','sta','adhoc');

-- Initial system date (update at runtime)
UPSERT INTO cis_system_date (date_id,system_date,report_date,processing_date,source_file,file_date_raw,is_active,is_business_day,loaded_by,loaded_at,created_at,updated_at)
VALUES (1,'20260421','20260420','20260420','MRC_PC_DATE.txt','20260420',true,true,'SYSTEM',UNIX_TIMESTAMP()*1000,UNIX_TIMESTAMP()*1000,UNIX_TIMESTAMP()*1000);

-- ============================================================================
-- SECTION 13: VERIFICATION
-- ============================================================================

SHOW TABLES;
