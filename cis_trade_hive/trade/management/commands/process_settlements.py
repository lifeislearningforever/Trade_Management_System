"""
Django Management Command: Process Settlements

EOD (End of Day) settlement processing for AVP position calculation.
Processes pending settlements from cis_settlement_queue and creates
positions in cis_trade_position table.

Usage:
    python manage.py process_settlements                    # Process today's settlements
    python manage.py process_settlements --date 2026-03-06  # Process specific date
    python manage.py process_settlements --dry-run          # Show what would be processed
    python manage.py process_settlements --verbose          # Verbose output

Created: 2026-03-06
Version: 1.0
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Tuple, Optional

from django.core.management.base import BaseCommand, CommandError

from trade.services.settlement_service import settlement_service
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process pending settlements for AVP position calculation (EOD job)'

    def add_arguments(self, parser):
        parser.add_argument(
            '-d', '--date',
            type=str,
            default=None,
            help='Settlement date to process (YYYY-MM-DD). Default: today'
        )
        parser.add_argument(
            '-n', '--dry-run',
            action='store_true',
            help='Show what would be processed without executing'
        )
        parser.add_argument(
            '-v', '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
        parser.add_argument(
            '--user',
            type=str,
            default='SYSTEM',
            help='User running the job. Default: SYSTEM'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of records to process per batch. Default: 100'
        )

    def handle(self, *args, **options):
        """Main entry point for the command."""
        settle_date = options['date'] or datetime.now().strftime('%Y-%m-%d')
        dry_run = options['dry_run']
        verbose = options['verbose']
        run_by = options['user']
        batch_size = options['batch_size']

        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('  CIS Trade Hive - EOD Settlement Processing'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(f'\nStarted: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'Settlement Date: {settle_date}')
        self.stdout.write(f'Run By: {run_by}')
        self.stdout.write(f'Dry Run: {dry_run}')
        self.stdout.write('')

        try:
            # Step 1: Get pending settlements
            self.stdout.write(self.style.HTTP_INFO('\n--- Checking Pending Settlements ---'))
            pending = self._get_pending_settlements(settle_date)

            if not pending:
                self.stdout.write(self.style.WARNING(
                    f'No pending settlements found for {settle_date}'
                ))
                return

            self.stdout.write(f'Found {len(pending)} pending settlements')

            # Show pending settlements
            if verbose or dry_run:
                self._show_pending_settlements(pending)

            # Dry run - stop here
            if dry_run:
                self.stdout.write(self.style.WARNING('\nDRY RUN - No changes made'))
                return

            # Step 2: Process settlements
            self.stdout.write(self.style.HTTP_INFO('\n--- Processing Settlements ---'))
            results = self._process_settlements(pending, settle_date, run_by, batch_size)

            # Step 3: Show summary
            self._show_summary(results)

            # Step 4: Show position results if verbose
            if verbose:
                self._show_position_results(settle_date, run_by)

            self.stdout.write(self.style.SUCCESS(
                f'\nEOD Settlement Processing Completed Successfully'
            ))

        except Exception as e:
            logger.exception('EOD settlement processing failed')
            raise CommandError(f'EOD settlement processing failed: {str(e)}')

    def _get_pending_settlements(self, settle_date: str) -> List[Dict[str, Any]]:
        """Get pending settlements from the queue."""
        return settlement_service.get_pending_settlements(settle_date)

    def _show_pending_settlements(self, pending: List[Dict[str, Any]]) -> None:
        """Display pending settlements."""
        self.stdout.write('\nPending Settlements:')
        self.stdout.write('-' * 100)
        self.stdout.write(
            f'{"Queue ID":<12} {"Trade ID":<10} {"Portfolio":<15} {"Security":<12} '
            f'{"Type":<6} {"Qty":<12} {"Price":<12} {"Settle Date":<12}'
        )
        self.stdout.write('-' * 100)

        for item in pending[:20]:  # Show first 20
            self.stdout.write(
                f'{item.get("queue_id", ""):<12} '
                f'{item.get("trade_id", ""):<10} '
                f'{str(item.get("portfolio_id", ""))[:15]:<15} '
                f'{str(item.get("security_id", ""))[:12]:<12} '
                f'{item.get("trade_type", ""):<6} '
                f'{str(item.get("quantity", 0)):<12} '
                f'{str(item.get("price", 0)):<12} '
                f'{item.get("settle_date", ""):<12}'
            )

        if len(pending) > 20:
            self.stdout.write(f'... and {len(pending) - 20} more records')

    def _process_settlements(
        self,
        pending: List[Dict[str, Any]],
        settle_date: str,
        run_by: str,
        batch_size: int
    ) -> Dict[str, int]:
        """Process all pending settlements."""
        results = {
            'processed': 0,
            'failed': 0,
            'skipped': 0,
            'total': len(pending)
        }

        start_time = datetime.now()

        # Use the settlement service to process
        service_results = settlement_service.process_pending_settlements(settle_date)

        results['processed'] = service_results.get('processed', 0)
        results['failed'] = service_results.get('failed', 0)
        results['skipped'] = service_results.get('skipped', 0)

        end_time = datetime.now()
        results['duration_seconds'] = (end_time - start_time).total_seconds()

        return results

    def _show_summary(self, results: Dict[str, int]) -> None:
        """Display processing summary."""
        self.stdout.write(self.style.HTTP_INFO('\n--- Processing Summary ---'))
        self.stdout.write(f'Total Records:     {results["total"]}')
        self.stdout.write(self.style.SUCCESS(f'Processed:         {results["processed"]}'))

        if results['failed'] > 0:
            self.stdout.write(self.style.ERROR(f'Failed:            {results["failed"]}'))
        else:
            self.stdout.write(f'Failed:            {results["failed"]}')

        self.stdout.write(f'Skipped:           {results["skipped"]}')
        self.stdout.write(f'Duration:          {results.get("duration_seconds", 0):.2f} seconds')

    def _show_position_results(self, settle_date: str, run_by: str) -> None:
        """Display position results."""
        self.stdout.write(self.style.HTTP_INFO('\n--- Position Results ---'))

        try:
            query = f"""
            SELECT
                portfolio_short_name,
                security_label,
                quantity,
                average_cost,
                total_cost,
                realized_pnl,
                status,
                position_date
            FROM gmp_cis.cis_trade_position
            WHERE updated_by = '{run_by}'
              AND position_date = '{settle_date}'
            ORDER BY version_id DESC
            LIMIT 20
            """

            results = impala_manager.execute_query(query, database='gmp_cis')

            if results:
                self.stdout.write('-' * 100)
                self.stdout.write(
                    f'{"Portfolio":<15} {"Security":<12} {"Qty":<12} {"Avg Cost":<14} '
                    f'{"Total Cost":<14} {"Realized P&L":<14} {"Status":<8}'
                )
                self.stdout.write('-' * 100)

                for row in results:
                    self.stdout.write(
                        f'{str(row.get("portfolio_short_name", ""))[:15]:<15} '
                        f'{str(row.get("security_label", ""))[:12]:<12} '
                        f'{str(row.get("quantity", 0)):<12} '
                        f'{str(row.get("average_cost", 0)):<14} '
                        f'{str(row.get("total_cost", 0)):<14} '
                        f'{str(row.get("realized_pnl", 0)):<14} '
                        f'{row.get("status", ""):<8}'
                    )
            else:
                self.stdout.write('No position records found')

        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Could not fetch position results: {str(e)}'))
