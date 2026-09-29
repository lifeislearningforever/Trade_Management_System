-- Diagnose Pending Settlement page showing blank list in UAT despite
-- stats badge showing a nonzero pending_settlement count.
--
-- Run against UAT: impala-shell -i <uat-host>:21050 -d gmp_cis -f diagnose_pending_settlement_blank.sql

-- =============================================================================
-- STEP 1: Exact status values with length (catches trailing/leading
-- whitespace, non-breaking spaces, or other invisible characters that a
-- plain UPPER() comparison won't catch).
-- =============================================================================
SELECT status, LENGTH(status) AS len, COUNT(*) AS cnt
FROM gmp_cis.cis_trade
WHERE is_deleted = false OR is_deleted IS NULL
GROUP BY status;

-- =============================================================================
-- STEP 2: Does a case-insensitive, trimmed match return anything at all?
-- =============================================================================
SELECT COUNT(*) AS cnt
FROM gmp_cis.cis_trade t
WHERE UPPER(TRIM(t.status)) = 'VALIDATED';

-- =============================================================================
-- STEP 3: Sanity check on total row count.
-- =============================================================================
SELECT COUNT(*) AS total_rows FROM gmp_cis.cis_trade;

-- =============================================================================
-- STEP 4: The exact query the Pending Settlement page runs
-- (get_pending_settlement_trades -> get_all_trades -> get_all_trades_multi_filter),
-- reproduced verbatim from trade/repositories/trade_kudu_repository.py.
-- If STEP 2 returns rows but this returns none, the LEFT JOINs are the culprit.
-- =============================================================================
SELECT
    t.trade_id, t.trade_type, t.deal_number,
    t.portfolio_short_name, t.portfolio_full_name,
    t.security_label, t.security_full_name, t.security_type,
    t.currency_code,
    t.trade_status, t.trade_date, t.settle_date, t.expiry_date,
    t.quantity, t.face_value, t.lot, t.price,
    t.commission, t.accrued_interest, t.sec_fee, t.other_charges, t.total_amount,
    t.total_amount_fc, t.total_amount_lc,
    t.gross_amount_fc, t.gross_amount_lc,
    t.open_close_position, t.extension, t.brokers, t.broker_name,
    t.gl_fund_type, t.gl_cost_centre, t.gl_account_code,
    t.contract_ref, t.fd_receipt, t.org_pur_date,
    t.open_fx_rate, t.curr_dealing, t.open_dealing,
    t.input_tax_oth, t.qty_entitled,
    t.selling_rule, t.cash_balance, t.custodian, t.amor_accr_method,
    t.lots_held, t.quantity_held,
    t.remarks,
    t.udf_fund_type, t.udf_section_31_26, t.udf_sub_custodian,
    t.udf_disclosure_req, t.udf_counter_pledged, t.udf_revision_code,
    t.udf_uobn_uobn_hk, t.udf_income_exp_type, t.udf_currency_hedge,
    t.realized_pnl, t.parent_trade_id, t.delivery_type, t.counterparty,
    t.reduction_type, t.reduction_amount, t.units_affected,
    t.income_type, t.ex_date, t.record_date, t.pay_date,
    t.amount_per_unit, t.gross_amount, t.withholding_tax, t.net_amount,
    t.split_type, t.split_ratio_new, t.split_ratio_old, t.effective_date,
    t.status, t.is_active, t.is_deleted, t.src_system,
    t.created_by, t.created_at, t.updated_by, t.updated_at,
    t.submitted_by, t.submitted_at,
    t.validated_by, t.validated_at, t.validation_comments,
    t.settled_by, t.settled_at, t.settlement_comments,
    t.cancelled_by, t.cancelled_at, t.cancel_reason,
    t.internal_ref, t.external_ref,
    t.charge_fee_type, t.charge_exchange, t.charge_country,
    t.charge_fee_rule, t.charge_fee_value,
    t.calculated_commission, t.calculated_clearing_fee,
    t.calculated_trading_fee, t.calculated_gst, t.calculated_other_fees,
    t.total_calculated_charges, t.charges_auto_calculated,
    COALESCE(p.currency, t.currency_code) AS portfolio_currency,
    COALESCE(p.description, '') AS portfolio_description,
    COALESCE(p.manager, '') AS portfolio_manager,
    COALESCE(p.portfolio_client, '') AS portfolio_client_name,
    s.security_id AS security_id,
    COALESCE(s.security_description, '') AS security_description
FROM gmp_cis.cis_trade t
LEFT JOIN gmp_cis.cis_portfolio p ON t.portfolio_short_name = p.name AND (p.is_active = true OR p.is_active IS NULL)
LEFT JOIN gmp_cis.cis_security s ON t.security_label = s.security_name
WHERE UPPER(t.status) = 'VALIDATED'
ORDER BY CASE WHEN UPPER(t.src_system) = 'CIS' THEN 0 ELSE 1 END,
         t.created_at DESC
LIMIT 100;

-- =============================================================================
-- STEP 5: Isolate whether the JOINs are dropping rows -- same filter,
-- no joins at all.
-- =============================================================================
SELECT COUNT(*) AS cnt_no_joins
FROM gmp_cis.cis_trade t
WHERE UPPER(t.status) = 'VALIDATED';
