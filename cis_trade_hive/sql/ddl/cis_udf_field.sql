-- Simplified UDF Field Table (Kudu)
-- Single table to store field codes, entity types, and their dropdown options

DROP TABLE IF EXISTS gmp_cis.cis_udf_field_kudu;

CREATE TABLE gmp_cis.cis_udf_field_kudu (
    id BIGINT NOT NULL,
    entity_type STRING NOT NULL,
    field_code STRING NOT NULL,
    option_value STRING NOT NULL,
    display_order INT,
    is_active BOOLEAN DEFAULT true,
    created_at BIGINT,
    created_by STRING,

    PRIMARY KEY (id)
)
PARTITION BY HASH (id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES('kudu.num_tablet_replicas' = '1');

-- Create external Impala table
DROP TABLE IF EXISTS gmp_cis.cis_udf_field;

CREATE EXTERNAL TABLE gmp_cis.cis_udf_field
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_udf_field_kudu');
