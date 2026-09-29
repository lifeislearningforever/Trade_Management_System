"""
Django Management Command: Backfill Cancelled Trade Visibility

One-off data fix for trades that were cancelled via the old trade_cancel
flow, which incorrectly called soft_delete_trade() and set is_deleted=true
alongside status='CANCELLED'. This hid cancelled trades from the trade list
entirely (even when explicitly filtering by status=CANCELLED), since the
list query unconditionally excludes is_deleted=true rows.

This command restores is_deleted=false for trades where status='CANCELLED'
and is_deleted=true, so they reappear in the trade list (dimmed, per
existing UI styling for CANCELLED rows). It does not touch trades that
were genuinely deleted for other reasons (status != 'CANCELLED').

Usage:
    python manage.py backfill_cancelled_trade_visibility --dry-run
    python manage.py backfill_cancelled_trade_visibility --apply
"""

import logging

import os
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from lib.management_base import BaseCommand, CommandError, run_command

from lib.impala_connection import impala_manager
from lib.trade_kudu_repository import trade_kudu_repository

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Restore is_deleted=false for trades wrongly soft-deleted by the old cancel flow'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually run the UPDATE. Without this flag, only a dry-run count is shown.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        database = trade_kudu_repository.DATABASE
        table = trade_kudu_repository.TABLE_NAME

        count_query = f"""
            SELECT COUNT(*) as cnt
            FROM {database}.{table}
            WHERE status = 'CANCELLED' AND is_deleted = true
        """

        with impala_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(count_query)
            row = cursor.fetchone()
            affected = row[0] if row else 0

        self.stdout.write(f"Trades with status=CANCELLED and is_deleted=true: {affected}")

        if affected == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to backfill."))
            return

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                "Dry run only. Re-run with --apply to restore these trades to the trade list."
            ))
            return

        update_query = f"""
            UPDATE {database}.{table}
            SET is_deleted = false
            WHERE status = 'CANCELLED' AND is_deleted = true
        """

        success = impala_manager.execute_write(update_query, database=database)
        if not success:
            raise CommandError("Backfill UPDATE failed. Check logs for details.")

        self.stdout.write(self.style.SUCCESS(
            f"Backfill complete. {affected} cancelled trade(s) restored to visible (is_deleted=false)."
        ))


if __name__ == '__main__':
    run_command(Command)
