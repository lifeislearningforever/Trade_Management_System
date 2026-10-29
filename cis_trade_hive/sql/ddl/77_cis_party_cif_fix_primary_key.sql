-- Migration 77: Fix cis_party_cif primary key
--
-- Bug: cis_party_cif was created with PRIMARY KEY (party_name) only.
--      GMP sends multiple CIF rows per party (one per country, e.g. SG + MY).
--      The UPSERT on a single-column PK overwrites earlier rows, so only the
--      last-ingested country survives. (e.g. 3M CO* loses SG or MY record.)
--
-- Fix: Recreate the table with PRIMARY KEY (party_name, m_label, country),
--      matching the original cis_counterparty_cif_kudu design and how the
--      repository's get_by_cif_key() queries the data.
--
-- Steps:
--   1. Create temp table with correct PK
--   2. Copy all existing data into temp
--   3. Drop old table
--   4. Create final table with correct PK
--   5. Copy data back from temp
--   6. Drop temp
--
-- Run: impala-shell -i localhost:21050 -d gmp_cis -f sql/ddl/77_cis_party_cif_fix_primary_key.sql

USE gmp_cis;

-- Step 1: Temp table with correct PK
CREATE TABLE IF NOT EXISTS cis_party_cif_tmp (
    party_name      STRING NOT NULL,
    m_label         STRING NOT NULL,
    country         STRING NOT NULL,
    isin            STRING,
    description     STRING,
    is_active       BOOLEAN,
    is_deleted      BOOLEAN,
    created_by      STRING,
    created_at      TIMESTAMP,
    updated_by      STRING,
    updated_at      TIMESTAMP,
    src_system      STRING,
    sub_system      STRING,
    data_cat        STRING,
    data_frq        STRING,
    src_id          STRING,
    processing_date STRING,
    record_type     STRING,
    PRIMARY KEY (party_name, m_label, country)
)
PARTITION BY HASH(party_name) PARTITIONS 4
STORED AS KUDU;

-- Step 2: Copy existing data to temp
INSERT INTO cis_party_cif_tmp
SELECT
    party_name,
    COALESCE(m_label, '')   AS m_label,
    COALESCE(country, '')   AS country,
    isin,
    description,
    is_active,
    is_deleted,
    created_by,
    created_at,
    updated_by,
    updated_at,
    src_system,
    sub_system,
    data_cat,
    data_frq,
    src_id,
    processing_date,
    record_type
FROM cis_party_cif;

-- Step 3: Drop old table
DROP TABLE IF EXISTS cis_party_cif;

-- Step 4: Create final table with correct PK
CREATE TABLE IF NOT EXISTS cis_party_cif (
    party_name      STRING NOT NULL,
    m_label         STRING NOT NULL,
    country         STRING NOT NULL,
    isin            STRING,
    description     STRING,
    is_active       BOOLEAN,
    is_deleted      BOOLEAN,
    created_by      STRING,
    created_at      TIMESTAMP,
    updated_by      STRING,
    updated_at      TIMESTAMP,
    src_system      STRING,
    sub_system      STRING,
    data_cat        STRING,
    data_frq        STRING,
    src_id          STRING,
    processing_date STRING,
    record_type     STRING,
    PRIMARY KEY (party_name, m_label, country)
)
PARTITION BY HASH(party_name) PARTITIONS 4
STORED AS KUDU;

-- Step 5: Copy data back from temp
INSERT INTO cis_party_cif
SELECT * FROM cis_party_cif_tmp;

-- Step 6: Drop temp
DROP TABLE IF EXISTS cis_party_cif_tmp;

-- Verify
SELECT COUNT(*) AS total_rows FROM cis_party_cif;
SELECT party_name, COUNT(*) AS cif_count FROM cis_party_cif GROUP BY party_name HAVING COUNT(*) > 1 LIMIT 20;
