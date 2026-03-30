-- CIS Party Tables DDL (Renamed from cis_counterparty_kudu and cis_counterparty_cif_kudu)
-- Run: impala-shell -i localhost:21050 -f sql/ddl/cis_party_kudu.sql

USE gmp_cis;

-- Drop existing tables if they exist
DROP TABLE IF EXISTS cis_party_cif;
DROP TABLE IF EXISTS cis_party;

-- ============================================================================
-- CIS_PARTY - Main Party Table (formerly cis_counterparty_kudu)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cis_party (
    party_short_name STRING NOT NULL,
    m_label STRING,
    party_full_name STRING,
    record_type STRING,
    address_line_0 STRING,
    address_line_1 STRING,
    address_line_2 STRING,
    address_line_3 STRING,
    city STRING,
    country STRING,
    postal_code STRING,
    fax_number STRING,
    telex_number STRING,
    primary_contact STRING,
    primary_number STRING,
    other_contact STRING,
    other_number STRING,
    industry STRING,
    industry_group STRING,
    is_broker BOOLEAN,
    is_custodian BOOLEAN,
    is_issuer BOOLEAN,
    is_bank BOOLEAN,
    is_subsidiary BOOLEAN,
    is_corporate BOOLEAN,
    subsidiary_level STRING,
    party_grandparent STRING,
    party_parent STRING,
    resident_y_n STRING,
    mas_industry_code STRING,
    country_of_incorporation STRING,
    gics_code STRING,
    src_system STRING,
    sub_system STRING,
    data_cat STRING,
    data_frq STRING,
    src_id STRING,
    processing_date STRING,
    -- Maker-checker workflow columns
    status STRING,                  -- INITIAL, MODIFIED, VALIDATED
    validated_by STRING,            -- User who approved/validated
    validation_comments STRING,     -- Approval notes
    -- Standard audit columns
    is_active BOOLEAN,
    is_deleted BOOLEAN,
    created_by STRING,
    created_at TIMESTAMP,
    updated_by STRING,
    updated_at TIMESTAMP,
    PRIMARY KEY (party_short_name)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU;

-- ============================================================================
-- CIS_PARTY_CIF - Party CIF Table (formerly cis_counterparty_cif_kudu)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cis_party_cif (
    party_name STRING NOT NULL,
    m_label STRING,
    country STRING,
    isin STRING,
    description STRING,
    is_active BOOLEAN,
    is_deleted BOOLEAN,
    created_by STRING,
    created_at TIMESTAMP,
    updated_by STRING,
    updated_at TIMESTAMP,
    src_system STRING,
    sub_system STRING,
    data_cat STRING,
    data_frq STRING,
    src_id STRING,
    processing_date STRING,
    record_type STRING,
    PRIMARY KEY (party_name)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU;

-- ============================================================================
-- MIGRATION: Copy data from old tables to new tables
-- ============================================================================

-- Migrate counterparty data to party
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
    subsidiary_level,
    party_grandparent,
    party_parent,
    resident_y_n,
    mas_industry_code,
    country_of_incorporation,
    gics_code,
    src_system,
    sub_system,
    data_cat,
    data_frq,
    src_id,
    processing_date,
    is_active,
    is_deleted,
    created_by,
    created_at,
    updated_by,
    updated_at
)
SELECT
    counterparty_short_name as party_short_name,
    m_label,
    counterparty_full_name as party_full_name,
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
    subsidiary_level,
    counterparty_grandparent as party_grandparent,
    counterparty_parent as party_parent,
    resident_y_n,
    mas_industry_code,
    country_of_incorporation,
    CAST(NULL AS STRING) as gics_code,
    src_system,
    sub_system,
    data_cat,
    data_frq,
    src_id,
    processing_date,
    is_active,
    is_deleted,
    created_by,
    created_at,
    updated_by,
    updated_at
FROM cis_counterparty_kudu;

-- Migrate CIF data to party_cif
UPSERT INTO cis_party_cif (
    party_name,
    m_label,
    country,
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
)
SELECT
    counterparty_short_name as party_name,
    m_label,
    country,
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
FROM cis_counterparty_cif_kudu;

-- Show row counts
SELECT 'cis_party' as table_name, COUNT(*) as row_count FROM cis_party
UNION ALL
SELECT 'cis_party_cif' as table_name, COUNT(*) as row_count FROM cis_party_cif;
