-- ============================================================================
-- DDL 67: Migrate RBAC tables to stable numeric IDs
-- ============================================================================
-- Problem:
--   All 5 RBAC tables use STRING primary keys. The application generates IDs
--   via epoch-ms (e.g. '1749123456789') which is numeric-as-string but:
--     1. Kudu STRING PRIMARY KEY partitions by hash of the string value, not
--        numeric order — '10' < '2' lexicographically, breaking MIN() logic
--     2. Seed DDL files used short integers ('1'..'54') which collide with
--        epoch-ms generated values if someone ever reseeds on a live table
--     3. Non-numeric IDs (e.g. 'UOBS-SG-TRADER-trade-create') are possible
--        because the column has no type constraint
--
-- Fix:
--   Step 1 — Register RBAC sequences in cis_sequence table
--             (one entry per RBAC table ID column)
--   Step 2 — Find the MAX numeric ID in each table and set sequence start
--             to MAX + 1000 (safety gap) so future IDs never collide
--   Step 3 — Identify and fix any non-numeric IDs in cis_group_permission_map
--             by reassigning them stable epoch-ms values and updating all
--             references (no FK constraints in Kudu, but group_permission_id
--             is only referenced within cis_group_permission_map itself)
--   Step 4 — Verification
--
-- After running this DDL, deploy the updated rbac_admin_repository.py which
-- uses get_next_rbac_id() instead of _id() (epoch-ms).
--
-- Run via:
--   impala-shell -i localhost:21050 -d gmp_cis \
--     -f sql/ddl/67_rbac_numeric_ids_migration.sql
-- ============================================================================


-- ============================================================================
-- STEP 1: Register RBAC sequences in cis_sequence
-- ============================================================================
-- cis_sequence is the project-wide sequence registry (see DDL 00).
-- We register one entry per RBAC table that uses an application-generated ID.
-- Starting value 10000 — well above the seed data range (1–54) and below
-- epoch-ms range (1700000000000+), so no collision with either.
-- The actual start will be overridden in Step 2 once we know the real MAX.
-- ============================================================================

