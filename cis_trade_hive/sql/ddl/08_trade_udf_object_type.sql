-- ============================================================================
-- Trade UDF Object Type and Field Name Configuration
-- ============================================================================
-- Purpose: Define UDF fields for Trade entity using simplified schema
--          Admin creates Object Type (TRADE) and Field Names
--          Users add Field Values as dropdown options
--
-- Schema: cis_udf_field table
--   - udf_id: Primary key (timestamp-based)
--   - object_type: 'TRADE' for trade-related fields
--   - field_name: Field definition name (admin creates)
--   - field_value: Dropdown option value (empty for definition, non-empty for values)
--   - is_active: Soft delete flag
--   - Audit fields: created_by, created_at, updated_by, updated_at
--
-- Created: 2026-01-16
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- STEP 1: Create Object Type = TRADE with Field Definitions (Admin)
-- These are field definition records where field_value is empty
-- ============================================================================

-- Field Definition: Fund Type
UPSERT INTO cis_udf_field VALUES (
    3001,                       -- udf_id
    'TRADE',                    -- object_type
    'Fund Type',                -- field_name (definition)
    '',                         -- field_value (empty = definition)
    true,                       -- is_active
    'SYSTEM',                   -- created_by
    1705363200000,              -- created_at (2024-01-16)
    'SYSTEM',                   -- updated_by
    1705363200000               -- updated_at
);

