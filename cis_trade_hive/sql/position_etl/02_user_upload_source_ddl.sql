-- ============================================================================
-- User Upload Source Tables DDL (1-5)
-- Source System: USER_UPLOAD
-- Format: Parquet external tables
-- Note: position_basis is NOT in the uploaded file — it is defaulted at
--       ingest time (TRADE_DATE for tables 1-3, SETTLE_DATE for tables 4-5)
-- ============================================================================

-- ============================================================================
-- USER_UPLOAD_1: Basic Position Data
-- Separator: | (pipe)
-- File headers: REPORTING_DATE, Portfolio, Client_Num, Exchange_Quoted,
--               ISIN_Code, Counter, Quantity_Yesterday, Movement, Quantity_Today
-- position_basis default: TRADE_DATE (server-injected, not in file)
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_user_sta_adhoc_position_1 (
    src_id              STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING,
    reporting_date          STRING,
    portfolio               STRING,
    client_num              STRING,
    exchange_quoted         STRING,
    isin_code               STRING,
    counter                 STRING,
    quantity_yesterday      STRING,
    movement                STRING,
    quantity_today          STRING,
    position_basis          STRING
)
COMMENT 'User Upload Source 1 - Basic Position Data (position_basis defaulted to TRADE_DATE at ingest)'
PARTITIONED BY (
    processing_date     STRING
)
STORED AS PARQUET
;

-- ============================================================================
-- USER_UPLOAD_2: Portfolio Holdings with Country
-- Fields: Portfolio_Name, Stock_Name, Security_Description, ISIN_Code,
--         Qty_Held, Shares_Issued, Pct_Holding, Country, Country_ID,
--         Reporting_Date
-- position_basis default: TRADE_DATE
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_user_sta_adhoc_position_2 (
    src_id              STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING,
    portfolio_name          STRING,
    stock_name              STRING,
    security_description    STRING,
    isin_code               STRING,
    qty_held                STRING,
    shares_issued           STRING,
    pct_holding             STRING,
    country                 STRING,
    country_id              STRING,
    reporting_date          STRING,
    position_basis          STRING
)
COMMENT 'User Upload Source 2 - Portfolio Holdings with Country (position_basis defaulted to TRADE_DATE at ingest)'
PARTITIONED BY (
    processing_date     STRING
)
STORED AS PARQUET
;

-- ============================================================================
-- USER_UPLOAD_3: Account Position Data
-- Fields: Account_name, Asset_description_short, ISIN, Shares_Par_value,
--         Shares_outstanding_total, Country_of_listing_code, Reporting_Date
-- position_basis default: TRADE_DATE
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_user_sta_adhoc_position_3 (
    src_id              STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING,
    account_name                STRING,
    asset_description_short     STRING,
    isin                        STRING,
    shares_par_value            STRING,
    shares_outstanding_total    STRING,
    country_of_listing_code     STRING,
    reporting_date              STRING,
    position_basis              STRING
)
COMMENT 'User Upload Source 3 - Account Position Data (position_basis defaulted to TRADE_DATE at ingest)'
PARTITIONED BY (
    processing_date     STRING
)
STORED AS PARQUET
;

