"""
Management command: cleanup_corr_duplicate_positions

Fixes duplicate is_latest=true CORR rows in cis_position caused by the
pre-fix refresh_positions._batch_upsert_eod bug (timestamp-based position_id,
fixed in commit cb4b04f "use deterministic position_id + UPSERT in
_batch_upsert_eod to stop duplicate EOD rows", 2026-07-20).

Any environment that ran `refresh_positions --run-type CORR` on the pre-fix
code generated a brand-new position_id on every run instead of reusing the
deterministic natural-key hash, so re-running for the same
(portfolio, security_label, position_basis, position_date) left the old row
stranded with is_latest=true alongside the new one, instead of the intended
UPSERT-in-place. Confirmed live: 953 natural keys for position_date
2026-02-27 each had exactly 2 is_latest=true CORR rows.

For each affected natural key group, this command keeps the row with the
highest version_id (the most recently written one) as is_latest=true and
flips every other row in that group to is_latest=false. It does NOT delete
any rows -- the stale rows remain in cis_position for audit purposes, just
no longer flagged as latest.

Usage:
    # Dry run (default) -- lists what would change, writes nothing
    python manage.py cleanup_corr_duplicate_positions

    # Scope to one position_date
    python manage.py cleanup_corr_duplicate_positions --position-date 2026-02-27

    # Live run -- actually flips is_latest=false on the stale rows
    python manage.py cleanup_corr_duplicate_positions --execute
    python manage.py cleanup_corr_duplicate_positions --position-date 2026-02-27 --execute
"""

import logging
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)

DATABASE = settings.IMPALA_CONFIG['DATABASE']
BATCH = 500


class Command(BaseCommand):
    help = (
        'Flip is_latest=false on stale duplicate CORR rows in cis_position '
        '(pre-fix refresh_positions timestamp-based position_id bug). '
        'Dry-run unless --execute is passed.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--position-type', type=str, default='CORR',
            help="Position type to scan for duplicates (default: CORR)."
        )
        parser.add_argument(
            '--position-date', type=str, default=None, dest='position_date',
            help='Optional: scope to a single position_date (YYYY-MM-DD). '
                 'Default: all dates.'
        )
        parser.add_argument(
            '--execute', action='store_true', default=False,
            help='Actually write is_latest=false. Without this flag, dry run only.'
        )

    def handle(self, *args, **options):
        position_type = options['position_type']
        position_date = options['position_date']
        execute       = options['execute']

        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Cleanup duplicate is_latest=true {position_type} rows in cis_position'
        ))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(f"Position type : {position_type}")
        self.stdout.write(f"Position date : {position_date or '(all dates)'}")
        self.stdout.write(f"Mode          : {'EXECUTE (will write)' if execute else 'DRY RUN'}")
        self.stdout.write('')

        stale_rows = self._find_stale_rows(position_type, position_date)

        if not stale_rows:
            self.stdout.write(self.style.SUCCESS('No duplicate is_latest=true rows found. Nothing to do.'))
            return

        by_date = {}
        for r in stale_rows:
            by_date.setdefault(r['position_date'], []).append(r)

        self.stdout.write(f"Found {len(stale_rows)} stale row(s) across {len(by_date)} position_date(s):")
        for pdate in sorted(by_date.keys()):
            self.stdout.write(f"  {pdate}: {len(by_date[pdate])} stale row(s)")
        self.stdout.write('')

        self.stdout.write('Sample (up to 10):')
        for r in stale_rows[:10]:
            self.stdout.write(
                f"  position_id={r['position_id']}  {r['portfolio']}/{r['security_label']}/"
                f"{r['position_basis']}  date={r['position_date']}  version_id={r['version_id']}"
            )
        self.stdout.write('')

        if not execute:
            self.stdout.write(self.style.WARNING(
                'DRY RUN -- no changes written. Re-run with --execute to apply.'
            ))
            return

        updated = self._flip_is_latest_false(stale_rows, position_type)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Flipped is_latest=false on {updated} row(s).'))

        remaining = self._find_stale_rows(position_type, position_date)
        if remaining:
            self.stdout.write(self.style.ERROR(
                f'Verification FAILED: {len(remaining)} duplicate row(s) still present after cleanup.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                'Verification passed: no duplicate is_latest=true rows remain in scope.'
            ))

    # -------------------------------------------------------------------------

    def _find_stale_rows(self, position_type, position_date):
        """
        Return every is_latest=true row that is NOT the highest-version_id row
        within its (portfolio, security_label, position_basis, position_date)
        group -- i.e. the stale duplicates left behind by the pre-fix bug.
        """
        date_clause = (
            f"AND position_date = '{self._escape(position_date)}'" if position_date else ""
        )
        query = f"""
            SELECT position_id, portfolio, security_label, position_basis,
                   position_date, version_id
            FROM (
                SELECT p.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY portfolio, security_label, position_basis, position_date
                           ORDER BY version_id DESC
                       ) AS rn
                FROM {DATABASE}.cis_position p
                WHERE position_type = '{self._escape(position_type)}'
                  AND is_latest = true
                  {date_clause}
            ) ranked
            WHERE rn > 1
        """
        try:
            return impala_manager.execute_query(query, database=DATABASE) or []
        except Exception as e:
            raise CommandError(f'Failed to query stale rows: {e}')

    def _flip_is_latest_false(self, stale_rows, position_type):
        """UPDATE is_latest=false on the given rows, batched by literal position_id IN-list."""
        ids = [str(r['position_id']) for r in stale_rows if r.get('position_id') is not None]
        updated = 0

        for i in range(0, len(ids), BATCH):
            chunk = ids[i:i + BATCH]
            ids_csv = ', '.join(chunk)
            sql = f"""
                UPDATE {DATABASE}.cis_position
                SET is_latest = false
                WHERE position_type = '{self._escape(position_type)}'
                  AND is_latest = true
                  AND position_id IN ({ids_csv})
            """
            impala_manager.execute_write(sql, database=DATABASE)
            updated += len(chunk)
            self.stdout.write(f"  Updated rows {i + 1}-{i + len(chunk)} of {len(ids)}...")

        return updated

    def _escape(self, value):
        if value is None:
            return ''
        return str(value).replace('\\', '\\\\').replace("'", "\\'")
