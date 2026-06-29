"""
Management command: delete_security_labels

Bulk-delete all cis_position rows (and optionally cis_trade rows) for a list of
security labels supplied as a single-column CSV file.

Usage:
    # Dry run — shows row counts, writes nothing
    python manage.py delete_security_labels --csv securities.csv --dry-run

    # Dry run and save output to file
    python manage.py delete_security_labels --csv securities.csv --dry-run --output dry_run.txt

    # Live run
    python manage.py delete_security_labels --csv securities.csv --execute --output result.txt

    # Also delete from cis_trade
    python manage.py delete_security_labels --csv securities.csv --execute --delete-trades

CSV format (single column, header row optional — detected automatically):
    security_name
    AMAG PHARMACEUTICALS INC
    PT ASIA PACIFIC FIBERS TBK NOTES 2020
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

# Header values that indicate the first row is a header, not a security name
_HEADER_VALUES = {
    'security_name', 'security_label', 'name', 'security', 'label',
    'security name', 'security label',
}


def _esc(val: str) -> str:
    return val.replace('\x00', '').replace("'", "''")


class TeeWriter:
    """Writes to both Django stdout and an optional file simultaneously."""

    def __init__(self, stdout, filepath=None):
        self._stdout = stdout
        self._file = open(filepath, 'w', encoding='utf-8') if filepath else None

    def write(self, msg: str):
        import re
        clean = re.sub(r'\x1b\[[0-9;]*m', '', msg)
        self._stdout.write(msg)
        if self._file:
            self._file.write(clean + '\n')
            self._file.flush()

    def close(self):
        if self._file:
            self._file.close()


class Command(BaseCommand):
    help = (
        'Bulk-delete security_label rows from cis_position (and optionally cis_trade) '
        'using a single-column CSV of security names. Dry-run unless --execute is passed.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv',
            required=True,
            metavar='FILE',
            help='Path to the CSV file with a single security_name column.',
        )
        parser.add_argument(
            '--execute',
            action='store_true',
            default=False,
            help='Actually delete rows. Without this flag the command is a dry run.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            dest='dry_run',
            help='Explicit dry-run flag (same as omitting --execute). Overrides --execute.',
        )
        parser.add_argument(
            '--delete-trades',
            action='store_true',
            default=False,
            help='Also delete matching rows from cis_trade (in addition to cis_position).',
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
        delete_trades = options['delete_trades']
        delimiter = options['delimiter']
        output_path = options['output']

        self._tee = TeeWriter(self.stdout, output_path)
        if output_path:
            self._tee.write(f'Output also saved to: {output_path}')

        mode = 'LIVE' if execute else 'DRY-RUN'
        self._tee.write(self.style.WARNING(f'\n=== delete_security_labels [{mode}] ===\n'))

        names = self._read_csv(csv_path, delimiter)
        if not names:
            self._tee.close()
            raise CommandError('No security names found in the CSV file.')

        self._tee.write(f'Loaded {len(names)} security name(s) from {csv_path}\n')
        for n in names:
            self._tee.write(f'  • {n!r}')
        self._tee.write('')

        if not execute:
            self._tee.write(self.style.WARNING(
                'DRY-RUN — no rows deleted. Re-run with --execute to apply.\n'
            ))
            self._show_counts(names, delete_trades)
        else:
            self._apply(names, delete_trades)

        self._tee.close()

    # ------------------------------------------------------------------

    def _read_csv(self, path: str, delimiter: str):
        names = []
        try:
            with open(path, newline='', encoding='utf-8-sig') as fh:
                reader = csv.reader(fh, delimiter=delimiter)
                for i, row in enumerate(reader):
                    if not row:
                        continue
                    name = row[0].strip()
                    if not name:
                        continue
                    # Skip header row
                    if i == 0 and name.lower() in _HEADER_VALUES:
                        continue
                    names.append(name)
        except FileNotFoundError:
            raise CommandError(f'CSV file not found: {path}')
        except Exception as e:
            raise CommandError(f'Error reading CSV: {e}')
        return names

    def _count(self, table: str, name: str) -> int:
        try:
            q = f"SELECT COUNT(*) AS cnt FROM {table} WHERE security_label = '{_esc(name)}'"
            rows = impala_manager.execute_query(q, database=DATABASE)
            return int(rows[0]['cnt']) if rows else 0
        except Exception as e:
            logger.warning(f'Count query failed for table={table} name={name!r}: {e}')
            return -1

    def _show_counts(self, names, delete_trades: bool):
        self._tee.write(self.style.HTTP_INFO('\nRow counts per security:\n'))
        total_pos = 0
        total_trade = 0
        no_match = []

        for name in names:
            pos_cnt = self._count(POSITION_TABLE, name)
            trade_cnt = self._count(TRADE_TABLE, name) if delete_trades else None

            total_pos += pos_cnt if pos_cnt > 0 else 0
            if trade_cnt is not None and trade_cnt > 0:
                total_trade += trade_cnt

            trade_col = f'  trades={trade_cnt}' if delete_trades else ''
            if pos_cnt == 0:
                no_match.append(name)
                self._tee.write(self.style.WARNING(
                    f'  {name!r:<60}  positions={pos_cnt}{trade_col}  *** NO MATCH ***'
                ))
            else:
                self._tee.write(f'  {name!r:<60}  positions={pos_cnt}{trade_col}')

        self._tee.write(f'\nTOTAL position rows to delete : {total_pos}')
        if delete_trades:
            self._tee.write(f'TOTAL trade rows to delete    : {total_trade}')
        if no_match:
            self._tee.write(self.style.WARNING(
                f'\n{len(no_match)} security name(s) had NO MATCH in cis_position — check spelling:'
            ))
            for n in no_match:
                self._tee.write(self.style.WARNING(f'  • {n!r}'))

    def _apply(self, names, delete_trades: bool):
        total_pos = 0
        total_trade = 0
        errors = []

        for name in names:
            pos_before = self._count(POSITION_TABLE, name)
            if pos_before == 0:
                self._tee.write(self.style.WARNING(f'  SKIP (0 rows in position): {name!r}'))
            else:
                try:
                    q = f"DELETE FROM {POSITION_TABLE} WHERE security_label = '{_esc(name)}'"
                    ok = impala_manager.execute_write(q, database=DATABASE)
                    if ok:
                        total_pos += pos_before
                        self._tee.write(
                            self.style.SUCCESS(f'  OK position ({pos_before:>4} rows deleted): {name!r}')
                        )
                    else:
                        errors.append(f'position DELETE returned False: {name!r}')
                        self._tee.write(self.style.ERROR(f'  FAIL position: {name!r}'))
                except Exception as e:
                    errors.append(f'position DELETE error for {name!r}: {e}')
                    self._tee.write(self.style.ERROR(f'  ERROR position {name!r}: {e}'))

            if delete_trades:
                trade_before = self._count(TRADE_TABLE, name)
                if trade_before == 0:
                    self._tee.write(self.style.WARNING(f'  SKIP (0 rows in trade): {name!r}'))
                else:
                    try:
                        q = f"DELETE FROM {TRADE_TABLE} WHERE security_label = '{_esc(name)}'"
                        ok = impala_manager.execute_write(q, database=DATABASE)
                        if ok:
                            total_trade += trade_before
                            self._tee.write(
                                self.style.SUCCESS(f'  OK trade    ({trade_before:>4} rows deleted): {name!r}')
                            )
                        else:
                            errors.append(f'trade DELETE returned False: {name!r}')
                            self._tee.write(self.style.ERROR(f'  FAIL trade: {name!r}'))
                    except Exception as e:
                        errors.append(f'trade DELETE error for {name!r}: {e}')
                        self._tee.write(self.style.ERROR(f'  ERROR trade {name!r}: {e}'))

        self._tee.write('\n' + '=' * 60)
        self._tee.write(self.style.SUCCESS(f'Done. Deleted {total_pos} position row(s).'))
        if delete_trades:
            self._tee.write(self.style.SUCCESS(f'      Deleted {total_trade} trade row(s).'))

        if errors:
            self._tee.write(self.style.ERROR(f'\n{len(errors)} error(s):'))
            for e in errors:
                self._tee.write(self.style.ERROR(f'  • {e}'))
            sys.exit(1)
