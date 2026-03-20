"""
Django Management Command: Trade Event Queue Worker

Background worker for processing trade events asynchronously:
- HISTORY: Insert trade history records
- SETTLEMENT: Process settlement and AVP calculations

Usage:
    python manage.py trade_event_worker start     # Start the worker (foreground)
    python manage.py trade_event_worker status    # Show queue statistics
    python manage.py trade_event_worker process   # Process pending items once (no loop)

For production, run as a daemon:
    nohup python manage.py trade_event_worker start >> /var/log/trade_event_worker.log 2>&1 &
"""

import signal
import sys
import time
import json
import logging
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Manage the trade event queue background worker'

    DATABASE = 'gmp_cis'
    EVENT_QUEUE_TABLE = 'cis_trade_event_queue'
    HISTORY_TABLE = 'cis_trade_history'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._shutdown_requested = False

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['start', 'status', 'process'],
            help='Action to perform: start, status, process'
        )
        parser.add_argument(
            '--poll-interval',
            type=int,
            default=5,
            help='Poll interval in seconds (default: 5)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Batch size for processing (default: 50)'
        )

    def handle(self, *args, **options):
        action = options['action']

        if action == 'start':
            self._start_worker(options)
        elif action == 'status':
            self._show_status()
        elif action == 'process':
            self._process_once(options)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.stdout.write(self.style.WARNING('\nShutdown signal received, finishing current batch...'))
        self._shutdown_requested = True

    def _start_worker(self, options):
        """Start the worker in continuous mode."""
        poll_interval = options['poll_interval']
        batch_size = options['batch_size']

        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.stdout.write(self.style.SUCCESS(
            f'Trade Event Worker started (poll: {poll_interval}s, batch: {batch_size})'
        ))

        while not self._shutdown_requested:
            try:
                processed = self._process_batch(batch_size)
                if processed > 0:
                    self.stdout.write(f'Processed {processed} events')
                else:
                    # No events, wait before next poll
                    time.sleep(poll_interval)
            except Exception as e:
                logger.error(f'Error in worker loop: {e}')
                time.sleep(poll_interval)

        self.stdout.write(self.style.SUCCESS('Worker stopped gracefully'))

    def _show_status(self):
        """Show queue statistics."""
        try:
            query = f"""
            SELECT status, COUNT(*) as count
            FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            GROUP BY status
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            self.stdout.write('\nTrade Event Queue Status:')
            self.stdout.write('-' * 40)

            total = 0
            if results:
                for row in results:
                    status = row.get('status', 'UNKNOWN')
                    count = row.get('count', 0)
                    total += count
                    self.stdout.write(f'  {status}: {count}')
            else:
                self.stdout.write('  No events in queue')

            self.stdout.write('-' * 40)
            self.stdout.write(f'  Total: {total}')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error getting status: {e}'))

    def _process_once(self, options):
        """Process one batch of events (no loop)."""
        batch_size = options['batch_size']
        processed = self._process_batch(batch_size)
        self.stdout.write(f'Processed {processed} events')

    def _process_batch(self, batch_size: int) -> int:
        """Process a batch of pending events."""
        try:
            # Get pending events
            query = f"""
            SELECT event_id, trade_id, deal_number, event_type, event_data,
                   retry_count, created_by
            FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            WHERE status = 'PENDING'
            ORDER BY created_at
            LIMIT {batch_size}
            """
            events = impala_manager.execute_query(query, database=self.DATABASE)

            if not events:
                return 0

            processed = 0
            for event in events:
                try:
                    self._process_event(event)
                    self._mark_completed(event['event_id'])
                    processed += 1
                except Exception as e:
                    logger.error(f"Error processing event {event['event_id']}: {e}")
                    self._mark_failed(event['event_id'], str(e), event.get('retry_count', 0))

            return processed

        except Exception as e:
            logger.error(f'Error fetching events: {e}')
            return 0

    def _process_event(self, event: dict):
        """Process a single event based on type."""
        event_type = event.get('event_type')
        event_data = json.loads(event.get('event_data', '{}'))

        if event_type == 'HISTORY':
            self._process_history_event(event, event_data)
        elif event_type == 'SETTLEMENT':
            self._process_settlement_event(event, event_data)
        else:
            logger.warning(f"Unknown event type: {event_type}")

    def _process_history_event(self, event: dict, event_data: dict):
        """Process a HISTORY event - insert trade history record."""
        trade_id = event['trade_id']
        deal_number = event['deal_number']
        created_by = event['created_by']
        action = event_data.get('action', 'CREATE')
        old_status = event_data.get('old_status')
        new_status = event_data.get('new_status', 'INITIAL')

        timestamp = datetime.now()
        history_id = int(timestamp.timestamp() * 1000)

        query = f"""
        UPSERT INTO {self.DATABASE}.{self.HISTORY_TABLE}
        (history_id, trade_id, deal_number, action, old_status, new_status,
         changes, comments, performed_by, performed_at)
        VALUES (
            {history_id},
            {trade_id},
            '{deal_number}',
            '{action}',
            {f"'{old_status}'" if old_status else 'NULL'},
            '{new_status}',
            '{{}}',
            'Trade created',
            '{created_by}',
            '{timestamp.strftime('%Y-%m-%d %H:%M:%S')}'
        )
        """
        impala_manager.execute_write(query, database=self.DATABASE)
        logger.info(f"Inserted history for trade {trade_id}")

    def _process_settlement_event(self, event: dict, event_data: dict):
        """Process a SETTLEMENT event - trigger settlement/AVP calculation."""
        from trade.services.settlement_service import settlement_service

        trade_id = event_data.get('trade_id')
        created_by = event['created_by']

        # Extract settlement data
        charges = (
            Decimal(str(event_data.get('commission', 0) or 0)) +
            Decimal(str(event_data.get('sec_fee', 0) or 0)) +
            Decimal(str(event_data.get('other_charges', 0) or 0))
        )

        # Process settlement (this calculates AVP)
        success, msg, result = settlement_service.process_trade_settlement(
            trade_id=trade_id,
            portfolio_id=event_data.get('portfolio_short_name', ''),
            security_id=event_data.get('security_label', ''),
            trade_type=event_data.get('trade_type', ''),
            quantity=Decimal(str(event_data.get('quantity', 0) or 0)),
            price=Decimal(str(event_data.get('price', 0) or 0)),
            charges=charges,
            trade_date=event_data.get('trade_date', ''),
            settle_date=event_data.get('settle_date', ''),
            updated_by=created_by,
            security_currency=event_data.get('security_currency'),
            portfolio_currency=event_data.get('portfolio_currency'),
            isin=event_data.get('isin'),
            security_name=event_data.get('security_name'),
            custodian=event_data.get('custodian', ''),
            sub_custodian=event_data.get('sub_custodian', ''),
            async_mode=False  # Process synchronously in worker
        )

        if success:
            logger.info(f"Settlement processed for trade {trade_id}: {msg}")
        else:
            logger.warning(f"Settlement issue for trade {trade_id}: {msg}")

    def _mark_completed(self, event_id: int):
        """Mark event as completed."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        query = f"""
        UPDATE {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
        SET status = 'COMPLETED', processed_at = '{timestamp}'
        WHERE event_id = {event_id}
        """
        # Kudu doesn't support UPDATE, use UPSERT pattern
        # First get the event, then upsert with new status
        get_query = f"""
        SELECT * FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
        WHERE event_id = {event_id}
        """
        results = impala_manager.execute_query(get_query, database=self.DATABASE)
        if results:
            event = results[0]
            upsert_query = f"""
            UPSERT INTO {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            (event_id, trade_id, deal_number, event_type, event_data, status,
             retry_count, error_message, created_by, created_at, processed_at)
            VALUES (
                {event_id},
                {event['trade_id']},
                '{event['deal_number']}',
                '{event['event_type']}',
                '{event['event_data'].replace("'", "''")}',
                'COMPLETED',
                {event.get('retry_count', 0)},
                NULL,
                '{event['created_by']}',
                '{event['created_at']}',
                '{timestamp}'
            )
            """
            impala_manager.execute_write(upsert_query, database=self.DATABASE)

    def _mark_failed(self, event_id: int, error_message: str, retry_count: int):
        """Mark event as failed with error message."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_retry_count = retry_count + 1
        status = 'FAILED' if new_retry_count >= 3 else 'PENDING'  # Retry up to 3 times

        get_query = f"""
        SELECT * FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
        WHERE event_id = {event_id}
        """
        results = impala_manager.execute_query(get_query, database=self.DATABASE)
        if results:
            event = results[0]
            error_escaped = error_message.replace("'", "''")[:500]  # Limit error length
            upsert_query = f"""
            UPSERT INTO {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            (event_id, trade_id, deal_number, event_type, event_data, status,
             retry_count, error_message, created_by, created_at, processed_at)
            VALUES (
                {event_id},
                {event['trade_id']},
                '{event['deal_number']}',
                '{event['event_type']}',
                '{event['event_data'].replace("'", "''")}',
                '{status}',
                {new_retry_count},
                '{error_escaped}',
                '{event['created_by']}',
                '{event['created_at']}',
                '{timestamp}'
            )
            """
            impala_manager.execute_write(upsert_query, database=self.DATABASE)
