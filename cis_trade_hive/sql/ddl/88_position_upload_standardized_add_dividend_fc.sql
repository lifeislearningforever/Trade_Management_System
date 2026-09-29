-- ============================================================================
-- Add dividend_fc to position_upload_standardized
-- ============================================================================
-- Description:
--   GMP's daily position source (gmp_cis_sta_dly_position) added a new
--   m_dividend_fc column (accumulated dividend, foreign/security currency).
--   position_upload_standardized needs a matching column so the ETL
--   (sql/pyspark/eod_ams_position_etl.py) can carry it through to
--   cis_position.dividend_fc, which already exists (see
--   sql/ddl/18_cis_position_column_rename.sql onwards) but was always
--   hardcoded to 0 on every UPSERT since no source ever supplied a real
--   value.
--
-- IMPORTANT: position_upload_standardized is written to by POSITIONAL
--   (no explicit column list) INSERT OVERWRITE statements in BOTH
--   sql/pyspark/eod_ams_position_etl.py (5 standardize blocks) and
--   upload/services/upload_service.py (5 SQL STANDARDIZE_SELECT blocks,
--   one per format, plus two special Python VALUES-row builders for
--   Formats 4 and 5). ALTER TABLE ADD COLUMNS appends this as the new
--   LAST non-partition column -- every one of those INSERT sites was
--   updated in the same change as this DDL to supply a value (NULL,
--   except the real m_dividend_fc value for GMP's own block) as its own
--   new last column, or the next run of any of them will fail with a
--   column-count mismatch.
--
-- dividend_lc (per SA requirement, same change): cis_position.dividend_lc
--   is computed at UPSERT time in eod_ams_position_etl.py's Step 7A as
--   dividend_fc * latest FX spot rate (gmp_cis_sta_dly_fx_rates,
--   ref_quot_ccy='FC-LC', spot_rate_d) as of the row's own reporting_date
--   -- NOT stored as its own column here, since it's derived, matching
--   how multicurrency_service._lookup_rate() already resolves FX
--   elsewhere in the app.
--
-- Database: gmp_cis
-- Date: 2026-08-11
-- ============================================================================

ALTER TABLE gmp_cis.position_upload_standardized
    ADD COLUMNS (dividend_fc DECIMAL(30,8) COMMENT 'Accumulated dividend, foreign/security currency -- from GMP m_dividend_fc; NULL for all other sources');

-- Verification
DESCRIBE gmp_cis.position_upload_standardized;
