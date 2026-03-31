"""
Trade Views

Implements Maker-Checker workflow for trade management.
Validates Portfolio, Security, and Counterparty before trade creation.

Workflow:
  MAKER Side:
    - Create Trade -> INITIAL
    - Update Trade -> MODIFIED
    - Cancel Trade -> CANCELLED
    - Submit for Validation -> PENDING_VALIDATION

  CHECKER Side:
    - Validate -> VALIDATED (or CANCELLED if rejected)
    - Settle -> SETTLED (final active state)
"""

import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, Http404, JsonResponse
from django.views.decorators.http import require_http_methods
import csv

logger = logging.getLogger(__name__)

from core.audit.audit_kudu_repository import audit_log_kudu_repository
from trade.repositories.trade_kudu_repository import trade_kudu_repository, TradeKuduRepository
from trade.repositories.trade_validation_repository import trade_validation_repository
from trade.services.trade_dropdown_service import trade_dropdown_service
from trade.services.multicurrency_service import multicurrency_service


class TradeWrapper:
    """Wrapper to convert Kudu dict data to object with attributes for template compatibility."""

    def __init__(self, data, index=0):
        self.data = data
        self.trade_id = data.get('trade_id', 0)
        self.deal_number = data.get('deal_number', '')
        self.trade_type = data.get('trade_type', '')

        # Portfolio & Security
        self.portfolio_short_name = data.get('portfolio_short_name', '')
        self.portfolio_full_name = data.get('portfolio_full_name', '')
        self.security_label = data.get('security_label', '')
        self.security_full_name = data.get('security_full_name', '')
        self.security_type = data.get('security_type', '')
        self.currency_code = data.get('currency_code', '')  # Portfolio Currency (Local CCY)
        self.security_currency = data.get('security_currency', '')  # Security Currency (Foreign CCY)

        # Dates & Quantities
        self.trade_status = data.get('trade_status', '')
        self.trade_date = data.get('trade_date', '')
        self.settle_date = data.get('settle_date', '')
        self.quantity = data.get('quantity', 0)
        self.face_value = data.get('face_value', 0)
        self.lot = data.get('lot', 0)
        self.price = data.get('price', 0)

        # Costs
        self.commission = data.get('commission', 0)
        self.accrued_interest = data.get('accrued_interest', 0)
        self.sec_fee = data.get('sec_fee', 0)
        self.other_charges = data.get('other_charges', 0)
        self.total_amount = data.get('total_amount', 0)  # Total Amount (legacy)

        # Multi-currency fields (FC = Security CCY, LC = Portfolio CCY)
        self.portfolio_currency = data.get('portfolio_currency', '')  # Local Currency
        self.fx_rate = data.get('open_fx_rate', 1.0)  # FX Rate (FC->LC)
        # total_amount_fc: Use new column if available, fallback to total_amount for backward compatibility
        self.total_amount_fc = data.get('total_amount_fc') or data.get('total_amount', 0)
        self.total_amount_lc = data.get('total_amount_lc', 0)  # Total Amount LC (Local Currency)

        # GL & Broker
        self.open_close_position = data.get('open_close_position', '')
        self.extension = data.get('extension', '')
        self.brokers = data.get('brokers', '')
        self.broker_name = data.get('broker_name', '')
        self.gl_fund_type = data.get('gl_fund_type', '')
        self.gl_cost_centre = data.get('gl_cost_centre', '')
        self.gl_account_code = data.get('gl_account_code', '')
        self.contract_ref = data.get('contract_ref', '')
        self.fd_receipt = data.get('fd_receipt', '')
        self.org_pur_date = data.get('org_pur_date', '')

        # FX & Dealing
        self.open_fx_rate = data.get('open_fx_rate', 0)
        self.curr_dealing = data.get('curr_dealing', 0)
        self.open_dealing = data.get('open_dealing', 0)
        self.input_tax_oth = data.get('input_tax_oth', 0)
        self.qty_entitled = data.get('qty_entitled', 0)

        # Post-trade
        self.selling_rule = data.get('selling_rule', '')
        self.cash_balance = data.get('cash_balance', 0)
        self.custodian = data.get('custodian', '')
        self.amor_accr_method = data.get('amor_accr_method', '')
        self.lots_held = data.get('lots_held', 0)
        self.quantity_held = data.get('quantity_held', 0)
        self.remarks = data.get('remarks', '')
        self.counterparty = data.get('counterparty', '')

        # UDF fields
        self.udf_fund_type = data.get('udf_fund_type', '')
        self.udf_section_31_26 = data.get('udf_section_31_26', '')
        self.udf_sub_custodian = data.get('udf_sub_custodian', '')
        self.udf_disclosure_req = data.get('udf_disclosure_req', False)
        self.udf_counter_pledged = data.get('udf_counter_pledged', False)
        self.udf_revision_code = data.get('udf_revision_code', '')
        self.udf_uobn_uobn_hk = data.get('udf_uobn_uobn_hk', '')
        self.udf_income_exp_type = data.get('udf_income_exp_type', '')
        self.udf_currency_hedge = data.get('udf_currency_hedge', False)

        # Broker charge fields (auto-calculated from cis_trade_charge_lut)
        self.charge_fee_type = data.get('charge_fee_type', '')
        self.charge_exchange = data.get('charge_exchange', '')
        self.charge_country = data.get('charge_country', '')
        self.charge_fee_rule = data.get('charge_fee_rule', '')
        self.charge_fee_value = data.get('charge_fee_value', 0)
        self.calculated_commission = data.get('calculated_commission', 0)
        self.calculated_clearing_fee = data.get('calculated_clearing_fee', 0)
        self.calculated_trading_fee = data.get('calculated_trading_fee', 0)
        self.calculated_gst = data.get('calculated_gst', 0)
        self.calculated_other_fees = data.get('calculated_other_fees', 0)
        self.total_calculated_charges = data.get('total_calculated_charges', 0)
        self.charges_auto_calculated = data.get('charges_auto_calculated', False)

        # Workflow status
        self.status = data.get('status', 'INITIAL')
        self.is_active = data.get('is_active', False)
        self.is_deleted = data.get('is_deleted', False)
        self.src_system = data.get('src_system', 'CIS')

        # Audit fields
        self.created_by = data.get('created_by', '')
        self.created_at = data.get('created_at', '')
        self.updated_by = data.get('updated_by', '')
        self.updated_at = data.get('updated_at', '')

        # Workflow fields
        self.submitted_by = data.get('submitted_by', '')
        self.submitted_at = data.get('submitted_at', '')
        self.validated_by = data.get('validated_by', '')
        self.validated_at = data.get('validated_at', '')
        self.validation_comments = data.get('validation_comments', '')
        self.settled_by = data.get('settled_by', '')
        self.settled_at = data.get('settled_at', '')
        self.settlement_comments = data.get('settlement_comments', '')
        self.cancelled_by = data.get('cancelled_by', '')
        self.cancelled_at = data.get('cancelled_at', '')
        self.cancel_reason = data.get('cancel_reason', '')


def get_user_info(request):
    """Get user info from session."""
    return {
        'username': request.session.get('user_login', 'anonymous'),
        'user_id': str(request.session.get('user_id', '')),
        'user_email': request.session.get('user_email', '')
    }


# =============================================================================
# TRADE LIST
# =============================================================================

