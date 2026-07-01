-- ============================================================================
-- ALTER TABLE: Add is_latest column to cis_position (gold table)
-- ============================================================================
-- Description:
--   Adds is_latest BOOLEAN to cis_position so the "current" row for each
--   logical position (portfolio + security_label + position_basis + position_date
--   + src_system) can be identified without scanning all rows.
--
--   is_latest semantics in cis_position:
--     true  — this is the authoritative row for that natural key
--     false — superseded by a later write (EOD re-run, upload re-run, etc.)
--
--   The natural key (portfolio, security_label, position_basis, position_date,
--   src_system) determines logical identity.  position_id is the Kudu primary key
--   and must be stable within the same position_date for EOD rewrites (see below).
--
-- position_id stability rules after this change:
--   INT (trade / upload):  position_id assigned at first creation, never changes
--   EOD:  position_id = same as the source INT/SOD row being repriced
--           (EOD is on the SAME position_date, so the logical position is identical)
--   SOD:  position_id = new (new position_date = new logical position)
--           CIS / GMP / AMSICEQ src_system → random (timestamp + seq)
--           USER_UPLOAD src_system          → deterministic fnv_hash of natural key
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