UPSERT INTO gmp_cis.cis_sequence VALUES ('rbac_user_id',             10000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('rbac_group_id',            10000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('rbac_permission_id',       10000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('rbac_user_group_map_id',   10000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('rbac_group_perm_map_id',   10000, 1);


-- ============================================================================
-- STEP 2: Set sequence current_value = MAX(existing numeric ID) + 1000
-- ============================================================================
-- We cast STRING ids to BIGINT to find the numeric max.
-- Non-numeric IDs will return NULL from CAST and are excluded from MAX().
-- The +1000 safety gap means even if a few more epoch-ms IDs were inserted
-- between now and the deploy of the new code, they will not collide.
-- ============================================================================

-- cis_user_info
UPSERT INTO gmp_cis.cis_sequence (sequence_name, current_value, increment_by)
SELECT 'rbac_user_id',
       COALESCE(MAX(CAST(user_id AS BIGINT)), 10000) + 1000,
       1
FROM gmp_cis.cis_user_info
WHERE user_id REGEXP '^[0-9]+$';

-- cis_user_group_info
UPSERT INTO gmp_cis.cis_sequence (sequence_name, current_value, increment_by)
SELECT 'rbac_group_id',
       COALESCE(MAX(CAST(user_group_id AS BIGINT)), 10000) + 1000,
       1
FROM gmp_cis.cis_user_group_info
WHERE user_group_id REGEXP '^[0-9]+$';

-- cis_permission_info
UPSERT INTO gmp_cis.cis_sequence (sequence_name, current_value, increment_by)
SELECT 'rbac_permission_id',
       COALESCE(MAX(CAST(permission_id AS BIGINT)), 10000) + 1000,
       1
FROM gmp_cis.cis_permission_info
WHERE permission_id REGEXP '^[0-9]+$';

-- cis_user_group_mapping_info
UPSERT INTO gmp_cis.cis_sequence (sequence_name, current_value, increment_by)
SELECT 'rbac_user_group_map_id',
       COALESCE(MAX(CAST(user_group_mapping_id AS BIGINT)), 10000) + 1000,
       1
FROM gmp_cis.cis_user_group_mapping_info
WHERE user_group_mapping_id REGEXP '^[0-9]+$';

-- cis_group_permission_map
UPSERT INTO gmp_cis.cis_sequence (sequence_name, current_value, increment_by)
SELECT 'rbac_group_perm_map_id',
       COALESCE(MAX(CAST(group_permission_id AS BIGINT)), 10000) + 1000,
       1
FROM gmp_cis.cis_group_permission_map
WHERE group_permission_id REGEXP '^[0-9]+$';


-- ============================================================================
-- STEP 3: Fix non-numeric group_permission_ids
-- ============================================================================
-- Find all rows where group_permission_id is NOT a pure number.
-- Assign each a new stable numeric ID drawn from the sequence.
-- Since Kudu has no UPDATE, we:
--   a) UPSERT the row under the new numeric ID (is_active/is_deleted unchanged)
--   b) UPSERT the old row with is_deleted=true to retire the non-numeric key
--
-- NOTE: group_permission_id is only a PK — it is not stored as a FK anywhere
-- else in the schema, so there are no other tables to update.
-- ============================================================================

-- Preview non-numeric IDs before fixing (uncomment to inspect first):
-- SELECT group_permission_id, group_name, permission_name, entity, is_active, is_deleted
-- FROM gmp_cis.cis_group_permission_map
-- WHERE group_permission_id NOT REGEXP '^[0-9]+$'
-- ORDER BY group_name, permission_name;

-- Step 3a: Insert new rows with numeric IDs for each non-numeric row.
-- We compute a new ID as: sequence_current_value + ROW_NUMBER().
-- The sequence is then bumped in Step 3b.
CREATE TABLE IF NOT EXISTS gmp_cis.rbac_fix_nonnumeric_gpm
STORED AS KUDU
AS
SELECT
    CAST(seq.current_value + rn.rownum AS STRING)   AS new_id,
    gpm.group_permission_id                          AS old_id,
    gpm.group_name,
    gpm.permission_name,
    gpm.entity,
    gpm.mode,
    gpm.description,
    gpm.is_active,
    gpm.is_deleted,
    gpm.created_on,
    gpm.created_by,
    NOW()                                            AS updated_on,
    'MIGRATION_DDL67'                                AS updated_by
FROM gmp_cis.cis_group_permission_map gpm
CROSS JOIN (SELECT current_value FROM gmp_cis.cis_sequence WHERE sequence_name = 'rbac_group_perm_map_id') seq
JOIN (
    SELECT group_permission_id,
           ROW_NUMBER() OVER (ORDER BY group_permission_id) AS rownum
    FROM gmp_cis.cis_group_permission_map
    WHERE group_permission_id NOT REGEXP '^[0-9]+$'
) rn ON gpm.group_permission_id = rn.group_permission_id
WHERE gpm.group_permission_id NOT REGEXP '^[0-9]+$';

-- Insert rows under their new numeric IDs
UPSERT INTO gmp_cis.cis_group_permission_map
(group_permission_id, group_name, permission_name, entity,
 mode, description, is_active, is_deleted,
 created_on, created_by, updated_on, updated_by)
SELECT
    new_id,
    group_name,
    permission_name,
    entity,
    mode,
    description,
    is_active,
    is_deleted,
    created_on,
    created_by,
    updated_on,
    updated_by
FROM gmp_cis.rbac_fix_nonnumeric_gpm;

-- Retire old non-numeric rows (soft-delete + mark inactive)
UPSERT INTO gmp_cis.cis_group_permission_map
(group_permission_id, group_name, permission_name, entity,
 mode, description, is_active, is_deleted,
 created_on, created_by, updated_on, updated_by)
SELECT
    old_id,
    group_name,
    permission_name,
    entity,
    mode,
    description,
    false,                 -- is_active
    true,                  -- is_deleted
    created_on,
    created_by,
    updated_on,
    updated_by
FROM gmp_cis.rbac_fix_nonnumeric_gpm;

-- Step 3b: Advance the sequence past all newly assigned IDs
UPSERT INTO gmp_cis.cis_sequence (sequence_name, current_value, increment_by)
SELECT 'rbac_group_perm_map_id',
       COALESCE(MAX(CAST(group_permission_id AS BIGINT)), 10000) + 1,
       1
FROM gmp_cis.cis_group_permission_map
WHERE group_permission_id REGEXP '^[0-9]+$'
  AND is_deleted = false;

DROP TABLE IF EXISTS gmp_cis.rbac_fix_nonnumeric_gpm;


-- ============================================================================
-- STEP 4: Verification
-- ============================================================================

-- 1. Sequence values registered (should show 5 rbac_* rows)
SELECT sequence_name, current_value
FROM gmp_cis.cis_sequence
WHERE sequence_name LIKE 'rbac_%'
ORDER BY sequence_name;

-- 2. No non-numeric active IDs remain in cis_group_permission_map (should be 0)
SELECT COUNT(*) AS non_numeric_active
FROM gmp_cis.cis_group_permission_map
WHERE group_permission_id NOT REGEXP '^[0-9]+$'
  AND is_deleted = false;

-- 3. No non-numeric IDs in other RBAC tables (should all be 0)
SELECT 'cis_user_info'              AS tbl, COUNT(*) AS non_numeric FROM gmp_cis.cis_user_info             WHERE user_id             NOT REGEXP '^[0-9]+$'
UNION ALL
SELECT 'cis_user_group_info'        AS tbl, COUNT(*) AS non_numeric FROM gmp_cis.cis_user_group_info        WHERE user_group_id        NOT REGEXP '^[0-9]+$'
UNION ALL
SELECT 'cis_permission_info'        AS tbl, COUNT(*) AS non_numeric FROM gmp_cis.cis_permission_info        WHERE permission_id        NOT REGEXP '^[0-9]+$'
UNION ALL
SELECT 'cis_user_group_mapping_info' AS tbl, COUNT(*) AS non_numeric FROM gmp_cis.cis_user_group_mapping_info WHERE user_group_mapping_id NOT REGEXP '^[0-9]+$';

-- 4. Active permission counts per group (sanity check)
SELECT group_name, COUNT(*) AS active_permissions
FROM gmp_cis.cis_group_permission_map
WHERE is_active = true AND is_deleted = false
GROUP BY group_name
ORDER BY group_name;
