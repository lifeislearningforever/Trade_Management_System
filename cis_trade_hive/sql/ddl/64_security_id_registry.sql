-- ============================================================================
-- Security ID Registry
-- ============================================================================
-- Purpose:
--   Stable identity ledger that maps every security's composite natural key
--   to a permanent 12-digit numeric ID.  The registry is APPEND-ONLY: once a
--   row is written here its security_id never changes, even if cis_security is
--   fully truncated and reloaded the next day.
--
-- Problem this solves:
--   The old approach generated security_id from a millisecond timestamp at
--   insert time.  GMP ETL truncated all GMP rows daily then reinserted them,
--   so every GMP security received a brand-new ID each run.  Downstream
--   systems treated ID changes as data changes.
--
-- CRITICAL DESIGN NOTE — cross-listed securities:
--   The same ISIN can represent DIFFERENT securities on different exchanges.
--   Example: ANZ Banking Group
--     ISIN AU000000ANZ3  listed on ASX  (AUD, src Australia)
--     ISIN AU000000ANZ3  listed on NZX  (NZD, src New Zealand)
--   These are distinct instruments — different currency, price, corporate
--   actions.  Using ISIN alone as the natural key would collapse both into one
--   ID, corrupting positions.
--
--   Correct discriminator = ISIN + exchange_code
--
-- Natural key hierarchy (applied in priority order):
--   1. ISIN + exchange_code          → "ISIN_EXCH:<isin>:<exch>"   ← PRIMARY
--   2. ISIN + country_of_exchange    → "ISIN_CTY:<isin>:<country>"  if no exch
--   3. ISIN only                     → "ISIN:<isin>"                bonds/private
--   4. name + exchange_code          → "NAME_EXCH:<name>:<exch>"    no ISIN
--   5. name + country_of_exchange    → "NAME_CTY:<name>:<country>"  no ISIN/exch
--   6. name only                     → "NAME:<name>"                last resort
--
-- ID range: 100_000_000_001 – 999_999_999_999 (always exactly 12 digits)
-- Legacy timestamp IDs are 13 digits (1_700_000_000_000+) — no collision.
--
-- Database: gmp_cis
-- Created:  2026-06-02
-- Updated:  2026-06-02  — ISIN+exchange composite key (cross-listed fix)
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- 1. ID COUNTER — singleton row holding the next available 12-digit ID
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmp_cis.cis_security_id_counter (
    counter_id    BIGINT NOT NULL,    -- Always 1
    next_id       BIGINT NOT NULL,    -- Next ID to hand out
    updated_at    BIGINT NOT NULL,    -- Unix ms of last update
    PRIMARY KEY (counter_id)
)
PARTITION BY HASH (counter_id) PARTITIONS 1
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '1');

-- Seed the counter.  First ID issued = 100_000_000_001.
INSERT INTO gmp_cis.cis_security_id_counter (counter_id, next_id, updated_at)
SELECT 1, 100000000001, UNIX_TIMESTAMP() * 1000
WHERE NOT EXISTS (
    SELECT 1 FROM gmp_cis.cis_security_id_counter WHERE counter_id = 1
);


-- ============================================================================
-- 2. ID REGISTRY — permanent composite natural-key → security_id mapping
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmp_cis.cis_security_id_registry (
    -- Primary key: normalised composite natural key string.
    -- Format examples:
    --   ISIN + exchange   → "ISIN_EXCH:AU000000ANZ3:ASX"
    --   ISIN + exchange   → "ISIN_EXCH:AU000000ANZ3:NZX"   (different ID!)
    --   ISIN + country    → "ISIN_CTY:AU000000ANZ3:AU"
    --   ISIN only         → "ISIN:AU000000ANZ3"
    --   Name + exchange   → "NAME_EXCH:ANZ BANKING GROUP:ASX"
    --   Name + country    → "NAME_CTY:ANZ BANKING GROUP:AU"
    --   Name only         → "NAME:ANZ BANKING GROUP"
    natural_key         STRING NOT NULL,

    -- The stable 12-digit ID for this natural key (never changes)
    security_id         BIGINT NOT NULL,

    -- Which strategy was used
    -- ISIN_EXCH | ISIN_CTY | ISIN | NAME_EXCH | NAME_CTY | NAME
    key_type            STRING NOT NULL,

    -- Raw components stored for human readability and diagnostics
    isin                STRING,
    security_name       STRING,
    exchange_code       STRING,
    country_of_exchange STRING,

    -- 'CIS' → created by UI user; GMP ETL must never overwrite this row
    -- 'GMP' → created by GMP ETL
    src_system          STRING NOT NULL,

    -- Immutable audit
    created_by          STRING NOT NULL,
    created_at          BIGINT NOT NULL,

    PRIMARY KEY (natural_key)
)
PARTITION BY HASH (natural_key) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '3');


