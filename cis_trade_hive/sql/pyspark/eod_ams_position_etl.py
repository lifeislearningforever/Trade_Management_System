"""
EOD AMS/GMP Position ETL Job
=============================
Standalone backend script — no Django dependency.
Runs the same 7-step position pipeline as upload_service.run_position_etl()
but for the AMS_STREET and GMP source tables instead of user-uploaded files.

Source tables (all STRING columns, partitioned by processing_date):
  AMS_STREET:
  1. gmp_cis_sta_dly_ams_multi_dis_cif           (AMS Multi Discretionary Fund)
  2. gmp_cis_sta_dly_ams_multi_hold              (AMS Multiple Holdings Daily)
  3. gmp_cis_sta_dly_stat_street_ams_iceq        (AMS ICEQ Daily)
  4. gmp_cis_sta_mthly_stat_street_ams_iceq_end  (AMS ICEQ Month End)
  5. gmp_cis_sta_dly_stat_street_ams_daily_limit (AMS S31 UOI Daily Limit)

  GMP:
  6. gmp_cis_sta_dly_position                    (GMP Daily Position — m_* column prefix)

Pipeline:
  Step 0  — standardize each source table → position_upload_standardized
  Step 1  — build pos_stage_1_base (decimal casts, date normalisation)
  Step 2  — portfolio validation vs cis_portfolio
  Step 3  — security ISIN match vs cis_security
  Step 4  — security fallback (full_name / short_name / ticker)
  Step 5  — equity price lookup from cis_equity_price
  Step 5B — auto-create new securities (NOT_FOUND with exchange present)
  Step 6  — consolidated staging (position_upload_staging)
  Step 7A — UPSERT into gmp_cis.cis_position (Kudu)
  Step 7B — INSERT OVERWRITE into gmp_cis.position_upload_report

Control-M / cron usage:
  python eod_ams_position_etl.py --processing-date 20260227
  python eod_ams_position_etl.py --processing-date 20260227 --source ams_iceq
  python eod_ams_position_etl.py --processing-date 20260227 --source gmp_position
  python eod_ams_position_etl.py --processing-date 20260227 --dry-run

The script connects to Impala via the same ImpalaConnectionManager used by
the Django app (reads IMPALA_* env vars or falls back to localhost:21050).

Author: CisTrade Team
"""

import argparse
import logging
import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Bootstrap: make the Django project importable without starting Django.
# Adjust BASE_DIR if the script moves.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Minimal Django settings so we can import app modules
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

from core.repositories.impala_connection import impala_manager  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s — %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('eod_ams_position_etl')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DB = 'gmp_cis'

# All source tables: name → metadata dict.
# position_basis=None means it is read from the source row (e.g. GMP's `line` column).
ALL_SOURCES = {
    'gmp_cis_sta_dly_ams_multi_dis_cif': {
        'position_basis': 'TRADED',
        'src_system':     'AMS_STREET',
        'description':    'AMS Multi Discretionary Fund',
    },
    'gmp_cis_sta_dly_ams_multi_hold': {
        'position_basis': 'TRADED',
        'src_system':     'AMS_STREET',
        'description':    'AMS Multiple Holdings Daily',
    },
    'gmp_cis_sta_dly_stat_street_ams_iceq': {
        'position_basis': 'TRADED',
        'src_system':     'AMS_STREET',
        'description':    'AMS ICEQ Daily',
    },
    'gmp_cis_sta_mthly_stat_street_ams_iceq_end': {
        'position_basis': 'SETTLED',
        'src_system':     'AMS_STREET',
        'description':    'AMS ICEQ Month End',
    },
    'gmp_cis_sta_dly_stat_street_ams_daily_limit': {
        'position_basis': 'TRADED',
        'src_system':     'AMS_STREET',
        'description':    'AMS S31 UOI Daily Limit',
    },
    'gmp_cis_sta_dly_position': {
        'position_basis': None,        # derived from `line` column in source
        'src_system':     'GMP',
        'description':    'GMP Daily Position (m_* columns)',
    },
}

# Keep backward-compatible alias for callers that still reference AMS_SOURCES
AMS_SOURCES = ALL_SOURCES

# Short alias → table name (for --source CLI arg)
SOURCE_ALIASES = {
    'ams_multi_dis':  'gmp_cis_sta_dly_ams_multi_dis_cif',
    'ams_multi_hold': 'gmp_cis_sta_dly_ams_multi_hold',
    'ams_iceq':       'gmp_cis_sta_dly_stat_street_ams_iceq',
    'ams_iceq_end':   'gmp_cis_sta_mthly_stat_street_ams_iceq_end',
    'ams_daily_limit':'gmp_cis_sta_dly_stat_street_ams_daily_limit',
    'gmp_position':   'gmp_cis_sta_dly_position',
    'all':            None,
}


# ---------------------------------------------------------------------------
# safe_decimal — identical to upload_service.py helper
# ---------------------------------------------------------------------------
def safe_decimal(col: str, dec_type: str) -> str:
    return (
        f"CAST(NULLIF(regexp_extract("
        f"regexp_replace("
        f"regexp_replace("
        f"regexp_replace("
        f"regexp_replace("
        f"TRIM(CAST({col} AS STRING)),"
        f" ',', ''),"
        f" '[\\\\$£€¥%]', ''),"
        f" '^\\\\(([0-9]+\\\\.?[0-9]*)\\\\)$', '-\\\\1'),"
        f" '^[-–—]+$', '0'),"
        f" '^-?[0-9]+(\\\\.?[0-9]*)?([eE][+-]?[0-9]+)?', 0),"
        f" '') AS {dec_type})"
    )


def normalize_ticker_suffix(col: str) -> str:
    """Generate SQL that rewrites ISO country suffixes to Bloomberg exchange suffixes.

    Examples:
      'DBS SG'  → 'DBS SP'   (Singapore ISO SG → Bloomberg SP)
      'MAY MY'  → 'MAY MK'   (Malaysia  ISO MY → Bloomberg MK)
      'DBS SP'  → 'DBS SP'   (already Bloomberg, unchanged)
      'NA'      → NULL        (placeholder stripped)
    """
    _ISO_TO_BB = {
        'SG': 'SP', 'MY': 'MK', 'ID': 'IJ', 'TH': 'TB', 'PH': 'PM',
        'IN': 'IS', 'CN': 'CH', 'TW': 'TT', 'KR': 'KS', 'JP': 'JT',
        'AU': 'AT', 'GB': 'LN', 'DE': 'GY', 'FR': 'FP', 'NL': 'NA',
        'CH': 'SW', 'SE': 'SS', 'DK': 'DC', 'FI': 'FH', 'IT': 'IM',
        'ES': 'SM', 'CA': 'CN', 'BR': 'BZ', 'MX': 'MM', 'AE': 'UH',
        'SA': 'AB', 'ZA': 'SJ',
    }
    _when_clauses = '\n    '.join(
        f"WHEN REGEXP_EXTRACT(UPPER(TRIM(CAST({col} AS STRING))), "
        f"'^(.+)\\\\s+{iso}$', 1) != '' "
        f"THEN CONCAT(REGEXP_EXTRACT(UPPER(TRIM(CAST({col} AS STRING))), "
        f"'^(.+)\\\\s+{iso}$', 1), ' {bb}')"
        for iso, bb in _ISO_TO_BB.items()
        if iso != bb
    )
    return (
        f"NULLIF(NULLIF(NULLIF(NULLIF(NULLIF(NULLIF(NULLIF("
        f"CASE\n    {_when_clauses}\n"
        f"    ELSE UPPER(TRIM(CAST({col} AS STRING)))\n"
        f"END,"
        f" 'NA'), 'N/A'), 'NIL'), 'NONE'), '-'), 'N.A.'), 'NAP')"
    )


