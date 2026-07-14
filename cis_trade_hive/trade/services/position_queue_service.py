"""
Position Queue Service - Async Background Processing for AVP

Phase 3: Async background processing with:
- Queue-based position calculation (decouple from trade save)
- Background worker with retry logic
- SLA: < 5 minutes from trade save to position update
- Error handling and dead letter queue

Based on SA Team Questionnaire Feedback (2026-03-04).
"""

import logging
import threading
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
import uuid

from core.repositories.impala_connection import impala_manager
from core.services.system_date_service import system_date_service
from trade.services.position_service import position_service, PositionService
from core.notifications import notify_user, notify_admins
from core.notifications.constants import (
    EVT_AVP_PROCESSING, EVT_AVP_COMPLETED, EVT_AVP_FAILED,
    EVT_AVP_DEAD_LETTER, EVT_AVP_SLA_BREACH,
)

logger = logging.getLogger(__name__)


class PositionQueueService:
    """
    Async queue service for position calculation.

    Features:
    - Decouples position calculation from trade save
    - Background worker processes queue
    - Retry logic for failed items (max 3 retries)
    - SLA monitoring (< 5 minutes)
    - Dead letter queue for permanent failures
    """

    DATABASE = 'gmp_cis'
    QUEUE_TABLE = 'cis_position_queue'

    # Queue status
    STATUS_PENDING = 'PENDING'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'
    STATUS_DEAD_LETTER = 'DEAD_LETTER'

    # Configuration
    MAX_RETRIES = 3
    BATCH_SIZE = 100
    POLL_INTERVAL = 10  # seconds
    SLA_SECONDS = 300  # 5 minutes

    def __init__(self, position_svc: PositionService = None):
        """Initialize queue service."""
        self.position_service = position_svc or position_service
        self._worker_running = False
        self._worker_thread = None
        self._in_memory_queue = Queue()
        self._executor = ThreadPoolExecutor(max_workers=4)

    # =========================================================================
    # QUEUE PRODUCER (Called by Trade Service)
    # =========================================================================

    def enqueue_position_calculation(
        self,
        trade_id: int,
        portfolio_id: str,
        security_id: str,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        settle_date: str,
        queued_by: str,
        security_currency: str = None,
        portfolio_currency: str = None,
        isin: str = None,
        security_name: str = None,
        use_db_queue: bool = True,
        chain_recalc_metadata: str = None,
        position_basis: str = 'TRADED',
        position_date: str = None,
        deal_number: str = '',
        gross_amount_lc: Decimal = None,
        total_amount_lc: Decimal = None,
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Add trade to position calculation queue.

        Args:
            trade_id: Trade ID
            portfolio_id: Portfolio short name
            security_id: Security label
            trade_type: BUY or SELL
            quantity: Trade quantity
            price: Trade price
            charges: Total charges
            settle_date: Settlement date
            queued_by: User who queued
            use_db_queue: If True, persist to database. If False, use in-memory queue.

        Returns:
            Tuple of (success, message, queue_id)
        """
        try:
            queue_id = self._generate_id()
            timestamp = datetime.now()

            # position_date: the actual date for this position record.
            # For TRADED basis: position_date = trade_date (passed by caller)
            # For SETTLED basis: position_date = settle_date (default)
            effective_position_date = position_date or settle_date

            # Encode LC amounts into error_message field (STRING column reused for metadata).
            # Format: "LC:<gross_lc>:<total_lc>" or prepend to CHAIN_RECALC string.
            lc_meta = None
            if gross_amount_lc is not None or total_amount_lc is not None:
                _glc = float(gross_amount_lc) if gross_amount_lc else 0
                _tlc = float(total_amount_lc) if total_amount_lc else 0
                lc_meta = f"LC:{_glc}:{_tlc}"

            if chain_recalc_metadata and lc_meta:
                effective_error_message = f"{lc_meta}|{chain_recalc_metadata}"
            elif lc_meta:
                effective_error_message = lc_meta
            else:
                effective_error_message = chain_recalc_metadata

            queue_item = {
                'queue_id': queue_id,
                'trade_id': trade_id,
                'deal_number': deal_number,
                'portfolio_id': portfolio_id,
                'security_id': security_id,
                'trade_type': trade_type,
                'quantity': float(quantity),
                'price': float(price),
                'charges': float(charges),
                'settle_date': settle_date,
                'position_date': effective_position_date,
                'position_basis': position_basis,
                'security_currency': security_currency,
                'portfolio_currency': portfolio_currency,
                'isin': isin,
                'security_name': security_name,
                'status': self.STATUS_PENDING,
                'retry_count': 0,
                'queued_at': timestamp,
                'queued_by': queued_by,
                'error_message': effective_error_message,
                # In-memory LC amounts (available immediately to worker)
                'gross_amount_lc': gross_amount_lc,
                'total_amount_lc': total_amount_lc,
            }

            if use_db_queue:
                # Persist to database queue
                success = self._insert_queue_item(queue_item)
            else:
                # Use in-memory queue (faster, but not persistent)
                self._in_memory_queue.put(queue_item)
                success = True

            if success:
                logger.info(f"Enqueued position calculation for trade {trade_id} (queue_id={queue_id})")
                return True, f"Position calculation queued (ID: {queue_id})", queue_id
            else:
                return False, "Failed to enqueue position calculation", None

        except Exception as e:
            logger.error(f"Error enqueueing position calculation: {str(e)}")
            return False, f"Queue error: {str(e)}", None

    def _insert_queue_item(self, item: Dict[str, Any]) -> bool:
        """Insert queue item into database."""
        try:
            timestamp = item['queued_at'].strftime('%Y-%m-%d %H:%M:%S')
            processing_date = item['queued_at'].strftime('%Y%m%d')

            # Cast decimal values to avoid precision errors
            quantity = f"CAST({item['quantity']} AS DECIMAL(20,8))"
            price = f"CAST({item['price']} AS DECIMAL(20,8))"
            charges = f"CAST({item['charges']} AS DECIMAL(20,8))"

            # Include error_message for CHAIN_RECALC metadata (for backdated trades)
            error_message = item.get('error_message')
            error_message_sql = f"'{self._escape(error_message)}'" if error_message else 'NULL'

            position_basis = item.get('position_basis', 'TRADED')
            position_date = item.get('position_date') or item['settle_date']

            query = f"""
            INSERT INTO {self.DATABASE}.{self.QUEUE_TABLE}
            (queue_id, trade_id, portfolio_id, security_id, trade_type,
             quantity, price, charges, settle_date, position_date, position_basis,
             security_currency, portfolio_currency, isin, security_name,
             status, retry_count, queued_at, queued_by, processing_date, error_message)
            VALUES (
                {item['queue_id']}, {item['trade_id']},
                '{self._escape(item['portfolio_id'])}',
                '{self._escape(item['security_id'])}',
                '{item['trade_type']}',
                {quantity}, {price}, {charges},
                '{item['settle_date']}',
                '{position_date}',
                '{position_basis}',
                {self._null_or_str(item.get('security_currency'))},
                {self._null_or_str(item.get('portfolio_currency'))},
                {self._null_or_str(item.get('isin'))},
                {self._null_or_str(item.get('security_name'))},
                '{self.STATUS_PENDING}', CAST(0 AS INT),
                '{timestamp}', '{self._escape(item['queued_by'])}',
                '{processing_date}', {error_message_sql}
            )
            """

            return impala_manager.execute_write(query, database=self.DATABASE)

        except Exception as e:
            logger.error(f"Error inserting queue item: {str(e)}")
            return False

    # =========================================================================
    # QUEUE CONSUMER (Background Worker)
    # =========================================================================

    def start_worker(self):
        """Start the background worker thread."""
        if self._worker_running:
            logger.warning("Worker is already running")
            return

        self._worker_running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.info("Position queue worker started")

    def stop_worker(self):
        """Stop the background worker thread."""
        self._worker_running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=30)
        logger.info("Position queue worker stopped")

    def _worker_loop(self):
        """Main worker loop - continuously process queue items."""
        logger.info("Worker loop started")

        while self._worker_running:
            try:
                # Process database queue
                processed = self._process_batch()

                # Process in-memory queue
                self._process_in_memory_queue()

                # Sleep if no items were processed
                if processed == 0:
                    time.sleep(self.POLL_INTERVAL)

            except Exception as e:
                logger.error(f"Error in worker loop: {str(e)}")
                time.sleep(self.POLL_INTERVAL)

    def _process_batch(self) -> int:
        """Process a batch of pending items from database queue."""
        try:
            pending = self.get_pending_items(limit=self.BATCH_SIZE)

            if not pending:
                return 0

            logger.info(f"Processing batch of {len(pending)} items")

            for item in pending:
                self._process_item(item)

            return len(pending)

        except Exception as e:
            logger.error(f"Error processing batch: {str(e)}")
            return 0

    def _process_in_memory_queue(self):
        """Process items from in-memory queue."""
        processed = 0
        while not self._in_memory_queue.empty() and processed < self.BATCH_SIZE:
            try:
                item = self._in_memory_queue.get_nowait()
                self._process_item(item, is_db_queue=False)
                processed += 1
            except Empty:
                break
            except Exception as e:
                logger.error(f"Error processing in-memory item: {str(e)}")

    def _process_item(self, item: Dict[str, Any], is_db_queue: bool = True):
        """Process a single queue item."""
        queue_id = item.get('queue_id')
        trade_id = item.get('trade_id')

        try:
            # Mark as processing
            if is_db_queue:
                self._update_status(queue_id, self.STATUS_PROCESSING)

            queued_by = item.get('queued_by', '')
            deal_number = item.get('deal_number') or str(trade_id)
            _notif_base = {
                'queue_id':    queue_id,
                'trade_id':    trade_id,
                'deal_number': deal_number,
                'portfolio':   item.get('portfolio_id', ''),
                'security':    item.get('security_name') or item.get('security_id', ''),
                'isin':        item.get('isin', ''),
                'position_basis': item.get('position_basis', 'TRADED'),
            }

            # Notify user: AVP processing started
            notify_user(queued_by, EVT_AVP_PROCESSING, {
                **_notif_base,
                'message': f'AVP calculation started for trade {deal_number}',
            })

            # Check SLA
            queued_at = item.get('queued_at')
            elapsed = 0
            if queued_at:
                if isinstance(queued_at, str):
                    queued_at = datetime.strptime(queued_at, '%Y-%m-%d %H:%M:%S')
                elapsed = (datetime.now() - queued_at).total_seconds()
                if elapsed > self.SLA_SECONDS:
                    logger.warning(
                        f"SLA breach for queue_id={queue_id}: {elapsed:.0f}s > {self.SLA_SECONDS}s"
                    )
                    notify_user(queued_by, EVT_AVP_SLA_BREACH, {
                        **_notif_base,
                        'elapsed_seconds': int(elapsed),
                        'sla_seconds': self.SLA_SECONDS,
                        'message': f'AVP SLA breach: trade {deal_number} waiting {int(elapsed)}s (SLA={self.SLA_SECONDS}s)',
                    })
                    notify_admins(EVT_AVP_SLA_BREACH, {
                        **_notif_base,
                        'queued_by': queued_by,
                        'elapsed_seconds': int(elapsed),
                        'sla_seconds': self.SLA_SECONDS,
                        'message': f'AVP SLA breach: queue_id={queue_id} trade={deal_number} user={queued_by} elapsed={int(elapsed)}s',
                    })

            # Check if this is a backdated trade requiring chain recalculation
            # error_message field may contain:
            # 1. CHAIN_RECALC metadata (original)
            # 2. Error message from previous retry (check for embedded CHAIN_RECALC)
            # 3. Combined: "Previous error. CHAIN_RECALC:..." or "Max retries exceeded. Last error: ..."
            error_message = item.get('error_message', '') or ''
            logger.info(f"Processing queue item: trade_id={trade_id}, error_message='{error_message}'")
            # Strip LC prefix before parsing CHAIN_RECALC metadata
            _chain_part = error_message
            if error_message.startswith('LC:') and '|' in error_message:
                _chain_part = error_message.split('|', 1)[1]
            chain_recalc_info = self._parse_chain_recalc_metadata(_chain_part)

            # For BACKDATED trades: Skip individual calculation, let chain recalculation handle ALL trades
            # This avoids the issue of creating a position that gets immediately deleted
            if chain_recalc_info:
                logger.info(f"Parsed chain_recalc_info: {chain_recalc_info}")
                logger.info(
                    f"Backdated trade detected for queue_id={queue_id}, trade_id={trade_id}. "
                    f"Using chain recalculation from {chain_recalc_info['from_date']}"
                )

                # Deduplication: if another queue item with the same CHAIN_RECALC signature
                # has already completed, skip re-running the full recalc — it would pre-invalidate
                # positions the first run just wrote, leaving orphaned false rows.
                chain_sig = f"CHAIN_RECALC:{chain_recalc_info['portfolio_id']}:{chain_recalc_info['security_id']}:{chain_recalc_info['from_date']}"
                try:
                    already_done = impala_manager.execute_query(
                        f"""
                        SELECT 1 FROM {self.DATABASE}.{self.QUEUE_TABLE}
                        WHERE error_message LIKE '{chain_sig}%'
                          AND status = '{self.STATUS_COMPLETED}'
                          AND queue_id != {queue_id}
                        LIMIT 1
                        """,
                        database=self.DATABASE
                    )
                    if already_done:
                        logger.info(
                            f"Chain recalc for {chain_sig} already completed by another "
                            f"queue item — marking queue_id={queue_id} as COMPLETED (dedup)."
                        )
                        if is_db_queue:
                            self._update_status(queue_id, self.STATUS_COMPLETED)
                        return
                except Exception as e:
                    logger.warning(f"Could not check for duplicate chain recalc: {e}")

                recalc_result = self._process_chain_recalculation(chain_recalc_info)

                # Check for errors first
                if recalc_result['errors'] > 0:
                    self._handle_failure(
                        item,
                        f"Chain recalculation had {recalc_result['errors']} errors",
                        is_db_queue
                    )
                    return

                # Check if any positions were actually recalculated
                if recalc_result['recalculated'] == 0:
                    # No trades found - this is an error condition
                    self._handle_failure(
                        item,
                        f"No trades found for chain recalculation from {chain_recalc_info['from_date']}. "
                        f"Portfolio={chain_recalc_info['portfolio_id']}, Security={chain_recalc_info['security_id']}",
                        is_db_queue
                    )
                    return

                # Success - positions were recalculated
                if is_db_queue:
                    self._update_status(queue_id, self.STATUS_COMPLETED)
                logger.info(
                    f"Successfully processed backdated trade queue_id={queue_id}, "
                    f"recalculated {recalc_result['recalculated']} positions"
                )
                notify_user(queued_by, EVT_AVP_COMPLETED, {
                    **_notif_base,
                    'recalculated': recalc_result['recalculated'],
                    'elapsed_seconds': int(elapsed),
                    'message': (
                        f'AVP complete (backdated): {recalc_result["recalculated"]} position(s) '
                        f'recalculated for trade {deal_number}'
                    ),
                })
                return

            # For T+0 / TRADED basis: Calculate position directly
            # position_date comes from queue (trade_date for TRADED basis,
            # settle_date for SETTLED basis)
            position_basis = item.get('position_basis', 'TRADED')
            position_date = item.get('position_date') or item['settle_date']

            # LC amounts: read from queue item (in-memory path) or parse from error_message
            # (DB path). Fall back to fetching from cis_trade only if both are missing.
            _gross_amount_lc = item.get('gross_amount_lc')
            _trade_lc = item.get('total_amount_lc')

            if _gross_amount_lc is None and _trade_lc is None:
                # Try to parse from error_message: "LC:<gross>:<total>" or "LC:<gross>:<total>|CHAIN_RECALC:..."
                _err_msg = item.get('error_message') or ''
                if _err_msg.startswith('LC:'):
                    try:
                        _lc_part = _err_msg.split('|')[0]  # strip any trailing CHAIN_RECALC
                        _, _glc_str, _tlc_str = _lc_part.split(':')
                        _gross_amount_lc = Decimal(_glc_str) if float(_glc_str) != 0 else None
                        _trade_lc = Decimal(_tlc_str) if float(_tlc_str) != 0 else None
                    except Exception as _parse_ex:
                        logger.warning(f"Could not parse LC from error_message '{_err_msg}': {_parse_ex}")

            if _gross_amount_lc is None and _trade_lc is None:
                # Last resort: fetch from cis_trade (may have race condition on new trades)
                try:
                    _trade_row = impala_manager.execute_query(
                        f"SELECT total_amount_lc, gross_amount_lc "
                        f"FROM {self.DATABASE}.cis_trade "
                        f"WHERE trade_id = {trade_id} LIMIT 1",
                        database=self.DATABASE,
                    )
                    if _trade_row:
                        _raw_tlc = _trade_row[0].get('total_amount_lc')
                        _raw_glc = _trade_row[0].get('gross_amount_lc')
                        _trade_lc = Decimal(str(_raw_tlc)) if _raw_tlc else None
                        _gross_amount_lc = Decimal(str(_raw_glc)) if _raw_glc else None
                except Exception as _lc_ex:
                    logger.warning(f"Could not fetch LC amounts for trade {trade_id}: {_lc_ex}")

            success, message, position = self.position_service.calculate_position(
                portfolio_id=item['portfolio_id'],
                security_id=item['security_id'],
                trade_type=item['trade_type'],
                quantity=Decimal(str(item['quantity'])),
                price=Decimal(str(item['price'])),
                charges=Decimal(str(item.get('charges', 0) or 0)),
                position_date=position_date,
                trade_id=trade_id,
                updated_by='SYSTEM',
                security_currency=item.get('security_currency'),
                portfolio_currency=item.get('portfolio_currency'),
                isin=item.get('isin'),
                security_name=item.get('security_name'),
                position_basis=position_basis,
                trade_lc=_trade_lc,
                gross_amount_lc=_gross_amount_lc,
            )

            if success:
                if is_db_queue:
                    self._update_status(queue_id, self.STATUS_COMPLETED)
                logger.info(f"Successfully processed queue_id={queue_id}, trade_id={trade_id}")
                notify_user(queued_by, EVT_AVP_COMPLETED, {
                    **_notif_base,
                    'elapsed_seconds': int(elapsed),
                    'message': f'AVP calculation complete for trade {deal_number}',
                })
            else:
                self._handle_failure(item, message, is_db_queue)

        except Exception as e:
            logger.error(f"Error processing queue_id={queue_id}: {str(e)}")
            self._handle_failure(item, str(e), is_db_queue)

    def _parse_chain_recalc_metadata(self, metadata: str) -> Optional[Dict[str, str]]:
        """
        Parse chain recalculation metadata from error_message field.
        Supports two formats:
        - Colon format: CHAIN_RECALC:portfolio_id:security_id:from_date
        - Space format: CHAIN_RECALC portfolio_id security_id from_date
        """
        if not metadata or not metadata.startswith('CHAIN_RECALC'):
            return None

        try:
            # Try colon format first (preferred)
            if metadata.startswith('CHAIN_RECALC:'):
                parts = metadata.split(':')
                if len(parts) >= 4:
                    return {
                        'portfolio_id': parts[1],
                        'security_id': parts[2],
                        'from_date': parts[3]
                    }

            # Try space format (legacy/alternate)
            # Format: CHAIN_RECALC portfolio_id security_id from_date
            parts = metadata.split()
            if len(parts) >= 4 and parts[0] == 'CHAIN_RECALC':
                return {
                    'portfolio_id': parts[1],
                    'security_id': parts[2],
                    'from_date': parts[3]
                }

            logger.warning(f"Could not parse CHAIN_RECALC metadata: {metadata}")
        except Exception as e:
            logger.error(f"Error parsing CHAIN_RECALC metadata '{metadata}': {e}")

        return None

    def _process_chain_recalculation(self, chain_info: Dict[str, str]) -> Dict[str, int]:
        """
        Recalculate position chain for backdated trades.

        This handles the scenario where a user enters a backdated trade that affects
        subsequent positions. For example:
        - T1 entered on 5th March (settle 5th March) - Position: qty=100, avg=130
        - T3 entered on 5th March (settle 3rd March - BACKDATED) - Must recalculate T1

        Steps:
        1. Get position BEFORE the backdated date (base position)
        2. Get ALL trades from backdated date onwards (including the backdated trade)
        3. Delete existing position versions from backdated date onwards
        4. Recalculate all positions in chronological order
        """
        counters = {'recalculated': 0, 'errors': 0, 'deleted': 0}

        try:
            portfolio_id = chain_info['portfolio_id']
            security_id = chain_info['security_id']
            from_date_raw = chain_info['from_date']
            today = system_date_service.get_system_date()

            # Normalize from_date to YYYY-MM-DD format
            # Handle various formats: YYYY-MM-DD, YYYYMMDD, or datetime string
            from_date = from_date_raw
            if len(from_date_raw) == 8 and from_date_raw.isdigit():
                # YYYYMMDD format
                from_date = f"{from_date_raw[:4]}-{from_date_raw[4:6]}-{from_date_raw[6:8]}"
            elif 'T' in from_date_raw:
                # ISO format with time
                from_date = from_date_raw.split('T')[0]
            # Else assume already YYYY-MM-DD

            logger.info(
                f"Chain recalc: from_date_raw='{from_date_raw}', normalized='{from_date}'"
            )

            logger.info(
                f"Starting chain recalculation for {portfolio_id}/{security_id} "
                f"from {from_date} to {today}"
            )

            # VERSION-BASED APPROACH: No deletes, create new versions
            # The position_service._save_position() method will:
            # 1. Mark existing versions for each date as is_latest=false
            # 2. Insert new version with is_latest=true
            # This maintains full audit trail

            # Step 1: Get ALL trades from backdated date onwards (>= not >)
            # This INCLUDES the backdated trade itself
            # Note: security_currency, portfolio_currency, isin, etc. are NOT in cis_trade table
            today_str = today.strftime("%Y-%m-%d")
            query = f"""
            SELECT trade_id, trade_type, quantity, price,
                   COALESCE(commission, 0) + COALESCE(sec_fee, 0) + COALESCE(other_charges, 0) as charges,
                   trade_date, settle_date
            FROM {self.DATABASE}.cis_trade
            WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
              AND security_label = '{self._escape(security_id)}'
              AND (trade_date >= '{from_date}' OR settle_date >= '{from_date}')
              AND settle_date <= '{today_str}'
              AND (trade_status IN ('INITIAL', 'MODIFIED', 'VALIDATED', 'SETTLED') OR status IN ('INITIAL', 'MODIFIED', 'VALIDATED', 'SETTLED'))
              AND (is_deleted = false OR is_deleted IS NULL)
            ORDER BY trade_date ASC, settle_date ASC, trade_id ASC
            """

            logger.info(
                f"Chain recalc query: portfolio={portfolio_id}, security={security_id}, "
                f"from_date={from_date}, to_date={today_str}"
            )
            logger.info(f"CHAIN_RECALC QUERY: {query}")

            trades = impala_manager.execute_query(query, database=self.DATABASE)
            logger.info(f"Found {len(trades) if trades else 0} trades for chain recalculation")

            if trades:
                for t in trades:
                    logger.info(f"  Trade found: id={t.get('trade_id')}, settle_date={t.get('settle_date')}, type={t.get('trade_type')}")

            if trades:
                logger.info(f"Recalculating {len(trades)} trades (both bases) from {from_date} to {today}")

                # Pre-invalidate all existing positions from from_date onwards (both bases).
                # Direct queue items may have already written positions for these dates; if the
                # chain recalc loop picks them up as base positions via DB read it will
                # double-count. Setting is_latest=false first means the loop's in-memory
                # base_position_override is the only authoritative source within this run.
                #
                # Wait 2s for Kudu to propagate writes from direct queue items that ran
                # just before this chain recalc — without this the SELECT below may miss
                # rows on a different pooled connection (stale read window).
                time.sleep(2)
                invalidate_query = f"""
                SELECT version_id, position_id, position_date, position_basis,
                       portfolio_short_name, security_label,
                       quantity, average_cost_fc, total_cost_fc,
                       average_cost_lc, total_cost_lc,
                       realized_pnl_fc, unrealized_pnl_fc,
                       realized_pnl_lc, unrealized_pnl_lc,
                       market_price, market_value_fc, market_value_lc,
                       dividend_fc, dividend_lc, provision_fc, provision_lc,
                       trade_id, trade_type, lots_held, custodian, sub_custodian,
                       security_currency, portfolio_currency, fx_rate,
                       status, is_active, created_by, created_at, updated_by, updated_at
                FROM {self.DATABASE}.{self.position_service.POSITION_TABLE}
                WHERE portfolio_short_name = '{self.position_service._escape(portfolio_id)}'
                  AND security_label = '{self.position_service._escape(security_id)}'
                  AND (position_date >= '{from_date}')
                  AND (is_latest = true OR is_latest IS NULL)
                """
                stale_rows = impala_manager.execute_query(invalidate_query, database=self.DATABASE)
                if stale_rows:
                    logger.info(f"Pre-invalidating {len(stale_rows)} stale position row(s) before chain recalc")
                    pos_table = self.position_service.POSITION_TABLE
                    esc = self.position_service._escape
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    for stale in stale_rows:
                        # Direct UPSERT by version_id — avoids a second DB read that may miss
                        # rows not yet visible on the connection pool.
                        def _cd(val):
                            try:
                                return f"CAST({float(val)} AS DECIMAL(30,8))"
                            except (TypeError, ValueError):
                                return 'NULL'
                        upsert_q = f"""
                        UPSERT INTO {self.DATABASE}.{pos_table}
                        (version_id, position_id, position_date, position_basis,
                         portfolio_short_name, security_label,
                         quantity, average_cost_fc, total_cost_fc,
                         average_cost_lc, total_cost_lc,
                         realized_pnl_fc, unrealized_pnl_fc,
                         realized_pnl_lc, unrealized_pnl_lc,
                         market_price, market_value_fc, market_value_lc,
                         dividend_fc, dividend_lc, provision_fc, provision_lc,
                         trade_id, trade_type, lots_held, custodian, sub_custodian,
                         security_currency, portfolio_currency, fx_rate,
                         status, is_active, is_latest,
                         created_by, created_at, updated_by, updated_at)
                        VALUES (
                            {stale['version_id']}, {stale['position_id']},
                            '{stale['position_date']}', '{stale['position_basis']}',
                            '{esc(stale['portfolio_short_name'])}', '{esc(stale['security_label'])}',
                            {_cd(stale.get('quantity'))},
                            {_cd(stale.get('average_cost_fc'))}, {_cd(stale.get('total_cost_fc'))},
                            {_cd(stale.get('average_cost_lc'))}, {_cd(stale.get('total_cost_lc'))},
                            {_cd(stale.get('realized_pnl_fc'))}, {_cd(stale.get('unrealized_pnl_fc'))},
                            {_cd(stale.get('realized_pnl_lc'))}, {_cd(stale.get('unrealized_pnl_lc'))},
                            {_cd(stale.get('market_price'))}, {_cd(stale.get('market_value_fc'))},
                            {_cd(stale.get('market_value_lc'))},
                            {_cd(stale.get('dividend_fc'))}, {_cd(stale.get('dividend_lc'))},
                            {_cd(stale.get('provision_fc'))}, {_cd(stale.get('provision_lc'))},
                            {stale['trade_id'] if stale.get('trade_id') else 'NULL'},
                            '{stale.get('trade_type', '')}',
                            {stale['lots_held'] if stale.get('lots_held') else 'NULL'},
                            {f"'{esc(stale['custodian'])}'" if stale.get('custodian') else 'NULL'},
                            {f"'{esc(stale['sub_custodian'])}'" if stale.get('sub_custodian') else 'NULL'},
                            {f"'{esc(stale['security_currency'])}'" if stale.get('security_currency') else 'NULL'},
                            {f"'{esc(stale['portfolio_currency'])}'" if stale.get('portfolio_currency') else 'NULL'},
                            {_cd(stale['fx_rate']) if stale.get('fx_rate') else 'NULL'},
                            '{stale.get('status', 'OPEN')}',
                            {str(stale.get('is_active', True)).lower()},
                            false,
                            '{esc(stale.get('created_by', ''))}',
                            '{stale.get('created_at', timestamp)}',
                            'SYSTEM', '{timestamp}'
                        )
                        """
                        impala_manager.execute_write(upsert_q, database=self.DATABASE)
                        logger.info(f"Pre-invalidated version_id={stale['version_id']} basis={stale['position_basis']} date={stale['position_date']}")

                last_trade_date_by_basis = {}
                # In-memory position state per basis — avoids Kudu stale-read between
                # consecutive writes in the same chain recalc loop.
                # Sentinel: {} means "start from zero" (first trade for this basis).
                # None means "not set yet — look up from DB" (used outside chain recalc).
                # We initialise to {} so the first trade always starts clean without a DB read.
                last_position_by_basis = {'TRADED': {}, 'SETTLED': {}}

                for trade in trades:
                    settle_date = trade.get('settle_date') or ''
                    trade_date  = trade.get('trade_date')  or settle_date

                    # Recalculate BOTH position bases per trade so each chain stays correct.
                    # TRADED basis uses trade_date as position_date.
                    # SETTLED basis uses settle_date as position_date.
                    # Skip a basis if its position_date is empty (data integrity guard).
                    for basis, pos_date in [
                        ('TRADED',  trade_date),
                        ('SETTLED', settle_date),
                    ]:
                        if not pos_date:
                            logger.warning(
                                f"Skipping basis={basis} for trade {trade.get('trade_id')}: "
                                f"pos_date is empty (trade_date={trade_date!r}, settle_date={settle_date!r})"
                            )
                            continue
                        try:
                            _raw_glc = trade.get('gross_amount_lc')
                            _glc = Decimal(str(_raw_glc)) if _raw_glc else None
                            _raw_tlc = trade.get('total_amount_lc')
                            _tlc = Decimal(str(_raw_tlc)) if _raw_tlc else None
                            success, msg, result = self.position_service.calculate_position(
                                portfolio_id=portfolio_id,
                                security_id=security_id,
                                trade_type=trade['trade_type'],
                                quantity=Decimal(str(trade['quantity'])),
                                price=Decimal(str(trade['price'])),
                                charges=Decimal(str(trade.get('charges', 0) or 0)),
                                position_date=pos_date,
                                trade_id=trade['trade_id'],
                                updated_by='SYSTEM',
                                security_currency=trade.get('security_currency'),
                                portfolio_currency=trade.get('portfolio_currency'),
                                isin=trade.get('isin'),
                                security_name=trade.get('security_name'),
                                custodian=trade.get('custodian'),
                                sub_custodian=trade.get('sub_custodian'),
                                is_chain_recalc=True,
                                position_basis=basis,
                                base_position_override=last_position_by_basis.get(basis),
                                trade_lc=_tlc,
                                gross_amount_lc=_glc,
                            )

                            if success:
                                counters['recalculated'] += 1
                                logger.info(
                                    f"Recalculated trade {trade['trade_id']} "
                                    f"basis={basis} date={pos_date}"
                                )
                                # Keep in-memory state so next iteration doesn't need a DB read
                                if result:
                                    last_position_by_basis[basis] = result
                                # Track the latest trade date processed per basis
                                if pos_date > last_trade_date_by_basis.get(basis, ''):
                                    last_trade_date_by_basis[basis] = pos_date
                            else:
                                counters['errors'] += 1
                                logger.error(
                                    f"Failed to recalculate trade {trade['trade_id']} "
                                    f"basis={basis}: {msg}"
                                )

                        except Exception as e:
                            logger.error(
                                f"Error recalculating trade {trade['trade_id']} basis={basis}: {str(e)}"
                            )
                            counters['errors'] += 1

                # After replaying all trades, carry the running position forward to every
                # business date between the last trade date and today so that each day
                # has an INT row (not just days with actual trades).
                self._carry_forward_to_today(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    last_trade_date_by_basis=last_trade_date_by_basis,
                    today_str=today_str,
                    counters=counters,
                )
            else:
                logger.warning(f"No trades found for recalculation from {from_date}")

            logger.info(
                f"Chain recalculation complete: {counters['recalculated']} recalculated, "
                f"{counters['errors']} errors"
            )
            return counters

        except Exception as e:
            logger.error(f"Error in chain recalculation: {str(e)}")
            return counters

    def _get_business_dates_between(self, from_date: str, to_date: str) -> List[str]:
        """
        Return all business dates (YYYY-MM-DD) from from_date (exclusive) to to_date (inclusive)
        by querying gmp_cis_sta_dly_alldatesinfo which only contains business days.
        Falls back to calendar days if the table is unavailable.
        """
        try:
            query = f"""
            SELECT DISTINCT CAST(contextual_today AS STRING) AS biz_date
            FROM gmp_cis.gmp_cis_sta_dly_alldatesinfo
            WHERE src_system = 'gmp'
              AND sub_system = 'cis'
              AND data_frq   = 'dly'
              AND record_type = 'D'
              AND CAST(contextual_today AS STRING) > '{from_date}'
              AND CAST(contextual_today AS STRING) <= '{to_date}'
            ORDER BY biz_date ASC
            """
            rows = impala_manager.execute_query(query, database='gmp_cis')
            if rows:
                return [r['biz_date'] for r in rows if r.get('biz_date')]
        except Exception as e:
            logger.warning(f"Could not fetch business dates from alldatesinfo: {e}. Falling back to calendar days.")

        # Fallback: every calendar day (excluding weekends)
        from datetime import date as _date, timedelta
        result = []
        cur = _date.fromisoformat(from_date) + timedelta(days=1)
        end = _date.fromisoformat(to_date)
        while cur <= end:
            if cur.weekday() < 5:  # Mon–Fri
                result.append(cur.isoformat())
            cur += timedelta(days=1)
        return result

    def _carry_forward_to_today(
        self,
        portfolio_id: str,
        security_id: str,
        last_trade_date_by_basis: Dict[str, str],
        today_str: str,
        counters: Dict[str, int],
    ) -> None:
        """
        For each position basis, carry the latest recalculated position forward to every
        business date between the last trade date and today, creating an INT row per date.
        This ensures every business date has an INT position record even on days with no trades.
        """
        for basis, last_trade_date in last_trade_date_by_basis.items():
            if last_trade_date >= today_str:
                continue  # already at today, nothing to carry forward

            fill_dates = self._get_business_dates_between(last_trade_date, today_str)
            if not fill_dates:
                continue

            # Get the running position after the last trade to carry forward
            running = self.position_service._get_position_as_of_date(
                portfolio_id=portfolio_id,
                security_id=security_id,
                as_of_date=last_trade_date,
                include_same_date=True,
                position_basis=basis,
            )
            if not running:
                logger.warning(
                    f"No position found at {last_trade_date} for {portfolio_id}/{security_id} "
                    f"basis={basis} — skipping carry-forward"
                )
                continue

            logger.info(
                f"Carrying forward {portfolio_id}/{security_id} basis={basis} "
                f"from {last_trade_date} to {today_str} over {len(fill_dates)} date(s)"
            )

            for fill_date in fill_dates:
                try:
                    carry = dict(running)
                    carry['position_date'] = fill_date
                    carry['position_type'] = 'INT'
                    carry['processing_timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    # Generate a new position_id/version_id so we don't collide
                    import time as _time
                    carry['version_id'] = int(_time.time() * 1000)
                    carry['position_id'] = carry['version_id'] + hash(f"{portfolio_id}{security_id}{basis}{fill_date}") % 10**6

                    success = self.position_service._save_position(carry, updated_by='SYSTEM_CARRYFORWARD')
                    if success:
                        counters['recalculated'] += 1
                        logger.info(f"Carried forward position to {fill_date} basis={basis}")
                    else:
                        counters['errors'] += 1
                        logger.error(f"Failed to carry forward position to {fill_date} basis={basis}")
                except Exception as e:
                    counters['errors'] += 1
                    logger.error(f"Error carrying forward to {fill_date} basis={basis}: {e}")

    def _handle_failure(self, item: Dict[str, Any], error_message: str, is_db_queue: bool = True):
        """Handle failed processing with retry logic."""
        queue_id  = item.get('queue_id')
        trade_id  = item.get('trade_id')
        deal_number = item.get('deal_number') or str(trade_id)
        queued_by = item.get('queued_by', '')
        retry_count = item.get('retry_count', 0)

        _notif_base = {
            'queue_id':   queue_id,
            'trade_id':   trade_id,
            'deal_number': deal_number,
            'portfolio':  item.get('portfolio_id', ''),
            'security':   item.get('security_name') or item.get('security_id', ''),
            'isin':       item.get('isin', ''),
        }

        if retry_count < self.MAX_RETRIES:
            # Retry later
            if is_db_queue:
                self._update_status(
                    queue_id, self.STATUS_PENDING,
                    error_message=error_message,
                    increment_retry=True
                )
            else:
                item['retry_count'] = retry_count + 1
                self._in_memory_queue.put(item)

            logger.warning(
                f"Queue item {queue_id} failed, will retry. "
                f"Retry {retry_count + 1}/{self.MAX_RETRIES}"
            )
            notify_user(queued_by, EVT_AVP_FAILED, {
                **_notif_base,
                'error': error_message,
                'retry': retry_count + 1,
                'max_retries': self.MAX_RETRIES,
                'message': (
                    f'AVP failed for trade {deal_number} — retrying '
                    f'({retry_count + 1}/{self.MAX_RETRIES})'
                ),
            })
        else:
            # Move to dead letter queue
            if is_db_queue:
                self._update_status(
                    queue_id, self.STATUS_DEAD_LETTER,
                    error_message=f"Max retries exceeded. Last error: {error_message}"
                )
            logger.error(
                f"Queue item {queue_id} moved to dead letter queue after {self.MAX_RETRIES} retries"
            )
            notify_user(queued_by, EVT_AVP_DEAD_LETTER, {
                **_notif_base,
                'error': error_message,
                'message': (
                    f'AVP permanently failed for trade {deal_number} after '
                    f'{self.MAX_RETRIES} retries — requires manual intervention'
                ),
            })
            notify_admins(EVT_AVP_DEAD_LETTER, {
                **_notif_base,
                'queued_by': queued_by,
                'error': error_message,
                'message': (
                    f'Dead letter: queue_id={queue_id} trade={deal_number} '
                    f'user={queued_by} — {error_message[:200]}'
                ),
            })

    # =========================================================================
    # QUEUE MANAGEMENT
    # =========================================================================

    def get_pending_items(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get pending items from database queue."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.QUEUE_TABLE}
            WHERE status = '{self.STATUS_PENDING}'
            ORDER BY queued_at ASC
            LIMIT {limit}
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error getting pending items: {str(e)}")
            return []

    def _update_status(
        self,
        queue_id: int,
        status: str,
        error_message: str = None,
        increment_retry: bool = False
    ) -> bool:
        """Update queue item status."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            set_clauses = [f"status = '{status}'", f"updated_at = '{timestamp}'"]

            if error_message:
                set_clauses.append(f"error_message = '{self._escape(error_message)}'")

            if status in [self.STATUS_COMPLETED, self.STATUS_FAILED, self.STATUS_DEAD_LETTER]:
                set_clauses.append(f"processed_at = '{timestamp}'")

            if increment_retry:
                set_clauses.append("retry_count = CAST(retry_count + 1 AS INT)")

            query = f"""
            UPDATE {self.DATABASE}.{self.QUEUE_TABLE}
            SET {', '.join(set_clauses)}
            WHERE queue_id = {queue_id}
            """

            return impala_manager.execute_write(query, database=self.DATABASE)

        except Exception as e:
            logger.error(f"Error updating queue status: {str(e)}")
            return False

    def get_queue_statistics(self) -> Dict[str, Any]:
        """Get queue statistics."""
        try:
            query = f"""
            SELECT
                status,
                COUNT(*) as count,
                AVG(retry_count) as avg_retries
            FROM {self.DATABASE}.{self.QUEUE_TABLE}
            GROUP BY status
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            stats = {
                'pending': 0,
                'processing': 0,
                'completed': 0,
                'failed': 0,
                'dead_letter': 0,
                'total': 0
            }

            if results:
                for row in results:
                    status = row.get('status', '').lower().replace('_', '')
                    if status == 'deadletter':
                        status = 'dead_letter'
                    count = row.get('count', 0)
                    stats[status] = count
                    stats['total'] += count

            return stats

        except Exception as e:
            logger.error(f"Error getting queue statistics: {str(e)}")
            return {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0, 'dead_letter': 0, 'total': 0}

    def retry_failed_items(self) -> Dict[str, int]:
        """Retry all failed items including those that hit max retries."""
        try:
            query = f"""
            UPDATE {self.DATABASE}.{self.QUEUE_TABLE}
            SET status = '{self.STATUS_PENDING}',
                retry_count = 0,
                error_message = NULL,
                updated_at = '{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}'
            WHERE status = '{self.STATUS_FAILED}'
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)
            return {'retried': 1 if success else 0}

        except Exception as e:
            logger.error(f"Error retrying failed items: {str(e)}")
            return {'retried': 0}

    def purge_completed(self, days_old: int = 7) -> Dict[str, int]:
        """Purge completed items older than specified days."""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_old)).strftime('%Y-%m-%d')

            query = f"""
            DELETE FROM {self.DATABASE}.{self.QUEUE_TABLE}
            WHERE status = '{self.STATUS_COMPLETED}'
              AND processed_at < '{cutoff_date}'
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)
            return {'purged': 1 if success else 0}

        except Exception as e:
            logger.error(f"Error purging completed items: {str(e)}")
            return {'purged': 0}

    # =========================================================================
    # SYNCHRONOUS PROCESSING (for testing/immediate needs)
    # =========================================================================

    def process_immediately(
        self,
        trade_id: int,
        portfolio_id: str,
        security_id: str,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        settle_date: str,
        updated_by: str,
        position_basis: str = 'TRADED',
        position_date: str = None,
        **kwargs
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Process position calculation immediately (synchronous).
        Use this when you need immediate results.
        """
        _raw_gross_lc = kwargs.get('gross_amount_lc')
        _gross_amount_lc = Decimal(str(_raw_gross_lc)) if _raw_gross_lc else None
        _raw_trade_lc = kwargs.get('total_amount_lc') or kwargs.get('trade_lc')
        _trade_lc = Decimal(str(_raw_trade_lc)) if _raw_trade_lc else None

        return self.position_service.calculate_position(
            portfolio_id=portfolio_id,
            security_id=security_id,
            trade_type=trade_type,
            quantity=quantity,
            price=price,
            charges=charges,
            position_date=position_date or settle_date,
            trade_id=trade_id,
            updated_by=updated_by,
            security_currency=kwargs.get('security_currency'),
            portfolio_currency=kwargs.get('portfolio_currency'),
            isin=kwargs.get('isin'),
            security_name=kwargs.get('security_name'),
            position_basis=position_basis,
            trade_lc=_trade_lc,
            gross_amount_lc=_gross_amount_lc,
        )

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _generate_id(self) -> int:
        """Generate unique ID."""
        return int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 1000)

    def _escape(self, value: str) -> str:
        """Escape string for SQL."""
        if value is None:
            return ''
        return str(value).replace("'", "''")

    def _null_or_str(self, value: str) -> str:
        """Return NULL or quoted string."""
        if value is None or value == '':
            return 'NULL'
        return f"'{self._escape(value)}'"


# Need to import timedelta
from datetime import timedelta

# Singleton instance
position_queue_service = PositionQueueService()
