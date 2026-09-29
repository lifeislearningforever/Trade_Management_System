-- ============================================================================
-- Position Master ETL - Hive SQL Implementation
-- Transforms 10 source tables into unified position_upload_standardized
-- No temporary views - single INSERT with UNION ALL
-- ============================================================================
-- Usage:
--   beeline -u "jdbc:hive2://localhost:10000" -n user -p password \
--     --hivevar processing_date=03032026 \
--     --hivevar batch_id=batch_001 \
--     -f 04_position_master_etl_hive.sql
-- ============================================================================

-- Set session properties
SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.exec.max.dynamic.partitions=10000;
SET hive.exec.max.dynamic.partitions.pernode=1000;
SET parquet.compression=SNAPPY;

-- ============================================================================
-- Single INSERT with UNION ALL from all 10 source tables
-- ============================================================================
INSERT INTO TABLE gmp_cis.position_upload_standardized
PARTITION (src_id, processing_date)
SELECT
    portfolio, security_full_name, security_short_name, isin, ticker,
    quantity, shares_outstanding, shares_issued, pct_holding,
    market_price, average_cost,
    cost_fc, market_value_fc, net_book_value_fc, unrealized_pnl_fc,
    cost_lc, market_value_lc, net_book_value_lc, unrealized_pnl_lc, provision_lc,
    product_type, security_type, quoted_unquoted, industry, fin_nonfin_co,
    issuer_type, reits_or_fund_y_n,
    exchange, country_code, country_of_exchange, country_of_incorporation,
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
        NULL                                AS product_type,
        NULL                                AS security_type,
        NULL                                AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        exchange_quoted                     AS exchange,
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
        trade_date                          AS position_basis,
        NULL                                AS reporting_date,
        NULL                                AS maturity_date,
        'USER_UPLOAD'                       AS src_system,
        sub_system, data_cat, data_frq,
        'cis_user_sta_adhoc_position_1'     AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        '${batch_id}'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.cis_user_sta_adhoc_position_1
    WHERE processing_date = '${processing_date}'

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
        qty_held                            AS quantity,
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
        NULL                                AS product_type,
        NULL                                AS security_type,
        NULL                                AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        NULL                                AS exchange,
        country_id                          AS country_code,
        country                             AS country_of_exchange,
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
        trade_date                          AS position_basis,
        NULL                                AS reporting_date,
        NULL                                AS maturity_date,
        'USER_UPLOAD'                       AS src_system,
        sub_system, data_cat, data_frq,
        'cis_user_sta_adhoc_position_2'     AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        '${batch_id}'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.cis_user_sta_adhoc_position_2
    WHERE processing_date = '${processing_date}'

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
        NULL                                AS product_type,
        NULL                                AS security_type,
        NULL                                AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        NULL                                AS exchange,
        country_of_listing_code             AS country_code,
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
        trade_date                          AS position_basis,
        NULL                                AS reporting_date,
        NULL                                AS maturity_date,
        'USER_UPLOAD'                       AS src_system,
        sub_system, data_cat, data_frq,
        'cis_user_sta_adhoc_position_3'     AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        '${batch_id}'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.cis_user_sta_adhoc_position_3
    WHERE processing_date = '${processing_date}'

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
        quantity                            AS quantity,
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
        NULL                                AS net_book_value_lc,
        NULL                                AS unrealized_pnl_lc,
        NULL                                AS provision_lc,
        product_type                        AS product_type,
        security_type                       AS security_type,
        quoted_unquoted                     AS quoted_unquoted,
        industry                            AS industry,
        financial_non_financial_co          AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        NULL                                AS exchange,
        NULL                                AS country_code,
        country_of_exchange                 AS country_of_exchange,
        country_of_incorporation            AS country_of_incorporation,
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
        settled_date                        AS position_basis,
        NULL                                AS reporting_date,
        NULL                                AS maturity_date,
        'USER_UPLOAD'                       AS src_system,
        sub_system, data_cat, data_frq,
        'cis_user_sta_adhoc_position_4'     AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        '${batch_id}'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.cis_user_sta_adhoc_position_4
    WHERE processing_date = '${processing_date}'

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
        product_type                        AS product_type,
        security_type                       AS security_type,
        quoted_unquoted                     AS quoted_unquoted,
        industry                            AS industry,
        NULL                                AS fin_nonfin_co,
        issuer_type                         AS issuer_type,
        reits_or_fund_y_n                   AS reits_or_fund_y_n,
        NULL                                AS exchange,
        NULL                                AS country_code,
        country_of_exchange                 AS country_of_exchange,
        country_of_incorporation            AS country_of_incorporation,
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
        settled_date                        AS position_basis,
        reporting_date                      AS reporting_date,
        NULL                                AS maturity_date,
        'USER_UPLOAD'                       AS src_system,
        sub_system, data_cat, data_frq,
        'cis_user_sta_adhoc_position_5'     AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        '${batch_id}'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.cis_user_sta_adhoc_position_5
    WHERE processing_date = '${processing_date}'

    UNION ALL

    -- ========================================================================
    -- 6. gmp_cis_sta_dly_ams_multi_dis_cif (position_basis = TRADED)
    -- ========================================================================
    SELECT
        portfolio_code                      AS portfolio,
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
        NULL                                AS product_type,
        NULL                                AS security_type,
        NULL                                AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        NULL                                AS exchange,
        country_code                        AS country_code,
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
        'TRADED'                        AS position_basis,
        NULL                                AS reporting_date,
        NULL                                AS maturity_date,
        'AMS_STREET'                        AS src_system,
        sub_system, data_cat, data_frq,
        'gmp_cis_sta_dly_ams_multi_dis_cif' AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        '${batch_id}'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.gmp_cis_sta_dly_ams_multi_dis_cif
    WHERE processing_date = '${processing_date}'

    UNION ALL

    -- ========================================================================
    -- 7. gmp_cis_sta_dly_ams_multi_hold (position_basis = trade_date)
    -- ========================================================================
    SELECT
        portfolio_code                      AS portfolio,
        security_name                       AS security_full_name,
        NULL                                AS security_short_name,
        isin                                AS isin,
        NULL                                AS ticker,
        quantity                            AS quantity,
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
        NULL                                AS product_type,
        NULL                                AS security_type,
        NULL                                AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        NULL                                AS exchange,
        country_code                        AS country_code,
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
        'TRADED'                        AS position_basis,
        NULL                                AS reporting_date,
        NULL                                AS maturity_date,
        'AMS_STREET'                        AS src_system,
        sub_system, data_cat, data_frq,
        'gmp_cis_sta_dly_ams_multi_hold'    AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        '${batch_id}'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.gmp_cis_sta_dly_ams_multi_hold
    WHERE processing_date = '${processing_date}'

    UNION ALL

    -- ========================================================================
    -- 8. gmp_cis_sta_dly_stat_street_ams_daily_limit (position_basis = trade_date)
    -- ========================================================================
    SELECT
        portfolio                           AS portfolio,
        security_desc                       AS security_full_name,
        NULL                                AS security_short_name,
        NULL                                AS isin,
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
        unrealised_p_l_fc                   AS unrealized_pnl_fc,
        total_cost_sgd                      AS cost_lc,
        mkt_value_sgd                       AS market_value_lc,
        NULL                                AS net_book_value_lc,
        unrealised_pl_sgd                   AS unrealized_pnl_lc,
        NULL                                AS provision_lc,
        product_type                        AS product_type,
        NULL                                AS security_type,
        quoted_unquoted                     AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        NULL                                AS exchange,
        NULL                                AS country_code,
        ctry_of_exchange                    AS country_of_exchange,
        ctry_incorporation                  AS country_of_incorporation,
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
        'TRADED'                        AS position_basis,
        NULL                                AS reporting_date,
        NULL                                AS maturity_date,
        'AMS_STREET'                        AS src_system,
        sub_system, data_cat, data_frq,
        'gmp_cis_sta_dly_stat_street_ams_daily_limit' AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        '${batch_id}'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.gmp_cis_sta_dly_stat_street_ams_daily_limit
    WHERE processing_date = '${processing_date}'

    UNION ALL

    -- ========================================================================
    -- 9. gmp_cis_sta_dly_stat_street_ams_iceq (position_basis = trade_date)
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
        asset_class                         AS product_type,
        NULL                                AS security_type,
        listing_status                      AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        NULL                                AS exchange,
        NULL                                AS country_code,
        country_name                        AS country_of_exchange,
        NULL                                AS country_of_incorporation,
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
        settled_date                        AS position_basis,
        valuation_date                      AS reporting_date,
        NULL                                AS maturity_date,
        'AMS_STREET'                        AS src_system,
        sub_system, data_cat, data_frq,
        'gmp_cis_sta_dly_stat_street_ams_iceq' AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        '${batch_id}'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.gmp_cis_sta_dly_stat_street_ams_iceq
    WHERE processing_date = '${processing_date}'

    UNION ALL

    -- ========================================================================
    -- 10. gmp_cis_sta_mthly_stat_street_ams_iceq_end (position_basis = settled_date)
    -- ========================================================================
    SELECT
        portfolio_code                      AS portfolio,
        security_long_name                  AS security_full_name,
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
        asset_class                         AS product_type,
        NULL                                AS security_type,
        listing_status                      AS quoted_unquoted,
        NULL                                AS industry,
        NULL                                AS fin_nonfin_co,
        NULL                                AS issuer_type,
        NULL                                AS reits_or_fund_y_n,
        NULL                                AS exchange,
        NULL                                AS country_code,
        country_name                        AS country_of_exchange,
        NULL                                AS country_of_incorporation,
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
        settled_date                        AS position_basis,
        valuation_date                      AS reporting_date,
        NULL                                AS maturity_date,
        'AMS_STREET'                        AS src_system,
        sub_system, data_cat, data_frq,
        'gmp_cis_sta_mthly_stat_street_ams_iceq_end' AS source_table,
        CURRENT_TIMESTAMP()                 AS etl_insert_ts,
        '${batch_id}'                       AS etl_batch_id,
        src_id, processing_date
    FROM gmp_cis.gmp_cis_sta_mthly_stat_street_ams_iceq_end
    WHERE processing_date = '${processing_date}'
) combined;


-- ============================================================================
-- Verify data load
-- ============================================================================
SELECT
    src_system,
    source_table,
    COUNT(*) AS record_count
FROM gmp_cis.position_upload_standardized
WHERE processing_date = '${processing_date}'
  AND etl_batch_id = '${batch_id}'
GROUP BY src_system, source_table
ORDER BY src_system, source_table;

SELECT
    COUNT(*) AS total_records,
    '${processing_date}' AS processing_date,
    '${batch_id}' AS batch_id
FROM gmp_cis.position_upload_standardized
WHERE processing_date = '${processing_date}'
  AND etl_batch_id = '${batch_id}';
