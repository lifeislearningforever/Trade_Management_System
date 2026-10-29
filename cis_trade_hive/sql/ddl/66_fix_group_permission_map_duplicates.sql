-- ============================================================================
-- DDL 66: Fix cis_group_permission_map duplicate rows
-- ============================================================================
-- Problem:
--   The old save_group_permissions() generated a new group_permission_id
--   (epoch-ms) on every save, even when the same (group_name, permission_name,
--   entity) was being reassigned.  Over time this left multiple rows per
--   logical permission:
--
--     id=111  SG-TRADER  trade-create  is_active=false  is_deleted=false  ← deactivated
--     id=222  SG-TRADER  trade-create  is_active=false  is_deleted=true   ← soft-deleted
--     id=333  SG-TRADER  trade-create  is_active=true   is_deleted=false  ← current (active)
--
--   The ACL read query (acl_repository_v2.py) filters:
--       AND is_active = true AND is_deleted = false
--   so duplicates are invisible to permission checks, but they:
--     - Bloat the table
--     - Corrupt the admin UI (shows duplicate rows)
--     - Cause confusion: is_active=false/is_deleted=false rows look "neither
--       active nor deleted" — an invalid state
--
-- Fix:
--   Step 1  — Mark invalid-state rows (is_active=false AND is_deleted=false)
--             as soft-deleted so there are no more rows in the limbo state.
--   Step 2  — For each (group_name, permission_name, entity) combination that
--             has more than one active row (is_active=true, is_deleted=false),
--             keep the row with the lowest group_permission_id and soft-delete
--             the rest.
--   Step 3  — Verification queries.
--
-- Run via:
--   impala-shell -i localhost:21050 -f sql/ddl/66_fix_group_permission_map_duplicates.sql
-- ============================================================================


-- ============================================================================
-- STEP 1: Fix limbo rows (is_active=false AND is_deleted=false)
-- ============================================================================
-- These rows have been deactivated but never soft-deleted.
-- Mark them deleted so they are fully excluded from all queries.
-- Safe to re-run: UPSERT is idempotent.
-- ============================================================================

-- Preview what will be fixed (run this SELECT before the UPSERT to verify)
-- SELECT group_permission_id, group_name, permission_name, entity, is_active, is_deleted
-- FROM gmp_cis.cis_group_permission_map
-- WHERE is_active = false AND is_deleted = false
-- ORDER BY group_name, permission_name;

CREATE TABLE IF NOT EXISTS gmp_cis.cis_group_permission_map_fix_limbo
STORED AS KUDU
AS
SELECT
    group_permission_id,
    group_name,
    permission_name,
    entity,
    mode,
    description,
    false   AS is_active,
    true    AS is_deleted,
    created_on,
    created_by,
    NOW()   AS updated_on,
    'MIGRATION_DDL66' AS updated_by
FROM gmp_cis.cis_group_permission_map
WHERE is_active = false
  AND is_deleted = false;

-- Apply the fix: mark limbo rows as deleted
UPSERT INTO gmp_cis.cis_group_permission_map
(group_permission_id, group_name, permission_name, entity,
 mode, description, is_active, is_deleted,
 created_on, created_by, updated_on, updated_by)
SELECT
    group_permission_id,
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
FROM gmp_cis.cis_group_permission_map_fix_limbo;

DROP TABLE IF EXISTS gmp_cis.cis_group_permission_map_fix_limbo;


-- ============================================================================
-- STEP 2: Deduplicate active rows
-- ============================================================================
-- Keep the row with the lowest group_permission_id per
-- (group_name, permission_name, entity).
-- Soft-delete all other active rows for the same logical key.
-- ============================================================================

-- Preview duplicates (run this SELECT before the UPSERT to verify)
-- SELECT group_name, permission_name, entity, COUNT(*) as cnt
-- FROM gmp_cis.cis_group_permission_map
-- WHERE is_active = true AND is_deleted = false
-- GROUP BY group_name, permission_name, entity
-- HAVING COUNT(*) > 1
-- ORDER BY group_name, permission_name;

-- Build set of rows to soft-delete:
--   active rows whose group_permission_id is NOT the minimum for that key.

CREATE TABLE IF NOT EXISTS gmp_cis.cis_group_permission_map_fix_dupes
STORED AS KUDU
AS
SELECT
    gpm.group_permission_id,
    gpm.group_name,
    gpm.permission_name,
    gpm.entity,
    gpm.mode,
    gpm.description,
    false   AS is_active,
    true    AS is_deleted,
    gpm.created_on,
    gpm.created_by,
    NOW()   AS updated_on,
    'MIGRATION_DDL66' AS updated_by
FROM gmp_cis.cis_group_permission_map gpm
JOIN (
    SELECT group_name, permission_name, entity, MIN(group_permission_id) AS keep_id
    FROM gmp_cis.cis_group_permission_map
    WHERE is_active = true
      AND is_deleted = false
    GROUP BY group_name, permission_name, entity
    HAVING COUNT(*) > 1
) keeper
    ON  gpm.group_name      = keeper.group_name
    AND gpm.permission_name = keeper.permission_name
    AND gpm.entity          = keeper.entity
    AND gpm.group_permission_id != keeper.keep_id
WHERE gpm.is_active = true
  AND gpm.is_deleted = false;

-- Apply: soft-delete the duplicate active rows
UPSERT INTO gmp_cis.cis_group_permission_map
(group_permission_id, group_name, permission_name, entity,
 mode, description, is_active, is_deleted,
 created_on, created_by, updated_on, updated_by)
SELECT
    group_permission_id,
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
FROM gmp_cis.cis_group_permission_map_fix_dupes;

DROP TABLE IF EXISTS gmp_cis.cis_group_permission_map_fix_dupes;


-- ============================================================================
-- STEP 3: Verification
-- ============================================================================

-- 1. No more limbo rows (should return 0)
SELECT COUNT(*) AS limbo_rows
FROM gmp_cis.cis_group_permission_map
WHERE is_active = false AND is_deleted = false;

-- 2. No more duplicate active rows (should return 0 rows)
SELECT group_name, permission_name, entity, COUNT(*) AS cnt
FROM gmp_cis.cis_group_permission_map
WHERE is_active = true AND is_deleted = false
GROUP BY group_name, permission_name, entity
HAVING COUNT(*) > 1
ORDER BY group_name, permission_name;

-- 3. Count of clean active permissions per group
SELECT group_name, COUNT(*) AS active_permissions
FROM gmp_cis.cis_group_permission_map
WHERE is_active = true AND is_deleted = false
GROUP BY group_name
ORDER BY group_name;

-- 4. Full active permission list (matches what ACL service sees)
SELECT group_name, permission_name, mode, entity
FROM gmp_cis.cis_group_permission_map
WHERE is_active = true AND is_deleted = false
ORDER BY group_name, permission_name;
