-- =====================================================
-- CisTrade - Core Tables DDL
-- Database: SQLite (Development) / MySQL (Production)
-- =====================================================

-- Audit Log Table
CREATE TABLE IF NOT EXISTS core_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER,
    username VARCHAR(150) NOT NULL,

    -- Action Details
    action VARCHAR(20) NOT NULL,
    severity VARCHAR(10) NOT NULL DEFAULT 'INFO',

    -- Object Details
    object_type VARCHAR(100) NOT NULL,
    object_id VARCHAR(100),
    object_repr VARCHAR(500),

    -- Change Details
    old_value TEXT,
    new_value TEXT,
    changes TEXT,

    -- Request Details
    ip_address VARCHAR(45),
    user_agent TEXT,
    request_path VARCHAR(500),
    request_method VARCHAR(10),

    -- Additional Context
    description TEXT,
    additional_data TEXT,

    -- Four-Eyes Principle
    requires_approval BOOLEAN DEFAULT FALSE,
    approved_by_id INTEGER,
    approved_at DATETIME,
    approval_status VARCHAR(20) DEFAULT 'PENDING',

    FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (approved_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
);

CREATE INDEX idx_audit_timestamp ON core_audit_log(timestamp);
CREATE INDEX idx_audit_user ON core_audit_log(user_id, timestamp);
CREATE INDEX idx_audit_object ON core_audit_log(object_type, object_id);
CREATE INDEX idx_audit_action ON core_audit_log(action, timestamp);
CREATE INDEX idx_audit_approval ON core_audit_log(approval_status);

-- =====================================================
-- MySQL Version (for production)
-- =====================================================

/*
CREATE TABLE IF NOT EXISTS core_audit_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id INT,
    username VARCHAR(150) NOT NULL,

    action VARCHAR(20) NOT NULL,
    severity VARCHAR(10) NOT NULL DEFAULT 'INFO',

    object_type VARCHAR(100) NOT NULL,
    object_id VARCHAR(100),
    object_repr VARCHAR(500),

    old_value JSON,
    new_value JSON,
    changes JSON,

    ip_address VARCHAR(45),
    user_agent TEXT,
    request_path VARCHAR(500),
    request_method VARCHAR(10),

    description TEXT,
    additional_data JSON,

    requires_approval BOOLEAN DEFAULT FALSE,
    approved_by_id INT,
    approved_at DATETIME,
    approval_status VARCHAR(20) DEFAULT 'PENDING',

    INDEX idx_audit_timestamp (timestamp),
    INDEX idx_audit_user (user_id, timestamp),
    INDEX idx_audit_object (object_type, object_id),
    INDEX idx_audit_action (action, timestamp),
    INDEX idx_audit_approval (approval_status),

    FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    FOREIGN KEY (approved_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
*/
