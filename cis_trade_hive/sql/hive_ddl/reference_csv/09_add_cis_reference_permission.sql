-- ================================================================
-- Add cis-reference Permission for Reference Data Module
-- This permission covers: Country, Calendar, Counterparty
-- (Currency has its own permission: cis-currency)
-- ================================================================

USE cis;

-- ================================================================
-- Add cis-reference permission to cis_permission table
-- ================================================================
INSERT INTO cis_permission VALUES (
    8,
    'cis-reference',
    'Permission for reference data (Country, Calendar, Counterparty)',
    false,
    CAST('2025-12-24 00:00:00.000000000' AS TIMESTAMP),
    'CIS_BATCH'
);

-- ================================================================
-- Grant READ access to CIS-DEV group (group_id: 1) for TMP3RC user
-- ================================================================
INSERT INTO cis_group_permissions VALUES (
    31,
    1,
    'cis-reference',
    'READ',
    false,
    CAST('2025-12-24 00:00:00.000000000' AS TIMESTAMP),
    'CIS_BATCH'
);

-- ================================================================
-- Summary:
-- - Added cis-reference permission (id: 8)
-- - Granted READ access to CIS-DEV group (group_id: 1)
-- - This allows TMP3RC user to access:
--   * Country list (/reference-data/country/)
--   * Calendar list (/reference-data/calendar/)
--   * Counterparty list (/reference-data/counterparty/)
-- ================================================================
