-- ================================================================
-- Insert UDF Definition for Desk Head Dropdown
-- Database: gmp_cis
-- Date: 2026-02-27
-- Description: Creates "Head of Desk" UDF field definition for Portfolio
-- ================================================================

USE gmp_cis;

-- ================================================================
-- Insert field DEFINITION (field_value is empty for definitions)
-- ================================================================
INSERT INTO cis_udf_field (udf_id, object_type, field_name, field_value, is_active, created_at, created_by)
VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 1 AS BIGINT),
    'PORTFOLIO',
    'Head of Desk',
    '',
    true,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM'
);

-- ================================================================
-- Insert sample field VALUES (these are the dropdown options)
-- Add more desk head names as needed
-- ================================================================
INSERT INTO cis_udf_field (udf_id, object_type, field_name, field_value, is_active, created_at, created_by)
VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 2 AS BIGINT),
    'PORTFOLIO',
    'Head of Desk',
    'John Smith',
    true,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM'
);

INSERT INTO cis_udf_field (udf_id, object_type, field_name, field_value, is_active, created_at, created_by)
VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 3 AS BIGINT),
    'PORTFOLIO',
    'Head of Desk',
    'Jane Doe',
    true,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM'
);

INSERT INTO cis_udf_field (udf_id, object_type, field_name, field_value, is_active, created_at, created_by)
VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 4 AS BIGINT),
    'PORTFOLIO',
    'Head of Desk',
    'Michael Wong',
    true,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM'
);

-- ================================================================
-- Verify inserted values
-- ================================================================
SELECT udf_id, field_name, field_value, is_active
FROM cis_udf_field
WHERE object_type = 'PORTFOLIO'
  AND field_name = 'Head of Desk'
ORDER BY field_value;
