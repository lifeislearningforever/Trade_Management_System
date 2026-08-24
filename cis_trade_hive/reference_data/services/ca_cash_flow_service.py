"""
Corporate Action Cash Flow Service

Service layer for generating cash flows from corporate actions.
Handles dividend, interest, coupon, and other CA types that result in cash flows.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from core.repositories.impala_connection import impala_manager
from reference_data.repositories.ca_cash_flow_queue_repository import ca_cash_flow_queue_repository
from trade.repositories.cash_flow_repository import CashFlowRepository
from trade.services.multicurrency_service import multicurrency_service
from trade.services.position_id_service import position_id as _calc_position_id
from django.conf import settings

logger = logging.getLogger(__name__)


class CACashFlowService:
    """Service for generating cash flows from corporate actions"""

    DATABASE = settings.IMPALA_CONFIG['DATABASE']
    POSITION_TABLE = 'cis_position'         # read: golden copy (all sources)
    WRITE_POSITION_TABLE = 'cis_trade_position'  # write: CIS working ledger (versioned)

    # CA types that generate cash flows (payment to holder)
    # DIVIDEND kept alongside CASH_DIVIDEND as a synonym for CAs synced before
    # the sync_gmp_corporate_actions.py rename to CASH_DIVIDEND -- existing
    # cis_corporate_actions/cis_cash_flow rows still carry ca_type='DIVIDEND'.
    CASH_FLOW_CA_TYPES = [
        'CASH_DIVIDEND', 'DIVIDEND', 'SPECIAL_DIVIDEND', 'INTEREST', 'COUPON', 'ROC',
        'CAPITAL_DISTRIBUTION',
        'INCOME_DISTRIBUTION',  # New: like dividend but accumulates RL_fc/RL_lc
    ]

    # CA types that affect position quantity (no cash flow)
    POSITION_ADJUSTMENT_CA_TYPES = [
        'BONUS_ISSUE', 'SPLIT', 'STOCK_SPLIT', 'REVERSE_SPLIT',
        'RIGHTS_ENTITLEMENT', 'RIGHTS_ISSUE', 'RIGHTS',
        'WARRANT_ENTITLEMENT', 'WARRANTS', 'CONSOLIDATION',
    ]

    # CF-only types: overwrite specific position fields, no cash flow record
    CF_POSITION_OVERWRITE_TYPES = [
        'CF-COMMITMENT',
        'CF-UN CALL COMMITMENT',
        'CF-PIPELINE',
        'CF-YTD',
        'CF-PROVISION',
    ]

    # CA type to Cash Flow type mapping
    CA_TO_CF_TYPE_MAP = {
        'CASH_DIVIDEND': 'CASH_DIVIDEND',
        'DIVIDEND': 'DIVIDEND',
        'SPECIAL_DIVIDEND': 'SPECIAL_DIVIDEND',
        'INTEREST': 'INTEREST',
        'COUPON': 'COUPON',
        'ROC': 'ROC',
        'CAPITAL_DISTRIBUTION': 'CAPITAL_DISTRIBUTION',
        'INCOME_DISTRIBUTION': 'INCOME_DISTRIBUTION',
    }

    # CA types where AVP is unchanged (just cash distribution)
    NO_AVP_CHANGE_CA_TYPES = [
        'CASH_DIVIDEND', 'DIVIDEND', 'SPECIAL_DIVIDEND', 'INTEREST', 'COUPON', 'INCOME_DISTRIBUTION',
    ]

    # CA types where AVP = AVP_old - price_per_share (per-share cost basis reduction)
    # CAPITAL_DISTRIBUTION and ROC both reduce the cost basis per share held
    AVP_REDUCTION_CA_TYPES = ['ROC', 'CAPITAL_DISTRIBUTION']

    @staticmethod
    def _escape(value: str) -> str:
        """Escape string for SQL."""
        if value is None:
            return ''
        return str(value).replace("\\", "\\\\").replace("'", "\\'")

    def _check_existing_cash_flow(
        self,
        ca_number: str,
        portfolio_short_name: str,
        security_name: str,
        ex_date: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if a cash flow already exists for this CA + portfolio + security + ex_date combination.
        Prevents duplicate cash flows when EOD job runs multiple times.

        Returns:
            Cash flow dict if exists, None otherwise
        """
        try:
            # Check by CA number + portfolio + security + ex_date to prevent duplicates
            # per portfolio per CA run. Must include ca_number so different CAs on the
            # same security/ex_date are not blocked by each other.
            query = f"""
            SELECT cash_flow_id, cash_flow_number
            FROM {self.DATABASE}.cis_cash_flow
            WHERE ca_number = '{self._escape(ca_number)}'
              AND portfolio_short_name = '{self._escape(portfolio_short_name)}'
              AND security_label = '{self._escape(security_name)}'
              AND ex_date = '{ex_date}'
              AND (is_deleted = false OR is_deleted IS NULL)
            LIMIT 1
            """
            logger.info(f"[CHECK_DUP] Checking for existing cash flow: ca={ca_number}, portfolio={portfolio_short_name}, security={security_name}, ex_date={ex_date}")
            results = impala_manager.execute_query(query, database=self.DATABASE)
            logger.info(f"[CHECK_DUP] Query returned {len(results) if results else 0} results")
            if results and len(results) > 0:
                row = results[0]
                # Validate the result has actual cash_flow columns (not a mis-mapped result)
                if row.get('cash_flow_id') is not None or row.get('cash_flow_number') is not None:
                    logger.info(f"[CHECK_DUP] Duplicate found: cash_flow_id={row.get('cash_flow_id')}, cf_number={row.get('cash_flow_number')}")
                    return row
                else:
                    logger.warning(f"[CHECK_DUP] Result row has no cash_flow_id/cash_flow_number — ignoring as mis-mapped result: {row}")
                    return None
            return None
        except Exception as e:
            logger.warning(f"[CHECK_DUP] Error checking existing cash flow: {e}")
            return None

    def queue_ca_for_processing(
        self,
        ca_id: int,
        ca_data: Dict[str, Any],
        username: str
    ) -> Tuple[bool, Optional[int]]:
        """
        Queue a corporate action for processing.

        Based on SA Specification:
        - Cash Flow CA Types: DIVIDEND, SPECIAL_DIVIDEND, ROC, INTEREST, COUPON
        - Position Adjustment CA Types: BONUS_ISSUE, SPLIT, RIGHTS_ENTITLEMENT, WARRANT_ENTITLEMENT

        Args:
            ca_id: Corporate Action ID
            ca_data: Corporate Action data dictionary
            username: User triggering the queue

        Returns:
            Tuple of (success, queue_id)
        """
        try:
            ca_type = (ca_data.get('ca_type') or '').strip().upper()

            # Check if CA type requires processing
            if (ca_type not in self.CASH_FLOW_CA_TYPES
                    and ca_type not in self.POSITION_ADJUSTMENT_CA_TYPES
                    and ca_type not in self.CF_POSITION_OVERWRITE_TYPES):
                logger.warning(
                    f"CA type '{ca_type}' is not in any processing type list — "
                    f"no cash flow or position update will occur. "
                    f"If this is a new type, add it to the appropriate list in CACashFlowService."
                )
                return True, None

            # Note: portfolio_name removed - CA applies at security level
            # EOD job will find all portfolios holding the security from positions
            queue_data = {
                'ca_id': ca_id,
                'ca_number': ca_data.get('ca_number'),
                'ca_type': ca_type,
                'security_name': ca_data.get('security_name'),
                'ex_date': ca_data.get('ex_date'),
                'record_date': ca_data.get('record_date'),
                'payment_date': ca_data.get('payment_date'),
                'price': ca_data.get('price'),
                'currency': ca_data.get('currency'),
                'created_by': username,
            }

            success, queue_id = ca_cash_flow_queue_repository.insert(queue_data)

            if success:
                processing_type = "cash flow" if ca_type in self.CASH_FLOW_CA_TYPES else "position adjustment"
                logger.info(f"Queued CA {ca_data.get('ca_number')} for {processing_type} processing")

            return success, queue_id

        except Exception as e:
            logger.error(f"Error queuing CA {ca_id} for processing: {str(e)}")
            return False, None

    def process_ca_cash_flows(
        self,
        queue_id: int,
        dry_run: bool = False,
        run_type: str = 'EOD'
    ) -> Tuple[bool, str, int, Decimal]:
        """
        Process a queued CA based on type.

        Based on SA Specification:
        ┌─────────────────────┬──────────────┬───────────────┬──────────────────────────┐
        │ CA Type             │ Cash Flow    │ Position Qty  │ AVP Calculation          │
        ├─────────────────────┼──────────────┼───────────────┼──────────────────────────┤
        │ DIVIDEND            │ qty × price  │ No change     │ No change                │
        │ SPECIAL_DIVIDEND    │ qty × price  │ No change     │ No change                │
        │ ROC                 │ qty × price  │ No change     │ avp_old - price          │
        │ BONUS_ISSUE         │ 0            │ qty changes   │ total_cost / new_qty     │
        │ SPLIT               │ 0            │ qty changes   │ avp_old / price          │
        │ RIGHTS_ENTITLEMENT  │ 0            │ new position  │ Creates new security     │
        │ WARRANT_ENTITLEMENT │ 0            │ new position  │ Creates new security     │
        └─────────────────────┴──────────────┴───────────────┴──────────────────────────┘

        Args:
            queue_id: Queue entry ID
            dry_run: If True, don't actually process

        Returns:
            Tuple of (success, message, items_processed, total_amount)
        """
        try:
            # Get queue entry
            queue_entry = ca_cash_flow_queue_repository.get_by_id(queue_id)
            if not queue_entry:
                return False, f"Queue entry {queue_id} not found", 0, Decimal('0')

            # Mark as processing
            if not dry_run:
                ca_cash_flow_queue_repository.mark_processing(queue_id)

            ca_type = (queue_entry.get('ca_type') or '').strip().upper()
            security_name = queue_entry.get('security_name')
            ex_date = queue_entry.get('ex_date')
            price = Decimal(str(queue_entry.get('price') or 0))
            currency = queue_entry.get('currency')
            # ca_id comes back from Impala as string — cast to int for BIGINT compatibility
            ca_id = int(queue_entry.get('ca_id')) if queue_entry.get('ca_id') else None
            ca_number = queue_entry.get('ca_number')
            payment_date = queue_entry.get('payment_date')
            record_date = queue_entry.get('record_date')

            # Route to appropriate processor based on CA type
            if ca_type in self.CF_POSITION_OVERWRITE_TYPES:
                # CF-only handlers: overwrite specific position fields, no cash flow
                return self._process_cf_position_overwrite(
                    queue_id=queue_id,
                    queue_entry=queue_entry,
                    dry_run=dry_run
                )

            if ca_type in self.POSITION_ADJUSTMENT_CA_TYPES:
                # Position adjustment types (BONUS_ISSUE, SPLIT, RIGHTS, WARRANT)
                return self._process_position_adjustment_ca(
                    queue_id=queue_id,
                    queue_entry=queue_entry,
                    dry_run=dry_run,
                    run_type=run_type
                )

            # Cash flow generating types - require price
            if not price or price <= 0:
                error_msg = f"Invalid price ({price}) for CA {ca_number}"
                if not dry_run:
                    ca_cash_flow_queue_repository.mark_failed(queue_id, error_msg)
                return False, error_msg, 0, Decimal('0')

            # Get ALL portfolios holding this security (CA applies to security level)
            logger.info(f"[EOD] Looking up holdings for security '{security_name}' as of {ex_date}")
            holdings = self.get_holdings_for_ca(
                security_name=security_name,
                as_of_date=ex_date
            )

            logger.info(f"[EOD] Found {len(holdings) if holdings else 0} holdings for {security_name}")
            if holdings:
                for i, h in enumerate(holdings):
                    logger.info(f"[EOD]   Holding {i+1}: portfolio={h.get('portfolio_short_name')}, "
                               f"security={h.get('security_label')}, qty={h.get('quantity')}")

            if not holdings:
                msg = f"No holdings found for security {security_name} as of {ex_date}"
                logger.info(msg)
                if not dry_run:
                    ca_cash_flow_queue_repository.mark_completed(queue_id, 0, Decimal('0'))
                return True, msg, 0, Decimal('0')

            # Generate cash flows for each holding
            cash_flows_created = 0
            total_amount = Decimal('0')
            errors = []

            logger.info(f"[EOD] Starting cash flow creation loop for {len(holdings)} holdings")
            for idx, holding in enumerate(holdings):
                logger.info(f"[EOD] === Processing holding {idx + 1}/{len(holdings)} ===")
                logger.info(f"[EOD]   Raw holding data: {holding}")

                portfolio_short_name = holding.get('portfolio_short_name')
                quantity = Decimal(str(holding.get('quantity') or 0))
                security_currency = holding.get('security_currency') or currency
                # Get portfolio currency (from position or portfolio table)
                portfolio_currency = (
                    holding.get('portfolio_base_currency') or
                    holding.get('portfolio_currency') or
                    security_currency  # Fallback to security currency if not found
                )

                logger.info(f"[EOD]   portfolio_short_name={portfolio_short_name}, quantity={quantity}, "
                           f"security_currency={security_currency}, portfolio_currency={portfolio_currency}")

                if quantity <= 0:
                    logger.info(f"[EOD]   Skipping: quantity <= 0")
                    continue

                # Calculate cash flow amount in FOREIGN currency (security currency)
                # Formula: Amount FC = Quantity × Dividend Price
                amount_fc = (quantity * price).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

                # Calculate cash flow amount in LOCAL currency (portfolio currency)
                # Formula: Amount LC = Amount FC × FX Rate
                if security_currency != portfolio_currency:
                    try:
                        fx_rate, _ = multicurrency_service.get_fx_rate(
                            security_currency, portfolio_currency, ex_date
                        )
                        amount_lc = (amount_fc * fx_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    except Exception as e:
                        logger.warning(f"FX rate lookup failed for {security_currency}->{portfolio_currency}: {e}")
                        fx_rate = Decimal('1')
                        amount_lc = amount_fc
                else:
                    fx_rate = Decimal('1')
                    amount_lc = amount_fc

                if dry_run:
                    logger.info(f"[DRY RUN] Would create {ca_type} cash flow: "
                               f"Portfolio={portfolio_short_name}, Qty={quantity}, "
                               f"Price={price}, Amount FC={amount_fc} {security_currency}, "
                               f"Amount LC={amount_lc} {portfolio_currency}, FX Rate={fx_rate}")
                    cash_flows_created += 1
                    total_amount += amount_lc  # Track in local currency
                    continue

                # Create cash flow with proper multi-currency support
                logger.info(f"[EOD]   Calling create_cash_flow_from_ca() for holding {idx + 1}")
                success, cash_flow_id, error = self.create_cash_flow_from_ca(
                    ca_id=ca_id,
                    ca_number=ca_number,
                    ca_type=ca_type,
                    portfolio_short_name=portfolio_short_name,
                    security_name=security_name,
                    quantity=quantity,
                    amount_fc=amount_fc,
                    amount_lc=amount_lc,
                    foreign_currency=security_currency,
                    local_currency=portfolio_currency,
                    fx_rate=fx_rate,
                    ex_date=ex_date,
                    record_date=record_date,
                    payment_date=payment_date,
                    created_by=queue_entry.get('created_by', 'system')
                )
                logger.info(f"[EOD]   create_cash_flow_from_ca result: success={success}, cash_flow_id={cash_flow_id}, error={error}")

                # Log the result
                log_data = {
                    'queue_id': queue_id,
                    'ca_id': ca_id,
                    'cash_flow_id': cash_flow_id,
                    'portfolio_short_name': portfolio_short_name,
                    'security_name': security_name,
                    'quantity': quantity,
                    'amount': amount_lc,  # Use local currency amount
                    'currency': portfolio_currency,  # Local currency = portfolio currency
                    'status': 'SUCCESS' if success else 'FAILED',
                    'error_message': error if not success else None
                }
                ca_cash_flow_queue_repository.insert_log(log_data)

                if success:
                    cash_flows_created += 1
                    total_amount += amount_lc  # Use local currency amount
                else:
                    errors.append(f"{portfolio_short_name}: {error}")

            # Update queue status
            if not dry_run:
                if errors:
                    error_msg = "; ".join(errors[:5])  # Limit error message length
                    if len(errors) > 5:
                        error_msg += f" (and {len(errors) - 5} more errors)"
                    ca_cash_flow_queue_repository.mark_failed(queue_id, error_msg)
                    return False, error_msg, cash_flows_created, total_amount
                else:
                    ca_cash_flow_queue_repository.mark_completed(
                        queue_id, cash_flows_created, total_amount
                    )

            msg = f"Created {cash_flows_created} cash flows, total amount: {total_amount} {currency}"
            return True, msg, cash_flows_created, total_amount

        except Exception as e:
            error_msg = f"Error processing CA cash flows: {str(e)}"
            logger.error(error_msg)
            if not dry_run:
                ca_cash_flow_queue_repository.mark_failed(queue_id, error_msg)
            return False, error_msg, 0, Decimal('0')

    def _resolve_security_labels(self, ca_security_names: List[str]) -> List[str]:
        """
        CA stores security_name = GMP description string (cis_security.security_description).
        cis_position.security_label = cis_security.security_name (the short name/code).
        This method resolves one to the other via a lookup on cis_security.

        Falls back to the original value if no match found (handles CIS-native CAs
        where security_name already equals the security_name/label directly).
        """
        if not ca_security_names:
            return []

        escaped = ", ".join(f"'{self._escape(s)}'" for s in ca_security_names)

        # Match on security_description (GMP source) OR security_name (CIS source)
        query = f"""
        SELECT security_name, security_description
        FROM {self.DATABASE}.cis_security
        WHERE security_description IN ({escaped})
           OR security_name IN ({escaped})
        """
        try:
            rows = impala_manager.execute_query(query, database=self.DATABASE) or []
        except Exception as e:
            logger.error(f"[HOLDINGS] Security label lookup failed: {e}")
            return ca_security_names  # fallback: pass through as-is

        # Build mapping: input value → security_name (position label)
        resolved = set()
        lookup = {r.get('security_description'): r.get('security_name') for r in rows if r.get('security_description')}
        lookup.update({r.get('security_name'): r.get('security_name') for r in rows if r.get('security_name')})

        for s in ca_security_names:
            mapped = lookup.get(s)
            if mapped:
                resolved.add(mapped)
            else:
                resolved.add(s)  # fallback: try as-is
                logger.warning(f"[HOLDINGS] No cis_security match for '{s}' — using as-is")

        return list(resolved)

    def get_holdings_for_ca(
        self,
        security_name: str,
        as_of_date: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get ALL portfolio holdings for a security as of a specific date.
        CA applies at security level - finds all portfolios holding the security.

        Args:
            security_name: Security name from CA (comma-separated if multiple).
                           May be security_description (GMP source) or security_name (CIS source).
            as_of_date: Date to check holdings (YYYY-MM-DD), defaults to today

        Returns:
            List of holdings with portfolio_short_name, quantity, security_label
        """
        try:
            if not as_of_date:
                as_of_date = datetime.now().strftime('%Y-%m-%d')

            # Handle multiple securities (comma-separated)
            ca_securities = [s.strip() for s in security_name.split(',') if s.strip()]
            if not ca_securities:
                return []

            # CA security_name (GMP = description, CIS = name) → cis_position.security_label
            # cis_position.security_label = cis_security.security_name
            position_labels = self._resolve_security_labels(ca_securities)
            logger.info(f"[HOLDINGS] CA security '{security_name}' resolved to position labels: {position_labels}")

            security_conditions = " OR ".join([
                f"security_label = '{self._escape(s)}'" for s in position_labels
            ])

            # Query cis_position (golden copy — all sources: CIS, GMP, AMSICEQ, USER_UPLOAD).
            # cis_position has one row per position_id (no status/is_active flags).
            # Use MAX(position_date) per portfolio+security to get the latest snapshot.
            # Only process portfolios belonging to entity_group = 'UOBS'.
            query = f"""
            SELECT
                p.portfolio              AS portfolio_short_name,
                p.security_label,
                p.quantity,
                p.average_cost_fc,
                p.average_cost_lc,
                p.cost_fc,
                p.cost_lc,
                p.market_value_fc,
                p.dividend_fc,
                p.dividend_lc,
                p.isin,
                pf.currency             AS portfolio_base_currency,
                sec.currency_code       AS security_currency
            FROM {self.DATABASE}.{self.POSITION_TABLE} p
            INNER JOIN (
                SELECT pos.portfolio, pos.security_label, MAX(pos.position_date) AS max_date
                FROM {self.DATABASE}.{self.POSITION_TABLE} pos
                INNER JOIN {self.DATABASE}.cis_portfolio pf2
                    ON pos.portfolio = pf2.name
                    AND pf2.entity_group = 'UOBS'
                WHERE ({security_conditions})
                  AND pos.position_date <= '{as_of_date}'
                GROUP BY pos.portfolio, pos.security_label
            ) latest ON p.portfolio = latest.portfolio
                    AND p.security_label = latest.security_label
                    AND p.position_date = latest.max_date
            INNER JOIN {self.DATABASE}.cis_portfolio pf
                ON p.portfolio = pf.name
                AND pf.entity_group = 'UOBS'
            LEFT JOIN {self.DATABASE}.cis_security sec ON p.security_label = sec.security_name
            WHERE p.quantity > 0
            ORDER BY p.portfolio, p.security_label
            """

            logger.info(f"[HOLDINGS] Executing holdings query:\n{query}")
            results = impala_manager.execute_query(query, database=self.DATABASE)
            logger.info(f"[HOLDINGS] Found {len(results) if results else 0} portfolios holding security {security_name} as of {as_of_date}")
            if results:
                logger.info(f"[HOLDINGS] Full results: {results}")
            return results if results else []

        except Exception as e:
            logger.error(f"Error getting holdings for CA: {str(e)}")
            return []

    def create_cash_flow_from_ca(
        self,
        ca_id: int,
        ca_number: str,
        ca_type: str,
        portfolio_short_name: str,
        security_name: str,
        quantity: Decimal,
        amount_fc: Decimal,
        amount_lc: Decimal,
        foreign_currency: str,
        local_currency: str,
        fx_rate: Decimal,
        ex_date: str,
        record_date: str,
        payment_date: str,
        created_by: str
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Create a cash flow entry from a corporate action with multi-currency support.

        Based on SA/BA specification:
        - Foreign Currency = Security Currency (e.g., USD)
        - Amount FC = Quantity × Dividend Price (e.g., 18 × $0.35 = $6.30)
        - Local Currency = Portfolio Currency (e.g., SGD)
        - Amount LC = Amount FC × FX Rate (e.g., $6.30 × 1.28964 = $8.12)

        Args:
            ca_id: Corporate Action ID
            ca_number: CA number
            ca_type: CA type (DIVIDEND, INTEREST, etc.)
            portfolio_short_name: Portfolio short name
            security_name: Security name
            quantity: Quantity held
            amount_fc: Amount in Foreign Currency (security currency)
            amount_lc: Amount in Local Currency (portfolio currency)
            foreign_currency: Security currency code (e.g., USD)
            local_currency: Portfolio currency code (e.g., SGD)
            fx_rate: FX rate used for conversion
            ex_date: Ex-dividend date
            record_date: Record date
            payment_date: Payment date
            created_by: User creating the cash flow

        Returns:
            Tuple of (success, cash_flow_id, error_message)
        """
        try:
            logger.info(f"[CREATE_CF] === create_cash_flow_from_ca called ===")
            logger.info(f"[CREATE_CF] ca_number={ca_number}, portfolio={portfolio_short_name}, "
                       f"security={security_name}, ex_date={ex_date}")

            # Check for duplicate - prevent creating multiple cash flows for same CA + portfolio + security
            logger.info(f"[CREATE_CF] Checking for existing cash flow...")
            existing = self._check_existing_cash_flow(ca_number, portfolio_short_name, security_name, ex_date)
            if existing:
                logger.info(f"[CREATE_CF] DUPLICATE DETECTED! Cash flow already exists: "
                           f"cash_flow_id={existing.get('cash_flow_id')}, cf_number={existing.get('cash_flow_number')}")
                return True, existing.get('cash_flow_id'), "Cash flow already exists (skipped)"
            logger.info(f"[CREATE_CF] No existing cash flow found, proceeding to create...")

            # Generate CF number
            timestamp = datetime.now()
            cf_number = f"CF-{timestamp.strftime('%Y%m%d')}-{int(timestamp.timestamp() * 1000) % 100000:05d}"
            logger.info(f"[CREATE_CF] Generated cf_number={cf_number}")

            # Map CA type to cash flow type
            cf_type = self.CA_TO_CF_TYPE_MAP.get(ca_type, ca_type)

            # send_receive drives cost-basis direction in process_approved_cashflows
            # (_reduce_avp): INCREASE -> cost increases, DECREASE -> cost decreases.
            # ROC/CAPITAL_DISTRIBUTION are a return of capital -- cash received
            # reduces the cost basis -- so they default to DECREASE. Everything
            # else (dividends, interest, coupons, income distribution) doesn't
            # touch cost at all (it accumulates a separate running-total field),
            # so it keeps the original INCREASE default.
            default_send_receive = (
                'DECREASE' if ca_type in self.AVP_REDUCTION_CA_TYPES else 'INCREASE'
            )

            # Map to actual cis_cash_flow table field names
            # Following SA/BA specification for multi-currency cash flows
            # CA-generated cash flows are auto-validated (no four-eyes needed)
            cf_data = {
                'cash_flow_number': cf_number,
                'portfolio_short_name': portfolio_short_name,
                'security_label': security_name,
                'cash_flow_type': cf_type,
                'send_receive': default_send_receive,
                'cf_processed': False,
                'value_date': ex_date,
                'payment_date': payment_date,
                'dividend_date': record_date,
                'ex_date': ex_date,
                'record_date': record_date,
                # Foreign Currency (Security Currency) - e.g., USD
                'foreign_ccy': foreign_currency,
                'foreign_ccy_amt': float(amount_fc),
                # Local Currency (Portfolio Currency) - e.g., SGD
                'local_ccy': local_currency,
                'local_ccy_amt': float(amount_lc),
                'flow_amount_local': float(amount_lc),
                # Dividend price per share (Amount FC / Quantity)
                'dividend_price': float(amount_fc / quantity) if quantity else 0,
                'quantity': float(quantity),    # Quantity held at ex-date
                'fx_rate': float(fx_rate.quantize(Decimal('0.0000001'), rounding=ROUND_HALF_UP)),  # 7dp — max GMP precision
                # CA-generated cash flows skip four-eyes and are auto-validated
                'status': 'VALIDATED',
                'src_system': 'CA',  # Mark as CA-generated (not manual CIS entry)
                # CA reference for audit trail
                'ca_id': ca_id,
                'ca_number': ca_number,
            }

            logger.info(f"[CREATE_CF] Creating cash flow: {cf_number}, Portfolio={portfolio_short_name}, "
                       f"Security={security_name}, Qty={quantity}, "
                       f"Amount FC={amount_fc} {foreign_currency}, "
                       f"Amount LC={amount_lc} {local_currency}, FX={fx_rate}")
            logger.info(f"[CREATE_CF] cf_data = {cf_data}")

            # Use cash flow repository to insert
            logger.info(f"[CREATE_CF] Calling CashFlowRepository.insert()...")
            success, cash_flow_id = CashFlowRepository.insert(cf_data, created_by)
            logger.info(f"[CREATE_CF] CashFlowRepository.insert() returned: success={success}, cash_flow_id={cash_flow_id}")

            if success:
                logger.info(f"[CREATE_CF] SUCCESS - Created cash flow {cf_number} (id={cash_flow_id}) "
                           f"from CA {ca_number} for portfolio {portfolio_short_name}")

                # Update position table with CA/cash flow details
                # Pass both FC and LC amounts along with currencies and FX rate
                self._update_position_with_ca_details(
                    portfolio_short_name=portfolio_short_name,
                    security_name=security_name,
                    ca_id=ca_id,
                    ca_number=ca_number,
                    ca_type=ca_type,
                    ex_date=ex_date,
                    cash_flow_id=cash_flow_id,
                    cash_flow_number=cf_number,
                    cash_flow_amount_fc=amount_fc,
                    cash_flow_amount_lc=amount_lc,
                    security_currency=foreign_currency,
                    portfolio_currency=local_currency,
                    fx_rate=fx_rate,
                    updated_by=created_by
                )

                return True, cash_flow_id, None
            else:
                logger.error(f"[CREATE_CF] FAILED - Failed to insert cash flow for {portfolio_short_name}")
                return False, None, "Failed to insert cash flow"

        except Exception as e:
            error_msg = f"Error creating cash flow from CA: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg

    def _update_position_with_ca_details(
        self,
        portfolio_short_name: str,
        security_name: str,
        ca_id: int,
        ca_number: str,
        ca_type: str,
        ex_date: str,
        cash_flow_id: int,
        cash_flow_number: str,
        cash_flow_amount_fc: Decimal,
        cash_flow_amount_lc: Decimal,
        security_currency: str,
        portfolio_currency: str,
        fx_rate: Decimal,
        updated_by: str
    ) -> bool:
        """
        Update existing INT rows in cis_position for a CA cash flow event.

        SA rule: All CA types update the existing INT records in place — no new
        position type. Both TRADE_DATE and SETTLE_DATE basis rows are updated
        if they exist. position_type stays INT throughout.

        AVP rules per CA type:
        - DIVIDEND / SPECIAL_DIVIDEND / INTEREST / COUPON: AVP unchanged; accumulate dividend_fc/lc
        - ROC / CAPITAL_DISTRIBUTION: AVP reduced by cash_flow_amount / qty
        - INCOME_DISTRIBUTION: AVP unchanged; accumulate realized_pnl_fc/lc
        - Default: AVP unchanged, no accumulation
        """
        try:
            logger.info(
                f"[UPDATE_POS] Updating INT positions for CA: portfolio={portfolio_short_name}, "
                f"security={security_name}, ca_number={ca_number}, ca_type={ca_type}, "
                f"amount_fc={cash_flow_amount_fc}, amount_lc={cash_flow_amount_lc}"
            )

            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            updated_any = False

            # cis_position stores position_basis as 'TRADED' / 'SETTLED'
            for cp_basis in ('TRADED', 'SETTLED'):
                # Find the existing CIS INT row for this basis — INT only, never EOD/SOD/CORR
                find_q = f"""
                SELECT position_id, version_id,
                       quantity,
                       average_cost_fc, cost_fc AS total_cost_fc,
                       average_cost_lc, cost_lc AS total_cost_lc,
                       market_value_fc, market_value_lc,
                       unrealized_pnl_fc, unrealized_pnl_lc,
                       realized_pnl_fc, realized_pnl_lc,
                       dividend_fc, dividend_lc,
                       uncall_fc, uncall_lc,
                       pipeline_fc, pipeline_lc,
                       provision_fc, provision_lc,
                       isin, src_system, source_table, position_date
                FROM {self.DATABASE}.{self.POSITION_TABLE}
                WHERE portfolio = '{self._escape(portfolio_short_name)}'
                  AND security_label = '{self._escape(security_name)}'
                  AND src_system = 'CIS'
                  AND position_type = 'INT'
                  AND position_basis = '{cp_basis}'
                  AND quantity > 0
                ORDER BY position_date DESC, version_id DESC
                LIMIT 1
                """
                rows = impala_manager.execute_query(find_q, database=self.DATABASE)
                if not rows:
                    logger.info(
                        f"[UPDATE_POS] No CIS {cp_basis} INT row found for "
                        f"{portfolio_short_name}/{security_name} — skipping basis"
                    )
                    continue

                row = rows[0]
                position_id   = row.get('position_id')
                position_date = row.get('position_date') or ex_date
                quantity      = Decimal(str(row.get('quantity') or 0))

                old_avg_cost_fc   = Decimal(str(row.get('average_cost_fc') or 0))
                old_total_cost_fc = Decimal(str(row.get('total_cost_fc') or 0))
                old_avg_cost_lc   = Decimal(str(row.get('average_cost_lc') or 0))
                old_total_cost_lc = Decimal(str(row.get('total_cost_lc') or 0))
                market_value_fc   = Decimal(str(row.get('market_value_fc') or 0))
                market_value_lc   = Decimal(str(row.get('market_value_lc') or 0))
                old_dividend_fc   = Decimal(str(row.get('dividend_fc') or 0))
                old_dividend_lc   = Decimal(str(row.get('dividend_lc') or 0))
                realized_pnl_fc   = Decimal(str(row.get('realized_pnl_fc') or 0))
                realized_pnl_lc   = Decimal(str(row.get('realized_pnl_lc') or 0))
                uncall_fc    = Decimal(str(row.get('uncall_fc') or 0))
                uncall_lc    = Decimal(str(row.get('uncall_lc') or 0))
                pipeline_fc  = Decimal(str(row.get('pipeline_fc') or 0))
                pipeline_lc  = Decimal(str(row.get('pipeline_lc') or 0))
                provision_fc = Decimal(str(row.get('provision_fc') or 0))
                provision_lc = Decimal(str(row.get('provision_lc') or 0))
                isin         = row.get('isin')
                source_table = row.get('source_table')

                logger.info(
                    f"[UPDATE_POS] {cp_basis}: qty={quantity}, avg_cost_fc={old_avg_cost_fc}, "
                    f"dividend_fc={old_dividend_fc}"
                )

                # --- AVP calculation ---
                if ca_type in self.NO_AVP_CHANGE_CA_TYPES:
                    new_avg_cost_fc   = old_avg_cost_fc
                    new_total_cost_fc = old_total_cost_fc
                    new_avg_cost_lc   = old_avg_cost_lc
                    new_total_cost_lc = old_total_cost_lc
                elif ca_type in self.AVP_REDUCTION_CA_TYPES:
                    pps_fc = (cash_flow_amount_fc / quantity).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP) if quantity > 0 else Decimal('0')
                    pps_lc = (cash_flow_amount_lc / quantity).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP) if quantity > 0 else Decimal('0')
                    new_avg_cost_fc   = max(Decimal('0'), (old_avg_cost_fc - pps_fc).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP))
                    new_avg_cost_lc   = max(Decimal('0'), (old_avg_cost_lc - pps_lc).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP))
                    new_total_cost_fc = (new_avg_cost_fc * quantity).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                    new_total_cost_lc = (new_avg_cost_lc * quantity).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                    logger.info(f"[UPDATE_POS] {cp_basis} AVP reduction: {old_avg_cost_fc} -> {new_avg_cost_fc}")
                else:
                    new_avg_cost_fc   = old_avg_cost_fc
                    new_total_cost_fc = old_total_cost_fc
                    new_avg_cost_lc   = old_avg_cost_lc
                    new_total_cost_lc = old_total_cost_lc

                # --- Accumulation ---
                if ca_type in ['CASH_DIVIDEND', 'DIVIDEND', 'SPECIAL_DIVIDEND', 'INTEREST', 'COUPON']:
                    new_dividend_fc     = (old_dividend_fc + cash_flow_amount_fc).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                    new_dividend_lc     = (old_dividend_lc + cash_flow_amount_lc).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                    new_realized_pnl_fc = realized_pnl_fc
                    new_realized_pnl_lc = realized_pnl_lc
                elif ca_type == 'INCOME_DISTRIBUTION':
                    new_dividend_fc     = old_dividend_fc
                    new_dividend_lc     = old_dividend_lc
                    new_realized_pnl_fc = (realized_pnl_fc + cash_flow_amount_fc).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                    new_realized_pnl_lc = (realized_pnl_lc + cash_flow_amount_lc).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                else:
                    new_dividend_fc     = old_dividend_fc
                    new_dividend_lc     = old_dividend_lc
                    new_realized_pnl_fc = realized_pnl_fc
                    new_realized_pnl_lc = realized_pnl_lc

                new_unrealized_pnl_fc = (market_value_fc - new_total_cost_fc).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                new_unrealized_pnl_lc = (market_value_lc - new_total_cost_lc).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

                # UPSERT on existing position_id — keeps position_type=INT
                new_version_id = int(datetime.now().timestamp() * 1000)
                upsert_sql = f"""
                UPSERT INTO {self.DATABASE}.{self.POSITION_TABLE} (
                    position_id, version_id,
                    portfolio, security_label,
                    position_basis, position_date,
                    src_system, processing_date,
                    position_type,
                    quantity,
                    average_cost_fc, cost_fc,
                    average_cost_lc, cost_lc,
                    market_value_fc, market_value_lc,
                    net_book_value_fc, net_book_value_lc,
                    unrealized_pnl_fc, unrealized_pnl_lc,
                    realized_pnl_fc, realized_pnl_lc,
                    dividend_fc, dividend_lc,
                    uncall_fc, uncall_lc,
                    pipeline_fc, pipeline_lc,
                    provision_fc, provision_lc,
                    isin, source_table
                ) VALUES (
                    {position_id}, {new_version_id},
                    '{self._escape(portfolio_short_name)}',
                    '{self._escape(security_name)}',
                    '{cp_basis}',
                    '{self._escape(str(position_date))}',
                    'CIS',
                    '{timestamp_str}',
                    'INT',
                    {float(quantity)},
                    {float(new_avg_cost_fc)},   {float(new_total_cost_fc)},
                    {float(new_avg_cost_lc)},   {float(new_total_cost_lc)},
                    {float(market_value_fc)},   {float(market_value_lc)},
                    {float(market_value_fc)},   {float(market_value_lc)},
                    {float(new_unrealized_pnl_fc)}, {float(new_unrealized_pnl_lc)},
                    {float(new_realized_pnl_fc)},   {float(new_realized_pnl_lc)},
                    {float(new_dividend_fc)},   {float(new_dividend_lc)},
                    {float(uncall_fc)},         {float(uncall_lc)},
                    {float(pipeline_fc)},       {float(pipeline_lc)},
                    {float(provision_fc)},      {float(provision_lc)},
                    {f"'{self._escape(isin)}'" if isin else 'NULL'},
                    {f"'{self._escape(source_table)}'" if source_table else 'NULL'}
                )
                """
                ok = impala_manager.execute_write(upsert_sql, database=self.DATABASE)
                if ok:
                    logger.info(
                        f"[UPDATE_POS] Updated {cp_basis} INT row: position_id={position_id} "
                        f"avg_cost_fc={new_avg_cost_fc} dividend_fc={new_dividend_fc} ca_type={ca_type}"
                    )
                    updated_any = True
                else:
                    logger.error(
                        f"[UPDATE_POS] Failed to update {cp_basis} INT row for "
                        f"{portfolio_short_name}/{security_name}"
                    )

            return updated_any

        except Exception as e:
            logger.error(f"[UPDATE_POS] Error updating position with CA details: {str(e)}")
            return False

    def _get_current_position(
        self,
        portfolio_short_name: str,
        security_name: str,
        position_basis: str = 'SETTLED'
    ) -> Optional[Dict[str, Any]]:
        """Get the current open CIS position for a portfolio/security combination.

        Primary:  cis_trade_position (versioned CIS ledger)
        Fallback: cis_position WHERE src_system='CIS' — covers cases where the
                  position exists in the golden copy but not yet in cis_trade_position
                  (e.g. positions created via a bulk tool before the CA runs).

        Args:
            position_basis: 'SETTLED' (default) or 'TRADED'
        """
        try:
            # --- Primary: cis_trade_position ---
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.WRITE_POSITION_TABLE}
            WHERE portfolio_short_name = '{self._escape(portfolio_short_name)}'
              AND security_label = '{self._escape(security_name)}'
              AND position_basis = '{position_basis}'
              AND status = 'OPEN'
              AND is_active = true
              AND (is_latest = true OR is_latest IS NULL)
            ORDER BY position_date DESC, version_id DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                return results[0]

            # --- Fallback: cis_position WHERE src_system='CIS' ---
            logger.info(
                f"[UPDATE_POS] cis_trade_position miss for {portfolio_short_name}/{security_name} "
                f"basis={position_basis} — checking cis_position (src_system=CIS)"
            )
            cp_basis = 'SETTLE_DATE' if position_basis == 'SETTLED' else 'TRADE_DATE'
            fallback_query = f"""
            SELECT
                position_id,
                version_id,
                portfolio        AS portfolio_short_name,
                security_label,
                position_basis,
                position_date,
                src_system,
                quantity,
                average_cost_fc,
                average_cost_lc,
                cost_fc          AS total_cost_fc,
                cost_lc          AS total_cost_lc,
                market_value_fc,
                market_value_lc,
                unrealized_pnl_fc,
                unrealized_pnl_lc,
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
                isin
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE portfolio = '{self._escape(portfolio_short_name)}'
              AND security_label = '{self._escape(security_name)}'
              AND src_system = 'CIS'
              AND position_basis = '{cp_basis}'
              AND quantity > 0
            ORDER BY position_date DESC, version_id DESC
            LIMIT 1
            """
            fallback = impala_manager.execute_query(fallback_query, database=self.DATABASE)
            if fallback:
                row = fallback[0]
                qty = float(row.get('quantity') or 0)
                mv_fc = float(row.get('market_value_fc') or 0)
                row['market_price'] = mv_fc / qty if qty else 0
                row['status'] = 'OPEN'
                row['is_latest'] = True
                logger.info(
                    f"[UPDATE_POS] Fallback hit: found CIS position in cis_position for "
                    f"{portfolio_short_name}/{security_name}"
                )
                return row

            logger.warning(
                f"[UPDATE_POS] No open CIS position found for {portfolio_short_name}/{security_name} "
                f"basis={position_basis} in cis_trade_position or cis_position"
            )
            return None
        except Exception as e:
            logger.error(f"[UPDATE_POS] Error getting current position ({position_basis}): {str(e)}")
            return None

    def _mark_old_version_not_latest(self, version_id: int) -> bool:
        """Mark an existing position version as not latest."""
        try:
            update_sql = f"""
            UPDATE {self.DATABASE}.{self.WRITE_POSITION_TABLE}
            SET is_latest = false,
                updated_at = '{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}'
            WHERE version_id = {version_id}
            """
            return impala_manager.execute_write(update_sql, database=self.DATABASE)
        except Exception as e:
            logger.error(f"[UPDATE_POS] Error marking version {version_id} as not latest: {str(e)}")
            return False

    def _process_position_adjustment_ca(
        self,
        queue_id: int,
        queue_entry: Dict[str, Any],
        dry_run: bool = False,
        run_type: str = 'EOD'
    ) -> Tuple[bool, str, int, Decimal]:
        """
        Process position adjustment CA types (no cash flow generated).

        Based on SA Specification:
        - BONUS_ISSUE: qty_new = qty_old × (1 + ratio), AVP = total_cost / new_qty
        - SPLIT: qty_new = qty_old × ratio, AVP = AVP_old / ratio
        - RIGHTS_ENTITLEMENT: Creates new position for the rights security
        - WARRANT_ENTITLEMENT: Creates new position for the warrant security

        Args:
            queue_id: Queue entry ID
            queue_entry: Queue entry data
            dry_run: If True, don't actually process

        Returns:
            Tuple of (success, message, positions_adjusted, amount=0)
        """
        try:
            ca_type = (queue_entry.get('ca_type') or '').strip().upper()
            security_name = queue_entry.get('security_name')
            ex_date = queue_entry.get('ex_date')
            raw_price = queue_entry.get('price')
            if raw_price is None or str(raw_price).strip() in ('', 'None', '0'):
                msg = (f"CA {queue_entry.get('ca_number')} ({ca_type}): price/ratio is NULL or zero in queue. "
                       f"Edit the CA record and set the correct ratio before reprocessing.")
                logger.error(f"[POS_ADJ] {msg}")
                return False, msg, 0, Decimal('0')
            price = Decimal(str(raw_price))  # ratio for BONUS/SPLIT/REVERSE_SPLIT
            ca_id = queue_entry.get('ca_id')
            ca_number = queue_entry.get('ca_number')
            created_by = queue_entry.get('created_by', 'system')

            logger.info(f"[POS_ADJ] Processing {ca_type} CA: {ca_number}, security={security_name}, "
                       f"ex_date={ex_date}, ratio/price={price}")

            # Get all holdings for this security
            holdings = self.get_holdings_for_ca(
                security_name=security_name,
                as_of_date=ex_date
            )

            if not holdings:
                msg = f"No holdings found for security {security_name} as of {ex_date}"
                logger.info(msg)
                if not dry_run:
                    ca_cash_flow_queue_repository.mark_completed(queue_id, 0, Decimal('0'))
                return True, msg, 0, Decimal('0')

            positions_adjusted = 0
            errors = []

            for holding in holdings:
                portfolio_short_name = holding.get('portfolio_short_name')
                quantity = Decimal(str(holding.get('quantity') or 0))
                # Use new FC column name
                avg_cost = Decimal(str(holding.get('average_cost_fc') or 0))
                security_currency = holding.get('security_currency')
                portfolio_currency = holding.get('portfolio_currency') or holding.get('portfolio_base_currency')

                if quantity <= 0:
                    continue

                try:
                    if ca_type == 'BONUS_ISSUE':
                        # qty_new = qty_old × (1 + ratio), AVP = total_cost / new_qty
                        success = self._process_bonus_issue(
                            portfolio_short_name=portfolio_short_name,
                            security_name=security_name,
                            old_quantity=quantity,
                            old_avg_cost=avg_cost,
                            ratio=price,  # price field stores the bonus ratio
                            ca_id=ca_id,
                            ca_number=ca_number,
                            ex_date=ex_date,
                            security_currency=security_currency,
                            portfolio_currency=portfolio_currency,
                            updated_by=created_by,
                            dry_run=dry_run,
                            run_type=run_type
                        )
                    elif ca_type in ['SPLIT', 'STOCK_SPLIT']:
                        # Price field stores the split ratio directly.
                        # e.g. price=2 means 1 share → 2 shares (2:1 forward split)
                        # qty_new = qty_old × ratio, AVP = AVP_old / ratio
                        split_ratio = price if price > 0 else Decimal('1')
                        logger.info(f"[STOCK_SPLIT] Price={price}, ratio={split_ratio}")
                        success = self._process_stock_split(
                            portfolio_short_name=portfolio_short_name,
                            security_name=security_name,
                            old_quantity=quantity,
                            old_avg_cost=avg_cost,
                            ratio=split_ratio,  # e.g., 3 for 1:3 split
                            ca_id=ca_id,
                            ca_number=ca_number,
                            ex_date=ex_date,
                            security_currency=security_currency,
                            portfolio_currency=portfolio_currency,
                            updated_by=created_by,
                            dry_run=dry_run,
                            run_type=run_type
                        )
                    elif ca_type == 'REVERSE_SPLIT':
                        # Reverse Split: 3:1 means 3 shares become 1 share
                        # Price field stores the ratio directly (e.g., 3.00 for 3:1 reverse split)
                        # qty_new = qty_old / ratio, AVP = AVP_old × ratio
                        reverse_ratio = price  # e.g., 3 for 3:1 reverse split
                        logger.info(f"[REVERSE_SPLIT] Price={price}, ratio={reverse_ratio}")
                        success = self._process_reverse_split(
                            portfolio_short_name=portfolio_short_name,
                            security_name=security_name,
                            old_quantity=quantity,
                            old_avg_cost=avg_cost,
                            ratio=reverse_ratio,  # e.g., 3 for 3:1 reverse split
                            ca_id=ca_id,
                            ca_number=ca_number,
                            ex_date=ex_date,
                            security_currency=security_currency,
                            portfolio_currency=portfolio_currency,
                            updated_by=created_by,
                            dry_run=dry_run,
                            run_type=run_type
                        )
                    elif ca_type == 'CONSOLIDATION':
                        # Consolidation is same as reverse split
                        reverse_ratio = price
                        success = self._process_reverse_split(
                            portfolio_short_name=portfolio_short_name,
                            security_name=security_name,
                            old_quantity=quantity,
                            old_avg_cost=avg_cost,
                            ratio=reverse_ratio,
                            ca_id=ca_id,
                            ca_number=ca_number,
                            ex_date=ex_date,
                            security_currency=security_currency,
                            portfolio_currency=portfolio_currency,
                            updated_by=created_by,
                            dry_run=dry_run,
                            run_type=run_type
                        )
                    elif ca_type in ['RIGHTS_ENTITLEMENT', 'RIGHTS_ISSUE', 'RIGHTS', 'WARRANT_ENTITLEMENT', 'WARRANTS']:
                        # Creates a new position for the rights/warrant security.
                        # Entitlement qty = old_qty * ratio (price field).
                        # New security label = original security + suffix (e.g. " RIGHTS" / " WRNTS").
                        # AVP of new position = 0 (rights/warrants are issued at no cost to holder).
                        suffix = ' RIGHTS' if ca_type in ['RIGHTS_ENTITLEMENT', 'RIGHTS_ISSUE', 'RIGHTS'] else ' WRNTS'
                        new_security_name = security_name.rstrip() + suffix
                        entitlement_qty = (quantity * price).quantize(
                            Decimal('0.00000001'), rounding=ROUND_HALF_UP
                        )
                        logger.info(f"[POS_ADJ] {ca_type}: Creating new position for {new_security_name}, "
                                   f"qty={entitlement_qty}, AVP=0 (no cost to holder)")
                        if not dry_run:
                            success = self._create_rights_warrant_position(
                                portfolio_short_name=portfolio_short_name,
                                new_security_name=new_security_name,
                                entitlement_qty=entitlement_qty,
                                ca_id=ca_id,
                                ca_number=ca_number,
                                ca_type=ca_type,
                                ex_date=ex_date,
                                security_currency=security_currency,
                                portfolio_currency=portfolio_currency,
                                created_by=created_by
                            )
                        else:
                            success = True
                    else:
                        logger.warning(f"[POS_ADJ] Unknown position adjustment CA type: {ca_type}")
                        success = False

                    if success:
                        positions_adjusted += 1
                    else:
                        errors.append(f"{portfolio_short_name}: Failed to process {ca_type}")

                except Exception as e:
                    errors.append(f"{portfolio_short_name}: {str(e)}")
                    logger.error(f"[POS_ADJ] Error processing {ca_type} for {portfolio_short_name}: {str(e)}")

            # Update queue status
            if not dry_run:
                if errors:
                    error_msg = "; ".join(errors[:5])
                    ca_cash_flow_queue_repository.mark_failed(queue_id, error_msg)
                    return False, error_msg, positions_adjusted, Decimal('0')
                else:
                    ca_cash_flow_queue_repository.mark_completed(queue_id, positions_adjusted, Decimal('0'))

            msg = f"Adjusted {positions_adjusted} positions for {ca_type} CA"
            return True, msg, positions_adjusted, Decimal('0')

        except Exception as e:
            error_msg = f"Error processing position adjustment CA: {str(e)}"
            logger.error(error_msg)
            if not dry_run:
                ca_cash_flow_queue_repository.mark_failed(queue_id, error_msg)
            return False, error_msg, 0, Decimal('0')

    def _process_bonus_issue(
        self,
        portfolio_short_name: str,
        security_name: str,
        old_quantity: Decimal,
        old_avg_cost: Decimal,
        ratio: Decimal,
        ca_id: int,
        ca_number: str,
        ex_date: str,
        security_currency: str,
        portfolio_currency: str,
        updated_by: str,
        dry_run: bool = False,
        run_type: str = 'EOD'
    ) -> bool:
        """
        Process BONUS_ISSUE: qty_new = qty_old × (1 + ratio), AVP = total_cost / new_qty

        Example: 1:10 bonus (ratio=0.1) with 100 shares @ $10
        - New qty = 100 × (1 + 0.1) = 110 shares
        - Total cost stays same = $1000
        - New AVP = $1000 / 110 = $9.09
        """
        try:
            # Calculate new quantity and AVP
            new_quantity = (old_quantity * (Decimal('1') + ratio)).quantize(
                Decimal('0.00000001'), rounding=ROUND_HALF_UP
            )
            old_total_cost = old_quantity * old_avg_cost
            new_avg_cost = (old_total_cost / new_quantity).quantize(
                Decimal('0.00000001'), rounding=ROUND_HALF_UP
            ) if new_quantity > 0 else Decimal('0')

            logger.info(f"[BONUS] Portfolio={portfolio_short_name}, Security={security_name}")
            logger.info(f"[BONUS] Old: qty={old_quantity}, avg_cost={old_avg_cost}, total={old_total_cost}")
            logger.info(f"[BONUS] New: qty={new_quantity}, avg_cost={new_avg_cost} (ratio={ratio})")

            if dry_run:
                return True

            # Create new position version
            return self._create_position_adjustment_version(
                portfolio_short_name=portfolio_short_name,
                security_name=security_name,
                new_quantity=new_quantity,
                new_avg_cost=new_avg_cost,
                new_total_cost=old_total_cost,  # Total cost unchanged for bonus
                ca_id=ca_id,
                ca_number=ca_number,
                ca_type='BONUS_ISSUE',
                ex_date=ex_date,
                security_currency=security_currency,
                portfolio_currency=portfolio_currency,
                updated_by=updated_by,
                run_type=run_type
            )

        except Exception as e:
            logger.error(f"[BONUS] Error processing bonus issue: {str(e)}")
            return False

    def _process_stock_split(
        self,
        portfolio_short_name: str,
        security_name: str,
        old_quantity: Decimal,
        old_avg_cost: Decimal,
        ratio: Decimal,
        ca_id: int,
        ca_number: str,
        ex_date: str,
        security_currency: str,
        portfolio_currency: str,
        updated_by: str,
        dry_run: bool = False,
        run_type: str = 'EOD'
    ) -> bool:
        """
        Process STOCK SPLIT (Forward Split): qty_new = qty_old × ratio, AVP = AVP_old / ratio

        Price field = ratio (e.g. price=2 means 1 share becomes 2 shares).
        Example: 2:1 split (ratio=2) with 88 shares @ $49.67
        - New qty = 88 × 2 = 176 shares
        - New AVP = $49.67 / 2 = $24.835
        - Total cost stays same = $4,370.96
        """
        try:
            # Calculate new quantity and AVP
            new_quantity = (old_quantity * ratio).quantize(
                Decimal('0.00000001'), rounding=ROUND_HALF_UP
            )
            new_avg_cost = (old_avg_cost / ratio).quantize(
                Decimal('0.00000001'), rounding=ROUND_HALF_UP
            ) if ratio > 0 else Decimal('0')
            old_total_cost = old_quantity * old_avg_cost

            logger.info(f"[STOCK_SPLIT] Portfolio={portfolio_short_name}, Security={security_name}")
            logger.info(f"[STOCK_SPLIT] Old: qty={old_quantity}, avg_cost={old_avg_cost}, total={old_total_cost}")
            logger.info(f"[STOCK_SPLIT] New: qty={new_quantity}, avg_cost={new_avg_cost} (ratio={ratio})")

            if dry_run:
                return True

            # Create new position version with STOCK_SPLIT type
            return self._create_position_adjustment_version(
                portfolio_short_name=portfolio_short_name,
                security_name=security_name,
                new_quantity=new_quantity,
                new_avg_cost=new_avg_cost,
                new_total_cost=old_total_cost,  # Total cost unchanged for split
                ca_id=ca_id,
                ca_number=ca_number,
                ca_type='STOCK_SPLIT',  # Distinct type name
                ex_date=ex_date,
                security_currency=security_currency,
                portfolio_currency=portfolio_currency,
                updated_by=updated_by,
                run_type=run_type
            )

        except Exception as e:
            logger.error(f"[STOCK_SPLIT] Error processing stock split: {str(e)}")
            return False

    def _process_reverse_split(
        self,
        portfolio_short_name: str,
        security_name: str,
        old_quantity: Decimal,
        old_avg_cost: Decimal,
        ratio: Decimal,
        ca_id: int,
        ca_number: str,
        ex_date: str,
        security_currency: str,
        portfolio_currency: str,
        updated_by: str,
        dry_run: bool = False,
        run_type: str = 'EOD'
    ) -> bool:
        """
        Process REVERSE SPLIT: qty_new = qty_old / ratio, AVP = AVP_old × ratio

        Example: 3:1 reverse split (ratio=3) with 88 shares @ $49.67
        - New qty = 88 / 3 = 29.33 shares
        - New AVP = $49.67 × 3 = $149.01
        - Total cost stays same = $4,370.96
        """
        try:
            # Calculate new quantity and AVP
            new_quantity = (old_quantity / ratio).quantize(
                Decimal('0.00000001'), rounding=ROUND_HALF_UP
            ) if ratio > 0 else old_quantity
            new_avg_cost = (old_avg_cost * ratio).quantize(
                Decimal('0.00000001'), rounding=ROUND_HALF_UP
            )
            old_total_cost = old_quantity * old_avg_cost

            logger.info(f"[REVERSE_SPLIT] Portfolio={portfolio_short_name}, Security={security_name}")
            logger.info(f"[REVERSE_SPLIT] Old: qty={old_quantity}, avg_cost={old_avg_cost}, total={old_total_cost}")
            logger.info(f"[REVERSE_SPLIT] New: qty={new_quantity}, avg_cost={new_avg_cost} (ratio={ratio})")

            if dry_run:
                return True

            # Create new position version with REVERSE_SPLIT type
            return self._create_position_adjustment_version(
                portfolio_short_name=portfolio_short_name,
                security_name=security_name,
                new_quantity=new_quantity,
                new_avg_cost=new_avg_cost,
                new_total_cost=old_total_cost,  # Total cost unchanged for reverse split
                ca_id=ca_id,
                ca_number=ca_number,
                ca_type='REVERSE_SPLIT',  # Distinct type name
                ex_date=ex_date,
                security_currency=security_currency,
                portfolio_currency=portfolio_currency,
                updated_by=updated_by,
                run_type=run_type
            )

        except Exception as e:
            logger.error(f"[REVERSE_SPLIT] Error processing reverse split: {str(e)}")
            return False

    def _create_position_adjustment_version(
        self,
        portfolio_short_name: str,
        security_name: str,
        new_quantity: Decimal,
        new_avg_cost: Decimal,
        new_total_cost: Decimal,
        ca_id: int,
        ca_number: str,
        ca_type: str,
        ex_date: str,
        security_currency: str,
        portfolio_currency: str,
        updated_by: str,
        run_type: str = 'EOD'
    ) -> bool:
        """Write the post-CA position into the INT row dated at ex_date.

        Rule: STOCK_SPLIT / BONUS_ISSUE / REVERSE_SPLIT never generate a new
        position_type — the result always lands in an INT row. But the row
        used as the CALCULATION BASIS and the row that gets WRITTEN are not
        necessarily the same record:

          - Basis: the latest position as-of ex_date. For a normal EOD run
            that's the latest of SOD/INT; for a CORR (catch-up) run it can
            also be an EOD row, since by the time a backdated CA is caught
            up, later EOD snapshots may already exist.
          - Target: the INT row dated exactly at ex_date. Since position_id
            is a deterministic hash of (portfolio, security_label,
            position_basis, position_date, src_system), we can compute the
            target id directly instead of doing a second lookup — if an INT
            row already exists for that exact date, the UPSERT lands on it;
            if not, the UPSERT creates it. This avoids clobbering a
            historical INT row that predates ex_date (the old bug: the
            basis row's own position_id/position_date was reused as the
            write target, silently overwriting history).
        """
        try:
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Get FX rate for LC calculations
            fx_rate = Decimal('1')
            if security_currency and portfolio_currency and security_currency != portfolio_currency:
                try:
                    fx_rate, _ = multicurrency_service.get_fx_rate(
                        security_currency, portfolio_currency, ex_date
                    )
                except Exception:
                    fx_rate = Decimal('1')

            # Get portfolio revaluation status for LC cost treatment
            try:
                _rv_rows = impala_manager.execute_query(
                    f"SELECT revaluation_status FROM {self.DATABASE}.cis_portfolio "
                    f"WHERE name = '{self._escape(portfolio_short_name)}' LIMIT 1",
                    database=self.DATABASE
                )
                reval_status = (
                    (_rv_rows[0].get('revaluation_status') or '').upper()
                    if _rv_rows else ''
                )
                if reval_status not in ('REVALUED', 'NON-REVALUED'):
                    reval_status = 'REVALUED'
            except Exception:
                reval_status = 'REVALUED'

            updated_any = False

            # Basis for calculation: normal runs use the latest of SOD/INT as of
            # ex_date; a CORR (catch-up) run may also need to look at EOD, since
            # later EOD snapshots can already exist by the time a backdated CA
            # is processed.
            basis_position_types = ['SOD', 'INT']
            if (run_type or '').strip().upper() == 'CORR':
                basis_position_types.append('EOD')
            basis_types_sql = ", ".join(f"'{t}'" for t in basis_position_types)

            # cis_position stores position_basis as 'TRADED' / 'SETTLED'
            for cp_basis in ('TRADED', 'SETTLED'):
                # Find the latest position as-of ex_date to use as the calc basis
                find_q = f"""
                SELECT position_id, version_id, market_value_fc, quantity,
                       cost_lc,
                       dividend_fc, dividend_lc, uncall_fc, uncall_lc,
                       pipeline_fc, pipeline_lc, provision_fc, provision_lc,
                       realized_pnl_fc, realized_pnl_lc, isin, src_system,
                       source_table, position_date
                FROM {self.DATABASE}.{self.POSITION_TABLE}
                WHERE portfolio = '{self._escape(portfolio_short_name)}'
                  AND security_label = '{self._escape(security_name)}'
                  AND src_system = 'CIS'
                  AND position_type IN ({basis_types_sql})
                  AND position_basis = '{cp_basis}'
                  AND position_date <= '{self._escape(str(ex_date))}'
                  AND quantity > 0
                ORDER BY position_date DESC, version_id DESC
                LIMIT 1
                """
                rows = impala_manager.execute_query(find_q, database=self.DATABASE)
                if not rows:
                    logger.info(f"[POS_ADJ] No CIS {cp_basis} row found for {portfolio_short_name}/{security_name} as of {ex_date} — skipping basis")
                    continue

                row = rows[0]
                # Target row is always the INT row dated at ex_date — computed
                # deterministically so the UPSERT lands on an existing same-date
                # INT row if one exists, or creates a new one if not. This is
                # deliberately NOT the basis row's own position_id/position_date.
                position_id   = _calc_position_id(
                    portfolio_short_name, security_name, cp_basis, str(ex_date), 'CIS'
                )
                position_date = str(ex_date)
                old_qty       = Decimal(str(row.get('quantity') or 0))
                old_mv_fc     = Decimal(str(row.get('market_value_fc') or 0))
                market_price  = (old_mv_fc / old_qty).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP) if old_qty else Decimal('0')

                # LC cost treatment — SA rule:
                #   NON-REVAL: redistribute the existing LC total cost over new qty
                #              (no FX recompute; cost in LC is preserved as-traded)
                #   REVAL:     recompute from FC cost × current FX rate
                if reval_status == 'NON-REVALUED':
                    old_total_cost_lc = Decimal(str(row.get('cost_lc') or 0))
                    new_total_cost_lc = old_total_cost_lc
                    new_avg_cost_lc   = (new_total_cost_lc / new_quantity).quantize(
                        Decimal('0.00000001'), rounding=ROUND_HALF_UP
                    ) if new_quantity > 0 else Decimal('0')
                else:
                    new_total_cost_lc = (new_total_cost * fx_rate).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                    new_avg_cost_lc   = (new_avg_cost * fx_rate).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

                market_value_fc   = (new_quantity * market_price).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                market_value_lc   = (market_value_fc * fx_rate).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                unrealized_pnl_fc = market_value_fc - new_total_cost
                unrealized_pnl_lc = market_value_lc - new_total_cost_lc

                # Carry forward accumulated CA/CF fields unchanged
                dividend_fc   = Decimal(str(row.get('dividend_fc', 0) or 0))
                dividend_lc   = Decimal(str(row.get('dividend_lc', 0) or 0))
                uncall_fc     = Decimal(str(row.get('uncall_fc', 0) or 0))
                uncall_lc     = Decimal(str(row.get('uncall_lc', 0) or 0))
                pipeline_fc   = Decimal(str(row.get('pipeline_fc', 0) or 0))
                pipeline_lc   = Decimal(str(row.get('pipeline_lc', 0) or 0))
                provision_fc  = Decimal(str(row.get('provision_fc', 0) or 0))
                provision_lc  = Decimal(str(row.get('provision_lc', 0) or 0))
                realized_pnl_fc = Decimal(str(row.get('realized_pnl_fc', 0) or 0))
                realized_pnl_lc = Decimal(str(row.get('realized_pnl_lc', 0) or 0))
                isin         = row.get('isin')
                source_table = row.get('source_table')

                # UPSERT on existing position_id — keeps position_type=INT, updates qty/AVP
                new_version_id = int(datetime.now().timestamp() * 1000)
                upsert_sql = f"""
                UPSERT INTO {self.DATABASE}.{self.POSITION_TABLE} (
                    position_id, version_id,
                    portfolio, security_label,
                    position_basis, position_date,
                    src_system, processing_date,
                    position_type,
                    quantity,
                    average_cost_fc, cost_fc,
                    average_cost_lc, cost_lc,
                    market_value_fc, market_value_lc,
                    net_book_value_fc, net_book_value_lc,
                    unrealized_pnl_fc, unrealized_pnl_lc,
                    realized_pnl_fc, realized_pnl_lc,
                    dividend_fc, dividend_lc,
                    uncall_fc, uncall_lc,
                    pipeline_fc, pipeline_lc,
                    provision_fc, provision_lc,
                    isin, source_table
                ) VALUES (
                    {position_id}, {new_version_id},
                    '{self._escape(portfolio_short_name)}',
                    '{self._escape(security_name)}',
                    '{cp_basis}',
                    '{self._escape(str(position_date))}',
                    'CIS',
                    '{timestamp_str}',
                    'INT',
                    {float(new_quantity)},
                    {float(new_avg_cost)},   {float(new_total_cost)},
                    {float(new_avg_cost_lc)}, {float(new_total_cost_lc)},
                    {float(market_value_fc)}, {float(market_value_lc)},
                    {float(market_value_fc)}, {float(market_value_lc)},
                    {float(unrealized_pnl_fc)}, {float(unrealized_pnl_lc)},
                    {float(realized_pnl_fc)},   {float(realized_pnl_lc)},
                    {float(dividend_fc)},   {float(dividend_lc)},
                    {float(uncall_fc)},     {float(uncall_lc)},
                    {float(pipeline_fc)},   {float(pipeline_lc)},
                    {float(provision_fc)},  {float(provision_lc)},
                    {f"'{self._escape(isin)}'" if isin else 'NULL'},
                    {f"'{self._escape(source_table)}'" if source_table else 'NULL'}
                )
                """
                ok = impala_manager.execute_write(upsert_sql, database=self.DATABASE)
                if ok:
                    logger.info(
                        f"[POS_ADJ] Wrote {cp_basis} INT row at position_date={position_date}: "
                        f"portfolio={portfolio_short_name} security={security_name} "
                        f"position_id={position_id} new_qty={new_quantity} "
                        f"new_avg_cost_fc={new_avg_cost} ca_type={ca_type}"
                    )
                    updated_any = True
                else:
                    logger.error(
                        f"[POS_ADJ] Failed to update {cp_basis} INT row for "
                        f"{portfolio_short_name}/{security_name}"
                    )

            return updated_any

        except Exception as e:
            logger.error(f"[POS_ADJ] Error updating position adjustment: {str(e)}")
            return False

    def _sync_ca_adjustment_to_golden_position(
        self,
        portfolio_short_name: str,
        security_name: str,
        new_quantity: Decimal,
        new_avg_cost: Decimal,
        new_total_cost: Decimal,
        market_value_fc: Decimal,
        market_value_lc: Decimal,
        unrealized_pnl_fc: Decimal,
        unrealized_pnl_lc: Decimal,
        dividend_fc: Decimal,
        dividend_lc: Decimal,
        uncall_fc: Decimal,
        uncall_lc: Decimal,
        pipeline_fc: Decimal,
        pipeline_lc: Decimal,
        provision_fc: Decimal,
        provision_lc: Decimal,
        position_date: str,
        ca_type: str,
        updated_by: str
    ) -> bool:
        """
        Sync a CA position adjustment (SPLIT, BONUS, REVERSE_SPLIT) into cis_position
        (the golden copy). cis_position PK = position_id — find the existing row for
        this portfolio+security (src_system='CIS') and UPSERT the updated qty/AVP.
        All other columns (realized_pnl, isin, src_system) are carried forward unchanged.
        """
        try:
            # Find the current row in cis_position for this portfolio+security (CIS source only)
            find_query = f"""
            SELECT position_id, version_id, realized_pnl_fc, realized_pnl_lc,
                   isin, source_table, src_system, position_basis
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE portfolio = '{self._escape(portfolio_short_name)}'
              AND security_label = '{self._escape(security_name)}'
              AND src_system = 'CIS'
            ORDER BY position_date DESC, version_id DESC
            LIMIT 1
            """
            rows = impala_manager.execute_query(find_query, database=self.DATABASE)
            if not rows:
                logger.warning(
                    f"[POS_ADJ] No cis_position row found for {portfolio_short_name}/{security_name} "
                    f"src_system=CIS — skipping golden copy sync"
                )
                return False

            row = rows[0]
            position_id = row.get('position_id')
            new_version_id = int(datetime.now().timestamp() * 1000) + 2  # +2 avoids collision
            today = datetime.now().strftime('%Y-%m-%d')

            realized_pnl_fc = Decimal(str(row.get('realized_pnl_fc') or 0))
            realized_pnl_lc = Decimal(str(row.get('realized_pnl_lc') or 0))
            isin = row.get('isin')
            source_table = row.get('source_table')
            src_system = row.get('src_system') or 'CIS'
            position_basis = row.get('position_basis') or 'SETTLED'

            upsert_sql = f"""
            UPSERT INTO {self.DATABASE}.{self.POSITION_TABLE} (
                position_id, version_id,
                portfolio, security_label,
                position_basis, position_date,
                src_system, processing_date,
                quantity,
                average_cost_fc, cost_fc,
                average_cost_lc, cost_lc,
                market_value_fc, market_value_lc,
                net_book_value_fc, net_book_value_lc,
                unrealized_pnl_fc, unrealized_pnl_lc,
                realized_pnl_fc, realized_pnl_lc,
                dividend_fc, dividend_lc,
                provision_fc, provision_lc,
                uncall_fc, uncall_lc,
                pipeline_fc, pipeline_lc,
                position_type,
                isin, source_table
            ) VALUES (
                {position_id}, {new_version_id},
                '{self._escape(portfolio_short_name)}',
                '{self._escape(security_name)}',
                '{self._escape(position_basis)}',
                '{self._escape(position_date)}',
                '{self._escape(src_system)}',
                '{today}',
                {float(new_quantity)},
                {float(new_avg_cost)}, {float(new_total_cost)},
                {float(new_avg_cost)}, {float(new_total_cost)},
                {float(market_value_fc)}, {float(market_value_lc)},
                {float(market_value_fc)}, {float(market_value_lc)},
                {float(unrealized_pnl_fc)}, {float(unrealized_pnl_lc)},
                {float(realized_pnl_fc)}, {float(realized_pnl_lc)},
                {float(dividend_fc)}, {float(dividend_lc)},
                {float(provision_fc)}, {float(provision_lc)},
                {float(uncall_fc)}, {float(uncall_lc)},
                {float(pipeline_fc)}, {float(pipeline_lc)},
                'CA_{self._escape(ca_type)}',
                {f"'{self._escape(isin)}'" if isin else 'NULL'},
                {f"'{self._escape(source_table)}'" if source_table else 'NULL'}
            )
            """

            success = impala_manager.execute_write(upsert_sql, database=self.DATABASE)
            if success:
                logger.info(
                    f"[POS_ADJ] Golden copy updated: cis_position position_id={position_id} "
                    f"portfolio={portfolio_short_name} security={security_name} "
                    f"qty={new_quantity} avg_cost_fc={new_avg_cost} ca_type={ca_type}"
                )
            else:
                logger.error(
                    f"[POS_ADJ] Failed to update cis_position for {portfolio_short_name}/{security_name}"
                )
            return success

        except Exception as e:
            logger.error(f"[POS_ADJ] Error syncing CA adjustment to cis_position: {str(e)}")
            return False

    def _apply_ca_to_trade_date_position(
        self,
        portfolio_short_name: str,
        security_name: str,
        new_quantity: Decimal,
        new_avg_cost: Decimal,
        new_total_cost: Decimal,
        ca_id: int,
        ca_number: str,
        ca_type: str,
        ex_date: str,
        security_currency: str,
        portfolio_currency: str,
        fx_rate: Decimal,
        updated_by: str
    ) -> bool:
        """Update the TRADED position after a CA split/bonus/reverse-split.

        Keeps committed-exposure (TRADED) view consistent with the settled
        position after a corporate action adjusts qty and AVP.
        """
        try:
            td_position = self._get_current_position(
                portfolio_short_name, security_name, position_basis='TRADED'
            )
            if not td_position:
                logger.warning(
                    f"[POS_ADJ] No TRADED position found for {portfolio_short_name}/{security_name} "
                    f"— skipping TRADED update (may be AMS/upload-only position)"
                )
                return True  # Not a hard failure

            td_version_id = td_position.get('version_id')
            td_position_id = td_position.get('position_id')
            td_market_price = Decimal(str(td_position.get('market_price', 0) or 0))
            td_dividend_fc = Decimal(str(td_position.get('dividend_fc', 0) or 0))
            td_dividend_lc = Decimal(str(td_position.get('dividend_lc', 0) or 0))
            uncall_fc = float(td_position.get('uncall_fc', 0) or 0)
            uncall_lc = float(td_position.get('uncall_lc', 0) or 0)
            pipeline_fc = float(td_position.get('pipeline_fc', 0) or 0)
            pipeline_lc = float(td_position.get('pipeline_lc', 0) or 0)
            commit_fc = float(td_position.get('commit_fc', 0) or 0)
            commit_lc = float(td_position.get('commit_lc', 0) or 0)
            provision_fc_val = float(td_position.get('provision_fc', 0) or 0)
            provision_lc_val = float(td_position.get('provision_lc', 0) or 0)
            position_type = td_position.get('position_type') or 'NORMAL'

            market_value_fc = (new_quantity * td_market_price).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
            market_value_lc = (market_value_fc * fx_rate).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

            # LC cost treatment — SA rule:
            #   NON-REVAL: redistribute existing LC total cost over new qty (no FX recompute)
            #   REVAL:     recompute from FC cost × current FX rate
            try:
                _rv_rows = impala_manager.execute_query(
                    f"SELECT revaluation_status FROM {self.DATABASE}.cis_portfolio "
                    f"WHERE name = '{self._escape(portfolio_short_name)}' LIMIT 1",
                    database=self.DATABASE
                )
                _reval_status = (
                    (_rv_rows[0].get('revaluation_status') or '').upper()
                    if _rv_rows else ''
                )
                if _reval_status not in ('REVALUED', 'NON-REVALUED'):
                    _reval_status = 'REVALUED'
            except Exception:
                _reval_status = 'REVALUED'

            if _reval_status == 'NON-REVALUED':
                old_total_cost_lc = Decimal(str(td_position.get('total_cost_lc') or 0))
                new_total_cost_lc = old_total_cost_lc
                new_avg_cost_lc = (new_total_cost_lc / new_quantity).quantize(
                    Decimal('0.00000001'), rounding=ROUND_HALF_UP
                ) if new_quantity > 0 else Decimal('0')
            else:
                new_total_cost_lc = (new_total_cost * fx_rate).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                new_avg_cost_lc = (new_avg_cost * fx_rate).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

            unrealized_pnl_fc = market_value_fc - new_total_cost
            unrealized_pnl_lc = market_value_lc - new_total_cost_lc

            self._mark_old_version_not_latest(td_version_id)

            timestamp = datetime.now()
            timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            new_version_id = int(timestamp.timestamp() * 1000) + 1  # +1 to avoid collision with SETTLED version

            insert_sql = f"""
            UPSERT INTO {self.DATABASE}.{self.WRITE_POSITION_TABLE} (
                version_id, position_id, position_date, position_basis,
                portfolio_short_name, security_label,
                quantity,
                average_cost_fc, total_cost_fc,
                average_cost_lc, total_cost_lc,
                market_price, market_value_fc, market_value_lc,
                realized_pnl_fc, unrealized_pnl_fc,
                realized_pnl_lc, unrealized_pnl_lc,
                dividend_fc, dividend_lc,
                uncall_fc, uncall_lc,
                pipeline_fc, pipeline_lc,
                commit_fc, commit_lc,
                provision_fc, provision_lc,
                position_type,
                trade_type,
                security_currency, portfolio_currency, fx_rate,
                status, is_active, is_latest,
                last_ca_id, last_ca_number, last_ca_type, last_ca_date,
                created_by, created_at, updated_by, updated_at
            ) VALUES (
                {new_version_id},
                {td_position_id},
                '{ex_date}',
                'TRADED',
                '{self._escape(portfolio_short_name)}',
                '{self._escape(security_name)}',
                {float(new_quantity)},
                {float(new_avg_cost)},
                {float(new_total_cost)},
                {float(new_avg_cost_lc)},
                {float(new_total_cost_lc)},
                {float(td_market_price)},
                {float(market_value_fc)},
                {float(market_value_lc)},
                0,
                {float(unrealized_pnl_fc)},
                0,
                {float(unrealized_pnl_lc)},
                {float(td_dividend_fc)},
                {float(td_dividend_lc)},
                {uncall_fc},
                {uncall_lc},
                {pipeline_fc},
                {pipeline_lc},
                {commit_fc},
                {commit_lc},
                {provision_fc_val},
                {provision_lc_val},
                '{self._escape(position_type)}',
                'CA_{ca_type}',
                '{self._escape(security_currency or "")}',
                '{self._escape(portfolio_currency or "")}',
                {float(fx_rate)},
                'OPEN',
                true,
                true,
                {ca_id},
                '{self._escape(ca_number)}',
                '{self._escape(ca_type)}',
                '{ex_date}',
                '{self._escape(updated_by)}',
                '{timestamp_str}',
                '{self._escape(updated_by)}',
                '{timestamp_str}'
            )
            """

            td_success = impala_manager.execute_write(insert_sql, database=self.DATABASE)
            if td_success:
                logger.info(
                    f"[POS_ADJ] SUCCESS - Created new TRADED position version {new_version_id} "
                    f"for {ca_type}. New qty={new_quantity}, avg_cost={new_avg_cost}"
                )
            else:
                logger.error(
                    f"[POS_ADJ] FAILED - Could not update TRADED position for "
                    f"{portfolio_short_name}/{security_name} after {ca_type}"
                )
            return td_success

        except Exception as e:
            logger.error(f"[POS_ADJ] Error updating TRADED position after {ca_type}: {str(e)}")
            return False

    def _create_rights_warrant_position(
        self,
        portfolio_short_name: str,
        new_security_name: str,
        entitlement_qty: Decimal,
        ca_id: int,
        ca_number: str,
        ca_type: str,
        ex_date: str,
        security_currency: str,
        portfolio_currency: str,
        created_by: str
    ) -> bool:
        """
        Create a brand-new position for a rights/warrant entitlement security.

        AVP = 0 (rights/warrants issued at no cost to the existing holder).
        position_id is a new ID (not the parent security's position_id).
        """
        try:
            timestamp = datetime.now()
            timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            new_version_id = int(timestamp.timestamp() * 1000)
            new_position_id = new_version_id + 1  # Unique position_id for the new security

            # FX rate for LC
            fx_rate = Decimal('1')
            if security_currency and portfolio_currency and security_currency != portfolio_currency:
                try:
                    fx_rate, _ = multicurrency_service.get_fx_rate(
                        security_currency, portfolio_currency, ex_date
                    )
                except Exception:
                    fx_rate = Decimal('1')

            insert_sql = f"""
            UPSERT INTO {self.DATABASE}.{self.WRITE_POSITION_TABLE} (
                version_id, position_id, position_date, position_basis,
                portfolio_short_name, security_label,
                quantity,
                average_cost_fc, total_cost_fc,
                average_cost_lc, total_cost_lc,
                market_price, market_value_fc, market_value_lc,
                realized_pnl_fc, unrealized_pnl_fc,
                realized_pnl_lc, unrealized_pnl_lc,
                dividend_fc, dividend_lc,
                uncall_fc, uncall_lc,
                pipeline_fc, pipeline_lc,
                commit_fc, commit_lc,
                provision_fc, provision_lc,
                position_type,
                trade_type,
                security_currency, portfolio_currency, fx_rate,
                status, is_active, is_latest,
                last_ca_id, last_ca_number, last_ca_type, last_ca_date,
                created_by, created_at, updated_by, updated_at
            ) VALUES (
                {new_version_id},
                {new_position_id},
                '{ex_date}',
                'SETTLED',
                '{self._escape(portfolio_short_name)}',
                '{self._escape(new_security_name)}',
                {float(entitlement_qty)},
                0, 0, 0, 0,
                0, 0, 0,
                0, 0, 0, 0,
                0, 0,
                0, 0, 0, 0,
                0, 0, 0, 0,
                'NORMAL',
                'CA_{ca_type}',
                '{self._escape(security_currency or "")}',
                '{self._escape(portfolio_currency or "")}',
                {float(fx_rate)},
                'OPEN',
                true,
                true,
                {ca_id},
                '{self._escape(ca_number)}',
                '{self._escape(ca_type)}',
                '{ex_date}',
                '{self._escape(created_by)}',
                '{timestamp_str}',
                '{self._escape(created_by)}',
                '{timestamp_str}'
            )
            """
            success = impala_manager.execute_write(insert_sql, database=self.DATABASE)
            if success:
                logger.info(f"[RIGHTS/WRNTS] Created new position for {new_security_name} "
                           f"in {portfolio_short_name}: qty={entitlement_qty}, AVP=0")
            else:
                logger.error(f"[RIGHTS/WRNTS] Failed to create position for {new_security_name}")
            return success

        except Exception as e:
            logger.error(f"[RIGHTS/WRNTS] Error creating rights/warrant position: {str(e)}")
            return False

    def _process_cf_position_overwrite(
        self,
        queue_id: int,
        queue_entry: Dict[str, Any],
        dry_run: bool = False
    ) -> Tuple[bool, str, int, Decimal]:
        """
        Process CF-only position overwrite types (no cash flow record created).

        Handlers:
          CF-COMMITMENT       → overwrite commit_fc / commit_lc
          CF-UN CALL COMMITMENT → overwrite uncall_fc / uncall_lc
          CF-PIPELINE         → overwrite pipeline_fc / pipeline_lc
          CF-YTD              → overwrite realized_pnl_fc / realized_pnl_lc
          CF-PROVISION        → overwrite provision_fc / provision_lc

        The 'price' field in the queue entry stores the new value (in FC).
        LC = price × FX rate.
        """
        try:
            ca_type = (queue_entry.get('ca_type') or '').strip().upper()
            security_name = queue_entry.get('security_name')
            ex_date = queue_entry.get('ex_date')
            new_value_fc = Decimal(str(queue_entry.get('price') or 0))
            currency = queue_entry.get('currency')
            ca_id = int(queue_entry.get('ca_id')) if queue_entry.get('ca_id') else None
            ca_number = queue_entry.get('ca_number')
            created_by = queue_entry.get('created_by', 'system')

            logger.info(f"[CF_OVERWRITE] Processing {ca_type}: security={security_name}, "
                       f"new_value_fc={new_value_fc}, ex_date={ex_date}")

            holdings = self.get_holdings_for_ca(security_name=security_name, as_of_date=ex_date)

            if not holdings:
                msg = f"No holdings found for security {security_name} as of {ex_date}"
                logger.info(msg)
                if not dry_run:
                    ca_cash_flow_queue_repository.mark_completed(queue_id, 0, Decimal('0'))
                return True, msg, 0, Decimal('0')

            positions_updated = 0
            errors = []

            for holding in holdings:
                portfolio_short_name = holding.get('portfolio_short_name')
                security_currency = holding.get('security_currency') or currency
                portfolio_currency = (
                    holding.get('portfolio_base_currency') or
                    holding.get('portfolio_currency') or
                    security_currency
                )

                # Convert FC value to LC
                if security_currency != portfolio_currency:
                    try:
                        fx_rate, _ = multicurrency_service.get_fx_rate(
                            security_currency, portfolio_currency, ex_date
                        )
                        new_value_lc = (new_value_fc * fx_rate).quantize(
                            Decimal('0.00000001'), rounding=ROUND_HALF_UP
                        )
                    except Exception as e:
                        logger.warning(f"FX lookup failed {security_currency}->{portfolio_currency}: {e}")
                        fx_rate = Decimal('1')
                        new_value_lc = new_value_fc
                else:
                    fx_rate = Decimal('1')
                    new_value_lc = new_value_fc

                if dry_run:
                    logger.info(f"[DRY RUN] Would overwrite {ca_type} on "
                               f"{portfolio_short_name}/{security_name}: "
                               f"FC={new_value_fc}, LC={new_value_lc}")
                    positions_updated += 1
                    continue

                try:
                    success = self._overwrite_position_field(
                        portfolio_short_name=portfolio_short_name,
                        security_name=security_name,
                        ca_type=ca_type,
                        new_value_fc=new_value_fc,
                        new_value_lc=new_value_lc,
                        ca_id=ca_id,
                        ca_number=ca_number,
                        ex_date=ex_date,
                        updated_by=created_by
                    )
                    if success:
                        positions_updated += 1
                    else:
                        errors.append(f"{portfolio_short_name}: overwrite failed")
                except Exception as e:
                    errors.append(f"{portfolio_short_name}: {str(e)}")

            if not dry_run:
                if errors:
                    error_msg = "; ".join(errors[:5])
                    ca_cash_flow_queue_repository.mark_failed(queue_id, error_msg)
                    return False, error_msg, positions_updated, Decimal('0')
                else:
                    ca_cash_flow_queue_repository.mark_completed(queue_id, positions_updated, Decimal('0'))

            msg = f"Overwrote {ca_type} on {positions_updated} positions"
            return True, msg, positions_updated, Decimal('0')

        except Exception as e:
            error_msg = f"Error processing CF position overwrite: {str(e)}"
            logger.error(error_msg)
            if not dry_run:
                ca_cash_flow_queue_repository.mark_failed(queue_id, error_msg)
            return False, error_msg, 0, Decimal('0')

    def _overwrite_position_field(
        self,
        portfolio_short_name: str,
        security_name: str,
        ca_type: str,
        new_value_fc: Decimal,
        new_value_lc: Decimal,
        ca_id: int,
        ca_number: str,
        ex_date: str,
        updated_by: str
    ) -> bool:
        """
        Create a new position version with a specific field overwritten.

        Field mapping:
          CF-COMMITMENT         → commit_fc / commit_lc
          CF-UN CALL COMMITMENT → uncall_fc / uncall_lc
          CF-PIPELINE           → pipeline_fc / pipeline_lc
          CF-YTD                → realized_pnl_fc / realized_pnl_lc
          CF-PROVISION          → provision_fc / provision_lc
        """
        try:
            current_position = self._get_current_position(portfolio_short_name, security_name)
            if not current_position:
                logger.warning(f"[CF_OVERWRITE] No open SETTLED position for "
                               f"{portfolio_short_name}/{security_name}")
                return False

            position_id = current_position.get('position_id')
            old_version_id = current_position.get('version_id')

            # Carry forward all existing values
            quantity = Decimal(str(current_position.get('quantity', 0) or 0))
            avg_cost_fc = Decimal(str(current_position.get('average_cost_fc', 0) or 0))
            total_cost_fc = Decimal(str(current_position.get('total_cost_fc', 0) or 0))
            avg_cost_lc = Decimal(str(current_position.get('average_cost_lc', 0) or 0))
            total_cost_lc = Decimal(str(current_position.get('total_cost_lc', 0) or 0))
            market_price = Decimal(str(current_position.get('market_price', 0) or 0))
            market_value_fc = Decimal(str(current_position.get('market_value_fc', 0) or 0))
            market_value_lc = Decimal(str(current_position.get('market_value_lc', 0) or 0))
            realized_pnl_fc = Decimal(str(current_position.get('realized_pnl_fc', 0) or 0))
            unrealized_pnl_fc = Decimal(str(current_position.get('unrealized_pnl_fc', 0) or 0))
            realized_pnl_lc = Decimal(str(current_position.get('realized_pnl_lc', 0) or 0))
            unrealized_pnl_lc = Decimal(str(current_position.get('unrealized_pnl_lc', 0) or 0))
            dividend_fc = Decimal(str(current_position.get('dividend_fc', 0) or 0))
            dividend_lc = Decimal(str(current_position.get('dividend_lc', 0) or 0))
            uncall_fc = float(current_position.get('uncall_fc', 0) or 0)
            uncall_lc = float(current_position.get('uncall_lc', 0) or 0)
            pipeline_fc = float(current_position.get('pipeline_fc', 0) or 0)
            pipeline_lc = float(current_position.get('pipeline_lc', 0) or 0)
            commit_fc = float(current_position.get('commit_fc', 0) or 0)
            commit_lc = float(current_position.get('commit_lc', 0) or 0)
            provision_fc_val = float(current_position.get('provision_fc', 0) or 0)
            provision_lc_val = float(current_position.get('provision_lc', 0) or 0)
            security_currency = current_position.get('security_currency', '')
            portfolio_currency = current_position.get('portfolio_currency', '')
            fx_rate = float(current_position.get('fx_rate', 1) or 1)
            position_type = current_position.get('position_type') or 'NORMAL'

            # Apply the overwrite based on CA type
            ca_type_upper = ca_type.upper()
            if ca_type_upper == 'CF-COMMITMENT':
                commit_fc = float(new_value_fc)
                commit_lc = float(new_value_lc)
            elif ca_type_upper == 'CF-UN CALL COMMITMENT':
                uncall_fc = float(new_value_fc)
                uncall_lc = float(new_value_lc)
            elif ca_type_upper == 'CF-PIPELINE':
                pipeline_fc = float(new_value_fc)
                pipeline_lc = float(new_value_lc)
            elif ca_type_upper == 'CF-YTD':
                realized_pnl_fc = new_value_fc
                realized_pnl_lc = new_value_lc
            elif ca_type_upper == 'CF-PROVISION':
                provision_fc_val = float(new_value_fc)
                provision_lc_val = float(new_value_lc)
            else:
                logger.warning(f"[CF_OVERWRITE] Unknown CF type: {ca_type}")
                return False

            # Mark old version as not latest
            self._mark_old_version_not_latest(old_version_id)

            timestamp = datetime.now()
            timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            new_version_id = int(timestamp.timestamp() * 1000)

            insert_sql = f"""
            UPSERT INTO {self.DATABASE}.{self.WRITE_POSITION_TABLE} (
                version_id, position_id, position_date, position_basis,
                portfolio_short_name, security_label,
                quantity,
                average_cost_fc, total_cost_fc,
                average_cost_lc, total_cost_lc,
                market_price, market_value_fc, market_value_lc,
                realized_pnl_fc, unrealized_pnl_fc,
                realized_pnl_lc, unrealized_pnl_lc,
                dividend_fc, dividend_lc,
                uncall_fc, uncall_lc,
                pipeline_fc, pipeline_lc,
                commit_fc, commit_lc,
                provision_fc, provision_lc,
                position_type,
                trade_type,
                security_currency, portfolio_currency, fx_rate,
                status, is_active, is_latest,
                last_ca_id, last_ca_number, last_ca_type, last_ca_date,
                created_by, created_at, updated_by, updated_at
            ) VALUES (
                {new_version_id},
                {position_id},
                '{ex_date}',
                'SETTLED',
                '{self._escape(portfolio_short_name)}',
                '{self._escape(security_name)}',
                {float(quantity)},
                {float(avg_cost_fc)},
                {float(total_cost_fc)},
                {float(avg_cost_lc)},
                {float(total_cost_lc)},
                {float(market_price)},
                {float(market_value_fc)},
                {float(market_value_lc)},
                {float(realized_pnl_fc)},
                {float(unrealized_pnl_fc)},
                {float(realized_pnl_lc)},
                {float(unrealized_pnl_lc)},
                {float(dividend_fc)},
                {float(dividend_lc)},
                {uncall_fc},
                {uncall_lc},
                {pipeline_fc},
                {pipeline_lc},
                {commit_fc},
                {commit_lc},
                {provision_fc_val},
                {provision_lc_val},
                '{self._escape(position_type)}',
                '{self._escape(ca_type)}',
                '{self._escape(security_currency)}',
                '{self._escape(portfolio_currency)}',
                {fx_rate},
                'OPEN',
                true,
                true,
                {ca_id},
                '{self._escape(ca_number)}',
                '{self._escape(ca_type)}',
                '{ex_date}',
                '{self._escape(updated_by)}',
                '{timestamp_str}',
                '{self._escape(updated_by)}',
                '{timestamp_str}'
            )
            """
            success = impala_manager.execute_write(insert_sql, database=self.DATABASE)
            if success:
                logger.info(f"[CF_OVERWRITE] SUCCESS - {ca_type} applied to "
                           f"{portfolio_short_name}/{security_name}: "
                           f"FC={new_value_fc}, LC={new_value_lc}")
            else:
                logger.error(f"[CF_OVERWRITE] FAILED - could not write new position version")
            return success

        except Exception as e:
            logger.error(f"[CF_OVERWRITE] Error: {str(e)}")
            return False

    def process_pending_cas(
        self,
        payment_date: str = None,
        batch_size: int = 100,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Process all pending CAs in the queue.

        Args:
            payment_date: Optional filter by payment date
            batch_size: Number of CAs to process per batch
            dry_run: If True, don't actually create cash flows

        Returns:
            Dictionary with processing statistics
        """
        try:
            pending = ca_cash_flow_queue_repository.get_pending(
                limit=batch_size,
                payment_date=payment_date
            )

            stats = {
                'total_processed': 0,
                'successful': 0,
                'failed': 0,
                'cash_flows_created': 0,
                'total_amount': Decimal('0'),
                'errors': []
            }

            logger.info(f"[PENDING] Processing {len(pending)} pending CA entries")
            for entry_idx, entry in enumerate(pending):
                queue_id = entry.get('queue_id')
                ca_number = entry.get('ca_number')

                logger.info(f"[PENDING] === Processing entry {entry_idx + 1}/{len(pending)}: CA {ca_number} (queue_id: {queue_id}) ===")
                logger.info(f"[PENDING] Full entry data: {entry}")

                success, message, cf_count, amount = self.process_ca_cash_flows(
                    queue_id=queue_id,
                    dry_run=dry_run
                )

                stats['total_processed'] += 1
                stats['cash_flows_created'] += cf_count
                stats['total_amount'] += amount

                if success:
                    stats['successful'] += 1
                else:
                    stats['failed'] += 1
                    stats['errors'].append(f"{ca_number}: {message}")

            return stats

        except Exception as e:
            logger.error(f"Error processing pending CAs: {str(e)}")
            return {
                'total_processed': 0,
                'successful': 0,
                'failed': 0,
                'cash_flows_created': 0,
                'total_amount': Decimal('0'),
                'errors': [str(e)]
            }

    def get_cash_flows_by_ca(self, ca_id: int) -> List[Dict[str, Any]]:
        """
        Get all cash flows generated from a specific corporate action.

        Args:
            ca_id: Corporate Action ID

        Returns:
            List of cash flow dictionaries
        """
        try:
            # Get from log table
            logs = ca_cash_flow_queue_repository.get_logs_by_queue_id(ca_id)

            # Also try to get directly from cash flow table if ca_id field exists
            try:
                query = f"""
                SELECT *
                FROM {self.DATABASE}.cis_cash_flow
                WHERE ca_id = {ca_id}
                ORDER BY created_at DESC
                """
                results = impala_manager.execute_query(query, database=self.DATABASE)
                if results:
                    return results
            except Exception:
                pass  # ca_id column may not exist yet

            return logs

        except Exception as e:
            logger.error(f"Error getting cash flows for CA {ca_id}: {str(e)}")
            return []


# Create singleton instance
ca_cash_flow_service = CACashFlowService()