def trade_list(request):
    """List all trades with search, filter, and CSV export."""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    perf_start = time.time()

    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    trade_type_filter = request.GET.get('trade_type', '').strip()
    trade_date_from = request.GET.get('trade_date_from', '').strip()
    trade_date_to = request.GET.get('trade_date_to', '').strip()
    # New filters per SA feedback #2
    src_system_filter = request.GET.get('src_system', '').strip()
    settle_date_from = request.GET.get('settle_date_from', '').strip()
    settle_date_to = request.GET.get('settle_date_to', '').strip()
    export = request.GET.get('export', '').strip()

    # Multi-select portfolios (comma-separated or list)
    portfolio_filter = request.GET.getlist('portfolios')
    if not portfolio_filter:
        # Fallback to single portfolio param
        single_portfolio = request.GET.get('portfolio', '').strip()
        if single_portfolio:
            portfolio_filter = [single_portfolio]

    # Multi-select securities (comma-separated or list)
    security_filter = request.GET.getlist('securities')
    if not security_filter:
        # Fallback to single security param
        single_security = request.GET.get('security', '').strip()
        if single_security:
            security_filter = [single_security]

    # PERFORMANCE: Execute main trade query, statistics, and dropdowns in parallel
    # This reduces total time from sequential (query + stats + dropdowns) to max(query, stats, dropdowns)
    trades_data = []
    stats = {}
    dropdown_options = {}

    def fetch_trades():
        return trade_kudu_repository.get_all_trades_multi_filter(
            limit=1000,
            trade_type=trade_type_filter if trade_type_filter else None,
            status=status_filter if status_filter else None,
            portfolios=portfolio_filter if portfolio_filter else None,
            securities=security_filter if security_filter else None,
            search=search_query if search_query else None,
            trade_date_from=trade_date_from if trade_date_from else None,
            trade_date_to=trade_date_to if trade_date_to else None,
            src_system=src_system_filter if src_system_filter else None,
            settle_date_from=settle_date_from if settle_date_from else None,
            settle_date_to=settle_date_to if settle_date_to else None
        )

    def fetch_stats():
        return trade_kudu_repository.get_trade_statistics()

    def fetch_dropdowns():
        return trade_dropdown_service.get_all_dropdown_options()

    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_trades = executor.submit(fetch_trades)
            future_stats = executor.submit(fetch_stats)
            future_dropdowns = executor.submit(fetch_dropdowns)

            # Wait for all to complete (max 30 seconds)
            trades_data = future_trades.result(timeout=30)
            stats = future_stats.result(timeout=30)
            dropdown_options = future_dropdowns.result(timeout=30)
    except Exception as e:
        logger.error(f"[PERF] Parallel fetch failed: {e}, falling back to sequential")
        # Fallback to sequential
        trades_data = fetch_trades()
        stats = fetch_stats()
        dropdown_options = fetch_dropdowns()

    logger.info(f"[PERF] Trade list parallel fetch took {(time.time() - perf_start)*1000:.0f}ms")

    # Calculate Total Amount LC for each trade using FX rates
    # FC (Foreign Currency) = Security Currency (currency_code)
    # LC (Local Currency) = Portfolio Currency (portfolio_currency)
    # PERFORMANCE: Batch fetch all unique currency pairs in single query
    currency_pairs = []
    for trade in trades_data:
        fc = trade.get('currency_code', '')  # Security/Foreign Currency
        lc = trade.get('portfolio_currency', '')  # Portfolio/Local Currency
        if not lc:
            lc = fc
            trade['portfolio_currency'] = fc
        if fc and lc and fc != lc:
            currency_pairs.append((fc, lc))

    # Batch fetch FX rates (single DB query)
    fx_rates_batch = multicurrency_service.get_fx_rates_batch(list(set(currency_pairs))) if currency_pairs else {}

    # Apply FX rates to trades
    for trade in trades_data:
        fc = trade.get('currency_code', '')
        lc = trade.get('portfolio_currency', '')
        total_fc = Decimal(str(trade.get('total_amount', 0) or 0))

        if fc and lc and fc != lc:
            fx_key = f"{fc}-{lc}"
            if fx_key in fx_rates_batch:
                fx_rate, _ = fx_rates_batch[fx_key]
                total_lc = (total_fc * fx_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                trade['fx_rate'] = float(fx_rate)
                trade['total_amount_lc'] = float(total_lc)
            else:
                # Fallback - shouldn't happen after batch fetch
                trade['fx_rate'] = 1.0
                trade['total_amount_lc'] = float(total_fc)
        else:
            # Same currency - no conversion needed, LC = FC
            trade['fx_rate'] = 1.0
            trade['total_amount_lc'] = float(total_fc)

    wrapped_trades = [TradeWrapper(t, idx) for idx, t in enumerate(trades_data)]

    # CSV Export
    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="trades.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Deal Number', 'Type', 'Portfolio', 'Security',
            'Trade Date', 'Settle Date', 'Quantity', 'Price',
            'Total Amount', 'Status'
        ])

        for trade in trades_data:
            writer.writerow([
                trade.get('deal_number', ''),
                trade.get('trade_type', ''),
                trade.get('portfolio_short_name', ''),
                trade.get('security_label', ''),
                trade.get('trade_date', ''),
                trade.get('settle_date', ''),
                trade.get('quantity', ''),
                trade.get('price', ''),
                trade.get('total_amount', ''),
                trade.get('status', '')
            ])

        user_info = get_user_info(request)
        audit_log_kudu_repository.log_action_async(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type='EXPORT',
            entity_type='TRADE',
            entity_name='Trade List',
            action_description=f'Exported {len(trades_data)} trades to CSV',
            status='SUCCESS',
            request_method='GET',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        return response

    # Pagination
    paginator = Paginator(wrapped_trades, 25)
    page = request.GET.get('page', 1)

    try:
        trades = paginator.page(page)
    except PageNotAnInteger:
        trades = paginator.page(1)
    except EmptyPage:
        trades = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # Note: stats and dropdown_options already fetched in parallel at the top of the function

    # Status options for filter dropdown
    status_options = [
        ('', 'All Statuses'),
        (TradeKuduRepository.STATUS_INITIAL, 'Initial'),
        (TradeKuduRepository.STATUS_MODIFIED, 'Modified'),
        (TradeKuduRepository.STATUS_PENDING_VALIDATION, 'Pending Validation'),
        (TradeKuduRepository.STATUS_VALIDATED, 'Validated'),
        (TradeKuduRepository.STATUS_SETTLED, 'Settled'),
        (TradeKuduRepository.STATUS_CANCELLED, 'Cancelled'),
    ]

    context = {
        'page_obj': trades,
        'search_query': search_query,
        'status_filter': status_filter,
        'trade_type_filter': trade_type_filter,
        'selected_portfolios': portfolio_filter,  # List of selected portfolio names
        'selected_securities': security_filter,   # List of selected security names
        'trade_date_from': trade_date_from,
        'trade_date_to': trade_date_to,
        # New filters per SA feedback #2
        'src_system_filter': src_system_filter,
        'settle_date_from': settle_date_from,
        'settle_date_to': settle_date_to,
        'total_count': len(trades_data),
        'status_options': status_options,
        'trade_types': dropdown_options.get('trade_types', []),
        'portfolios': dropdown_options.get('portfolios', []),
        'securities': dropdown_options.get('securities', []),
        'stats': stats,
        'pending_validation_count': stats.get('pending_validation', 0),
        'pending_settlement_count': stats.get('pending_settlement', 0),
    }

    return render(request, 'trade/trade_list.html', context)


def trade_dashboard(request):
    """Trade dashboard with statistics."""
    stats = trade_kudu_repository.get_trade_statistics()

    context = {
        'stats': stats,
    }

    return render(request, 'trade/trade_dashboard.html', context)


# =============================================================================
# TRADE DETAIL
# =============================================================================

def trade_detail(request, trade_id):
    """View trade details."""
    import time

    # Retry logic for Kudu eventual consistency
    trade_data = None
    max_retries = 3
    retry_delay = 0.5  # seconds

    for attempt in range(max_retries):
        trade_data = trade_kudu_repository.get_trade_by_id(trade_id)
        if trade_data:
            break
        if attempt < max_retries - 1:
            time.sleep(retry_delay)

    if not trade_data:
        raise Http404(f"Trade '{trade_id}' not found")

    # Fetch security currency if not present in trade data
    if not trade_data.get('security_currency') and trade_data.get('security_label'):
        security_details = trade_validation_repository.get_security_details(trade_data.get('security_label'))
        if security_details:
            trade_data['security_currency'] = security_details.get('currency_code', '')

    # Use stored total_amount_lc if available, otherwise calculate
    # total_amount_fc = Security Currency amount, total_amount_lc = Portfolio Currency amount
    stored_lc = trade_data.get('total_amount_lc')
    if stored_lc and float(stored_lc) != 0:
        # Use the stored value from database
        trade_data['total_amount_lc'] = float(stored_lc)
        trade_data['fx_rate'] = trade_data.get('open_fx_rate', 1.0)
    else:
        # Calculate Total Amount LC if not stored
        fc = trade_data.get('currency_code', '')  # Security/Foreign Currency
        lc = trade_data.get('portfolio_currency', '')  # Portfolio/Local Currency
        # Use total_amount_fc if available, fallback to total_amount
        total_fc = Decimal(str(trade_data.get('total_amount_fc') or trade_data.get('total_amount', 0) or 0))

        if not lc:
            lc = fc
            trade_data['portfolio_currency'] = fc

        if fc and lc and fc != lc:
            try:
                fx_rate, _ = multicurrency_service.get_fx_rate(fc, lc)
                total_lc = (total_fc * fx_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                trade_data['fx_rate'] = float(fx_rate)
                trade_data['total_amount_lc'] = float(total_lc)
            except Exception as e:
                logger.warning(f"FX rate lookup failed for {fc}->{lc}: {e}")
                trade_data['fx_rate'] = 1.0
                trade_data['total_amount_lc'] = float(total_fc)
        else:
            trade_data['fx_rate'] = 1.0
            trade_data['total_amount_lc'] = float(total_fc)

    trade = TradeWrapper(trade_data)
    status = trade.status
    src_system = trade.src_system

    # Determine allowed actions based on status and source system
    is_cis_record = src_system and src_system.upper() == 'CIS'

    # Maker actions (only for CIS records)
    can_edit = is_cis_record and status in TradeKuduRepository.MAKER_EDITABLE_STATUSES
    can_submit = is_cis_record and status in [TradeKuduRepository.STATUS_INITIAL, TradeKuduRepository.STATUS_MODIFIED]
    can_cancel = is_cis_record and status in [
        TradeKuduRepository.STATUS_INITIAL,
        TradeKuduRepository.STATUS_MODIFIED,
        TradeKuduRepository.STATUS_PENDING_VALIDATION
    ]
    can_reactivate = is_cis_record and status == TradeKuduRepository.STATUS_CANCELLED

    # Checker actions (only for CIS records)
    can_validate = is_cis_record and status == TradeKuduRepository.STATUS_PENDING_VALIDATION
    can_reject = is_cis_record and status == TradeKuduRepository.STATUS_PENDING_VALIDATION
    can_settle = is_cis_record and status == TradeKuduRepository.STATUS_VALIDATED

    # Get trade history
    history = trade_kudu_repository.get_trade_history(trade_id)

    # ========================================================================
    # POSITION IMPACT DISPLAY - DISABLED
    # Uncomment the following code to show position info for settled trades.
    # Also requires uncommenting PositionWrapper class and position views.
    # ========================================================================
    position = None
    # if status == TradeKuduRepository.STATUS_SETTLED:
    #     portfolio = trade_data.get('portfolio_short_name', '')
    #     security = trade_data.get('security_label', '')
    #     if portfolio and security:
    #         position_data = trade_kudu_repository.get_position(portfolio, security)
    #         if position_data:
    #             position = PositionWrapper(position_data)

    context = {
        'trade': trade,
        'history': history,
        'position': position,
        'can_edit': can_edit,
        'can_submit': can_submit,
        'can_cancel': can_cancel,
        'can_reactivate': can_reactivate,
        'can_validate': can_validate,
        'can_reject': can_reject,
        'can_settle': can_settle,
        'is_cis_record': is_cis_record,
    }

    return render(request, 'trade/trade_detail.html', context)


# =============================================================================
# TRADE CREATE
# =============================================================================

def trade_create(request, trade_type=None):
    """Create a new trade (Maker action: Create -> INITIAL)."""
    # Performance: Only load dropdowns for GET requests
    # POST requests don't need full dropdowns unless validation fails
    dropdown_options = None

    if request.method == 'POST':
        import time
        perf_start = time.time()
        try:
            user_info = get_user_info(request)

            # Collect form data
            trade_data = {
                'trade_type': request.POST.get('trade_type', trade_type or 'BUY'),
                'portfolio_short_name': request.POST.get('portfolio_short_name', '').strip(),
                'currency_code': request.POST.get('currency_code', '').strip(),
                'security_label': request.POST.get('security_label', '').strip(),
                'trade_status': request.POST.get('trade_status', ''),
                'trade_date': request.POST.get('trade_date', ''),
                'settle_date': request.POST.get('settle_date', ''),
                'quantity': request.POST.get('quantity', 0),
                'face_value': request.POST.get('face_value', 0),
                'lot': request.POST.get('lot', 0),
                'price': request.POST.get('price', 0),
                'commission': request.POST.get('commission', 0),
                'sec_fee': request.POST.get('sec_fee', 0),
                'other_charges': request.POST.get('other_charges', 0),
                'total_amount': request.POST.get('total_amount', 0),
                'total_amount_fc': request.POST.get('total_amount_fc', 0),
                'total_amount_lc': request.POST.get('total_amount_lc', 0),
                'open_close_position': request.POST.get('open_close_position', ''),
                'extension': request.POST.get('extension', ''),
                'brokers': request.POST.get('brokers', ''),
                'broker_name': request.POST.get('broker_name', ''),
                'gl_fund_type': request.POST.get('gl_fund_type', ''),
                'gl_cost_centre': request.POST.get('gl_cost_centre', ''),
                'gl_account_code': request.POST.get('gl_account_code', ''),
                'contract_ref': request.POST.get('contract_ref', ''),
                'fd_receipt': request.POST.get('fd_receipt', ''),
                'org_pur_date': request.POST.get('org_pur_date', ''),
                'open_fx_rate': request.POST.get('open_fx_rate', 0),
                'curr_dealing': request.POST.get('curr_dealing', 0),
                'open_dealing': request.POST.get('open_dealing', 0),
                'input_tax_oth': request.POST.get('input_tax_oth', 0),
                'qty_entitled': request.POST.get('qty_entitled', 0),
                'selling_rule': request.POST.get('selling_rule', ''),
                'cash_balance': request.POST.get('cash_balance', 0),
                'custodian': request.POST.get('custodian', ''),
                'amor_accr_method': request.POST.get('amor_accr_method', ''),
                'remarks': request.POST.get('remarks', ''),
                'counterparty': request.POST.get('counterparty', ''),
                # UDF fields
                'udf_fund_type': request.POST.get('udf_fund_type', ''),
                'udf_section_31_26': request.POST.get('udf_section_31_26', ''),
                'udf_sub_custodian': request.POST.get('udf_sub_custodian', ''),
                'udf_disclosure_req': request.POST.get('udf_disclosure_req', '') == 'on',
                'udf_counter_pledged': request.POST.get('udf_counter_pledged', '') == 'on',
                'udf_revision_code': request.POST.get('udf_revision_code', ''),
                'udf_uobn_uobn_hk': request.POST.get('udf_uobn_uobn_hk', ''),
                'udf_income_exp_type': request.POST.get('udf_income_exp_type', ''),
                'udf_currency_hedge': request.POST.get('udf_currency_hedge', '') == 'on',
                # Broker charge fields (auto-calculated from cis_trade_charge_lut)
                'charge_fee_type': request.POST.get('charge_fee_type', ''),
                'charge_exchange': request.POST.get('hidden_charge_exchange', '') or request.POST.get('charge_exchange', ''),
                'charge_country': request.POST.get('charge_country', ''),
                'charge_fee_rule': request.POST.get('charge_fee_rule', ''),
                'charge_fee_value': request.POST.get('charge_fee_value', 0),
                'calculated_commission': request.POST.get('calculated_commission', 0),
                'calculated_clearing_fee': request.POST.get('calculated_clearing_fee', 0),
                'calculated_trading_fee': request.POST.get('calculated_trading_fee', 0),
                'calculated_gst': request.POST.get('calculated_gst', 0),
                'calculated_other_fees': request.POST.get('calculated_other_fees', 0),
                'total_calculated_charges': request.POST.get('total_calculated_charges', 0),
                'charges_auto_calculated': request.POST.get('charges_auto_calculated', 'false') == 'true',
            }

            # Validate trade data (includes Portfolio, Security, Counterparty validation)
            # entity_details contains portfolio and security dicts for reuse
            perf_validate_start = time.time()
            is_valid, errors, entity_details = trade_kudu_repository.validate_trade_data(trade_data)
            logger.info(f"[PERF] Trade validation took {(time.time() - perf_validate_start)*1000:.0f}ms")

            if not is_valid:
                for error in errors:
                    messages.error(request, error)
                context = {
                    'dropdown_options': dropdown_options,
                    'trade': trade_data,
                    'trade_type': trade_type or trade_data.get('trade_type'),
                }
                return render(request, 'trade/trade_form.html', context)

            # Insert trade using FAST method with skip_validation=True
            # Pass entity_details to avoid duplicate DB queries for portfolio/security
            perf_insert_start = time.time()
            trade_id = trade_kudu_repository.insert_trade_fast(
                trade_data,
                created_by=user_info['username'],
                skip_validation=True,  # Already validated above
                entity_details=entity_details  # Reuse portfolio/security from validation
            )
            logger.info(f"[PERF] Trade insert took {(time.time() - perf_insert_start)*1000:.0f}ms")

            if not trade_id:
                raise Exception("Failed to create trade")

            # Audit logging is also async (non-blocking)
            audit_log_kudu_repository.log_action_async(
                user_id=user_info['user_id'],
                username=user_info['username'],
                user_email=user_info['user_email'],
                action_type='CREATE',
                entity_type='TRADE',
                entity_id=str(trade_id),
                entity_name=f"{trade_data['trade_type']} - {trade_data['security_label']}",
                action_description=f"Created {trade_data['trade_type']} trade for {trade_data['security_label']} (INITIAL status)",
                new_value=json.dumps(trade_data, default=str),
                request_method='POST',
                request_path=request.path,
                request_params=json.dumps(dict(request.POST)) if request.POST else None,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            total_time = (time.time() - perf_start) * 1000
            logger.info(f"[PERF] Total trade create took {total_time:.0f}ms")
            messages.success(request, f'Trade {trade_id} created with INITIAL status. Submit for validation when ready.')
            # Redirect to trade list instead of detail to avoid Kudu sync delay issues
            return redirect('trade:list')

        except ValueError as e:
            messages.error(request, str(e))
            # Only load dropdowns if validation fails and we need to re-render form
            dropdown_options = trade_dropdown_service.get_all_dropdown_options()
        except Exception as e:
            messages.error(request, f'Error creating trade: {str(e)}')
            # Only load dropdowns if error and we need to re-render form
            dropdown_options = trade_dropdown_service.get_all_dropdown_options()

    # GET request - load dropdowns for form display
    if dropdown_options is None:
        import time
        perf_dropdown_start = time.time()
        dropdown_options = trade_dropdown_service.get_all_dropdown_options()
        logger.info(f"[PERF] GET /trade/create/ dropdown loading took {(time.time() - perf_dropdown_start)*1000:.0f}ms")

    context = {
        'dropdown_options': dropdown_options,
        'trade_type': trade_type,
    }

    return render(request, 'trade/trade_form.html', context)


# =============================================================================
# TRADE EDIT
# =============================================================================

def trade_edit(request, trade_id):
    """Edit trade (Maker action: Update -> MODIFIED)."""
    trade_data = trade_kudu_repository.get_trade_by_id(trade_id)

    if not trade_data:
        messages.error(request, f'Trade {trade_id} not found')
        return redirect('trade:list')

    user_info = get_user_info(request)
    current_status = trade_data.get('status', '')
    src_system = trade_data.get('src_system', '')

    # Only CIS records in editable status can be edited
    if src_system and src_system.upper() != 'CIS':
        messages.error(request, 'Cannot edit GMP records. Only CIS records can be edited.')
        return redirect('trade:detail', trade_id=trade_id)

    if current_status not in TradeKuduRepository.MAKER_EDITABLE_STATUSES:
        messages.error(request, f'Cannot edit trade with status "{current_status}".')
        return redirect('trade:detail', trade_id=trade_id)

    # Performance: Only load dropdowns for GET or when POST fails
    dropdown_options = None

    if request.method == 'POST':
        try:
            # Collect form data (same as create)
            updated_data = {
                'currency_code': request.POST.get('currency_code', '').strip(),
                'trade_status': request.POST.get('trade_status', ''),
                'trade_date': request.POST.get('trade_date', ''),
                'settle_date': request.POST.get('settle_date', ''),
                'quantity': request.POST.get('quantity', 0),
                'face_value': request.POST.get('face_value', 0),
                'lot': request.POST.get('lot', 0),
                'price': request.POST.get('price', 0),
                'commission': request.POST.get('commission', 0),
                'sec_fee': request.POST.get('sec_fee', 0),
                'other_charges': request.POST.get('other_charges', 0),
                'total_amount': request.POST.get('total_amount', 0),
                'total_amount_fc': request.POST.get('total_amount_fc', 0),
                'total_amount_lc': request.POST.get('total_amount_lc', 0),
                'open_close_position': request.POST.get('open_close_position', ''),
                'extension': request.POST.get('extension', ''),
                'brokers': request.POST.get('brokers', ''),
                'broker_name': request.POST.get('broker_name', ''),
                'gl_fund_type': request.POST.get('gl_fund_type', ''),
                'gl_cost_centre': request.POST.get('gl_cost_centre', ''),
                'gl_account_code': request.POST.get('gl_account_code', ''),
                'contract_ref': request.POST.get('contract_ref', ''),
                'fd_receipt': request.POST.get('fd_receipt', ''),
                'org_pur_date': request.POST.get('org_pur_date', ''),
                'open_fx_rate': request.POST.get('open_fx_rate', 0),
                'curr_dealing': request.POST.get('curr_dealing', 0),
                'open_dealing': request.POST.get('open_dealing', 0),
                'input_tax_oth': request.POST.get('input_tax_oth', 0),
                'qty_entitled': request.POST.get('qty_entitled', 0),
                'selling_rule': request.POST.get('selling_rule', ''),
                'cash_balance': request.POST.get('cash_balance', 0),
                'custodian': request.POST.get('custodian', ''),
                'amor_accr_method': request.POST.get('amor_accr_method', ''),
                'remarks': request.POST.get('remarks', ''),
                'counterparty': request.POST.get('counterparty', ''),
                # UDF fields
                'udf_fund_type': request.POST.get('udf_fund_type', ''),
                'udf_section_31_26': request.POST.get('udf_section_31_26', ''),
                'udf_sub_custodian': request.POST.get('udf_sub_custodian', ''),
                'udf_disclosure_req': request.POST.get('udf_disclosure_req', '') == 'on',
                'udf_counter_pledged': request.POST.get('udf_counter_pledged', '') == 'on',
                'udf_revision_code': request.POST.get('udf_revision_code', ''),
                'udf_uobn_uobn_hk': request.POST.get('udf_uobn_uobn_hk', ''),
                'udf_income_exp_type': request.POST.get('udf_income_exp_type', ''),
                'udf_currency_hedge': request.POST.get('udf_currency_hedge', '') == 'on',
                # Broker charge fields (auto-calculated from cis_trade_charge_lut)
                'charge_fee_type': request.POST.get('charge_fee_type', ''),
                'charge_exchange': request.POST.get('hidden_charge_exchange', '') or request.POST.get('charge_exchange', ''),
                'charge_country': request.POST.get('charge_country', ''),
                'charge_fee_rule': request.POST.get('charge_fee_rule', ''),
                'charge_fee_value': request.POST.get('charge_fee_value', 0),
                'calculated_commission': request.POST.get('calculated_commission', 0),
                'calculated_clearing_fee': request.POST.get('calculated_clearing_fee', 0),
                'calculated_trading_fee': request.POST.get('calculated_trading_fee', 0),
                'calculated_gst': request.POST.get('calculated_gst', 0),
                'calculated_other_fees': request.POST.get('calculated_other_fees', 0),
                'total_calculated_charges': request.POST.get('total_calculated_charges', 0),
                'charges_auto_calculated': request.POST.get('charges_auto_calculated', 'false') == 'true',
            }

            # Keep portfolio and security from original (can't change)
            updated_data['portfolio_short_name'] = trade_data.get('portfolio_short_name', '')
            updated_data['security_label'] = trade_data.get('security_label', '')
            updated_data['trade_type'] = trade_data.get('trade_type', '')

            # Track changes for audit log
            changed_fields = []
            old_values = {}
            new_values = {}
            for key, new_val in updated_data.items():
                old_val = trade_data.get(key, '')
                # Convert to string for comparison
                old_str = str(old_val) if old_val is not None else ''
                new_str = str(new_val) if new_val is not None else ''
                if old_str != new_str:
                    changed_fields.append(key)
                    old_values[key] = old_str
                    new_values[key] = new_str

            success = trade_kudu_repository.update_trade(trade_id, updated_data, user_info['username'])

            if not success:
                raise Exception('Failed to update trade')

            # Check if position exists for this trade (was previously settled)
            from trade.services.trade_event_queue_service import trade_event_queue_service

            position_exists = trade_event_queue_service.check_position_exists(trade_id)
            logger.info(f"Trade {trade_id} position_exists={position_exists}")

            if position_exists:
                # Merge updated data with original trade data
                merged_trade_data = {**trade_data, **updated_data}

                # Queue position modify event to recalculate position
                trade_event_queue_service.queue_position_modify_event(
                    trade_id=trade_id,
                    deal_number=trade_data.get('deal_number', ''),
                    old_trade_data=trade_data,  # Original values
                    new_trade_data=merged_trade_data,  # Merged with updates
                    created_by=user_info['username']
                )
                logger.info(f"Queued POSITION_MODIFY event for trade {trade_id} (position exists)")
            else:
                logger.info(f"Trade {trade_id} has no position yet, will be calculated on settlement")

            # Use async audit logging for fast UI response
            audit_log_kudu_repository.log_action_async(
                user_id=user_info['user_id'],
                username=user_info['username'],
                user_email=user_info['user_email'],
                action_type='UPDATE',
                entity_type='TRADE',
                entity_id=str(trade_id),
                entity_name=trade_data.get('deal_number', ''),
                action_description=f'Updated trade {trade_id} (status set to MODIFIED)',
                field_name=', '.join(changed_fields) if changed_fields else None,
                old_value=json.dumps(old_values) if old_values else None,
                new_value=json.dumps(new_values) if new_values else None,
                request_method='POST',
                request_path=request.path,
                request_params=json.dumps(dict(request.POST)) if request.POST else None,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, f'Trade updated. Status set to MODIFIED.')
            return redirect('trade:detail', trade_id=trade_id)

        except Exception as e:
            messages.error(request, f'Error updating trade: {str(e)}')
            # Only load dropdowns if error and we need to re-render form
            dropdown_options = trade_dropdown_service.get_all_dropdown_options()

    # GET request or POST error - load dropdowns for form display
    if dropdown_options is None:
        dropdown_options = trade_dropdown_service.get_all_dropdown_options()

    context = {
        'trade': trade_data,
        'dropdown_options': dropdown_options,
        'is_edit': True,
    }

    return render(request, 'trade/trade_form.html', context)


# =============================================================================
# WORKFLOW ACTIONS
# =============================================================================

def trade_submit(request, trade_id):
    """Submit trade for validation (Maker action: Submit -> PENDING_VALIDATION)."""
    if request.method != 'POST':
        return redirect('trade:detail', trade_id=trade_id)

    trade_data = trade_kudu_repository.get_trade_by_id(trade_id)
    if not trade_data:
        messages.error(request, f'Trade {trade_id} not found')
        return redirect('trade:list')

    user_info = get_user_info(request)

    try:
        success = trade_kudu_repository.submit_for_validation(trade_id, user_info['username'])

        if not success:
            raise Exception('Failed to submit trade for validation')

        audit_log_kudu_repository.log_action_async(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type='SUBMIT',
            entity_type='TRADE',
            entity_id=str(trade_id),
            entity_name=trade_data.get('deal_number', ''),
            action_description=f'Submitted trade for validation: {trade_data.get("deal_number", "")}',
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        messages.success(request, f'Trade {trade_id} submitted for validation.')
    except Exception as e:
        messages.error(request, f'Error submitting trade: {str(e)}')

    # Redirect to pending validation list to avoid Kudu sync delay
    return redirect('trade:pending_validation')


def trade_validate(request, trade_id):
    """Validate or reject trade (Checker action)."""
    if request.method != 'POST':
        return redirect('trade:detail', trade_id=trade_id)

    trade_data = trade_kudu_repository.get_trade_by_id(trade_id)
    if not trade_data:
        messages.error(request, f'Trade {trade_id} not found')
        return redirect('trade:list')

    user_info = get_user_info(request)
    comments = request.POST.get('comments', '').strip()
    action = request.POST.get('action', 'approve')

    # Four-eyes check
    submitted_by = trade_data.get('submitted_by', '')
    if submitted_by and submitted_by == user_info['username']:
        messages.error(request, 'Four-eyes principle: You cannot validate your own submission.')
        return redirect('trade:detail', trade_id=trade_id)

    try:
        if action == 'reject':
            success = trade_kudu_repository.reject_trade(trade_id, user_info['username'], comments)
            action_type = 'REJECT'
            success_msg = 'Trade has been rejected.'
        else:
            success = trade_kudu_repository.validate_trade(trade_id, user_info['username'], comments)
            action_type = 'VALIDATE'
            success_msg = 'Trade validated. Ready for settlement.'

        if not success:
            raise Exception(f'Failed to {action} trade')

        audit_log_kudu_repository.log_action_async(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type=action_type,
            entity_type='TRADE',
            entity_id=str(trade_id),
            entity_name=trade_data.get('deal_number', ''),
            action_description=f'{action_type} trade: {trade_data.get("deal_number", "")}',
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        if action == 'reject':
            messages.warning(request, success_msg)
        else:
            messages.success(request, success_msg)

    except Exception as e:
        messages.error(request, f'Error processing trade: {str(e)}')

    return redirect('trade:detail', trade_id=trade_id)


def trade_settle(request, trade_id):
    """Settle trade (Checker action: Settle -> SETTLED)."""
    if request.method != 'POST':
        return redirect('trade:detail', trade_id=trade_id)

    trade_data = trade_kudu_repository.get_trade_by_id(trade_id)
    if not trade_data:
        messages.error(request, f'Trade {trade_id} not found')
        return redirect('trade:list')

    user_info = get_user_info(request)
    comments = request.POST.get('comments', '').strip()

    try:
        success = trade_kudu_repository.settle_trade(trade_id, user_info['username'], comments)

        if not success:
            raise Exception('Failed to settle trade')

        # Use async audit logging to avoid blocking UI
        audit_log_kudu_repository.log_action_async(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type='SETTLE',
            entity_type='TRADE',
            entity_id=str(trade_id),
            entity_name=trade_data.get('deal_number', ''),
            action_description=f'Settled trade: {trade_data.get("deal_number", "")}',
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        messages.success(request, 'Trade settled and is now ACTIVE!')
    except Exception as e:
        messages.error(request, f'Error settling trade: {str(e)}')

    return redirect('trade:detail', trade_id=trade_id)


def trade_cancel(request, trade_id):
    """Cancel trade."""
    if request.method != 'POST':
        return redirect('trade:detail', trade_id=trade_id)

    trade_data = trade_kudu_repository.get_trade_by_id(trade_id)
    if not trade_data:
        messages.error(request, f'Trade {trade_id} not found')
        return redirect('trade:list')

    user_info = get_user_info(request)
    reason = request.POST.get('reason', '').strip()

    try:
        success = trade_kudu_repository.soft_delete_trade(trade_id, user_info['username'], reason)

        if not success:
            raise Exception('Failed to cancel trade')

        # Handle position: either reverse or cancel pending events
        from trade.services.trade_event_queue_service import trade_event_queue_service

        if trade_event_queue_service.check_position_exists(trade_id):
            # Position exists - queue POSITION_CANCEL event to reverse
            trade_event_queue_service.queue_position_cancel_event(
                trade_id=trade_id,
                deal_number=trade_data.get('deal_number', ''),
                trade_data=trade_data,
                created_by=user_info['username']
            )
            logger.info(f"Queued POSITION_CANCEL event for trade {trade_id}")
        else:
            # Position not calculated yet - cancel any pending events
            cancelled_count, _ = trade_event_queue_service.cancel_pending_events(trade_id)
            if cancelled_count > 0:
                logger.info(f"Cancelled {cancelled_count} pending events for trade {trade_id}")

        # Prepare old values for audit (key trade details before cancellation)
        old_values = {
            'trade_type': trade_data.get('trade_type', ''),
            'portfolio_short_name': trade_data.get('portfolio_short_name', ''),
            'security_label': trade_data.get('security_label', ''),
            'quantity': str(trade_data.get('quantity', '')),
            'price': str(trade_data.get('price', '')),
            'total_amount': str(trade_data.get('total_amount', '')),
            'status': trade_data.get('status', ''),
        }

        audit_log_kudu_repository.log_action_async(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type='DELETE',
            entity_type='TRADE',
            entity_id=str(trade_id),
            entity_name=trade_data.get('deal_number', ''),
            action_description=f'Cancelled/Deleted trade: {trade_data.get("deal_number", "")}' + (f'. Reason: {reason}' if reason else ''),
            field_name='status',
            old_value=json.dumps(old_values),
            new_value=json.dumps({'status': 'CANCELLED', 'cancel_reason': reason}),
            request_method='POST',
            request_path=request.path,
            request_params=json.dumps(dict(request.POST)) if request.POST else None,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        messages.warning(request, 'Trade has been cancelled.')
    except Exception as e:
        messages.error(request, f'Error cancelling trade: {str(e)}')

    return redirect('trade:detail', trade_id=trade_id)


def trade_reactivate(request, trade_id):
    """Reactivate cancelled trade."""
    if request.method != 'POST':
        return redirect('trade:detail', trade_id=trade_id)

    messages.info(request, 'Reactivate functionality not yet implemented.')
    return redirect('trade:detail', trade_id=trade_id)


def trade_delete(request, trade_id):
    """Soft delete trade."""
    return trade_cancel(request, trade_id)


# =============================================================================
# APPROVAL QUEUES
# =============================================================================

def pending_validation(request):
    """List trades pending validation (for Checkers)."""
    trades_data = trade_kudu_repository.get_pending_validation_trades()
    wrapped_trades = [TradeWrapper(t, idx) for idx, t in enumerate(trades_data)]

    stats = trade_kudu_repository.get_trade_statistics()

    context = {
        'trades': wrapped_trades,
        'pending_count': len(trades_data),
        'view_type': 'validation',
        'pending_validation_count': stats.get('pending_validation', 0),
        'pending_settlement_count': stats.get('pending_settlement', 0),
    }

    return render(request, 'trade/pending_approvals.html', context)


def pending_settlement(request):
    """List validated trades ready for settlement (for Checkers)."""
    trades_data = trade_kudu_repository.get_pending_settlement_trades()
    wrapped_trades = [TradeWrapper(t, idx) for idx, t in enumerate(trades_data)]

    stats = trade_kudu_repository.get_trade_statistics()

    context = {
        'trades': wrapped_trades,
        'pending_count': len(trades_data),
        'view_type': 'settlement',
        'pending_validation_count': stats.get('pending_validation', 0),
        'pending_settlement_count': stats.get('pending_settlement', 0),
    }

    return render(request, 'trade/pending_approvals.html', context)


# =============================================================================
# HISTORY
# =============================================================================

def trade_history(request, trade_id):
    """View trade history."""
    trade_data = trade_kudu_repository.get_trade_by_id(trade_id)
    if not trade_data:
        raise Http404(f"Trade {trade_id} not found")

    history = trade_kudu_repository.get_trade_history(trade_id)

    context = {
        'trade': TradeWrapper(trade_data),
        'history': history,
    }

    return render(request, 'trade/trade_history.html', context)


# =============================================================================
# API ENDPOINTS FOR AJAX VALIDATION
# =============================================================================

@require_http_methods(["GET"])
def api_validate_portfolio(request):
    """API: Validate portfolio exists and is valid for trading."""
    portfolio_name = request.GET.get('name', '').strip()
    result = trade_validation_repository.validate_portfolio(portfolio_name)

    return JsonResponse({
        'is_valid': result.is_valid,
        'message': result.message,
        'details': result.details
    })


@require_http_methods(["GET"])
def api_validate_security(request):
    """API: Validate security exists and is valid for trading."""
    security_name = request.GET.get('name', '').strip()
    result = trade_validation_repository.validate_security(security_name)

    return JsonResponse({
        'is_valid': result.is_valid,
        'message': result.message,
        'details': result.details
    })


@require_http_methods(["GET"])
def api_validate_counterparty(request):
    """API: Validate counterparty exists and is active."""
    counterparty_name = request.GET.get('name', '').strip()
    result = trade_validation_repository.validate_counterparty(counterparty_name)

    return JsonResponse({
        'is_valid': result.is_valid,
        'message': result.message,
        'details': result.details
    })


@require_http_methods(["GET"])
def api_validate_settlement_date(request):
    """API: Validate settlement date is >= trade date."""
    trade_date = request.GET.get('trade_date', '').strip()
    settle_date = request.GET.get('settle_date', '').strip()

    result = trade_validation_repository.validate_settlement_date(trade_date, settle_date)

    return JsonResponse({
        'is_valid': result.is_valid,
        'message': result.message,
        'details': result.details
    })


@require_http_methods(["GET"])
def api_portfolios(request):
    """API: Get valid portfolios for dropdown (with search)."""
    search = request.GET.get('search', '').strip()
    portfolios = trade_dropdown_service.get_portfolios(search=search if search else None)

    return JsonResponse({'results': portfolios})


@require_http_methods(["GET"])
def api_securities(request):
    """API: Get valid securities for dropdown (with search)."""
    search = request.GET.get('search', '').strip()
    securities = trade_dropdown_service.get_securities(search=search if search else None)

    return JsonResponse({'results': securities})


@require_http_methods(["GET"])
def api_counterparties(request):
    """API: Get valid counterparties for dropdown (with search)."""
    search = request.GET.get('search', '').strip()
    counterparties = trade_dropdown_service.get_counterparties(search=search if search else None)

    return JsonResponse({'results': counterparties})


@require_http_methods(["GET"])
def api_get_position(request):
    """API: Get current position for portfolio-security."""
    portfolio = request.GET.get('portfolio', '').strip()
    security = request.GET.get('security', '').strip()

    position = trade_kudu_repository.get_position(portfolio, security)

    if position:
        return JsonResponse({
            'exists': True,
            'quantity': position.get('quantity', 0),
            'average_cost': position.get('average_cost', 0),
            'status': position.get('status', '')
        })
    else:
        return JsonResponse({
            'exists': False,
            'quantity': 0,
            'average_cost': 0,
            'status': ''
        })


@require_http_methods(["GET"])
def api_portfolios_detailed(request):
    """
    API: Get valid portfolios with full details for modal selection.
    Returns portfolio details including currency, manager, status for display.
    """
    search = request.GET.get('search', '').strip()
    portfolios = trade_validation_repository.get_valid_portfolios(search=search if search else None, limit=500)

    results = []
    for p in portfolios:
        results.append({
            'portfolio_short_name': p.get('portfolio_short_name', ''),
            'portfolio_full_name': p.get('portfolio_full_name', ''),
            'currency': p.get('currency', ''),
            'manager': p.get('manager', ''),
            'cash_balance': p.get('cash_balance', 0),
            'status': p.get('status', ''),
        })

    return JsonResponse({'results': results, 'total': len(results)})


@require_http_methods(["GET"])
def api_securities_detailed(request):
    """
    API: Get valid securities with full details for modal selection.
    Returns security details including type, ISIN, ticker, currency, price.
    """
    search = request.GET.get('search', '').strip()
    securities = trade_validation_repository.get_valid_securities(search=search if search else None)

    results = []
    for s in securities:
        results.append({
            'security_label': s.get('security_label', ''),
            'security_full_name': s.get('security_full_name', ''),
            'security_type': s.get('security_type', ''),
            'isin': s.get('isin', ''),
            'ticker': s.get('ticker', ''),
            'currency_code': s.get('currency_code', ''),
            'current_price': s.get('current_price', 0),
            'issuer': s.get('issuer', ''),
            'status': s.get('status', ''),
        })

    return JsonResponse({'results': results, 'total': len(results)})


@require_http_methods(["GET"])
def api_securities_by_currency(request):
    """
    API: Get securities filtered by currency code.
    Returns security list for cascading dropdown.
    """
    currency_code = request.GET.get('currency', '').strip()

    if not currency_code:
        return JsonResponse({'results': [], 'error': 'Currency code required'})

    securities = trade_dropdown_service.get_securities_by_currency(currency_code)

    return JsonResponse({'results': securities, 'total': len(securities)})


@require_http_methods(["GET"])
def api_get_equity_price(request):
    """
    API: Get latest equity price for a security and currency.
    Used to auto-fill price field based on currency and security selection.
    """
    security_label = request.GET.get('security', '').strip()
    currency_code = request.GET.get('currency', '').strip()

    if not security_label:
        return JsonResponse({'price': 0, 'error': 'Security label required'})

    price_data = trade_dropdown_service.get_equity_price(security_label, currency_code)

    return JsonResponse(price_data)


@require_http_methods(["GET"])
def api_get_fx_rate(request):
    """
    API: Get FX rate between two currencies.
    Uses cis_fx_rate table, spot_rate_d column.

    Query params:
        - from: Source currency code (e.g., 'USD') - security currency
        - to: Target currency code (e.g., 'SGD') - portfolio currency
        - date: Optional date for historical rate (YYYY-MM-DD)

    Returns:
        JSON with rate, date, and fx_pair (e.g., 'USD-SGD')
    """
    from_currency = request.GET.get('from', '').strip().upper()
    to_currency = request.GET.get('to', '').strip().upper()
    rate_date = request.GET.get('date', '').strip() or None

    if not from_currency or not to_currency:
        return JsonResponse({
            'rate': 1.0,
            'error': 'Both from and to currencies are required',
            'fx_pair': ''
        })

    # Same currency - rate is 1.0
    if from_currency == to_currency:
        return JsonResponse({
            'rate': 1.0,
            'fx_pair': f'{from_currency}-{to_currency}',
            'date': rate_date or 'N/A',
            'message': 'Same currency'
        })

    try:
        # Use multicurrency service to get the FX rate
        rate, date_used = multicurrency_service.get_fx_rate(
            from_currency, to_currency, rate_date
        )

        return JsonResponse({
            'rate': float(rate),
            'fx_pair': f'{from_currency}-{to_currency}',
            'date': str(date_used) if date_used else 'latest',
            'found': True
        })
    except Exception as e:
        logger.error(f"Error getting FX rate for {from_currency}-{to_currency}: {str(e)}")
        return JsonResponse({
            'rate': 1.0,
            'fx_pair': f'{from_currency}-{to_currency}',
            'error': str(e),
            'found': False
        })


@require_http_methods(["GET"])
def api_currencies(request):
    """
    API: Get available currencies for dropdown.
    Returns currencies that have associated securities/equity prices.
    """
    currencies = trade_dropdown_service.get_currencies()
    return JsonResponse({'results': currencies})


@require_http_methods(["GET"])
def api_get_broker_charges(request):
    """
    API: Get all active charges for a broker.
    Used to display charge breakdown in the trade form.
    """
    broker = request.GET.get('broker', '').strip()
    exchange = request.GET.get('exchange', '').strip()

    if not broker:
        return JsonResponse({'error': 'Broker is required', 'charges': []})

    charges = trade_dropdown_service.get_broker_charges(
        broker=broker,
        exchange=exchange if exchange else None
    )

    return JsonResponse({
        'broker': broker,
        'charges': charges,
        'count': len(charges)
    })


@require_http_methods(["GET"])
def api_calculate_charges(request):
    """
    API: Calculate trade charges based on broker, quantity, and price.
    Returns detailed breakdown of all applicable fees.
    """
    broker = request.GET.get('broker', '').strip()
    quantity = request.GET.get('quantity', '0')
    price = request.GET.get('price', '0')
    trade_type = request.GET.get('trade_type', 'BUY').strip()
    exchange = request.GET.get('exchange', '').strip()

    if not broker:
        return JsonResponse({
            'error': 'Broker is required',
            'charges': [],
            'total_charges': 0,
            'trade_value': 0,
            'grand_total': 0
        })

    try:
        qty = float(quantity) if quantity else 0
        prc = float(price) if price else 0
    except ValueError:
        return JsonResponse({
            'error': 'Invalid quantity or price',
            'charges': [],
            'total_charges': 0,
            'trade_value': 0,
            'grand_total': 0
        })

    result = trade_dropdown_service.calculate_trade_charges(
        broker=broker,
        quantity=qty,
        price=prc,
        trade_type=trade_type,
        exchange=exchange if exchange else None
    )

    # Log the result for debugging
    logger.info(f"Calculate charges API: broker={broker}, qty={qty}, price={prc}")
    logger.info(f"Calculate charges result: charges_count={len(result.get('charges', []))}, total={result.get('total_charges', 0)}")

    return JsonResponse(result)


@require_http_methods(["GET"])
def api_get_exchanges(request):
    """
    API: Get list of exchanges from charge lookup table.
    """
    exchanges = trade_dropdown_service.get_exchanges()
    return JsonResponse({'results': exchanges})


@require_http_methods(["GET"])
def api_debug_charge_lut(request):
    """
    API: Debug endpoint to show all brokers in charge lookup table.
    Use this to verify broker names match between cis_party and cis_trade_charge_lut.
    """
    broker_param = request.GET.get('broker', '').strip()

    # Get all brokers in lookup table
    brokers_in_lut = trade_dropdown_service.get_brokers_from_charge_lut()

    # If a broker is specified, show matching results
    matching_charges = []
    if broker_param:
        matching_charges = trade_dropdown_service.get_broker_charges(broker_param)

    return JsonResponse({
        'brokers_in_lookup_table': [b.get('value', '') for b in brokers_in_lut],
        'searched_broker': broker_param,
        'matching_charges': matching_charges,
        'match_count': len(matching_charges)
    })


# ==========================================================================
# POSITION QUEUE WORKER HEALTH CHECK
# ==========================================================================

def api_worker_health(request):
    """
    API: Health check endpoint for position queue worker.
    Used by CML monitoring to ensure the worker is running.

    Returns:
        JSON with worker status, queue statistics, and health indicators.

    Usage:
        GET /trade/api/worker-health/

    Response:
        {
            "status": "healthy" | "degraded" | "unhealthy",
            "worker_running": true | false,
            "queue": {
                "pending": 5,
                "processing": 1,
                "completed": 100,
                "failed": 2,
                "dead_letter": 0,
                "total": 108
            },
            "sla_ok": true,  # True if oldest pending < 5 minutes
            "timestamp": "2026-03-06 15:30:00"
        }
    """
    from datetime import datetime
    from trade.services.position_queue_service import position_queue_service

    try:
        # Get queue statistics
        stats = position_queue_service.get_queue_statistics()

        # Determine health status
        pending = stats.get('pending', 0)
        failed = stats.get('failed', 0)
        dead_letter = stats.get('dead_letter', 0)

        # Check if worker appears active (processing items or no backlog)
        worker_running = stats.get('processing', 0) > 0 or pending == 0

        # Check SLA - if pending items exist and are old, SLA is breached
        sla_ok = True
        oldest_pending_seconds = 0

        if pending > 0:
            # Get oldest pending item
            oldest = position_queue_service.get_pending_items(limit=1)
            if oldest:
                queued_at = oldest[0].get('queued_at')
                if queued_at:
                    if isinstance(queued_at, str):
                        queued_at = datetime.strptime(queued_at, '%Y-%m-%d %H:%M:%S')
                    oldest_pending_seconds = (datetime.now() - queued_at).total_seconds()
                    sla_ok = oldest_pending_seconds < 300  # 5 minute SLA

        # Determine overall health
        if dead_letter > 10:
            status = 'unhealthy'
        elif not sla_ok or failed > 5:
            status = 'degraded'
        else:
            status = 'healthy'

        return JsonResponse({
            'status': status,
            'worker_running': worker_running,
            'queue': {
                'pending': pending,
                'processing': stats.get('processing', 0),
                'completed': stats.get('completed', 0),
                'failed': failed,
                'dead_letter': dead_letter,
                'total': stats.get('total', 0)
            },
            'sla_ok': sla_ok,
            'oldest_pending_seconds': int(oldest_pending_seconds),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, status=500)


# ==========================================================================
# TRADE EVENT QUEUE MANAGEMENT APIs
# ==========================================================================

@require_http_methods(["GET"])
def api_trade_event_queue_health(request):
    """
    API: Get trade event queue health status.

    GET /trade/api/event-queue-health/

    Returns queue health metrics for monitoring.
    """
    try:
        from trade.services.trade_event_queue_service import trade_event_queue_service

        health = trade_event_queue_service.get_queue_health()

        return JsonResponse({
            'status': 'ok',
            'queue_health': health,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        logger.error(f"Event queue health check error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, status=500)


@require_http_methods(["GET"])
def api_trade_event_queue_failed(request):
    """
    API: Get failed/dead-letter events for review.

    GET /trade/api/event-queue-failed/

    Returns list of failed events that need attention.
    """
    try:
        from trade.services.trade_event_queue_service import trade_event_queue_service

        limit = int(request.GET.get('limit', 100))
        failed_events = trade_event_queue_service.get_failed_events(limit=limit)

        return JsonResponse({
            'status': 'ok',
            'count': len(failed_events),
            'events': failed_events,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        logger.error(f"Get failed events error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, status=500)


@require_http_methods(["POST"])
def api_trade_event_reprocess(request, event_id):
    """
    API: Reprocess a failed/dead-letter event.

    POST /trade/api/event-queue-reprocess/<event_id>/

    Resets the event to PENDING for reprocessing.
    """
    try:
        from trade.services.trade_event_queue_service import trade_event_queue_service

        success, message = trade_event_queue_service.reprocess_event(int(event_id))

        return JsonResponse({
            'status': 'ok' if success else 'error',
            'success': success,
            'message': message,
            'event_id': event_id,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        logger.error(f"Reprocess event error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, status=500)


@require_http_methods(["POST"])
def api_trade_event_reprocess_all_failed(request):
    """
    API: Reprocess all failed events (not dead-letter).

    POST /trade/api/event-queue-reprocess-all-failed/

    Resets all FAILED events to PENDING for reprocessing.
    """
    try:
        from trade.services.trade_event_queue_service import trade_event_queue_service

        success_count, error_count = trade_event_queue_service.reprocess_all_failed()

        return JsonResponse({
            'status': 'ok',
            'success_count': success_count,
            'error_count': error_count,
            'message': f'Requeued {success_count} events, {error_count} errors',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        logger.error(f"Reprocess all failed error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, status=500)


@require_http_methods(["POST"])
def api_trade_event_worker_start(request):
    """
    API: Start the trade event queue worker.

    POST /trade/api/event-worker-start/

    Note: In production, use the management command instead.
    """
    try:
        from trade.services.trade_event_queue_service import trade_event_queue_service

        started = trade_event_queue_service.start_worker()

        return JsonResponse({
            'status': 'ok',
            'started': started,
            'message': 'Worker started' if started else 'Worker already running',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        logger.error(f"Start worker error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, status=500)


@require_http_methods(["POST"])
def api_trade_event_worker_stop(request):
    """
    API: Stop the trade event queue worker.

    POST /trade/api/event-worker-stop/
    """
    try:
        from trade.services.trade_event_queue_service import trade_event_queue_service

        stopped = trade_event_queue_service.stop_worker()

        return JsonResponse({
            'status': 'ok',
            'stopped': stopped,
            'message': 'Worker stopped' if stopped else 'Worker not running',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        logger.error(f"Stop worker error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, status=500)


# ==========================================================================
# POSITION VIEWS - DISABLED
# ==========================================================================
# To re-enable position functionality, uncomment the code below and also:
#   1. Uncomment position URLs in trade/urls.py (lines 37-44)
#   2. Uncomment sidebar link in templates/components/sidebar.html (lines 97-102)
#   3. See docs/DISABLED_POSITION_CODE.md for full details
# ==========================================================================

# class PositionWrapper:
#     """Wrapper for position dict to enable template attribute access and numeric comparisons."""
#
#     def __init__(self, data: dict):
#         self._data = data
#
#     def __getattr__(self, name):
#         if name.startswith('_'):
#             return super().__getattribute__(name)
#         val = self._data.get(name)
#         if name in ('version_id', 'position_id'):
#             try:
#                 return int(float(val)) if val is not None else 0
#             except (ValueError, TypeError):
#                 return 0
#         if name in ('quantity', 'average_cost', 'total_cost', 'current_price',
#                      'market_value', 'unrealized_pnl', 'realized_pnl'):
#             try:
#                 return float(val) if val is not None else 0.0
#             except (ValueError, TypeError):
#                 return 0.0
#         return val
#
#
# def position_list(request):
#     """List all positions with P&L summary. Auto-refreshes market values on each load."""
#     # Auto-refresh market values on every page load
#     trade_kudu_repository.refresh_market_values()
#
#     positions_raw = trade_kudu_repository.get_all_positions(status='OPEN')
#     stats = trade_kudu_repository.get_position_statistics()
#
#     # Search filter
#     search_query = request.GET.get('q', '').strip()
#     if search_query:
#         search_lower = search_query.lower()
#         positions_raw = [
#             p for p in positions_raw
#             if search_lower in (p.get('portfolio_short_name', '') or '').lower()
#             or search_lower in (p.get('security_label', '') or '').lower()
#         ]
#
#     positions = [PositionWrapper(p) for p in positions_raw]
#
#     return render(request, 'trade/position_list.html', {
#         'positions': positions,
#         'stats': stats,
#         'search_query': search_query,
#     })
#
#
# def position_detail(request, position_id):
#     """Position detail view with version history."""
#     position_raw = trade_kudu_repository.get_position_by_id(position_id)
#     if not position_raw:
#         raise Http404("Position not found")
#
#     position = PositionWrapper(position_raw)
#     position_versions = trade_kudu_repository.get_position_versions(position_id)
#
#     # Look up currency_code from security table
#     currency_code = ''
#     try:
#         security_label = position_raw.get('security_label', '')
#         if security_label:
#             from core.repositories.impala_connection import impala_manager
#             escaped_label = security_label.replace('\\', '\\\\').replace("'", "\\'")
#             results = impala_manager.execute_query(
#                 f"SELECT currency_code FROM gmp_cis.cis_security "
#                 f"WHERE security_name = '{escaped_label}' LIMIT 1",
#                 database='gmp_cis'
#             )
#             if results:
#                 currency_code = results[0].get('currency_code', '')
#     except Exception:
#         pass
#
#     return render(request, 'trade/position_detail.html', {
#         'position': position,
#         'position_versions': position_versions,
#         'currency_code': currency_code,
#     })
#
#
# @require_http_methods(["POST"])
# def refresh_positions(request):
#     """Refresh market values for all open positions."""
#     counters = trade_kudu_repository.refresh_market_values()
#     messages.success(
#         request,
#         f"Market values refreshed: {counters['updated']} updated, "
#         f"{counters['skipped']} skipped, {counters['errors']} errors"
#     )
#     return redirect('trade:position_list')
