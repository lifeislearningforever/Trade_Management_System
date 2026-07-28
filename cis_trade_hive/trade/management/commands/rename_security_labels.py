"""
Management command: rename_security_labels

One-time bulk rename of security_label values in cis_position (and optionally
cis_trade) based on an old→new mapping supplied as a CSV file.

Usage:
    # Dry run — shows counts, writes nothing
    python manage.py rename_security_labels --csv mapping.csv --dry-run

    # Dry run and save output to file
    python manage.py rename_security_labels --csv mapping.csv --dry-run --output dry_run.txt

    # Live run
    python manage.py rename_security_labels --csv mapping.csv --execute --output result.txt

    # Also update cis_trade table
    python manage.py rename_security_labels --csv mapping.csv --execute --update-trades

CSV format (header row optional — detected automatically):
    old_security_name,new_security_name
    AMAG PHARMA,AMAG PHARMACEUTICALS INC
    PT ASIA PACIFIC FIBERS TBK NOTES'20,PT ASIA PACIFIC FIBERS TBK NOTES 2020
"""

import csv
import sys
import logging
from io import StringIO
from django.core.management.base import BaseCommand, CommandError
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'
POSITION_TABLE = f'{DATABASE}.cis_position'
TRADE_TABLE = f'{DATABASE}.cis_trade'


def _esc(val: str) -> str:
    """
    Escape a string for safe embedding in Impala SQL literals.
    Doubles single quotes and removes any NULL bytes.
    """
    return val.replace('\x00', '').replace('\\', '\\\\').replace("'", "\\'")


class TeeWriter:
    """Writes to both the Django stdout and an optional file simultaneously."""

    def __init__(self, stdout, filepath=None):
        self._stdout = stdout
        self._file = open(filepath, 'w', encoding='utf-8') if filepath else None

    def write(self, msg: str):
        # Strip ANSI colour codes for the file
        clean = self._strip_ansi(msg)
        self._stdout.write(msg)
        if self._file:
            self._file.write(clean + '\n')
            self._file.flush()

    def close(self):
        if self._file:
            self._file.close()

    @staticmethod
    def _strip_ansi(text: str) -> str:
        import re
        return re.sub(r'\x1b\[[0-9;]*m', '', text)


