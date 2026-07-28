-- ============================================================================
-- Cleanup: Drop CIS-sourced cis_security duplicates that shadow a GMP row
-- ============================================================================
-- Background:
--   Some securities exist twice in cis_security for the same (isin,
--   country_of_exchange) key — once as src_system='GMP' (migrated,
--   authoritative) and once as src_system='CIS' (created via UI trade entry
--   or the position-upload ETL's auto-create-security step, typically
--   because the ISIN match against the existing GMP row failed at entry
--   time due to a case/whitespace mismatch — see the Step 3 ISIN-match fix
--   in upload/services/upload_service.py for one confirmed cause).
--
--   When both exist for the same (isin, country_of_exchange), the GMP row
--   is authoritative — this script drops the CIS duplicate(s) only. It
--   never touches a group that has no GMP row, and never touches the GMP
--   row itself.
--
-- Match key: UPPER(TRIM(isin)) + UPPER(TRIM(country_of_exchange))
--   Same normalisation as the Step 3 ISIN-match fix, so this cleanup and
--   that fix agree on what counts as "the same security".
--
-- Run order:
--   STEP 1 — see duplicate groups (isin+country present under both GMP and CIS)
--   STEP 2 — preview exact CIS security_id rows that will be deleted
--   STEP 3 — DELETE (run only after confirming Steps 1 & 2)
--   STEP 4 — verify zero such groups remain
--
-- Usage:
--   impala-shell -i localhost:21050 -d gmp_cis -f sql/ddl/70_cleanup_cis_security_gmp_cis_duplicates.sql
--   Or run each step manually to review before proceeding.
--
-- Database: gmp_cis
-- Created:  2026-07-28
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- STEP 1: Duplicate groups — same (isin, country_of_exchange) present under
--         BOTH src_system='GMP' and src_system='CIS'
-- ============================================================================

SELECT
    UPPER(TRIM(isin))                                     AS isin_key,
    UPPER(TRIM(COALESCE(country_of_exchange, '')))        AS country_key,
    COUNT(*)                                                AS total_rows,
    SUM(CASE WHEN src_system = 'GMP' THEN 1 ELSE 0 END)    AS gmp_rows,
    SUM(CASE WHEN src_system = 'CIS' THEN 1 ELSE 0 END)    AS cis_rows
FROM gmp_cis.cis_security
WHERE isin IS NOT NULL AND TRIM(isin) != ''
GROUP BY UPPER(TRIM(isin)), UPPER(TRIM(COALESCE(country_of_exchange, '')))
HAVING SUM(CASE WHEN src_system = 'GMP' THEN 1 ELSE 0 END) >= 1
   AND SUM(CASE WHEN src_system = 'CIS' THEN 1 ELSE 0 END) >= 1
ORDER BY total_rows DESC;


-- ============================================================================
-- STEP 2: Preview exact CIS rows that will be deleted.
--         The GMP counterpart for the same isin+country is never touched.
-- ============================================================================

SELECT s.security_id, s.security_name, s.isin, s.country_of_exchange,
       s.src_system, s.is_active, s.created_at
FROM gmp_cis.cis_security s
INNER JOIN (
    SELECT UPPER(TRIM(isin))                              AS isin_key,
           UPPER(TRIM(COALESCE(country_of_exchange, ''))) AS country_key
    FROM gmp_cis.cis_security
    WHERE isin IS NOT NULL AND TRIM(isin) != ''
    GROUP BY UPPER(TRIM(isin)), UPPER(TRIM(COALESCE(country_of_exchange, '')))
    HAVING SUM(CASE WHEN src_system = 'GMP' THEN 1 ELSE 0 END) >= 1
       AND SUM(CASE WHEN src_system = 'CIS' THEN 1 ELSE 0 END) >= 1
) dup
    ON  UPPER(TRIM(s.isin)) = dup.isin_key
    AND UPPER(TRIM(COALESCE(s.country_of_exchange, ''))) = dup.country_key
WHERE s.src_system = 'CIS'
ORDER BY s.isin, s.security_name;


-- ============================================================================
-- STEP 3: DELETE the CIS duplicates — run only after confirming Steps 1 & 2
-- ============================================================================

DELETE FROM gmp_cis.cis_security
WHERE src_system = 'CIS'
  AND isin IS NOT NULL AND TRIM(isin) != ''
  AND security_id IN (
      SELECT s.security_id
      FROM gmp_cis.cis_security s
      INNER JOIN (
          SELECT UPPER(TRIM(isin))                              AS isin_key,
                 UPPER(TRIM(COALESCE(country_of_exchange, ''))) AS country_key
          FROM gmp_cis.cis_security
          WHERE isin IS NOT NULL AND TRIM(isin) != ''
          GROUP BY UPPER(TRIM(isin)), UPPER(TRIM(COALESCE(country_of_exchange, '')))
          HAVING SUM(CASE WHEN src_system = 'GMP' THEN 1 ELSE 0 END) >= 1
             AND SUM(CASE WHEN src_system = 'CIS' THEN 1 ELSE 0 END) >= 1
      ) dup
          ON  UPPER(TRIM(s.isin)) = dup.isin_key
          AND UPPER(TRIM(COALESCE(s.country_of_exchange, ''))) = dup.country_key
      WHERE s.src_system = 'CIS'
  );


-- ============================================================================
-- STEP 4: Verify — should return no rows
-- ============================================================================

SELECT
    UPPER(TRIM(isin))                                     AS isin_key,
    UPPER(TRIM(COALESCE(country_of_exchange, '')))        AS country_key,
    COUNT(*)                                                AS total_rows,
    SUM(CASE WHEN src_system = 'GMP' THEN 1 ELSE 0 END)    AS gmp_rows,
    SUM(CASE WHEN src_system = 'CIS' THEN 1 ELSE 0 END)    AS cis_rows
FROM gmp_cis.cis_security
WHERE isin IS NOT NULL AND TRIM(isin) != ''
GROUP BY UPPER(TRIM(isin)), UPPER(TRIM(COALESCE(country_of_exchange, '')))
HAVING SUM(CASE WHEN src_system = 'GMP' THEN 1 ELSE 0 END) >= 1
   AND SUM(CASE WHEN src_system = 'CIS' THEN 1 ELSE 0 END) >= 1;
