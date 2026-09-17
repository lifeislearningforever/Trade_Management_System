-- Debug: find special character corruption in all relevant tables
-- Run on server:
--   impala-shell -i <host>:21050 -d gmp_cis -f sql/debug/debug_special_char_check.sql
-- ---------------------------------------------------------------------------

-- ── 1. cis_position — security_label with any single quotes ─────────────────
SELECT DISTINCT security_label, src_system, position_type
FROM gmp_cis.cis_position
WHERE security_label LIKE "%'%"
ORDER BY security_label
LIMIT 20;

-- ── 2. cis_position — security_label with doubled quotes specifically ────────
SELECT DISTINCT security_label, src_system, position_type
FROM gmp_cis.cis_position
WHERE security_label LIKE "%''%"
LIMIT 20;

-- ── 3. cis_security — security_name with any single quotes ──────────────────
SELECT DISTINCT security_name, is_active
FROM gmp_cis.cis_security
WHERE security_name LIKE "%'%"
ORDER BY security_name
LIMIT 20;

-- ── 4. cis_security — security_name with doubled quotes ─────────────────────
SELECT DISTINCT security_name
FROM gmp_cis.cis_security
WHERE security_name LIKE "%''%"
LIMIT 20;

-- ── 5. Check the exact failing security in cis_position ─────────────────────
SELECT security_label, src_system, position_type, position_date, is_latest
FROM gmp_cis.cis_position
WHERE UPPER(security_label) LIKE '%YUHE%'
   OR UPPER(security_label) LIKE '%MOODY%'
   OR UPPER(security_label) LIKE '%INTL%L%'
LIMIT 20;

-- ── 6. Check the exact failing security in cis_security ─────────────────────
SELECT security_name, security_label, is_active
FROM gmp_cis.cis_security
WHERE UPPER(security_name) LIKE '%YUHE%'
   OR UPPER(security_name) LIKE '%MOODY%'
LIMIT 20;

-- ── 7. Check source upload table for the bad value ───────────────────────────
SELECT DISTINCT security_full_name, security_short_name
FROM gmp_cis.gmp_cis_sta_dly_cis_position_upload
WHERE UPPER(security_full_name) LIKE '%YUHE%'
   OR UPPER(security_short_name) LIKE '%YUHE%'
LIMIT 10;
