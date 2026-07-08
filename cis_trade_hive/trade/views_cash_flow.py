"""
Cash Flow Views

Implements Maker-Checker workflow for cash flow management.
Validates Portfolio and Security before cash flow creation.

Workflow (same as Portfolio):
  MAKER Side:
    - Create Cash Flow -> INITIAL
    - Update Cash Flow -> MODIFIED

  CHECKER Side:
    - Approve -> APPROVED
    - Reject -> REJECTED
"""

import json
import csv
import logging
from datetime import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from core.views.auth_views import require_login
from core.audit.audit_kudu_repository import audit_log_kudu_repository
from trade.services.cash_flow_service import cash_flow_service
from trade.services.cash_flow_dropdown_service import cash_flow_dropdown_service
from trade.repositories.trade_validation_repository import trade_validation_repository

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Helper to get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


def _build_security_fullname_map():
    """Return {security_label: full_name} from cached dropdown securities."""
    try:
        securities = cash_flow_dropdown_service.get_securities()
        return {s['value']: s['full_name'] for s in securities if s.get('value')}
    except Exception:
        return {}


def _enrich_security_fullname(cash_flows, sec_map):
    """Add security_full_name to each cash flow dict in-place."""
    for cf in cash_flows:
        label = cf.get('security_label') or ''
        cf['security_full_name'] = sec_map.get(label, label)


class CashFlowWrapper:
    """Wrapper to convert Kudu dict data to object with attributes for template compatibility."""

    def __init__(self, data, index=0):
        self.data = data
        self.cf_id = data.get('cf_id', 0)
        self.cf_number = data.get('cf_number', '')
        self.portfolio_short_name = data.get('portfolio_short_name', '')
        self.security_name = data.get('security_name', '')
        self.cash_flow_type = data.get('cash_flow_type', '')
        self.send_receive = data.get('send_receive', '')
        self.value_date = data.get('value_date', '')
        self.payment_date = data.get('payment_date', '')
        self.dividend_date = data.get('dividend_date', '')
        self.ex_date = data.get('ex_date', '')
        self.record_date = data.get('record_date', '')
        self.gl_acc_no = data.get('gl_acc_no', '')
        self.local_ccy = data.get('local_ccy', '')
        self.local_amount = data.get('local_amount', 0)
        self.flow_amount_local = data.get('flow_amount_local', 0)
        self.foreign_ccy = data.get('foreign_ccy', '')
        self.foreign_ccy_amount = data.get('foreign_ccy_amount', 0)
        self.cash_flow_status = data.get('cash_flow_status', '')
        self.src_system = data.get('src_system', '')
        self.status = data.get('status', '')
        self.is_active = data.get('is_active', False)
        self.is_deleted = data.get('is_deleted', False)
        self.created_by = data.get('created_by', '')
        self.created_at = data.get('created_at', '')
        self.updated_by = data.get('updated_by', '')
        self.updated_at = data.get('updated_at', '')
        self.reviewed_by = data.get('reviewed_by', '')
        self.reviewed_at = data.get('reviewed_at', '')
        self.reviewed_comments = data.get('reviewed_comments', '')

    def get(self, key, default=None):
        return self.data.get(key, default)


# ============================================================================
# Cash Flow List Views
# ============================================================================

