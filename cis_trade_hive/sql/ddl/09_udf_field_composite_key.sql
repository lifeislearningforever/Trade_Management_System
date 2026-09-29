-- ============================================================================
-- UDF FIELD TABLE - Composite Primary Key Schema
-- ============================================================================
-- Purpose: UDF field table with composite primary key (object_type, field_name, field_value)
-- Removes udf_id and uses 3 columns as primary key
--
-- Primary Key: (object_type, field_name, field_value)
--
-- Usage:
--   - Object Type: Entity type (TRADE, PORTFOLIO, SECURITY, etc.)
--   - Field Name: The dropdown field name (Fund Type, Selling Rule, etc.)
--   - Field Value: The dropdown option value (EQUITY, FIFO, etc.)
--     - Empty string ('') for field definition records (admin creates)
--     - Non-empty for dropdown option values (admin/system adds)
--
-- Created: 2026-01-16
-- ============================================================================

-- Drop existing table if recreating
-- DROP TABLE IF EXISTS gmp_cis.cis_udf_field_kudu;

-- ============================================================================
-- CREATE TABLE with Composite Primary Key
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmp_cis.cis_udf_field_kudu (
    -- Composite Primary Key columns
    object_type STRING NOT NULL,           -- Entity type: TRADE, PORTFOLIO, SECURITY, etc.
    field_name STRING NOT NULL,            -- Field definition name: Fund Type, Selling Rule, etc.
    field_value STRING NOT NULL,           -- Dropdown value (empty for definitions, non-empty for options)

    -- Metadata
    is_active BOOLEAN DEFAULT true,        -- Soft delete flag

    -- Audit Fields
    created_by STRING NOT NULL,
    created_at BIGINT NOT NULL,            -- Unix timestamp in milliseconds
    updated_by STRING NOT NULL,
    updated_at BIGINT NOT NULL,            -- Unix timestamp in milliseconds

    -- Composite Primary Key
    PRIMARY KEY (object_type, field_name, field_value)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '1');

-- Create Impala external table for easy querying
-- DROP TABLE IF EXISTS gmp_cis.cis_udf_field;
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_udf_field
STORED AS KUDU
TBLPROPERTIES(
    'kudu.table_name' = 'impala::gmp_cis.cis_udf_field_kudu'
);


-- ============================================================================
-- TRADE UDF DATA - Field Definitions and Values
-- ============================================================================

-- Fund Type - Field Definition (empty field_value)
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Fund Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Fund Type - Dropdown Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Fund Type', 'EQUITY', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Fund Type', 'FIXED_INCOME', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Fund Type', 'MONEY_MARKET', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Fund Type', 'BALANCED', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Section 31/26 - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Section 31/26', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Section 31/26', 'SEC_31', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Section 31/26', 'SEC_26', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Section 31/26', 'BOTH', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Section 31/26', 'NA', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Sub Custodian - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Sub Custodian', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Sub Custodian', 'DBS-SG', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Sub Custodian', 'SCB-SG', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Sub Custodian', 'CITI-SG', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Revision Code - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Revision Code', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Revision Code', 'REV-001', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Revision Code', 'REV-002', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Revision Code', 'NA', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- UOBN/UOBN-HK - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'UOBN/UOBN-HK', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'UOBN/UOBN-HK', 'UOBN-SG', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'UOBN/UOBN-HK', 'UOBN-HK', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'UOBN/UOBN-HK', 'UOBN-MY', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Income/Exp Type - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Income/Exp Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Income/Exp Type', 'TRADING', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Income/Exp Type', 'INVESTMENT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Income/Exp Type', 'DIVIDEND', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Income/Exp Type', 'INTEREST', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Selling Rule - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Selling Rule', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Selling Rule', 'FIFO', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Selling Rule', 'LIFO', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Selling Rule', 'WAVG', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Selling Rule', 'SPEC', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- GL Fund Type - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'GL Fund Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'GL Fund Type', 'TRADING', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'GL Fund Type', 'BANKING', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'GL Fund Type', 'INVESTMENT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'GL Fund Type', 'HEDGE', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- GL Cost Centre - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'GL Cost Centre', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'GL Cost Centre', 'CC-001', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'GL Cost Centre', 'CC-002', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'GL Cost Centre', 'CC-003', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- GL Account Code - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'GL Account Code', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'GL Account Code', 'ACC-1001', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'GL Account Code', 'ACC-1002', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'GL Account Code', 'ACC-1003', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Open/Close Position - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Open/Close Position', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Open/Close Position', 'OPEN', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Open/Close Position', 'CLOSE', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Extension - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Extension', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Extension', 'NONE', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Extension', 'EXT-1D', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Extension', 'EXT-2D', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Amortisation Method - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Amortisation Method', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Amortisation Method', 'STD', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Amortisation Method', 'EFF_INT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Amortisation Method', 'STRAIGHT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Amortisation Method', 'NONE', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Delivery Type - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Delivery Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Delivery Type', 'TRANSFER', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Delivery Type', 'CORP_ACTION', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Delivery Type', 'SETTLEMENT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Delivery Type', 'REDEMPTION', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Income Type - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Income Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Income Type', 'DIVIDEND', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Income Type', 'STOCK_DIV', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Income Type', 'INTEREST', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Income Type', 'PREMIUM', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Income Type', 'DISTRIBUTION', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Split Type - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Split Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Split Type', 'STOCK_SPLIT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Split Type', 'REVERSE_SPLIT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Split Type', 'LOT_SPLIT', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Split Type', 'BONUS_ISSUE', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);

-- Reduction Type - Field Definition and Values
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
    ('TRADE', 'Reduction Type', '', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Reduction Type', 'RETURN_CAPITAL', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Reduction Type', 'AMORTIZATION', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Reduction Type', 'WRITEDOWN', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000),
    ('TRADE', 'Reduction Type', 'PARTIAL_REDEMP', true, 'SYSTEM', 1705363200000, 'SYSTEM', 1705363200000);


-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- List all object types (field definitions)
SELECT DISTINCT object_type
FROM gmp_cis.cis_udf_field
WHERE field_value = ''
  AND is_active = true
ORDER BY object_type;

-- List all field definitions for TRADE
SELECT object_type, field_name
FROM gmp_cis.cis_udf_field
WHERE object_type = 'TRADE'
  AND field_value = ''
  AND is_active = true
ORDER BY field_name;

-- List all dropdown values for a specific field (e.g., Fund Type)
SELECT object_type, field_name, field_value
FROM gmp_cis.cis_udf_field
WHERE object_type = 'TRADE'
  AND field_name = 'Fund Type'
  AND field_value != ''
  AND is_active = true
ORDER BY field_value;

-- Count by field name
SELECT field_name, COUNT(*) - 1 as value_count  -- minus 1 for the definition record
FROM gmp_cis.cis_udf_field
WHERE object_type = 'TRADE'
  AND is_active = true
GROUP BY field_name
ORDER BY field_name;

-- ============================================================================
-- END OF UDF FIELD COMPOSITE KEY SCHEMA
-- ============================================================================
