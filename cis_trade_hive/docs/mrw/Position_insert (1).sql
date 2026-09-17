use gmp_cis;



drop table gmp_cis.position_upload_standardized 
;
CREATE EXTERNAL TABLE gmp_cis.position_upload_standardized (
    portfolio STRING,
    security_full_name STRING,
    security_short_name STRING,
    isin STRING,
    ticker STRING,
    quantity DECIMAL(18,4),
    shares_outstanding DECIMAL(18,4),
    shares_issued DECIMAL(18,4),
    pct_holding DECIMAL(10,6),
    market_price DECIMAL(18,6),
    average_cost DECIMAL(18,6),
    cost_fc DECIMAL(18,4),
    market_value_fc DECIMAL(18,4),
    net_book_value_fc DECIMAL(18,4),
    unrealized_pnl_fc DECIMAL(18,4),
    cost_lc DECIMAL(18,4),
    market_value_lc DECIMAL(18,4),
    net_book_value_lc DECIMAL(18,4),
    unrealized_pnl_lc DECIMAL(18,4),
    provision_lc DECIMAL(18,4),
    provision_fc DECIMAL(18,4),
    product_type STRING,
    security_type STRING,
    quoted_unquoted STRING,
    industry STRING,
    fin_nonfin_co STRING,
    issuer_type STRING,
    reits_or_fund_y_n STRING,
    `exchange` STRING,
    country_code STRING,
    country_of_exchange STRING,
    country_of_incorporation STRING,
    country_of_risk STRING,
    country_of_operation STRING,
    security_currency STRING,
    corp_code STRING,
    branch_code STRING,
    cost_centre STRING,
    cels STRING,
    bwcif_sg STRING,
    bwcif_ovs STRING,
    mas_6d_code_sg STRING,
    mas_6d_code_ovs STRING,
    position_basis STRING,
    reporting_date STRING,
    maturity_date STRING,
    src_system STRING,
    sub_system STRING,
    data_cat STRING,
    data_frq STRING,
    source_table STRING,
    etl_insert_ts TIMESTAMP,
    etl_batch_id STRING
)
PARTITIONED BY (src_id STRING, processing_date STRING)
STORED AS PARQUET;


WITH mhold_dedup AS (
    SELECT *
    FROM (
        SELECT
            mhold.*,
            ROW_NUMBER() OVER (
                PARTITION BY isin
                ORDER BY processing_date DESC
            ) AS rn
        FROM gmp_cis.gmp_cis_sta_dly_ams_multi_hold mhold
    ) t
    WHERE rn = 1
)

INSERT INTO TABLE gmp_cis.position_upload_standardized
PARTITION (processing_date,src_id)
SELECT
    portfolio, security_full_name, security_short_name, isin, ticker,
    cast(quantity as DECIMAL(18,4)), cast(shares_outstanding as DECIMAL(18,4)), cast(shares_issued as DECIMAL(18,4)), cast(pct_holding as DECIMAL(10,6)),
    cast(market_price as DECIMAL(18,6)), cast(average_cost as DECIMAL(18,6)),
    cast(cost_fc as DECIMAL(18,4)), cast(market_value_fc as DECIMAL(18,4)), cast(net_book_value_fc as DECIMAL(18,4)), cast(unrealized_pnl_fc as DECIMAL(18,4)),
    cast(cost_lc as DECIMAL(18,4)), cast(market_value_lc as DECIMAL(18,4)), cast(net_book_value_lc as DECIMAL(18,4)), cast(unrealized_pnl_lc as DECIMAL(18,4)), cast(provision_lc as DECIMAL(18,4)),cast(provision_fc as DECIMAL(18,4)),
    product_type, security_type, quoted_unquoted, industry, fin_nonfin_co,
    issuer_type, reits_or_fund_y_n,
    `exchange`, country_code, country_of_exchange, country_of_incorporation,
    country_of_risk, country_of_operation, security_currency,
    corp_code, branch_code, cost_centre, cels,
    bwcif_sg, bwcif_ovs, mas_6d_code_sg, mas_6d_code_ovs,
    position_basis, reporting_date, maturity_date,
    src_system, sub_system, data_cat, data_frq, source_table,
    etl_insert_ts, etl_batch_id,
    src_id, processing_date