@require_login
def cash_flow_list(request):
    """
    Cash Flow list view with search, filter, and CSV export.
    Requires: Authentication
    """
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    cf_type_filter = request.GET.get('cash_flow_type', '').strip()
    portfolio_filter = [p for p in request.GET.getlist('portfolios') if p.strip()]
    export = request.GET.get('export') == 'csv'
    page_number = request.GET.get('page', 1)

    try:
        # Get user info from session
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        # Fetch data
        cash_flows = cash_flow_service.list_all(
            search=search if search else None,
            status=status_filter if status_filter else None,
            cash_flow_type=cf_type_filter if cf_type_filter else None,
            portfolios=portfolio_filter if portfolio_filter else None
        )

        # Enrich with security full name and add workflow flags
        sec_map = _build_security_fullname_map()
        _enrich_security_fullname(cash_flows, sec_map)
        for cf in cash_flows:
            cf['can_approve'] = cash_flow_service.can_user_approve(cf, username)
            cf['status_color'] = cash_flow_service.get_status_display_color(cf.get('status', ''))

        # CSV Export
        if export:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="cash_flows_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'

            def fmt_num(val, dp=2):
                """Format a number with thousand separators for CSV export."""
                if val is None or val == '':
                    return ''
                try:
                    return f'{float(val):,.{dp}f}'
                except (ValueError, TypeError):
                    return val

            writer = csv.writer(response)
            writer.writerow([
                'CF Number', 'Portfolio', 'Security', 'Security Full Name', 'Cash Flow Type', 'Increase/Decrease',
                'Value Date', 'Payment Date', 'Ex Date', 'Record Date',
                'Local CCY', 'Local Amount', 'Foreign CCY', 'Foreign Amount',
                'FX Rate', 'Withholding Tax (FC)', 'Withholding Tax (LC)',
                'Cash Flow Status', 'Workflow Status', 'Created By', 'Created At'
            ])

            for cf in cash_flows:
                local_amt = cf.get('local_ccy_amt') or 0
                foreign_amt = cf.get('foreign_ccy_amt') or 0
                # FX Rate in FC→LC direction (how many local CCY per 1 foreign CCY,
                # e.g. USD→SGD: 1.26481). Always derive from amounts when available
                # so the direction is consistent regardless of how it was stored.
                fx_rate_csv = ''
                if local_amt and foreign_amt:
                    try:
                        fx_rate_csv = round(float(local_amt) / float(foreign_amt), 7)
                    except (ZeroDivisionError, TypeError, ValueError):
                        fx_rate_csv = cf.get('fx_rate', '')
                else:
                    fx_rate_csv = cf.get('fx_rate', '')
                writer.writerow([
                    cf.get('cash_flow_number', ''),
                    cf.get('portfolio_short_name', ''),
                    cf.get('security_label', ''),
                    cf.get('security_full_name', '') or cf.get('security_label', ''),
                    cf.get('cash_flow_type', ''),
                    cf.get('send_receive', ''),
                    cf.get('value_date', ''),
                    cf.get('payment_date', ''),
                    cf.get('ex_date', ''),
                    cf.get('record_date', ''),
                    cf.get('local_ccy', ''),
                    fmt_num(local_amt),
                    cf.get('foreign_ccy', ''),
                    fmt_num(foreign_amt),
                    fmt_num(fx_rate_csv, dp=6),
                    fmt_num(cf.get('tax_deducted_fc')),
                    fmt_num(cf.get('tax_deducted_lc')),
                    cf.get('cash_flow_status', ''),
                    cf.get('status', ''),
                    cf.get('created_by', ''),
                    cf.get('created_at', ''),
                ])

            # Log EXPORT action
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='EXPORT',
                entity_type='CASH_FLOW',
                entity_name='Cash Flow',
                entity_id='CF_EXPORT',
                action_description=f'Exported {len(cash_flows)} cash flows to CSV',
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            return response

        # Pagination
        paginator = Paginator(cash_flows, 25)
        page_obj = paginator.get_page(page_number)

        # Get dropdown options for filters
        dropdown_options = cash_flow_dropdown_service.get_all_dropdown_options()

        # Get pending count for badge
        pending_count = len(cash_flow_service.get_pending_approvals())

        context = {
            'cash_flows': page_obj,
            'search': search,
            'selected_status': status_filter,
            'selected_cash_flow_type': cf_type_filter,
            'selected_portfolios': portfolio_filter,
            'cash_flow_types': dropdown_options.get('cash_flow_types', []),
            'portfolios': dropdown_options.get('portfolios', []),
            'total_count': len(cash_flows),
            'pending_count': pending_count,
        }

        return render(request, 'trade/cash_flow_list.html', context)

    except Exception as e:
        logger.error(f"Error in cash_flow_list: {str(e)}")
        messages.error(request, f"Error loading cash flows: {str(e)}")
        return render(request, 'trade/cash_flow_list.html', {
            'cash_flows': [],
            'cash_flow_types': [],
            'portfolios': []
        })


