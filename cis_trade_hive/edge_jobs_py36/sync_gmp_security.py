"""
Django-free Management Command: Sync GMP Security

Reads security master data from the GMP source table
(gmp_cis_sta_dly_security) and upserts into cis_security via the same
stable security_id registry the live CIS app uses (see
lib/security_repository.py -- NOT a raw hash of security_label, which
would create IDs incompatible with securities also touched via the UI).

GMP table columns (gmp_cis_sta_dly_security), source -> cis_security target:
    security_label        -> security_name (+ dedup/partition key)
    isin                  -> isin
    security_full_name    -> security_description
    issuer_name           -> issuer
    ticker                -> ticker
    industry              -> industry
    security_type         -> security_type
    quoted_unquoted        -> quoted_unquoted ('Quoted'/'Unquoted', upper-cased)
    country                -> country_of_incorporation
    cntry_exch             -> country_of_exchange
    country_issue          -> country_of_issue
    cntry_pri_exch         -> country_of_primary_exchange
    exchange_code          -> exchange_code
    currency_code          -> currency_code
    shares_outstanding     -> shares_outstanding
    m_beta                 -> beta
    m_par_value            -> par_value
    m_pcthld1/2/3          -> pct_hld_entity_1/2/3
    m_pcthld_agg           -> pct_hld_entity_aggr
    m_subst                -> substantial_10_pct
    m_pevc_s32             -> pevc_s32_devest
    m_s32_repres           -> s32_representative
    m_biv_fund             -> base_liv_fund   (target column spelling per the
                                                live repository code, verified
                                                against security_hive_repository.py
                                                -- NOT "basel_iv_fund", which is
                                                what the source DDL snapshot uses)
    mas643                 -> mas_643_entity_type
    m_buh                  -> business_unit_head
    m_picharge             -> person_in_charge
    m_c_nc_ind             -> core_noncore
    m_f_indf_ind           -> fund_index_fund
    m_ml_class             -> management_limit_classification
    m_rel_index            -> relative_index
    is_active ('true'/'false' string) -> is_active (BOOLEAN)
    market, security_sub_type, security_investment, udf_country_issue,
    fintech_speculative, unlistedeq_speculative, related_company, approved_s32
        -> same-named target columns
    processing_date        -> dedup/filter only, not stored

Not present in GMP source (left NULL): investment_type, issuer_type,
mas_6d_code, fin_nonfin_ind, price_source.

Usage:
    python sync_gmp_security.py --env SIT --processing-date 20260227
    python sync_gmp_security.py --dry-run --verbose

Run schedule: Daily after GMP ETL job completes (before sync_gmp_equity_price.py,
since equity price sync joins against this table for currency_code/isin).

Pipeline:
    GMP ETL -> gmp_cis_sta_dly_security
                   |  (this command)
           cis_security (src_system='GMP', status='VALIDATED')
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
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from lib.management_base import BaseCommand, CommandError, run_command

from lib.impala_connection import impala_manager
from lib.security_repository import security_repository, SecurityRepository
from lib.config import settings

logger = logging.getLogger(__name__)

GMP_DATABASE = settings.IMPALA_CONFIG['DATABASE']
GMP_SOURCE_TABLE = 'gmp_cis_sta_dly_security'


def _parse_int(val: Any) -> Optional[int]:
    if val is None or str(val).strip() in ('', 'None', 'null', 'NULL'):
        return None
    try:
        return int(Decimal(str(val).strip()))
    except InvalidOperation:
        return None


def _parse_decimal(val: Any) -> Optional[Decimal]:
    if val is None or str(val).strip() in ('', 'None', 'null', 'NULL'):
        return None
    try:
        return Decimal(str(val).strip())
    except InvalidOperation:
        return None


def _parse_bool(val: Any) -> Optional[bool]:
    if val is None:
        return None
    s = str(val).strip().lower()
    if s == 'true':
        return True
    if s == 'false':
        return False
    return None


def _normalize_quoted_unquoted(val: Any) -> Optional[str]:
    if not val:
        return None
    s = str(val).strip()
    if s.lower() == 'quoted':
        return 'QUOTED'
    if s.lower() == 'unquoted':
        return 'UNQUOTED'
    return s.upper()


class Command(BaseCommand):
    help = 'Sync security master data from GMP source table into cis_security'

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
            SecurityRepository.DATABASE = database_override

        self._print_header(processing_date, dry_run, run_by, env_override, database_override)

        gmp_records = self._fetch_gmp_records(processing_date, batch_size)
        self.stdout.write(f'GMP records fetched  : {len(gmp_records)}')

        if not gmp_records:
            self.stdout.write(self.style.WARNING('No GMP security records found. Exiting.'))
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
    # security_label when processing_date isn't pinned.
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
                        PARTITION BY stg.security_label
                        ORDER BY stg.processing_date DESC
                    ) AS rn
                FROM {GMP_DATABASE}.{GMP_SOURCE_TABLE} stg
                {date_clause}
            )
            SELECT
                security_label, isin, security_full_name, issuer_name, ticker,
                industry, security_type, quoted_unquoted,
                country, cntry_exch, country_issue, cntry_pri_exch,
                exchange_code, currency_code, shares_outstanding,
                m_beta, m_par_value,
                m_pcthld1, m_pcthld2, m_pcthld3, m_pcthld_agg,
                m_subst, m_pevc_s32, m_s32_repres, m_biv_fund, mas643,
                m_buh, m_picharge, m_c_nc_ind, m_f_indf_ind, m_ml_class, m_rel_index,
                is_active, market, security_sub_type, security_investment,
                udf_country_issue, fintech_speculative, unlistedeq_speculative,
                related_company, approved_s32
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
        security_label = row.get('security_label', '')

        if not security_label:
            msg = 'Skipping row: missing security_label'
            if verbose:
                self.stdout.write(self.style.WARNING(f'  [INVALID] {msg}'))
            return {'outcome': 'skipped_invalid', 'error': msg}

        if verbose:
            self.stdout.write(f'  [SYNC] {security_label} | {row.get("isin")} | {row.get("exchange_code")}')

        if dry_run:
            return {'outcome': 'upserted'}

        security_data = {
            'security_name':                 security_label,
            'isin':                           row.get('isin'),
            'security_description':          row.get('security_full_name'),
            'issuer':                         row.get('issuer_name'),
            'ticker':                         row.get('ticker'),
            'industry':                       row.get('industry'),
            'security_type':                  row.get('security_type'),
            'quoted_unquoted':                _normalize_quoted_unquoted(row.get('quoted_unquoted')),
            'country_of_incorporation':       row.get('country'),
            'country_of_exchange':            row.get('cntry_exch'),
            'country_of_issue':               row.get('country_issue'),
            'country_of_primary_exchange':    row.get('cntry_pri_exch'),
            'exchange_code':                  row.get('exchange_code'),
            'currency_code':                  row.get('currency_code'),
            'shares_outstanding':             _parse_int(row.get('shares_outstanding')),
            'beta':                           _parse_decimal(row.get('m_beta')),
            'par_value':                      _parse_decimal(row.get('m_par_value')),
            'pct_hld_entity_1':               row.get('m_pcthld1'),
            'pct_hld_entity_2':               row.get('m_pcthld2'),
            'pct_hld_entity_3':               row.get('m_pcthld3'),
            'pct_hld_entity_aggr':            row.get('m_pcthld_agg'),
            'substantial_10_pct':             row.get('m_subst'),
            'pevc_s32_devest':                row.get('m_pevc_s32'),
            's32_representative':             row.get('m_s32_repres'),
            'base_liv_fund':                  row.get('m_biv_fund'),
            'mas_643_entity_type':            row.get('mas643'),
            'business_unit_head':             row.get('m_buh'),
            'person_in_charge':               row.get('m_picharge'),
            'core_noncore':                   row.get('m_c_nc_ind'),
            'fund_index_fund':                row.get('m_f_indf_ind'),
            'management_limit_classification': row.get('m_ml_class'),
            'relative_index':                 row.get('m_rel_index'),
            'market':                         row.get('market'),
            'security_sub_type':              row.get('security_sub_type'),
            'security_investment':            row.get('security_investment'),
            'udf_country_issue':              row.get('udf_country_issue'),
            'fintech_speculative':            row.get('fintech_speculative'),
            'unlistedeq_speculative':         row.get('unlistedeq_speculative'),
            'related_company':                row.get('related_company'),
            'approved_s32':                   row.get('approved_s32'),
            'status':                         'VALIDATED',
            'src_system':                     'GMP',
            # GMP's is_active is a 'true'/'false' string; default to active
            # when the source value is missing/unparseable rather than
            # silently writing a NULL is_active flag.
            'is_active':                      _parse_bool(row.get('is_active')) if _parse_bool(row.get('is_active')) is not None else True,
        }

        try:
            success = security_repository.upsert_security(security_data, created_by=run_by)
        except Exception as e:
            msg = f'DB error upserting {security_label}: {e}'
            logger.error(msg)
            return {'outcome': 'errors', 'error': msg}

        if not success:
            msg = f'Upsert failed for {security_label}'
            return {'outcome': 'errors', 'error': msg}

        return {'outcome': 'upserted'}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _print_header(self, processing_date, dry_run, run_by, env_override=None, database_override=None):
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('  CIS Trade Hive — GMP Security Sync'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(f'Started      : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'Run by       : {run_by}')
        self.stdout.write(f'CIS_ENV      : {os.environ.get("CIS_ENV", "LOCAL")}' + (' (overridden)' if env_override else ''))
        self.stdout.write(f'Source table : {GMP_DATABASE}.{GMP_SOURCE_TABLE}')
        self.stdout.write(f'Target table : {GMP_DATABASE}.cis_security' + (' (overridden)' if database_override else ''))
        if processing_date:
            self.stdout.write(f'Date filter  : {processing_date}')
        else:
            self.stdout.write('Date filter  : latest processing_date per security')
        if dry_run:
            self.stdout.write(self.style.WARNING('Mode         : DRY RUN (no writes)'))
        self.stdout.write('')

    def _print_summary(self, stats, errors, dry_run):
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('─' * 70))
        self.stdout.write(self.style.HTTP_INFO('  Summary'))
        self.stdout.write(self.style.HTTP_INFO('─' * 70))
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(f'{prefix}Upserted into cis_security : {stats["upserted"]}')
        self.stdout.write(f'Skipped (invalid)           : {stats["skipped_invalid"]}')
        self.stdout.write(f'Errors                      : {stats["errors"]}')

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
                '✓ Sync complete. Run sync_gmp_equity_price.py next -- it joins '
                'against cis_security for currency_code/isin.'
            ))
        self.stdout.write(f'Finished     : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))


if __name__ == '__main__':
    run_command(Command)
