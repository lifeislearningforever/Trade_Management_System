-- ============================================================================
-- Remove duplicate rows from cis_position
-- ============================================================================
-- Business key: portfolio + security_label + position_basis +
--               position_date + src_system
--
-- Keep rule: highest position_id per group (most recently written = current)
--
-- Run order:
--   STEP 1 — see duplicates and count
--   STEP 2 — preview exact position_ids to be deleted
--   STEP 3 — DELETE (run only after confirming Steps 1 & 2)
--   STEP 4 — verify zero duplicates remain
--
-- Database: gmp_cis
-- Created:  2026-06-03
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- STEP 1: See duplicate groups and how many extra rows exist
-- ============================================================================

-- Duplicate groups with row counts
SELECT
    portfolio,
    security_label,
    position_basis,
    position_date,
    src_system,
    COUNT(*)          AS row_count,
    MIN(position_id)  AS oldest_id,
    MAX(position_id)  AS keep_id
FROM gmp_cis.cis_position
GROUP BY
    portfolio, security_label, position_basis, position_date, src_system
HAVING COUNT(*) > 1
ORDER BY row_count DESC, portfolio, security_label;

-- Total rows vs unique business keys (shows how many rows will be removed)
SELECT
    COUNT(*)                                                           AS total_rows,
    COUNT(DISTINCT CONCAT(
        COALESCE(portfolio,      ''), '|',
        COALESCE(security_label, ''), '|',
        COALESCE(position_basis, ''), '|',
        COALESCE(position_date,  ''), '|',
        COALESCE(src_system,     '')
    ))                                                                 AS unique_keys,
    COUNT(*) - COUNT(DISTINCT CONCAT(
        COALESCE(portfolio,      ''), '|',
        COALESCE(security_label, ''), '|',
        COALESCE(position_basis, ''), '|',
        COALESCE(position_date,  ''), '|',
        COALESCE(src_system,     '')
    ))                                                                 AS duplicate_rows_to_remove
FROM gmp_cis.cis_position;


-- ============================================================================
-- STEP 2: Preview exact position_ids that will be deleted
--         (everything except the MAX position_id per business-key group)
-- ============================================================================

SELECT p.position_id
FROM gmp_cis.cis_position p
INNER JOIN (
    SELECT
        portfolio,
        security_label,
        position_basis,
        position_date,
        src_system,
        MAX(position_id) AS keep_id
    FROM gmp_cis.cis_position
    GROUP BY portfolio, security_label, position_basis, position_date, src_system
    HAVING COUNT(*) > 1
) keepers
    ON  COALESCE(p.portfolio,      '') = COALESCE(keepers.portfolio,      '')
    AND COALESCE(p.security_label, '') = COALESCE(keepers.security_label, '')
    AND COALESCE(p.position_basis, '') = COALESCE(keepers.position_basis, '')
    AND COALESCE(p.position_date,  '') = COALESCE(keepers.position_date,  '')
    AND COALESCE(p.src_system,     '') = COALESCE(keepers.src_system,     '')
    AND p.position_id != keepers.keep_id
ORDER BY p.position_id;


-- ============================================================================
-- STEP 3: DELETE duplicates — run after confirming Steps 1 & 2
-- ============================================================================

DELETE FROM gmp_cis.cis_position
WHERE position_id IN (
    SELECT p.position_id
    FROM gmp_cis.cis_position p
    INNER JOIN (
        SELECT
            portfolio,
            security_label,
            position_basis,
            position_date,
            src_system,
            MAX(position_id) AS keep_id
        FROM gmp_cis.cis_position
        GROUP BY portfolio, security_label, position_basis, position_date, src_system
        HAVING COUNT(*) > 1
    ) keepers
        ON  COALESCE(p.portfolio,      '') = COALESCE(keepers.portfolio,      '')
        AND COALESCE(p.security_label, '') = COALESCE(keepers.security_label, '')
        AND COALESCE(p.position_basis, '') = COALESCE(keepers.position_basis, '')
        AND COALESCE(p.position_date,  '') = COALESCE(keepers.position_date,  '')
        AND COALESCE(p.src_system,     '') = COALESCE(keepers.src_system,     '')
        AND p.position_id != keepers.keep_id
);


-- ============================================================================
-- STEP 4: Verify — should return no rows
-- ============================================================================

SELECT
    portfolio,
    security_label,
    position_basis,
    position_date,
    src_system,
    COUNT(*) AS row_count
FROM gmp_cis.cis_position
GROUP BY portfolio, security_label, position_basis, position_date, src_system
HAVING COUNT(*) > 1;
