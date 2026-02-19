-- ============================================================================
-- CIS Trade Hive - Hive Managed Tables DDL (ORC + ACID)
-- ============================================================================
-- Database: gmp_cis
-- File Format: ORC with SNAPPY compression
-- Transaction Support: Full ACID (INSERT, UPDATE, DELETE)
-- ============================================================================

-- Create database if not exists
CREATE DATABASE IF NOT EXISTS gmp_cis;
USE gmp_cis;

-- ============================================================================
-- CORE TABLES - Users, Groups, Permissions
-- ============================================================================

-- User table
CREATE TABLE IF NOT EXISTS cis_user (
    user_id             STRING,
    username            STRING,
    email               STRING,
    full_name           STRING,
    department          STRING,
    is_active           BOOLEAN,
    created_at          TIMESTAMP,
    created_by          STRING,
    updated_at          TIMESTAMP,
    updated_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (user_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- User Group table
CREATE TABLE IF NOT EXISTS cis_user_group (
    group_id            STRING,
    group_name          STRING,
    description         STRING,
    is_active           BOOLEAN,
    created_at          TIMESTAMP,
    created_by          STRING,
    updated_at          TIMESTAMP,
    updated_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (group_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- Group Permissions table
CREATE TABLE IF NOT EXISTS cis_group_permissions (
    permission_id       STRING,
    group_id            STRING,
    resource            STRING,
    action              STRING,
    is_allowed          BOOLEAN,
    created_at          TIMESTAMP,
    created_by          STRING,
    updated_at          TIMESTAMP,
    updated_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (permission_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- User Group Membership
CREATE TABLE IF NOT EXISTS cis_user_group_membership (
    membership_id       STRING,
    user_id             STRING,
    group_id            STRING,
    created_at          TIMESTAMP,
    created_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (membership_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- AUDIT LOG TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS cis_audit_log (
    audit_id            STRING,
    entity_type         STRING,
    entity_id           STRING,
    action              STRING,
    old_value           STRING,
    new_value           STRING,
    user_id             STRING,
    username            STRING,
    ip_address          STRING,
    user_agent          STRING,
    created_at          TIMESTAMP
)
CLUSTERED BY (audit_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- PORTFOLIO TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS cis_portfolio (
    portfolio_id            STRING,
    portfolio_short_name    STRING,
    portfolio_name          STRING,
    portfolio_type          STRING,
    currency                STRING,
    base_currency           STRING,
    manager_name            STRING,
    custodian               STRING,
    inception_date          DATE,
    description             STRING,
    status                  STRING,
    is_active               BOOLEAN,
    created_at              TIMESTAMP,
    created_by              STRING,
    updated_at              TIMESTAMP,
    updated_by              STRING,
    deleted_at              TIMESTAMP
)
CLUSTERED BY (portfolio_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

CREATE TABLE IF NOT EXISTS cis_portfolio_history (
    history_id          STRING,
    portfolio_id        STRING,
    action              STRING,
    old_value           STRING,
    new_value           STRING,
    changed_by          STRING,
    changed_at          TIMESTAMP,
    created_at          TIMESTAMP
)
CLUSTERED BY (history_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- TRADE TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS cis_trade (
    trade_id                STRING,
    portfolio_id            STRING,
    portfolio_short_name    STRING,
    security_id             STRING,
    security_name           STRING,
    trade_type              STRING,
    trade_action            STRING,
    quantity                DECIMAL(18,4),
    price                   DECIMAL(18,6),
    trade_amount            DECIMAL(18,2),
    currency                STRING,
    trade_date              DATE,
    settlement_date         DATE,
    value_date              DATE,
    counterparty_id         STRING,
    counterparty_name       STRING,
    broker_id               STRING,
    broker_name             STRING,
    commission              DECIMAL(18,4),
    fees                    DECIMAL(18,4),
    net_amount              DECIMAL(18,2),
    status                  STRING,
    notes                   STRING,
    is_active               BOOLEAN,
    created_at              TIMESTAMP,
    created_by              STRING,
    updated_at              TIMESTAMP,
    updated_by              STRING,
    deleted_at              TIMESTAMP
)
CLUSTERED BY (trade_id) INTO 8 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

CREATE TABLE IF NOT EXISTS cis_trade_history (
    history_id          STRING,
    trade_id            STRING,
    action              STRING,
    old_value           STRING,
    new_value           STRING,
    changed_by          STRING,
    changed_at          TIMESTAMP,
    created_at          TIMESTAMP
)
CLUSTERED BY (history_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

CREATE TABLE IF NOT EXISTS cis_trade_note (
    note_id             STRING,
    trade_id            STRING,
    note_type           STRING,
    note_text           STRING,
    created_at          TIMESTAMP,
    created_by          STRING,
    updated_at          TIMESTAMP,
    updated_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (note_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

CREATE TABLE IF NOT EXISTS cis_trade_position (
    position_id             STRING,
    trade_id                STRING,
    portfolio_id            STRING,
    security_id             STRING,
    position_date           DATE,
    quantity                DECIMAL(18,4),
    cost_local              DECIMAL(18,2),
    cost_base               DECIMAL(18,2),
    market_value_local      DECIMAL(18,2),
    market_value_base       DECIMAL(18,2),
    unrealized_pnl          DECIMAL(18,2),
    currency                STRING,
    version                 INT,
    created_at              TIMESTAMP,
    created_by              STRING,
    deleted_at              TIMESTAMP
)
CLUSTERED BY (position_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- SECURITY TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS cis_security (
    security_id             STRING,
    security_code           STRING,
    security_name           STRING,
    security_type           STRING,
    asset_class             STRING,
    currency                STRING,
    exchange_code           STRING,
    country                 STRING,
    sector                  STRING,
    industry                STRING,
    isin                    STRING,
    cusip                   STRING,
    sedol                   STRING,
    ticker                  STRING,
    issuer                  STRING,
    maturity_date           DATE,
    coupon_rate             DECIMAL(8,4),
    face_value              DECIMAL(18,2),
    status                  STRING,
    is_active               BOOLEAN,
    created_at              TIMESTAMP,
    created_by              STRING,
    updated_at              TIMESTAMP,
    updated_by              STRING,
    deleted_at              TIMESTAMP
)
CLUSTERED BY (security_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

CREATE TABLE IF NOT EXISTS cis_security_history (
    history_id          STRING,
    security_id         STRING,
    action              STRING,
    old_value           STRING,
    new_value           STRING,
    changed_by          STRING,
    changed_at          TIMESTAMP,
    created_at          TIMESTAMP
)
CLUSTERED BY (history_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- MARKET DATA TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS cis_equity_price (
    price_id            STRING,
    security_id         STRING,
    security_code       STRING,
    price_date          DATE,
    open_price          DECIMAL(18,6),
    high_price          DECIMAL(18,6),
    low_price           DECIMAL(18,6),
    close_price         DECIMAL(18,6),
    volume              BIGINT,
    currency            STRING,
    source              STRING,
    created_at          TIMESTAMP,
    created_by          STRING,
    updated_at          TIMESTAMP,
    updated_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (price_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

CREATE TABLE IF NOT EXISTS cis_equity_price_history (
    history_id          STRING,
    price_id            STRING,
    security_id         STRING,
    security_code       STRING,
    price_date          DATE,
    open_price          DECIMAL(18,6),
    high_price          DECIMAL(18,6),
    low_price           DECIMAL(18,6),
    close_price         DECIMAL(18,6),
    volume              BIGINT,
    currency            STRING,
    source              STRING,
    change_type         STRING,
    changed_by          STRING,
    changed_at          TIMESTAMP,
    created_at          TIMESTAMP
)
CLUSTERED BY (history_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

CREATE TABLE IF NOT EXISTS cis_fx_rate (
    rate_id             STRING,
    from_currency       STRING,
    to_currency         STRING,
    rate_date           DATE,
    rate                DECIMAL(18,8),
    bid_rate            DECIMAL(18,8),
    ask_rate            DECIMAL(18,8),
    source              STRING,
    created_at          TIMESTAMP,
    created_by          STRING,
    updated_at          TIMESTAMP,
    updated_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (rate_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

CREATE TABLE IF NOT EXISTS cis_fx_rate_history (
    history_id          STRING,
    rate_id             STRING,
    from_currency       STRING,
    to_currency         STRING,
    rate_date           DATE,
    rate                DECIMAL(18,8),
    bid_rate            DECIMAL(18,8),
    ask_rate            DECIMAL(18,8),
    source              STRING,
    change_type         STRING,
    changed_by          STRING,
    changed_at          TIMESTAMP,
    created_at          TIMESTAMP
)
CLUSTERED BY (history_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- REFERENCE DATA TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS cis_counterparty (
    counterparty_id     STRING,
    counterparty_code   STRING,
    counterparty_name   STRING,
    counterparty_type   STRING,
    country             STRING,
    address             STRING,
    contact_name        STRING,
    contact_email       STRING,
    contact_phone       STRING,
    status              STRING,
    is_active           BOOLEAN,
    created_at          TIMESTAMP,
    created_by          STRING,
    updated_at          TIMESTAMP,
    updated_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (counterparty_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

CREATE TABLE IF NOT EXISTS cis_currency (
    currency_id         STRING,
    currency_code       STRING,
    currency_name       STRING,
    symbol              STRING,
    decimal_places      INT,
    is_active           BOOLEAN,
    created_at          TIMESTAMP,
    created_by          STRING,
    updated_at          TIMESTAMP,
    updated_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (currency_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

CREATE TABLE IF NOT EXISTS cis_country (
    country_id          STRING,
    country_code        STRING,
    country_name        STRING,
    region              STRING,
    currency_code       STRING,
    is_active           BOOLEAN,
    created_at          TIMESTAMP,
    created_by          STRING,
    updated_at          TIMESTAMP,
    updated_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (country_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- UDF (User-Defined Fields) TABLE
-- ============================================================================
-- Single table for UDF field definitions with full CRUD support
-- Soft delete via deleted_at timestamp, restore by setting deleted_at to NULL

CREATE TABLE IF NOT EXISTS cis_udf_field (
    field_id            STRING,
    object_type         STRING,
    field_name          STRING,
    field_label         STRING,
    field_type          STRING,
    is_required         BOOLEAN,
    default_value       STRING,
    options             STRING,
    display_order       INT,
    is_active           BOOLEAN,
    created_at          TIMESTAMP,
    created_by          STRING,
    updated_at          TIMESTAMP,
    updated_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (field_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- SEQUENCE TABLE (for ID generation)
-- ============================================================================

CREATE TABLE IF NOT EXISTS cis_sequence (
    sequence_name       STRING,
    current_value       BIGINT,
    increment_by        INT,
    updated_at          TIMESTAMP
)
CLUSTERED BY (sequence_name) INTO 1 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- HELP CONTENT TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS cis_help_content (
    help_id             STRING,
    page_key            STRING,
    section_key         STRING,
    title               STRING,
    content             STRING,
    display_order       INT,
    is_active           BOOLEAN,
    created_at          TIMESTAMP,
    created_by          STRING,
    updated_at          TIMESTAMP,
    updated_by          STRING,
    deleted_at          TIMESTAMP
)
CLUSTERED BY (help_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- END OF DDL
-- ============================================================================