# ---------------------------------------------------------------------------
# Step 0: standardization SQL per source table
# Mirrors the STANDARDIZE_SELECT dict in upload_service.run_position_etl()
# but for AMS_STREET / GMP tables.
# ---------------------------------------------------------------------------
def _standardize_sql(table: str, processing_date: str, src_id: str) -> str:
    pos_basis = ALL_SOURCES[table]['position_basis']
    src_sys   = ALL_SOURCES[table]['src_system']

    if table == 'gmp_cis_sta_dly_ams_multi_dis_cif':
        # PORTIARP-7367: AMS sends multiple rows per (portfolio, security, isin, country).
        # Aggregate by (portfolio_code, security_name, isin, country_code) so that one
        # consolidated row enters position_upload_standardized.  All quantity/value fields
        # are SUM'd (they are in FC = security currency).  Non-additive fields (price) use
        # MAX to carry a representative value through.
        return f"""
            SELECT
                portfolio_code                                          AS portfolio,
                security_name                                           AS security_full_name,
                NULL                                                    AS security_short_name,
                isin                                                    AS isin,
                NULL                                                    AS ticker,
                CAST(SUM({safe_decimal('quantity', 'DECIMAL(30,8)')})
                     AS DECIMAL(30,8))                                  AS quantity,
                CAST(NULL AS DECIMAL(30,8))                             AS shares_outstanding,
                CAST(NULL AS DECIMAL(30,8))                             AS shares_issued,
                CAST(NULL AS DECIMAL(10,6))                             AS pct_holding,
                CAST(NULL AS DECIMAL(30,8))                             AS market_price,
                CAST(NULL AS DECIMAL(30,8))                             AS average_cost,
                CAST(NULL AS DECIMAL(30,8))                             AS cost_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS market_value_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS unrealized_pnl_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS cost_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS market_value_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS unrealized_pnl_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_lc,
                NULL                                                    AS product_type,
                NULL                                                    AS security_type,
                NULL                                                    AS quoted_unquoted,
                NULL                                                    AS industry,
                NULL                                                    AS fin_nonfin_co,
                NULL                                                    AS issuer_type,
                NULL                                                    AS reits_or_fund_y_n,
                country_code                                            AS exchange,
                country_code                                            AS country_code,
                country_code                                            AS country_of_exchange,
                NULL                                                    AS country_of_incorporation,
                NULL                                                    AS country_of_risk,
                NULL                                                    AS country_of_operation,
                NULL                                                    AS security_currency,
                NULL                                                    AS corp_code,
                NULL                                                    AS branch_code,
                NULL                                                    AS cost_centre,
                NULL                                                    AS cels,
                NULL                                                    AS bwcif_sg,
                NULL                                                    AS bwcif_ovs,
                NULL                                                    AS mas_6d_code_sg,
                NULL                                                    AS mas_6d_code_ovs,
                '{pos_basis}'                                           AS position_basis,
                processing_date                                         AS reporting_date,
                NULL                                                    AS maturity_date,
                '{src_sys}'                                             AS src_system,
                'ams'                                                   AS sub_system,
                'sta'                                                   AS data_cat,
                'dly'                                                   AS data_frq,
                '{table}'                                               AS source_table,
                CURRENT_TIMESTAMP()                                     AS etl_insert_ts,
                'eod_ams_etl'                                           AS etl_batch_id
            FROM {DB}.{table}
            WHERE processing_date = '{processing_date}'
            GROUP BY
                portfolio_code,
                security_name,
                isin,
                country_code,
                processing_date
        """

    if table == 'gmp_cis_sta_dly_ams_multi_hold':
        return f"""
            SELECT
                portfolio_code                                      AS portfolio,
                security_name                                       AS security_full_name,
                NULL                                                AS security_short_name,
                isin                                                AS isin,
                NULL                                                AS ticker,
                {safe_decimal('quantity', 'DECIMAL(30,8)')}        AS quantity,
                CAST(NULL AS DECIMAL(30,8))                         AS shares_outstanding,
                CAST(NULL AS DECIMAL(30,8))                         AS shares_issued,
                CAST(NULL AS DECIMAL(10,6))                         AS pct_holding,
                CAST(NULL AS DECIMAL(30,8))                         AS market_price,
                CAST(NULL AS DECIMAL(30,8))                         AS average_cost,
                CAST(NULL AS DECIMAL(30,8))                         AS cost_fc,
                CAST(NULL AS DECIMAL(30,8))                         AS market_value_fc,
                CAST(NULL AS DECIMAL(30,8))                         AS net_book_value_fc,
                CAST(NULL AS DECIMAL(30,8))                         AS unrealized_pnl_fc,
                CAST(NULL AS DECIMAL(30,8))                         AS provision_fc,
                CAST(NULL AS DECIMAL(30,8))                         AS cost_lc,
                CAST(NULL AS DECIMAL(30,8))                         AS market_value_lc,
                CAST(NULL AS DECIMAL(30,8))                         AS net_book_value_lc,
                CAST(NULL AS DECIMAL(30,8))                         AS unrealized_pnl_lc,
                CAST(NULL AS DECIMAL(30,8))                         AS provision_lc,
                NULL                                                AS product_type,
                NULL                                                AS security_type,
                NULL                                                AS quoted_unquoted,
                NULL                                                AS industry,
                NULL                                                AS fin_nonfin_co,
                NULL                                                AS issuer_type,
                NULL                                                AS reits_or_fund_y_n,
                country_code                                        AS exchange,
                country_code                                        AS country_code,
                country_code                                        AS country_of_exchange,
                NULL                                                AS country_of_incorporation,
                NULL                                                AS country_of_risk,
                NULL                                                AS country_of_operation,
                NULL                                                AS security_currency,
                NULL                                                AS corp_code,
                NULL                                                AS branch_code,
                NULL                                                AS cost_centre,
                NULL                                                AS cels,
                NULL                                                AS bwcif_sg,
                NULL                                                AS bwcif_ovs,
                NULL                                                AS mas_6d_code_sg,
                NULL                                                AS mas_6d_code_ovs,
                '{pos_basis}'                                       AS position_basis,
                processing_date                                     AS reporting_date,
                NULL                                                AS maturity_date,
                '{src_sys}'                                         AS src_system,
                'ams'                                               AS sub_system,
                'sta'                                               AS data_cat,
                'dly'                                               AS data_frq,
                '{table}'                                           AS source_table,
                CURRENT_TIMESTAMP()                                 AS etl_insert_ts,
                'eod_ams_etl'                                       AS etl_batch_id
            FROM {DB}.{table}
            WHERE processing_date = '{processing_date}'
        """

    if table == 'gmp_cis_sta_dly_stat_street_ams_iceq':
        return f"""
            SELECT
                portfolio_code                                          AS portfolio,
                security_name_long                                      AS security_full_name,
                NULL                                                    AS security_short_name,
                isin                                                    AS isin,
                NULL                                                    AS ticker,
                {safe_decimal('quantity', 'DECIMAL(30,8)')}            AS quantity,
                CAST(NULL AS DECIMAL(30,8))                             AS shares_outstanding,
                CAST(NULL AS DECIMAL(30,8))                             AS shares_issued,
                {safe_decimal('pct_ratio_reserved', 'DECIMAL(10,6)')}  AS pct_holding,
                {safe_decimal('market_unit_price_local', 'DECIMAL(30,8)')} AS market_price,
                {safe_decimal('cost_unit_price_local', 'DECIMAL(30,8)')}   AS average_cost,
                {safe_decimal('cost_value_local', 'DECIMAL(30,8)')}    AS cost_fc,
                {safe_decimal('market_value_local', 'DECIMAL(30,8)')}  AS market_value_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_fc,
                {safe_decimal('unrealized_pl_local', 'DECIMAL(30,8)')} AS unrealized_pnl_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_fc,
                {safe_decimal('cost_value_base', 'DECIMAL(30,8)')}     AS cost_lc,
                {safe_decimal('market_value_base', 'DECIMAL(30,8)')}   AS market_value_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_lc,
                {safe_decimal('unrealized_pl_base', 'DECIMAL(30,8)')}  AS unrealized_pnl_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_lc,
                asset_class                                             AS product_type,
                NULL                                                    AS security_type,
                listing_status                                          AS quoted_unquoted,
                NULL                                                    AS industry,
                NULL                                                    AS fin_nonfin_co,
                NULL                                                    AS issuer_type,
                NULL                                                    AS reits_or_fund_y_n,
                country_name                                            AS exchange,
                NULL                                                    AS country_code,
                country_name                                            AS country_of_exchange,
                NULL                                                    AS country_of_incorporation,
                NULL                                                    AS country_of_risk,
                NULL                                                    AS country_of_operation,
                security_currency                                       AS security_currency,
                NULL                                                    AS corp_code,
                NULL                                                    AS branch_code,
                NULL                                                    AS cost_centre,
                NULL                                                    AS cels,
                NULL                                                    AS bwcif_sg,
                NULL                                                    AS bwcif_ovs,
                NULL                                                    AS mas_6d_code_sg,
                NULL                                                    AS mas_6d_code_ovs,
                '{pos_basis}'                                           AS position_basis,
                COALESCE(valuation_date, processing_date)               AS reporting_date,
                NULL                                                    AS maturity_date,
                '{src_sys}'                                             AS src_system,
                'ams'                                                   AS sub_system,
                'sta'                                                   AS data_cat,
                'dly'                                                   AS data_frq,
                '{table}'                                               AS source_table,
                CURRENT_TIMESTAMP()                                     AS etl_insert_ts,
                'eod_ams_etl'                                           AS etl_batch_id
            FROM {DB}.{table}
            WHERE processing_date = '{processing_date}'
        """

    if table == 'gmp_cis_sta_mthly_stat_street_ams_iceq_end':
        return f"""
            SELECT
                portfolio_code                                          AS portfolio,
                security_long_name                                      AS security_full_name,
                NULL                                                    AS security_short_name,
                isin                                                    AS isin,
                NULL                                                    AS ticker,
                {safe_decimal('quantity', 'DECIMAL(30,8)')}            AS quantity,
                CAST(NULL AS DECIMAL(30,8))                             AS shares_outstanding,
                CAST(NULL AS DECIMAL(30,8))                             AS shares_issued,
                {safe_decimal('pct_ratio_reserved', 'DECIMAL(10,6)')}  AS pct_holding,
                {safe_decimal('market_unit_price_local', 'DECIMAL(30,8)')} AS market_price,
                {safe_decimal('cost_unit_price_local', 'DECIMAL(30,8)')}   AS average_cost,
                {safe_decimal('cost_value_local', 'DECIMAL(30,8)')}    AS cost_fc,
                {safe_decimal('market_value_local', 'DECIMAL(30,8)')}  AS market_value_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_fc,
                {safe_decimal('unrealized_pl_local', 'DECIMAL(30,8)')} AS unrealized_pnl_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_fc,
                {safe_decimal('cost_value_base', 'DECIMAL(30,8)')}     AS cost_lc,
                {safe_decimal('market_value_base', 'DECIMAL(30,8)')}   AS market_value_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_lc,
                {safe_decimal('unrealized_pl_base', 'DECIMAL(30,8)')}  AS unrealized_pnl_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_lc,
                asset_class                                             AS product_type,
                NULL                                                    AS security_type,
                listing_status                                          AS quoted_unquoted,
                NULL                                                    AS industry,
                NULL                                                    AS fin_nonfin_co,
                NULL                                                    AS issuer_type,
                NULL                                                    AS reits_or_fund_y_n,
                country_name                                            AS exchange,
                NULL                                                    AS country_code,
                country_name                                            AS country_of_exchange,
                NULL                                                    AS country_of_incorporation,
                NULL                                                    AS country_of_risk,
                NULL                                                    AS country_of_operation,
                security_currency                                       AS security_currency,
                NULL                                                    AS corp_code,
                NULL                                                    AS branch_code,
                NULL                                                    AS cost_centre,
                NULL                                                    AS cels,
                NULL                                                    AS bwcif_sg,
                NULL                                                    AS bwcif_ovs,
                NULL                                                    AS mas_6d_code_sg,
                NULL                                                    AS mas_6d_code_ovs,
                '{pos_basis}'                                           AS position_basis,
                COALESCE(settled_date, valuation_date, processing_date) AS reporting_date,
                NULL                                                    AS maturity_date,
                '{src_sys}'                                             AS src_system,
                'ams'                                                   AS sub_system,
                'sta'                                                   AS data_cat,
                'mthly'                                                 AS data_frq,
                '{table}'                                               AS source_table,
                CURRENT_TIMESTAMP()                                     AS etl_insert_ts,
                'eod_ams_etl'                                           AS etl_batch_id
            FROM {DB}.{table}
            WHERE processing_date = '{processing_date}'
        """

    if table == 'gmp_cis_sta_dly_stat_street_ams_daily_limit':
        return f"""
            SELECT
                portfolio                                               AS portfolio,
                security_desc                                           AS security_full_name,
                NULL                                                    AS security_short_name,
                NULL                                                    AS isin,
                {normalize_ticker_suffix('ticker')}                     AS ticker,
                {safe_decimal('quantity_units', 'DECIMAL(30,8)')}      AS quantity,
                CAST(NULL AS DECIMAL(30,8))                             AS shares_outstanding,
                CAST(NULL AS DECIMAL(30,8))                             AS shares_issued,
                {safe_decimal('stake_holdings', 'DECIMAL(10,6)')}      AS pct_holding,
                {safe_decimal('market_price', 'DECIMAL(30,8)')}        AS market_price,
                {safe_decimal('unit_cost', 'DECIMAL(30,8)')}           AS average_cost,
                {safe_decimal('total_cost_fc', 'DECIMAL(30,8)')}       AS cost_fc,
                {safe_decimal('mkt_value_fc', 'DECIMAL(30,8)')}        AS market_value_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_fc,
                {safe_decimal('unrealised_p_l_fc', 'DECIMAL(30,8)')}   AS unrealized_pnl_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_fc,
                {safe_decimal('total_cost_sgd', 'DECIMAL(30,8)')}      AS cost_lc,
                {safe_decimal('mkt_value_sgd', 'DECIMAL(30,8)')}       AS market_value_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_lc,
                {safe_decimal('unrealised_pl_sgd', 'DECIMAL(30,8)')}   AS unrealized_pnl_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_lc,
                product_type                                            AS product_type,
                NULL                                                    AS security_type,
                quoted_unquoted                                         AS quoted_unquoted,
                NULL                                                    AS industry,
                NULL                                                    AS fin_nonfin_co,
                NULL                                                    AS issuer_type,
                NULL                                                    AS reits_or_fund_y_n,
                ctry_of_exchange                                        AS exchange,
                NULL                                                    AS country_code,
                ctry_of_exchange                                        AS country_of_exchange,
                ctry_incorporation                                      AS country_of_incorporation,
                NULL                                                    AS country_of_risk,
                NULL                                                    AS country_of_operation,
                ccy                                                     AS security_currency,
                NULL                                                    AS corp_code,
                NULL                                                    AS branch_code,
                NULL                                                    AS cost_centre,
                NULL                                                    AS cels,
                NULL                                                    AS bwcif_sg,
                NULL                                                    AS bwcif_ovs,
                mas_6digit_code                                         AS mas_6d_code_sg,
                NULL                                                    AS mas_6d_code_ovs,
                '{pos_basis}'                                           AS position_basis,
                COALESCE(trade_date, processing_date)                   AS reporting_date,
                NULL                                                    AS maturity_date,
                '{src_sys}'                                             AS src_system,
                'ams'                                                   AS sub_system,
                'sta'                                                   AS data_cat,
                'dly'                                                   AS data_frq,
                '{table}'                                               AS source_table,
                CURRENT_TIMESTAMP()                                     AS etl_insert_ts,
                'eod_ams_etl'                                           AS etl_batch_id
            FROM {DB}.{table}
            WHERE processing_date = '{processing_date}'
        """

    if table == 'gmp_cis_sta_dly_position':
        # GMP daily position — columns have m_* prefix.
        # position_basis is read from the `line` column (TRADED / SETTLED).
        # m_security_code maps to isin (GMP uses security code as the ISIN identifier).
        return f"""
            SELECT
                m_cis_pfolio                                            AS portfolio,
                m_security_full_name                                    AS security_full_name,
                m_security_display_label                                AS security_short_name,
                m_security_code                                         AS isin,
                NULL                                                    AS ticker,
                {safe_decimal('m_quantity', 'DECIMAL(30,8)')}          AS quantity,
                {safe_decimal('m_outstanding_shares', 'DECIMAL(30,8)')} AS shares_outstanding,
                CAST(NULL AS DECIMAL(30,8))                             AS shares_issued,
                CAST(NULL AS DECIMAL(10,6))                             AS pct_holding,
                {safe_decimal('m_market_price', 'DECIMAL(30,8)')}      AS market_price,
                {safe_decimal('m_average_cost', 'DECIMAL(30,8)')}      AS average_cost,
                {safe_decimal('m_total_cost_fc', 'DECIMAL(30,8)')}     AS cost_fc,
                {safe_decimal('m_market_value_fc', 'DECIMAL(30,8)')}   AS market_value_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_fc,
                {safe_decimal('m_unrealized_pl_fc', 'DECIMAL(30,8)')}  AS unrealized_pnl_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS cost_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS market_value_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS unrealized_pnl_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_lc,
                NULL                                                    AS product_type,
                NULL                                                    AS security_type,
                m_quoted                                                AS quoted_unquoted,
                NULL                                                    AS industry,
                NULL                                                    AS fin_nonfin_co,
                NULL                                                    AS issuer_type,
                NULL                                                    AS reits_or_fund_y_n,
                m_country                                               AS exchange,
                m_country                                               AS country_code,
                m_country                                               AS country_of_exchange,
                m_country                                               AS country_of_incorporation,
                NULL                                                    AS country_of_risk,
                NULL                                                    AS country_of_operation,
                m_currency                                              AS security_currency,
                NULL                                                    AS corp_code,
                NULL                                                    AS branch_code,
                NULL                                                    AS cost_centre,
                NULL                                                    AS cels,
                NULL                                                    AS bwcif_sg,
                NULL                                                    AS bwcif_ovs,
                NULL                                                    AS mas_6d_code_sg,
                NULL                                                    AS mas_6d_code_ovs,
                UPPER(TRIM(line))                                       AS position_basis,
                processing_date                                         AS reporting_date,
                NULL                                                    AS maturity_date,
                '{src_sys}'                                             AS src_system,
                'gmp'                                                   AS sub_system,
                'sta'                                                   AS data_cat,
                'dly'                                                   AS data_frq,
                '{table}'                                               AS source_table,
                CURRENT_TIMESTAMP()                                     AS etl_insert_ts,
                'eod_ams_etl'                                           AS etl_batch_id
            FROM {DB}.{table}
            WHERE processing_date = '{processing_date}'
        """

    raise ValueError(f'No standardization SQL defined for table: {table}')


