"""
Management command: delete_security_labels

Bulk-delete rows from cis_security by security_name, using a single-column CSV.

Usage:
    # Dry run — shows row counts, writes nothing
    python manage.py delete_security_labels --csv securities.csv --dry-run

    # Dry run and save output to file
    python manage.py delete_security_labels --csv securities.csv --dry-run --output dry_run.txt

    # Live run
    python manage.py delete_security_labels --csv securities.csv --execute

    # Live run + save log
    python manage.py delete_security_labels --csv securities.csv --execute --output result.txt

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
from django.conf import settings

logger = logging.getLogger(__name__)

DATABASE = settings.IMPALA_CONFIG['DATABASE']
SECURITY_TABLE = f'{DATABASE}.cis_security'

_HEADER_VALUES = {
    'security_name', 'security_label', 'name', 'security', 'label',
    'security name', 'security label',
}


def _esc(val: str) -> str:
    return val.replace('\x00', '').replace('\\', '\\\\').replace("'", "\\'")


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
        'Bulk-delete rows from cis_security by security_name using a single-column CSV. '
        'Dry-run unless --execute is passed.'
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
            self._show_counts(names)
        else:
            self._apply(names)

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
                    if i == 0 and name.lower() in _HEADER_VALUES:
                        continue
                    names.append(name)
        except FileNotFoundError:
            raise CommandError(f'CSV file not found: {path}')
        except Exception as e:
            raise CommandError(f'Error reading CSV: {e}')
        return names

    def _count(self, name: str) -> int:
        try:
            q = f"SELECT COUNT(*) AS cnt FROM {SECURITY_TABLE} WHERE security_name = '{_esc(name)}'"
            rows = impala_manager.execute_query(q, database=DATABASE)
            return int(rows[0]['cnt']) if rows else 0
        except Exception as e:
            logger.warning(f'Count query failed for name={name!r}: {e}')
            return -1

    def _show_counts(self, names):
        self._tee.write(self.style.HTTP_INFO('\nRow counts per security:\n'))
        total = 0
        no_match = []

        for name in names:
            cnt = self._count(name)
            total += cnt if cnt > 0 else 0
            if cnt == 0:
                no_match.append(name)
                self._tee.write(self.style.WARNING(
                    f'  {name!r:<60}  rows={cnt}  *** NO MATCH ***'
                ))
            else:
                self._tee.write(f'  {name!r:<60}  rows={cnt}')

        self._tee.write(f'\nTOTAL cis_security rows to delete: {total}')
        if no_match:
            self._tee.write(self.style.WARNING(
                f'\n{len(no_match)} name(s) had NO MATCH in cis_security — check spelling:'
            ))
            for n in no_match:
                self._tee.write(self.style.WARNING(f'  • {n!r}'))

    def _apply(self, names):
        total = 0
        errors = []

        for name in names:
            before = self._count(name)
            if before == 0:
                self._tee.write(self.style.WARNING(f'  SKIP (0 rows): {name!r}'))
                continue
            try:
                q = f"DELETE FROM {SECURITY_TABLE} WHERE security_name = '{_esc(name)}'"
                ok = impala_manager.execute_write(q, database=DATABASE)
                if ok:
                    total += before
                    self._tee.write(
                        self.style.SUCCESS(f'  OK ({before:>4} rows deleted): {name!r}')
                    )
                else:
                    errors.append(f'DELETE returned False: {name!r}')
                    self._tee.write(self.style.ERROR(f'  FAIL: {name!r}'))
            except Exception as e:
                errors.append(f'DELETE error for {name!r}: {e}')
                self._tee.write(self.style.ERROR(f'  ERROR {name!r}: {e}'))

        self._tee.write('\n' + '=' * 60)
        self._tee.write(self.style.SUCCESS(f'Done. Deleted {total} cis_security row(s).'))

        if errors:
            self._tee.write(self.style.ERROR(f'\n{len(errors)} error(s):'))
            for e in errors:
                self._tee.write(self.style.ERROR(f'  • {e}'))
            sys.exit(1)
