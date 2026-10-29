-- ============================================================================
-- Sync GMP party / party_cif -> CIS cis_party / cis_party_cif
-- ============================================================================
-- Source: gmp_cis.gmp_cis_sta_dly_party, gmp_cis.gmp_cis_sta_dly_party_cif
--         (GMP sends a full snapshot every business date; ALL columns are
--          STRING on the GMP side per the source schema)
-- Target: gmp_cis.cis_party, gmp_cis.cis_party_cif (Kudu)
--
-- Run daily after GMP's party/party_cif files have landed for the day.
-- Idempotent: UPSERT on the Kudu primary key, safe to re-run for the same
-- processing_date.
--
-- Confirmed mappings:
--   - Boolean flags: GMP sends 'true'/'false' text; cast via LOWER(x)='true'.
--   - cis_party_cif.isin <- GMP's `cif` column (matches party_cif_repository.py's
--     actual read/write behavior today).
--   - cis_party.status is set to 'VALIDATED' for every synced row — GMP-sourced
--     records are already authoritative upstream and are read-only in CIS
--     (see can_edit_party()), so they don't go through CIS's own four-eyes flow.
--
-- Still open (flagged inline as TODO):
--   - cis_party.resident_y_n has no confirmed source column on the GMP side
--     (not visible in the schema reviewed) — left NULL below.
--   - cis_party_cif.party_name is sourced from GMP's `counterparty_cif_name`
--     — confirm this is the same value as party_short_name (the cis_party
--     join key) before relying on joins between the two synced tables.
--   - Only rows for the latest processing_date are pulled from each GMP
--     table (MAX(processing_date)) — adjust if a specific date is needed
--     (e.g. a backfill), see the variant at the bottom of this file.
--
-- Usage:
--   impala-shell -i localhost:21050 -d gmp_cis -f sql/transforms/sync_gmp_party_to_cis.sql
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- STEP 1 — cis_party  <-  gmp_cis_sta_dly_party (latest processing_date)
-- ============================================================================
-- PK: party_short_name. UPSERT replaces the whole row for that key, so a
-- party GMP no longer sends (or a soft-deleted one) is NOT automatically
-- retired here — this only inserts/updates rows GMP is actively sending.

UPSERT INTO cis_party (
    party_short_name,
    m_label,
    party_full_name,
    record_type,
    address_line_0,
    address_line_1,
    address_line_2,
    address_line_3,
    city,
    country,
    postal_code,
    fax_number,
    telex_number,
    primary_contact,
    primary_number,
    other_contact,
    other_number,
    industry,
    industry_group,
    is_broker,
    is_custodian,
    is_issuer,
    is_bank,
    is_subsidiary,
    is_corporate,
    is_financial_institute,
    is_other,
    subsidiary_level,
    party_grandparent,
    party_parent,
    resident_y_n,
    mas_industry_code,
    country_of_incorporation,
    cels_code,
    src_system,
    sub_system,
    data_cat,
    data_frq,
    src_id,
    processing_date,
    is_active,
    is_deleted,
    status,
    created_by,
    created_at,
    updated_by,
    updated_at
)
SELECT
    counterparty_short_name                                       AS party_short_name,
    m_label,
    counterparty_full_name                                        AS party_full_name,
    record_type,
    address_line0                                                 AS address_line_0,
    address_line1                                                 AS address_line_1,
    address_line2                                                 AS address_line_2,
    address_line3                                                 AS address_line_3,
    city,
    country,
    postal_code,
    fax                                                           AS fax_number,
    telex                                                         AS telex_number,
    primary_contact,
    primary_number,
    other_contact,
    other_number,
    industry,
    industry_group,
    -- GMP sends every flag as STRING ('true'/'false' or 'Y'/'N' — assume
    -- 'true'/'false' text per GMP convention; adjust the comparison below
    -- if GMP actually sends 'Y'/'N' or '1'/'0').
    CASE WHEN LOWER(is_broker)               = 'true' THEN true ELSE false END AS is_broker,
    CASE WHEN LOWER(is_custodian)            = 'true' THEN true ELSE false END AS is_custodian,
    CASE WHEN LOWER(is_issuer)               = 'true' THEN true ELSE false END AS is_issuer,
    CASE WHEN LOWER(is_bank)                 = 'true' THEN true ELSE false END AS is_bank,
    CASE WHEN LOWER(is_subsidiary)           = 'true' THEN true ELSE false END AS is_subsidiary,
    CASE WHEN LOWER(is_corporate)            = 'true' THEN true ELSE false END AS is_corporate,
    CASE WHEN LOWER(is_financial_institute)  = 'true' THEN true ELSE false END AS is_financial_institute,
    CASE WHEN LOWER(is_other)                = 'true' THEN true ELSE false END AS is_other,
    subsidiary_level,
    counterparty_grand_parent                                     AS party_grandparent,
    counterparty_parent                                           AS party_parent,
    CAST(NULL AS STRING)                                          AS resident_y_n,  -- TODO: confirm GMP source column, if any
    mas_industry_code,
    country_of_incorporation,
    cels_code,
    src_system,
    sub_system,
    data_cat,
    data_frq,
    src_id,
    processing_date,
    true                                                           AS is_active,
    false                                                          AS is_deleted,
    -- GMP-sourced records are authoritative upstream and read-only in CIS
    -- (see can_edit_party()) — treat them as already validated.
    'VALIDATED'                                                    AS status,
    'GMP_SYNC'                                                     AS created_by,
    NOW()                                                          AS created_at,
    'GMP_SYNC'                                                     AS updated_by,
    NOW()                                                          AS updated_at
