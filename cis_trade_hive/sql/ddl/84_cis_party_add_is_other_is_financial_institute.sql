-- Migration 84: Add is_other and is_financial_institute classification flags to cis_party
--
-- These two boolean classification columns are used alongside the existing
-- is_bank / is_broker / is_custodian / is_issuer / is_corporate / is_subsidiary
-- flags on the Party form, detail, list, and CSV export.
--
-- Run: impala-shell -i localhost:21050 -d gmp_cis -f sql/ddl/84_cis_party_add_is_other_is_financial_institute.sql

USE gmp_cis;

ALTER TABLE cis_party ADD COLUMNS (
    is_other BOOLEAN,
    is_financial_institute BOOLEAN
);
