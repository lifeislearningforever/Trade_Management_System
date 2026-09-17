"""
Django-free Management Command: Sync GMP Party CIF

Reads party CIF data from the GMP source table (gmp_cis_sta_dly_party_cif)
and upserts into cis_party_cif.

GMP table columns (gmp_cis_sta_dly_party_cif):
    party_name / counterparty_short_name - joins to cis_party.party_short_name
    m_label            - CIF label (auto-generated from party+country if blank)
    country            - Country code
    isin               - ISIN associated with this CIF (NOT `cif` -- see note below)
    description        - CIF description
    record_type        - GMP record type
    src_system         - 'gmp'
    sub_system         - 'cis'
    data_cat           - 'sta'
    data_frq            - 'dly'
    src_id             - Source table name
    processing_date    - GMP processing date (YYYYMMDD)

Note: an earlier draft of this sync referenced a `cif` column, but the live
cis_party_cif schema (verified against sql/ddl/77_cis_party_cif_fix_primary_key.sql
and reference_data/repositories/party_cif_repository.py) uses `isin`.

Usage:
    python sync_gmp_party_cif.py --env SIT --processing-date 20260227
    python sync_gmp_party_cif.py --dry-run --verbose

Run schedule: Daily after GMP ETL job completes (after sync_gmp_party.py).

Pipeline:
    GMP ETL -> gmp_cis_sta_dly_party_cif
                   |  (this command)
           cis_party_cif (src_system='GMP', status via record dedup on latest processing_date)
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
from lib.party_cif_repository import party_cif_repository, PartyCifRepository
from lib.config import settings

logger = logging.getLogger(__name__)

GMP_DATABASE = settings.IMPALA_CONFIG['DATABASE']
GMP_SOURCE_TABLE = 'gmp_cis_sta_dly_party_cif'


class Command(BaseCommand):
    help = 'Sync party CIF records from GMP source table into cis_party_cif'

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
            PartyCifRepository.DATABASE = database_override

        self._print_header(processing_date, dry_run, run_by, env_override, database_override)

        gmp_records = self._fetch_gmp_records(processing_date, batch_size)
        self.stdout.write(f'GMP records fetched  : {len(gmp_records)}')

        if not gmp_records:
            self.stdout.write(self.style.WARNING('No GMP party CIF records found. Exiting.'))
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
    # (party_name, m_label, country) when processing_date isn't pinned.
    # ------------------------------------------------------------------
    def _fetch_gmp_records(self, processing_date: Optional[str], batch_size: int) -> List[Dict[str, Any]]:
        try:
            date_clause = ''
            if processing_date:
                pd = processing_date.replace('-', '')
                date_clause = f"AND CAST(stg.processing_date AS STRING) = '{pd}'"
            else:
                date_clause = f"""
                AND stg.processing_date = (
                    SELECT MAX(processing_date) FROM {GMP_DATABASE}.{GMP_SOURCE_TABLE}
                )
                """

            query = f"""
            WITH stg_dedup AS (
                SELECT stg.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY stg.counterparty_short_name, stg.country
                        ORDER BY stg.processing_date DESC
                    ) AS rn
                FROM {GMP_DATABASE}.{GMP_SOURCE_TABLE} stg
                WHERE 1=1 {date_clause}
            )
            SELECT
                counterparty_short_name AS party_name,
                m_label,
                country,
                isin,
                description,
                record_type,
                src_system,
                sub_system,
                data_cat,
                data_frq,
                src_id,
                processing_date
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
        party_name = row.get('party_name', '')
        country = row.get('country', '')

        if not party_name:
            msg = 'Skipping row: missing party_name'
            if verbose:
                self.stdout.write(self.style.WARNING(f'  [INVALID] {msg}'))
            return {'outcome': 'skipped_invalid', 'error': msg}

        m_label = row.get('m_label') or f"{party_name}_{country}" if country else party_name

        if verbose:
            self.stdout.write(f'  [SYNC] {party_name} | {m_label} | {country}')

        if dry_run:
            return {'outcome': 'upserted'}

        cif_data = {
            'party_name':       party_name,
            'm_label':          m_label,
            'country':          country,
            'isin':             row.get('isin'),
            'description':      row.get('description'),
            'record_type':      row.get('record_type'),
            'src_system':       'GMP',
            'sub_system':       row.get('sub_system'),
            'data_cat':         row.get('data_cat'),
            'data_frq':         row.get('data_frq'),
            'src_id':           row.get('src_id'),
            'processing_date':  row.get('processing_date'),
            'is_active':        True,
            'is_deleted':       False,
            'created_by':       run_by,
            'updated_by':       run_by,
        }

        try:
            success = party_cif_repository.upsert(cif_data)
        except Exception as e:
            msg = f'DB error upserting {party_name}/{m_label}/{country}: {e}'
            logger.error(msg)
            return {'outcome': 'errors', 'error': msg}

        if not success:
            msg = f'Upsert failed for {party_name}/{m_label}/{country}'
            return {'outcome': 'errors', 'error': msg}

        return {'outcome': 'upserted'}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _print_header(self, processing_date, dry_run, run_by, env_override=None, database_override=None):
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('  CIS Trade Hive — GMP Party CIF Sync'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(f'Started      : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'Run by       : {run_by}')
        self.stdout.write(f'CIS_ENV      : {os.environ.get("CIS_ENV", "LOCAL")}' + (' (overridden)' if env_override else ''))
        self.stdout.write(f'Source table : {GMP_DATABASE}.{GMP_SOURCE_TABLE}')
        self.stdout.write(f'Target table : {GMP_DATABASE}.cis_party_cif' + (' (overridden)' if database_override else ''))
        if processing_date:
            self.stdout.write(f'Date filter  : {processing_date}')
        else:
            self.stdout.write('Date filter  : latest processing_date per (party_name, country)')
        if dry_run:
            self.stdout.write(self.style.WARNING('Mode         : DRY RUN (no writes)'))
        self.stdout.write('')

    def _print_summary(self, stats, errors, dry_run):
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('─' * 70))
        self.stdout.write(self.style.HTTP_INFO('  Summary'))
        self.stdout.write(self.style.HTTP_INFO('─' * 70))
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(f'{prefix}Upserted into cis_party_cif : {stats["upserted"]}')
        self.stdout.write(f'Skipped (invalid)            : {stats["skipped_invalid"]}')
        self.stdout.write(f'Errors                       : {stats["errors"]}')

        if errors:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR('Errors:'))
            for e in errors[:20]:
                self.stdout.write(self.style.ERROR(f'  • {e}'))
            if len(errors) > 20:
                self.stdout.write(self.style.ERROR(f'  ... and {len(errors) - 20} more'))

        self.stdout.write('')
        self.stdout.write(f'Finished     : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))


if __name__ == '__main__':
    run_command(Command)