-- ============================================================================
-- 3. ONE-TIME MIGRATION: back-fill existing cis_security rows into the registry
--    so all current security_ids are preserved from day one.
--    Run once after DDL deployment.  All INSERTs are guarded by NOT EXISTS.
-- ============================================================================

-- Priority 1: ISIN + exchange_code  (cross-listed: ANZ AU vs ANZ NZ)
INSERT INTO gmp_cis.cis_security_id_registry
    (natural_key, security_id, key_type, isin, security_name,
     exchange_code, country_of_exchange, src_system, created_by, created_at)
SELECT
    CONCAT('ISIN_EXCH:', UPPER(TRIM(isin)), ':', UPPER(TRIM(exchange_code))) AS natural_key,
    security_id,
    'ISIN_EXCH'                         AS key_type,
    UPPER(TRIM(isin))                   AS isin,
    security_name,
    UPPER(TRIM(exchange_code))          AS exchange_code,
    country_of_exchange,
    COALESCE(src_system, 'GMP')         AS src_system,
    'MIGRATION'                         AS created_by,
    UNIX_TIMESTAMP() * 1000             AS created_at
FROM gmp_cis.cis_security
WHERE isin IS NOT NULL           AND TRIM(isin) != ''
  AND exchange_code IS NOT NULL  AND TRIM(exchange_code) != ''
  AND NOT EXISTS (
      SELECT 1 FROM gmp_cis.cis_security_id_registry r
      WHERE r.natural_key = CONCAT('ISIN_EXCH:', UPPER(TRIM(isin)), ':', UPPER(TRIM(exchange_code)))
  );


-- Priority 2: ISIN + country_of_exchange  (ISIN present, exchange_code missing)
INSERT INTO gmp_cis.cis_security_id_registry
    (natural_key, security_id, key_type, isin, security_name,
     exchange_code, country_of_exchange, src_system, created_by, created_at)
SELECT
    CONCAT('ISIN_CTY:', UPPER(TRIM(isin)), ':', UPPER(TRIM(country_of_exchange))) AS natural_key,
    security_id,
    'ISIN_CTY'                          AS key_type,
    UPPER(TRIM(isin))                   AS isin,
    security_name,
    NULL                                AS exchange_code,
    UPPER(TRIM(country_of_exchange))    AS country_of_exchange,
    COALESCE(src_system, 'GMP')         AS src_system,
    'MIGRATION'                         AS created_by,
    UNIX_TIMESTAMP() * 1000             AS created_at
FROM gmp_cis.cis_security
WHERE isin IS NOT NULL                   AND TRIM(isin) != ''
  AND (exchange_code IS NULL             OR TRIM(exchange_code) = '')
  AND country_of_exchange IS NOT NULL    AND TRIM(country_of_exchange) != ''
  AND NOT EXISTS (
      SELECT 1 FROM gmp_cis.cis_security_id_registry r
      WHERE r.natural_key = CONCAT('ISIN_CTY:', UPPER(TRIM(isin)), ':', UPPER(TRIM(country_of_exchange)))
  );


-- Priority 3: ISIN only  (no exchange or country — bonds, private placements)
INSERT INTO gmp_cis.cis_security_id_registry
    (natural_key, security_id, key_type, isin, security_name,
     exchange_code, country_of_exchange, src_system, created_by, created_at)
SELECT
    CONCAT('ISIN:', UPPER(TRIM(isin)))  AS natural_key,
    security_id,
    'ISIN'                              AS key_type,
    UPPER(TRIM(isin))                   AS isin,
    security_name,
    NULL                                AS exchange_code,
    NULL                                AS country_of_exchange,
    COALESCE(src_system, 'GMP')         AS src_system,
    'MIGRATION'                         AS created_by,
    UNIX_TIMESTAMP() * 1000             AS created_at
FROM gmp_cis.cis_security
WHERE isin IS NOT NULL              AND TRIM(isin) != ''
  AND (exchange_code IS NULL        OR TRIM(exchange_code) = '')
  AND (country_of_exchange IS NULL  OR TRIM(country_of_exchange) = '')
  AND NOT EXISTS (
      SELECT 1 FROM gmp_cis.cis_security_id_registry r
      WHERE r.natural_key = CONCAT('ISIN:', UPPER(TRIM(isin)))
  );