@require_login
def cash_flow_pending_approvals(request):
    """
    List cash flows pending approval (INITIAL or MODIFIED status).
    Four-Eyes Principle: Checker reviews Maker's work.
    """
    try:
        cash_flows = cash_flow_service.get_pending_approvals()

        username = request.session.get('user_login', 'anonymous')

        # Enrich with security full name and add workflow flags
        sec_map = _build_security_fullname_map()
        _enrich_security_fullname(cash_flows, sec_map)
        for cf in cash_flows:
            cf['can_approve'] = cash_flow_service.can_user_approve(cf, username)
            cf['status_color'] = cash_flow_service.get_status_display_color(cf.get('status', ''))

        # Pagination
        paginator = Paginator(cash_flows, 25)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        stats = cash_flow_service.get_statistics()

        modified_count = sum(
            1 for cf in cash_flows if cf.get('status') == 'MODIFIED'
        )

        context = {
            'cash_flows': page_obj,
            'pending_count': len(cash_flows),
            'modified_count': modified_count,
            'approved_today': stats.get('approved_today', 0),
            'username': username,
        }

        return render(request, 'trade/cash_flow_pending_approvals.html', context)

    except Exception as e:
        logger.error(f"Error in cash_flow_pending_approvals: {str(e)}")
        messages.error(request, f"Error loading pending approvals: {str(e)}")
        return render(request, 'trade/cash_flow_pending_approvals.html', {
            'cash_flows': [],
            'pending_count': 0,
            'modified_count': 0,
            'approved_today': 0,
        })


# ============================================================================
# Cash Flow Detail Views
# ============================================================================

@require_login
def cash_flow_detail(request, cash_flow_id):
    """
    View cash flow details.
    Requires: Authentication
    """
    try:
        cf = cash_flow_service.get_by_id(int(cash_flow_id))

        if not cf:
            messages.error(request, f"Cash Flow {cash_flow_id} not found")
            return redirect('trade:cash_flow_list')

        # Get user info for can_approve check
        username = request.session.get('user_login', 'anonymous')

        # Get history
        history = cash_flow_service.get_history(int(cash_flow_id))

        # Enrich with security full name
        sec_map = _build_security_fullname_map()
        _enrich_security_fullname([cf], sec_map)

        context = {
            'cash_flow': cf,
            'history': history,
            'can_approve': cash_flow_service.can_user_approve(cf, username),
            'can_edit': cash_flow_service.can_user_edit(cf, username),
            'status_color': cash_flow_service.get_status_display_color(cf.get('status', '')),
        }

        return render(request, 'trade/cash_flow_detail.html', context)

    except Exception as e:
        logger.error(f"Error in cash_flow_detail: {str(e)}")
        messages.error(request, f"Error loading cash flow: {str(e)}")
        return redirect('trade:cash_flow_list')


# ============================================================================
# Cash Flow Create/Edit Views
# ============================================================================

@require_login
def cash_flow_create(request):
    """
    Create new cash flow.
    Requires: Authentication
    """
    if request.method == 'POST':
        try:
            username = request.session.get('user_login', 'anonymous')
            user_id = str(request.session.get('user_id', ''))
            user_email = request.session.get('user_email', '')

            cf_data = {
                'cf_number': request.POST.get('cf_number', '').strip(),
                'cash_flow_number': request.POST.get('cf_number', '').strip(),
                'portfolio_short_name': request.POST.get('portfolio_short_name', '').strip(),
                'security_name': request.POST.get('security_name', '').strip(),
                'security_label': request.POST.get('security_name', '').strip(),
                'cash_flow_type': request.POST.get('cash_flow_type', '').strip(),
                'send_receive': request.POST.get('send_receive', '').strip(),
                'value_date': request.POST.get('value_date', '').strip(),
                'payment_date': request.POST.get('payment_date', '').strip() or None,  # optional (item 3)
                'dividend_date': request.POST.get('dividend_date', '').strip() or None,
                'ex_date': request.POST.get('ex_date', '').strip() or None,
                'record_date': request.POST.get('record_date', '').strip() or None,
                'gl_acc_no': request.POST.get('gl_acc_no', '').strip() or None,
                'local_ccy': request.POST.get('local_ccy', '').strip(),
                'local_ccy_amt': request.POST.get('local_amount', '').strip() or None,
                'flow_amount_local': request.POST.get('flow_amount_local', '').strip() or None,
                'foreign_ccy': request.POST.get('foreign_ccy', '').strip(),
                'foreign_ccy_amt': request.POST.get('foreign_ccy_amount', '').strip() or None,
                'tax_deducted_fc': request.POST.get('withholding_tax_fc', '').strip() or None,  # item 9
                'tax_deducted_lc': request.POST.get('withholding_tax_lc', '').strip() or None,  # item 9
                'remarks': request.POST.get('remarks', '').strip() or None,
            }

            # Convert numeric fields
            for field in ['local_ccy_amt', 'flow_amount_local', 'foreign_ccy_amt',
                          'tax_deducted_fc', 'tax_deducted_lc']:
                if cf_data.get(field):
                    try:
                        cf_data[field] = float(cf_data[field])
                    except ValueError:
                        cf_data[field] = None

            success, cf_id, error_msg = cash_flow_service.create(
                cf_data=cf_data,
                user_id=user_id,
                username=username,
                user_email=user_email
            )

            if success:
                messages.success(request, f"Cash Flow '{cf_data.get('cf_number', cf_id)}' created successfully")
                return redirect('trade:cash_flow_list')
            else:
                messages.error(request, error_msg)

        except Exception as e:
            logger.error(f"Error creating cash flow: {str(e)}")
            messages.error(request, f"Error creating cash flow: {str(e)}")

    # GET request - show form with dropdowns
    dropdown_options = cash_flow_dropdown_service.get_all_dropdown_options()

    context = {
        'dropdown_options': dropdown_options,
    }
    return render(request, 'trade/cash_flow_form.html', context)


