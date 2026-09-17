-- Add maker-checker columns to cis_party table
-- Run: impala-shell -i localhost:21050 -f sql/ddl/cis_party_add_status_columns.sql
-- Or via Docker: docker exec -it kudu-impala impala-shell -i localhost:21050 -f /path/to/cis_party_add_status_columns.sql

USE gmp_cis;

-- Add status column for maker-checker workflow (INITIAL, MODIFIED, VALIDATED)
ALTER TABLE cis_party ADD COLUMNS (status STRING);

-- Add validated_by column to track who approved
ALTER TABLE cis_party ADD COLUMNS (validated_by STRING);

-- Add validation_comments for approval notes
ALTER TABLE cis_party ADD COLUMNS (validation_comments STRING);

-- Set default status to VALIDATED for existing records (they came from GMP, already approved)
-- Note: Kudu doesn't support UPDATE with WHERE clause directly, so we need to use UPSERT
-- For existing data, run this after adding columns:
-- This will be handled by the application - existing records will show as VALIDATED

-- Verify columns were added
DESCRIBE cis_party;

-- Show sample data
SELECT party_short_name, src_system, status, validated_by, is_active
FROM cis_party
LIMIT 5;
