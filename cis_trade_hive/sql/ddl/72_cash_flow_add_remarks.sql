-- DDL Migration 72: Add remarks column to cis_cash_flow
-- Purpose: Allow users to add optional notes/remarks on cash flow records
-- Run on: LOCAL, UAT, PROD
-- Date: 2026-06-23

ALTER TABLE gmp_cis.cis_cash_flow ADD COLUMNS (remarks STRING);
