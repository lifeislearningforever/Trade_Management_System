-- ============================================================================
-- SECURITY UDF Fields for CIS Trade Hive
-- ============================================================================
-- Version: 1.0
-- Created: 2026-04-05
-- Description: UDF field definitions for SECURITY object type
--              These are the dropdown field NAMES (not values)
--              The field_value contains the display name for UI labels
--
-- IMPORTANT: The field_name column contains the lookup key used in code
--            The field_value column contains the display label shown in UI
--            This file defines the FIELD DEFINITIONS, not dropdown options
--
-- Production UDF table structure:
--   object_type = 'SECURITY'
--   field_name = Display label (e.g., 'Industry', 'Country of Incorporation')
--   field_value = Dropdown option values (populated separately)
--
-- Note: Run this after the base UDF tables are created
-- ============================================================================

-- First, delete existing SECURITY UDF field definitions
DELETE FROM gmp_cis.cis_udf_field WHERE object_type = 'SECURITY';

-- Insert SECURITY object type marker
UPSERT INTO gmp_cis.cis_udf_field VALUES
(2, 'SECURITY', 'object_type', '', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

-- ============================================================================
-- SECURITY UDF Field Definitions (25 fields matching production)
-- These define which dropdown fields exist for SECURITY object type
-- field_name = The dropdown field name (used for lookup)
-- field_value = Empty for field definitions (populated with options separately)
-- ============================================================================

-- Field definitions - these tell the system which dropdowns exist
-- The actual dropdown OPTIONS are stored separately with same field_name

UPSERT INTO gmp_cis.cis_udf_field VALUES
(300, 'SECURITY', 'Industry', 'Industry', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(301, 'SECURITY', 'Country of Incorporation', 'Country of Incorporation', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(302, 'SECURITY', 'Exchange Code', 'Exchange Code', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(303, 'SECURITY', 'Security Type', 'Security Type', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(304, 'SECURITY', 'Investment Type', 'Investment Type', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(305, 'SECURITY', 'Price Source of Issue', 'Price Source of Issue', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(306, 'SECURITY', 'Country of Issue', 'Country of Issue', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(307, 'SECURITY', 'Country of Primary Exchange', 'Country of Primary Exchange', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(308, 'SECURITY', 'BWCIIF', 'BWCIIF', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(309, 'SECURITY', 'BWCIIF Others', 'BWCIIF Others', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(310, 'SECURITY', 'Issuer Type', 'Issuer Type', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(311, 'SECURITY', 'Approved S32', 'Approved S32', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(312, 'SECURITY', 'BASEL IV - FUND', 'BASEL IV - FUND', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(313, 'SECURITY', 'Business Unit Head', 'Business Unit Head', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(314, 'SECURITY', 'Core/Non Core', 'Core/Non Core', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(315, 'SECURITY', 'Fund / Index Fund', 'Fund / Index Fund', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(316, 'SECURITY', 'Management Limit Classification', 'Management Limit Classification', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(317, 'SECURITY', 'MAS 643 Entity Type', 'MAS 643 Entity Type', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(318, 'SECURITY', 'Person In Charge', 'Person In Charge', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(319, 'SECURITY', 'Substantial >10%', 'Substantial >10%', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(320, 'SECURITY', 'PEWC', 'PEWC', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(321, 'SECURITY', 'S32 Representative', 'S32 Representative', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(322, 'SECURITY', 'Quoted/Unquoted', 'Quoted/Unquoted', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(323, 'SECURITY', 'Fin/Non-Fin IND', 'Fin/Non-Fin IND', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field VALUES
(324, 'SECURITY', 'Relative Index', 'Relative Index', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);


-- ============================================================================
-- Verification Query
-- ============================================================================
SELECT object_type, field_name, field_value, is_active
FROM gmp_cis.cis_udf_field
WHERE object_type = 'SECURITY'
  AND is_active = true
ORDER BY field_name;
