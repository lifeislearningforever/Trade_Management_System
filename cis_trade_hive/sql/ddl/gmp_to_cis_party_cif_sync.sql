-- GMP → CIS Party CIF Sync Query
--
-- Syncs gmp_cis_sta_dly_party_cif into cis_party_cif.
--
-- Bug fixed: original query used ROW_NUMBER() OVER (PARTITION BY cif ...)
-- which collapsed multiple country rows for the same party into one.
-- e.g. "3M CO*" has both SG (m_label=4343) and MY (m_label=4349) in GMP
-- but only one was landing in cis_party_cif because PARTITION BY cif
-- treated them as duplicates.
--
-- Fix: PARTITION BY (counterparty_cif_name, cif, counterparty_cif_country)
-- so each (party, CIF number, country) combination is kept independently.
-- This matches the cis_party_cif PRIMARY KEY (party_name, m_label, country).
--
-- Run: impala-shell -i <host>:21050 -d gmp_cis -f gmp_to_cis_party_cif_sync.sql

USE gmp_cis;

INSERT INTO cis_party_cif (
    party_name,
    m_label,
    country,
    description,
    record_type,
    is_active,
    is_deleted,
    src_system,
    sub_system,
    data_cat,
    data_frq,
    src_id,
    processing_date,
    created_by,
    created_at,
    updated_by,
    updated_at
)
SELECT
    counterparty_cif_name                          AS party_name,
    CAST(cif AS STRING)                            AS m_label,
    counterparty_cif_country                       AS country,
    'Loaded from GMP BAU feed'                     AS description,
    record_type,
    TRUE                                           AS is_active,
    FALSE                                          AS is_deleted,
    'GMP'                                          AS src_system,
    'GMP LOAD'                                     AS sub_system,
    'GMP'                                          AS data_cat,
    'dly'                                          AS data_frq,
    'gmp_cis_sta_dly_party_cif'                    AS src_id,
    processing_date,
    'GMP LOAD'                                     AS created_by,
    FROM_UNIXTIME(UNIX_TIMESTAMP())                AS created_at,
    'GMP LOAD'                                     AS updated_by,
    FROM_UNIXTIME(UNIX_TIMESTAMP())                AS updated_at
FROM (
    SELECT
        counterparty_cif_name,
        cif,
        counterparty_cif_country                   AS counterparty_cif_country,
        record_type,
        sub_system,
        data_frq,
        data_cat,
        processing_date,
        -- FIXED: partition by (party_name, cif, country) so each country variant
        -- for the same party is treated as a distinct record, not a duplicate.
        -- Old: PARTITION BY cif  → dropped SG or MY row for 3M CO* etc.
        -- New: PARTITION BY counterparty_cif_name, cif, counterparty_cif_country
        ROW_NUMBER() OVER (
            PARTITION BY counterparty_cif_name, cif, counterparty_cif_country
            ORDER BY processing_date DESC
        ) AS rn
    FROM gmp_cis_sta_dly_party_cif
    WHERE processing_date = '20260227'    -- replace with target processing_date
      AND upper(src_system) = 'GMP'
) t
WHERE rn = 1;
