-- Test Kudu table creation
USE cis;

-- Simple test table
CREATE TABLE IF NOT EXISTS test_simple_kudu (
  id INT NOT NULL,
  name STRING,
  PRIMARY KEY (id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

SHOW TABLES;
