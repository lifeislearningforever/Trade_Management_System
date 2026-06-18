"""
Django Management Command: Process Corporate Actions

EOD (End of Day) processing for corporate actions to generate cash flows.
Processes validated CAs from cis_ca_cash_flow_queue and creates
cash flow entries in cis_cash_flow table.

Usage:
    python manage.py process_corporate_actions                    # Process all pending
    python manage.py process_corporate_actions --date 2026-03-18  # Process by payment date
    python manage.py process_corporate_actions --dry-run          # Show what would be processed
    python manage.py process_corporate_actions --ca-id 123456     # Process specific CA
    python manage.py process_corporate_actions --verbose          # Verbose output

Created: 2026-03-19
Version: 1.0
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

from django.core.management.base import BaseCommand, CommandError

from reference_data.services.ca_cash_flow_service import ca_cash_flow_service
from reference_data.repositories.ca_cash_flow_queue_repository import ca_cash_flow_queue_repository

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process corporate actions and generate cash flows (EOD job)'

    def add_arguments(self, parser):
        parser.add_argument(
            '-d', '--date',
            type=str,
            default=None,
            help='Filter by payment date (YYYY-MM-DD). Default: process all pending'
        )
        parser.add_argument(
            '-n', '--dry-run',
            action='store_true',
            help='Show what would be processed without executing'
        )
        parser.add_argument(
            '--verbose-output',
            action='store_true',
            dest='verbose',
            help='Enable verbose output'
        )
        parser.add_argument(
            '--ca-id',
            type=int,
            default=None,
            help='Process specific corporate action by CA ID'
        )
        parser.add_argument(
            '--queue-id',
            type=int,
            default=None,
            help='Process specific queue entry by queue ID'
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
        parser.add_argument(
            '--retry-failed',
            action='store_true',
            help='Retry previously failed queue entries'
        )
        parser.add_argument(
            '--reset-stuck',
            action='store_true',
            help='Reset stuck PROCESSING entries back to PENDING (for entries stuck > 10 minutes)'
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show queue statistics only, do not process'
        )
        parser.add_argument(
            '--correction',
            action='store_true',
            help='Correction run: void existing cash flows for CA, reset queue to PENDING, re-process. Requires --ca-id.'
        )

    def handle(self, *args, **options):
        """Main entry point for the command."""
        payment_date = options['date']
        dry_run = options['dry_run']
        verbose = options['verbose']
        ca_id = options['ca_id']
        queue_id = options['queue_id']
        run_by = options['user']
        batch_size = options['batch_size']
        retry_failed = options['retry_failed']
        reset_stuck = options['reset_stuck']
        show_status = options['status']
        correction = options['correction']

        # Print header
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('  CIS Trade Hive - Corporate Action Cash Flow Processing'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(f'\nStarted: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'Run By: {run_by}')
        if payment_date:
            self.stdout.write(f'Payment Date Filter: {payment_date}')
        if dry_run:
            self.stdout.write(self.style.WARNING('Mode: DRY RUN'))
        self.stdout.write('')

        try:
            # Show status only
            if show_status:
                self._show_statistics()
                return

            # Reset stuck PROCESSING entries
            if reset_stuck:
                self._reset_stuck_entries(verbose)
                return

            # Retry failed entries
            if retry_failed:
                self._retry_failed_entries(verbose)
                return

            # Process specific queue entry
            if queue_id:
                self._process_single_queue_entry(queue_id, dry_run, verbose)
                return

            # Correction run: void old cash flows + reset queue + re-process
            if correction:
                if not ca_id:
                    raise CommandError('--correction requires --ca-id')
                self._correction_run(ca_id, run_by, dry_run, verbose)
                return

            # Process specific CA
            if ca_id:
                self._process_by_ca_id(ca_id, dry_run, verbose)
                return

            # Process all pending
            self._process_pending(payment_date, batch_size, dry_run, verbose)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'\nError: {str(e)}'))
            logger.exception(f"Error in process_corporate_actions command: {str(e)}")
            raise CommandError(str(e))

        # Print footer
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(f'Completed: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))

    def _show_statistics(self):
        """Show queue statistics."""
        self.stdout.write(self.style.HTTP_INFO('\n--- Queue Statistics ---\n'))

        stats = ca_cash_flow_queue_repository.get_statistics()

        if not stats:
            self.stdout.write(self.style.WARNING('No statistics available'))
            return

        pending = stats.get('pending', 0)
        processing = stats.get('processing', 0)
        completed = stats.get('completed', 0)
        failed = stats.get('failed', 0)

        self.stdout.write(f"  Pending:    {pending}")
        if processing > 0:
            self.stdout.write(self.style.WARNING(f"  Processing: {processing}  (use --reset-stuck to reset)"))
        else:
            self.stdout.write(f"  Processing: {processing}")
        self.stdout.write(f"  Completed:  {completed}")
        if failed > 0:
            self.stdout.write(self.style.ERROR(f"  Failed:     {failed}  (use --retry-failed to retry)"))
        else:
            self.stdout.write(f"  Failed:     {failed}")
        self.stdout.write('')
        self.stdout.write(f"  Total Cash Flows Created: {stats.get('total_cash_flows', 0)}")
        self.stdout.write(f"  Total Amount: {stats.get('total_amount', Decimal('0'))}")

    def _process_pending(self, payment_date: str, batch_size: int, dry_run: bool, verbose: bool):
        """Process all pending queue entries."""
        self.stdout.write(self.style.HTTP_INFO('\n--- Processing Pending Corporate Actions ---\n'))

        # Get pending entries
        pending = ca_cash_flow_queue_repository.get_pending(
            limit=batch_size,
            payment_date=payment_date
        )

        if not pending:
            self.stdout.write(self.style.WARNING('No pending corporate actions found'))
            return

        self.stdout.write(f'Found {len(pending)} pending corporate action(s)\n')

        # Show pending entries
        if verbose or dry_run:
            self._show_pending_entries(pending)

        if dry_run:
            self.stdout.write(self.style.WARNING('\n--- DRY RUN - Processing Preview ---\n'))

        # Process each entry
        total_cf_created = 0
        total_amount = Decimal('0')
        successful = 0
        failed = 0

        for entry in pending:
            queue_id = entry.get('queue_id')
            ca_number = entry.get('ca_number', 'Unknown')
            ca_type = entry.get('ca_type', '')
            security = entry.get('security_name', '')

            self.stdout.write(f'\nProcessing: {ca_number} ({ca_type}) - {security}')

            success, message, cf_count, amount = ca_cash_flow_service.process_ca_cash_flows(
                queue_id=queue_id,
                dry_run=dry_run
            )

            if success:
                successful += 1
                total_cf_created += cf_count
                total_amount += amount
                self.stdout.write(self.style.SUCCESS(f'  ✓ {message}'))
            else:
                failed += 1
                self.stdout.write(self.style.ERROR(f'  ✗ Failed: {message}'))

        # Summary
        self.stdout.write(self.style.HTTP_INFO('\n--- Processing Summary ---\n'))
        self.stdout.write(f'  Total Processed: {len(pending)}')
        self.stdout.write(self.style.SUCCESS(f'  Successful: {successful}'))
        if failed > 0:
            self.stdout.write(self.style.ERROR(f'  Failed: {failed}'))
        else:
            self.stdout.write(f'  Failed: {failed}')
        self.stdout.write(f'  Cash Flows Created: {total_cf_created}')
        self.stdout.write(f'  Total Amount: {total_amount}')

    def _process_single_queue_entry(self, queue_id: int, dry_run: bool, verbose: bool):
        """Process a specific queue entry."""
        self.stdout.write(self.style.HTTP_INFO(f'\n--- Processing Queue Entry: {queue_id} ---\n'))

        entry = ca_cash_flow_queue_repository.get_by_id(queue_id)
        if not entry:
            self.stdout.write(self.style.ERROR(f'Queue entry {queue_id} not found'))
            return

        if verbose:
            self._show_entry_details(entry)

        success, message, cf_count, amount = ca_cash_flow_service.process_ca_cash_flows(
            queue_id=queue_id,
            dry_run=dry_run
        )

        if success:
            self.stdout.write(self.style.SUCCESS(f'\n✓ {message}'))
        else:
            self.stdout.write(self.style.ERROR(f'\n✗ Failed: {message}'))

    def _process_by_ca_id(self, ca_id: int, dry_run: bool, verbose: bool):
        """Process queue entries for a specific CA."""
        self.stdout.write(self.style.HTTP_INFO(f'\n--- Processing CA ID: {ca_id} ---\n'))

        entries = ca_cash_flow_queue_repository.get_by_ca_id(ca_id)
        if not entries:
            self.stdout.write(self.style.WARNING(f'No queue entries found for CA {ca_id}'))
            return

        for entry in entries:
            queue_id = entry.get('queue_id')
            status = entry.get('status')

            self.stdout.write(f'\nQueue Entry: {queue_id} (Status: {status})')

            if status == 'COMPLETED':
                self.stdout.write(self.style.WARNING('  Already completed, skipping'))
                continue

            if status == 'PROCESSING':
                self.stdout.write(self.style.WARNING('  Currently processing, skipping'))
                continue

            success, message, cf_count, amount = ca_cash_flow_service.process_ca_cash_flows(
                queue_id=queue_id,
                dry_run=dry_run
            )

            if success:
                self.stdout.write(self.style.SUCCESS(f'  ✓ {message}'))
            else:
                self.stdout.write(self.style.ERROR(f'  ✗ Failed: {message}'))

    def _reset_stuck_entries(self, verbose: bool):
        """Reset stuck PROCESSING entries back to PENDING."""
        self.stdout.write(self.style.HTTP_INFO('\n--- Resetting Stuck PROCESSING Entries ---\n'))

        try:
            from core.repositories.impala_connection import impala_manager

            # Find entries stuck in PROCESSING for more than 10 minutes
            query = """
            SELECT queue_id, ca_number, ca_type, security_name, created_at
            FROM gmp_cis.cis_ca_cash_flow_queue
            WHERE status = 'PROCESSING'
            ORDER BY created_at ASC
            """

            stuck = impala_manager.execute_query(query, database='gmp_cis')

            if not stuck:
                self.stdout.write(self.style.SUCCESS('No stuck PROCESSING entries found'))
                return

            self.stdout.write(f'Found {len(stuck)} stuck PROCESSING entry(ies)\n')

            reset_count = 0
            for entry in stuck:
                queue_id = entry.get('queue_id')
                ca_number = entry.get('ca_number', 'Unknown')

                self.stdout.write(f'Resetting: {ca_number} (queue_id: {queue_id})')

                # Reset status to PENDING
                update_sql = f"""
                UPDATE gmp_cis.cis_ca_cash_flow_queue
                SET status = 'PENDING',
                    error_message = 'Reset from stuck PROCESSING state'
                WHERE queue_id = {queue_id}
                """

                success = impala_manager.execute_write(update_sql, database='gmp_cis')

                if success:
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Reset to PENDING'))
                    reset_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f'  ✗ Failed to reset'))

            self.stdout.write(self.style.HTTP_INFO(f'\n--- Reset {reset_count} of {len(stuck)} entries ---'))
            self.stdout.write(self.style.WARNING('\nRun without --reset-stuck to process these entries'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error resetting stuck entries: {str(e)}'))

    def _retry_failed_entries(self, verbose: bool):
        """Retry failed queue entries."""
        self.stdout.write(self.style.HTTP_INFO('\n--- Retrying Failed Entries ---\n'))

        # Get failed entries (status=FAILED with retry_count < MAX_RETRIES)
        try:
            from core.repositories.impala_connection import impala_manager

            query = """
            SELECT *
            FROM gmp_cis.cis_ca_cash_flow_queue
            WHERE status = 'FAILED'
              AND retry_count < 3
            ORDER BY created_at ASC
            LIMIT 100
            """

            failed = impala_manager.execute_query(query, database='gmp_cis')

            if not failed:
                self.stdout.write(self.style.SUCCESS('No failed entries to retry'))
                return

            self.stdout.write(f'Found {len(failed)} failed entry(ies) to retry\n')

            for entry in failed:
                queue_id = entry.get('queue_id')
                ca_number = entry.get('ca_number', 'Unknown')
                retry_count = entry.get('retry_count', 0)

                self.stdout.write(f'\nRetrying: {ca_number} (attempt {retry_count + 1})')

                # Reset status to PENDING
                ca_cash_flow_queue_repository.reset_for_retry(queue_id)

                # Process
                success, message, cf_count, amount = ca_cash_flow_service.process_ca_cash_flows(
                    queue_id=queue_id,
                    dry_run=False
                )

                if success:
                    self.stdout.write(self.style.SUCCESS(f'  ✓ {message}'))
                else:
                    self.stdout.write(self.style.ERROR(f'  ✗ Failed again: {message}'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error retrying failed entries: {str(e)}'))

    def _correction_run(self, ca_id: int, run_by: str, dry_run: bool, verbose: bool):
        """
        Correction run: void existing cash flows for a CA, reset queue entry to PENDING,
        refresh queue fields from the current CA record, then re-process.

        Use when: EOD already ran and generated cash flows, but the CA was subsequently
        modified and re-validated, and the old cash flows must be replaced.
        """
        from core.repositories.impala_connection import impala_manager
        from reference_data.repositories.corporate_action_repository import CorporateActionRepository

        self.stdout.write(self.style.HTTP_INFO(f'\n--- Correction Run for CA ID: {ca_id} ---\n'))
        if dry_run:
            self.stdout.write(self.style.WARNING('Mode: DRY RUN — no changes will be written\n'))

        # 1. Load the current (modified) CA record
        ca = CorporateActionRepository.get_by_id(ca_id)
        if not ca:
            raise CommandError(f'Corporate action {ca_id} not found')

        ca_number = ca.get('ca_number', 'Unknown')
        ca_status = ca.get('status', '')
        self.stdout.write(f'CA Number : {ca_number}')
        self.stdout.write(f'CA Status : {ca_status}')
        self.stdout.write(f'Security  : {ca.get("security_name")}')
        self.stdout.write(f'Price     : {ca.get("price")} {ca.get("currency")}')
        self.stdout.write(f'Ex Date   : {ca.get("ex_date")}')
        self.stdout.write(f'Rec Date  : {ca.get("record_date")}')
        self.stdout.write(f'Pay Date  : {ca.get("payment_date")}')
        self.stdout.write('')

        if ca_status not in ('VALIDATED', 'APPROVED'):
            raise CommandError(
                f'CA {ca_number} has status "{ca_status}". '
                f'Correction requires a VALIDATED or APPROVED CA.'
            )

        # 2. Find queue entries for this CA
        entries = ca_cash_flow_queue_repository.get_by_ca_id(ca_id)
        if not entries:
            raise CommandError(f'No queue entries found for CA {ca_id} ({ca_number})')

        self.stdout.write(f'Found {len(entries)} queue entry(ies)')

        # 3. For each queue entry: void existing cash flows, reset to PENDING
        total_voided = 0
        queue_ids_to_reprocess = []

        for entry in entries:
            queue_id = entry.get('queue_id')
            q_status = entry.get('status', '')
            cf_created = entry.get('cash_flows_created', 0) or 0
            self.stdout.write(f'\n  Queue {queue_id} — status={q_status}, cash_flows_created={cf_created}')

            # --- void existing cash flows tied to this ca_number ---
            void_query = f"""
            SELECT cash_flow_id
            FROM gmp_cis.cis_cash_flow
            WHERE ca_number = '{ca_number}'
              AND (is_deleted = false OR is_deleted IS NULL)
            """
            existing_cfs = impala_manager.execute_query(void_query, database='gmp_cis')
            cf_ids = [row['cash_flow_id'] for row in (existing_cfs or []) if row.get('cash_flow_id')]

            self.stdout.write(f'  Found {len(cf_ids)} active cash flow(s) to void')

            if cf_ids and not dry_run:
                now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                for cf_id in cf_ids:
                    void_sql = f"""
                    UPDATE gmp_cis.cis_cash_flow
                    SET is_deleted = true,
                        is_active = false,
                        updated_by = '{run_by}',
                        updated_at = '{now_str}'
                    WHERE cash_flow_id = {cf_id}
                    """
                    ok = impala_manager.execute_write(void_sql, database='gmp_cis')
                    if ok:
                        total_voided += 1
                        if verbose:
                            self.stdout.write(f'    Voided cash_flow_id={cf_id}')
                    else:
                        self.stdout.write(self.style.ERROR(f'    Failed to void cash_flow_id={cf_id}'))

            elif cf_ids and dry_run:
                self.stdout.write(f'  [DRY RUN] Would void {len(cf_ids)} cash flow(s): {cf_ids}')
                total_voided += len(cf_ids)

            # --- reset queue entry ---
            if q_status in ('PROCESSING',):
                self.stdout.write(self.style.WARNING(
                    f'  Queue {queue_id} is PROCESSING — skipping (use --reset-stuck first)'
                ))
                continue

            # Refresh queue entry fields from current CA
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ex_date_val = f"'{ca.get('ex_date')}'" if ca.get('ex_date') else 'NULL'
            record_date_val = f"'{ca.get('record_date')}'" if ca.get('record_date') else 'NULL'
            payment_date_val = f"'{ca.get('payment_date')}'" if ca.get('payment_date') else 'NULL'
            price_val = str(ca.get('price')) if ca.get('price') is not None else 'NULL'

            reset_sql = f"""
            UPDATE gmp_cis.cis_ca_cash_flow_queue
            SET status = 'PENDING',
                price = {price_val},
                ex_date = {ex_date_val},
                record_date = {record_date_val},
                payment_date = {payment_date_val},
                error_message = NULL,
                retry_count = 0,
                cash_flows_created = 0,
                total_amount = 0,
                processed_at = NULL
            WHERE queue_id = {queue_id}
            """

            if not dry_run:
                ok = impala_manager.execute_write(reset_sql, database='gmp_cis')
                if ok:
                    self.stdout.write(self.style.SUCCESS(f'  Queue {queue_id} reset to PENDING'))
                    queue_ids_to_reprocess.append(queue_id)
                else:
                    self.stdout.write(self.style.ERROR(f'  Failed to reset queue {queue_id}'))
            else:
                self.stdout.write(f'  [DRY RUN] Would reset queue {queue_id} to PENDING with updated CA fields')
                queue_ids_to_reprocess.append(queue_id)

        # 4. Re-process each reset queue entry
        self.stdout.write('')
        if not queue_ids_to_reprocess:
            self.stdout.write(self.style.WARNING('No queue entries to re-process'))
        else:
            self.stdout.write(self.style.HTTP_INFO(f'--- Re-processing {len(queue_ids_to_reprocess)} queue entry(ies) ---\n'))
            total_cf_created = 0
            for queue_id in queue_ids_to_reprocess:
                self.stdout.write(f'Re-processing queue {queue_id}...')
                if dry_run:
                    self.stdout.write(f'  [DRY RUN] Would call process_ca_cash_flows(queue_id={queue_id})')
                    continue

                success, message, cf_count, amount = ca_cash_flow_service.process_ca_cash_flows(
                    queue_id=queue_id,
                    dry_run=False
                )
                if success:
                    total_cf_created += cf_count
                    self.stdout.write(self.style.SUCCESS(f'  ✓ {message}'))
                else:
                    self.stdout.write(self.style.ERROR(f'  ✗ Failed: {message}'))

        # 5. Summary
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('--- Correction Run Summary ---'))
        self.stdout.write(f'  CA          : {ca_number}')
        self.stdout.write(f'  Voided CFs  : {total_voided}')
        if not dry_run:
            self.stdout.write(f'  New CFs     : {total_cf_created if queue_ids_to_reprocess else 0}')
        self.stdout.write(self.style.SUCCESS('\n  Correction run complete.' if not dry_run else '\n  DRY RUN complete — no changes written.'))

    def _show_pending_entries(self, entries: List[Dict[str, Any]]):
        """Display pending queue entries."""
        self.stdout.write('\nPending Entries:')
        self.stdout.write('-' * 100)
        self.stdout.write(f'{"Queue ID":<18} {"CA Number":<20} {"Type":<12} {"Security":<15} {"Payment Date":<12} {"Price":<10}')
        self.stdout.write('-' * 100)

        for entry in entries:
            queue_id = str(entry.get('queue_id', ''))[:18]
            ca_number = str(entry.get('ca_number', ''))[:20]
            ca_type = str(entry.get('ca_type', ''))[:12]
            security = str(entry.get('security_name', ''))[:15]
            payment_date = str(entry.get('payment_date', ''))[:12]
            price = str(entry.get('price', ''))[:10]

            self.stdout.write(f'{queue_id:<18} {ca_number:<20} {ca_type:<12} {security:<15} {payment_date:<12} {price:<10}')

        self.stdout.write('-' * 100)

    def _show_entry_details(self, entry: Dict[str, Any]):
        """Display detailed information for a queue entry."""
        self.stdout.write('Entry Details:')
        self.stdout.write(f"  Queue ID:      {entry.get('queue_id')}")
        self.stdout.write(f"  CA ID:         {entry.get('ca_id')}")
        self.stdout.write(f"  CA Number:     {entry.get('ca_number')}")
        self.stdout.write(f"  CA Type:       {entry.get('ca_type')}")
        self.stdout.write(f"  Security:      {entry.get('security_name')}")
        self.stdout.write(f"  Portfolio:     {entry.get('portfolio_name') or 'All'}")
        self.stdout.write(f"  Ex Date:       {entry.get('ex_date')}")
        self.stdout.write(f"  Payment Date:  {entry.get('payment_date')}")
        self.stdout.write(f"  Price:         {entry.get('price')} {entry.get('currency')}")
        self.stdout.write(f"  Status:        {entry.get('status')}")
        self.stdout.write(f"  Retry Count:   {entry.get('retry_count')}")
        if entry.get('error_message'):
            self.stdout.write(f"  Last Error:    {entry.get('error_message')}")
