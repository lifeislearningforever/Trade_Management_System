-- ============================================================================
-- Position Count Diagnostic — staging vs report table
-- Use this to diagnose row count mismatches per processing_date.
--
-- Usage (Impala shell):
--   impala-shell -i <host>:21050 -d gmp_cis -f 05_position_count_check.sql
--
-- Usage (Beeline):
--   beeline -u "jdbc:hive2://localhost:10000" -n user -p password \
--     -f 05_position_count_check.sql
-- ============================================================================


-- 1. Count per processing_date in the staging (source) table
SELECT processing_date, COUNT(*) AS row_count
FROM gmp_cis.cis_user_sta_adhoc_position_5
GROUP BY processing_date
ORDER BY processing_date DESC;


-- 2. Count per processing_date in the standardised (report) table
SELECT processing_date, source_table, COUNT(*) AS row_count
FROM gmp_cis.position_upload_standardized
WHERE source_table = 'cis_user_sta_adhoc_position_5'
GROUP BY processing_date, source_table
ORDER BY processing_date DESC;


-- 3. Side-by-side comparison — staging vs report for each processing_date
SELECT
    s.processing_date,
    s.staging_count,
    r.report_count
FROM (
    SELECT processing_date, COUNT(*) AS staging_count
    FROM gmp_cis.cis_user_sta_adhoc_position_5
    GROUP BY processing_date
) s
LEFT JOIN (
    SELECT processing_date, COUNT(*) AS report_count
    FROM gmp_cis.position_upload_standardized
    WHERE source_table = 'cis_user_sta_adhoc_position_5'
    GROUP BY processing_date
) r ON s.processing_date = r.processing_date
ORDER BY s.processing_date DESC;


-- 4. Count in cis_position by source_table for a given processing_date
--    Replace '20260526' with the actual processing_date you are investigating.
SELECT src_system, source_table, COUNT(*) AS row_count
FROM gmp_cis.cis_position
WHERE processing_date = '20260526'
GROUP BY src_system, source_table
ORDER BY row_count DESC;


-- 5. Break down UI position list count by source — matches what the UI shows
--    (UI queries cis_position filtered by position_date range, not processing_date)
--    Replace date range with the range visible in the UI filter.
SELECT src_system, source_table, COUNT(*) AS row_count
FROM gmp_cis.cis_position
WHERE position_date BETWEEN '2026-04-26' AND '2026-05-26'
GROUP BY src_system, source_table
ORDER BY row_count DESC;
