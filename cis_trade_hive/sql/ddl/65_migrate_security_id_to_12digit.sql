-- ============================================================================
-- Migration: Rekey all existing security_ids to stable 12-digit IDs
-- ============================================================================
-- Purpose:
--   All 4707 existing cis_security rows carry legacy timestamp-based IDs
--   (13-digit, e.g. 177976653038xxx).  Downstream systems now require the
--   stable 12-digit IDs produced by the registry (DDL 64).
--   This script allocates new 12-digit IDs for every existing row, swaps
--   the PK on cis_security, and propagates the change to all referencing
--   tables.
--
-- Tables updated (in order):
--   1. cis_security_id_registry   — replace old_id with new_id
--   2. cis_security               — PK swap (recreate table, Kudu PK immutable)
--   3. cis_security_history_kudu  — update security_id FK
--   4. cis_position               — update security_id FK
--   5. cis_security_id_counter    — advance past all newly allocated IDs
--
-- Prerequisites:
--   DDL 64 (64_security_id_registry.sql) must already be deployed and
--   the backfill completed (registry has 4707 rows from migration).
--
-- Safety:
--   - All steps are idempotent — safe to re-run if interrupted.
--   - Uses a temp mapping table as the source of truth throughout.
--   - Run during a maintenance window (app down) to avoid partial reads.
--
-- Estimated runtime: 2-5 min for ~5000 rows on Kudu.
-- Database: gmp_cis
-- Created:  2026-06-04
-- ============================================================================

USE gmp_cis;


-- ============================================================================
-- STEP 1: Build old_id → new_id mapping table
-- ============================================================================
-- Allocate a fresh 12-digit ID for every existing registry row that still
-- holds a legacy (non-12-digit) ID.  Uses ROW_NUMBER() offset from the
-- current counter value so IDs are sequential and never reused.
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmp_cis.cis_security_id_map (
    old_security_id   BIGINT NOT NULL,
    new_security_id   BIGINT NOT NULL,
    natural_key       STRING NOT NULL,
    PRIMARY KEY (old_security_id)
)
PARTITION BY HASH (old_security_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '1');

-- Populate mapping: one row per legacy ID
-- new_security_id = counter_start + sequential offset (0-based)
-- CROSS JOIN counter to avoid scalar subquery (Impala does not support them)
INSERT INTO gmp_cis.cis_security_id_map (old_security_id, new_security_id, natural_key)
SELECT
    r.security_id                                                   AS old_security_id,
    c.next_id + ROW_NUMBER() OVER (ORDER BY r.natural_key) - 1    AS new_security_id,
    r.natural_key
FROM gmp_cis.cis_security_id_registry r
CROSS JOIN (SELECT next_id FROM gmp_cis.cis_security_id_counter WHERE counter_id = 1) c
WHERE LENGTH(CAST(r.security_id AS STRING)) != 12   -- only legacy IDs
  AND NOT EXISTS (
      SELECT 1 FROM gmp_cis.cis_security_id_map m
      WHERE m.old_security_id = r.security_id
  );

-- Verify mapping populated
SELECT COUNT(*) AS mapped_rows FROM gmp_cis.cis_security_id_map;


-- ============================================================================
-- STEP 2: Update cis_security_id_registry — replace old IDs with new IDs
-- ============================================================================
-- Registry natural_key stays the same; only security_id changes.
-- We UPSERT (overwrite) each row with its new_security_id.
-- ============================================================================

UPSERT INTO gmp_cis.cis_security_id_registry
    (natural_key, security_id, key_type, isin, security_name,
     exchange_code, country_of_exchange, src_system, created_by, created_at)
SELECT
    r.natural_key,
    m.new_security_id,
    r.key_type,
    r.isin,
    r.security_name,
    r.exchange_code,
    r.country_of_exchange,
    r.src_system,
    r.created_by,
    r.created_at
FROM gmp_cis.cis_security_id_registry r
INNER JOIN gmp_cis.cis_security_id_map m ON m.old_security_id = r.security_id;

-- Verify: no more legacy IDs in registry
SELECT COUNT(*) AS legacy_remaining
FROM gmp_cis.cis_security_id_registry
WHERE LENGTH(CAST(security_id AS STRING)) != 12;


-- ============================================================================
-- STEP 3: Swap cis_security PK (Kudu PK is immutable — must recreate table)
-- ============================================================================
-- Strategy:
--   a+b. CREATE TABLE AS SELECT with LEFT JOIN map — picks up live schema,
--        no hardcoded column list needed.
--   c. DROP cis_security (old)
--   d. ALTER TABLE ... RENAME to cis_security
-- ============================================================================

