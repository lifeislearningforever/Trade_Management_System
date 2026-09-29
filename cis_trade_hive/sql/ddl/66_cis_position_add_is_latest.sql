-- ============================================================================
-- ALTER TABLE: Add is_latest column to cis_position (gold table)
-- ============================================================================
-- Description:
--   Adds is_latest BOOLEAN to cis_position so the "current" row for each
--   logical position (portfolio + security_label + position_basis + position_date
--   + src_system) can be identified without scanning all rows.
--
--   is_latest semantics in cis_position:
--     true  — this is the authoritative row for this (natural_key + position_type)
--     false — superseded by a later write of the same type
--
--   SOD, INT, EOD, CORR COEXIST as separate rows on the same position_date.
--   Each position_type has its own position_id (all new rows, never overwritten
--   across types).  is_latest=true marks the current row per type.
--
-- position_id rules:
--   INT (trade):            new random per write (timestamp + uuid fragment)
--   INT (upload):           fnv_hash(portfolio|security|basis|date|src|'INT')
--                           → idempotent re-upload replaces same row
--   EOD:                    new random per EOD run (coexists with INT/SOD)
--   SOD (CIS/GMP/AMSICEQ):  new random per SOD run
--   SOD (USER_UPLOAD):      fnv_hash(portfolio|security|basis|date|src|'SOD')
--                           → idempotent re-run replaces same SOD row
--   CORR:                   new random (different month-end date)
--
-- Initialise existing rows to is_latest = true (safe: no history exists yet).
--
-- Database: gmp_cis
-- Created: 2026-07-01
-- ============================================================================

USE gmp_cis;

ALTER TABLE cis_position ADD COLUMNS (is_latest BOOLEAN);

-- Back-fill: mark every existing row as latest (no prior history).
-- In production this can be refined to mark only MAX(version_id) per natural
-- key as true and set the rest to false, but for an initial migration setting
-- all to true is safe.
UPDATE cis_position SET is_latest = true WHERE is_latest IS NULL;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
DESCRIBE cis_position;

SELECT
    position_type,
    COUNT(*)              AS total_rows,
    SUM(CASE WHEN is_latest = true  THEN 1 ELSE 0 END) AS is_latest_true,
    SUM(CASE WHEN is_latest = false THEN 1 ELSE 0 END) AS is_latest_false,
    SUM(CASE WHEN is_latest IS NULL THEN 1 ELSE 0 END) AS is_latest_null
FROM gmp_cis.cis_position
GROUP BY position_type
ORDER BY position_type;
