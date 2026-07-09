-- ============================================================================
-- Debug: Find and fix duplicate is_latest=true rows in cis_position
-- Run each step individually in Impala/Hue against gmp_cis database
-- ============================================================================


-- ============================================================================
-- STEP 1: Summary — duplicates for INT type, grouped by all 5 natural keys
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
    MIN(quantity)    AS min_qty,
    MAX(quantity)    AS max_qty,
    SUM(quantity)    AS total_qty
FROM gmp_cis.cis_position
WHERE position_type = 'INT'
  AND is_latest     = true
GROUP BY
    position_type,
    portfolio,
    security_label,
    position_basis,
    position_date
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, portfolio, security_label, position_date;


-- ============================================================================
-- STEP 2: Total count of duplicate groups (INT only)
-- ============================================================================
SELECT COUNT(*) AS total_duplicate_groups
FROM (
    SELECT
        position_type,
        portfolio,
        security_label,
        position_basis,
        position_date
    FROM gmp_cis.cis_position
    WHERE position_type = 'INT'
      AND is_latest     = true
    GROUP BY
        position_type,
        portfolio,
        security_label,
        position_basis,
        position_date
    HAVING COUNT(*) > 1
) dups;


-- ============================================================================
-- STEP 3: Detail — all INT duplicate rows with full column values
-- ============================================================================
SELECT
    pos.position_id,
    pos.position_type,
    pos.portfolio,
    pos.security_label,
    pos.position_basis,
    pos.position_date,
    pos.quantity,
    pos.average_cost_fc,
    pos.average_cost_lc,
    pos.cost_fc,
    pos.cost_lc,
    pos.market_value_fc,
    pos.is_latest,
    pos.trade_id,
    pos.src_system
FROM gmp_cis.cis_position pos
JOIN (
    SELECT
        position_type,
        portfolio,
        security_label,
        position_basis,
        position_date
    FROM gmp_cis.cis_position
    WHERE position_type = 'INT'
      AND is_latest     = true
    GROUP BY
        position_type,
        portfolio,
        security_label,
        position_basis,
        position_date
    HAVING COUNT(*) > 1
) dups
    ON  pos.position_type  = dups.position_type
    AND pos.portfolio      = dups.portfolio
    AND pos.security_label = dups.security_label
    AND pos.position_basis = dups.position_basis
    AND pos.position_date  = dups.position_date
WHERE pos.position_type = 'INT'
  AND pos.is_latest     = true
ORDER BY pos.portfolio, pos.security_label, pos.position_date, pos.position_basis, pos.position_id;


-- ============================================================================
-- STEP 4: Check ALL position_types (INT/SOD/EOD/CORR) for duplicates
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
-- STEP 5: Overall health check — total rows vs is_latest=true per type
-- ============================================================================
SELECT
    position_type,
    is_latest,
    COUNT(*) AS row_count,
    COUNT(DISTINCT
        CONCAT(portfolio, '|', security_label, '|', position_basis, '|', position_date)
    ) AS unique_natural_keys
FROM gmp_cis.cis_position
GROUP BY position_type, is_latest
ORDER BY position_type, is_latest;


-- ============================================================================
-- STEP 6: Fix — retire duplicate rows, keep MAX(position_id) per group
--         Covers ALL position_types in one pass.
--         Run steps in order: 6a → 6b (verify) → 6c → 6d → 6e (verify)
-- ============================================================================

-- 6a: Create temp table of position_ids to KEEP (one per natural key group)
--     Drop first in case a previous run left it behind.
DROP TABLE IF EXISTS gmp_cis.cis_position_dedup_keep;

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

-- 6b: Verify — count rows that will be retired
--     Should equal the total_duplicate_groups from STEP 2
SELECT COUNT(*) AS rows_to_retire
FROM gmp_cis.cis_position
JOIN gmp_cis.cis_position_dedup_keep
    ON gmp_cis.cis_position.position_id = gmp_cis.cis_position_dedup_keep.keep_id
    IS NOT MATCHED
WHERE gmp_cis.cis_position.is_latest = true;

-- NOTE: If the JOIN syntax above is not supported, use this alternative:
SELECT COUNT(*) AS rows_to_retire
FROM gmp_cis.cis_position pos
LEFT JOIN gmp_cis.cis_position_dedup_keep k
    ON pos.position_id = k.keep_id
WHERE pos.is_latest = true
  AND k.keep_id IS NULL;

-- 6c: Retire duplicate rows — set is_latest=false for non-keepers
--     Impala UPDATE does not support aliases or subqueries in WHERE,
--     so join to the keep table via NOT EXISTS workaround below.
UPDATE gmp_cis.cis_position
SET is_latest = false
WHERE is_latest = true
  AND position_id NOT IN (SELECT keep_id FROM gmp_cis.cis_position_dedup_keep);

-- 6d: Drop temp table
DROP TABLE IF EXISTS gmp_cis.cis_position_dedup_keep;

-- 6e: Final verify — should return 0 rows
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
