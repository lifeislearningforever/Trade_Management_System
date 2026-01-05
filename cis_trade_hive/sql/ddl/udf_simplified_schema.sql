-- ============================================================================
-- UDF SIMPLIFIED SCHEMA - Free Text Approach
-- ============================================================================
-- Purpose: Simplified UDF system with free-text fields only
-- Requirements: Field Name, Label, Entity Type, Required, Active
-- ============================================================================

-- Drop old complex tables (if redesigning from scratch)
-- DROP TABLE IF EXISTS gmp_cis.cis_udf_definition;
-- DROP TABLE IF EXISTS gmp_cis.cis_udf_option;
-- DROP TABLE IF EXISTS gmp_cis.cis_udf_value;

-- ============================================================================
-- Table: cis_udf_field
-- Purpose: Simple UDF field definitions (free text approach)
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmp_cis.cis_udf_field(
    -- Primary Key
    udf_id BIGINT NOT NULL,

    -- Core Fields
    entity_type STRING NOT NULL,        -- Entity this UDF belongs to (PORTFOLIO, TRADE, COMMENTS, etc.)
    field_name STRING NOT NULL,        -- Technical field name (e.g., 'trade_date', 'broker_code')
    field_value STRING NOT NULL,              -- Display label (e.g., 'Trade Date', 'Broker Code')


    -- Metadata
    is_active BOOLEAN DEFAULT true,     -- Soft delete flag (true = active, false = deleted)

    -- Audit Fields
    created_by STRING NOT NULL,
    created_at BIGINT NOT NULL,         -- Unix timestamp in milliseconds
    updated_by STRING NOT NULL,
    updated_at BIGINT NOT NULL,         -- Unix timestamp in milliseconds

    -- Primary Key Constraint
    PRIMARY KEY (udf_id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '1');

-- Create Impala view for easy querying
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_udf_field
STORED AS KUDU
TBLPROPERTIES(
  'kudu.table_name' = 'impala::gmp_cis.cis_udf_field_kudu'
);

-- ============================================================================
-- Sample Data (Optional - for testing)
-- ============================================================================

-- Portfolio UDF Fields
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES (
    1704063600000,                      -- udf_id
    'account_group',                    -- field_name
    'Account Group',                    -- label
    'PORTFOLIO',                        -- entity_type
    true,                               -- is_required
    true,                               -- is_active
    'SYSTEM',                           -- created_by
    1704063600000,                      -- created_at
    'SYSTEM',                           -- updated_by
    1704063600000                       -- updated_at
);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES (
    1704063601000,
    'entity_group',
    'Entity Group',
    'PORTFOLIO',
    false,
    true,
    'SYSTEM',
    1704063601000,
    'SYSTEM',
    1704063601000
);

-- Trade UDF Fields
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES (
    1704063602000,
    'trade_date',
    'Trade Date',
    'TRADE',
    true,
    true,
    'SYSTEM',
    1704063602000,
    'SYSTEM',
    1704063602000
);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES (
    1704063603000,
    'broker_code',
    'Broker Code',
    'TRADE',
    false,
    true,
    'SYSTEM',
    1704063603000,
    'SYSTEM',
    1704063603000
);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES (
    1704063604000,
    'settlement_note',
    'Settlement Note',
    'TRADE',
    false,
    true,
    'SYSTEM',
    1704063604000,
    'SYSTEM',
    1704063604000
);

-- Comments UDF Fields
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES (
    1704063605000,
    'internal_notes',
    'Internal Notes',
    'COMMENTS',
    false,
    true,
    'SYSTEM',
    1704063605000,
    'SYSTEM',
    1704063605000
);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES (
    1704063606000,
    'external_remarks',
    'External Remarks',
    'COMMENTS',
    false,
    true,
    'SYSTEM',
    1704063606000,
    'SYSTEM',
    1704063606000
);

-- ============================================================================
-- Indexes (Optional - for performance)
-- ============================================================================

-- Note: Kudu doesn't support secondary indexes directly
-- Use WHERE clauses on entity_type and is_active for filtering

-- ============================================================================
-- Cleanup Old Tables (if needed)
-- ============================================================================

-- To completely drop old complex UDF tables, uncomment and run:
-- DROP TABLE IF EXISTS gmp_cis.cis_udf_definition;
-- DROP TABLE IF EXISTS gmp_cis.cis_udf_option;
-- DROP TABLE IF EXISTS gmp_cis.cis_udf_value;
