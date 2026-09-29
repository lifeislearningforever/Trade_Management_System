"""
Django Management Command: Position Queue Worker

Background worker for processing position calculations asynchronously.
This decouples position calculation from trade save for fast response times.

Usage:
    python manage.py position_worker start     # Start the worker (foreground)
    python manage.py position_worker status    # Show queue statistics
    python manage.py position_worker process   # Process pending items once (no loop)
    python manage.py position_worker retry     # Retry failed items

For production, run as a daemon:
    nohup python manage.py position_worker start >> /var/log/position_worker.log 2>&1 &

Or use systemd service:
    [Unit]
    Description=CIS Position Queue Worker
    After=network.target

    [Service]
    Type=simple
    User=cis
    WorkingDirectory=/path/to/cis_trade_hive
    ExecStart=/path/to/venv/bin/python manage.py position_worker start
    Restart=always

    [Install]
    WantedBy=multi-user.target

Created: 2026-03-06
Version: 1.0
"""

import signal
import sys
import time
import logging
from datetime import datetime

import os
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from lib.management_base import BaseCommand, CommandError, run_command

from lib.position_queue_service import position_queue_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Manage the position queue background worker'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._shutdown_requested = False

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['start', 'status', 'process', 'retry', 'purge'],
            help='Action to perform: start, status, process, retry, purge'
        )
        parser.add_argument(
            '--poll-interval',
            type=int,
            default=10,
            help='Poll interval in seconds (default: 10)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Batch size for processing (default: 100)'
        )
        parser.add_argument(
            '--purge-days',
            type=int,
            default=7,
            help='Days to keep completed items (default: 7)'
        )

    def handle(self, *args, **options):
        action = options['action']

        if action == 'start':
            self._start_worker(options)
        elif action == 'status':
            self._show_status()
        elif action == 'process':
            self._process_once(options)
        elif action == 'retry':
            self._retry_failed()
        elif action == 'purge':
            self._purge_completed(options)

    def _start_worker(self, options):
        """Start the background worker (runs in foreground with signal handling)."""
        self.stdout.write(self.style.HTTP_INFO('=' * 60))
        self.stdout.write(self.style.HTTP_INFO('  CIS Position Queue Worker'))
        self.stdout.write(self.style.HTTP_INFO('=' * 60))
        self.stdout.write(f'\nStarted: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'Poll Interval: {options["poll_interval"]} seconds')
        self.stdout.write(f'Batch Size: {options["batch_size"]}')
        self.stdout.write('\nPress Ctrl+C to stop\n')

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Configure the service
        position_queue_service.POLL_INTERVAL = options['poll_interval']
        position_queue_service.BATCH_SIZE = options['batch_size']

        # Main loop (instead of starting separate thread, run in main thread)
        self.stdout.write(self.style.SUCCESS('Worker running...'))

        while not self._shutdown_requested:
            try:
                # Process database queue
                pending = position_queue_service.get_pending_items(
                    limit=options['batch_size']
                )

                if pending:
                    self.stdout.write(f'Processing {len(pending)} items...')
                    for item in pending:
                        if self._shutdown_requested:
                            break
                        position_queue_service._process_item(item)

                    # Show stats after processing
                    stats = position_queue_service.get_queue_statistics()
                    self.stdout.write(
                        f'  Completed. Queue: {stats["pending"]} pending, '
                        f'{stats["completed"]} completed, {stats["failed"]} failed'
                    )
                else:
                    # No items, sleep
                    time.sleep(options['poll_interval'])

            except Exception as e:
                logger.error(f'Worker error: {str(e)}')
                self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
                time.sleep(options['poll_interval'])

        self.stdout.write(self.style.WARNING('\nWorker stopped.'))

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.stdout.write(self.style.WARNING('\nShutdown signal received...'))
        self._shutdown_requested = True

    def _show_status(self):
        """Show queue statistics."""
        self.stdout.write(self.style.HTTP_INFO('=' * 60))
        self.stdout.write(self.style.HTTP_INFO('  Position Queue Status'))
        self.stdout.write(self.style.HTTP_INFO('=' * 60))

        stats = position_queue_service.get_queue_statistics()

        self.stdout.write(f'\nTotal Items:       {stats["total"]}')
        self.stdout.write(f'Pending:           {stats["pending"]}')
        self.stdout.write(f'Processing:        {stats["processing"]}')
        self.stdout.write(self.style.SUCCESS(f'Completed:         {stats["completed"]}'))

        if stats['failed'] > 0:
            self.stdout.write(self.style.ERROR(f'Failed:            {stats["failed"]}'))
        else:
            self.stdout.write(f'Failed:            {stats["failed"]}')

        if stats['dead_letter'] > 0:
            self.stdout.write(self.style.ERROR(f'Dead Letter:       {stats["dead_letter"]}'))
        else:
            self.stdout.write(f'Dead Letter:       {stats["dead_letter"]}')

        # Show pending items if any
        if stats['pending'] > 0:
            self.stdout.write('\nPending Items:')
            pending = position_queue_service.get_pending_items(limit=10)
            for item in pending:
                self.stdout.write(
                    f'  [{item.get("queue_id")}] Trade {item.get("trade_id")} - '
                    f'{item.get("trade_type")} {item.get("quantity")} @ {item.get("price")} '
                    f'(queued: {item.get("queued_at")})'
                )
            if stats['pending'] > 10:
                self.stdout.write(f'  ... and {stats["pending"] - 10} more')

    def _process_once(self, options):
        """Process pending items once (no loop)."""
        self.stdout.write('Processing pending items...')

        pending = position_queue_service.get_pending_items(
            limit=options['batch_size']
        )

        if not pending:
            self.stdout.write(self.style.WARNING('No pending items to process'))
            return

        self.stdout.write(f'Found {len(pending)} pending items')

        processed = 0
        failed = 0

        for item in pending:
            try:
                position_queue_service._process_item(item)
                processed += 1
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))

        self.stdout.write(self.style.SUCCESS(
            f'\nProcessed: {processed}, Failed: {failed}'
        ))

    def _retry_failed(self):
        """Retry failed items."""
        self.stdout.write('Retrying failed items...')

        result = position_queue_service.retry_failed_items()

        self.stdout.write(self.style.SUCCESS(
            f'Retried {result.get("retried", 0)} items'
        ))

    def _purge_completed(self, options):
        """Purge completed items older than specified days."""
        days = options['purge_days']
        self.stdout.write(f'Purging completed items older than {days} days...')

        result = position_queue_service.purge_completed(days_old=days)

        self.stdout.write(self.style.SUCCESS(
            f'Purged {result.get("purged", 0)} items'
        ))


if __name__ == '__main__':
    run_command(Command)
