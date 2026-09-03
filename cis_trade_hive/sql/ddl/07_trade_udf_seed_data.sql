-- ============================================================================
-- Trade UDF Seed Data
-- ============================================================================
-- Description: Pre-defined UDF (User Defined Fields) for Trade entity
--              Based on Trade_udf.JPG specifications
--
-- Database: gmp_cis
-- Created: 2026-01-12
-- Version: 1.0
--
-- UDF Fields for Trade:
--   1. Fund Type         - Dropdown (Equity, Bond, etc.)
--   2. Section 31/26     - Dropdown (Regulatory section)
--   3. Sub Custodian     - Dropdown
--   4. Disclosure Req    - Boolean
--   5. Counter Pledged   - Boolean
--   6. Revision Code     - Dropdown
--   7. UOBN/UOBN-HK      - Dropdown
--   8. Income/Exp Type   - Dropdown
--   9. Currency Hedge    - Boolean
--
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- INSERT UDF DEFINITIONS FOR TRADE
-- ============================================================================
-- Note: Uses cis_udf_field table (see cis_udf_field.sql)
-- Format: field_name, label, field_type, entity_type, is_required, dropdown_options, etc.
-- ============================================================================

-- First, let's check if cis_udf_field table exists
-- DESCRIBE cis_udf_field;

-- Clear existing Trade UDFs (if re-running)
-- DELETE FROM cis_udf_field WHERE entity_type = 'TRADE';

-- ============================================================================
-- 1. Fund Type
-- ============================================================================
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2001,
    'fund_type',
    'Fund Type',
    'Type of fund (e.g., Equity, Bond)',
    'DROPDOWN',
    'TRADE',
    true,
    '["Equity", "Fixed Income", "Money Market", "Balanced", "Alternative", "Real Estate", "Commodity", "Other"]',
    10,
    'Classification',
    true,
    NOW(),
    'system'
);

-- ============================================================================
-- 2. Section 31/26
-- ============================================================================
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2002,
    'section_31_26',
    'Section 31/26',
    'Regulatory section applicable',
    'DROPDOWN',
    'TRADE',
    false,
    '["Section 31", "Section 26", "Both", "N/A"]',
    20,
    'Regulatory',
    true,
    NOW(),
    'system'
);

-- ============================================================================
-- 3. Sub Custodian
-- ============================================================================
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2003,
    'sub_custodian',
    'Sub Custodian',
    'Name of sub-custodian handling assets',
    'DROPDOWN',
    'TRADE',
    true,
    '["DBS Bank", "Standard Chartered", "Citibank", "HSBC", "BNP Paribas", "State Street", "Northern Trust", "Other"]',
    30,
    'Custody',
    true,
    NOW(),
    'system'
);

-- ============================================================================
-- 4. Disclosure Req
-- ============================================================================
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2004,
    'disclosure_req',
    'Disclosure Req',
    'Disclosure requirement flag',
    'BOOLEAN',
    'TRADE',
    false,
    NULL,
    40,
    'Regulatory',
    true,
    NOW(),
    'system'
);

-- ============================================================================
-- 5. Counter Pledged
-- ============================================================================
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2005,
    'counter_pledged',
    'Counter Pledged',
    'Indicates if counterparty pledged',
    'BOOLEAN',
    'TRADE',
    false,
    NULL,
    50,
    'Counterparty',
    true,
    NOW(),
    'system'
);

-- ============================================================================
-- 6. Revision Code
-- ============================================================================
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2006,
    'revision_code',
    'Revision Code',
    'Code for revision tracking',
    'DROPDOWN',
    'TRADE',
    false,
    '["REV-001", "REV-002", "REV-003", "N/A"]',
    60,
    'Tracking',
    true,
    NOW(),
    'system'
);

-- ============================================================================
-- 7. UOBN/UOBN-HK
-- ============================================================================
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2007,
    'uobn_uobn_hk',
    'UOBN/UOBN-HK',
    'Unique order booking number',
    'DROPDOWN',
    'TRADE',
    true,
    '["UOBN-SG", "UOBN-HK", "UOBN-MY", "UOBN-TH", "UOBN-ID", "UOBN-CN", "Other"]',
    70,
    'Booking',
    true,
    NOW(),
    'system'
);

-- ============================================================================
-- 8. Income/Exp Type
-- ============================================================================
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2008,
    'income_exp_type',
    'Income/Exp Type',
    'Type of income or expense',
    'DROPDOWN',
    'TRADE',
    true,
    '["Trading", "Investment", "Dividend", "Interest", "Capital Gain", "Fee", "Commission", "Tax", "Other"]',
    80,
    'Classification',
    true,
    NOW(),
    'system'
);

-- ============================================================================
-- 9. Currency Hedge
-- ============================================================================
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2009,
    'currency_hedge',
    'Currency Hedge',
    'Indicates if currency hedge is applied',
    'BOOLEAN',
    'TRADE',
    false,
    NULL,
    90,
    'Risk',
    true,
    NOW(),
    'system'
);

-- ============================================================================
-- ADDITIONAL DROPDOWN OPTIONS FOR TRADE FIELDS
-- ============================================================================

-- Trade Status Options
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2010,
    'trade_status',
    'Trade Status',
    'Trading status of the transaction',
    'DROPDOWN',
    'TRADE',
    true,
    '["Pending", "Confirmed", "Matched", "Settled", "Failed", "Cancelled"]',
    5,
    'Status',
    true,
    NOW(),
    'system'
);

-- Open/Close Position Options
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2011,
    'open_close_position',
    'Open/Close Position',
    'Position status (Open or Close)',
    'DROPDOWN',
    'TRADE',
    true,
    '["Open", "Close"]',
    15,
    'Position',
    true,
    NOW(),
    'system'
);

-- GL Fund Type Options
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2012,
    'gl_fund_type',
    'GL Fund Type',
    'General ledger fund type',
    'DROPDOWN',
    'TRADE',
    true,
    '["Trading Book", "Banking Book", "Investment Book", "Hedge Book", "Other"]',
    100,
    'Accounting',
    true,
    NOW(),
    'system'
);

-- Selling Rule Options
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2013,
    'selling_rule',
    'Selling Rule',
    'Rule applied for selling',
    'DROPDOWN',
    'TRADE',
    true,
    '["FIFO", "LIFO", "Weighted Average", "Specific Identification", "HIFO"]',
    110,
    'Trading',
    true,
    NOW(),
    'system'
);

-- Broker List Options (can be extended)
INSERT INTO cis_udf_field (
    field_id,
    field_name,
    label,
    description,
    field_type,
    entity_type,
    is_required,
    dropdown_options,
    display_order,
    group_name,
    is_active,
    created_at,
    created_by
) VALUES (
    2014,
    'brokers',
    'Brokers',
    'List of available brokers',
    'DROPDOWN',
    'TRADE',
    true,
    '["Goldman Sachs", "Morgan Stanley", "JP Morgan", "UBS", "Credit Suisse", "Barclays", "Deutsche Bank", "HSBC", "Citi", "BofA Securities", "Other"]',
    120,
    'Execution',
    true,
    NOW(),
    'system'
);

-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Check all Trade UDFs created
SELECT field_id, field_name, label, field_type, is_required, display_order
FROM cis_udf_field
WHERE entity_type = 'TRADE'
ORDER BY display_order;

-- Count Trade UDFs
SELECT COUNT(*) as trade_udf_count
FROM cis_udf_field
WHERE entity_type = 'TRADE';

-- ============================================================================
-- END OF SEED DATA
-- ============================================================================