-- ============================================================================
-- USER_UPLOAD_4: Comprehensive Position with Valuation
-- Fields: PORTFOLIO, SECURITY_FULL_NAME, PRODUCT_TYPE, SECURITY_TYPE,
--         GL_FUND_TYPE, QUOTED_UNQUOTED, SECURITY_CURRENCY, QUANTITY,
--         COST_FC, NET_BOOK_VALUE_FC, NET_BOOK_VALUE_LC, LOCAL_CURRENCY_Home_ccy,
--         COST_LC, Pct_HOLDINGS, NO_OF_SHARES_ISSUES_BY_THE_COMPANY,
--         COUNTRY_OF_INCORPORATION, COUNTRY_OF_EXCHANGE, ISIN_CODE,
--         TICKER_CODE, INDUSTRY, Financial_Non_Financial_Co
-- position_basis default: SETTLE_DATE
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_user_sta_adhoc_position_4 (
    src_id              STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING,
    portfolio                           STRING,
    security_full_name                  STRING,
    product_type                        STRING,
    security_type                       STRING,
    gl_fund_type                        STRING,
    quoted_unquoted                     STRING,
    security_currency                   STRING,
    quantity                            STRING,
    cost_fc                             STRING,
    net_book_value_fc                   STRING,
    net_book_value_lc                   STRING,
    local_currency_home_ccy             STRING,
    cost_lc                             STRING,
    pct_holdings                        STRING,
    no_of_shares_issues_by_the_company  STRING,
    country_of_incorporation            STRING,
    country_of_exchange                 STRING,
    isin_code                           STRING,
    ticker_code                         STRING,
    industry                            STRING,
    financial_non_financial_co          STRING,
    reporting_date                      STRING,
    position_basis                      STRING
)
COMMENT 'User Upload Source 4 - Comprehensive Position with Valuation (position_basis defaulted to SETTLE_DATE at ingest)'
PARTITIONED BY (
    processing_date     STRING
)
STORED AS PARQUET
;

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
--         MAS_6D_CODE_Overseas, MATURITY_DATE, PORTIA_FUND_TYPE_CIS_INVESTMENT_TYPE
-- position_basis default: SETTLE_DATE
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_user_sta_adhoc_position_5 (
    src_id              STRING,
    src_system          STRING,
    sub_system          STRING,
    data_cat            STRING,
    data_frq            STRING,
    reporting_date                      STRING,
    portfolio                           STRING,
    security_full_name                  STRING,
    product_type                        STRING,
    security_type                       STRING,
    gl_fund_type                        STRING,
    quoted_unquoted                     STRING,
    security_currency_fc                STRING,
    quantity                            STRING,
    unit_avg_cost_unit_fc               STRING,
    market_price_unit_fc                STRING,
    cost_fc                             STRING,
    provision_fc                        STRING,
    unrealised_gain_loss_fc             STRING,
    net_book_value_fc                   STRING,
    market_value_fc                     STRING,
    local_currency                      STRING,
    cost_lc                             STRING,
    provision_lc                        STRING,
    unrealised_gain_loss_lc             STRING,
    net_book_value_lc                   STRING,
    market_value_lc                     STRING,
    fx_rate                             STRING,
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
    no_of_shares_issues_by_the_company  STRING,
    pct_holdings                        STRING,
    cels_code                           STRING,
    bwcif_number_sg                     STRING,
    mas_6d_code_sg                      STRING,
    bwcif_number_overseas               STRING,
    mas_6d_code_overseas                STRING,
    maturity_date                       STRING,
    portia_fund_type_cis_investment_type STRING,
    position_basis                      STRING
)
COMMENT 'User Upload Source 5 - Full Position with P&L and MAS Codes (position_basis defaulted to SETTLE_DATE at ingest)'
PARTITIONED BY (
    processing_date     STRING
)
STORED AS PARQUET
;
-- ============================================================================
-- Repair partitions after data load
-- ============================================================================
-- MSCK REPAIR TABLE gmp_cis.cis_user_sta_adhoc_position_1;
-- MSCK REPAIR TABLE gmp_cis.cis_user_sta_adhoc_position_2;
-- MSCK REPAIR TABLE gmp_cis.cis_user_sta_adhoc_position_3;
-- MSCK REPAIR TABLE gmp_cis.cis_user_sta_adhoc_position_4;
-- MSCK REPAIR TABLE gmp_cis.cis_user_sta_adhoc_position_5;

-- ============================================================================
-- ALTER TABLE: Add reporting_date to existing tables 1, 2, 3
-- Run these on the live cluster if tables were already created without the column.
-- Tables 4 and 5 do not need this (4 has no reporting_date; 5 already has it).
-- ============================================================================
-- ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_1 ADD COLUMNS (trade_date STRING);
-- ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_2 ADD COLUMNS (reporting_date STRING);
-- ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_3 ADD COLUMNS (reporting_date STRING);
