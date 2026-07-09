-- ============================================================================
-- Debug: Find duplicate is_latest=true rows in cis_position for INT type
-- Run in Impala/Hue against gmp_cis database
-- ============================================================================

-- ============================================================================
-- STEP 1: Summary — count duplicates grouped by natural key
--         Any row with duplicate_count > 1 is a problem.
-- ============================================================================
SELECT
    portfolio,
    security_label,
    position_basis,
    position_date,
    COUNT(*)         AS duplicate_count,
    MIN(position_id) AS first_position_id,
    MAX(position_id) AS last_position_id,
    MIN(quantity)    AS min_qty,
    MAX(quantity)    AS max_qty,
    SUM(quantity)    AS total_qty
FROM gmp_cis.cis_position
WHERE position_type = 'INT'
  AND is_latest     = true
GROUP BY
    portfolio,
    security_label,
    position_basis,
    position_date
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, portfolio, security_label, position_date;


-- ============================================================================
-- STEP 2: Total count of duplicate groups
-- ============================================================================
SELECT COUNT(*) AS total_duplicate_groups
FROM (
    SELECT
        portfolio,
        security_label,
        position_basis,
        position_date
    FROM gmp_cis.cis_position
    WHERE position_type = 'INT'
      AND is_latest     = true
    GROUP BY
        portfolio,
        security_label,
        position_basis,
        position_date
    HAVING COUNT(*) > 1
) dups;


-- ============================================================================
-- STEP 3: Detail — all duplicate rows with full column values
--         Shows exactly which position_ids are clashing.
-- ============================================================================
SELECT
    p.position_id,
    p.position_type,
    p.portfolio,
    p.security_label,
    p.position_basis,
    p.position_date,
    p.quantity,
    p.average_cost_fc,
    p.average_cost_lc,
    p.cost_fc,
    p.cost_lc,
    p.market_value_fc,
    p.is_latest,
    p.trade_id,
    p.src_system
FROM gmp_cis.cis_position p
WHERE p.position_type = 'INT'
  AND p.is_latest     = true
  AND (p.portfolio, p.security_label, p.position_basis, p.position_date) IN (
      SELECT portfolio, security_label, position_basis, position_date
      FROM gmp_cis.cis_position
      WHERE position_type = 'INT'
        AND is_latest     = true
      GROUP BY portfolio, security_label, position_basis, position_date
      HAVING COUNT(*) > 1
  )
ORDER BY p.portfolio, p.security_label, p.position_date, p.position_basis, p.position_id;


-- ============================================================================
-- STEP 4: Check all position_types (not just INT) for duplicates
--         Useful to see if SOD/EOD/CORR also have issues.
-- ============================================================================
SELECT
    position_type,
    portfolio,
    security_label,
    position_basis,
    position_date,
    COUNT(*)         AS duplicate_count,
    MIN(position_id) AS first_position_id,
    MAX(position_id) AS last_position_id,
    SUM(quantity)    AS total_qty
FROM gmp_cis.cis_position
WHERE is_latest = true
GROUP BY
    position_type,
    portfolio,
    security_label,
    position_basis,
    position_date
HAVING COUNT(*) > 1
ORDER BY position_type, duplicate_count DESC, portfolio, security_label, position_date;


-- ============================================================================
-- STEP 5: Overall health check — total rows vs is_latest=true rows
-- ============================================================================
SELECT
    position_type,
    is_latest,
    COUNT(*)     AS row_count,
    COUNT(DISTINCT CONCAT(portfolio, '|', security_label, '|',
                          position_basis, '|', position_date)) AS unique_keys
FROM gmp_cis.cis_position
GROUP BY position_type, is_latest
ORDER BY position_type, is_latest;


-- ============================================================================
-- STEP 6: Fix — retire older duplicate rows (keep MAX position_id per group)
--         Groups by position_type + portfolio + security_label + position_basis
--         + position_date. Covers INT, SOD, EOD, CORR all in one pass.
--
--         Only run after confirming duplicates in STEP 1 and reviewing STEP 3.
--         Impala does not support subqueries in UPDATE WHERE — use a temp table.
-- ============================================================================

-- 6a: Create temp table of position_ids to KEEP (one per natural key group)
CREATE TABLE gmp_cis.cis_position_dedup_keep
STORED AS PARQUET AS
SELECT MAX(position_id) AS keep_id
FROM gmp_cis.cis_position
WHERE is_latest = true
GROUP BY
    position_type,
    portfolio,
    security_label,
    position_basis,
    position_date;

-- 6b: Verify — count of rows that will be retired (should match Step 2 total)
SELECT COUNT(*) AS rows_to_retire
FROM gmp_cis.cis_position p
WHERE p.is_latest = true
  AND p.position_id NOT IN (SELECT keep_id FROM gmp_cis.cis_position_dedup_keep);

-- 6c: Retire duplicate rows — set is_latest=false for all except the keeper
--     Run only after confirming 6b row count looks correct.
UPDATE gmp_cis.cis_position p
SET is_latest = false
WHERE p.is_latest = true
  AND p.position_id NOT IN (SELECT keep_id FROM gmp_cis.cis_position_dedup_keep);

-- 6d: Drop temp table
DROP TABLE IF EXISTS gmp_cis.cis_position_dedup_keep;

-- 6e: Final verify — re-run Step 1 to confirm zero duplicates remain
SELECT
    position_type,
    portfolio,
    security_label,
    position_basis,
    position_date,
    COUNT(*) AS duplicate_count
FROM gmp_cis.cis_position
WHERE is_latest = true
GROUP BY
    position_type,
    portfolio,
    security_label,
    position_basis,
    position_date
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, portfolio, security_label, position_date;
