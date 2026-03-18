-- ============================================================================
-- Corporate Action UDF Field Data
-- Database: gmp_cis
--
-- This script inserts UDF field definitions for Corporate Action Types
-- Used by the corporate action dropdown service
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- Corporate Action Type UDF Field Definition
-- ============================================================================

-- First, create the field definition record (field_value is empty for definitions)
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', '', '',
    'Type of corporate action event',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- ============================================================================
-- Corporate Action Type Values
-- ============================================================================

-- DIVIDEND
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'DIVIDEND', 'Dividend',
    'Cash or stock dividend payment to shareholders',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- STOCK_SPLIT
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'STOCK_SPLIT', 'Stock Split',
    'Forward stock split increasing shares outstanding',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- REVERSE_SPLIT
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'REVERSE_SPLIT', 'Reverse Split',
    'Reverse stock split reducing shares outstanding',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- BONUS_ISSUE
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'BONUS_ISSUE', 'Bonus Issue',
    'Free shares issued to existing shareholders',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- RIGHTS_ISSUE
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'RIGHTS_ISSUE', 'Rights Issue',
    'Offer to existing shareholders to purchase additional shares',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- MERGER
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'MERGER', 'Merger',
    'Combination of two companies into one',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- ACQUISITION
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'ACQUISITION', 'Acquisition',
    'Purchase of one company by another',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- SPIN_OFF
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'SPIN_OFF', 'Spin Off',
    'Distribution of subsidiary shares to existing shareholders',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- CAPITAL_DISTRIBUTION
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'CAPITAL_DISTRIBUTION', 'Capital Distribution',
    'Return of capital to shareholders',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- CAPITAL_REDUCTION
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'CAPITAL_REDUCTION', 'Capital Reduction',
    'Reduction of company share capital',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- TENDER_OFFER
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'TENDER_OFFER', 'Tender Offer',
    'Offer to purchase shares at specified price',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- SHARE_BUYBACK
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'SHARE_BUYBACK', 'Share Buyback',
    'Company repurchasing its own shares',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- NAME_CHANGE
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'NAME_CHANGE', 'Name Change',
    'Change of company or security name',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- DELISTING
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'DELISTING', 'Delisting',
    'Removal of security from exchange listing',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- CONSOLIDATION
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'CONSOLIDATION', 'Consolidation',
    'Share consolidation reducing number of shares',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);

-- OTHER
UPSERT INTO cis_udf_field (
    object_type, field_name, field_value, label, description,
    is_active, created_by, created_at, updated_by, updated_at
) VALUES (
    'CORPORATE_ACTION', 'Corporate Action Type', 'OTHER', 'Other',
    'Other corporate action types not listed',
    true, 'SYSTEM', UNIX_TIMESTAMP() * 1000, 'SYSTEM', UNIX_TIMESTAMP() * 1000
);


-- ============================================================================
-- Verification Query
-- ============================================================================

-- Verify inserted data
-- SELECT field_value, label, description
-- FROM cis_udf_field
-- WHERE object_type = 'CORPORATE_ACTION'
--   AND field_name = 'Corporate Action Type'
--   AND field_value IS NOT NULL
--   AND field_value != ''
-- ORDER BY field_value;
