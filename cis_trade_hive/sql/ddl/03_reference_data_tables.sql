-- =====================================================
-- CisTrade - Reference Data Tables DDL
-- These tables cache data from Kudu/Impala
-- =====================================================

-- Currency Table
CREATE TABLE IF NOT EXISTS reference_currency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(3) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    full_name VARCHAR(200),
    symbol VARCHAR(10),

    decimal_places INTEGER DEFAULT 2,
    rate_precision INTEGER DEFAULT 6,

    calendar VARCHAR(50),
    spot_schedule VARCHAR(50),

    is_active BOOLEAN DEFAULT TRUE,
    is_base_currency BOOLEAN DEFAULT FALSE,

    source_system VARCHAR(50),
    source_id VARCHAR(100),
    last_synced_at DATETIME,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by_id INTEGER,
    updated_by_id INTEGER,

    FOREIGN KEY (created_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
);

CREATE INDEX idx_currency_code ON reference_currency(code);
CREATE INDEX idx_currency_active ON reference_currency(is_active);

-- Country Table
CREATE TABLE IF NOT EXISTS reference_country (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(3) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    full_name VARCHAR(200),

    region VARCHAR(100),
    continent VARCHAR(50),
    currency_code VARCHAR(3),

    is_active BOOLEAN DEFAULT TRUE,

    source_system VARCHAR(50),
    source_id VARCHAR(100),
    last_synced_at DATETIME,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by_id INTEGER,
    updated_by_id INTEGER,

    FOREIGN KEY (created_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
);

CREATE INDEX idx_country_code ON reference_country(code);
CREATE INDEX idx_country_active ON reference_country(is_active);

-- Calendar Table
CREATE TABLE IF NOT EXISTS reference_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_label VARCHAR(50) NOT NULL,
    calendar_description VARCHAR(200),
    holiday_date DATE NOT NULL,

    holiday_name VARCHAR(200),
    holiday_type VARCHAR(50),

    is_trading_day BOOLEAN DEFAULT TRUE,
    is_settlement_day BOOLEAN DEFAULT TRUE,
    market_open_time TIME,
    market_close_time TIME,
    is_half_day BOOLEAN DEFAULT FALSE,

    exchange VARCHAR(50) DEFAULT 'SGX',

    source_system VARCHAR(50),
    source_id VARCHAR(100),
    last_synced_at DATETIME,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by_id INTEGER,
    updated_by_id INTEGER,

    UNIQUE(calendar_label, holiday_date),

    FOREIGN KEY (created_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
);

CREATE INDEX idx_calendar_date ON reference_calendar(holiday_date);
CREATE INDEX idx_calendar_label ON reference_calendar(calendar_label);
CREATE INDEX idx_calendar_exchange ON reference_calendar(exchange);

-- Counterparty Table
CREATE TABLE IF NOT EXISTS reference_counterparty (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    legal_name VARCHAR(300),
    short_name VARCHAR(100),

    counterparty_type VARCHAR(50) DEFAULT 'CORPORATE',

    email VARCHAR(254),
    phone VARCHAR(20),
    website VARCHAR(200),

    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    postal_code VARCHAR(20),

    tax_id VARCHAR(50),
    registration_number VARCHAR(100),

    status VARCHAR(20) DEFAULT 'ACTIVE',
    is_active BOOLEAN DEFAULT TRUE,

    risk_category VARCHAR(20) DEFAULT 'MEDIUM',
    credit_rating VARCHAR(20),

    source_system VARCHAR(50),
    source_id VARCHAR(100),
    last_synced_at DATETIME,

    metadata TEXT,
    notes TEXT,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by_id INTEGER,
    updated_by_id INTEGER,

    FOREIGN KEY (created_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
);

CREATE INDEX idx_counterparty_code ON reference_counterparty(code);
CREATE INDEX idx_counterparty_type ON reference_counterparty(counterparty_type);
CREATE INDEX idx_counterparty_status ON reference_counterparty(status);

-- =====================================================
-- MySQL Version available in comments
-- Replace INTEGER with BIGINT, TEXT with JSON where appropriate
-- =====================================================
