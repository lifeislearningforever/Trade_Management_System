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

logger = logging.getLogger(__name__)


class CACashFlowService:
    """Service for generating cash flows from corporate actions"""

    DATABASE = 'gmp_cis'
    POSITION_TABLE = 'cis_trade_position'

    # CA types that generate cash flows
    CASH_FLOW_CA_TYPES = ['DIVIDEND', 'INTEREST', 'COUPON', 'CAPITAL_DISTRIBUTION']

    # CA type to Cash Flow type mapping
    CA_TO_CF_TYPE_MAP = {
        'DIVIDEND': 'DIVIDEND',
        'INTEREST': 'INTEREST',
        'COUPON': 'COUPON',
        'CAPITAL_DISTRIBUTION': 'CAPITAL_DISTRIBUTION',
    }

    @staticmethod
    def _escape(value: str) -> str:
        """Escape string for SQL."""
        if value is None:
            return ''
        return str(value).replace("'", "''")

    def queue_ca_for_processing(
        self,
        ca_id: int,
        ca_data: Dict[str, Any],
        username: str
    ) -> Tuple[bool, Optional[int]]:
        """
        Queue a corporate action for cash flow processing.

        Args:
            ca_id: Corporate Action ID
            ca_data: Corporate Action data dictionary
            username: User triggering the queue

        Returns:
            Tuple of (success, queue_id)
        """
        try:
            ca_type = ca_data.get('ca_type', '')

            # Only queue CA types that generate cash flows
            if ca_type not in self.CASH_FLOW_CA_TYPES:
                logger.info(f"CA type {ca_type} does not generate cash flows, skipping queue")
                return True, None

            queue_data = {
                'ca_id': ca_id,
                'ca_number': ca_data.get('ca_number'),
                'ca_type': ca_type,
                'security_name': ca_data.get('security_name'),
                'portfolio_name': ca_data.get('portfolio_name'),
                'ex_date': ca_data.get('ex_date'),
                'record_date': ca_data.get('record_date'),
                'payment_date': ca_data.get('payment_date'),
                'price': ca_data.get('price'),
                'currency': ca_data.get('currency'),
                'created_by': username,
            }

            success, queue_id = ca_cash_flow_queue_repository.insert(queue_data)

            if success:
                logger.info(f"Queued CA {ca_data.get('ca_number')} for cash flow processing")

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
        Process a queued CA and generate cash flows.

        Args:
            queue_id: Queue entry ID
            dry_run: If True, don't actually create cash flows

        Returns:
            Tuple of (success, message, cash_flows_created, total_amount)
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
            portfolio_name = queue_entry.get('portfolio_name')
            ex_date = queue_entry.get('ex_date')
            price = Decimal(str(queue_entry.get('price') or 0))
            currency = queue_entry.get('currency')
            ca_id = queue_entry.get('ca_id')
            ca_number = queue_entry.get('ca_number')
            payment_date = queue_entry.get('payment_date')
            record_date = queue_entry.get('record_date')

            if not price or price <= 0:
                error_msg = f"Invalid price ({price}) for CA {ca_number}"
                if not dry_run:
                    ca_cash_flow_queue_repository.mark_failed(queue_id, error_msg)
                return False, error_msg, 0, Decimal('0')

            # Get affected portfolios with their holdings
            holdings = self.get_holdings_for_ca(
                security_name=security_name,
                portfolio_name=portfolio_name,
                as_of_date=ex_date
            )

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

            for holding in holdings:
                portfolio_short_name = holding.get('portfolio_short_name')
                quantity = Decimal(str(holding.get('quantity') or 0))

                if quantity <= 0:
                    continue

                # Calculate cash flow amount: quantity × dividend price
                amount = (quantity * price).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

                if dry_run:
                    logger.info(f"[DRY RUN] Would create {ca_type} cash flow: "
                               f"Portfolio={portfolio_short_name}, Qty={quantity}, "
                               f"Price={price}, Amount={amount} {currency}")
                    cash_flows_created += 1
                    total_amount += amount
                    continue

                # Create cash flow
                success, cash_flow_id, error = self.create_cash_flow_from_ca(
                    ca_id=ca_id,
                    ca_number=ca_number,
                    ca_type=ca_type,
                    portfolio_short_name=portfolio_short_name,
                    security_name=security_name,
                    quantity=quantity,
                    amount=amount,
                    currency=currency,
                    ex_date=ex_date,
                    record_date=record_date,
                    payment_date=payment_date,
                    created_by=queue_entry.get('created_by', 'system')
                )

                # Log the result
                log_data = {
                    'queue_id': queue_id,
                    'ca_id': ca_id,
                    'cash_flow_id': cash_flow_id,
                    'portfolio_short_name': portfolio_short_name,
                    'security_name': security_name,
                    'quantity': quantity,
                    'amount': amount,
                    'currency': currency,
                    'status': 'SUCCESS' if success else 'FAILED',
                    'error_message': error if not success else None
                }
                ca_cash_flow_queue_repository.insert_log(log_data)

                if success:
                    cash_flows_created += 1
                    total_amount += amount
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
        portfolio_name: str = None,
        as_of_date: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get portfolio holdings for a security as of a specific date.

        Args:
            security_name: Security name (comma-separated if multiple)
            portfolio_name: Portfolio name filter (comma-separated if multiple, None for all)
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
            query = f"""
            SELECT
                p.portfolio_short_name,
                p.security_label,
                p.quantity,
                p.average_cost,
                p.security_currency
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
            WHERE p.quantity > 0
              AND p.status = 'OPEN'
              AND p.is_active = true
            """

            # Filter by specific portfolios if provided
            if portfolio_name:
                portfolios = [pf.strip() for pf in portfolio_name.split(',') if pf.strip()]
                if portfolios:
                    portfolio_conditions = " OR ".join([
                        f"p.portfolio_short_name = '{self._escape(pf)}'" for pf in portfolios
                    ])
                    query += f" AND ({portfolio_conditions})"

            query += " ORDER BY p.portfolio_short_name, p.security_label"

            results = impala_manager.execute_query(query, database=self.DATABASE)
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
        amount: Decimal,
        currency: str,
        ex_date: str,
        record_date: str,
        payment_date: str,
        created_by: str
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Create a cash flow entry from a corporate action.

        Args:
            ca_id: Corporate Action ID
            ca_number: CA number
            ca_type: CA type (DIVIDEND, INTEREST, etc.)
            portfolio_short_name: Portfolio short name
            security_name: Security name
            quantity: Quantity held
            amount: Calculated amount
            currency: Currency code
            ex_date: Ex-dividend date
            record_date: Record date
            payment_date: Payment date
            created_by: User creating the cash flow

        Returns:
            Tuple of (success, cash_flow_id, error_message)
        """
        try:
            # Generate CF number
            timestamp = datetime.now()
            cf_number = f"CF-{timestamp.strftime('%Y%m%d')}-{int(timestamp.timestamp() * 1000) % 100000:05d}"

            # Map CA type to cash flow type
            cf_type = self.CA_TO_CF_TYPE_MAP.get(ca_type, ca_type)

            # Map to actual cis_cash_flow table field names
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
                'local_ccy': currency,
                'local_ccy_amt': float(amount),
                'flow_amount_local': float(amount),
                'foreign_ccy': currency,
                'foreign_ccy_amt': float(amount),
                'dividend_price': float(quantity),  # Store quantity as reference
                'status': 'INITIAL',
                'src_system': 'CIS',
            }

            logger.info(f"Creating cash flow with data: security_label={security_name}, "
                       f"portfolio={portfolio_short_name}, cf_number={cf_number}")

            # Use cash flow repository to insert
            success, cash_flow_id = CashFlowRepository.insert(cf_data, created_by)

            if success:
                logger.info(f"Created cash flow {cf_number} from CA {ca_number} "
                           f"for portfolio {portfolio_short_name}, amount: {amount} {currency}")
                return True, cash_flow_id, None
            else:
                return False, None, "Failed to insert cash flow"

        except Exception as e:
            error_msg = f"Error creating cash flow from CA: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg

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

            for entry in pending:
                queue_id = entry.get('queue_id')
                ca_number = entry.get('ca_number')

                logger.info(f"Processing CA {ca_number} (queue_id: {queue_id})")

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
