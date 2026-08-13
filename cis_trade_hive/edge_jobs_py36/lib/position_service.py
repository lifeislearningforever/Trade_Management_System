"""
Position Service - AVP (Average Price Position) Calculator

Phase 1: Basic AVP with weighted average calculation.

Key Features:
- Weighted average price calculation for BUY/SELL trades
- 8 decimal precision for AVP calculations
- Output to position_master Hive external table with src_system='CIS'
- Position history tracking in cis_trade_position
- Multi-currency support (local/base)

Based on SA Team Questionnaire Feedback (2026-03-04).
"""

import logging
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date
import uuid

from .impala_connection import impala_manager
from .system_date_service import system_date_service
from .multicurrency_service import multicurrency_service
from .position_id_service import position_id as _calc_position_id
from .config import settings

logger = logging.getLogger(__name__)


class PositionService:
    """
    Service for calculating positions using weighted average method.

    AVP Formula:
    - BUY:  new_avg_cost = (old_total_cost + trade_cost + charges) / new_quantity
    - SELL: avg_cost unchanged, realized P&L = (sell_price - avg_cost) * quantity
    """

    DATABASE = settings.IMPALA_CONFIG['DATABASE']
    POSITION_TABLE = 'cis_trade_position'  # Internal CIS position tracking
    POSITION_MASTER_TABLE = 'position_master'  # External Hive table (shared)
    AVP_PRECISION = Decimal('0.00000001')  # 8 decimal places

    # Trade types that affect position
    POSITION_AFFECTING_TYPES = ['BUY', 'SELL']

    def __init__(self):
        """Initialize the position service."""
        pass

    # Fallback decimal places when a currency isn't found in gmp_cis_sta_dly_currency.
    _DEFAULT_AMOUNT_DP = 2

    def _get_currency_dp(self, currency_code: str) -> int:
        """Return decimal places for a currency from gmp_cis_sta_dly_currency.

        e.g. precision '0000000000.01' -> 2. Falls back to _DEFAULT_AMOUNT_DP
        if not found. Same table/parsing convention as the identical helper in
        trade/services/trade_dropdown_service.py and
        trade/management/commands/process_approved_cashflows.py — kept
        consistent deliberately rather than sharing a single implementation.
        """
        if not currency_code:
            return self._DEFAULT_AMOUNT_DP
        try:
            escaped = currency_code.replace('\\', '\\\\').replace("'", "\\'")
            results = impala_manager.execute_query(
                f"SELECT precision FROM {self.DATABASE}.gmp_cis_sta_dly_currency "
                f"WHERE iso_code = '{escaped}' "
                f"  AND processing_date = ("
                f"      SELECT MAX(processing_date) FROM {self.DATABASE}.gmp_cis_sta_dly_currency"
                f"  ) "
                f"LIMIT 1",
                database=self.DATABASE
            )
            if results:
                prec_str = str(results[0].get('precision') or '')
                if '.' in prec_str:
                    return len(prec_str.split('.')[1].rstrip('0') or '0')
        except Exception as e:
            logger.debug(f"Could not get currency precision for {currency_code}: {e}")
        return self._DEFAULT_AMOUNT_DP

    @staticmethod
    def _round_amount(value: float, decimal_places: int) -> float:
        """Round an FC/LC amount field to currency precision (ROUND_HALF_UP).

        Applies to cost/market-value/unrealized-pnl/provision/dividend/uncall
        fields per SA direction (Teams, 2026-07-30): those are amount fields
        and should follow currency-table precision, unlike average_cost_fc/lc
        which is a price field and stays on AVP_PRECISION (8dp). Consequence
        (explicitly called out as expected): average_cost * quantity will not
        exactly equal cost_fc/lc after this rounding.
        """
        if value is None:
            return value
        quantum = Decimal(1).scaleb(-decimal_places) if decimal_places > 0 else Decimal(1)
        return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))

    # =========================================================================
    # AVP CALCULATION
    # =========================================================================

    def _derive_position_type(self, position_date: str) -> Tuple[bool, str, Optional[str]]:
        """
        Derive position_type by comparing position_date to contextual_today.

        Returns (ok, message, position_type):
          - position_date == today  → INT  (same-day intraday)
          - position_date <  today  → INT  (backdated trade — still INT, not BACK/CORR)
          - position_date >  today  → blocked (future dates not allowed)

        CORR is only assigned externally for last-month-end corrections
        triggered from gmp_cis_sta_dly_alldatesinfo — never derived here.
        """
        try:
            pos_dt = datetime.strptime(position_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return False, f"Invalid position_date format: {position_date!r} (expected YYYY-MM-DD)", None

        today = system_date_service.get_system_date()
        if not isinstance(today, date):
            today = datetime.strptime(str(today), '%Y-%m-%d').date()

        if pos_dt <= today:
            return True, '', 'INT'
        else:
            return False, (
                f"Future position date {position_date} not allowed "
                f"(contextual_today={today.isoformat()})"
            ), None

    def calculate_position(
        self,
        portfolio_id: str,
        security_id: str,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        position_date: str,
        trade_id: int,
        updated_by: str,
        security_currency: str = None,
        portfolio_currency: str = None,
        isin: str = None,
        security_name: str = None,
        custodian: str = None,
        sub_custodian: str = None,
        is_chain_recalc: bool = False,
        uncall_fc: Decimal = None,
        uncall_lc: Decimal = None,
        pipeline_fc: Decimal = None,
        pipeline_lc: Decimal = None,
        position_type: str = None,
        position_basis: str = 'TRADED',
        base_position_override: Dict[str, Any] = None,
        trade_lc: Decimal = None,
        gross_amount_lc: Decimal = None,
        gross_amount_fc: Decimal = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Calculate position using weighted average method.

        Args:
            portfolio_id: Portfolio short name
            security_id: Security label
            trade_type: BUY or SELL
            quantity: Trade quantity (positive)
            price: Trade price per unit
            charges: Total charges (commission + sec_fee + other_charges)
            position_date: Position date (YYYY-MM-DD)
            trade_id: Reference trade ID
            updated_by: User performing the update
            security_currency: Security currency code
            portfolio_currency: Portfolio base currency code
            isin: ISIN code
            security_name: Security full name
            trade_lc: Total LC amount from trade (used for NON-REVAL SELL realized P&L)
            gross_amount_lc: Gross LC cost from trade (qty × price in LC, post user edits).
                             Used for NON-REVAL BUY cost_lc and as FX rate fallback.

        Returns:
            Tuple of (success, message, position_data)
        """
        # ENTRY-POINT TRACE (unconditional, print+logger, cannot be silently
        # skipped or filtered) — prints every raw argument exactly as this
        # function received it, before any processing. Added to settle
        # whether an open_fx_rate override is being lost before reaching
        # this function or lost inside it — every downstream hop has
        # individually checked out correct on paper, so this is the one
        # ground-truth point not yet directly observed at runtime.
        print(
            f"==> [CALC_POSITION ENTRY] trade_id={trade_id} portfolio_id={portfolio_id!r} "
            f"security_id={security_id!r} trade_type={trade_type!r} position_basis={position_basis!r} "
            f"security_currency={security_currency!r} portfolio_currency={portfolio_currency!r} "
            f"gross_amount_lc={gross_amount_lc!r} (type={type(gross_amount_lc).__name__}) "
            f"trade_lc={trade_lc!r} is_chain_recalc={is_chain_recalc!r}",
            flush=True
        )
        logger.info(
            f"[CALC_POSITION ENTRY] trade_id={trade_id} portfolio_id={portfolio_id!r} "
            f"security_id={security_id!r} trade_type={trade_type!r} position_basis={position_basis!r} "
            f"security_currency={security_currency!r} portfolio_currency={portfolio_currency!r} "
            f"gross_amount_lc={gross_amount_lc!r} (type={type(gross_amount_lc).__name__}) "
            f"trade_lc={trade_lc!r} is_chain_recalc={is_chain_recalc!r}"
        )
        try:
            # Validate trade type
            if trade_type not in self.POSITION_AFFECTING_TYPES:
                return True, f"Trade type {trade_type} does not affect position", None

            # --- IDEMPOTENCY GUARD ---
            # If cis_trade_position already has a row for this trade_id + position_basis,
            # this event has already been processed (e.g. worker double-processed the event
            # before the process-level lock took effect, or Kudu stale read race).
            # Return the existing row so callers get a valid result without re-calculating.
            if trade_id and not is_chain_recalc:
                existing_check = impala_manager.execute_query(
                    f"""
                    SELECT version_id, position_id, quantity, average_cost_fc, position_basis
                    FROM {self.DATABASE}.{self.POSITION_TABLE}
                    WHERE trade_id = {trade_id}
                      AND position_basis = '{position_basis}'
                      AND is_latest = true
                    LIMIT 1
                    """,
                    database=self.DATABASE
                )
                if existing_check:
                    print(
                        f"==> [CALC_POSITION] IDEMPOTENCY GUARD HIT: trade_id={trade_id} "
                        f"basis={position_basis} version={existing_check[0].get('version_id')} "
                        f"— returning existing row, _process_buy/_process_sell NOT called",
                        flush=True
                    )
                    logger.warning(
                        f"IDEMPOTENCY: trade_id={trade_id} basis={position_basis} already processed "
                        f"(version={existing_check[0].get('version_id')}). Skipping recalculation."
                    )
                    return True, f"Position already calculated for trade {trade_id} basis={position_basis} (idempotency guard)", existing_check[0]
            # -------------------------

            # Convert to Decimal for precision
            qty = Decimal(str(quantity))
            prc = Decimal(str(price))
            chrg = Decimal(str(charges)) if charges else Decimal('0')

            # Validate inputs
            if qty <= 0:
                return False, "Quantity must be positive", None
            if prc < 0:
                return False, "Price must not be negative", None

            # Derive position_type from position_date vs contextual_today
            ok, err_msg, derived_type = self._derive_position_type(position_date)
            if not ok:
                return False, err_msg, None
            position_type = derived_type

            # Get the appropriate base position for calculation
            # For chain recalculation (backdated trades), we need position BEFORE this date
            # to avoid picking up the old position for the same date
            # For normal trades, we include same date positions
            if is_chain_recalc:
                # Chain recalc: use in-memory override when the caller supplies it.
                # This avoids Kudu/Impala stale-read races where the write from the
                # previous loop iteration hasn't propagated to the connection pool yet.
                if base_position_override is not None:
                    # {} = sentinel for "first trade, start from zero" (no DB lookup)
                    # non-empty dict = accumulated position from previous loop iteration
                    current = base_position_override if base_position_override else None
                    logger.info(
                        f"Chain recalc mode: in-memory base for {portfolio_id}/{security_id} "
                        f"basis={position_basis} date={position_date}. "
                        f"qty={current.get('quantity') if current else 'none (fresh start)'}"
                    )
                else:
                    current = self._get_position_as_of_date(
                        portfolio_id, security_id, position_date,
                        include_same_date=True, position_basis=position_basis,
                        exclude_trade_id=trade_id
                    )
                    logger.info(
                        f"Chain recalc mode: DB lookup <= {position_date} "
                        f"(excl trade_id={trade_id}) for "
                        f"{portfolio_id}/{security_id} basis={position_basis}. Found: {current is not None}"
                    )
            else:
                # Normal mode: include same date positions, scoped to same basis
                current = self._get_position_as_of_date(
                    portfolio_id, security_id, position_date, position_basis=position_basis
                )

            # If no position before this date, this is the first trade for this date range
            # (which is correct for backdated trades creating a new earliest position)

            if trade_type == 'BUY':
                return self._process_buy(
                    current=current,
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    quantity=qty,
                    price=prc,
                    charges=chrg,
                    position_date=position_date,
                    trade_id=trade_id,
                    updated_by=updated_by,
                    security_currency=security_currency,
                    portfolio_currency=portfolio_currency,
                    isin=isin,
                    security_name=security_name,
                    custodian=custodian,
                    sub_custodian=sub_custodian,
                    uncall_fc=uncall_fc,
                    uncall_lc=uncall_lc,
                    pipeline_fc=pipeline_fc,
                    pipeline_lc=pipeline_lc,
                    position_type=position_type,
                    position_basis=position_basis,
                    trade_lc=trade_lc,
                    gross_amount_lc=gross_amount_lc,
                    gross_amount_fc=gross_amount_fc,
                )
            elif trade_type == 'SELL':
                return self._process_sell(
                    current=current,
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    quantity=qty,
                    price=prc,
                    position_date=position_date,
                    trade_id=trade_id,
                    updated_by=updated_by,
                    security_currency=security_currency,
                    portfolio_currency=portfolio_currency,
                    isin=isin,
                    security_name=security_name,
                    custodian=custodian,
                    sub_custodian=sub_custodian,
                    uncall_fc=uncall_fc,
                    uncall_lc=uncall_lc,
                    pipeline_fc=pipeline_fc,
                    pipeline_lc=pipeline_lc,
                    position_type=position_type,
                    position_basis=position_basis,
                    trade_lc=trade_lc,
                    gross_amount_lc=gross_amount_lc,
                    gross_amount_fc=gross_amount_fc,
                )

        except Exception as e:
            logger.error(f"Error calculating position: {str(e)}")
            return False, f"Position calculation error: {str(e)}", None

    def _process_buy(
        self,
        current: Optional[Dict[str, Any]],
        portfolio_id: str,
        security_id: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        position_date: str,
        trade_id: int,
        updated_by: str,
        security_currency: str = None,
        portfolio_currency: str = None,
        isin: str = None,
        security_name: str = None,
        custodian: str = None,
        sub_custodian: str = None,
        uncall_fc: Decimal = None,
        uncall_lc: Decimal = None,
        pipeline_fc: Decimal = None,
        pipeline_lc: Decimal = None,
        position_type: str = None,
        position_basis: str = 'TRADED',
        trade_lc: Decimal = None,
        gross_amount_lc: Decimal = None,
        gross_amount_fc: Decimal = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Process BUY trade - increase position, recalculate AVP.

        Formula (gross only — charges excluded per SA PORTIARP-8206):
            trade_cost    = gross_amount_fc from trade if supplied, else buy_qty * buy_price
            new_total_cost = old_total_cost + trade_cost
            new_quantity   = old_quantity + buy_qty
            new_avg_cost   = new_total_cost / new_quantity

        FC cost rule (SA feedback, Venkata Narayana Adisetty, 30/07/2026): the
        gross amount is stored directly as cost fc, unconditionally (no REVAL/
        NON-REVAL gating — that distinction only governs how LC is *derived*
        from FC, it has no meaning for FC itself). Falls back to quantity *
        price only when the caller has no gross_amount_fc to supply (e.g. a
        UI trade with no separate gross-amount entry).

        LC cost rules:
            NON-REVAL: trade_cost_lc = gross_amount_lc from trade (post user edits)
            REVAL:     trade_cost_lc = trade_cost × fx_rate (from FX table, date-bound)
        market_value_lc always uses fx_rate from FX table (date <= position_date),
        falling back to implied rate only when the table has no data for the pair.
        """
        # position_id is always deterministic from the natural key of THIS date.
        # In chain recalc the `current` dict carries the running balance from a
        # different date (e.g. Feb-27), so we must NOT inherit its position_id.
        position_id = _calc_position_id(
            portfolio_id, security_id, position_basis, position_date, 'CIS'
        )

        # Defensive: resolve currencies fresh if the caller's event_data payload
        # was missing either one — see _resolve_currencies docstring.
        security_currency, portfolio_currency = self._resolve_currencies(
            portfolio_id, security_id, security_currency, portfolio_currency
        )

        # Gross cost only — charges are a P&L item, not cost basis (SA PORTIARP-8206).
        # Use the trade's exact gross_amount_fc when supplied (migration/UI-edited
        # amount) rather than recomputing quantity * price — the two can differ by
        # a small amount when the source system's price has more precision than
        # what's stored in the `price` column, and SA direction is that the
        # tallied amount wins (30/07/2026).
        trade_cost = Decimal(str(gross_amount_fc)) if gross_amount_fc else quantity * price

        if current:
            # Existing position - add to it
            old_qty = Decimal(str(current.get('quantity', 0) or 0))
            # Use new column name average_cost_fc (fallback to average_cost for backward compat)
            old_avg_cost = Decimal(str(current.get('average_cost_fc') or current.get('average_cost', 0) or 0))
            # Chain off the stored total_cost_fc (the exact tallied gross cost —
            # see SA feedback, Venkata Narayana Adisetty, 30/07/2026: gross amount
            # is stored directly as cost fc/lc, average_cost is a *derived*,
            # AVP_PRECISION-rounded field). Reconstructing old_total_cost as
            # old_qty * old_avg_cost instead would multiply back through the
            # already-rounded average_cost on every subsequent BUY, compounding
            # rounding drift further away from the tallied amount with each
            # trade — exactly the LC branch below already avoids by reading
            # total_cost_lc directly. Fall back to the qty*avg_cost
            # reconstruction only for legacy rows with no total_cost_fc stored.
            old_total_cost = Decimal(str(current.get('total_cost_fc') or current.get('total_cost', 0) or 0))
            if old_total_cost == 0:
                old_total_cost = old_qty * old_avg_cost
            # Use new column name realized_pnl_fc (fallback to realized_pnl for backward compat)
            old_realized_pnl = Decimal(str(current.get('realized_pnl_fc') or current.get('realized_pnl', 0) or 0))

            new_qty = old_qty + quantity
            new_total_cost = old_total_cost + trade_cost
            new_avg_cost = (new_total_cost / new_qty).quantize(
                self.AVP_PRECISION, rounding=ROUND_HALF_UP
            )

            logger.info(
                f"BUY: Adding {quantity} @ {price} to position {position_id}. "
                f"Old: {old_qty} @ {old_avg_cost}, New: {new_qty} @ {new_avg_cost}"
            )
        else:
            old_qty = Decimal('0')
            old_realized_pnl = Decimal('0')

            new_qty = quantity
            new_total_cost = trade_cost
            new_avg_cost = (new_total_cost / new_qty).quantize(
                self.AVP_PRECISION, rounding=ROUND_HALF_UP
            )

            logger.info(
                f"BUY: Creating new position {position_id}. "
                f"Qty: {new_qty}, AVP: {new_avg_cost}"
            )

        # Fetch market price for unrealized P&L (convert to Decimal for consistency)
        # `is not None` (not truthiness) -- a genuine 0 market price must produce
        # market_value = 0, not silently fall back to the trade price (SA, 2026-08-12).
        market_price_raw = self._get_market_price(security_id)
        market_price = Decimal(str(market_price_raw)) if market_price_raw is not None else price
        market_value = new_qty * market_price
        # Associates/subsidiaries are carried at cost (equity method) — no MTM.
        # Computed once and threaded through position_data as '_is_equity_method' so
        # _save_position doesn't need its own query to gate unrealized_pnl_lc — see
        # the '_reval_status' passthrough above for why a second, independent query
        # for the same fact is a real bug class here, not just theoretical.
        is_equity_method = self._is_equity_method_security(security_id)
        if is_equity_method:
            unrealized_pnl = Decimal('0')
        else:
            unrealized_pnl = market_value - new_total_cost

        # Cost basis uses gross amounts (qty × price), never total (which includes charges).
        # gross_amount_lc is the user-editable LC equivalent of gross_amount_fc.
        logger.info(f"[DEBUG POS] _process_buy trade_id={trade_id} gross_amount_lc={gross_amount_lc!r} trade_cost={trade_cost}")
        is_cross_currency = bool(
            security_currency and portfolio_currency and security_currency != portfolio_currency
        )
        _effective_gross_lc = (
            Decimal(str(gross_amount_lc)) if gross_amount_lc and is_cross_currency else None
        )

        reval_status = self._get_portfolio_revaluation_status(portfolio_id)

        # Implied FX rate back-calculated from the trade's LC/FC amounts.
        # This captures whatever rate the user had at entry time, including manual LC edits.
        # Used as fallback only for NON-REVAL — REVAL must always trust the FX table
        # (SA PORTIARP-8206) even when the table has no data for the pair.
        implied_fx_rate = None
        if (reval_status == 'NON-REVALUED' and _effective_gross_lc
                and trade_cost and trade_cost != Decimal('0')):
            implied_fx_rate = _effective_gross_lc / trade_cost

        # FX rate from the table: latest date <= position_date, carry-forward if no exact
        # match. Falls back to implied_fx_rate only for NON-REVAL when the table has zero
        # rows for the pair.
        fx_rate = Decimal('1')
        if is_cross_currency:
            fx_rate = self._get_fx_rate(
                security_currency, portfolio_currency,
                rate_date=position_date,
                fallback_rate=implied_fx_rate,
            )

        # cost_lc rules (SA PORTIARP-8206):
        #   NON-REVAL: use effective gross_lc from trade (derived from user-entered total_amount_lc)
        #   REVAL:     trade_cost × fx_rate (table rate, date-bound)
        logger.info(
            f"[COST_LC DECISION] trade_id={trade_id} portfolio_id={portfolio_id!r} "
            f"security_currency={security_currency!r} portfolio_currency={portfolio_currency!r} "
            f"is_cross_currency={is_cross_currency} reval_status={reval_status!r} "
            f"gross_amount_lc_param={gross_amount_lc!r} _effective_gross_lc={_effective_gross_lc!r} "
            f"trade_cost={trade_cost} fx_rate={fx_rate} "
            f"will_use_override={reval_status == 'NON-REVALUED' and _effective_gross_lc is not None}"
        )
        if reval_status == 'NON-REVALUED' and _effective_gross_lc is not None:
            # NON-REVAL: cost LC comes directly from trade LC amounts (post user edits)
            this_trade_cost_lc = _effective_gross_lc
        else:
            # REVAL (or no LC amount supplied, or same-currency): derive from FX rate
            this_trade_cost_lc = trade_cost * fx_rate

        if current:
            old_total_cost_lc = Decimal(str(current.get('total_cost_lc', 0) or 0))
            if old_total_cost_lc == 0:
                old_total_cost_lc = Decimal(str(current.get('total_cost_fc') or current.get('total_cost', 0) or 0)) * fx_rate
            trade_cost_lc = this_trade_cost_lc
            new_total_cost_lc = old_total_cost_lc + trade_cost_lc
            new_avg_cost_lc = (new_total_cost_lc / new_qty).quantize(
                self.AVP_PRECISION, rounding=ROUND_HALF_UP
            )
            old_realized_pnl_lc = Decimal(str(current.get('realized_pnl_lc', 0) or 0))
        else:
            trade_cost_lc = this_trade_cost_lc
            new_total_cost_lc = trade_cost_lc
            new_avg_cost_lc = (new_total_cost_lc / new_qty).quantize(
                self.AVP_PRECISION, rounding=ROUND_HALF_UP
            )
            old_realized_pnl_lc = Decimal('0')

        # market_value_lc always uses the FX table rate (date-bound), implied only as last resort
        market_value_lc = market_value * fx_rate

        # Carry forward CA/CF fields from current position (never wiped on BUY)
        carried_dividend_fc = float(current.get('dividend_fc', 0) or 0) if current else 0
        carried_dividend_lc = float(current.get('dividend_lc', 0) or 0) if current else 0
        # uncall/pipeline: use explicitly passed value; else carry from current; else 0
        carried_uncall_fc = float(uncall_fc) if uncall_fc is not None else (
            float(current.get('uncall_fc', 0) or 0) if current else 0
        )
        carried_uncall_lc = float(uncall_lc) if uncall_lc is not None else (
            float(current.get('uncall_lc', 0) or 0) if current else 0
        )
        carried_pipeline_fc = float(pipeline_fc) if pipeline_fc is not None else (
            float(current.get('pipeline_fc', 0) or 0) if current else 0
        )
        carried_pipeline_lc = float(pipeline_lc) if pipeline_lc is not None else (
            float(current.get('pipeline_lc', 0) or 0) if current else 0
        )
        carried_provision_fc = float(current.get('provision_fc', 0) or 0) if current else 0
        carried_provision_lc = float(current.get('provision_lc', 0) or 0) if current else 0

        # net_book_value = cost + unrealized_pnl - provision
        net_book_value_fc = float(new_total_cost) + float(unrealized_pnl) - carried_provision_fc
        net_book_value_lc = float(new_total_cost_lc) + float(market_value_lc - new_total_cost_lc) - carried_provision_lc

        # Build position data
        # FC = Foreign Currency (Security Currency)
        # LC = Local Currency (Portfolio Currency)
        position_data = {
            'position_id': position_id,
            'portfolio_short_name': portfolio_id,
            'security_label': security_id,
            'quantity': float(new_qty),
            # Cost in FC (Foreign Currency = Security Currency)
            'average_cost_fc': float(new_avg_cost),
            'total_cost_fc': float(new_total_cost),
            # Cost in LC (Local Currency = Portfolio Currency)
            'average_cost_lc': float(new_avg_cost_lc),
            'total_cost_lc': float(new_total_cost_lc),
            # Market value
            'market_price': float(market_price),
            'market_value_fc': float(market_value),
            'market_value_lc': float(market_value_lc),
            # P&L
            'unrealized_pnl_fc': float(unrealized_pnl),
            'realized_pnl_fc': float(old_realized_pnl),
            'realized_pnl_lc': float(old_realized_pnl_lc),
            # Dividend tracking (carry forward from current)
            'dividend_fc': carried_dividend_fc,
            'dividend_lc': carried_dividend_lc,
            # Net book value (cost + unrealized_pnl - provision)
            'net_book_value_fc': net_book_value_fc,
            'net_book_value_lc': net_book_value_lc,
            # Provision (carry forward from current)
            'provision_fc': carried_provision_fc,
            'provision_lc': carried_provision_lc,
            # Trade reference
            'trade_id': trade_id,
            'trade_type': 'BUY',
            'position_date': position_date,
            'status': 'OPEN',
            'is_active': True,
            'src_system': 'CIS',
            'security_currency': security_currency,
            'portfolio_currency': portfolio_currency,
            'isin': isin,
            'security_name': security_name,
            'custodian': custodian,
            'sub_custodian': sub_custodian,
            'uncall_fc': carried_uncall_fc,
            'uncall_lc': carried_uncall_lc,
            'pipeline_fc': carried_pipeline_fc,
            'pipeline_lc': carried_pipeline_lc,
            'position_type': position_type or 'INT',
            'position_basis': position_basis,
            # Thread through the reval_status already resolved above so
            # _save_position doesn't re-query it independently — see
            # _save_position's reval_status parameter docstring for why a
            # second, separate query here was a real bug (not just a
            # theoretical race): two calls to _get_portfolio_revaluation_status
            # for the same trade could disagree, and _save_position's own
            # answer silently overwrote this function's correct NON-REVAL
            # cost_lc with a REVAL (market-rate) recomputation.
            '_reval_status': reval_status,
            '_is_equity_method': is_equity_method,
            '_expect_prior_version': current is not None,
        }

        # Save to cis_trade_position
        success = self._save_position(position_data, updated_by)

        if success:
            # TODO: Enable position_master sync after table is created
            # Disabled: position_master table may not exist in all environments
            # self._sync_to_position_master(position_data, updated_by)
            return True, "Position updated successfully", position_data
        else:
            return False, "Failed to save position", None

    def _process_sell(
        self,
        current: Optional[Dict[str, Any]],
        portfolio_id: str,
        security_id: str,
        quantity: Decimal,
        price: Decimal,
        position_date: str,
        trade_id: int,
        updated_by: str,
        security_currency: str = None,
        portfolio_currency: str = None,
        isin: str = None,
        security_name: str = None,
        custodian: str = None,
        sub_custodian: str = None,
        uncall_fc: Decimal = None,
        uncall_lc: Decimal = None,
        pipeline_fc: Decimal = None,
        pipeline_lc: Decimal = None,
        position_type: str = None,
        position_basis: str = 'TRADED',
        trade_lc: Decimal = None,
        gross_amount_lc: Decimal = None,
        gross_amount_fc: Decimal = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Process SELL trade - decrease position, AVP unchanged.

        Formula:
            realized_pnl = (sell_price - avg_cost) * sell_qty
            new_quantity = old_quantity - sell_qty
            new_avg_cost = old_avg_cost (unchanged)
        """
        # Validate: cannot sell without position
        if not current:
            return False, f"No position found for {security_id} in portfolio {portfolio_id}", None

        # Defensive: resolve currencies fresh if the caller's event_data payload
        # was missing either one — see _resolve_currencies docstring.
        security_currency, portfolio_currency = self._resolve_currencies(
            portfolio_id, security_id, security_currency, portfolio_currency
        )

        old_qty = Decimal(str(current.get('quantity', 0) or 0))
        # Use new column name average_cost_fc (fallback to average_cost for backward compat)
        old_avg_cost = Decimal(str(current.get('average_cost_fc') or current.get('average_cost', 0) or 0))
        # Use new column name realized_pnl_fc (fallback to realized_pnl for backward compat)
        old_realized_pnl = Decimal(str(current.get('realized_pnl_fc') or current.get('realized_pnl', 0) or 0))
        # position_id is always deterministic from the natural key of THIS date — never
        # inherited from the prior-date accumulator (which has a different position_date).
        position_id = _calc_position_id(
            portfolio_id, security_id, position_basis, position_date, 'CIS'
        )

        # Validate: no short selling
        if quantity > old_qty:
            return False, f"Insufficient quantity. Available: {old_qty}, Requested: {quantity}", None

        # Calculate realized P&L for this sale
        realized_pnl_this_trade = (price - old_avg_cost) * quantity
        new_realized_pnl = old_realized_pnl + realized_pnl_this_trade

        # Calculate new position
        new_qty = old_qty - quantity

        # Cost basis uses gross amounts (qty × price), never total (which includes charges).
        # Use the trade's exact gross_amount_fc when supplied (migration/UI-edited
        # amount) rather than recomputing quantity * price -- the two can differ by
        # a small amount when the source system's price has more precision than
        # what's stored in the `price` column, and SA direction is that the
        # tallied amount wins (30/07/2026) -- same rule _process_buy applies to trade_cost.
        sell_fc = Decimal(str(gross_amount_fc)) if gross_amount_fc else price * quantity
        is_cross_currency = bool(
            security_currency and portfolio_currency and security_currency != portfolio_currency
        )
        reval_status = self._get_portfolio_revaluation_status(portfolio_id)
        # Associates/subsidiaries are carried at cost (equity method) — no MTM.
        # Computed once here (not per-branch) and threaded through position_data as
        # '_is_equity_method' so _save_position doesn't need its own query to gate
        # unrealized_pnl_lc.
        is_equity_method = self._is_equity_method_security(security_id)

        _effective_sell_lc = (
            Decimal(str(gross_amount_lc)) if gross_amount_lc and is_cross_currency else None
        )
        # Implied rate fallback only for NON-REVAL — REVAL must always trust the FX
        # table (SA PORTIARP-8206) even when the table has no data for the pair.
        implied_fx_rate = None
        if (reval_status == 'NON-REVALUED' and _effective_sell_lc
                and sell_fc and sell_fc != Decimal('0')):
            implied_fx_rate = _effective_sell_lc / sell_fc

        # FX rate from table: latest date <= position_date, carry-forward if no exact match.
        fx_rate = Decimal('1')
        if is_cross_currency:
            fx_rate = self._get_fx_rate(
                security_currency, portfolio_currency,
                rate_date=position_date,
                fallback_rate=implied_fx_rate,
            )

        # Get existing LC values from current position
        old_avg_cost_lc = Decimal(str(current.get('average_cost_lc', 0) or 0))
        old_total_cost_lc = Decimal(str(current.get('total_cost_lc', 0) or 0))
        old_realized_pnl_lc = Decimal(str(current.get('realized_pnl_lc', 0) or 0))

        # Fallback if no LC values stored
        if old_avg_cost_lc == 0 and old_avg_cost > 0:
            old_avg_cost_lc = old_avg_cost * fx_rate
            old_total_cost_lc = old_qty * old_avg_cost_lc

        # Realized P&L in LC (SA rule):
        #   NON-REVAL: sell proceeds LC = user-entered trade_lc (total_amount_lc from form),
        #              only for cross-currency trades. Fallback to price × fx_rate otherwise.
        #   REVAL:     sell proceeds LC = price × latest system fx_rate.
        if reval_status == 'NON-REVALUED' and trade_lc is not None and is_cross_currency:
            sell_proceeds_lc = Decimal(str(trade_lc))
            sell_lc_per_unit = sell_proceeds_lc / quantity if quantity else Decimal('0')
            realized_pnl_this_trade_lc = (sell_lc_per_unit - old_avg_cost_lc) * quantity
        else:
            realized_pnl_this_trade_lc = (price * fx_rate - old_avg_cost_lc) * quantity
        new_realized_pnl_lc = old_realized_pnl_lc + realized_pnl_this_trade_lc

        logger.info(
            f"SELL: Selling {quantity} @ {price} from position {position_id}. "
            f"Old: {old_qty} @ {old_avg_cost}, Realized P&L: {realized_pnl_this_trade}, "
            f"Realized P&L LC: {realized_pnl_this_trade_lc}"
        )

        if new_qty <= 0:
            # Position fully closed
            # FC = Foreign Currency (Security Currency)
            # LC = Local Currency (Portfolio Currency)
            position_data = {
                'position_id': position_id,
                'portfolio_short_name': portfolio_id,
                'security_label': security_id,
                'quantity': 0,
                # Cost in FC
                'average_cost_fc': 0,
                'total_cost_fc': 0,
                # Cost in LC
                'average_cost_lc': 0,
                'total_cost_lc': 0,
                # Market value
                'market_price': 0,
                'market_value_fc': 0,
                'market_value_lc': 0,
                # P&L
                'unrealized_pnl_fc': 0,
                'realized_pnl_fc': float(new_realized_pnl),
                'realized_pnl_lc': float(new_realized_pnl_lc),
                # Net book value (zero on full close)
                'net_book_value_fc': 0,
                'net_book_value_lc': 0,
                # Dividend tracking - carry forward from current position
                'dividend_fc': float(current.get('dividend_fc', 0) or 0),
                'dividend_lc': float(current.get('dividend_lc', 0) or 0),
                # Provision - carry forward from current (recorded for audit, position still closed)
                'provision_fc': float(current.get('provision_fc', 0) or 0),
                'provision_lc': float(current.get('provision_lc', 0) or 0),
                # Trade reference
                'trade_id': trade_id,
                'trade_type': 'SELL',
                'position_date': position_date,
                'status': 'CLOSED',
                'is_active': False,
                'src_system': 'CIS',
                'security_currency': security_currency,
                'portfolio_currency': portfolio_currency,
                'isin': isin,
                'security_name': security_name,
                'custodian': custodian,
                'sub_custodian': sub_custodian,
                # uncall/pipeline: carry from current (obligations survive position close)
                'uncall_fc': float(uncall_fc) if uncall_fc is not None else float(current.get('uncall_fc', 0) or 0),
                'uncall_lc': float(uncall_lc) if uncall_lc is not None else float(current.get('uncall_lc', 0) or 0),
                'pipeline_fc': float(pipeline_fc) if pipeline_fc is not None else float(current.get('pipeline_fc', 0) or 0),
                'pipeline_lc': float(pipeline_lc) if pipeline_lc is not None else float(current.get('pipeline_lc', 0) or 0),
                'position_type': position_type or 'INT',
                'position_basis': position_basis,
                '_reval_status': reval_status,
                '_is_equity_method': is_equity_method,
                '_expect_prior_version': current is not None,
            }
            logger.info(f"Position {position_id} fully closed. Total realized P&L: {new_realized_pnl}, LC: {new_realized_pnl_lc}")
        else:
            # Partial sell - AVP unchanged
            new_total_cost = new_qty * old_avg_cost
            new_total_cost_lc = new_qty * old_avg_cost_lc  # LC cost unchanged per unit

            # `is not None` (not truthiness) -- a genuine 0 market price must produce
            # market_value = 0, not silently fall back to old_avg_cost (SA, 2026-08-12).
            market_price_raw = self._get_market_price(security_id)
            market_price = Decimal(str(market_price_raw)) if market_price_raw is not None else old_avg_cost
            market_value = new_qty * market_price
            market_value_lc = market_value * fx_rate  # Calculate market_value_lc
            # Associates/subsidiaries are carried at cost (equity method) — no MTM
            if is_equity_method:
                unrealized_pnl = Decimal('0')
            else:
                unrealized_pnl = market_value - new_total_cost

            # FC = Foreign Currency (Security Currency)
            # LC = Local Currency (Portfolio Currency)
            position_data = {
                'position_id': position_id,
                'portfolio_short_name': portfolio_id,
                'security_label': security_id,
                'quantity': float(new_qty),
                # Cost in FC - unchanged for SELL
                'average_cost_fc': float(old_avg_cost),
                'total_cost_fc': float(new_total_cost),
                # Cost in LC - unchanged for SELL
                'average_cost_lc': float(old_avg_cost_lc),
                'total_cost_lc': float(new_total_cost_lc),
                # Market value
                'market_price': float(market_price),
                'market_value_fc': float(market_value),
                'market_value_lc': float(market_value_lc),
                # P&L
                'unrealized_pnl_fc': float(unrealized_pnl),
                'realized_pnl_fc': float(new_realized_pnl),
                'realized_pnl_lc': float(new_realized_pnl_lc),
                # Dividend / provision / uncall / pipeline — carry forward from current
                'dividend_fc': float(current.get('dividend_fc', 0) or 0),
                'dividend_lc': float(current.get('dividend_lc', 0) or 0),
                'provision_fc': float(current.get('provision_fc', 0) or 0),
                'provision_lc': float(current.get('provision_lc', 0) or 0),
                # Net book value (remaining cost + unrealized_pnl - provision)
                'net_book_value_fc': float(new_total_cost) + float(unrealized_pnl) - float(current.get('provision_fc', 0) or 0),
                'net_book_value_lc': float(new_total_cost_lc) + float(market_value_lc - new_total_cost_lc) - float(current.get('provision_lc', 0) or 0),
                # Trade reference
                'trade_id': trade_id,
                'trade_type': 'SELL',
                'position_date': position_date,
                'status': 'OPEN',
                'is_active': True,
                'src_system': 'CIS',
                'security_currency': security_currency,
                'portfolio_currency': portfolio_currency,
                'isin': isin,
                'security_name': security_name,
                'custodian': custodian,
                'sub_custodian': sub_custodian,
                'uncall_fc': float(uncall_fc) if uncall_fc is not None else float(current.get('uncall_fc', 0) or 0),
                'uncall_lc': float(uncall_lc) if uncall_lc is not None else float(current.get('uncall_lc', 0) or 0),
                'pipeline_fc': float(pipeline_fc) if pipeline_fc is not None else float(current.get('pipeline_fc', 0) or 0),
                'pipeline_lc': float(pipeline_lc) if pipeline_lc is not None else float(current.get('pipeline_lc', 0) or 0),
                'position_type': position_type or current.get('position_type') or 'INT',
                'position_basis': position_basis,
                '_reval_status': reval_status,
                '_is_equity_method': is_equity_method,
                '_expect_prior_version': current is not None,
            }

        # Save to cis_trade_position
        success = self._save_position(position_data, updated_by)

        if success:
            # TODO: Enable position_master sync after table is created
            # Disabled: position_master table may not exist in all environments
            # self._sync_to_position_master(position_data, updated_by)
            return True, "Position updated successfully", position_data
        else:
            return False, "Failed to save position", None

    # =========================================================================
    # POSITION DATA ACCESS
    # =========================================================================

    def _get_current_position(self, portfolio_id: str, security_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current open position for portfolio-security combination.

        Returns the latest version (is_latest=true) of the most recent position_date.
        """
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
              AND security_label = '{self._escape(security_id)}'
              AND status = 'OPEN'
              AND is_active = true
              AND (is_latest = true OR is_latest IS NULL)
            ORDER BY position_date DESC, version_id DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting current position: {str(e)}")
            return None

    # Retry a "no prior position found" result before trusting it — guards against
    # a Kudu/Impala read-after-write race where a just-committed row from a
    # previous trade on the same portfolio/security/basis hasn't yet propagated
    # to the connection this query lands on. Without this, the query silently
    # returns empty, the caller treats it as "first trade for this date" and
    # creates a brand-new position instead of adding to the existing one —
    # observed 2026-07-22: a second same-day BUY on TRADED basis overwrote a
    # qty=10 position with qty=20 instead of accumulating to 30, while the
    # SETTLED-basis lookup for the identical trade succeeded moments later.
    _STALE_READ_RETRY_ATTEMPTS = 2
    _STALE_READ_RETRY_DELAY_SECONDS = 0.5

    def _get_position_as_of_date(
        self,
        portfolio_id: str,
        security_id: str,
        as_of_date: str,
        include_same_date: bool = True,
        position_basis: str = 'TRADED',
        exclude_trade_id: int = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get position as of a specific date, scoped to a specific position_basis.

        Critical for dual-position logic: TRADED and SETTLED positions are
        stored separately. Each basis chain must only look at its own prior positions
        to avoid cross-contamination of AVP calculations.

        Args:
            portfolio_id: Portfolio short name
            security_id: Security label
            as_of_date: Date to check (YYYY-MM-DD)
            include_same_date: If True, includes positions with position_date <= as_of_date
                              If False, only positions with position_date < as_of_date (for backdated)
            position_basis: 'TRADED' or 'SETTLED' — scope lookup to this basis only
            exclude_trade_id: Exclude the row written by this trade_id (used during chain recalc
                              so a trade does not use its own just-written row as its base)

        Returns the latest version (is_latest=true) with position_date <= or < as_of_date.
        A "not found" result is retried a couple of times with a short delay before
        being trusted — see _STALE_READ_RETRY_ATTEMPTS docstring above.

        Falls back to cis_position (the golden/reporting copy) when
        cis_trade_position has no row at all for this natural key — e.g. a
        position fed purely from AMS/GMP that has never had a CIS trade booked
        against it. Without this, the first CIS trade against such a position
        would start its AVP chain from zero instead of resuming from the known
        balance. Mirrors the same CIS-ledger-first/golden-copy-fallback pattern
        already used by process_approved_cashflows.py's _get_current_positions().
        """
        date_operator = '<=' if include_same_date else '<'

        exclude_clause = ''
        if exclude_trade_id is not None:
            exclude_clause = f'AND (trade_id != {exclude_trade_id} OR trade_id IS NULL)'

        query = f"""
        SELECT *
        FROM {self.DATABASE}.{self.POSITION_TABLE}
        WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
          AND security_label = '{self._escape(security_id)}'
          AND position_date {date_operator} '{as_of_date}'
          AND position_basis = '{position_basis}'
          AND (is_latest = true OR is_latest IS NULL)
          {exclude_clause}
        ORDER BY position_date DESC, version_id DESC
        LIMIT 1
        """

        for attempt in range(1 + self._STALE_READ_RETRY_ATTEMPTS):
            try:
                results = impala_manager.execute_query(query, database=self.DATABASE)
                if results:
                    return results[0]
            except Exception as e:
                logger.error(f"Error getting position as of {as_of_date}: {str(e)}")
                return None

            if attempt < self._STALE_READ_RETRY_ATTEMPTS:
                logger.warning(
                    f"_get_position_as_of_date found nothing for "
                    f"{portfolio_id}/{security_id} basis={position_basis} "
                    f"as_of={as_of_date} (attempt {attempt + 1}/"
                    f"{1 + self._STALE_READ_RETRY_ATTEMPTS}) — retrying in "
                    f"{self._STALE_READ_RETRY_DELAY_SECONDS}s in case of a "
                    f"Kudu read-after-write propagation delay"
                )
                time.sleep(self._STALE_READ_RETRY_DELAY_SECONDS)

        return self._get_position_from_golden_copy(
            portfolio_id, security_id, as_of_date, date_operator, position_basis
        )

    def _get_position_from_golden_copy(
        self,
        portfolio_id: str,
        security_id: str,
        as_of_date: str,
        date_operator: str,
        position_basis: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Fallback base for _get_position_as_of_date() when cis_trade_position has
        no row: read the latest cis_position (golden copy) row and reshape it
        into the same field names _process_buy/_process_sell read off `current`.

        Only ever used as a *base to build on* — the resulting trade always
        writes a proper new cis_trade_position row via _save_position()
        regardless of whether `current` came from here or the real ledger, so
        this doesn't need position_id/version_id/is_latest/trade_id semantics.
        """
        try:
            rows = impala_manager.execute_query(
                f"""
                SELECT
                    quantity,
                    average_cost_fc,
                    cost_fc            AS total_cost_fc,
                    average_cost_lc,
                    cost_lc            AS total_cost_lc,
                    realized_pnl_fc,
                    realized_pnl_lc,
                    dividend_fc,
                    dividend_lc,
                    uncall_fc,
                    uncall_lc,
                    pipeline_fc,
                    pipeline_lc,
                    provision_fc,
                    provision_lc,
                    position_type,
                    position_date,
                    src_system
                FROM {self.DATABASE}.cis_position
                WHERE portfolio = '{self._escape(portfolio_id)}'
                  AND security_label = '{self._escape(security_id)}'
                  AND position_basis = '{position_basis}'
                  AND position_date {date_operator} '{as_of_date}'
                  AND quantity > 0
                  AND (is_latest = true OR is_latest IS NULL)
                ORDER BY position_date DESC
                LIMIT 1
                """,
                database=self.DATABASE
            )
        except Exception as e:
            logger.error(
                f"Error reading cis_position fallback for {portfolio_id}/{security_id} "
                f"basis={position_basis} as_of={as_of_date}: {str(e)}"
            )
            return None

        if not rows:
            return None

        logger.info(
            f"_get_position_as_of_date: no cis_trade_position row for "
            f"{portfolio_id}/{security_id} basis={position_basis} — "
            f"falling back to cis_position (src_system={rows[0].get('src_system')}, "
            f"position_date={rows[0].get('position_date')})"
        )
        return rows[0]

    def get_position(self, portfolio_id: str, security_id: str) -> Optional[Dict[str, Any]]:
        """Public method to get current position."""
        return self._get_current_position(portfolio_id, security_id)

    def get_all_positions(
        self,
        portfolio_id: str = None,
        status: str = 'OPEN',
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Get all positions with optional filters.

        Only returns latest versions (is_latest=true) for each portfolio+security combination.
        """
        try:
            where_clauses = ["(is_latest = true OR is_latest IS NULL)"]

            if portfolio_id:
                where_clauses.append(f"portfolio_short_name = '{self._escape(portfolio_id)}'")

            if status:
                where_clauses.append(f"status = '{self._escape(status)}'")

            where_clause = " AND ".join(where_clauses)

            # Get latest version (is_latest=true) per portfolio+security, most recent date
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE {where_clause}
            ORDER BY position_date DESC, created_at DESC
            LIMIT {limit}
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []
        except Exception as e:
            logger.error(f"Error getting all positions: {str(e)}")
            return []

    # =========================================================================
    # POSITION PERSISTENCE
    # =========================================================================

    def _save_position(self, position_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Save position to cis_trade_position table (versioned, immutable).

        Version-based approach:
        1. Mark any existing versions for same portfolio+security+position_date as is_latest=false
        2. Insert new version with is_latest=true
        3. Never delete - maintains full audit trail
        """
        try:
            version_id = self._generate_id()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            position_date = position_data.get('position_date', timestamp[:10])
            portfolio_id = position_data['portfolio_short_name']
            security_id = position_data['security_label']

            # Step 1: Mark existing versions for this date as is_latest=false
            # This is done via UPSERT with the same version_id but is_latest=false
            position_basis = position_data.get('position_basis', 'TRADED')
            self._mark_old_versions_not_latest(
                portfolio_id, security_id, position_date, position_basis,
                expect_prior_version=bool(position_data.get('_expect_prior_version'))
            )

            # Get FX rate for multi-currency calculations
            # Use strict=True for cross-currency positions to ensure accurate AVP
            security_currency = position_data.get('security_currency', '')
            portfolio_currency = position_data.get('portfolio_currency', '')
            is_cross_currency = security_currency and portfolio_currency and security_currency != portfolio_currency
            try:
                fx_rate_raw = self._get_fx_rate(
                    security_currency, portfolio_currency,
                    rate_date=position_date,
                    strict=is_cross_currency,
                ) if security_currency and portfolio_currency else Decimal('1')
            except ValueError as e:
                # Log error and use 1.0 as fallback, but mark position as needing FX review
                logger.error(f"FX rate lookup failed for position {portfolio_id}/{security_id}: {e}")
                fx_rate_raw = Decimal('1')
                # TODO: Could add a flag to position record indicating FX rate issue
            # Convert to float for calculations (fx_rate returns Decimal)
            fx_rate = float(fx_rate_raw) if fx_rate_raw else 1.0

            # Calculate LC (portfolio currency) values from FC (security currency) values
            # FC = Foreign Currency = Security Currency (where trade happens)
            # LC = Local Currency = Portfolio Currency (reporting currency)
            quantity = float(position_data.get('quantity', 0) or 0)
            # Use _fc suffixed fields (set by _process_buy/_process_sell), fallback to non-suffixed for backward compat
            average_cost = float(position_data.get('average_cost_fc') or position_data.get('average_cost', 0) or 0)
            total_cost = float(position_data.get('total_cost_fc') or position_data.get('total_cost', 0) or 0)
            realized_pnl = float(position_data.get('realized_pnl_fc') or position_data.get('realized_pnl', 0) or 0)
            unrealized_pnl = float(position_data.get('unrealized_pnl_fc') or position_data.get('unrealized_pnl', 0) or 0)
            market_value = float(position_data.get('market_value_fc') or position_data.get('market_value', 0) or 0)

            # Get portfolio revaluation status — prefer the value the caller
            # already resolved (_process_buy/_process_sell compute this once
            # and pass it through as position_data['_reval_status']). Re-
            # querying independently here was a real bug: if this second,
            # separate call to _get_portfolio_revaluation_status ever
            # disagreed with the caller's earlier answer for the same trade,
            # it silently overwrote a correct NON-REVAL cost_lc (computed
            # upstream in _process_buy/_process_sell) with a REVAL market-
            # rate recomputation — with no error, no log trace at the
            # decision point, since this function has no reason to think
            # anything is wrong.
            revaluation_status = position_data.get('_reval_status') or \
                self._get_portfolio_revaluation_status(portfolio_id)
            logger.debug(f"Portfolio {portfolio_id} revaluation_status: {revaluation_status}")

            # Equity-method securities (ASSOC/SUBSI) are carried at cost — no MTM.
            # _process_buy/_process_sell already zero out unrealized_pnl_fc for these
            # via _is_equity_method_security() and thread the answer through as
            # '_is_equity_method' (same passthrough pattern as '_reval_status' above,
            # for the same reason: a second independent query here could disagree).
            # Without this gate, unrealized_pnl_lc below is computed fresh from
            # market_value_lc regardless of investment type, so it comes out non-zero
            # for equity-method securities even though unrealized_pnl_fc is correctly 0.
            is_equity_method = position_data.get('_is_equity_method')
            if is_equity_method is None:
                is_equity_method = self._is_equity_method_security(security_id)

            # LC calculations based on revaluation_status
            # fx_rate = security_currency -> portfolio_currency (e.g., USD/SGD = 1.35)
            if revaluation_status == 'NON-REVALUED':
                # NON-REVALUED: Cost values use historical LC from trade (stored in position_data)
                # Market value uses current FX rate
                # If historical LC not available, fall back to current FX conversion
                average_cost_lc = float(position_data.get('average_cost_lc', 0) or 0)
                if average_cost_lc == 0 and average_cost > 0 and fx_rate:
                    # Fallback: use current FX if historical not available
                    average_cost_lc = average_cost * fx_rate
                    logger.warning(f"No historical average_cost_lc for {portfolio_id}/{security_id}, using current FX")

                total_cost_lc = float(position_data.get('total_cost_lc', 0) or 0)
                if total_cost_lc == 0 and total_cost > 0 and fx_rate:
                    # Fallback: use current FX if historical not available
                    total_cost_lc = total_cost * fx_rate
                    logger.warning(f"No historical total_cost_lc for {portfolio_id}/{security_id}, using current FX")

                realized_pnl_lc = float(position_data.get('realized_pnl_lc', 0) or 0)
                if realized_pnl_lc == 0 and realized_pnl != 0 and fx_rate:
                    # Fallback: use current FX if historical not available
                    realized_pnl_lc = realized_pnl * fx_rate
                    logger.warning(f"No historical realized_pnl_lc for {portfolio_id}/{security_id}, using current FX")

                # Market value LC uses current table FX rate (mark-to-market)
                market_value_lc = market_value * fx_rate if fx_rate else market_value

                # Unrealized P&L LC = market_value_lc - total_cost_lc
                # (0 for equity-method securities — carried at cost, no MTM, mirrors
                # unrealized_pnl_fc which _process_buy/_process_sell already zeroed)
                unrealized_pnl_lc = 0.0 if is_equity_method else market_value_lc - total_cost_lc

                # Override fx_rate stored in cis_trade_position with the implied rate
                # derived from LC cost so carry-forward rows inherit the correct rate.
                # Implied rate = total_cost_lc / total_cost_fc.
                # This does NOT affect market_value_lc (already computed above).
                if total_cost > 0 and total_cost_lc and total_cost_lc != 0:
                    fx_rate = total_cost_lc / total_cost

                logger.info(
                    f"NON-REVALUED position {portfolio_id}/{security_id}: "
                    f"cost_lc={total_cost_lc:.2f} (historical), "
                    f"implied_fx={fx_rate:.8f}, "
                    f"market_lc={market_value_lc:.2f} (current FX), "
                    f"unrealized_lc={unrealized_pnl_lc:.2f}"
                )
            else:
                # REVALUED (default): All values use current FX rate (mark-to-market)
                if fx_rate and fx_rate != 0:
                    average_cost_lc = average_cost * fx_rate
                    total_cost_lc = total_cost * fx_rate
                    realized_pnl_lc = realized_pnl * fx_rate
                    market_value_lc = market_value * fx_rate
                    # 0 for equity-method securities — carried at cost, no MTM.
                    unrealized_pnl_lc = 0.0 if is_equity_method else market_value_lc - total_cost_lc
                else:
                    average_cost_lc = average_cost
                    total_cost_lc = total_cost
                    realized_pnl_lc = realized_pnl
                    market_value_lc = market_value
                    unrealized_pnl_lc = unrealized_pnl

                logger.debug(
                    f"REVALUED position {portfolio_id}/{security_id}: "
                    f"all LC values use current FX rate {fx_rate}"
                )

            # Round amount fields (not average_cost, which stays at AVP_PRECISION)
            # to currency-table precision per SA direction (Teams, 2026-07-30):
            # fc fields -> security currency, lc fields -> portfolio currency.
            # Mutate position_data in place too, since provision_fc/lc and
            # uncall_fc/lc are re-read straight from position_data further
            # below (and by the cis_position gold-sync block) rather than
            # through a local variable.
            fc_dp = self._get_currency_dp(security_currency)
            lc_dp = self._get_currency_dp(portfolio_currency)
            total_cost = self._round_amount(total_cost, fc_dp)
            total_cost_lc = self._round_amount(total_cost_lc, lc_dp)
            market_value = self._round_amount(market_value, fc_dp)
            market_value_lc = self._round_amount(market_value_lc, lc_dp)
            unrealized_pnl = self._round_amount(unrealized_pnl, fc_dp)
            unrealized_pnl_lc = self._round_amount(unrealized_pnl_lc, lc_dp)
            position_data['total_cost_fc'] = total_cost
            position_data['total_cost_lc'] = total_cost_lc
            position_data['market_value_fc'] = market_value
            position_data['market_value_lc'] = market_value_lc
            position_data['unrealized_pnl_fc'] = unrealized_pnl
            position_data['unrealized_pnl_lc'] = unrealized_pnl_lc
            position_data['dividend_fc'] = self._round_amount(float(position_data.get('dividend_fc', 0) or 0), fc_dp)
            position_data['dividend_lc'] = self._round_amount(float(position_data.get('dividend_lc', 0) or 0), lc_dp)
            position_data['uncall_fc'] = self._round_amount(float(position_data.get('uncall_fc', 0) or 0), fc_dp)
            position_data['uncall_lc'] = self._round_amount(float(position_data.get('uncall_lc', 0) or 0), lc_dp)
            position_data['provision_fc'] = self._round_amount(float(position_data.get('provision_fc', 0) or 0), fc_dp)
            position_data['provision_lc'] = self._round_amount(float(position_data.get('provision_lc', 0) or 0), lc_dp)

            # Match columns to cis_trade_position table structure (DDL: 13_avp_tables_kudu.sql)
            # FC = Foreign Currency (Security Currency)
            # LC = Local Currency (Portfolio Currency)
            # Updated column names: average_cost_fc, total_cost_fc, average_cost_lc, total_cost_lc
            # Added: market_price, market_value_fc, dividend_fc, dividend_lc
            # Added: last_cash_flow_amount_fc, last_cash_flow_amount_lc
            columns = [
                'version_id', 'position_id', 'position_date', 'position_basis',
                'portfolio_short_name', 'security_label',
                'quantity',
                # Cost in FC (Foreign Currency = Security Currency)
                'average_cost_fc', 'total_cost_fc',
                # Cost in LC (Local Currency = Portfolio Currency)
                'average_cost_lc', 'total_cost_lc',
                # P&L in FC
                'realized_pnl_fc', 'unrealized_pnl_fc',
                # P&L in LC
                'realized_pnl_lc', 'unrealized_pnl_lc',
                # Market value
                'market_price', 'market_value_fc', 'market_value_lc',
                # Dividend tracking
                'dividend_fc', 'dividend_lc',
                # Trade reference
                'trade_id', 'trade_type',
                'lots_held', 'custodian', 'sub_custodian',
                'security_currency', 'portfolio_currency', 'fx_rate',
                'status', 'is_active', 'is_latest',
                # Uncalled capital (PE/VC)
                'uncall_fc', 'uncall_lc',
                # Pipeline (pending trades/commitments)
                'pipeline_fc', 'pipeline_lc',
                # Provision (carried forward from CA events)
                'provision_fc', 'provision_lc',
                # Position classification
                'position_type',
                'created_by', 'created_at', 'updated_by', 'updated_at'
            ]

            # Helper to cast decimal values — use DECIMAL(30,8) in the CAST expression
            # to avoid Impala "Decimal expression overflow" for large LC values
            # (e.g. total_cost_lc = large_cost_fc * HKD_fx_rate > 12 integer digits).
            # Column is DECIMAL(30,8) — 22 integer digits, matches cis_trade_position DDL.
            def cast_decimal(val):
                if val is None:
                    return 'NULL'
                try:
                    numeric = float(val)
                except (ValueError, TypeError):
                    return 'NULL'
                return f"CAST({numeric} AS DECIMAL(30,8))"

            # Get values from position_data (already set with _fc and _lc suffixes)
            # Fall back to calculated local values for LC values if not in position_data
            average_cost_fc_val = float(position_data.get('average_cost_fc', 0) or 0)
            total_cost_fc_val = float(position_data.get('total_cost_fc', 0) or 0)
            realized_pnl_fc_val = float(position_data.get('realized_pnl_fc', 0) or 0)
            unrealized_pnl_fc_val = float(position_data.get('unrealized_pnl_fc', 0) or 0)
            market_price_val = float(position_data.get('market_price', 0) or 0)
            market_value_fc_val = float(position_data.get('market_value_fc', 0) or 0)
            dividend_fc_val = float(position_data.get('dividend_fc', 0) or 0)
            dividend_lc_val = float(position_data.get('dividend_lc', 0) or 0)

            # Use LC values from position_data if available, otherwise use calculated values
            average_cost_lc_val = float(position_data.get('average_cost_lc', 0) or 0) or average_cost_lc
            total_cost_lc_val = float(position_data.get('total_cost_lc', 0) or 0) or total_cost_lc

            values = [
                str(version_id),
                str(position_data['position_id']),
                f"'{position_date}'",
                f"'{position_basis}'",
                f"'{self._escape(portfolio_id)}'",
                f"'{self._escape(security_id)}'",
                cast_decimal(quantity),
                # Cost in FC
                cast_decimal(average_cost_fc_val),
                cast_decimal(total_cost_fc_val),
                # Cost in LC
                cast_decimal(average_cost_lc_val),
                cast_decimal(total_cost_lc_val),
                # P&L in FC
                cast_decimal(realized_pnl_fc_val),
                cast_decimal(unrealized_pnl_fc_val),
                # P&L in LC
                cast_decimal(realized_pnl_lc),
                cast_decimal(unrealized_pnl_lc),
                # Market value
                cast_decimal(market_price_val),
                cast_decimal(market_value_fc_val),
                cast_decimal(market_value_lc),
                # Dividend tracking
                cast_decimal(dividend_fc_val),
                cast_decimal(dividend_lc_val),
                # Trade reference
                str(position_data.get('trade_id')) if position_data.get('trade_id') else 'NULL',
                f"'{position_data.get('trade_type', '')}'",
                str(position_data.get('lots_held', 0)) if position_data.get('lots_held') else 'NULL',
                f"'{self._escape(position_data.get('custodian', ''))}'" if position_data.get('custodian') else 'NULL',
                f"'{self._escape(position_data.get('sub_custodian', ''))}'" if position_data.get('sub_custodian') else 'NULL',
                f"'{self._escape(security_currency)}'" if security_currency else 'NULL',
                f"'{self._escape(portfolio_currency)}'" if portfolio_currency else 'NULL',
                cast_decimal(fx_rate) if fx_rate else 'NULL',
                f"'{position_data.get('status', 'OPEN')}'",
                str(position_data.get('is_active', True)).lower(),
                'true',  # is_latest = true for new version
                # Uncalled capital (PE/VC)
                cast_decimal(position_data.get('uncall_fc', 0) or 0),
                cast_decimal(position_data.get('uncall_lc', 0) or 0),
                # Pipeline (pending trades/commitments)
                cast_decimal(position_data.get('pipeline_fc', 0) or 0),
                cast_decimal(position_data.get('pipeline_lc', 0) or 0),
                # Provision (carried from CA events)
                cast_decimal(position_data.get('provision_fc', 0) or 0),
                cast_decimal(position_data.get('provision_lc', 0) or 0),
                # Position classification
                f"'{position_data.get('position_type', 'INT')}'" if position_data.get('position_type') else "'INT'",
                f"'{self._escape(updated_by)}'",
                f"'{timestamp}'",
                f"'{self._escape(updated_by)}'",
                f"'{timestamp}'"
            ]

            query = f"""
            UPSERT INTO {self.DATABASE}.{self.POSITION_TABLE}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)
            if success:
                logger.info(
                    f"Saved position version {version_id} for position {position_data['position_id']} "
                    f"(date={position_date}, is_latest=true)"
                )

                # Sync to cis_position gold table
                # TODO: DUAL POSITION LOGIC — position_basis hardcoded 'TRADED' here is WRONG.
                # Once dual position logic is implemented, position_basis must come from
                # position_data (set by caller via calculate_position's position_basis param).
                # See trade_kudu_repository.py TODO for full implementation plan.
                provision_fc_val = float(position_data.get('provision_fc', 0) or 0)
                provision_lc_val = float(position_data.get('provision_lc', 0) or 0)
                # Rounded to currency precision like the other amount fields it's
                # built from (cost/unrealized_pnl/provision) -- not just for
                # consistency, but because summing/subtracting large floats here
                # (values can run into the billions) loses precision at exactly
                # this magnitude, e.g. cost + unrealized_pnl - 0 landing on
                # X.33984000 instead of the mathematically exact X.34.
                net_book_value_fc_val = self._round_amount(float(position_data.get(
                    'net_book_value_fc',
                    total_cost + unrealized_pnl - provision_fc_val
                ) or 0), fc_dp)
                net_book_value_lc_val = self._round_amount(float(position_data.get(
                    'net_book_value_lc',
                    total_cost_lc + unrealized_pnl_lc - provision_lc_val
                ) or 0), lc_dp)
                sync_data = {
                    'position_id': position_data['position_id'],
                    'version_id': version_id,
                    'portfolio': portfolio_id,
                    'security_label': security_id,
                    'position_basis': position_data.get('position_basis', 'TRADED'),  # TODO: pass from caller
                    'position_date': position_date,
                    'src_system': 'CIS',
                    'processing_date': timestamp[:10].replace('-', ''),  # YYYYMMDD
                    'quantity': quantity,
                    'average_cost_fc': average_cost,
                    'cost_fc': total_cost,
                    'market_value_fc': market_value,
                    'net_book_value_fc': net_book_value_fc_val,
                    'unrealized_pnl_fc': unrealized_pnl,
                    'average_cost_lc': average_cost_lc,
                    'cost_lc': total_cost_lc,
                    'market_value_lc': market_value_lc,
                    'net_book_value_lc': net_book_value_lc_val,
                    'unrealized_pnl_lc': unrealized_pnl_lc,
                    'provision_fc': provision_fc_val,
                    'provision_lc': provision_lc_val,
                    'dividend_fc': dividend_fc_val,
                    'dividend_lc': dividend_lc_val,
                    'realized_pnl_fc': realized_pnl,
                    'realized_pnl_lc': realized_pnl_lc,
                    'isin': position_data.get('isin', ''),
                }
                self._sync_to_cis_position(sync_data, updated_by)

            return success

        except Exception as e:
            logger.error(f"Error saving position: {str(e)}")
            return False

    def _sync_to_cis_position(self, position_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Sync CIS position to cis_position gold/master table.

        This is called whenever a position is saved to cis_trade_position with is_latest=true.
        The cis_position table is the consolidated view from all source systems.

        Schema from production (cis_position):
            position_id, version_id, portfolio, security_label, position_basis,
            position_date, src_system, processing_date, quantity, average_cost_fc,
            cost_fc, market_value_fc, net_book_value_fc, unrealized_pnl_fc,
            cost_lc, market_value_lc, net_book_value_lc, unrealized_pnl_lc,
            provision_fc, provision_lc, dividend_fc, dividend_lc,
            realized_pnl_fc, realized_pnl_lc, isin, average_cost_lc,
            source_table, processing_timestamp

        Args:
            position_data: Position data to sync
            updated_by: User performing the update

        Returns:
            True if sync successful, False otherwise
        """
        try:
            # cis_position table columns (matching actual production schema)
            # Note: average_cost renamed to average_cost_fc, placeholder_2 renamed to average_cost_lc
            columns = [
                'position_id', 'version_id', 'portfolio', 'security_label',
                'position_basis', 'position_date', 'src_system', 'processing_date',
                'quantity',
                'average_cost_fc',      # Avg cost in Security Currency (renamed from average_cost)
                'cost_fc',              # Total cost in Security Currency
                'market_value_fc',
                'net_book_value_fc',
                'unrealized_pnl_fc',
                'cost_lc',              # Total cost in Portfolio Currency
                'market_value_lc',
                'net_book_value_lc',
                'unrealized_pnl_lc',
                'provision_fc', 'provision_lc',
                'dividend_fc', 'dividend_lc',
                'realized_pnl_fc', 'realized_pnl_lc',
                'isin',
                'average_cost_lc',      # Avg cost in Portfolio Currency (renamed from placeholder_2)
                'source_table', 'processing_timestamp',
                'uncall_fc', 'uncall_lc',
                'pipeline_fc', 'pipeline_lc',
                'position_type', 'is_latest'
            ]

            # cis_position uses DECIMAL(30,8) columns.
            def cast_decimal(val, precision=8):
                if val is None:
                    return f'CAST(0 AS DECIMAL(30,{precision}))'
                try:
                    return f"CAST({float(val)} AS DECIMAL(30,{precision}))"
                except (ValueError, TypeError):
                    return f'CAST(0 AS DECIMAL(30,{precision}))'

            values = [
                str(position_data.get('position_id', 0)),
                str(position_data.get('version_id', 0)),
                f"'{self._escape(position_data.get('portfolio', ''))}'",
                f"'{self._escape(position_data.get('security_label', ''))}'",
                f"'{position_data.get('position_basis', 'TRADED')}'",
                f"'{position_data.get('position_date', '')}'",
                "'CIS'",  # src_system - always CIS for CIS-generated positions
                f"'{position_data.get('processing_date', '')}'",
                cast_decimal(position_data.get('quantity', 0)),
                cast_decimal(position_data.get('average_cost_fc', 0)),
                cast_decimal(position_data.get('cost_fc', 0)),
                cast_decimal(position_data.get('market_value_fc', 0)),
                cast_decimal(position_data.get('net_book_value_fc', 0)),
                cast_decimal(position_data.get('unrealized_pnl_fc', 0)),
                cast_decimal(position_data.get('cost_lc', 0)),
                cast_decimal(position_data.get('market_value_lc', 0)),
                cast_decimal(position_data.get('net_book_value_lc', 0)),
                cast_decimal(position_data.get('unrealized_pnl_lc', 0)),
                cast_decimal(position_data.get('provision_fc', 0)),
                cast_decimal(position_data.get('provision_lc', 0)),
                cast_decimal(position_data.get('dividend_fc', 0)),
                cast_decimal(position_data.get('dividend_lc', 0)),
                cast_decimal(position_data.get('realized_pnl_fc', 0)),
                cast_decimal(position_data.get('realized_pnl_lc', 0)),
                f"'{self._escape(position_data.get('isin', ''))}'",
                cast_decimal(position_data.get('average_cost_lc', 0)),
                f"'{self._escape(position_data.get('source_table', 'cis_trade'))}'",
                f"'{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}'",  # processing_timestamp
                cast_decimal(position_data.get('uncall_fc', 0)),
                cast_decimal(position_data.get('uncall_lc', 0)),
                cast_decimal(position_data.get('pipeline_fc', 0)),
                cast_decimal(position_data.get('pipeline_lc', 0)),
                f"'{position_data.get('position_type', 'INT')}'" if position_data.get('position_type') else "'INT'",
                'true'  # is_latest — _sync_to_cis_position is only called for the new is_latest=true version
            ]

            query = f"""
            UPSERT INTO {self.DATABASE}.cis_position
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)
            if success:
                logger.info(
                    f"Synced to cis_position: {position_data.get('portfolio')}/{position_data.get('security_label')}"
                )
            else:
                logger.warning(
                    f"Failed to sync to cis_position: {position_data.get('portfolio')}/{position_data.get('security_label')}"
                )

            return success

        except Exception as e:
            logger.error(f"Error syncing to cis_position: {str(e)}")
            # Don't fail the main operation if gold table sync fails
            return False

    def _mark_old_versions_not_latest(
        self,
        portfolio_id: str,
        security_id: str,
        position_date: str,
        position_basis: str = 'TRADED',
        expect_prior_version: bool = False
    ) -> bool:
        """
        Mark existing versions for a position_date+basis as is_latest=false.

        Scoped to position_basis so TRADED and SETTLED chains are
        independently versioned — recalculating one basis never stomps on the other.

        Note: Kudu doesn't support UPDATE with complex WHERE, so we need to:
        1. Query existing versions for this date+basis
        2. Re-insert each with is_latest=false

        expect_prior_version: True when the caller already confirmed (moments earlier,
        in the same calculate_position() call) that a position row exists for this
        date+basis — e.g. it was read back as `current` before this trade was applied.
        If the SELECT below comes back empty despite that, it's very likely a stale
        read on a different pooled connection (Kudu/Impala doesn't guarantee
        read-your-writes across connections — the same class of issue already worked
        around with a sleep in position_queue_service._process_chain_recalculation),
        not evidence the row doesn't exist. One short retry resolves it without
        adding latency to the common cases (truly-fresh positions correctly find
        nothing on the first try and never retry; existing positions usually find
        the row on the first try too).
        """
        try:
            query = f"""
            SELECT version_id, position_id, position_date,
                   portfolio_short_name, security_label,
                   quantity, average_cost_fc, total_cost_fc,
                   average_cost_lc, total_cost_lc,
                   realized_pnl_fc, unrealized_pnl_fc,
                   realized_pnl_lc, unrealized_pnl_lc,
                   market_price, market_value_fc, market_value_lc,
                   dividend_fc, dividend_lc,
                   provision_fc, provision_lc,
                   trade_id, trade_type,
                   lots_held, custodian, sub_custodian,
                   security_currency, portfolio_currency, fx_rate,
                   status, is_active,
                   created_by, created_at, updated_by, updated_at
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
              AND security_label = '{self._escape(security_id)}'
              AND position_date = '{position_date}'
              AND position_basis = '{position_basis}'
              AND (is_latest = true OR is_latest IS NULL)
            """

            existing = impala_manager.execute_query(query, database=self.DATABASE)

            if not existing and expect_prior_version:
                # Caller confirmed a row should exist — this is very likely a stale
                # read on a different pooled connection, not a genuine absence.
                # Reuses the same retry budget as _get_position_as_of_date's
                # stale-read guard (_STALE_READ_RETRY_ATTEMPTS/_DELAY_SECONDS)
                # rather than a one-off sleep, so both workarounds for this class
                # of issue stay tunable from one place.
                for attempt in range(self._STALE_READ_RETRY_ATTEMPTS):
                    logger.warning(
                        f"_mark_old_versions_not_latest found no rows for "
                        f"{portfolio_id}/{security_id} {position_basis}/{position_date} "
                        f"despite expect_prior_version=True — retrying "
                        f"({attempt + 1}/{self._STALE_READ_RETRY_ATTEMPTS}, suspected "
                        f"stale read on pooled connection)"
                    )
                    time.sleep(self._STALE_READ_RETRY_DELAY_SECONDS)
                    existing = impala_manager.execute_query(query, database=self.DATABASE)
                    if existing:
                        break

            if not existing:
                # No existing versions to update
                return True

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            for row in existing:
                # Re-insert with is_latest=false (UPSERT by version_id)
                # Using new column names
                update_query = f"""
                UPSERT INTO {self.DATABASE}.{self.POSITION_TABLE}
                (version_id, position_id, position_date, position_basis,
                 portfolio_short_name, security_label,
                 quantity, average_cost_fc, total_cost_fc,
                 average_cost_lc, total_cost_lc,
                 realized_pnl_fc, unrealized_pnl_fc,
                 realized_pnl_lc, unrealized_pnl_lc,
                 market_price, market_value_fc, market_value_lc,
                 dividend_fc, dividend_lc,
                 provision_fc, provision_lc,
                 trade_id, trade_type,
                 lots_held, custodian, sub_custodian,
                 security_currency, portfolio_currency, fx_rate,
                 status, is_active, is_latest,
                 created_by, created_at, updated_by, updated_at)
                VALUES (
                    {row['version_id']}, {row['position_id']}, '{row['position_date']}',
                    '{position_basis}',
                    '{self._escape(row['portfolio_short_name'])}', '{self._escape(row['security_label'])}',
                    CAST({float(row.get('quantity') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('average_cost_fc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('total_cost_fc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('average_cost_lc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('total_cost_lc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('realized_pnl_fc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('unrealized_pnl_fc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('realized_pnl_lc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('unrealized_pnl_lc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('market_price') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('market_value_fc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('market_value_lc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('dividend_fc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('dividend_lc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('provision_fc') or 0)} AS DECIMAL(30,8)),
                    CAST({float(row.get('provision_lc') or 0)} AS DECIMAL(30,8)),
                    {row.get('trade_id') or 'NULL'},
                    '{row.get('trade_type', '')}',
                    {row.get('lots_held') or 'NULL'},
                    {f"'{self._escape(row.get('custodian', ''))}'" if row.get('custodian') else 'NULL'},
                    {f"'{self._escape(row.get('sub_custodian', ''))}'" if row.get('sub_custodian') else 'NULL'},
                    {f"'{self._escape(row.get('security_currency', ''))}'" if row.get('security_currency') else 'NULL'},
                    {f"'{self._escape(row.get('portfolio_currency', ''))}'" if row.get('portfolio_currency') else 'NULL'},
                    {f"CAST({float(row.get('fx_rate'))} AS DECIMAL(30,8))" if row.get('fx_rate') not in (None, '', 0) else 'NULL'},
                    '{row.get('status', 'OPEN')}',
                    {str(row.get('is_active', True)).lower()},
                    false,
                    '{self._escape(row.get('created_by', ''))}',
                    '{row.get('created_at', timestamp)}',
                    'SYSTEM',
                    '{timestamp}'
                )
                """
                impala_manager.execute_write(update_query, database=self.DATABASE)
                logger.debug(f"Marked version {row['version_id']} as is_latest=false")

            logger.info(
                f"Marked {len(existing)} old version(s) as is_latest=false "
                f"for {portfolio_id}/{security_id} on {position_date}"
            )
            return True

        except Exception as e:
            logger.error(f"Error marking old versions: {str(e)}")
            return False

    def _sync_to_position_master(self, position_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Sync CIS position to position_master Hive external table.

        This writes the position to the shared position_master table with src_system='CIS'.
        The table is partitioned by (src_id, processing_date).
        """
        try:
            timestamp = datetime.now()
            processing_date = timestamp.strftime('%d%m%Y')  # DDMMYYYY format
            etl_batch_id = f"CIS-AVP-{timestamp.strftime('%Y%m%d%H%M%S')}"

            # Map CIS position fields to position_master schema
            columns = [
                'portfolio', 'security_full_name', 'security_short_name', 'isin',
                'quantity', 'market_price', 'average_cost',
                'cost_lc', 'market_value_lc', 'unrealized_pnl_lc',
                'product_type', 'security_type', 'security_currency',
                'reporting_date', 'position_basis',
                'src_system', 'source_table',
                'etl_insert_ts', 'etl_batch_id',
                'src_id', 'processing_date'
            ]

            # Build values
            portfolio = self._escape(position_data.get('portfolio_short_name', ''))
            security_label = self._escape(position_data.get('security_label', ''))
            security_name = self._escape(position_data.get('security_name', security_label))
            isin = self._escape(position_data.get('isin', ''))
            quantity = position_data.get('quantity', 0)
            market_price = position_data.get('current_price', 0)
            avg_cost = position_data.get('average_cost', 0)
            total_cost = position_data.get('total_cost', 0)
            market_value = position_data.get('market_value', 0)
            unrealized_pnl = position_data.get('unrealized_pnl', 0)
            security_currency = self._escape(position_data.get('security_currency', ''))
            position_date = position_data.get('position_date', timestamp.strftime('%Y-%m-%d'))

            values = [
                f"'{portfolio}'",
                f"'{security_name}'",
                f"'{security_label}'",
                f"'{isin}'" if isin else 'NULL',
                str(quantity),
                str(market_price),
                str(avg_cost),
                str(total_cost),  # cost_lc
                str(market_value),  # market_value_lc
                str(unrealized_pnl),  # unrealized_pnl_lc
                "'EQUITY'",  # product_type default
                "'COMMON STOCK'",  # security_type default
                f"'{security_currency}'" if security_currency else 'NULL',
                f"'{position_date}'",  # reporting_date
                "'trade_date'",  # position_basis
                "'CIS'",  # src_system
                "'cis_trade_position'",  # source_table
                f"'{timestamp.strftime('%Y-%m-%d %H:%M:%S')}'",  # etl_insert_ts
                f"'{etl_batch_id}'",  # etl_batch_id
                "'CIS'",  # src_id (partition)
                f"'{processing_date}'"  # processing_date (partition)
            ]

            query = f"""
            INSERT INTO {self.DATABASE}.{self.POSITION_MASTER_TABLE}
            PARTITION (src_id='CIS', processing_date='{processing_date}')
            ({', '.join(columns[:-2])})
            VALUES ({', '.join(values[:-2])})
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)
            if success:
                logger.info(f"Synced position to position_master: {portfolio}/{security_label}")
            else:
                logger.warning(f"Failed to sync position to position_master: {portfolio}/{security_label}")

            return success

        except Exception as e:
            logger.error(f"Error syncing to position_master: {str(e)}")
            return False

    # =========================================================================
    # MARKET DATA
    # =========================================================================

    def _get_market_price(self, security_label: str) -> Optional[float]:
        """Fetch latest market price for a security."""
        try:
            query = f"""
            SELECT main_closing_price
            FROM {self.DATABASE}.cis_equity_price
            WHERE security_label = '{self._escape(security_label)}'
              AND is_active = true
            ORDER BY price_date DESC, price_timestamp DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('main_closing_price') is not None:
                return float(results[0]['main_closing_price'])
            return None
        except Exception as e:
            logger.error(f"Error fetching market price for {security_label}: {str(e)}")
            return None

    def _is_equity_method_security(self, security_label: str) -> bool:
        """Return True if security_investment is ASSOC or SUBSI (carried at cost, no MTM)."""
        try:
            query = f"""
            SELECT security_investment
            FROM {self.DATABASE}.cis_security
            WHERE security_name = '{self._escape(security_label)}'
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                inv_type = (results[0].get('security_investment') or '').upper()
                return inv_type in ('ASSOC', 'SUBSI')
        except Exception as e:
            logger.error(f"Error checking security_investment for {security_label}: {str(e)}")
        return False

    def _get_fx_rate(
        self,
        from_ccy: str,
        to_ccy: str,
        rate_date: str = None,
        fallback_rate: Decimal = None,
        strict: bool = False
    ) -> Decimal:
        """
        Get FX rate between currencies using multicurrency service.

        Lookup order:
          1. FX table: latest date <= rate_date (carry-forward if no exact match)
          2. If table has no row at all for that pair: use fallback_rate (implied
             rate back-calculated from the trade's LC/FC amounts)
          3. Never silently return 1.0 for a cross-currency position

        Args:
            from_ccy: Source currency code
            to_ccy: Target currency code
            rate_date: Upper bound date for rate lookup (YYYY-MM-DD). Uses latest
                       available date <= rate_date. Defaults to latest ever if None.
            fallback_rate: Implied rate from trade (gross_amount_lc / gross_amount_fc).
                           Used only when the FX table has zero rows for the pair.
            strict: If True, raise error when rate not found and no fallback available.
        """
        if from_ccy == to_ccy:
            return Decimal('1')

        if not from_ccy or not to_ccy:
            if strict:
                raise ValueError(f"Currency codes are required for FX rate lookup. "
                                f"Got from='{from_ccy}', to='{to_ccy}'")
            return fallback_rate if fallback_rate else Decimal('1')

        try:
            rate, date_used = multicurrency_service.get_fx_rate(
                from_ccy, to_ccy, rate_date=rate_date, strict=False
            )
            # multicurrency_service returns Decimal('1') silently when nothing found.
            # Detect that case by checking if currencies differ but rate is exactly 1.
            # If so and we have a fallback, prefer the fallback over the silent default.
            if rate == Decimal('1') and fallback_rate and fallback_rate != Decimal('1'):
                logger.warning(
                    f"FX table returned no rate for {from_ccy}-{to_ccy} "
                    f"(rate_date={rate_date}). Using implied trade rate {fallback_rate}."
                )
                return fallback_rate
            if date_used:
                logger.debug(
                    f"FX rate {from_ccy}-{to_ccy}: {rate} from {date_used} "
                    f"(requested date: {rate_date})"
                )
            return rate
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error fetching FX rate for {from_ccy}-{to_ccy}: {str(e)}")
            if strict:
                raise ValueError(f"Error fetching FX rate for {from_ccy}-{to_ccy}: {str(e)}")
            return fallback_rate if fallback_rate else Decimal('1')

    def _get_portfolio_revaluation_status(self, portfolio_id: str) -> str:
        """
        Get portfolio revaluation status from cis_portfolio table.

        Args:
            portfolio_id: Portfolio short name

        Returns:
            'REVALUED' or 'NON-REVALUED' (defaults to 'REVALUED' if genuinely
            not found in cis_portfolio after retrying transient errors)

        IMPORTANT: a transient connection error here (e.g. Kudu/Impala
        TTransportException on a stale pooled connection) used to be
        silently swallowed and treated as "default to REVALUED" — exactly
        as if the portfolio were genuinely REVALUED. For a NON-REVALUED
        portfolio, that silently skips the cost_lc override in
        _process_buy/_process_sell and falls back to the market FX rate,
        with only a logger.error line (easy to miss) and no other symptom.
        This caused intermittent wrong cost_lc with no reproducible pattern.
        Now retries once before giving up, and raises on repeated failure
        so the caller's trade genuinely fails/retries instead of silently
        computing against the wrong revaluation basis.
        """
        query = f"""
        SELECT revaluation_status
        FROM {self.DATABASE}.cis_portfolio
        WHERE name = '{self._escape(portfolio_id)}'
        LIMIT 1
        """
        last_error = None
        for attempt in range(2):
            try:
                results = impala_manager.execute_query(query, database=self.DATABASE)
                if results and results[0].get('revaluation_status'):
                    status = results[0]['revaluation_status'].upper()
                    if status in ('REVALUED', 'NON-REVALUED'):
                        return status
                # Query succeeded but portfolio genuinely has no/invalid
                # revaluation_status — that's a real "not found", not a
                # transient error, so defaulting to REVALUED is correct here.
                return 'REVALUED'
            except Exception as e:
                last_error = e
                logger.error(
                    f"Error fetching revaluation status for {portfolio_id} "
                    f"(attempt {attempt + 1}/2): {str(e)}"
                )
        raise RuntimeError(
            f"Could not determine revaluation_status for portfolio {portfolio_id} "
            f"after 2 attempts: {last_error}"
        )

    def _resolve_currencies(
        self, portfolio_id: str, security_id: str,
        security_currency: str = None, portfolio_currency: str = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Fall back to a fresh DB lookup when the caller's security_currency/
        portfolio_currency are missing.

        These are normally threaded through from the trade's event_data
        (populated at trade-entry time). If that payload was ever incomplete
        (e.g. security/portfolio lookup returned no currency_code at queue
        time), _process_buy/_process_sell would silently treat the trade as
        same-currency and skip the NON-REVAL cost_lc override entirely —
        falling back to the FX-table market rate with no error or log trace.
        This makes that failure mode impossible: missing currency is always
        resolved fresh rather than silently defaulting to "no FX difference".
        """
        if security_currency and portfolio_currency:
            return security_currency, portfolio_currency
        try:
            if not security_currency:
                rows = impala_manager.execute_query(
                    f"SELECT currency_code FROM {self.DATABASE}.cis_security "
                    f"WHERE security_name = '{self._escape(security_id)}' LIMIT 1",
                    database=self.DATABASE
                )
                if rows and rows[0].get('currency_code'):
                    security_currency = rows[0]['currency_code']
                    logger.warning(
                        f"security_currency missing from caller for {security_id} — "
                        f"resolved fresh from cis_security: {security_currency}"
                    )
            if not portfolio_currency:
                rows = impala_manager.execute_query(
                    f"SELECT currency FROM {self.DATABASE}.cis_portfolio "
                    f"WHERE name = '{self._escape(portfolio_id)}' LIMIT 1",
                    database=self.DATABASE
                )
                if rows and rows[0].get('currency'):
                    portfolio_currency = rows[0]['currency']
                    logger.warning(
                        f"portfolio_currency missing from caller for {portfolio_id} — "
                        f"resolved fresh from cis_portfolio: {portfolio_currency}"
                    )
        except Exception as e:
            logger.error(f"Error resolving fallback currencies for {portfolio_id}/{security_id}: {str(e)}")
        return security_currency, portfolio_currency

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def validate_trade_for_position(
        self,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        portfolio_id: str,
        security_id: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate trade data before position calculation.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Rule 1: Only BUY/SELL affect position
        if trade_type not in self.POSITION_AFFECTING_TYPES:
            return True, []  # Skip validation, trade doesn't affect position

        # Rule 2: Quantity must be positive
        if quantity <= 0:
            errors.append("Trade quantity must be positive")

        # Rule 3: Price must not be negative (zero is allowed)
        if price < 0:
            errors.append("Trade price must not be negative")

        # Rule 4: No short selling (SELL qty <= position qty)
        if trade_type == 'SELL':
            current_position = self._get_current_position(portfolio_id, security_id)
            available_qty = Decimal(str(current_position.get('quantity', 0) or 0)) if current_position else Decimal('0')
            if quantity > available_qty:
                errors.append(
                    f"Insufficient quantity for sale. Available: {available_qty}, Requested: {quantity}"
                )

        return len(errors) == 0, errors

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _generate_id(self) -> int:
        """Generate unique ID for position/version."""
        return int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 1000)

    def _escape(self, value: str) -> str:
        """Escape string value for SQL.

        Impala uses C-style escaping (\\' for a single quote), NOT the ANSI/
        Postgres/MySQL doubled-quote convention (''). Names containing an
        apostrophe (e.g. security "CD INT'L ENT") produced a ParseException
        wherever this was used to build a WHERE/VALUES clause with '' instead
        of \\'.
        """
        if value is None:
            return ''
        s = str(value)
        s = s.replace('\\', '\\\\')  # backslash first
        s = s.replace("'", "\\'")
        return s


# Singleton instance
position_service = PositionService()
