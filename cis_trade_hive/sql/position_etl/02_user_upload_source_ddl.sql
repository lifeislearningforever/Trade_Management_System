-- ============================================================================
-- User Upload Source Tables DDL (1-5)
-- Source System: USER_UPLOAD
-- Format: Parquet external tables
-- ============================================================================

-- ============================================================================
-- USER_UPLOAD_1: Basic Position Data
-- Fields: Portfolio, Client_Num, Exchange_Quoted, ISIN_Code, Counter,
--         Quantity_Yesterday, Movement, Quantity_Today, trade_date
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.user_upload_1 (
    portfolio               STRING,
    client_num              STRING,
    exchange_quoted         STRING,
    isin_code               STRING,
    counter                 STRING,
    quantity_yesterday      DECIMAL(18,4),
    movement                DECIMAL(18,4),
    quantity_today          DECIMAL(18,4),
    trade_date              STRING
)
COMMENT 'User Upload Source 1 - Basic Position Data'
PARTITIONED BY (
    src_id              STRING,
    processing_date     STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/source/user_upload_1'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- ============================================================================
-- USER_UPLOAD_2: Portfolio Holdings with Country
-- Fields: Portfolio_Name, Stock_Name, Security_Description, ISIN_Code,
--         Qty_Held, Shares_Issued, Pct_Holding, Country, Country_ID, trade_date
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.user_upload_2 (
    portfolio_name          STRING,
    stock_name              STRING,
    security_description    STRING,
    isin_code               STRING,
    qty_held                DECIMAL(18,4),
    shares_issued           DECIMAL(18,4),
    pct_holding             DECIMAL(10,6),
    country                 STRING,
    country_id              STRING,
    trade_date              STRING
)
COMMENT 'User Upload Source 2 - Portfolio Holdings with Country'
PARTITIONED BY (
    src_id              STRING,
    processing_date     STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/source/user_upload_2'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- ============================================================================
-- USER_UPLOAD_3: Account Position Data
-- Fields: Account_name, Asset_description_short, ISIN, Shares_Par_value,
--         Shares_outstanding_total, Country_of_listing_code, trade_date
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.user_upload_3 (
    account_name                STRING,
    asset_description_short     STRING,
    isin                        STRING,
    shares_par_value            DECIMAL(18,4),
    shares_outstanding_total    DECIMAL(18,4),
    country_of_listing_code     STRING,
    trade_date                  STRING
)
COMMENT 'User Upload Source 3 - Account Position Data'
PARTITIONED BY (
    src_id              STRING,
    processing_date     STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/source/user_upload_3'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- ============================================================================
-- USER_UPLOAD_4: Comprehensive Position with Valuation
-- Fields: PORTFOLIO, SECURITY_FULL_NAME, PRODUCT_TYPE, SECURITY_TYPE,
--         GL_FUND_TYPE, QUOTED_UNQUOTED, SECURITY_CURRENCY, QUANTITY,
--         COST_FC, NET_BOOK_VALUE_FC, LOCAL_CURRENCY_Home_ccy, COST_LC,
--         Pct_HOLDINGS, NO_OF_SHARES_ISSUES_BY_THE_COMPANY,
--         COUNTRY_OF_INCORPORATION, COUNTRY_OF_EXCHANGE, ISIN_CODE,
--         TICKER_CODE, INDUSTRY, Financial_Non_Financial_Co, settled_date
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.user_upload_4 (
    portfolio                           STRING,
    security_full_name                  STRING,
    product_type                        STRING,
    security_type                       STRING,
    gl_fund_type                        STRING,
    quoted_unquoted                     STRING,
    security_currency                   STRING,
    quantity                            DECIMAL(18,4),
    cost_fc                             DECIMAL(18,4),
    net_book_value_fc                   DECIMAL(18,4),
    local_currency_home_ccy             STRING,
    cost_lc                             DECIMAL(18,4),
    pct_holdings                        DECIMAL(10,6),
    no_of_shares_issues_by_the_company  DECIMAL(18,4),
    country_of_incorporation            STRING,
    country_of_exchange                 STRING,
    isin_code                           STRING,
    ticker_code                         STRING,
    industry                            STRING,
    financial_non_financial_co          STRING,
    settled_date                        STRING
)
COMMENT 'User Upload Source 4 - Comprehensive Position with Valuation'
PARTITIONED BY (
    src_id              STRING,
    processing_date     STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/source/user_upload_4'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- ============================================================================
-- USER_UPLOAD_5: Full Position with P&L and MAS Codes
-- Fields: REPORTING_DATE, PORTFOLIO_NAME, SECURITY_FULL_NAME, PRODUCT_TYPE,
--         SECURITY_TYPE, GL_FUND_TYPE, QUOTED_UNQUOTED, SECURITY_CURRENCY_FC,
--         QUANTITY, Unit_Avg_Cost_unit_FC, Market_Price_unit_FC, COST_FC,
--         PROVISION_FC, UNREALISED_GAIN_LOSS_FC, NET_BOOK_VALUE_FC,
--         MARKET_VALUE_FC, LOCAL_CURRENCY, COST_LC, PROVISION_LC,
--         UNREALISED_GAIN_LOSS_LC, NET_BOOK_VALUE_LC, MARKET_VALUE_LC,
--         FX_RATE, CORP_CODE, BRANCH_CODE, COST_CENTRE, GL_ACCOUNT_NO_COST,
--         GL_ACCOUNT_NO_PROVISION, GL_ACCOUNT_NO_UNRL, COUNTRY_OF_RISK,
--         COUNTRY_OF_OPERATION, COUNTRY_OF_INCORPORATION, COUNTRY_OF_EXCHANGE,
--         ISIN_CODE, TICKER_CODE, ISSUER_TYPE, REITS_or_Fund_Y_N, INDUSTRY,
--         NO_OF_SHARES_ISSUES_BY_THE_COMPANY, Pct_HOLDINGS, CELS_Code,
--         BWCIF_NUMBER_SG, MAS_6D_CODE_SG, BWCIF_NUMBER_Overseas,
--         MAS_6D_CODE_Overseas, MATURITY_DATE, PORTIA_FUND_TYPE_CIS_INVESTMENT_TYPE,
--         settled_date
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.user_upload_5 (
    reporting_date                      STRING,
    portfolio_name                      STRING,
    security_full_name                  STRING,
    product_type                        STRING,
    security_type                       STRING,
    gl_fund_type                        STRING,
    quoted_unquoted                     STRING,
    security_currency_fc                STRING,
    quantity                            DECIMAL(18,4),
    unit_avg_cost_unit_fc               DECIMAL(18,6),
    market_price_unit_fc                DECIMAL(18,6),
    cost_fc                             DECIMAL(18,4),
    provision_fc                        DECIMAL(18,4),
    unrealised_gain_loss_fc             DECIMAL(18,4),
    net_book_value_fc                   DECIMAL(18,4),
    market_value_fc                     DECIMAL(18,4),
    local_currency                      STRING,
    cost_lc                             DECIMAL(18,4),
    provision_lc                        DECIMAL(18,4),
    unrealised_gain_loss_lc             DECIMAL(18,4),
    net_book_value_lc                   DECIMAL(18,4),
    market_value_lc                     DECIMAL(18,4),
    fx_rate                             DECIMAL(18,8),
    corp_code                           STRING,
    branch_code                         STRING,
    cost_centre                         STRING,
    gl_account_no_cost                  STRING,
    gl_account_no_provision             STRING,
    gl_account_no_unrl                  STRING,
    country_of_risk                     STRING,
    country_of_operation                STRING,
    country_of_incorporation            STRING,
    country_of_exchange                 STRING,
    isin_code                           STRING,
    ticker_code                         STRING,
    issuer_type                         STRING,
    reits_or_fund_y_n                   STRING,
    industry                            STRING,
    no_of_shares_issues_by_the_company  DECIMAL(18,4),
    pct_holdings                        DECIMAL(10,6),
    cels_code                           STRING,
    bwcif_number_sg                     STRING,
    mas_6d_code_sg                      STRING,
    bwcif_number_overseas               STRING,
    mas_6d_code_overseas                STRING,
    maturity_date                       STRING,
    portia_fund_type_cis_investment_type STRING,
    settled_date                        STRING
)
COMMENT 'User Upload Source 5 - Full Position with P&L and MAS Codes'
PARTITIONED BY (
    src_id              STRING,
    processing_date     STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/source/user_upload_5'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- ============================================================================
-- Repair partitions after data load
-- ============================================================================
-- MSCK REPAIR TABLE gmp_cis.user_upload_1;
-- MSCK REPAIR TABLE gmp_cis.user_upload_2;
-- MSCK REPAIR TABLE gmp_cis.user_upload_3;
-- MSCK REPAIR TABLE gmp_cis.user_upload_4;
-- MSCK REPAIR TABLE gmp_cis.user_upload_5;
