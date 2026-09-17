-- ============================================================================
-- Migration 74: Add ex_date, record_date, payment_date to cis_ca_cash_flow_queue
-- ============================================================================
-- The table was created before these columns existed in the DDL.
-- Run on any environment where the table is missing these columns.
--
-- Safe to run multiple times — Kudu ALTER TABLE ADD COLUMNS is idempotent
-- if the column already exists (it will error, not corrupt data).
--
-- Run with:
--   impala-shell -i <host>:21050 -f 74_ca_queue_add_ex_record_payment_date_columns.sql
-- ============================================================================

ALTER TABLE gmp_cis.cis_ca_cash_flow_queue
    ADD COLUMNS (
        ex_date      STRING COMMENT 'Ex-dividend/ex-date (YYYY-MM-DD)',
        record_date  STRING COMMENT 'Record date (YYYY-MM-DD)',
        payment_date STRING COMMENT 'Payment/distribution date (YYYY-MM-DD)'
    );
