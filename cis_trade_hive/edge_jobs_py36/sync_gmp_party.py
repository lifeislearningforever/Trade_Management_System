"""
Django-free Management Command: Sync GMP Party

Reads party/counterparty master data from the GMP source table
(gmp_cis_sta_dly_party) and upserts into cis_party.

GMP table columns (gmp_cis_sta_dly_party):
    counterparty_short_name / counterparty_full_name - party identity
    record_type, address_line0..3, city, country, postal_code
    fax, telex, primary_contact, primary_number, other_contact, other_number
    industry, industry_group
    is_broker, is_custodian, is_issuer, is_bank, is_subsidiate (sic — GMP source
        spelling), is_corporate, is_financial_institute, is_other  (all 'Y'/'N')
    subsidiary_level, counterparty_grand_parent, counterparty_parent
    mas_industry_code, country_of_incorporation, cels_code
    src_system, sub_system, data_cat, data_frq, processing_date

Usage:
    python sync_gmp_party.py --env SIT --processing-date 20260227
    python sync_gmp_party.py --dry-run --verbose

Run schedule: Daily after GMP ETL job completes (before sync_gmp_party_cif.py).

Pipeline:
    GMP ETL -> gmp_cis_sta_dly_party
                   |  (this command)
           cis_party (src_system='GMP', status='VALIDATED')
"""

import os
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _apply_early_env_override(argv):
    """--env must be applied before importing lib.config/lib.impala_connection
    below -- see sync_gmp_corporate_actions.py for the full rationale."""
    for i, arg in enumerate(argv):
        if arg == '--env' and i + 1 < len(argv):
            os.environ['CIS_ENV'] = argv[i + 1].upper()
            return
        if arg.startswith('--env='):
            os.environ['CIS_ENV'] = arg.split('=', 1)[1].upper()
            return


_apply_early_env_override(sys.argv)

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from lib.management_base import BaseCommand, CommandError, run_command

from lib.impala_connection import impala_manager
from lib.party_repository import party_repository, PartyRepository
from lib.config import settings

logger = logging.getLogger(__name__)

GMP_DATABASE = settings.IMPALA_CONFIG['DATABASE']
GMP_SOURCE_TABLE = 'gmp_cis_sta_dly_party'


def _yn_to_bool(val: Any) -> bool:
    """GMP boolean flags are 'Y'/'N' strings."""
    return bool(val) and str(val).strip().upper() == 'Y'


