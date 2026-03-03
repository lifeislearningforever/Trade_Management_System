-- ============================================================================
-- AMS Street Source Tables DDL (1-5)
-- Source System: AMS_STREET
-- Format: Parquet external tables
-- ============================================================================

-- ============================================================================
-- AMS_STREET_1: AMS Multi Discretionary Fund
-- Fields: Portfolio, Security Name, ISIN, Price, Units, Country Code, trade_date
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.ams_street_1 (
    portfolio               STRING,
    security_name           STRING,
    isin                    STRING,
    price                   DECIMAL(18,6),
    units                   DECIMAL(18,4),
    country_code            STRING,
    trade_date              STRING
)
COMMENT 'AMS Street Source 1 - AMS Multi Discretionary Fund'
PARTITIONED BY (
    src_id              STRING,
    processing_date     STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/source/ams_street_1'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- ============================================================================
-- AMS_STREET_2: AMS Multiple Holdings Daily
-- Fields: Portfolio Code, Security Name, ISIN, Quantity, AC_No, Country Code, trade_date
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.ams_street_2 (
    portfolio_code          STRING,
    security_name           STRING,
    isin                    STRING,
    quantity                DECIMAL(18,4),
    ac_no                   STRING,
    country_code            STRING,
    trade_date              STRING
)
COMMENT 'AMS Street Source 2 - AMS Multiple Holdings Daily'
PARTITIONED BY (
    src_id              STRING,
    processing_date     STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/source/ams_street_2'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- ============================================================================
-- AMS_STREET_3: AMS ICEQ Month End (First variant)
-- Fields: Portfolio Code, Sub-Portfolio/Reserved, Security Name (Long),
--         Country Name, Security Currency, Asset Class, Listing Status,
--         Quantity, Pct/Ratio, Cost Unit Price (Local), Market Unit Price (Local),
--         Cost Value (Local), Market Value (Local), Cost Value (Base),
--         Market Value (Base), Unrealized P/L (Local), Unrealized P/L (Base),
--         ISIN, FX Rate, Portfolio Code, Flag, Valuation Date,
--         Reporting Currency, Padding/Reserved, settled_date
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.ams_street_3 (
    portfolio_code              STRING,
    sub_portfolio_reserved      STRING,
    security_name_long          STRING,
    country_name                STRING,
    security_currency           STRING,
    asset_class                 STRING,
    listing_status              STRING,
    quantity                    DECIMAL(18,4),
    pct_ratio_reserved          DECIMAL(10,6),
    cost_unit_price_local       DECIMAL(18,6),
    market_unit_price_local     DECIMAL(18,6),
    cost_value_local            DECIMAL(18,4),
    market_value_local          DECIMAL(18,4),
    cost_value_base             DECIMAL(18,4),
    market_value_base           DECIMAL(18,4),
    unrealized_pl_local         DECIMAL(18,4),
    unrealized_pl_base          DECIMAL(18,4),
    isin                        STRING,
    fx_rate_base_local          DECIMAL(18,8),
    portfolio_code_2            STRING,
    flag_reserved               STRING,
    valuation_date              STRING,
    reporting_currency          STRING,
    padding_reserved            STRING,
    settled_date                STRING
)
COMMENT 'AMS Street Source 3 - AMS ICEQ Month End (Variant 1)'
PARTITIONED BY (
    src_id              STRING,
    processing_date     STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/source/ams_street_3'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- ============================================================================
-- AMS_STREET_4: AMS ICEQ Month End (Second variant - same structure as 3)
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.ams_street_4 (
    portfolio_code              STRING,
    sub_portfolio_reserved      STRING,
    security_name_long          STRING,
    country_name                STRING,
    security_currency           STRING,
    asset_class                 STRING,
    listing_status              STRING,
    quantity                    DECIMAL(18,4),
    pct_ratio_reserved          DECIMAL(10,6),
    cost_unit_price_local       DECIMAL(18,6),
    market_unit_price_local     DECIMAL(18,6),
    cost_value_local            DECIMAL(18,4),
    market_value_local          DECIMAL(18,4),
    cost_value_base             DECIMAL(18,4),
    market_value_base           DECIMAL(18,4),
    unrealized_pl_local         DECIMAL(18,4),
    unrealized_pl_base          DECIMAL(18,4),
    isin                        STRING,
    fx_rate_base_local          DECIMAL(18,8),
    portfolio_code_2            STRING,
    flag_reserved               STRING,
    valuation_date              STRING,
    reporting_currency          STRING,
    padding_reserved            STRING,
    settled_date                STRING
)
COMMENT 'AMS Street Source 4 - AMS ICEQ Month End (Variant 2)'
PARTITIONED BY (
    src_id              STRING,
    processing_date     STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/source/ams_street_4'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- ============================================================================
-- AMS_STREET_5: AMS S31 UOI
-- Fields: Ticker, Security Desc, Portfolio, Fund Type, Quoted Unquoted,
--         Quantity Units, CCY, Product Type, Ctry of Exchange,
--         Ctry Incorporation, Total Cost (FC), Mkt Value (FC),
--         Unrealised P/L (FC), Total Cost (SGD), Mkt Value (SGD),
--         Unrealised P/L (SGD), FX Rate, Issue Indicator, ISO Code,
--         MAS 6Digit Code, GL Fund Type, MajorStake Indicate,
--         Stake Holdings, Unit Cost, Market Price, trade_date
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.ams_street_5 (
    ticker                      STRING,
    security_desc               STRING,
    portfolio                   STRING,
    fund_type                   STRING,
    quoted_unquoted             STRING,
    quantity_units              DECIMAL(18,4),
    ccy                         STRING,
    product_type                STRING,
    ctry_of_exchange            STRING,
    ctry_incorporation          STRING,
    total_cost_fc               DECIMAL(18,4),
    mkt_value_fc                DECIMAL(18,4),
    unrealised_pl_fc            DECIMAL(18,4),
    total_cost_sgd              DECIMAL(18,4),
    mkt_value_sgd               DECIMAL(18,4),
    unrealised_pl_sgd           DECIMAL(18,4),
    fx_rate                     DECIMAL(18,8),
    issue_indicator             STRING,
    iso_code                    STRING,
    mas_6digit_code             STRING,
    gl_fund_type                STRING,
    majorstake_indicate         STRING,
    stake_holdings              DECIMAL(10,6),
    unit_cost                   DECIMAL(18,6),
    market_price                DECIMAL(18,6),
    trade_date                  STRING
)
COMMENT 'AMS Street Source 5 - AMS S31 UOI'
PARTITIONED BY (
    src_id              STRING,
    processing_date     STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/source/ams_street_5'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- ============================================================================
-- Repair partitions after data load
-- ============================================================================
-- MSCK REPAIR TABLE gmp_cis.ams_street_1;
-- MSCK REPAIR TABLE gmp_cis.ams_street_2;
-- MSCK REPAIR TABLE gmp_cis.ams_street_3;
-- MSCK REPAIR TABLE gmp_cis.ams_street_4;
-- MSCK REPAIR TABLE gmp_cis.ams_street_5;
