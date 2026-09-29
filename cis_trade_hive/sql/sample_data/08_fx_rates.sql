-- ============================================================================
-- Sample FX Rate Data for gmp_cis_sta_dly_fx_rates
-- ============================================================================
-- Data Source: BOSET (Bloomberg) market data set
-- Data extracted from Impala query-48209 screenshots
-- Date: 2026-02-08
--
-- IMPORTANT: The production table is an external Parquet table that receives
-- data via ETL/file loads. For local Docker development, we use a Kudu-backed
-- table that accepts direct INSERTs.
-- ============================================================================

-- ============================================================================
-- DDL: Create Kudu-backed FX Rates table for local development
-- ============================================================================

-- Drop existing table if it exists
DROP TABLE IF EXISTS gmp_cis.gmp_cis_sta_dly_fx_rates_kudu;

-- Create Kudu-backed table for local development (supports INSERT/UPSERT)
CREATE TABLE IF NOT EXISTS gmp_cis.gmp_cis_sta_dly_fx_rates_kudu (
    src_system STRING NOT NULL,
    sub_system STRING NOT NULL,
    data_cat STRING NOT NULL,
    data_frq STRING NOT NULL,
    record_type STRING NOT NULL,
    spot_flag STRING,
    ref_quot_ccy STRING NOT NULL,
    base_cur STRING NOT NULL,
    `date` STRING NOT NULL,
    ask_rate STRING,
    underlying_cur STRING NOT NULL,
    bid_rate STRING,
    mktdata_set STRING,
    spot_rate_d STRING,
    src_id STRING,
    processing_date STRING NOT NULL,
    PRIMARY KEY (ref_quot_ccy, `date`, processing_date)
)
PARTITION BY HASH (ref_quot_ccy) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '1');

-- Create external table alias pointing to Kudu table
DROP TABLE IF EXISTS gmp_cis.gmp_cis_sta_dly_fx_rates;
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.gmp_cis_sta_dly_fx_rates
STORED AS KUDU
TBLPROPERTIES ('kudu.table_name' = 'impala::gmp_cis.gmp_cis_sta_dly_fx_rates_kudu');


-- ============================================================================
-- Sample Data: Major Currency Pairs (USD Base) - From Screenshot Data
-- Processing Date: 20251120
-- ============================================================================

