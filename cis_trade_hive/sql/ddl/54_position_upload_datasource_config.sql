-- ============================================================================
-- Datasource Config: 5 User Position Upload Files
-- ============================================================================
-- Registers all 5 fixed-format position CSV files in cis_datasource_mng so the
-- upload app can validate column structure and ingest into the correct Hive
-- external table.
--
-- Key rules:
--   - source_name must match the uploaded filename EXACTLY (case-sensitive)
--     Actual filenames: CIS_External_upload_format_1.csv .. _5.csv
--   - intake_columns lists only file columns (no position_basis — it is
--     server-injected at ingest time via POSITION_TABLE_BASIS dict)
--   - reporting_date IS a file column for tables 1, 2, 3 — included here
--   - position_basis is NOT listed — excluded from validation, defaulted at
--     ingest: TRADE_DATE (tables 1-3), SETTLE_DATE (tables 4-5)
--
-- Run:
--   impala-shell -i localhost:21050 -f sql/ddl/54_position_upload_datasource_config.sql
-- ============================================================================

USE gmp_cis;

-- ----------------------------------------------------------------------------
-- Position Upload 1: Basic Position Data
-- Separator: | (pipe)
-- CSV has header row: TRUE
-- CSV columns (9 file columns, position_basis is server-injected — NOT listed):
--   Portfolio, Client_Num, Exchange_Quoted, ISIN_Code, Counter,
--   Quantity_Yesterday, Movement, Quantity_Today, Trade_Date
-- position_basis defaulted to: TRADE_DATE at ingest
-- NOTE: UPSERT keyed on source_id — updates existing row in DB
-- ----------------------------------------------------------------------------
UPSERT INTO gmp_cis.cis_datasource_mng (
    source_id,
    source_name,
    target_table,
    separator,
    header,
    no_of_skip_line,
    intake_columns,
    src_system,
    sub_system,
    data_cat,
    data_frq
) VALUES (
    'cis_user_sta_adhoc_position_1',
    'CIS_External_upload_format_1.csv',
    'cis_user_sta_adhoc_position_1',
    '|',
    'true',
    '0',
    'portfolio,client_num,exchange_quoted,isin_code,counter,quantity_yesterday,movement,quantity_today,trade_date',
    'USER_UPLOAD',
    'user',
    'sta',
    'adhoc'
);

-- ----------------------------------------------------------------------------
-- Position Upload 2: Portfolio Holdings with Country
-- CSV columns: Portfolio_Name, Stock_Name, Security_Description, ISIN_Code,
--              Qty_Held, Shares_Issued, Pct_Holding, Country, Country_ID,
--              Reporting_Date
-- position_basis defaulted to: TRADE_DATE
-- ----------------------------------------------------------------------------
UPSERT INTO gmp_cis.cis_datasource_mng (
    source_id,
    source_name,
    target_table,
    separator,
    header,
    no_of_skip_line,
    intake_columns,
    src_system,
    sub_system,
    data_cat,
    data_frq
) VALUES (
    'cis_user_sta_adhoc_position_2',
    'CIS_External_upload_format_2.csv',
    'cis_user_sta_adhoc_position_2',
    ',',
    'true',
    '0',
    'portfolio_name,stock_name,security_description,isin_code,qty_held,shares_issued,pct_holding,country,country_id,reporting_date',
    'USER_UPLOAD',
    'user',
    'sta',
    'adhoc'
);

-- ----------------------------------------------------------------------------
-- Position Upload 3: Account Position Data
-- CSV columns: Account_name, Asset_description_short, ISIN, Shares_Par_value,
--              Shares_outstanding_total, Country_of_listing_code, Reporting_Date
-- position_basis defaulted to: TRADE_DATE
-- ----------------------------------------------------------------------------
UPSERT INTO gmp_cis.cis_datasource_mng (
    source_id,
    source_name,
    target_table,
    separator,
    header,
    no_of_skip_line,
    intake_columns,
    src_system,
    sub_system,
    data_cat,
    data_frq
) VALUES (
    'cis_user_sta_adhoc_position_3',
    'CIS_External_upload_format_3.csv',
    'cis_user_sta_adhoc_position_3',
    ',',
    'true',
    '0',
    'account_name,asset_description_short,isin,shares_par_value,shares_outstanding_total,country_of_listing_code,reporting_date',
    'USER_UPLOAD',
    'user',
    'sta',
    'adhoc'
);