FROM (
    -- ========================================================================
    -- 1. cis_user_sta_adhoc_position_1 (position_basis = trade_date)
    -- ========================================================================
    SELECT
        portfolio                           AS portfolio,
        counter                             AS security_full_name,
        NULL                                AS security_short_name,
        isin_code                           AS isin,
        NULL                                AS ticker,
        quantity_today                      AS quantity,
        NULL                                AS shares_outstanding,
        NULL                                AS shares_issued,
        NULL                                AS pct_holding,
        NULL                                AS market_price,
        NULL                                AS average_cost,
        NULL                                AS cost_fc,
        NULL                                AS market_value_fc,
        NULL                                AS net_book_value_fc,
        NULL                                AS unrealized_pnl_fc,
        NULL                                AS cost_lc,
        NULL                                AS market_value_lc,
        NULL                                AS net_book_value_lc,
        NULL                                AS unrealized_pnl_lc,
        NULL                                AS provision_lc,
		NULL 								AS provision_fc,
        NULL                                AS product_type,
        NULL                                AS security_type,
        NULL                                AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        exchange_quoted                     AS `exchange`,
        NULL                                AS country_code,
        NULL                                AS country_of_exchange,
        NULL                                AS country_of_incorporation,
        NULL                                AS country_of_risk,
        NULL                                AS country_of_operation,
        NULL                                AS security_currency,
        NULL                                AS corp_code,
        NULL                                AS branch_code,
        NULL                                AS cost_centre,
        NULL                                AS cels,
        NULL                                AS bwcif_sg,
        NULL                                AS bwcif_ovs,
        NULL                                AS mas_6d_code_sg,
        NULL                                AS mas_6d_code_ovs,
        "trade_date"                          AS position_basis,
        trade_date                                AS reporting_date,
        NULL                                AS maturity_date,
        'USER_UPLOAD'                       AS src_system,
        sub_system, data_cat, data_frq,
        'cis_user_sta_adhoc_position_1'     AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        'batch_002'                       AS etl_batch_id,
		
        src_id, processing_date
    FROM gmp_cis.cis_user_sta_adhoc_position_1
    WHERE processing_date = '20260130'

    UNION ALL

    -- ========================================================================
    -- 2. cis_user_sta_adhoc_position_2 (position_basis = trade_date)
    -- ========================================================================
    SELECT
        portfolio_name                      AS portfolio,
        security_description                AS security_full_name,
        stock_name                          AS security_short_name,
        isin_code                           AS isin,
        NULL                                AS ticker,
        qty_held                           AS quantity,
        shares_issued                       AS shares_outstanding,
        NULL                                AS shares_issued,
        pct_holding                         AS pct_holding,
        NULL                                AS market_price,
        NULL                                AS average_cost,
        NULL                                AS cost_fc,
        NULL                                AS market_value_fc,
        NULL                                AS net_book_value_fc,
        NULL                                AS unrealized_pnl_fc,
        NULL                                AS cost_lc,
        NULL                                AS market_value_lc,
        NULL                                AS net_book_value_lc,
        NULL                                AS unrealized_pnl_lc,
        NULL                                AS provision_lc,
		NULL 								AS provision_fc,
        NULL                                AS product_type,
        NULL                                AS security_type,
        NULL                                AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        country_id                                AS `exchange`,
        country_id                          AS country_code,
        country_id                             AS country_of_exchange,
        country_id                                AS country_of_incorporation,
        NULL                                AS country_of_risk,
        NULL                                AS country_of_operation,
        NULL                                AS security_currency,
        NULL                                AS corp_code,
        NULL                                AS branch_code,
        NULL                                AS cost_centre,
        NULL                                AS cels,
        NULL                                AS bwcif_sg,
        NULL                                AS bwcif_ovs,
        NULL                                AS mas_6d_code_sg,
        NULL                                AS mas_6d_code_ovs,
        "trade_date"                          AS position_basis,
        trade_date                                AS reporting_date,
        NULL                                AS maturity_date,
        'USER_UPLOAD'                       AS src_system,
        sub_system, data_cat, data_frq,
        'cis_user_sta_adhoc_position_2'     AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        'batch_002'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.cis_user_sta_adhoc_position_2
    WHERE processing_date = '20260130'

    UNION ALL

    -- ========================================================================
    -- 3. cis_user_sta_adhoc_position_3 (position_basis = trade_date)
    -- ========================================================================
    SELECT
        account_name                        AS portfolio,
        NULL                                AS security_full_name,
        asset_description_short             AS security_short_name,
        isin                                AS isin,
        NULL                                AS ticker,
        shares_outstanding_total            AS quantity,
        NULL                                AS shares_outstanding,
        NULL                                AS shares_issued,
        NULL                                AS pct_holding,
        NULL                                AS market_price,
        NULL                                AS average_cost,
        NULL                                AS cost_fc,
        NULL                                AS market_value_fc,
        NULL                                AS net_book_value_fc,
        NULL                                AS unrealized_pnl_fc,
        NULL                                AS cost_lc,
        NULL                                AS market_value_lc,
        NULL                                AS net_book_value_lc,
        NULL                                AS unrealized_pnl_lc,
        NULL                                AS provision_lc,
		NULL 								AS provision_fc,
        NULL                                AS product_type,
        NULL                                AS security_type,
        NULL                                AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        country_of_listing_code                                AS `exchange`,
        country_of_listing_code             AS country_code,
        country_of_listing_code                                AS country_of_exchange,
        country_of_listing_code                                AS country_of_incorporation,
        NULL                                AS country_of_risk,
        NULL                                AS country_of_operation,
        NULL                                AS security_currency,
        NULL                                AS corp_code,
        NULL                                AS branch_code,
        NULL                                AS cost_centre,
        NULL                                AS cels,
        NULL                                AS bwcif_sg,
        NULL                                AS bwcif_ovs,
        NULL                                AS mas_6d_code_sg,
        NULL                                AS mas_6d_code_ovs,
        "trade_date"                          AS position_basis,
        trade_date                                AS reporting_date,
        NULL                                AS maturity_date,
        'USER_UPLOAD'                       AS src_system,
        sub_system, data_cat, data_frq,
        'cis_user_sta_adhoc_position_3'     AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        'batch_002'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.cis_user_sta_adhoc_position_3
    WHERE processing_date = '20260130'

    UNION ALL

    -- ========================================================================
    -- 4. cis_user_sta_adhoc_position_4 (position_basis = settled_date)
    -- ========================================================================
    SELECT
        portfolio                           AS portfolio,
        security_full_name                  AS security_full_name,
        NULL                                AS security_short_name,
        isin_code                           AS isin,
        ticker_code                         AS ticker,
        quantity                           AS quantity,
        NULL                                AS shares_outstanding,
        no_of_shares_issues_by_the_company  AS shares_issued,
        pct_holdings                        AS pct_holding,
        NULL                                AS market_price,
        NULL                                AS average_cost,
        cost_fc                             AS cost_fc,
        NULL                                AS market_value_fc,
        net_book_value_fc                   AS net_book_value_fc,
        NULL                                AS unrealized_pnl_fc,
        cost_lc                             AS cost_lc,
        NULL                                AS market_value_lc,
        net_book_value_lc                   AS net_book_value_lc,
        NULL                                AS unrealized_pnl_lc,
        NULL                                AS provision_lc,
		NULL 								AS provision_fc,
        product_type                        AS product_type,
        security_type                       AS security_type,
        quoted_unquoted                     AS quoted_unquoted,
        industry                            AS industry,
        financial_non_financial_co          AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        NULL                                AS `exchange`,
        NULL                                AS country_code,
        cou.label                 AS country_of_exchange,
        cou.label            AS country_of_incorporation,
        cou.label                                AS country_of_risk,
        cou.label                                AS country_of_operation,
        security_currency                   AS security_currency,
        NULL                                AS corp_code,
        NULL                                AS branch_code,
        NULL                                AS cost_centre,
        NULL                                AS cels,
        NULL                                AS bwcif_sg,
        NULL                                AS bwcif_ovs,
        NULL                                AS mas_6d_code_sg,
        NULL                                AS mas_6d_code_ovs,
        "settled_date"                        AS position_basis,
        settled_date                                AS reporting_date,
        NULL                                AS maturity_date,
        'USER_UPLOAD'                       AS src_system,
        pos.sub_system as sub_system, pos.data_cat as data_cat, pos.data_frq as data_frq,
        'cis_user_sta_adhoc_position_4'     AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        'batch_002'                       AS etl_batch_id,
        pos.src_id as src_id, pos.processing_date as processing_date
    FROM gmp_cis.cis_user_sta_adhoc_position_4 pos
	left JOIN gmp_cis_sta_dly_country cou
    on pos.processing_date = cou.processing_date
    and upper(pos.country_of_incorporation) = upper(cou.full_name)
    WHERE pos.processing_date = '20260130'

    UNION ALL

    -- ========================================================================
    -- 5. cis_user_sta_adhoc_position_5 (position_basis = settled_date)
    -- ========================================================================
    SELECT
        portfolio_name                      AS portfolio,
        security_full_name                  AS security_full_name,
        NULL                                AS security_short_name,
        isin_code                           AS isin,
        ticker_code                         AS ticker,
        quantity                            AS quantity,
        NULL                                AS shares_outstanding,
        no_of_shares_issues_by_the_company  AS shares_issued,
        pct_holdings                        AS pct_holding,
        market_price_unit_fc                AS market_price,
        unit_avg_cost_unit_fc               AS average_cost,
        cost_fc                             AS cost_fc,
        market_value_fc                     AS market_value_fc,
        net_book_value_fc                   AS net_book_value_fc,
        unrealised_gain_loss_fc             AS unrealized_pnl_fc,
        cost_lc                             AS cost_lc,
        market_value_lc                     AS market_value_lc,
        net_book_value_lc                   AS net_book_value_lc,
        unrealised_gain_loss_lc             AS unrealized_pnl_lc,
        provision_lc                        AS provision_lc,
		provision_fc 								AS provision_fc,
        product_type                        AS product_type,
        security_type                       AS security_type,
        quoted_unquoted                     AS quoted_unquoted,
        industry                            AS industry,
        NULL                                AS fin_nonfin_co,
        issuer_type                         AS issuer_type,
        reits_or_fund_y_n                   AS reits_or_fund_y_n,
        cou.label                                AS `exchange`,
        cou.label                                AS country_code,
        cou.label                 AS country_of_exchange,
        cou.label            AS country_of_incorporation,
        country_of_risk                     AS country_of_risk,
        country_of_operation                AS country_of_operation,
        security_currency_fc                AS security_currency,
        corp_code                           AS corp_code,
        branch_code                         AS branch_code,
        cost_centre                         AS cost_centre,
        cels_code                           AS cels,
        bwcif_number_sg                     AS bwcif_sg,
        bwcif_number_overseas               AS bwcif_ovs,
        mas_6d_code_sg                      AS mas_6d_code_sg,
        mas_6d_code_overseas                AS mas_6d_code_ovs,
        "settled_date"                        AS position_basis,
        reporting_date                      AS reporting_date,
        NULL                                AS maturity_date,
        'USER_UPLOAD'                       AS src_system,
        pos.sub_system as sub_system, pos.data_cat as data_cat, pos.data_frq as data_frq,
        'cis_user_sta_adhoc_position_5'     AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        'batch_002'                       AS etl_batch_id,
        pos.src_id as src_id, pos.processing_date as processing_date
    FROM gmp_cis.cis_user_sta_adhoc_position_5 pos
	left JOIN gmp_cis_sta_dly_country cou
    on pos.processing_date = cou.processing_date
    and (upper(pos.country_of_risk) = upper(cou.full_name)
     OR UPPER(pos.country_of_risk) = UPPER(cou.label)
	 OR upper(pos.country_of_exchange) = upper(cou.full_name)
     OR UPPER(pos.country_of_exchange) = UPPER(cou.label))
    WHERE pos.processing_date = '20260130'

    UNION ALL

    -- ========================================================================
    -- 6. gmp_cis_sta_dly_ams_multi_dis_cif (position_basis = trade_date)
    -- ========================================================================
    SELECT
        "AMSMULTIDISCF"                           AS portfolio,
        security_name                       AS security_full_name,
        NULL                                AS security_short_name,
        isin                                AS isin,
        NULL                                AS ticker,
        units                               AS quantity,
        NULL                                AS shares_outstanding,
        NULL                                AS shares_issued,
        NULL                                AS pct_holding,
        price                               AS market_price,
        NULL                                AS average_cost,
        NULL                                AS cost_fc,
        NULL                                AS market_value_fc,
        NULL                                AS net_book_value_fc,
        NULL                                AS unrealized_pnl_fc,
        NULL                                AS cost_lc,
        NULL                                AS market_value_lc,
        NULL                                AS net_book_value_lc,
        NULL                                AS unrealized_pnl_lc,
        NULL                                AS provision_lc,
		NULL 								AS provision_fc,
        NULL                                AS product_type,
        NULL                                AS security_type,
        NULL                                AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        country_code                                AS `exchange`,
        country_code                        AS country_code,
        country_code                                AS country_of_exchange,
        country_code                                AS country_of_incorporation,
        NULL                                AS country_of_risk,
        NULL                                AS country_of_operation,
        NULL                                AS security_currency,
        NULL                                AS corp_code,
        NULL                                AS branch_code,
        NULL                                AS cost_centre,
        NULL                                AS cels,
        NULL                                AS bwcif_sg,
        NULL                                AS bwcif_ovs,
        NULL                                AS mas_6d_code_sg,
        NULL                                AS mas_6d_code_ovs,
        "trade_date"                                AS position_basis,
        NULL                                AS reporting_date,
        NULL                                AS maturity_date,
        'AMS_STREET'                        AS src_system,
        sub_system, data_cat, data_frq,
        'gmp_cis_sta_dly_ams_multi_dis_cif' AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        'batch_002'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.gmp_cis_sta_dly_ams_multi_dis_cif
    WHERE processing_date = '20260130'

    UNION ALL

  
    -- ========================================================================
    -- 7. gmp_cis_sta_dly_stat_street_ams_daily_limit (position_basis = trade_date)
    -- ========================================================================
    SELECT
        'AMSS31UOI'                           AS portfolio,
        security_desc                       AS security_full_name,
        NULL                                AS security_short_name,
        mhold.isin AS isin,
        ticker                              AS ticker,
        quantity_units                      AS quantity,
        NULL                                AS shares_outstanding,
        NULL                                AS shares_issued,
        stake_holdings                      AS pct_holding,
        market_price                        AS market_price,
        unit_cost                           AS average_cost,
        total_cost_fc                       AS cost_fc,
        mkt_value_fc                        AS market_value_fc,
        NULL                                AS net_book_value_fc,
        unrealised_pl_fc                    AS unrealized_pnl_fc,
        total_cost_sgd                      AS cost_lc,
        mkt_value_sgd                       AS market_value_lc,
        NULL                                AS net_book_value_lc,
        unrealised_pl_sgd                   AS unrealized_pnl_lc,
        NULL                                AS provision_lc,
		NULL 								AS provision_fc,
        product_type                        AS product_type,
        NULL                                AS security_type,
        quoted_unquoted                     AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        ctry_of_exchange                                AS `exchange`,
        ctry_of_exchange                                AS country_code,
        ctry_of_exchange                    AS country_of_exchange,
        ctry_of_exchange                  AS country_of_incorporation,
        NULL                                AS country_of_risk,
        NULL                                AS country_of_operation,
        ccy                                 AS security_currency,
        NULL                                AS corp_code,
        NULL                                AS branch_code,
        NULL                                AS cost_centre,
        NULL                                AS cels,
        NULL                                AS bwcif_sg,
        NULL                                AS bwcif_ovs,
        mas_6digit_code                     AS mas_6d_code_sg,
        NULL                                AS mas_6d_code_ovs,
        "trade_date"                          AS position_basis,
        NULL                                AS reporting_date,
        NULL                                AS maturity_date,
        'AMS_STREET'                        AS src_system,
        dli.sub_system, dli.data_cat, dli.data_frq,
        'gmp_cis_sta_dly_stat_street_ams_daily_limit' AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        'batch_002'                       AS etl_batch_id,
        dli.src_id, dli.processing_date
    FROM gmp_cis.gmp_cis_sta_dly_stat_street_ams_daily_limit dli
	LEFT JOIN mhold_dedup mhold
        ON dli.security_desc = mhold.security_name
    WHERE dli.processing_date = '20260130'
   

    UNION ALL

    -- ========================================================================
    -- 8. gmp_cis_sta_dly_stat_street_ams_iceq (position_basis = trade_date)
    -- ========================================================================
     SELECT
        portfolio_code                      AS portfolio,
        security_name_long                  AS security_full_name,
        NULL                                AS security_short_name,
        isin                                AS isin,
        NULL                                AS ticker,
        quantity                            AS quantity,
        NULL                                AS shares_outstanding,
        NULL                                AS shares_issued,
        pct_ratio_reserved                  AS pct_holding,
        market_unit_price_local            AS market_price,
        cost_unit_price_local               AS average_cost,
        cost_value_base                    AS cost_fc,
        market_value_local                  AS market_value_fc,
        NULL                                AS net_book_value_fc,
        unrealized_pl_local                 AS unrealized_pnl_fc,
        cost_value_base                     AS cost_lc,
        market_value_base                   AS market_value_lc,
        NULL                                AS net_book_value_lc,
        unrealized_pl_base                  AS unrealized_pnl_lc,
        NULL                                AS provision_lc,
		NULL 								AS provision_fc,
        asset_class                         AS product_type,
        NULL                                AS security_type,
        listing_status                      AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        cou.label                                AS `exchange`,
        cou.label                                AS country_code,
        cou.label                        AS country_of_exchange,
        cou.label                                AS country_of_incorporation,
        NULL                                AS country_of_risk,
        NULL                                AS country_of_operation,
        security_currency                   AS security_currency,
        NULL                                AS corp_code,
        NULL                                AS branch_code,
        NULL                                AS cost_centre,
        NULL                                AS cels,
        NULL                                AS bwcif_sg,
        NULL                                AS bwcif_ovs,
        NULL                                AS mas_6d_code_sg,
        NULL                                AS mas_6d_code_ovs,
        'trade_date'                        AS position_basis,
        valuation_date                      AS reporting_date,
        NULL                                AS maturity_date,
        'AMS_STREET'                        AS src_system,
        pos.sub_system as sub_system, pos.data_cat as data_cat, pos.data_frq as data_frq,
        'gmp_cis_sta_dly_stat_street_ams_iceq' AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        'batch_002'                       AS etl_batch_id,
        pos.src_id as src_id, pos.processing_date as processing_date
    FROM gmp_cis.gmp_cis_sta_dly_stat_street_ams_iceq pos
	left JOIN gmp_cis_sta_dly_country cou
    on pos.processing_date = cou.processing_date
    and (upper(pos.country_name) = upper(cou.full_name)
     OR UPPER(pos.country_name) = UPPER(cou.label))
    WHERE pos.processing_date = '20260130'


    UNION ALL

    -- ========================================================================
    -- 9. gmp_cis_sta_mthly_stat_street_ams_iceq_end (position_basis = settled_date)
    -- ========================================================================
    SELECT
        'AMSMONTHENDUOI'                      AS portfolio,
        security_name_long                  AS security_full_name,
        NULL                                AS security_short_name,
        isin                                AS isin,
        NULL                                AS ticker,
        quantity                            AS quantity,
        NULL                                AS shares_outstanding,
        NULL                                AS shares_issued,
        pct_ratio_reserved                  AS pct_holding,
        market_unit_price_local             AS market_price,
        cost_unit_price_local               AS average_cost,
        cost_value_local                    AS cost_fc,
        market_value_local                  AS market_value_fc,
        NULL                                AS net_book_value_fc,
        unrealized_pl_local                 AS unrealized_pnl_fc,
        cost_value_base                     AS cost_lc,
        market_value_base                   AS market_value_lc,
        NULL                                AS net_book_value_lc,
        unrealized_pl_base                  AS unrealized_pnl_lc,
        NULL                                AS provision_lc,
		NULL 								AS provision_fc,
        asset_class                         AS product_type,
        NULL                                AS security_type,
        listing_status                      AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        cou.label                                AS `exchange`,
        cou.label                                AS country_code,
        cou.label                        AS country_of_exchange,
        cou.label                                AS country_of_incorporation,
        NULL                                AS country_of_risk,
        NULL                                AS country_of_operation,
        security_currency                   AS security_currency,
        NULL                                AS corp_code,
        NULL                                AS branch_code,
        NULL                                AS cost_centre,
        NULL                                AS cels,
        NULL                                AS bwcif_sg,
        NULL                                AS bwcif_ovs,
        NULL                                AS mas_6d_code_sg,
        NULL                                AS mas_6d_code_ovs,
        "settled_date"                      AS position_basis,
        valuation_date                      AS reporting_date,
        NULL                                AS maturity_date,
        'AMS_STREET'                        AS src_system,
        pos.sub_system as sub_system, pos.data_cat as data_cat, pos.data_frq as data_frq,
        'gmp_cis_sta_mthly_stat_street_ams_iceq_end' AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        'batch_002'                       AS etl_batch_id,
        pos.src_id as src_id, pos.processing_date as processing_date
    FROM gmp_cis.gmp_cis_sta_mthly_stat_street_ams_iceq_end pos
	left JOIN gmp_cis_sta_dly_country cou
    on pos.processing_date = cou.processing_date
    and (upper(pos.country_name) = upper(cou.full_name)
     OR UPPER(pos.country_name) = UPPER(cou.label))
    WHERE pos.processing_date = '20260130'
	
	UNION ALL

    -- ========================================================================
    -- 10. GMP trade position
    -- ========================================================================
    SELECT
        pos.m_cis_pfolio                      AS portfolio,
        pos.m_security_full_name                  AS security_full_name,
        pos.m_security_display_label                                AS security_short_name,
        pos.m_security_code                                AS isin,
        NULL                                AS ticker,
        pos.m_quantity                            AS quantity,
        pos.m_outstanding_shares                                AS shares_outstanding,
        NULL                                AS shares_issued,
        NULL                  AS pct_holding,
        pos.m_market_price             AS market_price,
        pos.m_average_cost               AS average_cost,
        pos.m_total_cost_fc                    AS cost_fc,
        pos.m_market_value_fc                  AS market_value_fc,
        NULL                                AS net_book_value_fc,
        pos.m_unrealized_pl_fc                 AS unrealized_pnl_fc,
        NULL                     AS cost_lc,
        NULL                   AS market_value_lc,
        NULL                                AS net_book_value_lc,
        NULL                  AS unrealized_pnl_lc,
        NULL                                AS provision_lc,
		NULL 								AS provision_fc,
        NULL                         AS product_type,
        NULL                                AS security_type,
        pos.m_quoted                      AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        pos.m_country                                AS `exchange`,
        pos.m_country                                AS country_code,
        pos.m_country                        AS country_of_exchange,
        pos.m_country                                AS country_of_incorporation,
        NULL                                AS country_of_risk,
        NULL                                AS country_of_operation,
        pos.m_currency                   AS security_currency,
        NULL                                AS corp_code,
        NULL                                AS branch_code,
        NULL                                AS cost_centre,
        NULL                                AS cels,
        NULL                                AS bwcif_sg,
        NULL                                AS bwcif_ovs,
        NULL                                AS mas_6d_code_sg,
        NULL                                AS mas_6d_code_ovs,
        pos.line                      AS position_basis,
        POS.processing_date                      AS reporting_date,
        NULL                                AS maturity_date,
        pos.src_id                        AS src_system,
        pos.sub_system as sub_system, pos.data_cat as data_cat, pos.data_frq as data_frq,
        'gmp_cis_sta_dly_position' AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        'batch_002'                       AS etl_batch_id,
        pos.src_id as src_id, pos.processing_date as processing_date
    FROM gmp_cis.gmp_cis_sta_dly_position pos
    WHERE pos.processing_date = '20260130'
) combined;