-- USD-AED (UAE Dirham)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-AED', 'AED', '20251120', '3.67315', 'USD', '3.6728', 'BOSET', '3.673', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-ADA (Cardano - Crypto)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-ADA', 'ADA', '20251120', '0.512025', 'USD', '0.5117', 'BOSET', '0.511825', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-ARS (Argentine Peso)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-ARS', 'ARS', '20251120', '1003', 'USD', '1002', 'BOSET', '1002.5', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-AUD (Australian Dollar)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-AUD', 'AUD', '20251120', '1.54205', 'USD', '1.5417', 'BOSET', '1.54185', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-BDT (Bangladeshi Taka)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-BDT', 'BDT', '20251120', '122.6', 'USD', '122.5', 'BOSET', '122.6', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-BHD (Bahraini Dinar)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-BHD', 'BHD', '20251120', '0.377375', 'USD', '0.37685', 'BOSET', '0.377', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-BMD (Bermuda Dollar)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-BMD', 'BMD', '20251120', '1.00100', 'USD', '0.999', 'BOSET', '1', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-BND (Brunei Dollar)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-BND', 'BND', '20251120', '1.34760', 'USD', '1.34585', 'BOSET', '1.3467', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-BOB (Bolivian Boliviano)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-BOB', 'BOB', '20251120', '6.95', 'USD', '6.85', 'BOSET', '6.91', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-BRL (Brazilian Real)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-BRL', 'BRL', '20251120', '5.83145', 'USD', '5.8291', 'BOSET', '5.8307', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-BTC (Bitcoin)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-BTC', 'BTC', '20251120', '0.0000109', 'USD', '0.0000108', 'BOSET', '0.0000109', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-CAD (Canadian Dollar)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-CAD', 'CAD', '20251120', '1.40575', 'USD', '1.4054', 'BOSET', '1.40555', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-CHF (Swiss Franc)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-CHF', 'CHF', '20251120', '0.88425', 'USD', '0.88385', 'BOSET', '0.8841', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-CLP (Chilean Peso)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-CLP', 'CLP', '20251120', '972.24', 'USD', '971.96', 'BOSET', '972', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-CNH (Chinese Yuan Offshore)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-CNH', 'CNH', '20251120', '7.2225', 'USD', '7.206', 'BOSET', '7.21425', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-CNY (Chinese Yuan Onshore)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-CNY', 'CNY', '20251120', '7.11425', 'USD', '7.11405', 'BOSET', '7.11415', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-COP (Colombian Peso)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-COP', 'COP', '20251120', '4393586', 'USD', '4391288', 'BOSET', '4393000', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-CZK (Czech Koruna)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-CZK', 'CZK', '20251120', '24.002', 'USD', '23.982', 'BOSET', '23.987', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-DKK (Danish Krone)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-DKK', 'DKK', '20251120', '7.07475', 'USD', '7.0735', 'BOSET', '7.07275', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-EGP (Egyptian Pound)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-EGP', 'EGP', '20251120', '50.0225', 'USD', '49.925', 'BOSET', '49.965', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-ETH (Ethereum)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-ETH', 'ETH', '20251120', '0.000321', 'USD', '0.000319', 'BOSET', '0.00032', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-EUR (Euro)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-EUR', 'EUR', '20251120', '0.95015', 'USD', '0.9497', 'BOSET', '0.94995', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-GBP (British Pound)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-GBP', 'GBP', '20251120', '0.79545', 'USD', '0.79525', 'BOSET', '0.79535', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-GEL (Georgian Lari)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-GEL', 'GEL', '20251120', '2.755', 'USD', '2.745', 'BOSET', '2.75', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-HKD (Hong Kong Dollar)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-HKD', 'HKD', '20251120', '7.78105', 'USD', '7.7808', 'BOSET', '7.7809', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-HUF (Hungarian Forint)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-HUF', 'HUF', '20251120', '391.75', 'USD', '391.25', 'BOSET', '391.15', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-IDR (Indonesian Rupiah)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-IDR', 'IDR', '20251120', '16734.75', 'USD', '16734.75', 'BOSET', '16734.75', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-ILS (Israeli Shekel)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-ILS', 'ILS', '20251120', '3.7035', 'USD', '3.70185', 'BOSET', '3.70285', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-INR (Indian Rupee)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-INR', 'INR', '20251120', '84.6575', 'USD', '84.65', 'BOSET', '84.6575', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-JPY (Japanese Yen)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-JPY', 'JPY', '20251120', '156.47', 'USD', '156.41', 'BOSET', '156.44', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-KES (Kenyan Shilling)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-KES', 'KES', '20251120', '130.25', 'USD', '129.75', 'BOSET', '130', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-KRW (South Korean Won)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-KRW', 'KRW', '20251120', '1401.7', 'USD', '1401.1', 'BOSET', '1401.4', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-KWD (Kuwaiti Dinar)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-KWD', 'KWD', '20251120', '0.30785', 'USD', '0.3076', 'BOSET', '0.3077', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-KZT (Kazakhstani Tenge)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-KZT', 'KZT', '20251120', '512.85', 'USD', '508.55', 'BOSET', '510.85', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-LAK (Lao Kip)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-LAK', 'LAK', '20251120', '22050', 'USD', '21700', 'BOSET', '21700', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-LKR (Sri Lankan Rupee)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-LKR', 'LKR', '20251120', '297.9', 'USD', '297.8', 'BOSET', '297.9', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-MNT (Mongolian Tugrik)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-MNT', 'MNT', '20251120', '3575', 'USD', '3395', 'BOSET', '3505', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-MOP (Macanese Pataca)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-MOP', 'MOP', '20251120', '8.031', 'USD', '8.011', 'BOSET', '8.015', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-MXN (Mexican Peso)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-MXN', 'MXN', '20251120', '20.39095', 'USD', '20.38705', 'BOSET', '20.389', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-MYR (Malaysian Ringgit)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-MYR', 'MYR', '20251120', '4.461125', 'USD', '4.458625', 'BOSET', '4.459625', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-NGN (Nigerian Naira)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-NGN', 'NGN', '20251120', '1750', 'USD', '1650', 'BOSET', '1700', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-NOK (Norwegian Krone)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-NOK', 'NOK', '20251120', '11.13885', 'USD', '11.1363', 'BOSET', '11.13755', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-NPR (Nepalese Rupee)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-NPR', 'NPR', '20251120', '136.25', 'USD', '135.25', 'BOSET', '135.65', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-NZD (New Zealand Dollar)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-NZD', 'NZD', '20251120', '1.7065', 'USD', '1.70565', 'BOSET', '1.70605', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-OMR (Omani Rial)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-OMR', 'OMR', '20251120', '0.385', 'USD', '0.38485', 'BOSET', '0.38495', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-PHP (Philippine Peso)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-PHP', 'PHP', '20251120', '58.6095', 'USD', '58.5785', 'BOSET', '58.5905', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-PKR (Pakistani Rupee)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-PKR', 'PKR', '20251120', '278.375', 'USD', '278', 'BOSET', '278.375', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-PLN (Polish Zloty)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-PLN', 'PLN', '20251120', '4.07185', 'USD', '4.0708', 'BOSET', '4.0716', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-QAR (Qatari Riyal)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-QAR', 'QAR', '20251120', '3.646', 'USD', '3.6445', 'BOSET', '3.645', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-RON (Romanian Leu)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-RON', 'RON', '20251120', '4.61825', 'USD', '4.6155', 'BOSET', '4.61255', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-RUB (Russian Ruble)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-RUB', 'RUB', '20251120', '80.75', 'USD', '80.65', 'BOSET', '80.7', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-SAR (Saudi Riyal)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-SAR', 'SAR', '20251120', '3.7508', 'USD', '3.7503', 'BOSET', '3.75055', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-SEK (Swedish Krona)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-SEK', 'SEK', '20251120', '11.03195', 'USD', '11.02855', 'BOSET', '11.0302', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-SGD (Singapore Dollar)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-SGD', 'SGD', '20251120', '1.34555', 'USD', '1.34495', 'BOSET', '1.34525', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-THB (Thai Baht)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-THB', 'THB', '20251120', '34.625', 'USD', '34.59', 'BOSET', '34.6075', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-TRY (Turkish Lira)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-TRY', 'TRY', '20251120', '34.4075', 'USD', '34.37', 'BOSET', '34.3875', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-TWD (Taiwan Dollar)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-TWD', 'TWD', '20251120', '32.445', 'USD', '32.43', 'BOSET', '32.435', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-UAH (Ukrainian Hryvnia)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-UAH', 'UAH', '20251120', '41.9', 'USD', '41.2', 'BOSET', '41.55', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-VND (Vietnamese Dong)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-VND', 'VND', '20251120', '25435', 'USD', '25415', 'BOSET', '25425', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-XAG (Silver)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-XAG', 'XAG', '20251120', '0.0324', 'USD', '0.0322', 'BOSET', '0.0323', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-XAU (Gold)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-XAU', 'XAU', '20251120', '0.000381', 'USD', '0.000379', 'BOSET', '0.00038', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-XOF (West African CFA Franc)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-XOF', 'XOF', '20251120', '625', 'USD', '620', 'BOSET', '622.5', 'gmp_cis_sta_dly_fx_rates', '20251120');

