"""
Management command: rename_security_labels

One-time bulk rename of security_label values in cis_position (and optionally
cis_trade) based on an old→new mapping supplied as a CSV file.

Usage:
    # Dry run first — shows what would change, writes nothing
    python manage.py rename_security_labels --csv /path/to/mapping.csv

    # Live run
    python manage.py rename_security_labels --csv /path/to/mapping.csv --execute

    # Also update cis_trade table
    python manage.py rename_security_labels --csv /path/to/mapping.csv --execute --update-trades

CSV format (header row optional — detected automatically):
    old_security_name,new_security_name
    AMAG PHARMA,AMAG PHARMACEUTICALS INC
    AIRBUS SE,AIRBUS SE COMMON STOCK EUR5
"""

import csv
import sys
import logging
from django.core.management.base import BaseCommand, CommandError
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'
POSITION_TABLE = f'{DATABASE}.cis_position'
TRADE_TABLE = f'{DATABASE}.cis_trade'


def _esc(val: str) -> str:
    """Escape single quotes for Impala SQL strings."""
    return val.replace("'", "''")


class Command(BaseCommand):
    help = 'Bulk-rename security_label in cis_position (and optionally cis_trade) from a CSV mapping file.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv',
            required=True,
            metavar='FILE',
            help='Path to the CSV file with old_security_name,new_security_name columns.',
        )
        parser.add_argument(
            '--execute',
            action='store_true',
            default=False,
            help='Actually write changes. Without this flag the command runs in dry-run mode.',
        )
        parser.add_argument(
            '--update-trades',
            action='store_true',
            default=False,
            help='Also update security_label in cis_trade (in addition to cis_position).',
        )
        parser.add_argument(
            '--delimiter',
            default=',',
            help='CSV delimiter (default: comma).',
        )

    def handle(self, *args, **options):
        csv_path = options['csv']
        execute = options['execute']
        update_trades = options['update_trades']
        delimiter = options['delimiter']

        mode = 'LIVE' if execute else 'DRY-RUN'
        self.stdout.write(self.style.WARNING(f'\n=== rename_security_labels [{mode}] ===\n'))

        # --- Read CSV ---
        mapping = self._read_csv(csv_path, delimiter)
        if not mapping:
            raise CommandError('No rows found in the CSV file.')
        self.stdout.write(f'Loaded {len(mapping)} rename rule(s) from {csv_path}\n')

        # --- Preview ---
        self.stdout.write(f'{"OLD NAME":<60}  {"NEW NAME":<60}')
        self.stdout.write('-' * 122)
        for old, new in mapping:
            self.stdout.write(f'{old:<60}  {new:<60}')
        self.stdout.write('')

        if not execute:
            self.stdout.write(self.style.WARNING(
                'DRY-RUN mode — no changes written. Re-run with --execute to apply.\n'
            ))
            # Still show counts per rule so the user can verify scope
            self._show_counts(mapping, update_trades)
            return

        # --- Live run ---
        self._apply(mapping, update_trades)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_csv(self, path: str, delimiter: str):
        """Return list of (old, new) tuples from CSV. Auto-skips header."""
        rows = []
        try:
            with open(path, newline='', encoding='utf-8-sig') as fh:
                reader = csv.reader(fh, delimiter=delimiter)
                for i, row in enumerate(reader):
                    if len(row) < 2:
                        continue
                    old_name = row[0].strip()
                    new_name = row[1].strip()
                    # Skip blank lines and likely header row
                    if not old_name or not new_name:
                        continue
                    if i == 0 and old_name.lower() in ('old_security_name', 'old', 'from', 'security_name'):
                        continue
                    rows.append((old_name, new_name))
        except FileNotFoundError:
            raise CommandError(f'CSV file not found: {path}')
        except Exception as e:
            raise CommandError(f'Error reading CSV: {e}')
        return rows

    def _count_positions(self, old_name: str) -> int:
        try:
            q = f"""
            SELECT COUNT(*) AS cnt
            FROM {POSITION_TABLE}
            WHERE security_label = '{_esc(old_name)}'
            """
            rows = impala_manager.execute_query(q, database=DATABASE)
            return int(rows[0]['cnt']) if rows else 0
        except Exception as e:
            logger.warning(f'Count query failed for "{old_name}": {e}')
            return -1

    def _count_trades(self, old_name: str) -> int:
        try:
            q = f"""
            SELECT COUNT(*) AS cnt
            FROM {TRADE_TABLE}
            WHERE security_label = '{_esc(old_name)}'
            """
            rows = impala_manager.execute_query(q, database=DATABASE)
            return int(rows[0]['cnt']) if rows else 0
        except Exception as e:
            logger.warning(f'Count query failed for "{old_name}": {e}')
            return -1

    def _show_counts(self, mapping, update_trades: bool):
        """Print row counts per rule (dry-run)."""
        self.stdout.write(self.style.HTTP_INFO('\nRow counts (what would be updated):\n'))
        total_pos = 0
        total_trade = 0
        for old, new in mapping:
            pos_cnt = self._count_positions(old)
            trade_cnt = self._count_trades(old) if update_trades else '-'
            total_pos += pos_cnt if isinstance(pos_cnt, int) else 0
            if isinstance(trade_cnt, int):
                total_trade += trade_cnt
            trade_col = f'  trades={trade_cnt}' if update_trades else ''
            flag = '  *** NO MATCH ***' if pos_cnt == 0 else ''
            self.stdout.write(f'  {old!r:<55}  positions={pos_cnt}{trade_col}{flag}')
        self.stdout.write(f'\nTOTAL: {total_pos} position row(s) would be renamed.')
        if update_trades:
            self.stdout.write(f'TOTAL: {total_trade} trade row(s) would be renamed.')
        self.stdout.write('')

    def _apply(self, mapping, update_trades: bool):
        """Execute the renames."""
        total_pos = 0
        total_trade = 0
        errors = []

        for old, new in mapping:
            # -- cis_position --
            # Kudu requires UPSERT for changes; UPDATE is supported via Impala
            # only if the column is not part of the primary key. security_label
            # is NOT the PK (position_id is), so a plain UPDATE works.
            pos_before = self._count_positions(old)
            if pos_before == 0:
                self.stdout.write(self.style.WARNING(f'  SKIP (0 rows): {old!r}'))
                continue

            try:
                update_pos_q = f"""
                UPDATE {POSITION_TABLE}
                SET security_label = '{_esc(new)}'
                WHERE security_label = '{_esc(old)}'
                """
                ok = impala_manager.execute_write(update_pos_q, database=DATABASE)
                if ok:
                    total_pos += pos_before
                    self.stdout.write(
                        self.style.SUCCESS(f'  OK position ({pos_before} rows): {old!r} → {new!r}')
                    )
                else:
                    errors.append(f'position UPDATE returned False for: {old!r}')
                    self.stdout.write(self.style.ERROR(f'  FAIL position: {old!r}'))
            except Exception as e:
                errors.append(f'position UPDATE error for {old!r}: {e}')
                self.stdout.write(self.style.ERROR(f'  ERROR position {old!r}: {e}'))

            # -- cis_trade (optional) --
            if update_trades:
                trade_before = self._count_trades(old)
                if trade_before > 0:
                    try:
                        update_trade_q = f"""
                        UPDATE {TRADE_TABLE}
                        SET security_label = '{_esc(new)}'
                        WHERE security_label = '{_esc(old)}'
                        """
                        ok = impala_manager.execute_write(update_trade_q, database=DATABASE)
                        if ok:
                            total_trade += trade_before
                            self.stdout.write(
                                self.style.SUCCESS(f'  OK trade    ({trade_before} rows): {old!r} → {new!r}')
                            )
                        else:
                            errors.append(f'trade UPDATE returned False for: {old!r}')
                    except Exception as e:
                        errors.append(f'trade UPDATE error for {old!r}: {e}')
                        self.stdout.write(self.style.ERROR(f'  ERROR trade {old!r}: {e}'))

        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'Done. Renamed {total_pos} position row(s).'
        ))
        if update_trades:
            self.stdout.write(self.style.SUCCESS(f'      Renamed {total_trade} trade row(s).'))
        if errors:
            self.stdout.write(self.style.ERROR(f'\n{len(errors)} error(s):'))
            for e in errors:
                self.stdout.write(self.style.ERROR(f'  • {e}'))
            sys.exit(1)
