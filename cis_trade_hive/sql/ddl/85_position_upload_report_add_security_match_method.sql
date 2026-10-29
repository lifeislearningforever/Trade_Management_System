-- DDL Migration 85: Add security_match_method to position_upload_report.
--
-- The security-matching cascade in upload/services/upload_service.py
-- (run_position_etl, Step 3+4) was rewritten to the 10-tier cascade
-- specified by Venkata Narayana Adisetty (30/07/2026 — "Change Position
-- ETL security matching logic"): Short Name, ISIN+Country, Ticker+Country,
-- Full Name(description)+Country, Normalized Full Name+Country, then the
-- same four without the country requirement, then Create Security.
--
-- security_match_method records which tier resolved the match (or 'NONE'
-- if a new security had to be created). Values: SHORT_NAME, ISIN, TICKER,
-- FULL_NAME, NORMALIZED_FULL_NAME, ISIN_ONLY, TICKER_ONLY, FULL_NAME_ONLY,
-- NORMALIZED_FULL_NAME_ONLY, NONE.
--
-- Run on server:
--   impala-shell -i <host>:21050 -f 85_position_upload_report_add_security_match_method.sql
-- ---------------------------------------------------------------------------

ALTER TABLE gmp_cis.position_upload_report
ADD COLUMNS (
    security_match_method STRING COMMENT 'Tier of the 10-tier security matching cascade that produced the match, or NONE if a new security was created'
);
