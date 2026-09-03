-- ============================================================================
-- DDL: Standardise timestamp columns across gmp_cis
-- ============================================================================
-- Ticket : DATE_STD_001
-- Author : CIS Team
-- Date   : 2026-05-05
--
-- Standard adopted:
--   Audit timestamps  (created_at, updated_at, etc.)  → STRING 'YYYY-MM-DD HH:MM:SS'
--   Business dates    (trade_date, price_date, etc.)  → STRING 'YYYY-MM-DD'  (no change)
--   Partition dates   (processing_date, system_date)  → STRING 'YYYYMMDD'    (no change)
--   Millisecond PKs   (trade_id, event_id)            → BIGINT               (no change)
--
-- NOTE: Kudu does NOT support CREATE TABLE ... LIKE or ALTER COLUMN type.
--       Each table is migrated by:
--         1. CREATE new table with STRING timestamp columns (full DDL below)
--         2. INSERT INTO new SELECT ..., with conversion expression
--         3. Validate row counts match
--         4. Rename old → _bak, new → live  (commands commented — run manually)
--         5. Drop backup after smoke test    (commands commented — run manually)
--
-- Conversion expressions:
--   BIGINT ms  → STRING : from_unixtime(CAST(col AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
--   TIMESTAMP  → STRING : from_timestamp(col, 'yyyy-MM-dd HH:mm:ss')
-- ============================================================================


-- ============================================================================
-- GROUP 1: BIGINT → STRING
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1A. cis_equity_price_kudu
--     Columns migrated: price_timestamp, created_at, updated_at
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_equity_price_kudu_new (
    currency_code      STRING NOT NULL,
    security_label     STRING NOT NULL,
    price_date         STRING NOT NULL,
    isin               STRING,
    main_closing_price DECIMAL(18, 6),
    price_timestamp    STRING,
    src_system         STRING,
    is_active          BOOLEAN,
    created_by         STRING NOT NULL,
    created_at         STRING NOT NULL,
    updated_by         STRING,
    updated_at         STRING,
    PRIMARY KEY (currency_code, security_label, price_date)
)
PARTITION BY HASH (currency_code, security_label) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = '${KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '3'
);

INSERT INTO gmp_cis.cis_equity_price_kudu_new
SELECT
    currency_code,
    security_label,
    price_date,
    isin,
    main_closing_price,
    src_system,
    is_active,
    created_by,
    updated_by,
    from_unixtime(CAST(price_timestamp AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS price_timestamp,
    from_unixtime(CAST(created_at      AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_unixtime(CAST(updated_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_equity_price_kudu;

-- Validate:
-- SELECT COUNT(*) FROM gmp_cis.cis_equity_price_kudu;
-- SELECT COUNT(*) FROM gmp_cis.cis_equity_price_kudu_new;
-- SELECT currency_code, security_label, price_date, price_timestamp, created_at FROM gmp_cis.cis_equity_price_kudu_new LIMIT 5;

-- Rename (uncomment and run after validation):
-- ALTER TABLE gmp_cis.cis_equity_price_kudu     RENAME TO gmp_cis.cis_equity_price_kudu_bak;
-- ALTER TABLE gmp_cis.cis_equity_price_kudu_new RENAME TO gmp_cis.cis_equity_price_kudu;
-- DROP TABLE gmp_cis.cis_equity_price_kudu_bak;   -- run after smoke test


-- ----------------------------------------------------------------------------
-- 1B. cis_equity_price_history
--     Columns migrated: price_timestamp, changed_at
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_equity_price_history_new (
    history_id         BIGINT NOT NULL,
    currency_code      STRING NOT NULL,
    security_label     STRING NOT NULL,
    price_date         STRING NOT NULL,
    isin               STRING,
    main_closing_price DECIMAL(18, 6),
    price_timestamp    STRING,
    src_system         STRING,
    changed_by         STRING NOT NULL,
    changed_at         STRING NOT NULL,
    change_type        STRING,
    PRIMARY KEY (history_id)
)
PARTITION BY HASH (history_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = '${KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '3'
);

INSERT INTO gmp_cis.cis_equity_price_history_new
SELECT
    history_id,
    currency_code,
    security_label,
    price_date,
    isin,
    main_closing_price,
    src_system,
    changed_by,
    change_type,
    from_unixtime(CAST(changed_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS changed_at,
    CASE WHEN price_timestamp IS NOT NULL
         THEN from_unixtime(CAST(price_timestamp AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS price_timestamp
FROM gmp_cis.cis_equity_price_history;

-- SELECT COUNT(*) FROM gmp_cis.cis_equity_price_history;
-- SELECT COUNT(*) FROM gmp_cis.cis_equity_price_history_new;
-- SELECT history_id, changed_at, price_timestamp FROM gmp_cis.cis_equity_price_history_new LIMIT 5;

-- ALTER TABLE gmp_cis.cis_equity_price_history     RENAME TO gmp_cis.cis_equity_price_history_bak;
-- ALTER TABLE gmp_cis.cis_equity_price_history_new RENAME TO gmp_cis.cis_equity_price_history;
-- DROP TABLE gmp_cis.cis_equity_price_history_bak;


-- ----------------------------------------------------------------------------
-- 1C. cis_security_kudu
--     Columns migrated: created_at, updated_at, submitted_for_approval_at, reviewed_at
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_security_kudu_new (
    security_id                      BIGINT NOT NULL,
    security_name                    STRING NOT NULL,
    isin                             STRING,
    security_description             STRING,
    issuer                           STRING,
    ticker                           STRING,
    industry                         STRING,
    security_type                    STRING,
    investment_type                  STRING,
    issuer_type                      STRING,
    quoted_unquoted                  STRING,
    country_of_incorporation         STRING,
    country_of_exchange              STRING,
    country_of_issue                 STRING,
    country_of_primary_exchange      STRING,
    exchange_code                    STRING,
    currency_code                    STRING,
    price                            DECIMAL(20, 4),
    price_date                       STRING,
    price_source                     STRING,
    shares_outstanding               BIGINT,
    beta                             DECIMAL(10, 4),
    par_value                        DECIMAL(20, 6),
    shareholding_entity_1            DECIMAL(10, 4),
    shareholding_entity_2            DECIMAL(10, 4),
    shareholding_entity_3            DECIMAL(10, 4),
    shareholding_aggregated          DECIMAL(10, 4),
    substantial_10_pct               STRING,
    bwciif                           BIGINT,
    bwciif_others                    BIGINT,
    cels                             STRING,
    approved_s32                     STRING,
    basel_iv_fund                    STRING,
    mas_643_entity_type              STRING,
    mas_6d_code                      STRING,
    fin_nonfin_ind                   STRING,
    business_unit_head               STRING,
    person_in_charge                 STRING,
    core_noncore                     STRING,
    fund_index_fund                  STRING,
    management_limit_classification  STRING,
    relative_index                   STRING,
    status                           STRING,
    submitted_for_approval_at        STRING,
    submitted_by                     STRING,
    reviewed_at                      STRING,
    reviewed_by                      STRING,
    review_comments                  STRING,
    is_active                        BOOLEAN,
    created_by                       STRING NOT NULL,
    created_at                       STRING NOT NULL,
    updated_by                       STRING NOT NULL,
    updated_at                       STRING NOT NULL,
    PRIMARY KEY (security_id)
)
PARTITION BY HASH (security_id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = '${KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '3'
);

INSERT INTO gmp_cis.cis_security_kudu_new
SELECT
    security_id, security_name, isin, security_description, issuer, ticker,
    industry, security_type, investment_type, issuer_type, quoted_unquoted,
    country_of_incorporation, country_of_exchange, country_of_issue,
    country_of_primary_exchange, exchange_code, currency_code,
    price, price_date, price_source, shares_outstanding, beta, par_value,
    shareholding_entity_1, shareholding_entity_2, shareholding_entity_3,
    shareholding_aggregated, substantial_10_pct,
    bwciif, bwciif_others, cels, approved_s32, basel_iv_fund,
    mas_643_entity_type, mas_6d_code, fin_nonfin_ind,
    business_unit_head, person_in_charge, core_noncore,
    fund_index_fund, management_limit_classification, relative_index,
    status, submitted_by, reviewed_by, review_comments, is_active,
    created_by, updated_by,
    from_unixtime(CAST(created_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    from_unixtime(CAST(updated_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS updated_at,
    CASE WHEN submitted_for_approval_at IS NOT NULL
         THEN from_unixtime(CAST(submitted_for_approval_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS submitted_for_approval_at,
    CASE WHEN reviewed_at IS NOT NULL
         THEN from_unixtime(CAST(reviewed_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS reviewed_at
FROM gmp_cis.cis_security_kudu;

-- SELECT COUNT(*) FROM gmp_cis.cis_security_kudu;
-- SELECT COUNT(*) FROM gmp_cis.cis_security_kudu_new;
-- SELECT security_id, created_at, updated_at, submitted_for_approval_at FROM gmp_cis.cis_security_kudu_new LIMIT 5;

-- ALTER TABLE gmp_cis.cis_security_kudu     RENAME TO gmp_cis.cis_security_kudu_bak;
-- ALTER TABLE gmp_cis.cis_security_kudu_new RENAME TO gmp_cis.cis_security_kudu;
-- DROP TABLE gmp_cis.cis_security_kudu_bak;


-- ----------------------------------------------------------------------------
-- 1D. cis_corporate_action (actual table name: cis_corporate_actions)
--     Columns migrated: created_at, updated_at
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_corporate_actions_new (
    ca_id                    BIGINT NOT NULL,
    ca_number                STRING,
    ca_type                  STRING,
    security_name            STRING,
    announcement_date        STRING,
    ex_date                  STRING,
    record_date              STRING,
    payment_date             STRING,
    effective_date           STRING,
    subscription_start_date  STRING,
    subscription_end_date    STRING,
    price                    DECIMAL(20, 6),
    currency                 STRING,
    src_system               STRING,
    status                   STRING,
    submitted_for_approval_at STRING,
    reviewed_by              STRING,
    reviewed_at              STRING,
    reviewed_comments        STRING,
    is_deleted               BOOLEAN,
    is_active                BOOLEAN,
    created_by               STRING,
    created_at               STRING,
    updated_by               STRING,
    updated_at               STRING,
    PRIMARY KEY (ca_id)
)
PARTITION BY HASH (ca_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = '${KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '1'
);

INSERT INTO gmp_cis.cis_corporate_actions_new
SELECT
    ca_id, ca_number, ca_type, security_name,
    announcement_date, ex_date, record_date, payment_date,
    effective_date, subscription_start_date, subscription_end_date,
    price, currency, src_system, status,
    submitted_for_approval_at, reviewed_by, reviewed_at, reviewed_comments,
    is_deleted, is_active, created_by, updated_by,
    from_unixtime(CAST(created_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_unixtime(CAST(updated_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_corporate_actions;

-- SELECT COUNT(*) FROM gmp_cis.cis_corporate_actions;
-- SELECT COUNT(*) FROM gmp_cis.cis_corporate_actions_new;
-- SELECT ca_id, created_at, updated_at FROM gmp_cis.cis_corporate_actions_new LIMIT 5;

-- ALTER TABLE gmp_cis.cis_corporate_actions     RENAME TO gmp_cis.cis_corporate_actions_bak;
-- ALTER TABLE gmp_cis.cis_corporate_actions_new RENAME TO gmp_cis.cis_corporate_actions;
-- DROP TABLE gmp_cis.cis_corporate_actions_bak;


-- ----------------------------------------------------------------------------
-- 1E. cis_system_date
--     Columns migrated: loaded_at, created_at, updated_at
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_system_date_new (
    date_id         BIGINT NOT NULL,
    system_date     STRING,
    report_date     STRING,
    processing_date STRING,
    source_file     STRING,
    file_date_raw   STRING,
    is_active       BOOLEAN,
    is_business_day BOOLEAN,
    loaded_by       STRING,
    loaded_at       STRING,
    created_at      STRING,
    updated_at      STRING,
    PRIMARY KEY (date_id)
)
PARTITION BY HASH (date_id) PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = '${KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '1'
);

INSERT INTO gmp_cis.cis_system_date_new
SELECT
    date_id, system_date, report_date, processing_date,
    source_file, file_date_raw, is_active, is_business_day, loaded_by,
    from_unixtime(CAST(loaded_at  AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS loaded_at,
    from_unixtime(CAST(created_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_unixtime(CAST(updated_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_system_date;

-- SELECT COUNT(*) FROM gmp_cis.cis_system_date;
-- SELECT COUNT(*) FROM gmp_cis.cis_system_date_new;
-- SELECT date_id, loaded_at, created_at FROM gmp_cis.cis_system_date_new LIMIT 5;

-- ALTER TABLE gmp_cis.cis_system_date     RENAME TO gmp_cis.cis_system_date_bak;
-- ALTER TABLE gmp_cis.cis_system_date_new RENAME TO gmp_cis.cis_system_date;
-- DROP TABLE gmp_cis.cis_system_date_bak;


-- ============================================================================
-- GROUP 2: TIMESTAMP → STRING
-- NOTE: Run on CML cluster (not local Docker) to ensure timezone correctness.
--       Spot-check 5–10 rows before and after each rename.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 2A. cis_party
--     Columns migrated: created_at, updated_at
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_party_new (
    party_short_name          STRING NOT NULL,
    m_label                   STRING,
    party_full_name           STRING,
    record_type               STRING,
    address_line_0            STRING,
    address_line_1            STRING,
    address_line_2            STRING,
    address_line_3            STRING,
    city                      STRING,
    country                   STRING,
    postal_code               STRING,
    fax_number                STRING,
    telex_number              STRING,
    primary_contact           STRING,
    primary_number            STRING,
    other_contact             STRING,
    other_number              STRING,
    industry                  STRING,
    industry_group            STRING,
    is_broker                 BOOLEAN,
    is_custodian              BOOLEAN,
    is_issuer                 BOOLEAN,
    is_bank                   BOOLEAN,
    is_subsidiary             BOOLEAN,
    is_corporate              BOOLEAN,
    subsidiary_level          STRING,
    party_grandparent         STRING,
    party_parent              STRING,
    resident_y_n              STRING,
    mas_industry_code         STRING,
    country_of_incorporation  STRING,
    cels_code                 STRING,
    src_system                STRING,
    sub_system                STRING,
    data_cat                  STRING,
    data_frq                  STRING,
    src_id                    STRING,
    processing_date           STRING,
    status                    STRING,
    validated_by              STRING,
    validation_comments       STRING,
    is_active                 BOOLEAN,
    is_deleted                BOOLEAN,
    created_by                STRING,
    created_at                STRING,
    updated_by                STRING,
    updated_at                STRING,
    PRIMARY KEY (party_short_name)
)
PARTITION BY HASH (party_short_name) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = '${KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '1'
);

INSERT INTO gmp_cis.cis_party_new
SELECT
    party_short_name, m_label, party_full_name, record_type,
    address_line_0, address_line_1, address_line_2, address_line_3,
    city, country, postal_code, fax_number, telex_number,
    primary_contact, primary_number, other_contact, other_number,
    industry, industry_group, is_broker, is_custodian, is_issuer,
    is_bank, is_subsidiary, is_corporate, subsidiary_level,
    party_grandparent, party_parent, resident_y_n, mas_industry_code,
    country_of_incorporation, cels_code, src_system, sub_system,
    data_cat, data_frq, src_id, processing_date,
    status, validated_by, validation_comments, is_active, is_deleted,
    created_by, updated_by,
    from_timestamp(created_at, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_timestamp(updated_at, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_party;

-- SELECT COUNT(*) FROM gmp_cis.cis_party;
-- SELECT COUNT(*) FROM gmp_cis.cis_party_new;
-- SELECT party_short_name, created_at, updated_at FROM gmp_cis.cis_party_new LIMIT 5;

-- ALTER TABLE gmp_cis.cis_party     RENAME TO gmp_cis.cis_party_bak;
-- ALTER TABLE gmp_cis.cis_party_new RENAME TO gmp_cis.cis_party;
-- DROP TABLE gmp_cis.cis_party_bak;


-- ----------------------------------------------------------------------------
-- 2B. cis_user
--     Columns migrated: created_at, updated_at  (stored as created_on/updated_on in live table)
--     NOTE: check DESCRIBE gmp_cis.cis_user on your cluster to confirm column names
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_user_new (
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
TBLPROPERTIES (
    'kudu.master_addresses' = '${KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '1'
);

-- NOTE: cis_user in this schema uses created_on/updated_on (BIGINT) not created_at/updated_at.
-- If your cluster has different column names, adjust the INSERT below accordingly.
-- Run DESCRIBE gmp_cis.cis_user; first to verify.
INSERT INTO gmp_cis.cis_user_new
SELECT
    user_id, username, login, name, email, domain, entity,
    cis_user_group_id, is_active, is_deleted, enabled,
    last_login, created_on, created_by, updated_on, updated_by
FROM gmp_cis.cis_user;

-- SELECT COUNT(*) FROM gmp_cis.cis_user;
-- SELECT COUNT(*) FROM gmp_cis.cis_user_new;

-- ALTER TABLE gmp_cis.cis_user     RENAME TO gmp_cis.cis_user_bak;
-- ALTER TABLE gmp_cis.cis_user_new RENAME TO gmp_cis.cis_user;
-- DROP TABLE gmp_cis.cis_user_bak;


-- ----------------------------------------------------------------------------
-- 2C. cis_user_group
--     Columns migrated: created_at, updated_at  (BIGINT → STRING)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_user_group_new (
    group_id    BIGINT NOT NULL,
    user_id     BIGINT,
    group_name  STRING,
    description STRING,
    is_active   BOOLEAN,
    is_deleted  BOOLEAN,
    created_at  STRING,
    updated_at  STRING,
    PRIMARY KEY (group_id)
)
PARTITION BY HASH (group_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = '${KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '1'
);

INSERT INTO gmp_cis.cis_user_group_new
SELECT
    group_id, user_id, group_name, description, is_active, is_deleted,
    from_unixtime(CAST(created_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_unixtime(CAST(updated_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_user_group;

-- SELECT COUNT(*) FROM gmp_cis.cis_user_group;
-- SELECT COUNT(*) FROM gmp_cis.cis_user_group_new;
-- SELECT group_id, group_name, created_at FROM gmp_cis.cis_user_group_new LIMIT 5;

-- ALTER TABLE gmp_cis.cis_user_group     RENAME TO gmp_cis.cis_user_group_bak;
-- ALTER TABLE gmp_cis.cis_user_group_new RENAME TO gmp_cis.cis_user_group;
-- DROP TABLE gmp_cis.cis_user_group_bak;


-- ----------------------------------------------------------------------------
-- 2D. cis_group_permissions
--     Columns migrated: created_at, updated_at  (BIGINT → STRING)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_group_permissions_new (
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
    created_at      STRING,
    updated_at      STRING,
    PRIMARY KEY (permission_id)
)
PARTITION BY HASH (permission_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = '${KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '1'
);

INSERT INTO gmp_cis.cis_group_permissions_new
SELECT
    permission_id, group_id, permission_name,
    can_view, can_create, can_edit, can_delete, can_approve,
    object_id, read_write, is_active, is_deleted,
    from_unixtime(CAST(created_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_unixtime(CAST(updated_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_group_permissions;

-- SELECT COUNT(*) FROM gmp_cis.cis_group_permissions;
-- SELECT COUNT(*) FROM gmp_cis.cis_group_permissions_new;
-- SELECT permission_id, permission_name, created_at FROM gmp_cis.cis_group_permissions_new LIMIT 5;

-- ALTER TABLE gmp_cis.cis_group_permissions     RENAME TO gmp_cis.cis_group_permissions_bak;
-- ALTER TABLE gmp_cis.cis_group_permissions_new RENAME TO gmp_cis.cis_group_permissions;
-- DROP TABLE gmp_cis.cis_group_permissions_bak;


-- ----------------------------------------------------------------------------
-- 2E. cis_cash_flow
--     Columns migrated: created_at, updated_at, validated_at, settled_at, cancelled_at
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_cash_flow_new (
    cash_flow_id          BIGINT NOT NULL,
    cash_flow_number      STRING,
    security_label        STRING,
    portfolio_short_name  STRING,
    cash_flow_type        STRING,
    send_receive          STRING,
    cf_processed          BOOLEAN,
    foreign_ccy           STRING,
    local_ccy             STRING,
    local_ccy_amt         DECIMAL(20, 8),
    foreign_ccy_amt       DECIMAL(20, 8),
    flow_amount_local     DECIMAL(20, 8),
    dividend_price        DECIMAL(20, 8),
    quantity              DECIMAL(20, 8),
    fx_rate               DECIMAL(20, 8),
    tax_deducted_fc       DECIMAL(20, 8),
    tax_deducted_lc       DECIMAL(20, 8),
    other_charges_fc      DECIMAL(20, 8),
    gl_acc_no             STRING,
    src_system            STRING,
    ca_id                 BIGINT,
    ca_number             STRING,
    payment_date          STRING,
    trade_date            STRING,
    value_date            STRING,
    dividend_date         STRING,
    ex_date               STRING,
    record_date           STRING,
    status                STRING,
    created_by            STRING,
    created_at            STRING,
    updated_by            STRING,
    updated_at            STRING,
    validated_by          STRING,
    validated_at          STRING,
    validation_comments   STRING,
    settled_by            STRING,
    settled_at            STRING,
    settlement_comments   STRING,
    cancelled_by          STRING,
    cancelled_at          STRING,
    cancel_reason         STRING,
    PRIMARY KEY (cash_flow_id)
)
PARTITION BY HASH (cash_flow_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = '${KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '1'
);

INSERT INTO gmp_cis.cis_cash_flow_new
SELECT
    cash_flow_id, cash_flow_number, security_label, portfolio_short_name,
    cash_flow_type, send_receive, cf_processed,
    foreign_ccy, local_ccy, local_ccy_amt, foreign_ccy_amt,
    flow_amount_local, dividend_price, quantity, fx_rate,
    tax_deducted_fc, tax_deducted_lc, other_charges_fc,
    gl_acc_no, src_system, ca_id, ca_number,
    payment_date, trade_date, value_date, dividend_date, ex_date, record_date,
    status, created_by, updated_by,
    validated_by, validation_comments,
    settled_by, settlement_comments,
    cancelled_by, cancel_reason,
    from_timestamp(created_at,   'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at   IS NOT NULL THEN from_timestamp(updated_at,   'yyyy-MM-dd HH:mm:ss') ELSE NULL END AS updated_at,
    CASE WHEN validated_at IS NOT NULL THEN from_timestamp(validated_at, 'yyyy-MM-dd HH:mm:ss') ELSE NULL END AS validated_at,
    CASE WHEN settled_at   IS NOT NULL THEN from_timestamp(settled_at,   'yyyy-MM-dd HH:mm:ss') ELSE NULL END AS settled_at,
    CASE WHEN cancelled_at IS NOT NULL THEN from_timestamp(cancelled_at, 'yyyy-MM-dd HH:mm:ss') ELSE NULL END AS cancelled_at
FROM gmp_cis.cis_cash_flow;

-- SELECT COUNT(*) FROM gmp_cis.cis_cash_flow;
-- SELECT COUNT(*) FROM gmp_cis.cis_cash_flow_new;
-- SELECT cash_flow_id, created_at, validated_at, settled_at FROM gmp_cis.cis_cash_flow_new LIMIT 5;

-- ALTER TABLE gmp_cis.cis_cash_flow     RENAME TO gmp_cis.cis_cash_flow_bak;
-- ALTER TABLE gmp_cis.cis_cash_flow_new RENAME TO gmp_cis.cis_cash_flow;
-- DROP TABLE gmp_cis.cis_cash_flow_bak;


-- ----------------------------------------------------------------------------
-- 2F. cis_file_upload
--     Columns migrated: created_at, updated_at
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_file_upload_new (
    upload_id                STRING NOT NULL,
    file_name                STRING,
    original_file_name       STRING,
    file_path                STRING,
    hdfs_path                STRING,
    file_type                STRING,
    mime_type                STRING,
    file_size                BIGINT,
    `encoding`               STRING,
    delimiter                STRING,
    has_header               BOOLEAN,
    row_count                INT,
    column_count             INT,
    schema_json              STRING,
    sample_data_json         STRING,
    validation_errors_json   STRING,
    status                   STRING,
    target_table_name        STRING,
    target_database          STRING,
    description              STRING,
    is_deleted               BOOLEAN,
    created_by               STRING,
    created_at               STRING,
    updated_by               STRING,
    updated_at               STRING,
    PRIMARY KEY (upload_id)
)
PARTITION BY HASH (upload_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = '${KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '1'
);

INSERT INTO gmp_cis.cis_file_upload_new
SELECT
    upload_id, file_name, original_file_name, file_path, hdfs_path,
    file_type, mime_type, file_size, `encoding`, delimiter,
    has_header, row_count, column_count,
    schema_json, sample_data_json, validation_errors_json,
    status, target_table_name, target_database, description,
    is_deleted, created_by, updated_by,
    from_timestamp(created_at, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_timestamp(updated_at, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_file_upload;

-- SELECT COUNT(*) FROM gmp_cis.cis_file_upload;
-- SELECT COUNT(*) FROM gmp_cis.cis_file_upload_new;
-- SELECT upload_id, created_at, updated_at FROM gmp_cis.cis_file_upload_new LIMIT 5;

-- ALTER TABLE gmp_cis.cis_file_upload     RENAME TO gmp_cis.cis_file_upload_bak;
-- ALTER TABLE gmp_cis.cis_file_upload_new RENAME TO gmp_cis.cis_file_upload;
-- DROP TABLE gmp_cis.cis_file_upload_bak;