-- Field Definition: Section 31/26
UPSERT INTO cis_udf_field VALUES (
    3002, 'TRADE', 'Section 31/26', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: Sub Custodian
UPSERT INTO cis_udf_field VALUES (
    3003, 'TRADE', 'Sub Custodian', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: Revision Code
UPSERT INTO cis_udf_field VALUES (
    3004, 'TRADE', 'Revision Code', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: UOBN/UOBN-HK
UPSERT INTO cis_udf_field VALUES (
    3005, 'TRADE', 'UOBN/UOBN-HK', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: Income/Exp Type
UPSERT INTO cis_udf_field VALUES (
    3006, 'TRADE', 'Income/Exp Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: Selling Rule
UPSERT INTO cis_udf_field VALUES (
    3007, 'TRADE', 'Selling Rule', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: GL Fund Type
UPSERT INTO cis_udf_field VALUES (
    3008, 'TRADE', 'GL Fund Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: GL Cost Centre
UPSERT INTO cis_udf_field VALUES (
    3009, 'TRADE', 'GL Cost Centre', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: GL Account Code
UPSERT INTO cis_udf_field VALUES (
    3010, 'TRADE', 'GL Account Code', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: Open/Close Position
UPSERT INTO cis_udf_field VALUES (
    3011, 'TRADE', 'Open/Close Position', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: Extension
UPSERT INTO cis_udf_field VALUES (
    3012, 'TRADE', 'Extension', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: Amortisation Method
UPSERT INTO cis_udf_field VALUES (
    3013, 'TRADE', 'Amortisation Method', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: Delivery Type (for Deliver Long)
UPSERT INTO cis_udf_field VALUES (
    3014, 'TRADE', 'Delivery Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: Income Type (for Income tab)
UPSERT INTO cis_udf_field VALUES (
    3015, 'TRADE', 'Income Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: Split Type (for Split Transaction)
UPSERT INTO cis_udf_field VALUES (
    3016, 'TRADE', 'Split Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);

-- Field Definition: Reduction Type (for Reduction Basis)
UPSERT INTO cis_udf_field VALUES (
    3017, 'TRADE', 'Reduction Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000
);


-- ============================================================================
-- STEP 2: Add Field Values (Dropdown Options) for each Field Definition
-- These are value records where field_value is NOT empty
-- ============================================================================

-- Fund Type Values
UPSERT INTO cis_udf_field VALUES (3101, 'TRADE', 'Fund Type', 'EQUITY', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3102, 'TRADE', 'Fund Type', 'FIXED_INCOME', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3103, 'TRADE', 'Fund Type', 'MONEY_MARKET', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3104, 'TRADE', 'Fund Type', 'BALANCED', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Section 31/26 Values
UPSERT INTO cis_udf_field VALUES (3111, 'TRADE', 'Section 31/26', 'SEC_31', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3112, 'TRADE', 'Section 31/26', 'SEC_26', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3113, 'TRADE', 'Section 31/26', 'BOTH', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3114, 'TRADE', 'Section 31/26', 'NA', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Revision Code Values
UPSERT INTO cis_udf_field VALUES (3121, 'TRADE', 'Revision Code', 'REV-001', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3122, 'TRADE', 'Revision Code', 'REV-002', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3123, 'TRADE', 'Revision Code', 'NA', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- UOBN/UOBN-HK Values
UPSERT INTO cis_udf_field VALUES (3131, 'TRADE', 'UOBN/UOBN-HK', 'UOBN-SG', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3132, 'TRADE', 'UOBN/UOBN-HK', 'UOBN-HK', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3133, 'TRADE', 'UOBN/UOBN-HK', 'UOBN-MY', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Income/Exp Type Values
UPSERT INTO cis_udf_field VALUES (3141, 'TRADE', 'Income/Exp Type', 'TRADING', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3142, 'TRADE', 'Income/Exp Type', 'INVESTMENT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3143, 'TRADE', 'Income/Exp Type', 'DIVIDEND', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3144, 'TRADE', 'Income/Exp Type', 'INTEREST', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Selling Rule Values
UPSERT INTO cis_udf_field VALUES (3151, 'TRADE', 'Selling Rule', 'FIFO', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3152, 'TRADE', 'Selling Rule', 'LIFO', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3153, 'TRADE', 'Selling Rule', 'WAVG', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3154, 'TRADE', 'Selling Rule', 'SPEC', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- GL Fund Type Values
UPSERT INTO cis_udf_field VALUES (3161, 'TRADE', 'GL Fund Type', 'TRADING', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3162, 'TRADE', 'GL Fund Type', 'BANKING', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3163, 'TRADE', 'GL Fund Type', 'INVESTMENT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3164, 'TRADE', 'GL Fund Type', 'HEDGE', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- GL Cost Centre Values
UPSERT INTO cis_udf_field VALUES (3171, 'TRADE', 'GL Cost Centre', 'CC-001', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3172, 'TRADE', 'GL Cost Centre', 'CC-002', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3173, 'TRADE', 'GL Cost Centre', 'CC-003', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- GL Account Code Values
UPSERT INTO cis_udf_field VALUES (3181, 'TRADE', 'GL Account Code', 'ACC-1001', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3182, 'TRADE', 'GL Account Code', 'ACC-1002', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3183, 'TRADE', 'GL Account Code', 'ACC-1003', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Open/Close Position Values
UPSERT INTO cis_udf_field VALUES (3191, 'TRADE', 'Open/Close Position', 'OPEN', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3192, 'TRADE', 'Open/Close Position', 'CLOSE', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Extension Values
UPSERT INTO cis_udf_field VALUES (3201, 'TRADE', 'Extension', 'NONE', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3202, 'TRADE', 'Extension', 'EXT-1D', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3203, 'TRADE', 'Extension', 'EXT-2D', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Amortisation Method Values
UPSERT INTO cis_udf_field VALUES (3211, 'TRADE', 'Amortisation Method', 'STD', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3212, 'TRADE', 'Amortisation Method', 'EFF_INT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3213, 'TRADE', 'Amortisation Method', 'STRAIGHT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3214, 'TRADE', 'Amortisation Method', 'NONE', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Delivery Type Values (for Deliver Long)
UPSERT INTO cis_udf_field VALUES (3221, 'TRADE', 'Delivery Type', 'TRANSFER', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3222, 'TRADE', 'Delivery Type', 'CORP_ACTION', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3223, 'TRADE', 'Delivery Type', 'SETTLEMENT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3224, 'TRADE', 'Delivery Type', 'REDEMPTION', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Income Type Values (for Income tab)
UPSERT INTO cis_udf_field VALUES (3231, 'TRADE', 'Income Type', 'DIVIDEND', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3232, 'TRADE', 'Income Type', 'STOCK_DIV', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3233, 'TRADE', 'Income Type', 'INTEREST', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3234, 'TRADE', 'Income Type', 'PREMIUM', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3235, 'TRADE', 'Income Type', 'DISTRIBUTION', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Split Type Values (for Split Transaction)
UPSERT INTO cis_udf_field VALUES (3241, 'TRADE', 'Split Type', 'STOCK_SPLIT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3242, 'TRADE', 'Split Type', 'REVERSE_SPLIT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3243, 'TRADE', 'Split Type', 'LOT_SPLIT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3244, 'TRADE', 'Split Type', 'BONUS_ISSUE', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Reduction Type Values (for Reduction Basis)
UPSERT INTO cis_udf_field VALUES (3251, 'TRADE', 'Reduction Type', 'RETURN_CAPITAL', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3252, 'TRADE', 'Reduction Type', 'AMORTIZATION', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3253, 'TRADE', 'Reduction Type', 'WRITEDOWN', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3254, 'TRADE', 'Reduction Type', 'PARTIAL_REDEMP', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Sub Custodian Values (from counterparty where is_custodian=true is preferred)
-- These are fallback values if counterparty query fails
UPSERT INTO cis_udf_field VALUES (3261, 'TRADE', 'Sub Custodian', 'DBS-SG', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3262, 'TRADE', 'Sub Custodian', 'SCB-SG', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);
UPSERT INTO cis_udf_field VALUES (3263, 'TRADE', 'Sub Custodian', 'CITI-SG', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);


-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- List all TRADE field definitions (admin-created)
SELECT udf_id, object_type, field_name
FROM cis_udf_field
WHERE object_type = 'TRADE'
  AND (field_value IS NULL OR field_value = '')
  AND is_active = true
ORDER BY field_name;

-- List all field values for a specific field (e.g., Fund Type)
SELECT udf_id, field_name, field_value
FROM cis_udf_field
WHERE object_type = 'TRADE'
  AND field_name = 'Fund Type'
  AND field_value IS NOT NULL
  AND field_value != ''
  AND is_active = true
ORDER BY field_value;

-- Count by field_name
SELECT field_name, COUNT(*) as value_count
FROM cis_udf_field
WHERE object_type = 'TRADE'
  AND field_value IS NOT NULL
  AND field_value != ''
  AND is_active = true
GROUP BY field_name
ORDER BY field_name;

-- ============================================================================
-- END OF TRADE UDF CONFIGURATION
-- ============================================================================
