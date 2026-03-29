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

logger = logging.getLogger(__name__)


class CACashFlowService:
    """Service for generating cash flows from corporate actions"""

    DATABASE = 'gmp_cis'
    POSITION_TABLE = 'cis_trade_position'

    # CA types that generate cash flows (payment to holder)
    # Includes both internal names and dropdown values
    CASH_FLOW_CA_TYPES = [
        'DIVIDEND', 'SPECIAL_DIVIDEND', 'INTEREST', 'COUPON', 'ROC',
        'CAPITAL_DISTRIBUTION',  # From dropdown
    ]

    # CA types that affect position quantity (no cash flow)
    # Includes both internal names and dropdown values
    POSITION_ADJUSTMENT_CA_TYPES = [
        'BONUS_ISSUE', 'SPLIT', 'STOCK_SPLIT', 'REVERSE_SPLIT',
        'RIGHTS_ENTITLEMENT', 'RIGHTS_ISSUE',
        'WARRANT_ENTITLEMENT', 'CONSOLIDATION',
    ]

    # CA type to Cash Flow type mapping
    CA_TO_CF_TYPE_MAP = {
        'DIVIDEND': 'DIVIDEND',
        'SPECIAL_DIVIDEND': 'SPECIAL_DIVIDEND',
        'INTEREST': 'INTEREST',
        'COUPON': 'COUPON',
        'ROC': 'ROC',  # Return of Capital
    }

    # CA types where AVP (average cost) should NOT change
    # Dividend/Special Dividend: AVP unchanged (just cash distribution)
    NO_AVP_CHANGE_CA_TYPES = ['DIVIDEND', 'SPECIAL_DIVIDEND', 'INTEREST', 'COUPON']

    # CA types where AVP should be reduced by price (cost basis reduction)
    # ROC: AVP = AVP_old - price_per_share
    AVP_REDUCTION_CA_TYPES = ['ROC']

    @staticmethod
    def _escape(value: str) -> str:
        """Escape string for SQL."""
        if value is None:
            return ''
        return str(value).replace("'", "''")

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
            # Check by matching ex_date, portfolio, security, and cash flow type
            query = f"""
            SELECT cash_flow_id, cash_flow_number
            FROM {self.DATABASE}.cis_cash_flow
            WHERE portfolio_short_name = '{self._escape(portfolio_short_name)}'
              AND security_label = '{self._escape(security_name)}'
              AND ex_date = '{ex_date}'
              AND cash_flow_type IN ('DIVIDEND', 'INTEREST', 'COUPON', 'CAPITAL_DISTRIBUTION')
              AND (is_deleted = false OR is_deleted IS NULL)
            LIMIT 1
            """
            logger.info(f"[CHECK_DUP] Checking for existing cash flow with query: {query.strip()}")
            results = impala_manager.execute_query(query, database=self.DATABASE)
            logger.info(f"[CHECK_DUP] Query returned {len(results) if results else 0} results: {results}")
            if results and len(results) > 0:
                return results[0]
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
            ca_type = ca_data.get('ca_type', '')

            # Check if CA type requires processing
            if ca_type not in self.CASH_FLOW_CA_TYPES and ca_type not in self.POSITION_ADJUSTMENT_CA_TYPES:
                logger.info(f"CA type {ca_type} does not require processing, skipping queue")
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
        dry_run: bool = False
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

            ca_type = queue_entry.get('ca_type')
            security_name = queue_entry.get('security_name')
            ex_date = queue_entry.get('ex_date')
            price = Decimal(str(queue_entry.get('price') or 0))
            currency = queue_entry.get('currency')
            ca_id = queue_entry.get('ca_id')
            ca_number = queue_entry.get('ca_number')
            payment_date = queue_entry.get('payment_date')
            record_date = queue_entry.get('record_date')

            # Route to appropriate processor based on CA type
            if ca_type in self.POSITION_ADJUSTMENT_CA_TYPES:
                # Position adjustment types (BONUS_ISSUE, SPLIT, RIGHTS, WARRANT)
                return self._process_position_adjustment_ca(
                    queue_id=queue_id,
                    queue_entry=queue_entry,
                    dry_run=dry_run
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

    def get_holdings_for_ca(
        self,
        security_name: str,
        as_of_date: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get ALL portfolio holdings for a security as of a specific date.
        CA applies at security level - finds all portfolios holding the security.

        Args:
            security_name: Security name (comma-separated if multiple)
            as_of_date: Date to check holdings (YYYY-MM-DD), defaults to today

        Returns:
            List of holdings with portfolio_short_name, quantity, security_label
        """
        try:
            if not as_of_date:
                as_of_date = datetime.now().strftime('%Y-%m-%d')

            # Handle multiple securities (comma-separated)
            securities = [s.strip() for s in security_name.split(',') if s.strip()]
            if not securities:
                return []

            security_conditions = " OR ".join([
                f"security_label = '{self._escape(s)}'" for s in securities
            ])

            # Build query for holdings as of ex_date
            # Get the latest position version for each portfolio+security as of the ex_date
            # This finds ALL portfolios holding the security - no portfolio filter
            # Also join with portfolio table to get portfolio currency (for local amount calculation)
            query = f"""
            SELECT
                p.portfolio_short_name,
                p.security_label,
                p.quantity,
                p.average_cost,
                p.security_currency,
                p.portfolio_currency,
                pf.currency as portfolio_base_currency
            FROM {self.DATABASE}.{self.POSITION_TABLE} p
            INNER JOIN (
                SELECT portfolio_short_name, security_label, MAX(position_date) as max_date
                FROM {self.DATABASE}.{self.POSITION_TABLE}
                WHERE ({security_conditions})
                  AND position_date <= '{as_of_date}'
                  AND status = 'OPEN'
                  AND is_active = true
                GROUP BY portfolio_short_name, security_label
            ) latest ON p.portfolio_short_name = latest.portfolio_short_name
                    AND p.security_label = latest.security_label
                    AND p.position_date = latest.max_date
            LEFT JOIN {self.DATABASE}.cis_portfolio pf ON p.portfolio_short_name = pf.name
            WHERE p.quantity > 0
              AND p.status = 'OPEN'
              AND p.is_active = true
            ORDER BY p.portfolio_short_name, p.security_label
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

            # Map to actual cis_cash_flow table field names
            # Following SA/BA specification for multi-currency cash flows
            # CA-generated cash flows are auto-validated (no four-eyes needed)
            cf_data = {
                'cash_flow_number': cf_number,
                'portfolio_short_name': portfolio_short_name,
                'security_label': security_name,
                'cash_flow_type': cf_type,
                'send_receive': 'RECEIVE',  # Dividends are received
                'position_updated': False,
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
                'fx_rate': float(fx_rate),      # FX rate used for LC conversion
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
        Create a NEW position version with CA/cash flow details.

        Based on SA Specification for AVP changes:
        - DIVIDEND/SPECIAL_DIVIDEND: AVP unchanged (just record cash flow)
        - ROC (Return of Capital): AVP = AVP_old - price_per_share (cost basis reduction)

        Args:
            portfolio_short_name: Portfolio short name
            security_name: Security label
            ca_id: Corporate Action ID
            ca_number: CA number
            ca_type: CA type (DIVIDEND, INTEREST, ROC, etc.)
            ex_date: Ex-dividend date
            cash_flow_id: Created cash flow ID
            cash_flow_number: Cash flow number
            cash_flow_amount_fc: Cash flow amount in Foreign Currency (security currency)
            cash_flow_amount_lc: Cash flow amount in Local Currency (portfolio currency)
            security_currency: Security currency code (FC)
            portfolio_currency: Portfolio currency code (LC)
            fx_rate: FX rate used (FC to LC)
            updated_by: User who triggered the update

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"[UPDATE_POS] Creating new position version with CA details: "
                       f"portfolio={portfolio_short_name}, security={security_name}, "
                       f"ca_number={ca_number}, cf_number={cash_flow_number}, "
                       f"amount_fc={cash_flow_amount_fc} {security_currency}, "
                       f"amount_lc={cash_flow_amount_lc} {portfolio_currency}, fx_rate={fx_rate}")

            # Step 1: Get current open position
            current_position = self._get_current_position(portfolio_short_name, security_name)

            if not current_position:
                logger.warning(f"[UPDATE_POS] No open position found for {portfolio_short_name}/{security_name}")
                return False

            # Step 2: Extract current values
            position_id = current_position.get('position_id')
            old_version_id = current_position.get('version_id')
            quantity = Decimal(str(current_position.get('quantity', 0) or 0))
            old_total_cost = Decimal(str(current_position.get('total_cost', 0) or 0))
            old_avg_cost = Decimal(str(current_position.get('average_cost', 0) or 0))
            old_total_cost_base = Decimal(str(current_position.get('total_cost_base', 0) or 0))
            old_avg_cost_base = Decimal(str(current_position.get('average_cost_base', 0) or 0))
            current_price = Decimal(str(current_position.get('current_price', 0) or 0))
            market_value = Decimal(str(current_position.get('market_value', 0) or 0))

            # Get existing P&L values (in FC)
            realized_pnl_fc = Decimal(str(current_position.get('realized_pnl_fc', 0) or
                                         current_position.get('realized_pnl', 0) or 0))
            realized_pnl_lc = Decimal(str(current_position.get('realized_pnl_lc', 0) or
                                         current_position.get('realized_pnl_base', 0) or 0))

            logger.info(f"[UPDATE_POS] Current position: qty={quantity}, total_cost={old_total_cost}, "
                       f"avg_cost={old_avg_cost}, realized_pnl_fc={realized_pnl_fc}, realized_pnl_lc={realized_pnl_lc}")

            # Step 3: Calculate new values based on CA type per SA specification
            if ca_type in self.NO_AVP_CHANGE_CA_TYPES:
                # DIVIDEND, SPECIAL_DIVIDEND, INTEREST, COUPON: AVP unchanged
                # Just record the cash flow, no cost basis change
                logger.info(f"[UPDATE_POS] CA type {ca_type}: AVP unchanged per SA specification")
                new_total_cost_fc = old_total_cost
                new_avg_cost_fc = old_avg_cost
                new_total_cost_lc = old_total_cost_base
                new_avg_cost_lc = old_avg_cost_base
            elif ca_type in self.AVP_REDUCTION_CA_TYPES:
                # ROC (Return of Capital): AVP = AVP_old - price_per_share
                # Cost basis is reduced by the ROC amount
                logger.info(f"[UPDATE_POS] CA type {ca_type}: AVP reduced by cash flow amount (cost basis reduction)")
                new_total_cost_fc = (old_total_cost - cash_flow_amount_fc).quantize(
                    Decimal('0.00000001'), rounding=ROUND_HALF_UP
                )
                if new_total_cost_fc < 0:
                    new_total_cost_fc = Decimal('0')  # Cost basis can't go negative

                # Recalculate average cost in FC
                if quantity > 0:
                    new_avg_cost_fc = (new_total_cost_fc / quantity).quantize(
                        Decimal('0.00000001'), rounding=ROUND_HALF_UP
                    )
                else:
                    new_avg_cost_fc = Decimal('0')

                # Calculate values in LC
                new_total_cost_lc = (old_total_cost_base - cash_flow_amount_lc).quantize(
                    Decimal('0.00000001'), rounding=ROUND_HALF_UP
                )
                if new_total_cost_lc < 0:
                    new_total_cost_lc = Decimal('0')

                if quantity > 0:
                    new_avg_cost_lc = (new_total_cost_lc / quantity).quantize(
                        Decimal('0.00000001'), rounding=ROUND_HALF_UP
                    )
                else:
                    new_avg_cost_lc = Decimal('0')
            else:
                # Default: keep existing values
                new_total_cost_fc = old_total_cost
                new_avg_cost_fc = old_avg_cost
                new_total_cost_lc = old_total_cost_base
                new_avg_cost_lc = old_avg_cost_base

            # Market value in LC
            market_value_lc = (market_value * fx_rate).quantize(
                Decimal('0.00000001'), rounding=ROUND_HALF_UP
            )

            # Calculate unrealized P&L in FC
            new_unrealized_pnl_fc = (market_value - new_total_cost_fc).quantize(
                Decimal('0.00000001'), rounding=ROUND_HALF_UP
            )

            # Unrealized P&L in LC
            new_unrealized_pnl_lc = (market_value_lc - new_total_cost_lc).quantize(
                Decimal('0.00000001'), rounding=ROUND_HALF_UP
            )

            logger.info(f"[UPDATE_POS] After {ca_type} in FC: total_cost={new_total_cost_fc}, "
                       f"avg_cost={new_avg_cost_fc}, unrealized_pnl={new_unrealized_pnl_fc}")
            logger.info(f"[UPDATE_POS] After {ca_type} in LC: total_cost={new_total_cost_lc}, "
                       f"avg_cost={new_avg_cost_lc}, unrealized_pnl={new_unrealized_pnl_lc}")

            # Step 5: Mark old version as not latest
            self._mark_old_version_not_latest(old_version_id)

            # Step 6: Create new position version with all currency values
            timestamp = datetime.now()
            timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            new_version_id = int(timestamp.timestamp() * 1000)

            insert_sql = f"""
            UPSERT INTO {self.DATABASE}.{self.POSITION_TABLE} (
                version_id, position_id, position_date,
                portfolio_short_name, security_label,
                quantity, average_cost, total_cost,
                current_price, market_value, market_value_lc,
                realized_pnl, unrealized_pnl,
                realized_pnl_fc, unrealized_pnl_fc,
                realized_pnl_lc, unrealized_pnl_lc,
                trade_id, trade_type,
                security_currency, portfolio_currency, fx_rate,
                average_cost_base, total_cost_base, realized_pnl_base,
                status, is_active, is_latest,
                last_ca_id, last_ca_number, last_ca_type, last_ca_date,
                last_cash_flow_id, last_cash_flow_number, last_cash_flow_amount,
                created_by, created_at, updated_by, updated_at
            ) VALUES (
                {new_version_id},
                {position_id},
                '{ex_date}',
                '{self._escape(portfolio_short_name)}',
                '{self._escape(security_name)}',
                {float(quantity)},
                {float(new_avg_cost_fc)},
                {float(new_total_cost_fc)},
                {float(current_price)},
                {float(market_value)},
                {float(market_value_lc)},
                {float(realized_pnl_fc)},
                {float(new_unrealized_pnl_fc)},
                {float(realized_pnl_fc)},
                {float(new_unrealized_pnl_fc)},
                {float(realized_pnl_lc)},
                {float(new_unrealized_pnl_lc)},
                NULL,
                'CA_{ca_type}',
                '{self._escape(security_currency)}',
                '{self._escape(portfolio_currency)}',
                {float(fx_rate)},
                {float(new_avg_cost_lc)},
                {float(new_total_cost_lc)},
                {float(realized_pnl_lc)},
                'OPEN',
                true,
                true,
                {ca_id},
                '{self._escape(ca_number)}',
                '{self._escape(ca_type)}',
                '{ex_date}',
                {cash_flow_id},
                '{self._escape(cash_flow_number)}',
                {float(cash_flow_amount_lc)},
                '{self._escape(updated_by)}',
                '{timestamp_str}',
                '{self._escape(updated_by)}',
                '{timestamp_str}'
            )
            """

            success = impala_manager.execute_write(insert_sql, database=self.DATABASE)

            if success:
                logger.info(f"[UPDATE_POS] SUCCESS - Created new position version {new_version_id} "
                           f"with CA/cash flow details. New avg_cost_fc={new_avg_cost_fc}, avg_cost_lc={new_avg_cost_lc}")
            else:
                logger.error(f"[UPDATE_POS] FAILED - Could not create new position version")

            return success

        except Exception as e:
            logger.error(f"[UPDATE_POS] Error creating position version with CA details: {str(e)}")
            # Don't fail the cash flow creation if position update fails
            return False

    def _get_current_position(
        self,
        portfolio_short_name: str,
        security_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get the current open position for a portfolio/security combination."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE portfolio_short_name = '{self._escape(portfolio_short_name)}'
              AND security_label = '{self._escape(security_name)}'
              AND status = 'OPEN'
              AND is_active = true
              AND (is_latest = true OR is_latest IS NULL)
            ORDER BY position_date DESC, version_id DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"[UPDATE_POS] Error getting current position: {str(e)}")
            return None

    def _mark_old_version_not_latest(self, version_id: int) -> bool:
        """Mark an existing position version as not latest."""
        try:
            update_sql = f"""
            UPDATE {self.DATABASE}.{self.POSITION_TABLE}
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
        dry_run: bool = False
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
            ca_type = queue_entry.get('ca_type')
            security_name = queue_entry.get('security_name')
            ex_date = queue_entry.get('ex_date')
            price = Decimal(str(queue_entry.get('price') or 1))  # Price is ratio for BONUS/SPLIT
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
                avg_cost = Decimal(str(holding.get('average_cost') or 0))
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
                            dry_run=dry_run
                        )
                    elif ca_type in ['SPLIT', 'STOCK_SPLIT', 'CONSOLIDATION']:
                        # Forward split: qty_new = qty_old × ratio, AVP = AVP_old / ratio
                        success = self._process_split(
                            portfolio_short_name=portfolio_short_name,
                            security_name=security_name,
                            old_quantity=quantity,
                            old_avg_cost=avg_cost,
                            ratio=price,  # price field stores the split ratio (e.g., 2 for 2:1 split)
                            ca_id=ca_id,
                            ca_number=ca_number,
                            ex_date=ex_date,
                            security_currency=security_currency,
                            portfolio_currency=portfolio_currency,
                            updated_by=created_by,
                            dry_run=dry_run
                        )
                    elif ca_type == 'REVERSE_SPLIT':
                        # Reverse split: qty_new = qty_old / ratio, AVP = AVP_old × ratio
                        # For reverse split, invert the ratio
                        reverse_ratio = Decimal('1') / price if price > 0 else Decimal('1')
                        success = self._process_split(
                            portfolio_short_name=portfolio_short_name,
                            security_name=security_name,
                            old_quantity=quantity,
                            old_avg_cost=avg_cost,
                            ratio=reverse_ratio,  # Inverted ratio for reverse split
                            ca_id=ca_id,
                            ca_number=ca_number,
                            ex_date=ex_date,
                            security_currency=security_currency,
                            portfolio_currency=portfolio_currency,
                            updated_by=created_by,
                            dry_run=dry_run
                        )
                    elif ca_type in ['RIGHTS_ENTITLEMENT', 'RIGHTS_ISSUE', 'WARRANT_ENTITLEMENT']:
                        # Creates new position for the rights/warrant security
                        # For now, just log - actual implementation would need the new security details
                        logger.info(f"[POS_ADJ] {ca_type}: Would create new position for rights/warrant. "
                                   f"Portfolio={portfolio_short_name}, Old Security={security_name}, Qty={quantity}")
                        success = True  # Placeholder - full implementation needs new security info
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
        dry_run: bool = False
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
                updated_by=updated_by
            )

        except Exception as e:
            logger.error(f"[BONUS] Error processing bonus issue: {str(e)}")
            return False

    def _process_split(
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
        dry_run: bool = False
    ) -> bool:
        """
        Process SPLIT: qty_new = qty_old × ratio, AVP = AVP_old / ratio

        Example: 2:1 split (ratio=2) with 100 shares @ $100
        - New qty = 100 × 2 = 200 shares
        - New AVP = $100 / 2 = $50
        - Total cost stays same = $10,000
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

            logger.info(f"[SPLIT] Portfolio={portfolio_short_name}, Security={security_name}")
            logger.info(f"[SPLIT] Old: qty={old_quantity}, avg_cost={old_avg_cost}, total={old_total_cost}")
            logger.info(f"[SPLIT] New: qty={new_quantity}, avg_cost={new_avg_cost} (ratio={ratio})")

            if dry_run:
                return True

            # Create new position version
            return self._create_position_adjustment_version(
                portfolio_short_name=portfolio_short_name,
                security_name=security_name,
                new_quantity=new_quantity,
                new_avg_cost=new_avg_cost,
                new_total_cost=old_total_cost,  # Total cost unchanged for split
                ca_id=ca_id,
                ca_number=ca_number,
                ca_type='SPLIT',
                ex_date=ex_date,
                security_currency=security_currency,
                portfolio_currency=portfolio_currency,
                updated_by=updated_by
            )

        except Exception as e:
            logger.error(f"[SPLIT] Error processing split: {str(e)}")
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
        updated_by: str
    ) -> bool:
        """Create a new position version for position adjustment CAs (BONUS, SPLIT)."""
        try:
            # Get current position
            current_position = self._get_current_position(portfolio_short_name, security_name)
            if not current_position:
                logger.warning(f"[POS_ADJ] No open position found for {portfolio_short_name}/{security_name}")
                return False

            position_id = current_position.get('position_id')
            old_version_id = current_position.get('version_id')
            current_price = Decimal(str(current_position.get('current_price', 0) or 0))

            # Get FX rate for LC calculations
            fx_rate = Decimal('1')
            if security_currency and portfolio_currency and security_currency != portfolio_currency:
                try:
                    fx_rate, _ = multicurrency_service.get_fx_rate(
                        security_currency, portfolio_currency, ex_date
                    )
                except Exception:
                    fx_rate = Decimal('1')

            # Calculate values
            market_value = (new_quantity * current_price).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
            market_value_lc = (market_value * fx_rate).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
            new_total_cost_lc = (new_total_cost * fx_rate).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
            new_avg_cost_lc = (new_avg_cost * fx_rate).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
            unrealized_pnl_fc = market_value - new_total_cost
            unrealized_pnl_lc = market_value_lc - new_total_cost_lc

            # Mark old version as not latest
            self._mark_old_version_not_latest(old_version_id)

            # Create new version
            timestamp = datetime.now()
            timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            new_version_id = int(timestamp.timestamp() * 1000)

            insert_sql = f"""
            UPSERT INTO {self.DATABASE}.{self.POSITION_TABLE} (
                version_id, position_id, position_date,
                portfolio_short_name, security_label,
                quantity, average_cost, total_cost,
                current_price, market_value, market_value_lc,
                realized_pnl, unrealized_pnl,
                realized_pnl_fc, unrealized_pnl_fc,
                realized_pnl_lc, unrealized_pnl_lc,
                trade_type,
                security_currency, portfolio_currency, fx_rate,
                average_cost_base, total_cost_base,
                status, is_active, is_latest,
                last_ca_id, last_ca_number, last_ca_type, last_ca_date,
                created_by, created_at, updated_by, updated_at
            ) VALUES (
                {new_version_id},
                {position_id},
                '{ex_date}',
                '{self._escape(portfolio_short_name)}',
                '{self._escape(security_name)}',
                {float(new_quantity)},
                {float(new_avg_cost)},
                {float(new_total_cost)},
                {float(current_price)},
                {float(market_value)},
                {float(market_value_lc)},
                0,
                {float(unrealized_pnl_fc)},
                0,
                {float(unrealized_pnl_fc)},
                0,
                {float(unrealized_pnl_lc)},
                'CA_{ca_type}',
                '{self._escape(security_currency or "")}',
                '{self._escape(portfolio_currency or "")}',
                {float(fx_rate)},
                {float(new_avg_cost_lc)},
                {float(new_total_cost_lc)},
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
                logger.info(f"[POS_ADJ] SUCCESS - Created new position version {new_version_id} "
                           f"for {ca_type}. New qty={new_quantity}, avg_cost={new_avg_cost}")
            else:
                logger.error(f"[POS_ADJ] FAILED - Could not create position version for {ca_type}")

            return success

        except Exception as e:
            logger.error(f"[POS_ADJ] Error creating position adjustment version: {str(e)}")
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
