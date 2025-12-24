-- =====================================================
-- CisTrade - Portfolio Tables DDL
-- Implements Four-Eyes Principle (Maker-Checker)
-- =====================================================

-- Portfolio Table
CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Basic Information
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,

    -- Currency
    currency VARCHAR(3) NOT NULL,

    -- Management
    manager VARCHAR(200),
    portfolio_client VARCHAR(200),

    -- Financial
    cash_balance DECIMAL(20, 2) DEFAULT 0,
    cash_balance_list VARCHAR(200),

    -- Classification
    cost_centre_code VARCHAR(50),
    corp_code VARCHAR(50),
    account_group VARCHAR(100),
    portfolio_group VARCHAR(100),
    report_group VARCHAR(100),
    entity_group VARCHAR(100),

    -- Revaluation
    revaluation_status VARCHAR(50),

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    is_active BOOLEAN DEFAULT FALSE,

    -- Four-Eyes Principle
    submitted_for_approval_at DATETIME,
    submitted_by_id INTEGER,
    reviewed_at DATETIME,
    reviewed_by_id INTEGER,
    review_comments TEXT,

    -- Metadata
    metadata TEXT,
    notes TEXT,

    -- Audit Fields
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by_id INTEGER,
    updated_by_id INTEGER,

    FOREIGN KEY (created_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (submitted_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (reviewed_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
);

CREATE INDEX idx_portfolio_code ON portfolio(code);
CREATE INDEX idx_portfolio_status ON portfolio(status, is_active);
CREATE INDEX idx_portfolio_currency ON portfolio(currency);
CREATE INDEX idx_portfolio_created ON portfolio(created_at);

-- Portfolio History Table
CREATE TABLE IF NOT EXISTS portfolio_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    changes TEXT,
    comments TEXT,
    performed_by_id INTEGER,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by_id INTEGER,
    updated_by_id INTEGER,

    FOREIGN KEY (portfolio_id) REFERENCES portfolio(id) ON DELETE CASCADE,
    FOREIGN KEY (performed_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
);

CREATE INDEX idx_portfolio_history_portfolio ON portfolio_history(portfolio_id);
CREATE INDEX idx_portfolio_history_created ON portfolio_history(created_at);

-- =====================================================
-- MySQL Version (for production)
-- =====================================================

/*
CREATE TABLE IF NOT EXISTS portfolio (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,

    currency VARCHAR(3) NOT NULL,

    manager VARCHAR(200),
    portfolio_client VARCHAR(200),

    cash_balance DECIMAL(20, 2) DEFAULT 0,
    cash_balance_list VARCHAR(200),

    cost_centre_code VARCHAR(50),
    corp_code VARCHAR(50),
    account_group VARCHAR(100),
    portfolio_group VARCHAR(100),
    report_group VARCHAR(100),
    entity_group VARCHAR(100),

    revaluation_status VARCHAR(50),

    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    is_active BOOLEAN DEFAULT FALSE,

    submitted_for_approval_at DATETIME,
    submitted_by_id INT,
    reviewed_at DATETIME,
    reviewed_by_id INT,
    review_comments TEXT,

    metadata JSON,
    notes TEXT,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by_id INT,
    updated_by_id INT,

    INDEX idx_portfolio_code (code),
    INDEX idx_portfolio_status (status, is_active),
    INDEX idx_portfolio_currency (currency),
    INDEX idx_portfolio_created (created_at),

    FOREIGN KEY (created_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (submitted_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (reviewed_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS portfolio_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    portfolio_id BIGINT NOT NULL,
    action VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    changes JSON,
    comments TEXT,
    performed_by_id INT,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by_id INT,
    updated_by_id INT,

    INDEX idx_portfolio_history_portfolio (portfolio_id),
    INDEX idx_portfolio_history_created (created_at),

    FOREIGN KEY (portfolio_id) REFERENCES portfolio(id) ON DELETE CASCADE,
    FOREIGN KEY (performed_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
*/