class Command(BaseCommand):
    help = 'Sync party/counterparty master data from GMP source table into cis_party'

    def add_arguments(self, parser):
        parser.add_argument(
            '--env',
            type=str,
            default=None,
            choices=['LOCAL', 'SIT', 'UAT', 'PROD', 'DR'],
            help=(
                'Override CIS_ENV (Impala host/port/auth) for this run. '
                'NOTE: read directly from sys.argv before argparse runs '
                '(see _apply_early_env_override) -- declared here only so '
                'it shows up in --help and gets validated.'
            )
        )
        parser.add_argument(
            '--database',
            type=str,
            default=None,
            help='Override target Kudu database name (default: from CIS_ENV config, e.g. gmp_cis)'
        )
        parser.add_argument(
            '-d', '--date', '--processing-date',
            dest='date',
            type=str,
            default=None,
            help='Filter GMP records by processing_date (YYYY-MM-DD or YYYYMMDD). Default: latest available'
        )
        parser.add_argument(
            '-n', '--dry-run',
            action='store_true',
            help='Preview what would be synced without writing anything'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print each record processed'
        )
        parser.add_argument(
            '--user',
            type=str,
            default='GMP_ETL',
            help='User name to record as creator. Default: GMP_ETL'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=2000,
            help='Records per batch fetch from GMP table. Default: 2000'
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        global GMP_DATABASE

        env_override = options.get('env')
        database_override = options.get('database')
        processing_date = options['date']
        dry_run = options['dry_run']
        verbose = options['verbose']
        run_by = options['user']
        batch_size = options['batch_size']

        if database_override:
            GMP_DATABASE = database_override
            PartyRepository.DATABASE = database_override

        self._print_header(processing_date, dry_run, run_by, env_override, database_override)

        gmp_records = self._fetch_gmp_records(processing_date, batch_size)
        self.stdout.write(f'GMP records fetched  : {len(gmp_records)}')

        if not gmp_records:
            self.stdout.write(self.style.WARNING('No GMP party records found. Exiting.'))
            return

        stats = {'upserted': 0, 'skipped_invalid': 0, 'errors': 0}
        errors = []

        for row in gmp_records:
            result = self._process_row(row, run_by, dry_run, verbose)
            stats[result['outcome']] += 1
            if result.get('error'):
                errors.append(result['error'])

        self._print_summary(stats, errors, dry_run)

    # ------------------------------------------------------------------
    # Fetch from GMP source table, deduped to the latest row per
    # counterparty_short_name when processing_date isn't pinned.
    # ------------------------------------------------------------------
    def _fetch_gmp_records(self, processing_date: Optional[str], batch_size: int) -> List[Dict[str, Any]]:
        try:
            if processing_date:
                pd = processing_date.replace('-', '')
                date_clause = f"WHERE CAST(processing_date AS STRING) = '{pd}'"
            else:
                date_clause = f"""
                WHERE processing_date = (
                    SELECT MAX(processing_date) FROM {GMP_DATABASE}.{GMP_SOURCE_TABLE}
                )
                """

            query = f"""
            WITH stg_dedup AS (
                SELECT stg.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY stg.counterparty_short_name
                        ORDER BY stg.processing_date DESC
                    ) AS rn
                FROM {GMP_DATABASE}.{GMP_SOURCE_TABLE} stg
                {date_clause}
                AND UPPER(stg.src_system) = 'GMP'
            )
            SELECT
                counterparty_short_name, counterparty_full_name, record_type,
                address_line0, address_line1, address_line2, address_line3,
                city, country, postal_code,
                fax, telex, primary_contact, primary_number, other_contact, other_number,
                industry, industry_group,
                is_broker, is_custodian, is_issuer, is_bank, is_subsidiate,
                is_corporate, is_financial_institute, is_other,
                subsidiary_level, counterparty_grand_parent, counterparty_parent,
                mas_industry_code, country_of_incorporation, cels_code,
                src_system, sub_system, data_cat, data_frq, processing_date
            FROM stg_dedup
            WHERE rn = 1
            LIMIT {batch_size}
            """

            result = impala_manager.execute_query(query, database=GMP_DATABASE)
            return result if result else []

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error fetching GMP records: {e}'))
            logger.error(f'Error fetching GMP records: {e}')
            return []

    # ------------------------------------------------------------------
    # Process a single GMP row
    # ------------------------------------------------------------------
    def _process_row(self, row: Dict[str, Any], run_by: str, dry_run: bool, verbose: bool) -> Dict[str, Any]:
        party_short_name = row.get('counterparty_short_name', '')

        if not party_short_name:
            msg = 'Skipping row: missing counterparty_short_name'
            if verbose:
                self.stdout.write(self.style.WARNING(f'  [INVALID] {msg}'))
            return {'outcome': 'skipped_invalid', 'error': msg}

        if verbose:
            self.stdout.write(f'  [SYNC] {party_short_name}')

        if dry_run:
            return {'outcome': 'upserted'}

        party_data = {
            'party_short_name':          party_short_name,
            'party_full_name':           row.get('counterparty_full_name'),
            'record_type':               row.get('record_type'),
            'address_line_0':            row.get('address_line0'),
            'address_line_1':            row.get('address_line1'),
            'address_line_2':            row.get('address_line2'),
            'address_line_3':            row.get('address_line3'),
            'city':                      row.get('city'),
            'country':                   row.get('country'),
            'postal_code':               row.get('postal_code'),
            'fax_number':                row.get('fax'),
            'telex_number':              row.get('telex'),
            'primary_contact':           row.get('primary_contact'),
            'primary_number':            row.get('primary_number'),
            'other_contact':             row.get('other_contact'),
            'other_number':              row.get('other_number'),
            'industry':                  row.get('industry'),
            'industry_group':            row.get('industry_group'),
            'is_broker':                 _yn_to_bool(row.get('is_broker')),
            'is_custodian':              _yn_to_bool(row.get('is_custodian')),
            'is_issuer':                 _yn_to_bool(row.get('is_issuer')),
            'is_bank':                   _yn_to_bool(row.get('is_bank')),
            'is_subsidiary':             _yn_to_bool(row.get('is_subsidiate')),
            'is_corporate':              _yn_to_bool(row.get('is_corporate')),
            'is_financial_institute':    _yn_to_bool(row.get('is_financial_institute')),
            'is_other':                  _yn_to_bool(row.get('is_other')),
            'subsidiary_level':          row.get('subsidiary_level'),
            'party_grandparent':         row.get('counterparty_grand_parent'),
            'party_parent':              row.get('counterparty_parent'),
            'mas_industry_code':         row.get('mas_industry_code'),
            'country_of_incorporation':  row.get('country_of_incorporation'),
            'cels_code':                 row.get('cels_code'),
            'src_system':                'GMP',
            'sub_system':                row.get('sub_system'),
            'data_cat':                  row.get('data_cat'),
            'data_frq':                  row.get('data_frq'),
            'processing_date':           row.get('processing_date'),
            'status':                    'VALIDATED',
            'is_active':                 True,
            'is_deleted':                False,
            'created_by':                run_by,
            'updated_by':                run_by,
            # PartyRepository.upsert() only checks *presence* of these keys
            # (it always emits the literal NOW() regardless of the value) --
            # True is just a presence marker, not a real timestamp value.
            'created_at':                True,
            'updated_at':                True,
        }

        try:
            success = party_repository.upsert(party_data)
        except Exception as e:
            msg = f'DB error upserting {party_short_name}: {e}'
            logger.error(msg)
            return {'outcome': 'errors', 'error': msg}

        if not success:
            msg = f'Upsert failed for {party_short_name}'
            return {'outcome': 'errors', 'error': msg}

        return {'outcome': 'upserted'}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _print_header(self, processing_date, dry_run, run_by, env_override=None, database_override=None):
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('  CIS Trade Hive — GMP Party Sync'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(f'Started      : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'Run by       : {run_by}')
        self.stdout.write(f'CIS_ENV      : {os.environ.get("CIS_ENV", "LOCAL")}' + (' (overridden)' if env_override else ''))
        self.stdout.write(f'Source table : {GMP_DATABASE}.{GMP_SOURCE_TABLE}')
        self.stdout.write(f'Target table : {GMP_DATABASE}.cis_party' + (' (overridden)' if database_override else ''))
        if processing_date:
            self.stdout.write(f'Date filter  : {processing_date}')
        else:
            self.stdout.write('Date filter  : latest processing_date per party')
        if dry_run:
            self.stdout.write(self.style.WARNING('Mode         : DRY RUN (no writes)'))
        self.stdout.write('')

    def _print_summary(self, stats, errors, dry_run):
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('─' * 70))
        self.stdout.write(self.style.HTTP_INFO('  Summary'))
        self.stdout.write(self.style.HTTP_INFO('─' * 70))
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(f'{prefix}Upserted into cis_party : {stats["upserted"]}')
        self.stdout.write(f'Skipped (invalid)        : {stats["skipped_invalid"]}')
        self.stdout.write(f'Errors                   : {stats["errors"]}')

        if errors:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR('Errors:'))
            for e in errors[:20]:
                self.stdout.write(self.style.ERROR(f'  • {e}'))
            if len(errors) > 20:
                self.stdout.write(self.style.ERROR(f'  ... and {len(errors) - 20} more'))

        self.stdout.write('')
        if stats['upserted'] > 0 and not dry_run:
            self.stdout.write(self.style.SUCCESS(
                '✓ Sync complete. Run sync_gmp_party_cif.py next to sync party CIF records.'
            ))
        self.stdout.write(f'Finished     : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))


if __name__ == '__main__':
    run_command(Command)
