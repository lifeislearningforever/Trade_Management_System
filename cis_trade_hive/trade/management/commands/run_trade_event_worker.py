"""
Management Command: Run Trade Event Queue Worker

Usage:
    python manage.py run_trade_event_worker

This starts a background worker that processes trade events from cis_trade_event_queue.
Events include:
- HISTORY: Insert trade history records
- SETTLEMENT: Process settlement and AVP calculations

The worker runs continuously until stopped (Ctrl+C).

For production, run this as a systemd service or supervisor job.
"""

import signal
import sys
import time
from django.core.management.base import BaseCommand

from trade.services.trade_event_queue_service import trade_event_queue_service


class Command(BaseCommand):
    help = 'Run the trade event queue worker for async processing of trade side effects'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Process pending events once and exit (for testing/cron)',
        )
        parser.add_argument(
            '--poll-interval',
            type=int,
            default=5,
            help='Seconds between queue polls (default: 5)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting trade event queue worker...'))

        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            self.stdout.write(self.style.WARNING('\nShutdown signal received...'))
            trade_event_queue_service.stop_worker()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Update poll interval if specified
        if options['poll_interval']:
            trade_event_queue_service.POLL_INTERVAL_SECONDS = options['poll_interval']

        if options['once']:
            # Single run mode - process pending events and exit
            self.stdout.write('Running in single-pass mode...')
            self._process_once()
        else:
            # Continuous mode - start worker thread
            self.stdout.write('Running in continuous mode (Ctrl+C to stop)...')
            trade_event_queue_service.start_worker()

            # Keep main thread alive and periodically show status
            try:
                while trade_event_queue_service.is_running():
                    time.sleep(30)  # Status update every 30 seconds
                    stats = trade_event_queue_service.get_stats()
                    health = trade_event_queue_service.get_queue_health()

                    self.stdout.write(
                        f"Worker status: processed={stats['processed']}, "
                        f"failed={stats['failed']}, "
                        f"dead_letter={stats['dead_letter']}, "
                        f"pending={health.get('pending_count', 0)}"
                    )

                    if health.get('sla_breached'):
                        self.stdout.write(
                            self.style.WARNING(
                                f"SLA BREACH: Oldest pending event: {health.get('oldest_pending')}"
                            )
                        )
            except KeyboardInterrupt:
                pass

            self.stdout.write(self.style.SUCCESS('Worker stopped.'))

    def _process_once(self):
        """Process all pending events once and return."""
        # Manually fetch and process events
        pending_count = trade_event_queue_service.get_pending_count()
        self.stdout.write(f'Found {pending_count} pending events')

        if pending_count == 0:
            self.stdout.write(self.style.SUCCESS('No pending events to process.'))
            return

        # Fetch and process
        events = trade_event_queue_service._fetch_pending_events()
        processed = 0
        failed = 0

        for event in events:
            success = trade_event_queue_service._process_event(event)
            if success:
                processed += 1
            else:
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Processed {processed} events, {failed} failed'
            )
        )
