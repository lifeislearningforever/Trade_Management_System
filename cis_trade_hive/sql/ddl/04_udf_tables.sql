-- =====================================================
-- CisTrade - UDF (User-Defined Fields) Tables DDL
-- Allows flexible custom fields with Four-Eyes principle
-- =====================================================

-- UDF Definition Table
CREATE TABLE IF NOT EXISTS udf (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Basic Information
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,

    -- Field Type
    field_type VARCHAR(50) NOT NULL, -- TEXT, NUMBER, DATE, BOOLEAN, SELECT
    data_type VARCHAR(50),

    -- Validation
    is_required BOOLEAN DEFAULT FALSE,
    min_length INTEGER,
    max_length INTEGER,
    min_value DECIMAL(20, 4),
    max_value DECIMAL(20, 4),
    regex_pattern VARCHAR(500),

    -- Options (for SELECT type)
    options TEXT, -- JSON array of options

    -- Display
    display_order INTEGER DEFAULT 0,
    help_text TEXT,
    placeholder VARCHAR(200),

    -- Scope
    entity_type VARCHAR(100), -- portfolio, trade, instrument, etc.

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

CREATE INDEX idx_udf_code ON udf(code);
CREATE INDEX idx_udf_status ON udf(status);
CREATE INDEX idx_udf_entity ON udf(entity_type);
CREATE INDEX idx_udf_active ON udf(is_active);

-- UDF Values Table (stores actual values)
CREATE TABLE IF NOT EXISTS udf_value (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    udf_id INTEGER NOT NULL,

    -- Entity reference
    entity_type VARCHAR(100) NOT NULL,
    entity_id INTEGER NOT NULL,

    -- Value storage
    text_value TEXT,
    number_value DECIMAL(20, 4),
    date_value DATE,
    boolean_value BOOLEAN,
    json_value TEXT,

    -- Audit Fields
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by_id INTEGER,
    updated_by_id INTEGER,

    UNIQUE(udf_id, entity_type, entity_id),

    FOREIGN KEY (udf_id) REFERENCES udf(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
);

CREATE INDEX idx_udf_value_udf ON udf_value(udf_id);
CREATE INDEX idx_udf_value_entity ON udf_value(entity_type, entity_id);

-- UDF History Table
CREATE TABLE IF NOT EXISTS udf_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    udf_id INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    changes TEXT,
    comments TEXT,
    performed_by_id INTEGER,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by_id INTEGER,
    updated_by_id INTEGER,

    FOREIGN KEY (udf_id) REFERENCES udf(id) ON DELETE CASCADE,
    FOREIGN KEY (performed_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
);

CREATE INDEX idx_udf_history_udf ON udf_history(udf_id);
CREATE INDEX idx_udf_history_created ON udf_history(created_at);
