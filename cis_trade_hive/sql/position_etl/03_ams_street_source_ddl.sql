-- ============================================================================
-- AMS Street Source Tables DDL (1-5)
-- Source System: AMS_STREET
-- Format: Parquet external tables
-- Note: All columns are STRING datatype (ingestion standard)
-- ============================================================================

-- ============================================================================
-- AMS_STREET_1: AMS Multi Discretionary Fund
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.gmp_cis_sta_dly_ams_multi_dis_cif (
    src_id                  STRING,
    src_system              STRING,
    sub_system              STRING,
    data_cat                STRING,
    data_frq                STRING,
    portfolio_code          STRING,
    security_name           STRING,
    isin                    STRING,
    price                   STRING,
    units                   STRING,
    country_code            STRING
)
COMMENT 'AMS Street Source 1 - AMS Multi Discretionary Fund'
PARTITIONED BY (
    processing_date     STRING
)
STORED AS PARQUET
;

-- ============================================================================
-- AMS_STREET_2: AMS Multiple Holdings Daily
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.gmp_cis_sta_dly_ams_multi_hold (
    src_id                  STRING,
    src_system              STRING,
    sub_system              STRING,
    data_cat                STRING,
    data_frq                STRING,
    portfolio_code          STRING,
    security_name           STRING,
    isin                    STRING,
    quantity                STRING,
    ac_no                   STRING,
    country_code            STRING,
    trade_date              STRING
)
COMMENT 'AMS Street Source 2 - AMS Multiple Holdings Daily'
PARTITIONED BY (
    processing_date     STRING
)
STORED AS PARQUET
;

-- ============================================================================
-- AMS_STREET_3: AMS ICEQ Daily
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.gmp_cis_sta_dly_stat_street_ams_iceq (
    src_id                      STRING,
    src_system                  STRING,
    sub_system                  STRING,
    data_cat                    STRING,
    data_frq                    STRING,
    portfolio_code              STRING,
    sub_portfolio_reserved      STRING,
    security_name_long          STRING,
    country_name                STRING,
    security_currency           STRING,
    asset_class                 STRING,
    listing_status              STRING,
    quantity                    STRING,
    pct_ratio_reserved          STRING,
    cost_unit_price_local       STRING,
    market_unit_price_local     STRING,
    cost_value_local            STRING,
    market_value_local          STRING,
    cost_value_base             STRING,
    market_value_base           STRING,
    unrealized_pl_local         STRING,
    unrealized_pl_base          STRING,
    isin                        STRING,
    fx_rate_base_local          STRING,
    portfolio_code_2            STRING,
    flag_reserved               STRING,
    valuation_date              STRING,
    reporting_currency          STRING,
    padding_reserved            STRING,
    settled_date                STRING
)
COMMENT 'AMS Street Source 3 - AMS ICEQ Daily'
PARTITIONED BY (
    processing_date     STRING
)
STORED AS PARQUET
;

-- ============================================================================
-- AMS_STREET_4: AMS ICEQ Month End
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.gmp_cis_sta_mthly_stat_street_ams_iceq_end (
    src_id                      STRING,
    src_system                  STRING,
    sub_system                  STRING,
    data_cat                    STRING,
    data_frq                    STRING,
    portfolio_code              STRING,
    sub_portfolio_reserved      STRING,
    security_long_name          STRING,
    country_name                STRING,
    security_currency           STRING,
    asset_class                 STRING,
    listing_status              STRING,
    quantity                    STRING,
    pct_ratio_reserved          STRING,
    cost_unit_price_local       STRING,
    market_unit_price_local     STRING,
    cost_value_local            STRING,
    market_value_local          STRING,
    cost_value_base             STRING,
    market_value_base           STRING,
    unrealized_pl_local         STRING,
    unrealized_pl_base          STRING,
    isin                        STRING,
    fx_rate_base_local          STRING,
    portfolio_code_2            STRING,
    flag_reserved               STRING,
    valuation_date              STRING,
    reporting_currency          STRING,
    padding_reserved            STRING,
    settled_date                STRING
)
COMMENT 'AMS Street Source 4 - AMS ICEQ Month End'
PARTITIONED BY (
    processing_date     STRING
)
STORED AS PARQUET
;

-- ============================================================================
-- AMS_STREET_5: AMS S31 UOI Daily Limit
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.gmp_cis_sta_dly_stat_street_ams_daily_limit (
    src_id                  STRING,
    src_system              STRING,
    sub_system              STRING,
    data_cat                STRING,
    data_frq                STRING,
    ticker                  STRING,
    security_desc           STRING,
    portfolio               STRING,
    fund_type               STRING,
    quoted_unquoted         STRING,
    quantity_units          STRING,
    ccy                     STRING,
    product_type            STRING,
    ctry_of_exchange        STRING,
    ctry_incorporation      STRING,
    total_cost_fc           STRING,
    mkt_value_fc            STRING,
    unrealised_p_l_fc       STRING,
    total_cost_sgd          STRING,
    mkt_value_sgd           STRING,
    unrealised_pl_sgd       STRING,
    fx_rate                 STRING,
    issue_indicator         STRING,
    iso_code                STRING,
    mas_6digit_code         STRING,
    gl_fund_type            STRING,
    majorstake_indicate     STRING,
    stake_holdings          STRING,
    unit_cost               STRING,
    market_price            STRING,
    trade_date              STRING
)
COMMENT 'AMS Street Source 5 - AMS S31 UOI Daily Limit'
PARTITIONED BY (
    processing_date     STRING
)
STORED AS PARQUET
;
