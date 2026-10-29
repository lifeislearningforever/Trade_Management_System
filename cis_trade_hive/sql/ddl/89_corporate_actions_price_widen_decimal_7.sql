-- ============================================================================
-- DDL 89: Widen cis_corporate_actions.price from DECIMAL(20,6) to DECIMAL(20,7)
--
-- Context: edge_jobs_py36/sync_gmp_corporate_actions.py parses the GMP source
-- price/rate field into a Decimal with no rounding (parse_gmp_price() keeps
-- full source precision). The Kudu column was declared DECIMAL(20,6), so the
-- 7th decimal digit was silently rounded off on every UPSERT.
--
-- Kudu does not support ALTER COLUMN to change a DECIMAL's precision/scale
-- in place -- its physical on-disk width is fixed at column creation. This
-- follows the same create-new/copy/rename pattern already used in
-- sql/ddl/56_standardise_timestamp_columns.sql.
--
-- Run against each environment (SIT/UAT/prod) that already has data.
-- ============================================================================

USE gmp_cis;

-- Step 1: create the widened table alongside the existing one.
CREATE TABLE IF NOT EXISTS cis_corporate_actions_new (
    ca_id BIGINT COMMENT 'Corporate Action ID - Primary Key (timestamp-based)',
    ca_number STRING COMMENT 'Corporate Action Number (format: CA-YYYYMMDD-XXXXX)',
    ca_type STRING COMMENT 'Corporate Action Type (from UDF: DIVIDEND, STOCK_SPLIT, etc.)',
    security_name STRING COMMENT 'Security label/name from cis_security (comma-separated for multiple)',
    announcement_date STRING COMMENT 'Announcement/Declaration Date (YYYY-MM-DD)',
    ex_date STRING COMMENT 'Ex-Dividend/Ex-Date (YYYY-MM-DD)',
    record_date STRING COMMENT 'Record Date (YYYY-MM-DD)',
    payment_date STRING COMMENT 'Payment/Distribution Date (YYYY-MM-DD)',
    effective_date STRING COMMENT 'Effective Date (YYYY-MM-DD)',
    subscription_start_date STRING COMMENT 'Subscription Start Date (YYYY-MM-DD)',
    subscription_end_date STRING COMMENT 'Subscription End Date (YYYY-MM-DD)',
    price DECIMAL(20, 7) COMMENT 'Price/Rate/Ratio for the corporate action',
    currency STRING COMMENT 'Currency code (e.g., USD, SGD)',
    src_system STRING COMMENT 'Source System: CIS for manual entry, GMP for imported',
    status STRING COMMENT 'Workflow Status: INITIAL, MODIFIED, VALIDATED, REJECTED',
    submitted_for_approval_at STRING COMMENT 'Timestamp when submitted for approval',
    reviewed_by STRING COMMENT 'Username of reviewer',
    reviewed_at STRING COMMENT 'Timestamp of review',
    reviewed_comments STRING COMMENT 'Review comments',
    is_deleted BOOLEAN COMMENT 'Soft delete flag (true = deleted)',
    is_active BOOLEAN COMMENT 'Active flag (true = active)',
    cash_flow_queued BOOLEAN COMMENT 'True when a queue entry has been created for this CA',
    ca_processed     BOOLEAN COMMENT 'True when the CA queue job completed — cash flows were generated',
    ca_processed_at  STRING  COMMENT 'Timestamp when CA processing completed (YYYY-MM-DD HH:MM:SS)',
    created_by STRING COMMENT 'Username who created the record',
    created_at BIGINT COMMENT 'Creation timestamp (epoch milliseconds)',
    updated_by STRING COMMENT 'Username who last updated the record',
    updated_at BIGINT COMMENT 'Last update timestamp (epoch milliseconds)',
    PRIMARY KEY (ca_id)
)
PARTITION BY HASH (ca_id) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.num_tablet_replicas' = '1'
);

-- Step 2: copy existing data across. CAST widens the stored value without
-- rounding (existing rows only ever had up to 6 decimal digits anyway).
INSERT INTO cis_corporate_actions_new
SELECT
    ca_id, ca_number, ca_type, security_name,
    announcement_date, ex_date, record_date, payment_date, effective_date,
    subscription_start_date, subscription_end_date,
    CAST(price AS DECIMAL(20, 7)),
    currency, src_system, status,
    submitted_for_approval_at, reviewed_by, reviewed_at, reviewed_comments,
    is_deleted, is_active,
    cash_flow_queued, ca_processed, ca_processed_at,
    created_by, created_at, updated_by, updated_at
FROM cis_corporate_actions;

-- Step 3: verify row counts and a few known rows match before swapping.
-- SELECT COUNT(*) FROM cis_corporate_actions;
-- SELECT COUNT(*) FROM cis_corporate_actions_new;
-- SELECT ca_id, ca_number, price FROM cis_corporate_actions_new ORDER BY updated_at DESC LIMIT 10;

-- Step 4 (manual, after verifying Step 3): swap the tables.
-- ALTER TABLE cis_corporate_actions     RENAME TO cis_corporate_actions_bak;
-- ALTER TABLE cis_corporate_actions_new RENAME TO cis_corporate_actions;
-- DROP TABLE cis_corporate_actions_bak;   -- run after smoke-testing CA sync + cash flow processing
