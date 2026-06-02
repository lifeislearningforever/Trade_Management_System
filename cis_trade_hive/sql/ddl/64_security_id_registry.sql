-- ============================================================================
-- Security ID Registry
-- ============================================================================
-- Purpose:
--   Stable identity ledger that maps every security's natural key to a
--   permanent 12-digit numeric ID.  The registry is APPEND-ONLY: once a row
--   is written here, its security_id never changes — even if cis_security_kudu
--   is fully truncated and reloaded the next day.
--
-- Problem this solves:
--   The old approach generated security_id from a millisecond timestamp at
--   insert time.  GMP ETL truncates all GMP rows daily then reinserts them,
--   causing every GMP security to get a brand-new ID each run.  Downstream
--   systems treat ID changes as data changes.
--
-- Design:
--   Natural key hierarchy (applied in priority order):
--     1. isin            — globally unique, preferred
--     2. security_name + exchange_code  — for unlisted/OTC without ISIN
--     3. security_name alone            — last resort
--
--   ID range: 100_000_000_000 – 999_999_999_999 (12 digits, always)
--   Legacy timestamp IDs are 13 digits (1_700_000_000_000+), so no collision.
--
--   The natural_key column stores the normalised lookup string that was used
--   to allocate this ID so future lookups are O(1) on the PK.
--
-- Database: gmp_cis
-- Created:  2026-06-02
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- 1. ID COUNTER — single-row table that holds the next available ID
--    We use a Kudu UPSERT (singleton row, id=1) to increment atomically.
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmp_cis.cis_security_id_counter (
    counter_id    BIGINT NOT NULL,    -- Always 1 (singleton row)
    next_id       BIGINT NOT NULL,    -- Next 12-digit ID to hand out
    updated_at    BIGINT NOT NULL,    -- Unix ms of last update
    PRIMARY KEY (counter_id)
)
PARTITION BY HASH (counter_id) PARTITIONS 1
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '1');

-- Seed the counter.  Start at 100_000_000_001 so the first ID issued is
-- 100_000_000_001 (12 digits).
INSERT INTO gmp_cis.cis_security_id_counter (counter_id, next_id, updated_at)
SELECT 1, 100000000001, UNIX_TIMESTAMP() * 1000
WHERE NOT EXISTS (
    SELECT 1 FROM gmp_cis.cis_security_id_counter WHERE counter_id = 1
);


-- ============================================================================
-- 2. ID REGISTRY — the permanent natural-key → security_id mapping
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmp_cis.cis_security_id_registry (
    -- Primary key: the normalised natural key string
    -- Format examples:
    --   ISIN present          → "ISIN:US0231351067"
    --   Name + exchange       → "NAME_EXCH:APPLE INC:NASDAQ"
    --   Name only             → "NAME:APPLE INC"
    natural_key     STRING NOT NULL,

    -- The stable 12-digit ID assigned to this natural key (never changes)
    security_id     BIGINT NOT NULL,

    -- Which natural key strategy was used (ISIN / NAME_EXCH / NAME)
    key_type        STRING NOT NULL,

    -- Raw components (for human readability / debugging)
    isin            STRING,
    security_name   STRING,
    exchange_code   STRING,

    -- Which system originally created this entry
    -- 'CIS'  → created by a user in CIS; GMP ETL must never overwrite
    -- 'GMP'  → created by GMP ETL
    src_system      STRING NOT NULL,

    -- Immutable audit fields
    created_by      STRING NOT NULL,
    created_at      BIGINT NOT NULL,   -- Unix ms

    PRIMARY KEY (natural_key)
)
PARTITION BY HASH (natural_key) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '3');


-- ============================================================================
-- 3. MIGRATE EXISTING RECORDS
--    Back-fill the registry from what is already in cis_security_kudu so that
--    all existing security_ids are preserved.
--
--    Run once after DDL deployment; idempotent (INSERT only if not exists).
-- ============================================================================

-- Back-fill for securities that have an ISIN
INSERT INTO gmp_cis.cis_security_id_registry
    (natural_key, security_id, key_type, isin, security_name, exchange_code,
     src_system, created_by, created_at)
SELECT
    CONCAT('ISIN:', UPPER(TRIM(isin)))          AS natural_key,
    security_id,
    'ISIN'                                       AS key_type,
    UPPER(TRIM(isin))                            AS isin,
    security_name,
    exchange_code,
    COALESCE(src_system, 'GMP')                  AS src_system,
    'MIGRATION'                                  AS created_by,
    UNIX_TIMESTAMP() * 1000                      AS created_at
FROM gmp_cis.cis_security_kudu
WHERE isin IS NOT NULL
  AND TRIM(isin) != ''
  AND NOT EXISTS (
      SELECT 1 FROM gmp_cis.cis_security_id_registry r
      WHERE r.natural_key = CONCAT('ISIN:', UPPER(TRIM(isin)))
  );

-- Back-fill for securities without ISIN (use name + exchange)
INSERT INTO gmp_cis.cis_security_id_registry
    (natural_key, security_id, key_type, isin, security_name, exchange_code,
     src_system, created_by, created_at)
SELECT
    CONCAT('NAME_EXCH:', UPPER(TRIM(security_name)), ':', COALESCE(UPPER(TRIM(exchange_code)), '')) AS natural_key,
    security_id,
    'NAME_EXCH'                                  AS key_type,
    NULL                                         AS isin,
    security_name,
    exchange_code,
    COALESCE(src_system, 'GMP')                  AS src_system,
    'MIGRATION'                                  AS created_by,
    UNIX_TIMESTAMP() * 1000                      AS created_at
FROM gmp_cis.cis_security_kudu
WHERE (isin IS NULL OR TRIM(isin) = '')
  AND security_name IS NOT NULL
  AND exchange_code IS NOT NULL
  AND TRIM(exchange_code) != ''
  AND NOT EXISTS (
      SELECT 1 FROM gmp_cis.cis_security_id_registry r
      WHERE r.natural_key = CONCAT('NAME_EXCH:', UPPER(TRIM(security_name)), ':', UPPER(TRIM(exchange_code)))
  );

-- Back-fill for securities without ISIN or exchange (name only — last resort)
INSERT INTO gmp_cis.cis_security_id_registry
    (natural_key, security_id, key_type, isin, security_name, exchange_code,
     src_system, created_by, created_at)
SELECT
    CONCAT('NAME:', UPPER(TRIM(security_name)))  AS natural_key,
    security_id,
    'NAME'                                       AS key_type,
    NULL                                         AS isin,
    security_name,
    NULL                                         AS exchange_code,
    COALESCE(src_system, 'GMP')                  AS src_system,
    'MIGRATION'                                  AS created_by,
    UNIX_TIMESTAMP() * 1000                      AS created_at
FROM gmp_cis.cis_security_kudu
WHERE (isin IS NULL OR TRIM(isin) = '')
  AND (exchange_code IS NULL OR TRIM(exchange_code) = '')
  AND security_name IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM gmp_cis.cis_security_id_registry r
      WHERE r.natural_key = CONCAT('NAME:', UPPER(TRIM(security_name)))
  );


-- ============================================================================
-- 4. VERIFICATION
-- ============================================================================

SELECT key_type, src_system, COUNT(*) AS cnt
FROM gmp_cis.cis_security_id_registry
GROUP BY key_type, src_system
ORDER BY key_type, src_system;

SELECT MIN(security_id) AS min_id, MAX(security_id) AS max_id,
       COUNT(*) AS total
FROM gmp_cis.cis_security_id_registry;
