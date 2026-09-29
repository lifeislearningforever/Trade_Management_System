-- ================================================================
-- Add cis-udf Group Permissions
-- The cis-udf permission exists but has no group assignments
-- ================================================================

USE cis;

-- ================================================================
-- Grant READ and WRITE access to CIS-DEV group (group_id: 1)
-- for cis-udf permission
-- ================================================================

-- READ access for viewing UDF definitions
INSERT INTO cis_group_permissions VALUES (
    32,
    1,
    'cis-udf',
    'READ',
    false,
    CAST('2025-12-24 00:00:00.000000000' AS TIMESTAMP),
    'CIS_BATCH'
);

-- WRITE access for creating/editing/deleting UDF definitions
INSERT INTO cis_group_permissions VALUES (
    33,
    1,
    'cis-udf',
    'WRITE',
    false,
    CAST('2025-12-24 00:00:00.000000000' AS TIMESTAMP),
    'CIS_BATCH'
);

-- ================================================================
-- Summary:
-- - Granted READ access to cis-udf for CIS-DEV group
-- - Granted WRITE access to cis-udf for CIS-DEV group
-- - This allows TMP3RC user to:
--   * View UDF definitions (udf_list, udf_detail)
--   * Create UDF definitions (udf_create)
--   * Edit UDF definitions (udf_edit)
--   * Delete UDF definitions (udf_delete)
--   * Manage entity UDF values (entity_udf_values)
--   * Bulk upload UDF options (udf_bulk_upload)
-- ================================================================
