-- ============================================================================
-- Cleanup: Remove duplicate cis_security rows from migration re-runs
-- ============================================================================
-- Background:
--   Earlier migration runs used a timestamp-based security_id (_timestamp_ms()
--   + row_index), which generated a new unique PK on every run causing UPSERT
--   to behave as INSERT and creating duplicate rows per security.
--   The loader was fixed to use a deterministic hash-based security_id
--   (SHA-256 of security_name + isin) so future runs UPSERT correctly.
--
--   This script removes the older duplicate rows, keeping only the row with
--   the latest created_at per (security_name, isin) group.
--
-- Usage:
--   Run steps 1-4 in order via impala-shell:
--   impala-shell -i localhost:21050 -d gmp_cis -f sql/ddl/69_cleanup_cis_security_duplicates.sql
--
--   Or run each step manually to verify before proceeding.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- STEP 1: Check scale — how many security_name+isin groups have duplicates
-- ----------------------------------------------------------------------------
SELECT COUNT(*) AS duplicate_groups
FROM (
    SELECT security_name, isin
    FROM gmp_cis.cis_security
    GROUP BY security_name, isin
    HAVING COUNT(*) > 1
) t;

-- ----------------------------------------------------------------------------
-- STEP 2: Preview latest created_at per duplicate group (sanity check)
-- ----------------------------------------------------------------------------
SELECT security_name, isin, MAX(created_at) AS latest_created_at, COUNT(*) AS cnt
FROM gmp_cis.cis_security
GROUP BY security_name, isin
HAVING COUNT(*) > 1
ORDER BY security_name
LIMIT 20;

-- ----------------------------------------------------------------------------
-- STEP 3: Preview which rows WILL BE DELETED (older duplicates)
--         Review this output before running Step 4.
-- ----------------------------------------------------------------------------
SELECT s.security_id, s.security_name, s.isin, s.created_at
FROM gmp_cis.cis_security s
JOIN (
    SELECT security_name, isin, MAX(created_at) AS latest_created_at
    FROM gmp_cis.cis_security
    GROUP BY security_name, isin
    HAVING COUNT(*) > 1
) dupes
    ON  s.security_name = dupes.security_name
    AND (s.isin = dupes.isin OR (s.isin IS NULL AND dupes.isin IS NULL))
WHERE s.created_at < dupes.latest_created_at
ORDER BY s.security_name, s.created_at;

-- ----------------------------------------------------------------------------
-- STEP 4: Delete the older duplicate rows — keeps the most recently created
--         row per (security_name, isin) group.
-- ----------------------------------------------------------------------------
DELETE s
FROM gmp_cis.cis_security s
JOIN (
    SELECT security_name, isin, MAX(created_at) AS latest_created_at
    FROM gmp_cis.cis_security
    GROUP BY security_name, isin
    HAVING COUNT(*) > 1
) dupes
    ON  s.security_name = dupes.security_name
    AND (s.isin = dupes.isin OR (s.isin IS NULL AND dupes.isin IS NULL))
WHERE s.created_at < dupes.latest_created_at;

-- ----------------------------------------------------------------------------
-- STEP 5: Verify — should return 0 rows if cleanup was successful
-- ----------------------------------------------------------------------------
SELECT security_name, isin, COUNT(*) AS cnt
FROM gmp_cis.cis_security
GROUP BY security_name, isin
HAVING COUNT(*) > 1;

-- ----------------------------------------------------------------------------
-- STEP 6: Final row count after cleanup
-- ----------------------------------------------------------------------------
SELECT COUNT(*) AS total_securities
FROM gmp_cis.cis_security;
