-- Add required columns to cis_portfolio table for close/reactivate functionality
-- Database: gmp_cis
--
-- Required columns:
-- - code (STRING) - Portfolio unique code
-- - is_active (BOOLEAN) - For soft delete
-- - updated_by (STRING) - Track who made changes
--
-- Usage:
--   1. First check if table exists and what columns it has:
--      impala-shell -q "DESCRIBE gmp_cis.cis_portfolio"
--
--   2. If columns are missing, run this script:
--      impala-shell -f 02_alter_portfolio_add_columns.sql
--

USE gmp_cis;

-- Check current table structure
DESCRIBE cis_portfolio;

-- Note: Kudu ALTER TABLE has limitations
-- - Cannot add nullable columns to existing data easily
-- - Best approach: Create new table with updated schema and migrate data

-- Option 1: If 'code' column doesn't exist and you're using 'name' as primary key
-- You can add additional columns with ALTER TABLE (for nullable columns)
-- ALTER TABLE cis_portfolio ADD COLUMNS (
--   is_active BOOLEAN,
--   updated_by STRING
-- );

-- Option 2: If you need to add 'code' or change primary key
-- You must create a new table and migrate data

-- Check if we need code column (if name is being used as code, this is optional)
-- Check if is_active exists
-- Check if updated_by exists

-- UNCOMMENT BELOW if is_active and updated_by columns don't exist:
-- ALTER TABLE cis_portfolio ADD COLUMNS (
--   is_active BOOLEAN,
--   updated_by STRING
-- );

-- Verify changes
DESCRIBE cis_portfolio;

SELECT 'Check table structure above. Uncomment ALTER TABLE if needed' as instructions;
