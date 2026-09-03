-- ============================================
-- UDF Sample Data Initialization Script
-- Run this in beeline to populate sample UDF data
-- ============================================

-- Usage:
-- beeline -u jdbc:hive2://localhost:10000/cis -f init_udf_sample_data.sql

-- ============================================
-- 1. UDF Definitions for PORTFOLIO
-- ============================================

-- Account Group (Dropdown - Required)
INSERT INTO cis.cis_udf_definition VALUES (
    1, 'account_group', 'Account Group',
    'Portfolio account classification', 'DROPDOWN', 'PORTFOLIO',
    true, false, NULL, NULL, NULL, 1,
    'Portfolio Classification',
    NULL, NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Entity Group (Dropdown - Required)
INSERT INTO cis.cis_udf_definition VALUES (
    2, 'entity_group', 'Entity Group',
    'Legal entity grouping', 'DROPDOWN', 'PORTFOLIO',
    true, false, NULL, NULL, NULL, 2,
    'Portfolio Classification',
    NULL, NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Risk Rating (Number 1-10)
INSERT INTO cis.cis_udf_definition VALUES (
    3, 'risk_rating', 'Risk Rating',
    'Portfolio risk rating (1-10)', 'NUMBER', 'PORTFOLIO',
    false, false, NULL, 1, 10, 3,
    'Risk Management',
    NULL, NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Compliance Notes (Text - 500 chars max)
INSERT INTO cis.cis_udf_definition VALUES (
    4, 'compliance_notes', 'Compliance Notes',
    'Internal compliance notes', 'TEXT', 'PORTFOLIO',
    false, false, 500, NULL, NULL, 4,
    'Compliance',
    NULL, NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Is Restricted (Boolean)
INSERT INTO cis.cis_udf_definition VALUES (
    5, 'is_restricted', 'Restricted',
    'Is this portfolio restricted', 'BOOLEAN', 'PORTFOLIO',
    false, false, NULL, NULL, NULL, 5,
    'Compliance',
    NULL, NULL, NULL, false, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Portfolio Manager (Text - 100 chars)
INSERT INTO cis.cis_udf_definition VALUES (
    6, 'portfolio_manager', 'Portfolio Manager',
    'Name of assigned portfolio manager', 'TEXT', 'PORTFOLIO',
    false, false, 100, NULL, NULL, 6,
    'Management',
    NULL, NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Target Return (Percentage)
INSERT INTO cis.cis_udf_definition VALUES (
    7, 'target_return', 'Target Return %',
    'Target annual return percentage', 'PERCENTAGE', 'PORTFOLIO',
    false, false, NULL, 0, 100, 7,
    'Performance',
    NULL, NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Review Date (Date)
INSERT INTO cis.cis_udf_definition VALUES (
    8, 'next_review_date', 'Next Review Date',
    'Date of next portfolio review', 'DATE', 'PORTFOLIO',
    false, false, NULL, NULL, NULL, 8,
    'Management',
    NULL, NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- ============================================
-- 2. UDF Dropdown Options
-- ============================================

-- Account Group Options
INSERT INTO cis.cis_udf_option VALUES
('account_group', 'TRADING', 'Trading', 1, true, 'admin', from_unixtime(unix_timestamp()));

INSERT INTO cis.cis_udf_option VALUES
('account_group', 'INVESTMENT', 'Investment', 2, true, 'admin', from_unixtime(unix_timestamp()));

INSERT INTO cis.cis_udf_option VALUES
('account_group', 'HEDGING', 'Hedging', 3, true, 'admin', from_unixtime(unix_timestamp()));

INSERT INTO cis.cis_udf_option VALUES
('account_group', 'TREASURY', 'Treasury', 4, true, 'admin', from_unixtime(unix_timestamp()));

INSERT INTO cis.cis_udf_option VALUES
('account_group', 'OPERATIONS', 'Operations', 5, true, 'admin', from_unixtime(unix_timestamp()));

-- Entity Group Options
INSERT INTO cis.cis_udf_option VALUES
('entity_group', 'CORPORATE', 'Corporate', 1, true, 'admin', from_unixtime(unix_timestamp()));

INSERT INTO cis.cis_udf_option VALUES
('entity_group', 'INSTITUTIONAL', 'Institutional', 2, true, 'admin', from_unixtime(unix_timestamp()));

INSERT INTO cis.cis_udf_option VALUES
('entity_group', 'RETAIL', 'Retail', 3, true, 'admin', from_unixtime(unix_timestamp()));

INSERT INTO cis.cis_udf_option VALUES
('entity_group', 'GOVERNMENT', 'Government', 4, true, 'admin', from_unixtime(unix_timestamp()));

INSERT INTO cis.cis_udf_option VALUES
('entity_group', 'FUND', 'Fund', 5, true, 'admin', from_unixtime(unix_timestamp()));

-- ============================================
-- 3. Sample UDF Values for Portfolio ID 1
-- ============================================

-- Account Group = TRADING
INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 1, 'account_group', 1, 'TRADING',
    NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Entity Group = CORPORATE
INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 1, 'entity_group', 2, 'CORPORATE',
    NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Risk Rating = 7
INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 1, 'risk_rating', 3, NULL,
    7, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Compliance Notes
INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 1, 'compliance_notes', 4, 'Quarterly compliance review required. All KYC documents verified.',
    NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Is Restricted = false
INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 1, 'is_restricted', 5, NULL,
    NULL, NULL, false, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Portfolio Manager
INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 1, 'portfolio_manager', 6, 'John Smith',
    NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- Target Return = 12.5%
INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 1, 'target_return', 7, NULL,
    NULL, 12.5, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- ============================================
-- 4. Sample UDF Values for Portfolio ID 2
-- ============================================

INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 2, 'account_group', 1, 'INVESTMENT',
    NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 2, 'entity_group', 2, 'INSTITUTIONAL',
    NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 2, 'risk_rating', 3, NULL,
    4, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 2, 'is_restricted', 5, NULL,
    NULL, NULL, true, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 2, 'portfolio_manager', 6, 'Sarah Johnson',
    NULL, NULL, NULL, NULL,
    true, 'admin', from_unixtime(unix_timestamp()), 'admin', from_unixtime(unix_timestamp())
);

-- ============================================
-- Verification Queries
-- ============================================

-- Verify UDF Definitions
SELECT COUNT(*) as definition_count FROM cis.cis_udf_definition WHERE is_active = true;

-- Verify UDF Options
SELECT COUNT(*) as option_count FROM cis.cis_udf_option WHERE is_active = true;

-- Verify UDF Values
SELECT COUNT(*) as value_count FROM cis.cis_udf_value WHERE is_active = true;

-- Show Portfolio 1 UDFs
SELECT field_name, value_string, value_int, value_decimal, value_bool
FROM cis.cis_udf_value
WHERE entity_type = 'PORTFOLIO' AND entity_id = 1 AND is_active = true;