FROM gmp_cis_sta_dly_party
WHERE processing_date = (
    SELECT MAX(processing_date) FROM gmp_cis_sta_dly_party
)
-- CIS-created parties (src_system='cis') must never be overwritten by the
-- GMP feed — this sync only ever touches GMP-sourced rows.
AND UPPER(src_system) = 'GMP';


-- ============================================================================
-- STEP 2 — cis_party_cif  <-  gmp_cis_sta_dly_party_cif (latest processing_date)
-- ============================================================================
-- PK: (party_name, m_label, country). UPSERT replaces the whole row for
-- that composite key.

UPSERT INTO cis_party_cif (
    party_name,
    m_label,
    country,
    isin,
    description,
    src_system,
    sub_system,
    data_cat,
    data_frq,
    src_id,
    processing_date,
    record_type,
    is_active,
    is_deleted,
    created_by,
    created_at,
    updated_by,
    updated_at
)
SELECT
    counterparty_cif_name                                         AS party_name,  -- TODO: confirm this equals party_short_name for join purposes
    m_label,
    counterparty_country                                          AS country,
    cif                                                            AS isin,
    CAST(NULL AS STRING)                                          AS description,
    src_system,
    sub_system,
    data_cat,
    data_frq,
    src_id,
    processing_date,
    record_type,
    true                                                           AS is_active,
    false                                                          AS is_deleted,
    'GMP_SYNC'                                                     AS created_by,
    NOW()                                                          AS created_at,
    'GMP_SYNC'                                                     AS updated_by,
    NOW()                                                          AS updated_at
FROM gmp_cis_sta_dly_party_cif
WHERE processing_date = (
    SELECT MAX(processing_date) FROM gmp_cis_sta_dly_party_cif
)
AND UPPER(src_system) = 'GMP';


-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT 'cis_party (GMP rows)' AS check_name, COUNT(*) AS row_count
FROM cis_party WHERE UPPER(src_system) = 'GMP'
UNION ALL
SELECT 'cis_party_cif (GMP rows)', COUNT(*)
FROM cis_party_cif WHERE UPPER(src_system) = 'GMP';

-- Spot-check a few synced rows
SELECT party_short_name, party_full_name, is_broker, is_bank, is_financial_institute,
       is_other, party_grandparent, party_parent, processing_date
FROM cis_party
WHERE UPPER(src_system) = 'GMP'
ORDER BY processing_date DESC
LIMIT 10;

-- ============================================================================
-- BACKFILL / SPECIFIC-DATE VARIANT
-- ============================================================================
-- To sync a specific processing_date instead of the latest, replace both
-- occurrences of:
--     WHERE processing_date = (SELECT MAX(processing_date) FROM ...)
-- with:
--     WHERE processing_date = '20260724'   -- YYYYMMDD, matching GMP's format
