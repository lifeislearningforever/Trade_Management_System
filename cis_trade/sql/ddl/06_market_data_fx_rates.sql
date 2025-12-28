-- =====================================================
-- CisTrade - Market Data FX Rates External Table (Hive)
-- External table for daily FX rates from GMP system
-- =====================================================

-- Drop table if exists
DROP TABLE IF EXISTS gmp_cis_sta_dly_fx_rates;

-- Create external table for FX rates
CREATE EXTERNAL TABLE gmp_cis_sta_dly_fx_rates (
    record_type     STRING      COMMENT 'Record type indicator (D=Detail, H=Header)',
    ref_quot        STRING      COMMENT 'Reference quotation identifier',
    spot_ff0        STRING      COMMENT 'Currency pair (e.g., USD-AED)',
    base            STRING      COMMENT 'Base currency code',
    trade_date      STRING      COMMENT 'Trade date in YYYYMMDD format',
    spot_rf_a       DECIMAL(18,6)   COMMENT 'Spot rate reference A',
    underlng        STRING      COMMENT 'Underlying currency code',
    spot_rf_b       DECIMAL(18,6)   COMMENT 'Spot rate reference B',
    alias           STRING      COMMENT 'Source/Alias identifier (e.g., BOSET)',
    mid_rate        DECIMAL(18,6)   COMMENT 'Mid rate calculated as (spot_rf_a + spot_rf_b)/2'
)
COMMENT 'Daily FX Rates from GMP system - Detail records only (Header records excluded)'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE
LOCATION '/user/hive/warehouse/gmp_cis_sta_dly_fx_rates'
TBLPROPERTIES (
    'skip.header.line.count'='1',
    'serialization.null.format'='',
    'source.system'='GMP',
    'data.type'='FX_RATES',
    'refresh.frequency'='DAILY'
);

-- =====================================================
-- Notes:
-- 1. Header records (H|GMP|...) should be filtered during load
-- 2. Only detail records (D|...) should be loaded
-- 3. mid_rate can be calculated during query or ETL process
-- 4. File format: pipe-delimited (|) text file
-- 5. Expected location: HDFS path for daily FX rate files
-- =====================================================

-- Sample query to calculate mid_rate on the fly
-- SELECT
--     record_type,
--     ref_quot,
--     spot_ff0,
--     base,
--     trade_date,
--     spot_rf_a,
--     underlng,
--     spot_rf_b,
--     alias,
--     ROUND((spot_rf_a + spot_rf_b) / 2, 6) as mid_rate
-- FROM gmp_cis_sta_dly_fx_rates
-- WHERE record_type = 'D';

-- =====================================================
-- Filter for Detail Records Only (exclude Header)
-- =====================================================
-- CREATE VIEW gmp_cis_sta_dly_fx_rates_detail AS
-- SELECT *
-- FROM gmp_cis_sta_dly_fx_rates
-- WHERE record_type = 'D';