-- USD-ZAR (South African Rand)
UPSERT INTO gmp_cis.gmp_cis_sta_dly_fx_rates_kudu
(src_system, sub_system, data_cat, data_frq, record_type, spot_flag, ref_quot_ccy, base_cur, `date`, ask_rate, underlying_cur, bid_rate, mktdata_set, spot_rate_d, src_id, processing_date)
VALUES ('gmp', 'cis', 'sta', 'dly', 'D', '1', 'USD-ZAR', 'ZAR', '20251120', '18.1645', 'USD', '18.1575', 'BOSET', '18.161', 'gmp_cis_sta_dly_fx_rates', '20251120');


-- ============================================================================
-- Refresh table metadata after inserts
-- ============================================================================
-- INVALIDATE METADATA gmp_cis.gmp_cis_sta_dly_fx_rates;
-- COMPUTE STATS gmp_cis.gmp_cis_sta_dly_fx_rates;


-- ============================================================================
-- Verification query
-- ============================================================================
-- SELECT COUNT(*) as total_rates,
--        COUNT(DISTINCT ref_quot_ccy) as unique_pairs,
--        MIN(`date`) as min_date,
--        MAX(`date`) as max_date
-- FROM gmp_cis.gmp_cis_sta_dly_fx_rates
-- WHERE record_type = 'D';