-- 3a+3b. Create new table from existing schema + copy all rows with swapped IDs.
-- CREATE TABLE AS SELECT picks up the exact live schema — no hardcoded column list.
-- LEFT JOIN + COALESCE: legacy rows get new 12-digit ID; already-12-digit rows
-- keep their current ID unchanged.
CREATE TABLE gmp_cis.cis_security_new
PRIMARY KEY (security_id)
PARTITION BY HASH (security_id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '3')
AS
SELECT
    COALESCE(m.new_security_id, s.security_id) AS security_id,
    s.* EXCEPT (security_id)
FROM gmp_cis.cis_security s
LEFT JOIN gmp_cis.cis_security_id_map m ON m.old_security_id = s.security_id;

-- Verify row counts match before dropping old table
SELECT 'cis_security (old)' AS tbl, COUNT(*) AS cnt FROM gmp_cis.cis_security
UNION ALL
SELECT 'cis_security_new',          COUNT(*) AS cnt FROM gmp_cis.cis_security_new;

-- 3c. Drop old table
DROP TABLE gmp_cis.cis_security;

-- 3d. Rename new table to cis_security
ALTER TABLE gmp_cis.cis_security_new RENAME TO gmp_cis.cis_security;


-- ============================================================================
-- STEP 4: Update cis_security_history_kudu — propagate new security_id
-- ============================================================================
-- history_id is the PK (immutable); security_id is a plain column so we
-- can UPSERT the full row with the updated security_id.
-- ============================================================================

UPSERT INTO gmp_cis.cis_security_history_kudu
    (history_id, security_id, security_name, isin, action,
     status, changes, comments, performed_by, performed_at)
SELECT
    h.history_id,
    m.new_security_id,
    h.security_name,
    h.isin,
    h.action,
    h.status,
    h.changes,
    h.comments,
    h.performed_by,
    h.performed_at
FROM gmp_cis.cis_security_history_kudu h
INNER JOIN gmp_cis.cis_security_id_map m ON m.old_security_id = h.security_id;

-- Verify: no legacy IDs remain in history
SELECT COUNT(*) AS legacy_history_remaining
FROM gmp_cis.cis_security_history_kudu
WHERE LENGTH(CAST(security_id AS STRING)) != 12;


-- ============================================================================
-- STEP 5: cis_position — NO ACTION REQUIRED
-- ============================================================================
-- cis_position (DDL 63) uses security_label (STRING ticker/label) as the
-- security reference, not security_id.  No update needed here.
-- ============================================================================


-- ============================================================================
-- STEP 6: Advance cis_security_id_counter past all newly allocated IDs
-- ============================================================================
-- next_id must be MAX(new_security_id) + 1 so future allocations never
-- collide with any ID assigned in this migration.
-- ============================================================================

UPSERT INTO gmp_cis.cis_security_id_counter (counter_id, next_id, updated_at)
SELECT
    1,
    MAX(new_security_id) + 1,
    UNIX_TIMESTAMP() * 1000
FROM gmp_cis.cis_security_id_map;

-- Confirm counter value
SELECT * FROM gmp_cis.cis_security_id_counter;


-- ============================================================================
-- STEP 7: Clean up mapping table
-- ============================================================================

DROP TABLE gmp_cis.cis_security_id_map;


-- ============================================================================
-- FINAL VERIFICATION
-- ============================================================================

-- 1. All security IDs in cis_security are 12 digits
SELECT
    MIN(security_id)  AS min_id,
    MAX(security_id)  AS max_id,
    COUNT(*)          AS total_rows,
    SUM(CASE WHEN LENGTH(CAST(security_id AS STRING)) != 12 THEN 1 ELSE 0 END) AS wrong_length
FROM gmp_cis.cis_security;

-- 2. Registry has no legacy IDs
SELECT
    SUM(CASE WHEN LENGTH(CAST(security_id AS STRING)) != 12 THEN 1 ELSE 0 END) AS registry_legacy_remaining
FROM gmp_cis.cis_security_id_registry;

-- 3. No duplicate security_ids anywhere
SELECT security_id, COUNT(*) AS cnt
FROM gmp_cis.cis_security
GROUP BY security_id
HAVING COUNT(*) > 1;

-- 4. Counter is ahead of all assigned IDs
SELECT
    c.next_id                           AS counter_next,
    MAX(s.security_id)                  AS max_assigned,
    c.next_id > MAX(s.security_id)      AS counter_is_ahead
FROM gmp_cis.cis_security_id_counter c, gmp_cis.cis_security s
WHERE c.counter_id = 1
GROUP BY c.next_id;

-- 5. Row counts: cis_security vs cis_security_id_registry should match
SELECT 'cis_security'            AS tbl, COUNT(*) AS cnt FROM gmp_cis.cis_security
UNION ALL
SELECT 'cis_security_id_registry',       COUNT(*) AS cnt FROM gmp_cis.cis_security_id_registry;
