-- Drop existing UDF field tables
DROP TABLE IF EXISTS gmp_cis.cis_udf_field;
DROP TABLE IF EXISTS gmp_cis.cis_udf_field_kudu;

-- Create simplified UDF field table
CREATE TABLE IF NOT EXISTS gmp_cis.cis_udf_field_kudu(
    -- Primary Key
    udf_id BIGINT NOT NULL,

    -- Core Fields
    object_type STRING NOT NULL,        -- Object this UDF belongs to (PORTFOLIO, TRADE, COMMENTS, etc.)
    field_name STRING NOT NULL,         -- Technical field name (e.g., 'trade_date', 'broker_code')
    field_value STRING NOT NULL,        -- Display label (e.g., 'Trade Date', 'Broker Code')

    -- Metadata
    is_active BOOLEAN DEFAULT true,     -- Soft delete flag (true = active, false = deleted)

    -- Audit Fields
    created_by STRING NOT NULL,
    created_at BIGINT NOT NULL,         -- Unix timestamp in milliseconds
    updated_by STRING NOT NULL,
    updated_at BIGINT NOT NULL,         -- Unix timestamp in milliseconds

    -- Primary Key Constraint
    PRIMARY KEY (udf_id)
)
PARTITION BY HASH (udf_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '1');

-- Create external table mapping
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_udf_field
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_udf_field_kudu');

-- Sample data for object types (field_value is empty for object type records)
-- Object Types
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(1, 'PORTFOLIO', 'object_type', '', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(2, 'EQUITY_PRICE', 'object_type', '', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(3, 'SECURITY', 'object_type', '', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

-- Sample fields for PORTFOLIO object
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(100, 'PORTFOLIO', 'portfolio_type', 'Portfolio Type', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(101, 'PORTFOLIO', 'portfolio_category', 'Portfolio Category', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(102, 'PORTFOLIO', 'investment_strategy', 'Investment Strategy', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

-- Sample fields for EQUITY_PRICE object
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(200, 'EQUITY_PRICE', 'market', 'Market', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(201, 'EQUITY_PRICE', 'price_source', 'Price Source', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

-- ============================================================================
-- SECURITY UDF Fields (25 fields matching production)
-- field_name must match EXACTLY what is used in security_dropdown_service.py
-- ============================================================================
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(300, 'SECURITY', 'Industry', 'Industry', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(301, 'SECURITY', 'Country of Incorporation', 'Country of Incorporation', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(302, 'SECURITY', 'Exchange Code', 'Exchange Code', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(303, 'SECURITY', 'Security Type', 'Security Type', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(304, 'SECURITY', 'Investment Type', 'Investment Type', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(305, 'SECURITY', 'Price Source of Issue', 'Price Source of Issue', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(306, 'SECURITY', 'Country of Issue', 'Country of Issue', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(307, 'SECURITY', 'Country of Primary Exchange', 'Country of Primary Exchange', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(308, 'SECURITY', 'BWCIIF', 'BWCIIF', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(309, 'SECURITY', 'BWCIIF Others', 'BWCIIF Others', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(310, 'SECURITY', 'Issuer Type', 'Issuer Type', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(311, 'SECURITY', 'Approved S32', 'Approved S32', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(312, 'SECURITY', 'BASEL IV - FUND', 'BASEL IV - FUND', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(313, 'SECURITY', 'Business Unit Head', 'Business Unit Head', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(314, 'SECURITY', 'Core/Non Core', 'Core/Non Core', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(315, 'SECURITY', 'Fund / Index Fund', 'Fund / Index Fund', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(316, 'SECURITY', 'Management Limit Classification', 'Management Limit Classification', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(317, 'SECURITY', 'MAS 643 Entity Type', 'MAS 643 Entity Type', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(318, 'SECURITY', 'Person In Charge', 'Person In Charge', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(319, 'SECURITY', 'Substantial >10%', 'Substantial >10%', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(320, 'SECURITY', 'PEWC', 'PEWC', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(321, 'SECURITY', 'S32 Representative', 'S32 Representative', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(322, 'SECURITY', 'Quoted/Unquoted', 'Quoted/Unquoted', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(323, 'SECURITY', 'Fin/Non-Fin IND', 'Fin/Non-Fin IND', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(324, 'SECURITY', 'Relative Index', 'Relative Index', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);