@require_login
def cash_flow_edit(request, cash_flow_id):
    """
    Edit existing cash flow.
    Requires: Authentication
    """
    try:
        cf = cash_flow_service.get_by_id(int(cash_flow_id))
        if not cf:
            messages.error(request, f"Cash Flow {cash_flow_id} not found")
            return redirect('trade:cash_flow_list')

        username = request.session.get('user_login', 'anonymous')

        # Check if editable
        if not cash_flow_service.can_user_edit(cf, username):
            messages.warning(request, f"Cannot edit cash flow with status '{cf.get('status')}' or from external source.")
            return redirect('trade:cash_flow_list')

        if request.method == 'POST':
            user_id = str(request.session.get('user_id', ''))
            user_email = request.session.get('user_email', '')

            cf_data = {
                'portfolio_short_name': request.POST.get('portfolio_short_name', '').strip(),
                'security_name': request.POST.get('security_name', '').strip(),
                'security_label': request.POST.get('security_name', '').strip(),
                'cash_flow_type': request.POST.get('cash_flow_type', '').strip(),
                'send_receive': request.POST.get('send_receive', '').strip(),
                'value_date': request.POST.get('value_date', '').strip(),
                'payment_date': request.POST.get('payment_date', '').strip() or None,  # optional (item 3)
                'dividend_date': request.POST.get('dividend_date', '').strip() or None,
                'ex_date': request.POST.get('ex_date', '').strip() or None,
                'record_date': request.POST.get('record_date', '').strip() or None,
                'gl_acc_no': request.POST.get('gl_acc_no', '').strip() or None,
                'local_ccy': request.POST.get('local_ccy', '').strip(),
                'local_ccy_amt': request.POST.get('local_amount', '').strip() or None,
                'flow_amount_local': request.POST.get('flow_amount_local', '').strip() or None,
                'foreign_ccy': request.POST.get('foreign_ccy', '').strip(),
                'foreign_ccy_amt': request.POST.get('foreign_ccy_amount', '').strip() or None,
                'cash_flow_status': request.POST.get('cash_flow_status', '').strip(),
                'tax_deducted_fc': request.POST.get('withholding_tax_fc', '').strip() or None,  # item 9
                'tax_deducted_lc': request.POST.get('withholding_tax_lc', '').strip() or None,  # item 9
                'remarks': request.POST.get('remarks', '').strip() or None,
            }

            # Convert numeric fields
            for field in ['local_ccy_amt', 'flow_amount_local', 'foreign_ccy_amt',
                          'tax_deducted_fc', 'tax_deducted_lc']:
                if cf_data.get(field):
                    try:
                        cf_data[field] = float(cf_data[field])
                    except ValueError:
                        cf_data[field] = None

            success, error_msg = cash_flow_service.update(
                cf_id=int(cash_flow_id),
                cf_data=cf_data,
                user_id=user_id,
                username=username,
                user_email=user_email
            )

            if success:
                messages.success(request, f"Cash Flow '{cf.get('cash_flow_number', cash_flow_id)}' updated successfully")
                return redirect('trade:cash_flow_list')
            else:
                messages.error(request, error_msg)

        # GET request - show form with existing data
        dropdown_options = cash_flow_dropdown_service.get_all_dropdown_options()

        context = {
            'cash_flow': cf,
            'dropdown_options': dropdown_options,
            'is_edit': True,
        }
        return render(request, 'trade/cash_flow_form.html', context)

    except Exception as e:
        logger.error(f"Error editing cash flow: {str(e)}")
        messages.error(request, f"Error editing cash flow: {str(e)}")
        return redirect('trade:cash_flow_list')