-- Priority 4: name + exchange_code  (no ISIN)
INSERT INTO gmp_cis.cis_security_id_registry
    (natural_key, security_id, key_type, isin, security_name,
     exchange_code, country_of_exchange, src_system, created_by, created_at)
SELECT
    CONCAT('NAME_EXCH:', UPPER(TRIM(security_name)), ':', UPPER(TRIM(exchange_code))) AS natural_key,
    security_id,
    'NAME_EXCH'                         AS key_type,
    NULL                                AS isin,
    security_name,
    UPPER(TRIM(exchange_code))          AS exchange_code,
    country_of_exchange,
    COALESCE(src_system, 'GMP')         AS src_system,
    'MIGRATION'                         AS created_by,
    UNIX_TIMESTAMP() * 1000             AS created_at
FROM gmp_cis.cis_security
WHERE (isin IS NULL OR TRIM(isin) = '')
  AND exchange_code IS NOT NULL  AND TRIM(exchange_code) != ''
  AND NOT EXISTS (
      SELECT 1 FROM gmp_cis.cis_security_id_registry r
      WHERE r.natural_key = CONCAT('NAME_EXCH:', UPPER(TRIM(security_name)), ':', UPPER(TRIM(exchange_code)))
  );


-- Priority 5: name + country_of_exchange  (no ISIN, no exchange_code)
INSERT INTO gmp_cis.cis_security_id_registry
    (natural_key, security_id, key_type, isin, security_name,
     exchange_code, country_of_exchange, src_system, created_by, created_at)
SELECT
    CONCAT('NAME_CTY:', UPPER(TRIM(security_name)), ':', UPPER(TRIM(country_of_exchange))) AS natural_key,
    security_id,
    'NAME_CTY'                          AS key_type,
    NULL                                AS isin,
    security_name,
    NULL                                AS exchange_code,
    UPPER(TRIM(country_of_exchange))    AS country_of_exchange,
    COALESCE(src_system, 'GMP')         AS src_system,
    'MIGRATION'                         AS created_by,
    UNIX_TIMESTAMP() * 1000             AS created_at
FROM gmp_cis.cis_security
WHERE (isin IS NULL OR TRIM(isin) = '')
  AND (exchange_code IS NULL OR TRIM(exchange_code) = '')
  AND country_of_exchange IS NOT NULL AND TRIM(country_of_exchange) != ''
  AND NOT EXISTS (
      SELECT 1 FROM gmp_cis.cis_security_id_registry r
      WHERE r.natural_key = CONCAT('NAME_CTY:', UPPER(TRIM(security_name)), ':', UPPER(TRIM(country_of_exchange)))
  );


-- Priority 6: name only  (absolute last resort)
INSERT INTO gmp_cis.cis_security_id_registry
    (natural_key, security_id, key_type, isin, security_name,
     exchange_code, country_of_exchange, src_system, created_by, created_at)
SELECT
    CONCAT('NAME:', UPPER(TRIM(security_name)))  AS natural_key,
    security_id,
    'NAME'                              AS key_type,
    NULL                                AS isin,
    security_name,
    NULL                                AS exchange_code,
    NULL                                AS country_of_exchange,
    COALESCE(src_system, 'GMP')         AS src_system,
    'MIGRATION'                         AS created_by,
    UNIX_TIMESTAMP() * 1000             AS created_at
FROM gmp_cis.cis_security
WHERE (isin IS NULL OR TRIM(isin) = '')
  AND (exchange_code IS NULL OR TRIM(exchange_code) = '')
  AND (country_of_exchange IS NULL OR TRIM(country_of_exchange) = '')
  AND NOT EXISTS (
      SELECT 1 FROM gmp_cis.cis_security_id_registry r
      WHERE r.natural_key = CONCAT('NAME:', UPPER(TRIM(security_name)))
  );


-- ============================================================================
-- 4. VERIFICATION
-- ============================================================================

-- Count by strategy
SELECT key_type, src_system, COUNT(*) AS cnt
FROM gmp_cis.cis_security_id_registry
GROUP BY key_type, src_system
ORDER BY key_type, src_system;

-- Sanity check: no two registry rows share the same security_id
SELECT security_id, COUNT(*) AS cnt
FROM gmp_cis.cis_security_id_registry
GROUP BY security_id
HAVING cnt > 1;

-- Confirm ID range is 12 digits
SELECT
    MIN(security_id) AS min_id,
    MAX(security_id) AS max_id,
    COUNT(*)         AS total,
    SUM(CASE WHEN LENGTH(CAST(security_id AS STRING)) != 12 THEN 1 ELSE 0 END) AS wrong_length
FROM gmp_cis.cis_security_id_registry;
