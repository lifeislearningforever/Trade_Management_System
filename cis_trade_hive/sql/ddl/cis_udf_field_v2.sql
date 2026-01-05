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

-- Sample fields for SECURITY object
UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(300, 'SECURITY', 'security_type', 'Security Type', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);

UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
(301, 'SECURITY', 'industry', 'Industry', true, 'SYSTEM', unix_timestamp() * 1000, 'SYSTEM', unix_timestamp() * 1000);