# ============================================================================
# Cash Flow Workflow Actions
# ============================================================================

@require_login
@require_http_methods(["POST"])
def cash_flow_approve(request, cash_flow_id):
    """
    Approve cash flow (Checker action).
    POST with action='approve' or action='reject'
    """
    try:
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        comments = request.POST.get('comments', '').strip()
        action = request.POST.get('action', 'approve')

        if action == 'approve':
            success, error_msg = cash_flow_service.approve(
                cf_id=int(cash_flow_id),
                user_id=user_id,
                username=username,
                user_email=user_email,
                comments=comments
            )

            if success:
                messages.success(request, f"Cash Flow {cash_flow_id} approved successfully")
            else:
                messages.error(request, error_msg)
        else:
            # Reject action
            success, error_msg = cash_flow_service.reject(
                cf_id=int(cash_flow_id),
                user_id=user_id,
                username=username,
                user_email=user_email,
                comments=comments
            )

            if success:
                messages.success(request, f"Cash Flow {cash_flow_id} rejected")
            else:
                messages.error(request, error_msg)

    except Exception as e:
        logger.error(f"Error approving cash flow: {str(e)}")
        messages.error(request, f"Error approving cash flow: {str(e)}")

    return redirect('trade:cash_flow_pending_approvals')


@require_login
@require_http_methods(["POST"])
def cash_flow_delete(request, cash_flow_id):
    """
    Soft delete cash flow (POST only).
    Requires: Authentication
    """
    try:
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        success, error_msg = cash_flow_service.delete(
            cf_id=int(cash_flow_id),
            user_id=user_id,
            username=username,
            user_email=user_email
        )

        if success:
            messages.success(request, f"Cash Flow {cash_flow_id} deleted successfully")
        else:
            messages.error(request, error_msg)

    except Exception as e:
        logger.error(f"Error deleting cash flow: {str(e)}")
        messages.error(request, f"Error deleting cash flow: {str(e)}")

    return redirect('trade:cash_flow_list')


@require_login
@require_http_methods(["POST"])
def cash_flow_restore(request, cash_flow_id):
    """
    Restore soft-deleted cash flow (POST only).
    Requires: Authentication
    """
    try:
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        success, error_msg = cash_flow_service.restore(
            cf_id=int(cash_flow_id),
            user_id=user_id,
            username=username,
            user_email=user_email
        )

        if success:
            messages.success(request, f"Cash Flow {cash_flow_id} restored successfully")
        else:
            messages.error(request, error_msg)

    except Exception as e:
        logger.error(f"Error restoring cash flow: {str(e)}")
        messages.error(request, f"Error restoring cash flow: {str(e)}")

    return redirect('trade:cash_flow_list')


# ============================================================================
# Cash Flow API Endpoints (for AJAX validation)
# ============================================================================

@require_login
def api_validate_cf_portfolio(request):
    """API: Validate portfolio for cash flow."""
    portfolio_short_name = request.GET.get('portfolio', '').strip()
    if not portfolio_short_name:
        return JsonResponse({'valid': False, 'is_valid': False, 'message': 'Portfolio short name is required'})
    result = trade_validation_repository.validate_portfolio(portfolio_short_name)
    return JsonResponse({
        'valid': result.is_valid,
        'is_valid': result.is_valid,
        'message': result.message,
        'details': result.details,
    })


@require_login
def api_validate_cf_security(request):
    """API: Validate security for cash flow."""
    security_name = request.GET.get('security', '').strip()
    if not security_name:
        return JsonResponse({'valid': False, 'is_valid': False, 'message': 'Security name is required'})
    result = trade_validation_repository.validate_security(security_name)
    return JsonResponse({
        'valid': result.is_valid,
        'is_valid': result.is_valid,
        'message': result.message,
        'details': result.details,
    })