# ---------------------------------------------------------------------------
# Core ETL — runs Steps 0–7B for one source table
# ---------------------------------------------------------------------------
def run_etl_for_table(table: str, processing_date: str, dry_run: bool) -> dict:
    src_id = table  # partition value in position_upload_standardized
    result = {'table': table, 'src_id': src_id, 'processing_date': processing_date,
              'total': 0, 'passed': 0, 'failed': 0, 'ok': False}

    pos_basis_label = ALL_SOURCES[table]['position_basis'] or 'from source row'
    print(f"\n{'='*70}")
    print(f"  {ALL_SOURCES[table]['description']} ({table})")
    print(f"  processing_date={processing_date}  position_basis={pos_basis_label}")
    print(f"{'='*70}")

    # ---- Step 0: check source has data for this partition ----
    check = impala_manager.execute_query(
        f"SELECT COUNT(*) AS cnt FROM {DB}.{table} WHERE processing_date='{processing_date}'",
        database=DB
    )
    src_count = int(check[0].get('cnt', 0)) if check else 0
    print(f"[Step 0] Source rows for processing_date={processing_date}: {src_count}")
    if src_count == 0:
        print(f"[Step 0] No data — skipping {table}")
        return result

    if dry_run:
        print(f"[DRY RUN] Would standardize {src_count} rows and run ETL pipeline. Skipping writes.")
        result['total'] = src_count
        result['ok'] = True
        return result

    # ---- Step 0: standardize → position_upload_standardized ----
    std_sql = _standardize_sql(table, processing_date, src_id)
    # Drop this partition first to allow re-runs
    impala_manager.execute_write(
        f"ALTER TABLE {DB}.position_upload_standardized "
        f"DROP IF EXISTS PARTITION (processing_date='{processing_date}', src_id='{src_id}')",
        database=DB
    )
    ok = impala_manager.execute_write(
        f"""
        INSERT OVERWRITE {DB}.position_upload_standardized
        PARTITION (processing_date='{processing_date}', src_id='{src_id}')
        {std_sql}
        """,
        database=DB
    )
    if not ok:
        print(f"[Step 0] FAILED — INSERT into position_upload_standardized failed")
        return result

    impala_manager.execute_write(
        f"INVALIDATE METADATA {DB}.position_upload_standardized", database=DB
    )
    std_rows_res = impala_manager.execute_query(
        f"SELECT COUNT(*) AS cnt FROM {DB}.position_upload_standardized "
        f"WHERE src_id='{src_id}' AND processing_date='{processing_date}'",
        database=DB
    )
    std_rows = int(std_rows_res[0].get('cnt', 0)) if std_rows_res else 0
    print(f"[Step 0] Standardized {std_rows} rows into position_upload_standardized")
    if std_rows == 0:
        print(f"[Step 0] FAILED — 0 rows standardized")
        return result

    # ---- Step 1: pos_stage_1_base ----
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_1_base", database=DB)
    ok = impala_manager.execute_write(
        f"""
        CREATE TABLE pos_stage_1_base STORED AS PARQUET AS
        SELECT
            ROW_NUMBER() OVER (ORDER BY portfolio, security_full_name) AS row_id,
            portfolio, security_full_name, security_short_name,
            isin, ticker,
            COALESCE(quantity,           CAST(0 AS DECIMAL(30,8))) AS quantity,
            COALESCE(shares_outstanding, CAST(0 AS DECIMAL(30,8))) AS shares_outstanding,
            COALESCE(shares_issued,      CAST(0 AS DECIMAL(30,8))) AS shares_issued,
            COALESCE(pct_holding,        CAST(0 AS DECIMAL(10,6))) AS pct_holding,
            market_price, average_cost,
            COALESCE(cost_fc,            CAST(0 AS DECIMAL(30,8))) AS cost_fc,
            COALESCE(market_value_fc,    CAST(0 AS DECIMAL(30,8))) AS market_value_fc,
            COALESCE(net_book_value_fc,  CAST(0 AS DECIMAL(30,8))) AS net_book_value_fc,
            COALESCE(unrealized_pnl_fc,  CAST(0 AS DECIMAL(30,8))) AS unrealized_pnl_fc,
            COALESCE(cost_lc,            CAST(0 AS DECIMAL(30,8))) AS cost_lc,
            COALESCE(market_value_lc,    CAST(0 AS DECIMAL(30,8))) AS market_value_lc,
            COALESCE(net_book_value_lc,  CAST(0 AS DECIMAL(30,8))) AS net_book_value_lc,
            COALESCE(unrealized_pnl_lc,  CAST(0 AS DECIMAL(30,8))) AS unrealized_pnl_lc,
            COALESCE(provision_lc,       CAST(0 AS DECIMAL(30,8))) AS provision_lc,
            COALESCE(provision_fc,       CAST(0 AS DECIMAL(30,8))) AS provision_fc,
            product_type, security_type, quoted_unquoted, industry, fin_nonfin_co,
            issuer_type, reits_or_fund_y_n,
            `exchange` AS `exchange`,
            country_code, country_of_exchange, country_of_incorporation,
            country_of_risk, country_of_operation, security_currency,
            corp_code, branch_code, cost_centre, cels,
            bwcif_sg, bwcif_ovs, mas_6d_code_sg, mas_6d_code_ovs,
            position_basis,
            from_timestamp(
                CASE
                    WHEN reporting_date LIKE '%/%/%' AND length(reporting_date) = 10 THEN
                        CAST(unix_timestamp(reporting_date, 'dd/MM/yyyy') AS TIMESTAMP)
                    WHEN reporting_date LIKE '__-__-____' THEN
                        CAST(unix_timestamp(reporting_date, 'dd-MM-yyyy') AS TIMESTAMP)
                    WHEN reporting_date LIKE '____-__-__' AND length(reporting_date) = 10 THEN
                        CAST(unix_timestamp(reporting_date, 'yyyy-MM-dd') AS TIMESTAMP)
                    WHEN length(reporting_date) = 8 THEN
                        CAST(unix_timestamp(reporting_date, 'yyyyMMdd') AS TIMESTAMP)
                    WHEN reporting_date LIKE '%-%-% %:%:%' THEN
                        CAST(regexp_replace(reporting_date, ' .*', '') AS TIMESTAMP)
                    ELSE CAST(reporting_date AS TIMESTAMP)
                END,
                'yyyy-MM-dd'
            ) AS reporting_date,
            maturity_date, src_system, sub_system, data_cat, data_frq,
            source_table, etl_insert_ts, etl_batch_id, src_id, processing_date
        FROM {DB}.position_upload_standardized
        WHERE src_id = '{src_id}'
          AND processing_date = '{processing_date}'
        """,
        database=DB
    )
    if not ok:
        print("[Step 1] FAILED — pos_stage_1_base creation failed")
        return result
    print("[Step 1] pos_stage_1_base created")

    # ---- Step 2: portfolio validation ----
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_2_portfolio", database=DB)
    impala_manager.execute_write(
        f"""
        CREATE TABLE pos_stage_2_portfolio STORED AS PARQUET AS
        SELECT b.row_id, b.portfolio,
            pf.name AS valid_portfolio,
            pf.currency AS portfolio_currency,
            CASE WHEN pf.name IS NOT NULL THEN 'PASS'
                 ELSE 'FAIL: Portfolio not found in cis_portfolio'
            END AS portfolio_status
        FROM pos_stage_1_base b
        LEFT JOIN {DB}.cis_portfolio pf ON b.portfolio = pf.name
        """,
        database=DB
    )
    print("[Step 2] Portfolio validation complete")

    # ---- Step 3: security ISIN match ----
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_3_security", database=DB)
    impala_manager.execute_write(
        f"""
        CREATE TABLE pos_stage_3_security STORED AS PARQUET AS
        WITH sec_join AS (
            SELECT
                b.row_id,
                b.isin                  AS upload_isin,
                b.security_full_name,
                b.security_short_name,
                b.ticker,
                b.`exchange`            AS upload_exchange,
                p2.portfolio_status,
                s.security_id,
                s.security_name,
                s.isin                  AS s_isin,
                s.exchange_code,
                s.country_of_exchange,
                s.currency_code,
                s.src_system            AS s_src_system,
                -- 1 when this cis_security row also matches the upload exchange
                CASE
                    WHEN b.`exchange` IS NOT NULL AND TRIM(b.`exchange`) != ''
                     AND UPPER(TRIM(b.`exchange`)) = UPPER(TRIM(COALESCE(s.country_of_exchange, '')))
                    THEN 1 ELSE 0
                END AS is_exchange_match,
                -- How many cis_security rows match isin + exchange for this upload row
                SUM(CASE
                    WHEN b.`exchange` IS NOT NULL AND TRIM(b.`exchange`) != ''
                     AND UPPER(TRIM(b.`exchange`)) = UPPER(TRIM(COALESCE(s.country_of_exchange, '')))
                    THEN 1 ELSE 0
                END) OVER (PARTITION BY b.row_id) AS cnt_isin_exchange,
                -- How many cis_security rows match isin alone for this upload row
                COUNT(s.security_id) OVER (PARTITION BY b.row_id) AS cnt_isin_only,
                -- Priority: exact exchange match first, then CIS src, then lowest id
                ROW_NUMBER() OVER (
                    PARTITION BY b.row_id
                    ORDER BY
                        CASE
                            WHEN b.`exchange` IS NOT NULL AND TRIM(b.`exchange`) != ''
                             AND UPPER(TRIM(b.`exchange`)) = UPPER(TRIM(COALESCE(s.country_of_exchange, '')))
                            THEN 0 ELSE 1
                        END,
                        CASE WHEN s.src_system = 'GMP' THEN 0 ELSE 1 END,
                        s.security_id
                ) AS rn_priority
            FROM pos_stage_1_base b
            JOIN pos_stage_2_portfolio p2
                ON b.row_id = p2.row_id AND p2.portfolio_status = 'PASS'
            LEFT JOIN {DB}.cis_security s
                ON  s.is_active = true
                AND b.isin IS NOT NULL AND TRIM(b.isin) != ''
                AND UPPER(TRIM(b.isin)) NOT IN ('NA', 'N/A', 'NIL', 'NONE', '-', 'N.A.', 'NAP')
                AND b.isin = s.isin
        )
        SELECT
            row_id,
            upload_isin,
            security_full_name,
            security_short_name,
            ticker,
            upload_exchange,
            portfolio_status,
            CASE WHEN rn_priority = 1 AND cnt_isin_only >= 1 THEN security_id         ELSE NULL END AS matched_security_id,
            CASE WHEN rn_priority = 1 AND cnt_isin_only >= 1 THEN security_name       ELSE NULL END AS matched_security_name,
            CASE WHEN rn_priority = 1 AND cnt_isin_only >= 1 THEN s_isin              ELSE NULL END AS matched_isin,
            CASE WHEN rn_priority = 1 AND cnt_isin_only >= 1 THEN exchange_code       ELSE NULL END AS matched_exchange,
            CASE WHEN rn_priority = 1 AND cnt_isin_only >= 1 THEN country_of_exchange ELSE NULL END AS matched_country,
            CASE WHEN rn_priority = 1 AND cnt_isin_only >= 1 THEN currency_code       ELSE NULL END AS matched_currency,
            CASE
                WHEN upload_isin IS NULL OR TRIM(upload_isin) = ''
                  OR UPPER(TRIM(upload_isin)) IN ('NA', 'N/A', 'NIL', 'NONE', '-', 'N.A.', 'NAP')
                    THEN 'NO_ISIN'
                WHEN cnt_isin_only > 1 AND cnt_isin_exchange != 1
                    THEN 'FAIL: Multiple securities found'
                WHEN cnt_isin_only >= 1
                    THEN 'ISIN_MATCH'
                ELSE 'ISIN_NO_MATCH'
            END AS match_type
        FROM sec_join
        WHERE rn_priority = 1
        """,
        database=DB
    )
    print("[Step 3] Security ISIN match complete")

    # ---- Step 4: security fallback matching (short_name / ticker / desc_prefix) ----
    # Three fallback tiers tried in order when ISIN match fails (ISIN_NO_MATCH or NO_ISIN):
    #
    #   Tier 1 — short_name:   cis_security.security_name = security_short_name
    #             (GMP-specific: m_security_display_label e.g. "775 HK")
    #
    #   Tier 2 — ticker:       cis_security.ticker = upload ticker
    #             (AMS daily-limit rows always carry a ticker, rarely an ISIN)
    #
    #   Tier 3 — desc_prefix:  strip everything from "COMMON STOCK" onward in
    #             security_full_name (= security_desc for AMS) and match the
    #             prefix against cis_security.security_name.
    #             e.g. "ABC COMPANY COMMON STOCK 1.2"  →  "ABC COMPANY"
    #             If still no match, Step 5B creates the security using the
    #             truncated desc_prefix as the security name.
    #
    # Priority within each tier: lowest security_id wins (stable tiebreak).
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_security_fallback", database=DB)
    impala_manager.execute_write(
        f"""
        CREATE TABLE pos_stage_4_security_fallback STORED AS PARQUET AS
        WITH
        -- Pre-compute desc_prefix: everything before "COMMON STOCK" (case-insensitive).
        -- If "COMMON STOCK" is absent the full name is used as-is.
        base_with_prefix AS (
            SELECT
                s3.*,
                TRIM(
                    CASE
                        WHEN UPPER(s3.security_full_name) LIKE '%COMMON STOCK%'
                          OR UPPER(s3.security_full_name) LIKE '%COMMON STICK%'
                        THEN regexp_replace(
                                s3.security_full_name,
                                '(?i)\\s*COMMON\\s+(STOCK|STICK).*$',
                                ''
                             )
                        ELSE s3.security_full_name
                    END
                ) AS desc_prefix
            FROM pos_stage_3_security s3
        ),
        -- Tier 1: short_name match (GMP)
        tier1 AS (
            SELECT
                b.row_id,
                sn.security_id,
                sn.security_name,
                sn.isin,
                sn.exchange_code,
                sn.country_of_exchange,
                sn.currency_code,
                ROW_NUMBER() OVER (PARTITION BY b.row_id ORDER BY sn.security_id) AS rn
            FROM base_with_prefix b
            JOIN {DB}.cis_security sn
                ON  b.match_type IN ('ISIN_NO_MATCH', 'NO_ISIN')
                AND b.security_short_name IS NOT NULL
                AND TRIM(b.security_short_name) != ''
                AND sn.is_active = true
                AND UPPER(TRIM(sn.security_name)) = UPPER(TRIM(b.security_short_name))
        ),
        -- Tier 2: ticker match (AMS)
        -- AMS ticker is a short code (e.g. "AAREIT SP"); GMP stores the full Bloomberg
        -- ticker (e.g. "AAREIT SP Equity"). Match if cis_security.ticker equals the
        -- upload ticker exactly OR starts with it followed by a space.
        tier2 AS (
            SELECT
                b.row_id,
                sn.security_id,
                sn.security_name,
                sn.isin,
                sn.exchange_code,
                sn.country_of_exchange,
                sn.currency_code,
                ROW_NUMBER() OVER (PARTITION BY b.row_id ORDER BY sn.security_id) AS rn
            FROM base_with_prefix b
            JOIN {DB}.cis_security sn
                ON  b.match_type IN ('ISIN_NO_MATCH', 'NO_ISIN')
                AND b.ticker IS NOT NULL
                AND TRIM(b.ticker) != ''
                AND sn.is_active = true
                AND (
                    UPPER(TRIM(sn.ticker)) = UPPER(TRIM(b.ticker))
                    OR UPPER(TRIM(sn.ticker)) LIKE CONCAT(UPPER(TRIM(b.ticker)), ' %')
                )
        ),
        -- Tier 3: desc_prefix match (AMS — truncated at "COMMON STOCK")
        tier3 AS (
            SELECT
                b.row_id,
                sn.security_id,
                sn.security_name,
                sn.isin,
                sn.exchange_code,
                sn.country_of_exchange,
                sn.currency_code,
                ROW_NUMBER() OVER (PARTITION BY b.row_id ORDER BY sn.security_id) AS rn
            FROM base_with_prefix b
            JOIN {DB}.cis_security sn
                ON  b.match_type IN ('ISIN_NO_MATCH', 'NO_ISIN')
                AND b.desc_prefix IS NOT NULL
                AND TRIM(b.desc_prefix) != ''
                AND sn.is_active = true
                AND UPPER(TRIM(sn.security_name)) = UPPER(TRIM(b.desc_prefix))
        )
        SELECT
            b.row_id,
            b.upload_isin,
            b.security_full_name,
            b.security_short_name,
            b.desc_prefix,
            b.upload_exchange,
            b.portfolio_status,
            b.match_type AS isin_match_type,
            -- Cascade: ISIN → short_name → ticker → desc_prefix
            COALESCE(
                b.matched_security_id,
                CASE WHEN t1.rn = 1 THEN t1.security_id   ELSE NULL END,
                CASE WHEN t2.rn = 1 THEN t2.security_id   ELSE NULL END,
                CASE WHEN t3.rn = 1 THEN t3.security_id   ELSE NULL END
            ) AS final_security_id,
            COALESCE(
                b.matched_security_name,
                CASE WHEN t1.rn = 1 THEN t1.security_name ELSE NULL END,
                CASE WHEN t2.rn = 1 THEN t2.security_name ELSE NULL END,
                CASE WHEN t3.rn = 1 THEN t3.security_name ELSE NULL END
            ) AS final_security_name,
            COALESCE(
                b.matched_isin,
                CASE WHEN t1.rn = 1 THEN t1.isin          ELSE NULL END,
                CASE WHEN t2.rn = 1 THEN t2.isin          ELSE NULL END,
                CASE WHEN t3.rn = 1 THEN t3.isin          ELSE NULL END
            ) AS final_isin,
            COALESCE(
                b.matched_exchange,
                CASE WHEN t1.rn = 1 THEN t1.exchange_code ELSE NULL END,
                CASE WHEN t2.rn = 1 THEN t2.exchange_code ELSE NULL END,
                CASE WHEN t3.rn = 1 THEN t3.exchange_code ELSE NULL END
            ) AS final_exchange,
            COALESCE(
                b.matched_country,
                CASE WHEN t1.rn = 1 THEN t1.country_of_exchange ELSE NULL END,
                CASE WHEN t2.rn = 1 THEN t2.country_of_exchange ELSE NULL END,
                CASE WHEN t3.rn = 1 THEN t3.country_of_exchange ELSE NULL END
            ) AS final_country,
            COALESCE(
                b.matched_currency,
                CASE WHEN t1.rn = 1 THEN t1.currency_code ELSE NULL END,
                CASE WHEN t2.rn = 1 THEN t2.currency_code ELSE NULL END,
                CASE WHEN t3.rn = 1 THEN t3.currency_code ELSE NULL END
            ) AS final_currency,
            CASE
                WHEN b.match_type = 'ISIN_MATCH'           THEN 'ISIN_ONLY'
                WHEN t1.rn = 1 AND t1.security_id IS NOT NULL THEN 'SHORT_NAME'
                WHEN t2.rn = 1 AND t2.security_id IS NOT NULL THEN 'TICKER'
                WHEN t3.rn = 1 AND t3.security_id IS NOT NULL THEN 'DESC_PREFIX'
                ELSE                                             'NONE'
            END AS match_method,
            CASE
                WHEN b.match_type = 'FAIL: Multiple securities found'  THEN 'FAIL: Multiple securities found'
                WHEN b.match_type = 'ISIN_MATCH'                       THEN 'ISIN_MATCH'
                WHEN t1.rn = 1 AND t1.security_id IS NOT NULL          THEN 'SHORT_NAME_MATCH'
                WHEN t2.rn = 1 AND t2.security_id IS NOT NULL          THEN 'TICKER_MATCH'
                WHEN t3.rn = 1 AND t3.security_id IS NOT NULL          THEN 'DESC_PREFIX_MATCH'
                ELSE                                                         'NOT_FOUND: Create new security'
            END AS security_status
        FROM base_with_prefix b
        LEFT JOIN tier1 t1 ON b.row_id = t1.row_id AND t1.rn = 1
        LEFT JOIN tier2 t2 ON b.row_id = t2.row_id AND t2.rn = 1
        LEFT JOIN tier3 t3 ON b.row_id = t3.row_id AND t3.rn = 1
        """,
        database=DB
    )
    print("[Step 4] Security fallback matching complete (short_name / ticker / desc_prefix)")

    # ---- Step 5: price lookup ----
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_5_price", database=DB)
    impala_manager.execute_write(
        f"""
        CREATE TABLE pos_stage_5_price STORED AS PARQUET AS
        SELECT
            b.row_id, b.isin, b.reporting_date,
            b.market_price AS upload_market_price,
            ep.main_closing_price,
            CAST(CASE
                WHEN ep.main_closing_price IS NOT NULL AND ep.main_closing_price != 0 THEN CAST(ep.main_closing_price AS DECIMAL(30,8))
                WHEN b.market_price IS NOT NULL AND b.market_price != 0              THEN CAST(b.market_price AS DECIMAL(30,8))
                ELSE NULL
            END AS DECIMAL(30,8)) AS final_market_price,
            CASE
                WHEN ep.main_closing_price IS NOT NULL AND ep.main_closing_price != 0 THEN 'PASS: Using cis_equity_price'
                WHEN b.market_price IS NOT NULL AND b.market_price != 0              THEN 'PASS: Using uploaded'
                WHEN ep.main_closing_price = 0 OR b.market_price = 0                THEN 'WARN: Price is zero (omitted)'
                ELSE 'WARN: No price'
            END AS price_status
        FROM pos_stage_1_base b
        JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
        LEFT JOIN (
            SELECT isin, price_date, main_closing_price,
                   ROW_NUMBER() OVER (PARTITION BY isin, price_date ORDER BY price_timestamp DESC) AS rn
            FROM {DB}.cis_equity_price
            WHERE is_active = true AND main_closing_price IS NOT NULL AND main_closing_price != 0
        ) ep ON b.isin = ep.isin AND b.reporting_date = ep.price_date AND ep.rn = 1
        WHERE p4.security_status NOT LIKE 'FAIL%'
        """,
        database=DB
    )
    print("[Step 5] Price lookup complete")

    # ---- Step 5B: auto-create new securities ----
    impala_manager.execute_write(
        f"""
        INSERT INTO {DB}.cis_security (
            security_id, security_name, isin, security_description, issuer, ticker,
            industry, security_type, investment_type, issuer_type, quoted_unquoted,
            country_of_incorporation, country_of_exchange, exchange_code, currency_code,
            shares_outstanding, fin_nonfin_ind, src_system, status, is_active,
            created_by, created_at, updated_by, updated_at
        )
        WITH candidates AS (
            SELECT
                -- Use desc_prefix (COMMON STOCK/STICK already stripped in Step 4).
                -- Fallback strips the suffix inline if desc_prefix is null/empty.
                COALESCE(
                    p4.desc_prefix,
                    b.security_short_name,
                    TRIM(regexp_replace(
                        b.security_full_name,
                        '(?i)\\s*COMMON\\s+(STOCK|STICK).*$',
                        ''
                    )),
                    b.isin
                ) AS security_name,
                b.isin, b.security_full_name AS security_description,
                b.ticker, b.industry, b.security_type, b.issuer_type, b.quoted_unquoted,
                b.country_of_incorporation, b.country_of_exchange, b.`exchange`,
                b.security_currency AS currency_code,
                b.shares_outstanding, b.fin_nonfin_co,
                b.row_id,
                -- One row per unique security_name across all source tables in this batch
                ROW_NUMBER() OVER (
                    PARTITION BY UPPER(TRIM(COALESCE(
                        p4.desc_prefix,
                        b.security_short_name,
                        TRIM(regexp_replace(b.security_full_name, '(?i)\\s*COMMON\\s+(STOCK|STICK).*$', '')),
                        b.isin
                    )))
                    ORDER BY b.row_id
                ) AS rn
            FROM pos_stage_1_base b
            JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
            -- Only create security when portfolio also matched — prevents orphan securities
            JOIN pos_stage_2_portfolio p2
                ON b.row_id = p2.row_id AND p2.portfolio_status = 'PASS'
            -- Dedup guard: skip if a security with the same name already exists in cis_security
            LEFT JOIN {DB}.cis_security existing
                ON existing.is_active = true
                AND UPPER(TRIM(existing.security_name)) = UPPER(TRIM(COALESCE(
                    p4.desc_prefix,
                    b.security_short_name,
                    TRIM(regexp_replace(b.security_full_name, '(?i)\\s*COMMON\\s+(STOCK|STICK).*$', '')),
                    b.isin
                )))
            WHERE p4.security_status = 'NOT_FOUND: Create new security'
              AND (b.quantity IS NOT NULL OR b.cost_fc IS NOT NULL)
              AND existing.security_id IS NULL
        )
        SELECT
            (UNIX_TIMESTAMP() * 1000) + row_id AS security_id,
            security_name,
            isin, security_description,
            NULL AS issuer, ticker, industry, security_type,
            NULL AS investment_type, issuer_type, quoted_unquoted,
            country_of_incorporation, country_of_exchange, `exchange`,
            currency_code,
            CAST(shares_outstanding AS BIGINT) AS shares_outstanding,
            fin_nonfin_co AS fin_nonfin_ind,
            'CIS' AS src_system,
            'ACTIVE' AS status, TRUE AS is_active,
            'EOD_AMS_ETL' AS created_by,
            from_unixtime(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS created_at,
            'EOD_AMS_ETL' AS updated_by,
            from_unixtime(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS updated_at
        FROM candidates
        WHERE rn = 1
        """,
        database=DB
    )
    print("[Step 5B] New securities created (if any)")

    # ---- Step 6: consolidated staging ----
    impala_manager.execute_write("DROP TABLE IF EXISTS position_upload_staging", database=DB)
    impala_manager.execute_write(
        f"""
        CREATE TABLE position_upload_staging STORED AS PARQUET AS
        SELECT
            b.*,
            p2.valid_portfolio, p2.portfolio_currency, p2.portfolio_status,
            p4.final_security_id,
            p4.final_security_name AS matched_security_name,
            p4.final_isin, p4.final_country AS country_resolved,
            p4.final_currency AS security_currency_resolved,
            p4.security_status,
            p5.final_market_price, p5.price_status,
            CASE WHEN b.quantity IS NOT NULL THEN CAST(b.quantity AS DECIMAL(30,8))
                 WHEN b.cost_fc IS NOT NULL  THEN CAST(b.cost_fc  AS DECIMAL(30,8))
                 ELSE CAST(NULL AS DECIMAL(30,8))
            END AS final_quantity,
            CASE WHEN b.quantity IS NOT NULL THEN 'PASS'
                 WHEN b.cost_fc IS NOT NULL  THEN 'PASS: Using cost_fc'
                 ELSE 'FAIL: Both quantity and cost_fc null' END AS quantity_status,
            CASE WHEN b.shares_issued IS NOT NULL THEN CAST(b.shares_issued AS DECIMAL(30,8))
                 WHEN b.pct_holding IS NOT NULL AND b.quantity IS NOT NULL AND b.pct_holding > 0
                     THEN CAST(CAST(b.quantity AS DECIMAL(30,8)) / CAST(b.pct_holding AS DECIMAL(30,8)) AS DECIMAL(30,8))
                 ELSE CAST(NULL AS DECIMAL(30,8))
            END AS final_shares_issued,
            CASE WHEN b.`exchange` IS NULL OR TRIM(b.`exchange`) = ''
                     THEN 'WARN: Exchange is null'
                 ELSE 'PASS' END AS exchange_status,
            CASE WHEN b.market_value_fc IS NOT NULL AND b.market_value_fc != 0
                     THEN CAST(b.market_value_fc AS DECIMAL(30,8))
                 WHEN b.quantity IS NOT NULL AND p5.final_market_price IS NOT NULL
                     THEN CAST(CAST(b.quantity AS DECIMAL(30,8)) * CAST(p5.final_market_price AS DECIMAL(30,8)) AS DECIMAL(30,8))
                 ELSE CAST(NULL AS DECIMAL(30,8))
            END AS final_market_value_fc,
            CASE WHEN b.net_book_value_fc IS NOT NULL THEN CAST(b.net_book_value_fc AS DECIMAL(30,8))
                 WHEN b.cost_fc IS NOT NULL
                     THEN CAST(CAST(b.cost_fc AS DECIMAL(30,8)) - CAST(COALESCE(b.provision_fc, CAST(0 AS DECIMAL(30,8))) AS DECIMAL(30,8)) AS DECIMAL(30,8))
                 ELSE CAST(NULL AS DECIMAL(30,8))
            END AS final_net_book_value_fc,
            CASE
                WHEN p4.security_status LIKE 'FAIL: No identifier%'  THEN 'INVALID: No security identifier'
                WHEN b.quantity IS NULL AND b.cost_fc IS NULL        THEN 'INVALID: No quantity'
                WHEN p4.security_status = 'NOT_FOUND: Create new security' THEN 'VALID: New security created'
                WHEN p4.security_status = 'ISIN_MATCH' THEN 'VALID'
                WHEN p4.security_status LIKE 'FAIL%' THEN CONCAT('INVALID: ', p4.security_status)
                ELSE 'VALID'
            END AS overall_status
        FROM pos_stage_1_base b
        JOIN pos_stage_2_portfolio p2 ON b.row_id = p2.row_id AND p2.portfolio_status = 'PASS'
        JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
        LEFT JOIN pos_stage_5_price p5 ON b.row_id = p5.row_id
        """,
        database=DB
    )
    print("[Step 6] Consolidated staging complete")

    # ---- Step 7A: UPSERT into cis_position ----
    ok = impala_manager.execute_write(
        f"""
        UPSERT INTO {DB}.cis_position (
            position_id, version_id, portfolio, security_label, position_basis,
            position_date, src_system, processing_date, quantity,
            average_cost_fc, cost_fc, market_value_fc, net_book_value_fc, unrealized_pnl_fc,
            cost_lc, market_value_lc, net_book_value_lc, unrealized_pnl_lc,
            provision_lc, provision_fc,
            dividend_fc, dividend_lc, realized_pnl_fc, realized_pnl_lc,
            isin, average_cost_lc, source_table, processing_timestamp,
            uncall_fc, uncall_lc, pipeline_fc, pipeline_lc, position_type
        )
        SELECT
            ABS(CAST(fnv_hash(CONCAT_WS('|',
                COALESCE(portfolio, ''),
                COALESCE(COALESCE(matched_security_name, security_full_name, security_short_name), ''),
                COALESCE(position_basis, ''),
                COALESCE(CAST(reporting_date AS STRING), ''),
                COALESCE(src_system, '')
            )) AS BIGINT))                                  AS position_id,
            CAST(UNIX_TIMESTAMP() * 1000 AS BIGINT)         AS version_id,
            portfolio,
            COALESCE(matched_security_name, security_full_name, security_short_name) AS security_label,
            position_basis,
            reporting_date                                  AS position_date,
            src_system,
            processing_date,
            CAST(final_quantity          AS DECIMAL(30,8))  AS quantity,
            CAST(average_cost            AS DECIMAL(30,8))  AS average_cost_fc,
            CAST(cost_fc                 AS DECIMAL(30,8))  AS cost_fc,
            CAST(final_market_value_fc   AS DECIMAL(30,8))  AS market_value_fc,
            CAST(final_net_book_value_fc AS DECIMAL(30,8))  AS net_book_value_fc,
            CAST(unrealized_pnl_fc       AS DECIMAL(30,8))  AS unrealized_pnl_fc,
            CAST(cost_lc                 AS DECIMAL(30,8))  AS cost_lc,
            CAST(market_value_lc         AS DECIMAL(30,8))  AS market_value_lc,
            CAST(net_book_value_lc       AS DECIMAL(30,8))  AS net_book_value_lc,
            CAST(unrealized_pnl_lc       AS DECIMAL(30,8))  AS unrealized_pnl_lc,
            CAST(provision_lc            AS DECIMAL(30,8))  AS provision_lc,
            CAST(provision_fc            AS DECIMAL(30,8))  AS provision_fc,
            CAST(0 AS DECIMAL(30,8))                        AS dividend_fc,
            CAST(0 AS DECIMAL(30,8))                        AS dividend_lc,
            CAST(0 AS DECIMAL(30,8))                        AS realized_pnl_fc,
            CAST(0 AS DECIMAL(30,8))                        AS realized_pnl_lc,
            COALESCE(final_isin, isin)                      AS isin,
            CAST(0 AS DECIMAL(30,8))                        AS average_cost_lc,
            source_table                                    AS source_table,
            from_unixtime(unix_timestamp(), 'yyyy-MM-dd HH:mm:ss') AS processing_timestamp,
            CAST(0 AS DECIMAL(30,8))                        AS uncall_fc,
            CAST(0 AS DECIMAL(30,8))                        AS uncall_lc,
            CAST(0 AS DECIMAL(30,8))                        AS pipeline_fc,
            CAST(0 AS DECIMAL(30,8))                        AS pipeline_lc,
            'EOD'                                           AS position_type
        FROM position_upload_staging
        WHERE overall_status LIKE 'VALID%'
        """,
        database=DB
    )
    if not ok:
        print("[Step 7A] FAILED — UPSERT into cis_position failed")
        return result
    print("[Step 7A] cis_position UPSERT complete")

    # ---- Step 7B: INSERT OVERWRITE position_upload_report ----
    # Verify pos_stage_1_base still has rows (sanity check before writing report)
    _base_cnt_res = impala_manager.execute_query(
        "SELECT COUNT(*) AS cnt FROM pos_stage_1_base", database=DB
    )
    _base_cnt = int(_base_cnt_res[0].get('cnt', 0)) if _base_cnt_res else 0
    print(f"[Step 7B] pos_stage_1_base has {_base_cnt} rows")

    # Ensure the Hive partition exists before INSERT OVERWRITE
    impala_manager.execute_write(
        f"ALTER TABLE {DB}.position_upload_report "
        f"ADD IF NOT EXISTS PARTITION (processing_date='{processing_date}', src_id='{src_id}')",
        database=DB
    )

    ok_7b = impala_manager.execute_write(
        f"""
        INSERT OVERWRITE {DB}.position_upload_report
        PARTITION (processing_date='{processing_date}', src_id='{src_id}')
        SELECT
            b.portfolio,
            COALESCE(b.security_full_name, b.security_short_name, b.isin) AS security_full_name,
            b.security_short_name, b.isin, b.ticker,
            b.quantity, b.shares_outstanding, b.shares_issued, b.pct_holding,
            b.market_price, b.average_cost, b.cost_fc, b.market_value_fc,
            b.net_book_value_fc, b.unrealized_pnl_fc, b.provision_fc,
            b.cost_lc, b.market_value_lc, b.net_book_value_lc,
            b.unrealized_pnl_lc, b.provision_lc,
            b.product_type, b.security_type, b.quoted_unquoted, b.industry,
            b.fin_nonfin_co, b.issuer_type, b.reits_or_fund_y_n,
            b.`exchange` AS `exchange`,
            b.country_of_exchange, b.country_of_incorporation,
            b.country_of_risk, b.country_of_operation, b.security_currency,
            b.corp_code, b.branch_code, b.cost_centre, b.cels,
            b.bwcif_sg, b.bwcif_ovs, b.mas_6d_code_sg, b.mas_6d_code_ovs,
            b.position_basis, b.reporting_date, b.maturity_date,
            b.src_system, b.source_table,
            CASE
                WHEN p2.portfolio_status LIKE 'FAIL%'  THEN 'FAIL'
                WHEN p4.security_status  LIKE 'FAIL%'  THEN 'FAIL'
                WHEN s.overall_status    LIKE 'INVALID%' THEN 'FAIL'
                WHEN s.overall_status    LIKE 'VALID%'   THEN 'PASS'
                ELSE 'FAIL'
            END AS row_status,
            CASE
                WHEN p2.portfolio_status LIKE 'FAIL%'    THEN 'Portfolio not found in cis_portfolio'
                WHEN p4.security_status  LIKE 'FAIL%'    THEN p4.security_status
                WHEN s.overall_status    LIKE 'INVALID%' THEN s.overall_status
                ELSE NULL
            END AS fail_reason,
            COALESCE(p2.portfolio_status, s.portfolio_status) AS portfolio_status,
            COALESCE(p4.security_status,  s.security_status)  AS security_status,
            s.price_status, s.quantity_status, s.exchange_status,
            CAST(s.final_security_id AS STRING) AS matched_security_id,
            s.matched_security_name
        FROM pos_stage_1_base b
        LEFT JOIN pos_stage_2_portfolio        p2 ON b.row_id = p2.row_id
        LEFT JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
        LEFT JOIN position_upload_staging       s  ON b.row_id = s.row_id
        """,
        database=DB
    )
    if not ok_7b:
        print("[Step 7B] FAILED — INSERT into position_upload_report failed")
    impala_manager.execute_write(
        f"INVALIDATE METADATA {DB}.position_upload_report", database=DB
    )
    impala_manager.execute_write(
        f"REFRESH {DB}.position_upload_report", database=DB
    )
    print("[Step 7B] position_upload_report written")

    # ---- Summary ----
    rows = impala_manager.execute_query(
        f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN row_status = 'PASS' THEN 1 ELSE 0 END) AS passed,
            SUM(CASE WHEN row_status = 'FAIL' THEN 1 ELSE 0 END) AS failed
        FROM {DB}.position_upload_report
        WHERE src_id = '{src_id}' AND processing_date = '{processing_date}'
        """,
        database=DB
    )
    if rows:
        result['total']  = int(rows[0].get('total',  0) or 0)
        result['passed'] = int(rows[0].get('passed', 0) or 0)
        result['failed'] = int(rows[0].get('failed', 0) or 0)

    result['ok'] = True
    print(f"[Done] total={result['total']}  pass={result['passed']}  fail={result['failed']}")
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description='EOD AMS/GMP Position ETL')
    parser.add_argument(
        '--processing-date', required=True,
        help='Partition date in YYYYMMDD format (e.g. 20260227)'
    )
    parser.add_argument(
        '--source', default='all',
        choices=list(SOURCE_ALIASES.keys()),
        help='Which source to process (default: all)'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Check row counts and exit without writing'
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not __import__('re').match(r'^\d{8}$', args.processing_date):
        print(f"ERROR: processing-date must be YYYYMMDD, got '{args.processing_date}'")
        sys.exit(1)

    processing_date = args.processing_date

    if args.source == 'all':
        tables = list(ALL_SOURCES.keys())
    else:
        tables = [SOURCE_ALIASES[args.source]]

    print('\n' + '=' * 70)
    print('  CIS Trade Hive — EOD AMS/GMP Position ETL')
    print('=' * 70)
    print(f'  processing_date : {processing_date}')
    print(f'  sources         : {", ".join(tables)}')
    print(f'  dry_run         : {args.dry_run}')
    print(f'  started         : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 70)

    overall = {'total': 0, 'passed': 0, 'failed': 0, 'errors': []}

    for table in tables:
        try:
            r = run_etl_for_table(table, processing_date, args.dry_run)
            overall['total']  += r['total']
            overall['passed'] += r['passed']
            overall['failed'] += r['failed']
            if not r['ok']:
                overall['errors'].append(table)
        except Exception as exc:
            logger.exception(f"ETL failed for {table}: {exc}")
            overall['errors'].append(table)

    print('\n' + '=' * 70)
    print('  SUMMARY')
    print('=' * 70)
    print(f"  Total rows  : {overall['total']}")
    print(f"  PASS        : {overall['passed']}")
    print(f"  FAIL        : {overall['failed']}")
    if overall['errors']:
        print(f"  ERRORS in   : {', '.join(overall['errors'])}")
        sys.exit(1)
    else:
        print('  All sources completed successfully')
    print(f"  finished    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print('=' * 70)


if __name__ == '__main__':
    main()
