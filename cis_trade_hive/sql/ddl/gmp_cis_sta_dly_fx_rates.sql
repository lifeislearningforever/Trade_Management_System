-- =====================================================
-- CisTrade - Market Data FX Rates External Table DDL
-- =====================================================
--
-- Table: gmp_cis_sta_dly_fx_rates
-- Purpose: Daily FX spot rates from external sources
-- Source: BOSET and other market data providers
-- Update Frequency: Daily
--
-- Created: 2025-12-27
-- =====================================================

-- Drop table if exists (for recreation)
DROP TABLE IF EXISTS gmp_cis.gmp_cis_sta_dly_fx_rates;

-- Create the external table
CREATE EXTERNAL TABLE gmp_cis.gmp_cis_sta_dly_fx_rates (
    record_type     STRING          COMMENT 'Record type indicator (D=Detail, H=Header)',
    ref_quot        STRING          COMMENT 'Reference quotation identifier',
    spot_ff0        STRING          COMMENT 'Currency pair (e.g., USD-AED)',
    base            STRING          COMMENT 'Base currency code',
    trade_date      STRING          COMMENT 'Trade date in YYYYMMDD format',
    spot_rf_a       DECIMAL(18,6)   COMMENT 'Spot rate reference A (bid rate)',
    underlng        STRING          COMMENT 'Underlying currency code',
    spot_rf_b       DECIMAL(18,6)   COMMENT 'Spot rate reference B (ask rate)',
    alias           STRING          COMMENT 'Source/Alias identifier (e.g., BOSET)',
    mid_rate        DECIMAL(18,6)   COMMENT 'Mid rate calculated as (spot_rf_a + spot_rf_b)/2',
    processing_date STRING          COMMENT 'ETL processing date in YYYYMMDD format - date when file was loaded'
)
COMMENT 'Daily FX spot rates from external market data sources'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
LINES TERMINATED BY '\n'
STORED AS TEXTFILE
LOCATION 'file:/var/lib/impala/warehouse/gmp_cis.db/gmp_cis_sta_dly_fx_rates'
TBLPROPERTIES (
    'external.table.purge' = 'true',
    'skip.header.line.count' = '1'
);

-- Create indexes for better query performance
-- Note: These are commented out - create after table is populated

-- CREATE INDEX idx_fx_trade_date ON gmp_cis.gmp_cis_sta_dly_fx_rates(trade_date);
-- CREATE INDEX idx_fx_currency_pair ON gmp_cis.gmp_cis_sta_dly_fx_rates(spot_ff0);
-- CREATE INDEX idx_fx_base_currency ON gmp_cis.gmp_cis_sta_dly_fx_rates(base);

-- Verify table creation
DESCRIBE FORMATTED gmp_cis.gmp_cis_sta_dly_fx_rates;

-- Sample query to check data
-- SELECT * FROM gmp_cis.gmp_cis_sta_dly_fx_rates
-- WHERE trade_date = '20251227'
-- LIMIT 10;

-- =====================================================
-- Sample Data Format (pipe-delimited)
-- =====================================================
-- record_type|ref_quot|spot_ff0|base|trade_date|spot_rf_a|underlng|spot_rf_b|alias|mid_rate|processing_date
-- D|Q001|USD-AED|USD|20251227|3.672500|AED|3.673500|BOSET|3.673000|20251229
-- D|Q002|USD-EUR|USD|20251227|0.850000|EUR|0.851000|BOSET|0.850500|20251229
-- D|Q003|USD-GBP|USD|20251227|0.750000|GBP|0.751000|BOSET|0.750500|20251229
-- =====================================================

-- =====================================================
-- Usage Examples
-- =====================================================

-- 1. Get latest FX rate for a currency pair
-- SELECT spot_ff0, base, trade_date, mid_rate
-- FROM gmp_cis.gmp_cis_sta_dly_fx_rates
-- WHERE spot_ff0 = 'USD-AED'
--   AND trade_date = (SELECT MAX(trade_date) FROM gmp_cis.gmp_cis_sta_dly_fx_rates)
--   AND record_type = 'D';

-- 2. Get all FX rates for a specific date
-- SELECT spot_ff0, base, underlng, mid_rate, alias
-- FROM gmp_cis.gmp_cis_sta_dly_fx_rates
-- WHERE trade_date = '20251227'
--   AND record_type = 'D'
-- ORDER BY spot_ff0;

-- 3. Get historical rates for a currency pair
-- SELECT trade_date, spot_ff0, mid_rate, spot_rf_a, spot_rf_b
-- FROM gmp_cis.gmp_cis_sta_dly_fx_rates
-- WHERE spot_ff0 = 'USD-EUR'
--   AND record_type = 'D'
--   AND trade_date >= '20251201'
-- ORDER BY trade_date DESC;

-- 4. Calculate spread (ask - bid)
-- SELECT spot_ff0, trade_date,
--        spot_rf_a as bid_rate,
--        spot_rf_b as ask_rate,
--        (spot_rf_b - spot_rf_a) as spread,
--        mid_rate
-- FROM gmp_cis.gmp_cis_sta_dly_fx_rates
-- WHERE trade_date = '20251227'
--   AND record_type = 'D'
-- ORDER BY spread DESC;

-- =====================================================
-- Data Quality Checks
-- =====================================================

-- Check for missing mid_rates
-- SELECT COUNT(*) as missing_mid_rate_count
-- FROM gmp_cis.gmp_cis_sta_dly_fx_rates
-- WHERE mid_rate IS NULL AND record_type = 'D';

-- Check for invalid rates (negative or zero)
-- SELECT spot_ff0, trade_date, mid_rate
-- FROM gmp_cis.gmp_cis_sta_dly_fx_rates
-- WHERE (mid_rate <= 0 OR spot_rf_a <= 0 OR spot_rf_b <= 0)
--   AND record_type = 'D';

-- Check data freshness (latest trade date)
-- SELECT MAX(trade_date) as latest_date,
--        COUNT(DISTINCT spot_ff0) as currency_pair_count,
--        COUNT(*) as total_records
-- FROM gmp_cis.gmp_cis_sta_dly_fx_rates
-- WHERE record_type = 'D';

-- =====================================================
-- Maintenance Commands
-- =====================================================

-- Refresh table metadata (after data loads)
-- INVALIDATE METADATA gmp_cis.gmp_cis_sta_dly_fx_rates;

-- Compute statistics for better query performance
-- COMPUTE STATS gmp_cis.gmp_cis_sta_dly_fx_rates;

-- Optimize table (if using Kudu instead of HDFS)
-- ALTER TABLE gmp_cis.gmp_cis_sta_dly_fx_rates SET TBLPROPERTIES ('kudu.table_id' = 'impala::gmp_cis.gmp_cis_sta_dly_fx_rates');

-- =====================================================
-- End of DDL
-- =====================================================
