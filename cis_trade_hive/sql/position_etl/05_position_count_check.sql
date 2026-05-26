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
