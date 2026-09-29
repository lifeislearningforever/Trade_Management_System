-- ============================================================================
-- CIS Counterparty CIF Table (Version 2 - with country in primary key)
-- ============================================================================
-- Description: Stores Customer Identification Numbers (CIFs) for counterparties
--              Supports multiple CIFs per counterparty across different countries
-- Primary Key: (counterparty_short_name, m_label, country)
-- Constraint: One CIF per country per counterparty
-- ============================================================================

-- Drop existing table if it exists
DROP TABLE IF EXISTS cis_counterparty_cif_kudu;

-- Create new table with updated schema
CREATE TABLE cis_counterparty_cif_kudu (
    -- Primary Key Fields
    counterparty_short_name STRING NOT NULL COMMENT 'Counterparty short name (FK to cis_counterparty_kudu)',
    m_label STRING NOT NULL COMMENT 'CIF number',
    country STRING NOT NULL COMMENT 'Country code (constraint: one CIF per country)',

    -- CIF Details
    isin STRING COMMENT 'ISIN code',
    description STRING COMMENT 'CIF description',

    -- Status Flags
    is_active BOOLEAN DEFAULT TRUE COMMENT 'Active status',
    is_deleted BOOLEAN DEFAULT FALSE COMMENT 'Soft delete flag',

    -- Audit Fields
    created_by STRING COMMENT 'User who created the record',
    created_at TIMESTAMP DEFAULT now() COMMENT 'Creation timestamp',
    updated_by STRING COMMENT 'User who last updated the record',
    updated_at TIMESTAMP DEFAULT now() COMMENT 'Last update timestamp',

    -- Metadata
    src_system STRING DEFAULT 'CIS_TRADE_HIVE' COMMENT 'Source system',
    sub_system STRING COMMENT 'Sub-system',
    data_cat STRING DEFAULT 'REFERENCE' COMMENT 'Data category',
    data_frq STRING COMMENT 'Data frequency',
    src_id STRING COMMENT 'Source record ID',
    processing_date STRING COMMENT 'Processing date (YYYY-MM-DD)',
    record_type STRING COMMENT 'Record type indicator',

    -- Primary Key
    PRIMARY KEY (counterparty_short_name, m_label, country)
)
PARTITION BY HASH (counterparty_short_name) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.num_tablet_replicas' = '1',
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Add table comment
COMMENT ON TABLE cis_counterparty_cif_kudu IS
'Counterparty CIF data with country-level uniqueness constraint';