-- ----------------------------------------------------------------------------
-- Position Upload 4: Comprehensive Position with Valuation
-- CSV columns: Portfolio, Security_Full_Name, Product_Type, Security_Type,
--              GL_Fund_Type, Quoted_Unquoted, Security_Currency, Quantity,
--              Cost_FC, Net_Book_Value_FC, Net_Book_Value_LC,
--              Local_Currency_Home_ccy, Cost_LC, Pct_Holdings,
--              No_of_Shares_Issues_by_the_Company, Country_of_Incorporation,
--              Country_of_Exchange, ISIN_Code, Ticker_Code, Industry,
--              Financial_Non_Financial_Co
-- position_basis defaulted to: SETTLE_DATE
-- Note: No reporting_date column in table 4 file format
-- ----------------------------------------------------------------------------
UPSERT INTO gmp_cis.cis_datasource_mng (
    source_id,
    source_name,
    target_table,
    separator,
    header,
    no_of_skip_line,
    intake_columns,
    src_system,
    sub_system,
    data_cat,
    data_frq
) VALUES (
    'cis_user_sta_adhoc_position_4',
    'CIS_External_upload_format_4.csv',
    'cis_user_sta_adhoc_position_4',
    ',',
    'true',
    '0',
    'portfolio,security_full_name,product_type,security_type,gl_fund_type,quoted_unquoted,security_currency,quantity,cost_fc,net_book_value_fc,net_book_value_lc,local_currency_home_ccy,cost_lc,pct_holdings,no_of_shares_issues_by_the_company,country_of_incorporation,country_of_exchange,isin_code,ticker_code,industry,financial_non_financial_co',
    'USER_UPLOAD',
    'user',
    'sta',
    'adhoc'
);

-- ----------------------------------------------------------------------------
-- Position Upload 5: Full Position with P&L and MAS Codes
-- CSV columns: Reporting_Date, Portfolio_Name, Security_Full_Name, Product_Type,
--              Security_Type, GL_Fund_Type, Quoted_Unquoted, Security_Currency_FC,
--              Quantity, Unit_Avg_Cost_unit_FC, Market_Price_unit_FC, Cost_FC,
--              Provision_FC, Unrealised_Gain_Loss_FC, Net_Book_Value_FC,
--              Market_Value_FC, Local_Currency, Cost_LC, Provision_LC,
--              Unrealised_Gain_Loss_LC, Net_Book_Value_LC, Market_Value_LC,
--              FX_Rate, Corp_Code, Branch_Code, Cost_Centre,
--              GL_Account_No_Cost, GL_Account_No_Provision, GL_Account_No_Unrl,
--              Country_of_Risk, Country_of_Operation, Country_of_Incorporation,
--              Country_of_Exchange, ISIN_Code, Ticker_Code, Issuer_Type,
--              REITS_or_Fund_Y_N, Industry, No_of_Shares_Issues_by_the_Company,
--              Pct_Holdings, CELS_Code, BWCIF_Number_SG, MAS_6D_Code_SG,
--              BWCIF_Number_Overseas, MAS_6D_Code_Overseas, Maturity_Date,
--              PORTIA_Fund_Type_CIS_Investment_Type
-- position_basis defaulted to: SETTLE_DATE
-- ----------------------------------------------------------------------------
UPSERT INTO gmp_cis.cis_datasource_mng (
    source_id,
    source_name,
    target_table,
    separator,
    header,
    no_of_skip_line,
    intake_columns,
    src_system,
    sub_system,
    data_cat,
    data_frq
) VALUES (
    'cis_user_sta_adhoc_position_5',
    'CIS_External_upload_format_5.csv',
    'cis_user_sta_adhoc_position_5',
    ',',
    'true',
    '0',
    'reporting_date,portfolio_name,security_full_name,product_type,security_type,gl_fund_type,quoted_unquoted,security_currency_fc,quantity,unit_avg_cost_unit_fc,market_price_unit_fc,cost_fc,provision_fc,unrealised_gain_loss_fc,net_book_value_fc,market_value_fc,local_currency,cost_lc,provision_lc,unrealised_gain_loss_lc,net_book_value_lc,market_value_lc,fx_rate,corp_code,branch_code,cost_centre,gl_account_no_cost,gl_account_no_provision,gl_account_no_unrl,country_of_risk,country_of_operation,country_of_incorporation,country_of_exchange,isin_code,ticker_code,issuer_type,reits_or_fund_y_n,industry,no_of_shares_issues_by_the_company,pct_holdings,cels_code,bwcif_number_sg,mas_6d_code_sg,bwcif_number_overseas,mas_6d_code_overseas,maturity_date,portia_fund_type_cis_investment_type',
    'USER_UPLOAD',
    'user',
    'sta',
    'adhoc'
);

-- Verify all 5 configs
SELECT source_id, source_name, target_table, separator, header, intake_columns
FROM gmp_cis.cis_datasource_mng
WHERE source_id IN (
    'cis_user_sta_adhoc_position_1',
    'cis_user_sta_adhoc_position_2',
    'cis_user_sta_adhoc_position_3',
    'cis_user_sta_adhoc_position_4',
    'cis_user_sta_adhoc_position_5'
)
ORDER BY source_id;
