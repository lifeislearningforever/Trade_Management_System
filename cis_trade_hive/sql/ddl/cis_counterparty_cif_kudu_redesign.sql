-- ============================================================================
-- CIS Counterparty CIF Kudu Table - Redesigned with Composite Primary Key
-- ============================================================================
-- Purpose: Link counterparties with their CIF numbers (one-to-many relationship)
-- Primary Key: (counterparty_short_name, m_label) - Composite key
-- Author: Claude Code
-- Date: 2025-01-07
-- ============================================================================

USE gmp_cis;

-- Drop existing CIF table
DROP TABLE IF EXISTS cis_counterparty_cif_kudu;

-- Create redesigned CIF table with composite primary key
CREATE TABLE cis_counterparty_cif_kudu (
    -- Composite Primary Key
    counterparty_short_name STRING NOT NULL,       -- FK to cis_counterparty_kudu
    m_label STRING NOT NULL,                        -- CIF number

    -- CIF Details
    country STRING,
    isin STRING,
    description STRING,                             -- Purpose/description of this CIF

    -- Source System Metadata
    src_system STRING,
    sub_system STRING,
    data_cat STRING,
    data_frq STRING,
    src_id STRING,
    processing_date STRING,
    record_type STRING,

    -- Audit Fields
    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_by STRING,
    created_at TIMESTAMP DEFAULT now(),
    updated_by STRING,
    updated_at TIMESTAMP DEFAULT now(),

    PRIMARY KEY (counterparty_short_name, m_label)
)
PARTITION BY HASH (counterparty_short_name) PARTITIONS 8
STORED AS KUDU
TBLPROPERTIES (
    'kudu.num_tablet_replicas' = '1',
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- ============================================================================
-- IMPORTANT NOTES:
-- ============================================================================
-- 1. PRIMARY KEY is composite: (counterparty_short_name, m_label)
-- 2. One counterparty can have multiple CIFs
-- 3. counterparty_short_name is foreign key reference to cis_counterparty_kudu
-- 4. m_label (CIF number) is now STRING type for flexibility
-- 5. ETL should do UPSERT (UPDATE if exists, INSERT if new)
-- 6. Soft delete supported via is_active and is_deleted flags
-- ============================================================================