class Command(BaseCommand):
    help = (
        'Bulk-rename security_label in cis_position (and optionally cis_trade) '
        'from a CSV mapping file. Runs in dry-run mode unless --execute is passed.'
    )

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
            help='Actually write changes. Without this flag the command is a dry run.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            dest='dry_run',
            help='Explicit dry-run flag (same as omitting --execute). Overrides --execute.',
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
            help='CSV column delimiter (default: comma).',
        )
        parser.add_argument(
            '--output',
            default=None,
            metavar='FILE',
            help='Save the full output log to this file (in addition to printing to terminal).',
        )

    def handle(self, *args, **options):
        csv_path = options['csv']
        execute = options['execute'] and not options['dry_run']
        update_trades = options['update_trades']
        delimiter = options['delimiter']
        output_path = options['output']

        self._tee = TeeWriter(self.stdout, output_path)
        if output_path:
            self._tee.write(f'Output also saved to: {output_path}')

        mode = 'LIVE' if execute else 'DRY-RUN'
        self._tee.write(self.style.WARNING(f'\n=== rename_security_labels [{mode}] ===\n'))

        mapping = self._read_csv(csv_path, delimiter)
        if not mapping:
            self._tee.close()
            raise CommandError('No rows found in the CSV file.')

        self._tee.write(f'Loaded {len(mapping)} rename rule(s) from {csv_path}\n')
        self._tee.write(f'{"OLD NAME":<65}  {"NEW NAME"}')
        self._tee.write('-' * 130)
        for old, new in mapping:
            self._tee.write(f'{old:<65}  {new}')
        self._tee.write('')

        if not execute:
            self._tee.write(self.style.WARNING(
                'DRY-RUN — no changes written. Re-run with --execute to apply.\n'
            ))
            self._show_counts(mapping, update_trades)
        else:
            self._apply(mapping, update_trades)

        self._tee.close()

    # ------------------------------------------------------------------

    def _read_csv(self, path: str, delimiter: str):
        rows = []
        try:
            with open(path, newline='', encoding='utf-8-sig') as fh:
                reader = csv.reader(fh, delimiter=delimiter)
                for i, row in enumerate(reader):
                    if len(row) < 2:
                        continue
                    old_name = row[0].strip()
                    new_name = row[1].strip()
                    if not old_name or not new_name:
                        continue
                    # Skip header row
                    if i == 0 and old_name.lower() in (
                        'old_security_name', 'old', 'from', 'security_name', 'old name'
                    ):
                        continue
                    rows.append((old_name, new_name))
        except FileNotFoundError:
            raise CommandError(f'CSV file not found: {path}')
        except Exception as e:
            raise CommandError(f'Error reading CSV: {e}')
        return rows

    def _count(self, table: str, old_name: str) -> int:
        """Count rows matching old_name in the given table. Uses string escaping."""
        try:
            q = f"SELECT COUNT(*) AS cnt FROM {table} WHERE security_label = '{_esc(old_name)}'"
            rows = impala_manager.execute_query(q, database=DATABASE)
            return int(rows[0]['cnt']) if rows else 0
        except Exception as e:
            logger.warning(f'Count query failed for table={table} name={old_name!r}: {e}')
            return -1

    def _show_counts(self, mapping, update_trades: bool):
        self._tee.write(self.style.HTTP_INFO('\nRow counts per rule:\n'))
        total_pos = 0
        total_trade = 0
        no_match = []

        for old, new in mapping:
            pos_cnt = self._count(POSITION_TABLE, old)
            trade_cnt = self._count(TRADE_TABLE, old) if update_trades else None

            total_pos += pos_cnt if pos_cnt > 0 else 0
            if trade_cnt is not None and trade_cnt > 0:
                total_trade += trade_cnt

            trade_col = f'  trades={trade_cnt}' if update_trades else ''
            if pos_cnt == 0:
                no_match.append(old)
                flag = '  *** NO MATCH ***'
                self._tee.write(self.style.WARNING(f'  {old!r:<60}  positions={pos_cnt}{trade_col}{flag}'))
            else:
                self._tee.write(f'  {old!r:<60}  positions={pos_cnt}{trade_col}')

        self._tee.write(f'\nTOTAL position rows to rename : {total_pos}')
        if update_trades:
            self._tee.write(f'TOTAL trade rows to rename    : {total_trade}')
        if no_match:
            self._tee.write(self.style.WARNING(
                f'\n{len(no_match)} rule(s) had NO MATCH in cis_position — check spelling:'
            ))
            for n in no_match:
                self._tee.write(self.style.WARNING(f'  • {n!r}'))

    def _apply(self, mapping, update_trades: bool):
        total_pos = 0
        total_trade = 0
        errors = []

        for old, new in mapping:
            pos_before = self._count(POSITION_TABLE, old)
            if pos_before == 0:
                self._tee.write(self.style.WARNING(f'  SKIP (0 rows): {old!r}'))
                continue

            # UPDATE is valid for non-PK columns in Kudu via Impala
            try:
                q = f"""
                UPDATE {POSITION_TABLE}
                SET security_label = '{_esc(new)}'
                WHERE security_label = '{_esc(old)}'
                """
                ok = impala_manager.execute_write(q, database=DATABASE)
                if ok:
                    total_pos += pos_before
                    self._tee.write(
                        self.style.SUCCESS(f'  OK position ({pos_before:>4} rows): {old!r} → {new!r}')
                    )
                else:
                    errors.append(f'position UPDATE returned False: {old!r}')
                    self._tee.write(self.style.ERROR(f'  FAIL position: {old!r}'))
            except Exception as e:
                errors.append(f'position UPDATE error for {old!r}: {e}')
                self._tee.write(self.style.ERROR(f'  ERROR position {old!r}: {e}'))

            if update_trades:
                trade_before = self._count(TRADE_TABLE, old)
                if trade_before > 0:
                    try:
                        q = f"""
                        UPDATE {TRADE_TABLE}
                        SET security_label = '{_esc(new)}'
                        WHERE security_label = '{_esc(old)}'
                        """
                        ok = impala_manager.execute_write(q, database=DATABASE)
                        if ok:
                            total_trade += trade_before
                            self._tee.write(
                                self.style.SUCCESS(f'  OK trade    ({trade_before:>4} rows): {old!r} → {new!r}')
                            )
                        else:
                            errors.append(f'trade UPDATE returned False: {old!r}')
                            self._tee.write(self.style.ERROR(f'  FAIL trade: {old!r}'))
                    except Exception as e:
                        errors.append(f'trade UPDATE error for {old!r}: {e}')
                        self._tee.write(self.style.ERROR(f'  ERROR trade {old!r}: {e}'))

        self._tee.write('\n' + '=' * 60)
        self._tee.write(self.style.SUCCESS(f'Done. Renamed {total_pos} position row(s).'))
        if update_trades:
            self._tee.write(self.style.SUCCESS(f'      Renamed {total_trade} trade row(s).'))

        if errors:
            self._tee.write(self.style.ERROR(f'\n{len(errors)} error(s):'))
            for e in errors:
                self._tee.write(self.style.ERROR(f'  • {e}'))
            sys.exit(1)
