-- ============================================================================
-- Cleanup: Drop CIS-sourced cis_security duplicates that shadow a GMP row
--          (and any positions booked against the duplicate's security_label)
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
--   The CIS duplicate is usually auto-created with its OWN security_name
--   (e.g. an abbreviated form of the raw upload name), not the GMP row's
--   name — so any position already booked against it in cis_trade_position /
--   cis_position is keyed by that distinct security_label and would be
--   orphaned (referencing a security_name with no cis_security row at all)
--   if only the master row were deleted. This script drops those positions
--   first, then the CIS security master row.
--
--   Scope is positions only (cis_trade_position, cis_position) — cis_trade
--   itself (the underlying trade records) is intentionally NOT touched here;
--   that's actual transactional history and a separate, bigger decision.
--
-- Match key: UPPER(TRIM(isin)) + UPPER(TRIM(country_of_exchange))
--   Same normalisation as the Step 3 ISIN-match fix, so this cleanup and
--   that fix agree on what counts as "the same security".
--
-- Run order:
--   STEP 1 — see duplicate groups (isin+country present under both GMP and CIS)
--   STEP 2 — preview exact CIS security rows that will be deleted
--   STEP 3 — preview cis_trade_position rows for those CIS security_labels
--   STEP 4 — preview cis_position rows for those CIS security_labels
--   STEP 5 — DELETE cis_trade_position rows (run only after confirming 1-4)
--   STEP 6 — DELETE cis_position rows
--   STEP 7 — DELETE the cis_security CIS duplicate rows
--   STEP 8 — verify zero duplicate groups and zero orphaned positions remain
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
-- STEP 3: Preview cis_trade_position rows keyed by the CIS duplicate's
--         security_label (security_name) — these will be deleted in Step 5.
-- ============================================================================

SELECT tp.position_id, tp.portfolio_short_name, tp.security_label,
       tp.position_basis, tp.position_date, tp.quantity, tp.is_latest
FROM gmp_cis.cis_trade_position tp
WHERE tp.security_label IN (
    SELECT s.security_name
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
)
ORDER BY tp.security_label, tp.position_date;


-- ============================================================================
-- STEP 4: Preview cis_position rows keyed by the CIS duplicate's
--         security_label — these will be deleted in Step 6.
-- ============================================================================

SELECT p.position_id, p.portfolio, p.security_label,
       p.position_basis, p.position_date, p.quantity, p.is_latest
FROM gmp_cis.cis_position p
WHERE p.security_label IN (
    SELECT s.security_name
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
)
ORDER BY p.security_label, p.position_date;


-- ============================================================================
-- STEP 5: DELETE cis_trade_position rows — run only after confirming 1-4
-- ============================================================================

DELETE FROM gmp_cis.cis_trade_position
WHERE security_label IN (
    SELECT s.security_name
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
-- STEP 6: DELETE cis_position rows
-- ============================================================================

DELETE FROM gmp_cis.cis_position
WHERE security_label IN (
    SELECT s.security_name
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
-- STEP 7: DELETE the CIS security duplicates themselves
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
-- STEP 8: Verify — both queries should return no rows
-- ============================================================================

-- No more GMP+CIS duplicate groups
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

-- No orphaned positions left referencing a security_name with no cis_security row
SELECT tp.security_label, COUNT(*) AS orphaned_rows
FROM gmp_cis.cis_trade_position tp
LEFT JOIN gmp_cis.cis_security s ON s.security_name = tp.security_label
WHERE s.security_id IS NULL
GROUP BY tp.security_label;
