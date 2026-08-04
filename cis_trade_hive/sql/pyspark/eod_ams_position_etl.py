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
DB = os.environ.get('IMPALA_DB', 'gmp_cis')

# All source tables: name → metadata dict.
# position_basis=None means it is read from the source row (e.g. GMP's `line` column).
ALL_SOURCES = {
    'gmp_cis_sta_dly_ams_multi_dis_cif': {
        'position_basis': 'TRADED',
        'src_system':     'AMS_STREET',
        'position_type':  'INT',
        'description':    'AMS Multi Discretionary Fund',
    },
    # gmp_cis_sta_dly_ams_multi_hold is used only as an ISIN lookup for
    # gmp_cis_sta_dly_stat_street_ams_daily_limit — not processed as its own pipeline.
    'gmp_cis_sta_dly_stat_street_ams_iceq': {
        'position_basis': 'TRADED',
        'src_system':     'AMS_STREET',
        'position_type':  'INT',
        'description':    'AMS ICEQ Daily',
    },
    'gmp_cis_sta_mthly_stat_street_ams_iceq_end': {
        'position_basis': 'SETTLED',
        'src_system':     'AMS_STREET',
        'position_type':  'INT',
        'description':    'AMS ICEQ Month End',
    },
    'gmp_cis_sta_dly_stat_street_ams_daily_limit': {
        'position_basis': 'TRADED',
        'src_system':     'AMS_STREET',
        'position_type':  'INT',
        'description':    'AMS S31 UOI Daily Limit',
    },
    'gmp_cis_sta_dly_position': {
        'position_basis': None,        # derived from `line` column in source
        'src_system':     'GMP',
        'position_type':  'INT',
        'description':    'GMP Daily Position (m_* columns)',
    },
}

# Keep backward-compatible alias for callers that still reference AMS_SOURCES
AMS_SOURCES = ALL_SOURCES

# Short alias → table name (for --source CLI arg)
SOURCE_ALIASES = {
    'ams_multi_dis':  'gmp_cis_sta_dly_ams_multi_dis_cif',
    # 'ams_multi_hold' removed — used only as ISIN lookup, not a standalone ETL source
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


def abbreviate_security_name(name: str, max_len: int = 35) -> str:
    """Abbreviate a company name to max_len chars using a word-level dict,
    initialism fallback, then hard word-boundary truncation.

    Mirrors upload_service.UploadService.run_position_etl()'s local helper
    of the same name — kept as a duplicate here since this script has no
    Django dependency and that helper is a nested closure, not importable.

    Pre-processing strips punctuation (.,) so that variants like
    'CO.,LTD', 'CO. LTD.', 'CO LTD' all normalise to 'CO LTD' before dict
    substitution. Old GMP abbreviations (MGT) are also expanded back to
    their full form so the dict can re-abbreviate them consistently.
    """
    import re as _re
    _ABBREV = {
        "CORPORATION":      "CORP",
        "INCORPORATED":     "INC",
        "BERHAD":           "BHD",
        "SENDIRIAN":        "SDN",
        "PRIVATE":          "PTE",
        "LIMITED":          "LTD",
        "COMPANY":          "CO",
        "HOLDINGS":         "HLDGS",
        "INTERNATIONAL":    "INTL",
        "INVESTMENTS":      "INVT",
        "INVESTMENT":       "INVT",
        "MANAGEMENT":       "MGMT",
        "INDUSTRIES":       "INDS",
        "INDUSTRY":         "IND",
        "TECHNOLOGIES":     "TECH",
        "TECHNOLOGY":       "TECH",
        "INFRASTRUCTURE":   "INFRA",
        "DEVELOPMENT":      "DEV",
        "ENTERPRISE":       "ENTPR",
        "ENTERPRISES":      "ENTPR",
        "RESOURCES":        "RES",
        "PROPERTIES":       "PROP",
        "CAPITAL":          "CAP",
        "FINANCIAL":        "FIN",
        "SERVICES":         "SVCS",
        "SERVICE":          "SVC",
        "GLOBAL":           "GLB",
        "NATIONAL":         "NATL",
        "REGIONAL":         "RGNL",
        "INDUSTRIAL":       "INDL",
        "MANUFACTURING":    "MFG",
        "ENGINEERING":      "ENGG",
        "CONSTRUCTION":     "CONST",
        "DISTRIBUTION":     "DIST",
        "ASSOCIATION":      "ASSOC",
        "FOUNDATION":       "FNDN",
        "EXCHANGE":         "EXCH",
        "COMMUNICATIONS":   "COMM",
        "COMMUNICATION":    "COMM",
        "INSURANCE":        "INS",
        "ASSURANCE":        "ASSUR",
        "HEALTHCARE":       "HLTHCR",
        "PHARMACEUTICALS":  "PHARMA",
        "PHARMACEUTICAL":   "PHARMA",
        "PLANTATIONS":      "PLANT",
        "PLANTATION":       "PLANT",
        "PETROLEUM":        "PETRO",
        "BANK":             "BK",
        "FUND":             "FD",
        "GROUP":            "GRP",
    }
    _EXPAND = {
        "MGT": "MANAGEMENT",
    }
    if not name:
        return name
    result = name.upper().strip()
    result = _re.sub(r'[.,]+', ' ', result)
    result = ' '.join(result.split())
    for old_abbr, full in _EXPAND.items():
        result = _re.sub(r'\b' + old_abbr + r'\b', full, result)
    result = ' '.join(result.split())
    for word, abbr in sorted(_ABBREV.items(), key=lambda x: -len(x[0])):
        result = _re.sub(r'\b' + word + r'\b', abbr, result)
    result = ' '.join(result.split())
    if len(result) <= max_len:
        return result
    _abbrev_values = set(_ABBREV.values())
    words = result.split()
    for i, w in sorted(enumerate(words), key=lambda x: -len(x[1])):
        if len(result) <= max_len:
            break
        if len(w) > 6 and w not in _abbrev_values and '.' not in w:
            words[i] = w[:4] + '.'
            result = ' '.join(words)
    result = ' '.join(result.split())
    if len(result) <= max_len:
        return result
    truncated = result[:max_len]
    last_space = truncated.rfind(' ')
    return truncated[:last_space] if last_space > 0 else truncated


# Module-level cache for normalized(security_name / security_description) ->
# list of candidate security dicts, used by the "Normalized Full Name" tiers
# (5 and 9) of the security-matching cascade. A list (not a single winner)
# so a normalized-name collision can be reported as MULTIPLE_MATCH instead
# of silently keeping the first candidate found.
_cis_normalized_cache: dict = {}
_cis_normalized_cache_ts: float = 0.0
_CIS_NORMALIZED_CACHE_TTL: int = 300  # seconds


def _build_normalized_cache(force: bool = False) -> dict:
    """Build/return the module-level normalized-name match cache."""
    global _cis_normalized_cache, _cis_normalized_cache_ts
    import time as _time_cache
    _now_ts = _time_cache.time()
    if (not force and _cis_normalized_cache and
            _now_ts - _cis_normalized_cache_ts <= _CIS_NORMALIZED_CACHE_TTL):
        return _cis_normalized_cache
    _cis_rows = impala_manager.execute_query(
        f"""
        SELECT security_id, security_name, security_description,
               isin, exchange_code, country_of_exchange, currency_code
        FROM {DB}.cis_security WHERE is_active = true
        """,
        database=DB
    ) or []
    _cache: dict = {}
    for _cs in _cis_rows:
        _cand = {
            'security_id':         int(_cs.get('security_id')),
            'security_name':       _cs.get('security_name'),
            'isin':                _cs.get('isin'),
            'exchange_code':       _cs.get('exchange_code'),
            'country_of_exchange': _cs.get('country_of_exchange'),
            'currency_code':       _cs.get('currency_code'),
        }
        for _raw in (_cs.get('security_name'), _cs.get('security_description')):
            _key = abbreviate_security_name(_raw or '')
            if not _key:
                continue
            _bucket = _cache.setdefault(_key, [])
            if not any(c['security_id'] == _cand['security_id'] for c in _bucket):
                _bucket.append(_cand)
    _cis_normalized_cache = _cache
    _cis_normalized_cache_ts = _now_ts
    print(f"[Step 4] Rebuilt normalized-name match cache ({len(_cache)} keys)")
    return _cache


def _apply_python_tier_result(matches: dict, multi_ids: set, tier_name: str, status_suffix: str = '_MATCH') -> None:
    """Recreate pos_stage_4_security_fallback, applying Python-computed tier
    results (matches / multi-match fails) to rows currently 'PENDING'; every
    other row's existing result passes through unchanged. Impala Parquet
    tables are immutable — recreate in place, matching this pipeline's
    established pattern (see Step 4B in upload_service.run_position_etl()).
    """
    _match_ids = ', '.join(str(rid) for rid in matches.keys()) or '-1'
    _multi_ids_sql = ', '.join(str(rid) for rid in multi_ids) or '-1'
    _match_when = ' '.join(
        f"WHEN row_id = {rid} THEN {c['security_id']}"
        for rid, c in matches.items()
    ) or "WHEN 1 = 0 THEN NULL"
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_tier_update", database=DB)
    impala_manager.execute_write(
        f"""
        CREATE TABLE pos_stage_4_tier_update
        STORED AS PARQUET AS
        SELECT
            p.row_id, p.upload_isin, p.security_full_name, p.security_short_name,
            p.desc_prefix, p.upload_exchange, p.portfolio_status, p.resolved_country,
            p.clean_ticker,
            p.final_security_id   AS prev_security_id,
            p.final_security_name AS prev_security_name,
            p.final_isin          AS prev_isin,
            p.final_exchange      AS prev_exchange,
            p.final_country       AS prev_country,
            p.final_currency      AS prev_currency,
            p.security_match_method AS prev_method,
            p.security_status        AS prev_status,
            CASE
                WHEN p.row_id IN ({_match_ids}) THEN CASE {_match_when} ELSE NULL END
                ELSE NULL
            END AS matched_security_id,
            CASE
                WHEN p.row_id IN ({_match_ids}) THEN 'MATCHED'
                WHEN p.row_id IN ({_multi_ids_sql}) THEN 'MULTI'
                ELSE 'UNCHANGED'
            END AS tier_outcome
        FROM pos_stage_4_security_fallback p
        """,
        database=DB
    )
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_security_fallback", database=DB)
    impala_manager.execute_write(
        f"""
        CREATE TABLE pos_stage_4_security_fallback
        STORED AS PARQUET AS
        SELECT
            u.row_id, u.upload_isin, u.security_full_name, u.security_short_name,
            u.desc_prefix, u.upload_exchange, u.portfolio_status, u.resolved_country,
            u.clean_ticker,
            CASE WHEN u.tier_outcome = 'MATCHED' THEN u.matched_security_id ELSE u.prev_security_id END AS final_security_id,
            CASE WHEN u.tier_outcome = 'MATCHED' THEN sn.security_name ELSE u.prev_security_name END AS final_security_name,
            CASE WHEN u.tier_outcome = 'MATCHED' THEN sn.isin ELSE u.prev_isin END AS final_isin,
            CASE WHEN u.tier_outcome = 'MATCHED' THEN sn.exchange_code ELSE u.prev_exchange END AS final_exchange,
            CASE WHEN u.tier_outcome = 'MATCHED' THEN sn.country_of_exchange ELSE u.prev_country END AS final_country,
            CASE WHEN u.tier_outcome = 'MATCHED' THEN sn.currency_code ELSE u.prev_currency END AS final_currency,
            CASE
                WHEN u.tier_outcome = 'MATCHED' THEN '{tier_name}'
                WHEN u.tier_outcome = 'MULTI'   THEN 'FAIL: MULTIPLE_MATCH_{tier_name}'
                ELSE u.prev_method
            END AS security_match_method,
            CASE
                WHEN u.tier_outcome = 'MATCHED' THEN '{tier_name}{status_suffix}'
                WHEN u.tier_outcome = 'MULTI'   THEN 'FAIL: MULTIPLE_MATCH_{tier_name}'
                ELSE u.prev_status
            END AS security_status
        FROM pos_stage_4_tier_update u
        LEFT JOIN {DB}.cis_security sn
            ON u.tier_outcome = 'MATCHED' AND sn.security_id = u.matched_security_id
        """,
        database=DB
    )
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_tier_update", database=DB)


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
                CAST(SUM({safe_decimal('quantity', 'DECIMAL(30,8)')}) * 1000
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
        # PORTIARP-7364: daily_limit has no ISIN column. Look up ISIN from
        # gmp_cis_sta_dly_ams_multi_hold by matching security_name = security_desc
        # and country_code = ctry_of_exchange (same processing_date partition).
        return f"""
            SELECT
                dl.portfolio                                            AS portfolio,
                dl.security_desc                                        AS security_full_name,
                NULL                                                    AS security_short_name,
                mh.isin                                                 AS isin,
                {normalize_ticker_suffix('dl.ticker')}                  AS ticker,
                {safe_decimal('dl.quantity_units', 'DECIMAL(30,8)')}   AS quantity,
                CAST(NULL AS DECIMAL(30,8))                             AS shares_outstanding,
                CAST(NULL AS DECIMAL(30,8))                             AS shares_issued,
                {safe_decimal('dl.stake_holdings', 'DECIMAL(10,6)')}   AS pct_holding,
                {safe_decimal('dl.market_price', 'DECIMAL(30,8)')}     AS market_price,
                {safe_decimal('dl.unit_cost', 'DECIMAL(30,8)')}        AS average_cost,
                {safe_decimal('dl.total_cost_fc', 'DECIMAL(30,8)')}    AS cost_fc,
                {safe_decimal('dl.mkt_value_fc', 'DECIMAL(30,8)')}     AS market_value_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_fc,
                {safe_decimal('dl.unrealised_p_l_fc', 'DECIMAL(30,8)')} AS unrealized_pnl_fc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_fc,
                {safe_decimal('dl.total_cost_sgd', 'DECIMAL(30,8)')}   AS cost_lc,
                {safe_decimal('dl.mkt_value_sgd', 'DECIMAL(30,8)')}    AS market_value_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS net_book_value_lc,
                {safe_decimal('dl.unrealised_p_l_sgd', 'DECIMAL(30,8)')} AS unrealized_pnl_lc,
                CAST(NULL AS DECIMAL(30,8))                             AS provision_lc,
                dl.product_type                                         AS product_type,
                NULL                                                    AS security_type,
                dl.quoted_unquoted                                      AS quoted_unquoted,
                NULL                                                    AS industry,
                NULL                                                    AS fin_nonfin_co,
                NULL                                                    AS issuer_type,
                NULL                                                    AS reits_or_fund_y_n,
                dl.ctry_of_exchange                                     AS exchange,
                NULL                                                    AS country_code,
                dl.ctry_of_exchange                                     AS country_of_exchange,
                dl.ctry_incorporation                                   AS country_of_incorporation,
                NULL                                                    AS country_of_risk,
                NULL                                                    AS country_of_operation,
                dl.ccy                                                  AS security_currency,
                NULL                                                    AS corp_code,
                NULL                                                    AS branch_code,
                NULL                                                    AS cost_centre,
                NULL                                                    AS cels,
                NULL                                                    AS bwcif_sg,
                NULL                                                    AS bwcif_ovs,
                dl.mas_6digit_code                                      AS mas_6d_code_sg,
                NULL                                                    AS mas_6d_code_ovs,
                '{pos_basis}'                                           AS position_basis,
                COALESCE(dl.trade_date, dl.processing_date)             AS reporting_date,
                NULL                                                    AS maturity_date,
                '{src_sys}'                                             AS src_system,
                'ams'                                                   AS sub_system,
                'sta'                                                   AS data_cat,
                'dly'                                                   AS data_frq,
                '{table}'                                               AS source_table,
                CURRENT_TIMESTAMP()                                     AS etl_insert_ts,
                'eod_ams_etl'                                           AS etl_batch_id
            FROM {DB}.{table} dl
            LEFT JOIN (
                SELECT DISTINCT
                    UPPER(TRIM(security_name)) AS security_name,
                    UPPER(TRIM(country_code))  AS country_code,
                    isin
                FROM {DB}.gmp_cis_sta_dly_ams_multi_hold
                WHERE processing_date = '{processing_date}'
                  AND isin IS NOT NULL
                  AND TRIM(isin) != ''
            ) mh
                ON  UPPER(TRIM(dl.security_desc))    = mh.security_name
                AND UPPER(TRIM(dl.ctry_of_exchange)) = mh.country_code
            WHERE dl.processing_date = '{processing_date}'
        """

    if table == 'gmp_cis_sta_dly_position':
        # GMP daily position — columns have m_* prefix.
        # m_security_code  = real ISIN (e.g. "US0404132054") — used for Step 3 ISIN match.
        # m_security_display_label = Bloomberg short code (e.g. "ANET UN") — used for
        #   Step 4 Tier 1 short_name match against cis_security.security_name.
        # No ticker column — Step 4 Tier 2 is not used for GMP.
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

    pos_basis_label  = ALL_SOURCES[table]['position_basis'] or 'from source row'
    position_type    = ALL_SOURCES[table].get('position_type', 'EOD')
    print(f"\n{'='*70}")
    print(f"  {ALL_SOURCES[table]['description']} ({table})")
    print(f"  processing_date={processing_date}  position_basis={pos_basis_label}  position_type={position_type}")
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

    # ------------------------------------------------------------------
    # Step 3+4: Security matching — 10-tier cascade per SA requirement
    # (Venkata Narayana Adisetty, 30/07/2026 — "Change Position ETL
    # security matching logic"):
    #   1. Short Name           -> cis_security.security_name
    #   2. ISIN + Country of Exchange
    #   3. Ticker (trailing "EQUITY" stripped) + Country of Exchange
    #   4. Full Name            -> cis_security.security_description + Country of Exchange
    #   5. Normalized Full Name + Country of Exchange
    #   6. ISIN only
    #   7. Ticker only
    #   8. Full Name only       -> cis_security.security_description
    #   9. Normalized Full Name only
    #   10. Create Security
    #
    # Rules: a tier is only evaluated when its required fields are
    # populated; matching is case-insensitive and trimmed; per tier 0
    # matches -> next tier, 1 match -> stop, >1 matches -> FAIL:
    # MULTIPLE_MATCH_<TIER> and stop (no security is created for that
    # row). security_match_method records which tier resolved the match
    # ('NONE' if a new security had to be created). CIS security_name is
    # treated as Short Name; security_description is treated as Full
    # Name, per the SA's explicit mapping.
    #
    # pos_stage_1_base.country_of_exchange is already resolved per-source
    # during Step 0 standardization (see _standardize_sql), so tiers that
    # require Country of Exchange use it directly — no live LUT join
    # needed here (unlike upload_service.py, whose upload sources
    # sometimes only carry a raw exchange code).
    #
    # Tiers 1-4 and 6-8 are pure SQL (Stage A / Stage C). Tiers 5 and 9
    # ("Normalized Full Name") reuse abbreviate_security_name() — a
    # Python-side normalizer — so they run as Python passes (Stage B /
    # Stage D) between the SQL stages, each only touching rows still
    # 'PENDING' after the higher-priority tiers.
    # ------------------------------------------------------------------

    # ---- Stage A (SQL): Tier 1 Short Name, Tier 2 ISIN+Country,
    #      Tier 3 Ticker+Country, Tier 4 Full Name(description)+Country ----
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_3_security", database=DB)
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_security_fallback", database=DB)
    impala_manager.execute_write(
        f"""
        CREATE TABLE pos_stage_4_security_fallback
        STORED AS PARQUET AS
        WITH
        base AS (
            SELECT
                b.row_id,
                b.isin                  AS upload_isin,
                b.security_full_name,
                b.security_short_name,
                b.`exchange`            AS upload_exchange,
                p2.portfolio_status,
                b.country_of_exchange   AS resolved_country,
                NULLIF(regexp_replace(UPPER(TRIM(CAST(b.ticker AS STRING))), '\\s+EQUITY$', ''), '') AS clean_ticker,
                TRIM(
                    CASE
                        WHEN UPPER(b.security_full_name) LIKE '%COMMON STOCK%'
                          OR UPPER(b.security_full_name) LIKE '%COMMON STICK%'
                        THEN regexp_replace(
                                b.security_full_name,
                                '(?i)\\s*COMMON\\s+(STOCK|STICK).*$',
                                ''
                             )
                        ELSE b.security_full_name
                    END
                ) AS desc_prefix
            FROM pos_stage_1_base b
            JOIN pos_stage_2_portfolio p2
                ON b.row_id = p2.row_id AND p2.portfolio_status = 'PASS'
        ),
        -- Tier 1: Short Name -> cis_security.security_name (no country requirement)
        t1 AS (
            SELECT base.row_id, sn.security_id, sn.security_name, sn.isin,
                   sn.exchange_code, sn.country_of_exchange, sn.currency_code,
                   ROW_NUMBER() OVER (PARTITION BY base.row_id ORDER BY sn.security_id) AS rn,
                   COUNT(*) OVER (PARTITION BY base.row_id) AS cnt
            FROM base
            JOIN {DB}.cis_security sn
                ON  sn.is_active = true
                AND base.security_short_name IS NOT NULL AND TRIM(base.security_short_name) != ''
                AND UPPER(TRIM(sn.security_name)) = UPPER(TRIM(base.security_short_name))
        ),
        -- Tier 2: ISIN + Country of Exchange
        t2 AS (
            SELECT base.row_id, sn.security_id, sn.security_name, sn.isin,
                   sn.exchange_code, sn.country_of_exchange, sn.currency_code,
                   ROW_NUMBER() OVER (PARTITION BY base.row_id ORDER BY sn.security_id) AS rn,
                   COUNT(*) OVER (PARTITION BY base.row_id) AS cnt
            FROM base
            JOIN {DB}.cis_security sn
                ON  sn.is_active = true
                AND base.upload_isin IS NOT NULL AND TRIM(base.upload_isin) != ''
                AND UPPER(TRIM(base.upload_isin)) NOT IN ('NA', 'N/A', 'NIL', 'NONE', '-', 'N.A.', 'NAP')
                AND UPPER(TRIM(CAST(base.upload_isin AS STRING))) = UPPER(TRIM(CAST(sn.isin AS STRING)))
                AND base.resolved_country IS NOT NULL AND TRIM(base.resolved_country) != ''
                AND (
                    UPPER(TRIM(base.resolved_country)) = UPPER(TRIM(COALESCE(sn.exchange_code, '')))
                    OR UPPER(TRIM(base.resolved_country)) = UPPER(TRIM(COALESCE(sn.country_of_exchange, '')))
                )
        ),
        -- Tier 3: Ticker (trailing "EQUITY" stripped) + Country of Exchange
        t3 AS (
            SELECT base.row_id, sn.security_id, sn.security_name, sn.isin,
                   sn.exchange_code, sn.country_of_exchange, sn.currency_code,
                   ROW_NUMBER() OVER (PARTITION BY base.row_id ORDER BY sn.security_id) AS rn,
                   COUNT(*) OVER (PARTITION BY base.row_id) AS cnt
            FROM base
            JOIN {DB}.cis_security sn
                ON  sn.is_active = true
                AND base.clean_ticker IS NOT NULL AND TRIM(base.clean_ticker) != ''
                AND regexp_replace(UPPER(TRIM(CAST(sn.ticker AS STRING))), '\\s+EQUITY$', '') = base.clean_ticker
                AND base.resolved_country IS NOT NULL AND TRIM(base.resolved_country) != ''
                AND (
                    UPPER(TRIM(base.resolved_country)) = UPPER(TRIM(COALESCE(sn.exchange_code, '')))
                    OR UPPER(TRIM(base.resolved_country)) = UPPER(TRIM(COALESCE(sn.country_of_exchange, '')))
                )
        ),
        -- Tier 4: Full Name -> cis_security.security_description + Country of Exchange
        t4 AS (
            SELECT base.row_id, sn.security_id, sn.security_name, sn.isin,
                   sn.exchange_code, sn.country_of_exchange, sn.currency_code,
                   ROW_NUMBER() OVER (PARTITION BY base.row_id ORDER BY sn.security_id) AS rn,
                   COUNT(*) OVER (PARTITION BY base.row_id) AS cnt
            FROM base
            JOIN {DB}.cis_security sn
                ON  sn.is_active = true
                AND base.security_full_name IS NOT NULL AND TRIM(base.security_full_name) != ''
                AND sn.security_description IS NOT NULL
                AND UPPER(TRIM(sn.security_description)) = UPPER(TRIM(base.security_full_name))
                AND base.resolved_country IS NOT NULL AND TRIM(base.resolved_country) != ''
                AND (
                    UPPER(TRIM(base.resolved_country)) = UPPER(TRIM(COALESCE(sn.exchange_code, '')))
                    OR UPPER(TRIM(base.resolved_country)) = UPPER(TRIM(COALESCE(sn.country_of_exchange, '')))
                )
        )
        SELECT
            base.row_id,
            base.upload_isin,
            base.security_full_name,
            base.security_short_name,
            base.desc_prefix,
            base.upload_exchange,
            base.portfolio_status,
            base.resolved_country,
            base.clean_ticker,
            COALESCE(
                CASE WHEN COALESCE(t1.cnt, 0) = 1 THEN t1.security_id END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 1 THEN t2.security_id END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 1 THEN t3.security_id END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 0 AND COALESCE(t4.cnt, 0) = 1 THEN t4.security_id END
            ) AS final_security_id,
            COALESCE(
                CASE WHEN COALESCE(t1.cnt, 0) = 1 THEN t1.security_name END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 1 THEN t2.security_name END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 1 THEN t3.security_name END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 0 AND COALESCE(t4.cnt, 0) = 1 THEN t4.security_name END
            ) AS final_security_name,
            COALESCE(
                CASE WHEN COALESCE(t1.cnt, 0) = 1 THEN t1.isin END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 1 THEN t2.isin END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 1 THEN t3.isin END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 0 AND COALESCE(t4.cnt, 0) = 1 THEN t4.isin END
            ) AS final_isin,
            COALESCE(
                CASE WHEN COALESCE(t1.cnt, 0) = 1 THEN t1.exchange_code END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 1 THEN t2.exchange_code END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 1 THEN t3.exchange_code END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 0 AND COALESCE(t4.cnt, 0) = 1 THEN t4.exchange_code END
            ) AS final_exchange,
            COALESCE(
                CASE WHEN COALESCE(t1.cnt, 0) = 1 THEN t1.country_of_exchange END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 1 THEN t2.country_of_exchange END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 1 THEN t3.country_of_exchange END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 0 AND COALESCE(t4.cnt, 0) = 1 THEN t4.country_of_exchange END
            ) AS final_country,
            COALESCE(
                CASE WHEN COALESCE(t1.cnt, 0) = 1 THEN t1.currency_code END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 1 THEN t2.currency_code END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 1 THEN t3.currency_code END,
                CASE WHEN COALESCE(t1.cnt, 0) = 0 AND COALESCE(t2.cnt, 0) = 0 AND COALESCE(t3.cnt, 0) = 0 AND COALESCE(t4.cnt, 0) = 1 THEN t4.currency_code END
            ) AS final_currency,
            CASE
                WHEN COALESCE(t1.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_SHORT_NAME'
                WHEN COALESCE(t1.cnt, 0) = 1 THEN 'SHORT_NAME'
                WHEN COALESCE(t2.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_ISIN'
                WHEN COALESCE(t2.cnt, 0) = 1 THEN 'ISIN'
                WHEN COALESCE(t3.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_TICKER'
                WHEN COALESCE(t3.cnt, 0) = 1 THEN 'TICKER'
                WHEN COALESCE(t4.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_FULL_NAME'
                WHEN COALESCE(t4.cnt, 0) = 1 THEN 'FULL_NAME'
                ELSE 'PENDING'
            END AS security_match_method,
            CASE
                WHEN COALESCE(t1.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_SHORT_NAME'
                WHEN COALESCE(t1.cnt, 0) = 1 THEN 'SHORT_NAME_MATCH'
                WHEN COALESCE(t2.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_ISIN'
                WHEN COALESCE(t2.cnt, 0) = 1 THEN 'ISIN_MATCH'
                WHEN COALESCE(t3.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_TICKER'
                WHEN COALESCE(t3.cnt, 0) = 1 THEN 'TICKER_MATCH'
                WHEN COALESCE(t4.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_FULL_NAME'
                WHEN COALESCE(t4.cnt, 0) = 1 THEN 'FULL_NAME_MATCH'
                ELSE 'PENDING'
            END AS security_status
        FROM base
        LEFT JOIN t1 ON base.row_id = t1.row_id AND t1.rn = 1
        LEFT JOIN t2 ON base.row_id = t2.row_id AND t2.rn = 1
        LEFT JOIN t3 ON base.row_id = t3.row_id AND t3.rn = 1
        LEFT JOIN t4 ON base.row_id = t4.row_id AND t4.rn = 1
        """,
        database=DB
    )
    print("[Step 3] Stage A (tiers 1-4: short_name / isin+country / ticker+country / full_name+country) complete")

    # ---- Stage B (Python): Tier 5 — Normalized Full Name + Country ----
    _pending_b = impala_manager.execute_query(
        "SELECT row_id, security_full_name, resolved_country "
        "FROM pos_stage_4_security_fallback WHERE security_status = 'PENDING'",
        database=DB
    ) or []
    if _pending_b:
        _norm_cache = _build_normalized_cache()
        _t5_match, _t5_multi = {}, set()
        for _row in _pending_b:
            _country = (_row.get('resolved_country') or '').strip()
            if not _country:
                continue  # required field not populated — tier 5 not evaluated
            _key = abbreviate_security_name(_row.get('security_full_name') or '')
            if not _key:
                continue
            _country_matches = [
                c for c in _norm_cache.get(_key, [])
                if _country.upper() == (c.get('exchange_code') or '').strip().upper()
                or _country.upper() == (c.get('country_of_exchange') or '').strip().upper()
            ]
            if len(_country_matches) == 1:
                _t5_match[_row['row_id']] = _country_matches[0]
            elif len(_country_matches) > 1:
                _t5_multi.add(_row['row_id'])
        if _t5_match or _t5_multi:
            _apply_python_tier_result(_t5_match, _t5_multi, 'NORMALIZED_FULL_NAME')
        print(f"[Step 4] Stage B (Tier 5 normalized+country) — {len(_t5_match)} matched, {len(_t5_multi)} multi-match")
    else:
        print("[Step 4] Stage B (Tier 5): no PENDING rows")

    # ---- Stage C (SQL): Tier 6 ISIN only, Tier 7 Ticker only, Tier 8 Full Name only
    #      (all three: country-blank fallback, see t6/t7/t8 comment below) ----
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_tier_update", database=DB)
    impala_manager.execute_write(
        f"""
        CREATE TABLE pos_stage_4_tier_update
        STORED AS PARQUET AS
        WITH
        pending AS (
            SELECT * FROM pos_stage_4_security_fallback WHERE security_status = 'PENDING'
        ),
        -- Tiers 6/7/8 are the ISIN-only / Ticker-only / Full-Name-only
        -- fallback for rows whose upload country was genuinely blank (SA
        -- spec: all of tiers 6-9 are the country-blank fallback group,
        -- mirroring tiers 2-5's country-required group). Gating only on
        -- "tiers 1-5 found nothing" was wrong -- it also fired when the
        -- upload DID supply a country but that country didn't match any
        -- cis_security row (e.g. same ISIN cross-listed under a different
        -- country), silently matching the wrong listing instead of
        -- respecting the country mismatch signal. Tier 9 (Python, Stage D)
        -- has the same gate applied there.
        t6 AS (
            SELECT p.row_id, sn.security_id, sn.security_name, sn.isin,
                   sn.exchange_code, sn.country_of_exchange, sn.currency_code,
                   ROW_NUMBER() OVER (PARTITION BY p.row_id ORDER BY sn.security_id) AS rn,
                   COUNT(*) OVER (PARTITION BY p.row_id) AS cnt
            FROM pending p
            JOIN {DB}.cis_security sn
                ON  sn.is_active = true
                AND (p.resolved_country IS NULL OR TRIM(p.resolved_country) = '')
                AND p.upload_isin IS NOT NULL AND TRIM(p.upload_isin) != ''
                AND UPPER(TRIM(p.upload_isin)) NOT IN ('NA', 'N/A', 'NIL', 'NONE', '-', 'N.A.', 'NAP')
                AND UPPER(TRIM(CAST(p.upload_isin AS STRING))) = UPPER(TRIM(CAST(sn.isin AS STRING)))
        ),
        t7 AS (
            SELECT p.row_id, sn.security_id, sn.security_name, sn.isin,
                   sn.exchange_code, sn.country_of_exchange, sn.currency_code,
                   ROW_NUMBER() OVER (PARTITION BY p.row_id ORDER BY sn.security_id) AS rn,
                   COUNT(*) OVER (PARTITION BY p.row_id) AS cnt
            FROM pending p
            JOIN {DB}.cis_security sn
                ON  sn.is_active = true
                AND (p.resolved_country IS NULL OR TRIM(p.resolved_country) = '')
                AND p.clean_ticker IS NOT NULL AND TRIM(p.clean_ticker) != ''
                AND regexp_replace(UPPER(TRIM(CAST(sn.ticker AS STRING))), '\\s+EQUITY$', '') = p.clean_ticker
        ),
        t8 AS (
            SELECT p.row_id, sn.security_id, sn.security_name, sn.isin,
                   sn.exchange_code, sn.country_of_exchange, sn.currency_code,
                   ROW_NUMBER() OVER (PARTITION BY p.row_id ORDER BY sn.security_id) AS rn,
                   COUNT(*) OVER (PARTITION BY p.row_id) AS cnt
            FROM pending p
            JOIN {DB}.cis_security sn
                ON  sn.is_active = true
                AND (p.resolved_country IS NULL OR TRIM(p.resolved_country) = '')
                AND p.security_full_name IS NOT NULL AND TRIM(p.security_full_name) != ''
                AND sn.security_description IS NOT NULL
                AND UPPER(TRIM(sn.security_description)) = UPPER(TRIM(p.security_full_name))
        )
        SELECT
            p.row_id, p.upload_isin, p.security_full_name, p.security_short_name,
            p.desc_prefix, p.upload_exchange, p.portfolio_status, p.resolved_country, p.clean_ticker,
            COALESCE(
                CASE WHEN COALESCE(t6.cnt, 0) = 1 THEN t6.security_id END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 1 THEN t7.security_id END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 0 AND COALESCE(t8.cnt, 0) = 1 THEN t8.security_id END
            ) AS final_security_id,
            COALESCE(
                CASE WHEN COALESCE(t6.cnt, 0) = 1 THEN t6.security_name END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 1 THEN t7.security_name END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 0 AND COALESCE(t8.cnt, 0) = 1 THEN t8.security_name END
            ) AS final_security_name,
            COALESCE(
                CASE WHEN COALESCE(t6.cnt, 0) = 1 THEN t6.isin END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 1 THEN t7.isin END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 0 AND COALESCE(t8.cnt, 0) = 1 THEN t8.isin END
            ) AS final_isin,
            COALESCE(
                CASE WHEN COALESCE(t6.cnt, 0) = 1 THEN t6.exchange_code END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 1 THEN t7.exchange_code END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 0 AND COALESCE(t8.cnt, 0) = 1 THEN t8.exchange_code END
            ) AS final_exchange,
            COALESCE(
                CASE WHEN COALESCE(t6.cnt, 0) = 1 THEN t6.country_of_exchange END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 1 THEN t7.country_of_exchange END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 0 AND COALESCE(t8.cnt, 0) = 1 THEN t8.country_of_exchange END
            ) AS final_country,
            COALESCE(
                CASE WHEN COALESCE(t6.cnt, 0) = 1 THEN t6.currency_code END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 1 THEN t7.currency_code END,
                CASE WHEN COALESCE(t6.cnt, 0) = 0 AND COALESCE(t7.cnt, 0) = 0 AND COALESCE(t8.cnt, 0) = 1 THEN t8.currency_code END
            ) AS final_currency,
            CASE
                WHEN COALESCE(t6.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_ISIN_ONLY'
                WHEN COALESCE(t6.cnt, 0) = 1 THEN 'ISIN_ONLY'
                WHEN COALESCE(t7.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_TICKER_ONLY'
                WHEN COALESCE(t7.cnt, 0) = 1 THEN 'TICKER_ONLY'
                WHEN COALESCE(t8.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_FULL_NAME_ONLY'
                WHEN COALESCE(t8.cnt, 0) = 1 THEN 'FULL_NAME_ONLY'
                ELSE 'PENDING'
            END AS security_match_method,
            CASE
                WHEN COALESCE(t6.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_ISIN_ONLY'
                WHEN COALESCE(t6.cnt, 0) = 1 THEN 'ISIN_ONLY_MATCH'
                WHEN COALESCE(t7.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_TICKER_ONLY'
                WHEN COALESCE(t7.cnt, 0) = 1 THEN 'TICKER_ONLY_MATCH'
                WHEN COALESCE(t8.cnt, 0) > 1 THEN 'FAIL: MULTIPLE_MATCH_FULL_NAME_ONLY'
                WHEN COALESCE(t8.cnt, 0) = 1 THEN 'FULL_NAME_ONLY_MATCH'
                ELSE 'PENDING'
            END AS security_status
        FROM pending p
        LEFT JOIN t6 ON p.row_id = t6.row_id AND t6.rn = 1
        LEFT JOIN t7 ON p.row_id = t7.row_id AND t7.rn = 1
        LEFT JOIN t8 ON p.row_id = t8.row_id AND t8.rn = 1

        UNION ALL

        SELECT
            row_id, upload_isin, security_full_name, security_short_name,
            desc_prefix, upload_exchange, portfolio_status, resolved_country, clean_ticker,
            final_security_id, final_security_name, final_isin, final_exchange,
            final_country, final_currency, security_match_method, security_status
        FROM pos_stage_4_security_fallback
        WHERE security_status != 'PENDING'
        """,
        database=DB
    )
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_security_fallback", database=DB)
    impala_manager.execute_write(
        "CREATE TABLE pos_stage_4_security_fallback STORED AS PARQUET AS "
        "SELECT * FROM pos_stage_4_tier_update",
        database=DB
    )
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_tier_update", database=DB)
    print("[Step 4] Stage C (tiers 6-8: isin_only / ticker_only / full_name_only) complete")

    # ---- Stage D (Python): Tier 9 — Normalized Full Name only (country blank) ----
    _pending_d = impala_manager.execute_query(
        "SELECT row_id, security_full_name, resolved_country "
        "FROM pos_stage_4_security_fallback WHERE security_status = 'PENDING'",
        database=DB
    ) or []
    if _pending_d:
        _norm_cache = _build_normalized_cache()
        _t9_match, _t9_multi = {}, set()
        for _row in _pending_d:
            if (_row.get('resolved_country') or '').strip():
                continue  # tier 9 is the country-blank fallback — a mismatch stays PENDING
            _key = abbreviate_security_name(_row.get('security_full_name') or '')
            if not _key:
                continue
            _candidates = _norm_cache.get(_key, [])
            if len(_candidates) == 1:
                _t9_match[_row['row_id']] = _candidates[0]
            elif len(_candidates) > 1:
                _t9_multi.add(_row['row_id'])
        if _t9_match or _t9_multi:
            _apply_python_tier_result(_t9_match, _t9_multi, 'NORMALIZED_FULL_NAME_ONLY')
        print(f"[Step 4] Stage D (Tier 9 normalized only) — {len(_t9_match)} matched, {len(_t9_multi)} multi-match")
    else:
        print("[Step 4] Stage D (Tier 9): no PENDING rows")

    # ---- Tier 10: anything still PENDING is a create-security candidate ----
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_tier_update", database=DB)
    impala_manager.execute_write(
        """
        CREATE TABLE pos_stage_4_tier_update
        STORED AS PARQUET AS
        SELECT
            row_id, upload_isin, security_full_name, security_short_name,
            desc_prefix, upload_exchange, portfolio_status, resolved_country, clean_ticker,
            final_security_id, final_security_name, final_isin, final_exchange,
            final_country, final_currency,
            CASE WHEN security_status = 'PENDING' THEN 'NONE' ELSE security_match_method END AS security_match_method,
            CASE WHEN security_status = 'PENDING' THEN 'NOT_FOUND: Create new security' ELSE security_status END AS security_status
        FROM pos_stage_4_security_fallback
        """,
        database=DB
    )
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_security_fallback", database=DB)
    impala_manager.execute_write(
        "CREATE TABLE pos_stage_4_security_fallback STORED AS PARQUET AS "
        "SELECT * FROM pos_stage_4_tier_update",
        database=DB
    )
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_tier_update", database=DB)
    print("[Step 4] Security fallback matching complete (10-tier cascade)")

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
    # Python-driven (like upload_service.py's equivalent step) rather than a
    # single SQL INSERT, because a plain name/isin/ticker collision check
    # can only ever skip-or-fail a candidate. cis_security has no unique
    # constraint on security_name (only security_id, the PK), so an
    # unguarded INSERT on a name collision would silently succeed and
    # create a second, ambiguous security — and skipping it silently is
    # just as wrong, since Step 6 would still report the row VALID.
    #
    # Resolution order per candidate:
    #   1. No collision at all        -> create with the plain name.
    #   2. Collision on a DIFFERENT exchange (the common case: the same
    #      issuer cross-listed on more than one exchange) -> disambiguate
    #      by appending the exchange code, e.g. 'DBS' -> 'DBS (HK)'.
    #   3. Collision on the SAME exchange, or the disambiguated name still
    #      collides -> genuinely ambiguous, can't be resolved automatically
    #      -> fail the row instead of creating or silently skipping it.
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_5b_candidates", database=DB)
    impala_manager.execute_write(
        f"""
        CREATE TABLE pos_stage_5b_candidates
        STORED AS PARQUET AS
        SELECT
            COALESCE(
                p4.desc_prefix,
                b.security_short_name,
                TRIM(regexp_replace(b.security_full_name, '(?i)\\s*COMMON\\s+(STOCK|STICK).*$', '')),
                b.isin
            ) AS raw_security_name,
            b.isin, b.security_full_name AS security_description,
            b.ticker, b.industry, b.security_type, b.issuer_type, b.quoted_unquoted,
            b.country_of_incorporation, b.country_of_exchange, b.`exchange`,
            b.security_currency AS currency_code,
            b.shares_outstanding, b.fin_nonfin_co,
            b.row_id,
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
        JOIN pos_stage_2_portfolio p2
            ON b.row_id = p2.row_id AND p2.portfolio_status = 'PASS'
        WHERE p4.security_status = 'NOT_FOUND: Create new security'
          AND (b.quantity IS NOT NULL OR b.cost_fc IS NOT NULL)
        """,
        database=DB
    )
    _candidates = impala_manager.execute_query(
        "SELECT * FROM pos_stage_5b_candidates WHERE rn = 1", database=DB
    ) or []

    def _sql_str(v):
        # Impala uses C-style \' escaping, not doubled quotes.
        if v in (None, ''):
            return 'NULL'
        s = str(v).replace('\\', '\\\\').replace("'", "\\'")
        return "'" + s + "'"

    def _sql_bigint(v):
        try:
            return str(int(float(v)))
        except (TypeError, ValueError):
            return 'NULL'

    _norm_cache_5b = _build_normalized_cache()
    _collision_rows: dict = {}   # row_id -> FAIL reason string
    _pending: dict = {}          # sec_name -> {'row_id':.., 'exchange':..} (this batch)

    def _exch_key(d: dict) -> str:
        return (d.get('country_of_exchange') or d.get('exchange_code')
                or d.get('exchange') or '').strip().upper()

    def _lookup(name: str) -> list:
        hits = list(_norm_cache_5b.get(name) or [])
        p = _pending.get(name)
        if p:
            hits.append({
                'security_id': f"pending row_id={p['row_id']}",
                'exchange_code': p['exchange'], 'country_of_exchange': p['exchange'],
                'isin': None,
            })
        return hits

    if _candidates:
        _base_ts = int(datetime.now().timestamp()) * 1000
        _now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        _value_rows = []
        for _row in _candidates:
            _raw_name = _row.get('raw_security_name') or ''
            _row_id   = int(_row.get('row_id') or 0)
            _cand_exch = _exch_key(_row)
            _base_name = abbreviate_security_name(_raw_name)

            _sec_name = None
            _fail_reason = None
            _hits = _lookup(_base_name)
            if not _hits:
                _sec_name = _base_name
            else:
                _same_exch = next((h for h in _hits if _exch_key(h) == _cand_exch), None)
                if _same_exch:
                    _fail_reason = (
                        f"FAIL: DUPLICATE_NAME — security '{_base_name}' already exists on the "
                        f"same exchange (security_id={_same_exch.get('security_id')}, "
                        f"isin={_same_exch.get('isin') or 'N/A'}, exchange={_cand_exch or 'N/A'})"
                    )
                else:
                    # Cross-listed on a different exchange — disambiguate.
                    _suffix = _cand_exch or 'UNK'
                    _max_base = max(10, 35 - len(_suffix) - 3)
                    _disamb_name = f"{abbreviate_security_name(_raw_name, max_len=_max_base)} ({_suffix})"
                    _hits2 = _lookup(_disamb_name)
                    if _hits2:
                        _e = _hits2[0]
                        _fail_reason = (
                            f"FAIL: DUPLICATE_NAME — security '{_base_name}' already exists under a "
                            f"different exchange (security_id={_e.get('security_id')}, "
                            f"exchange={_exch_key(_e) or 'N/A'}); disambiguated name '{_disamb_name}' "
                            f"also collides — needs manual resolution"
                        )
                    else:
                        _sec_name = _disamb_name
                        print(
                            f"[Step 5B] disambiguated '{_base_name}' -> '{_sec_name}' "
                            f"(candidate exchange={_cand_exch or 'N/A'}, existing exchange="
                            f"{_exch_key(_hits[0]) or 'N/A'})"
                        )

            if _fail_reason:
                _collision_rows[_row_id] = _fail_reason
                continue
            _pending[_sec_name] = {'row_id': _row_id, 'exchange': _cand_exch}

            _value_rows.append(
                f"({_base_ts + _row_id},"
                f"{_sql_str(_sec_name)},"
                f"{_sql_str(_row.get('isin'))},"
                f"{_sql_str(_row.get('security_description'))},"
                f"NULL,"
                f"{_sql_str(_row.get('ticker'))},"
                f"{_sql_str(_row.get('industry'))},"
                f"{_sql_str(_row.get('security_type'))},"
                f"NULL,"
                f"{_sql_str(_row.get('issuer_type'))},"
                f"{_sql_str(_row.get('quoted_unquoted'))},"
                f"{_sql_str(_row.get('country_of_incorporation'))},"
                f"{_sql_str(_row.get('country_of_exchange'))},"
                f"{_sql_str(_row.get('exchange'))},"
                f"{_sql_str(_row.get('currency_code'))},"
                f"{_sql_bigint(_row.get('shares_outstanding'))},"
                f"{_sql_str(_row.get('fin_nonfin_co'))},"
                f"'CIS','ACTIVE',TRUE,"
                f"'EOD_AMS_ETL','{_now}',"
                f"'EOD_AMS_ETL','{_now}')"
            )

        if _value_rows:
            impala_manager.execute_write(
                f"""
                INSERT INTO {DB}.cis_security (
                    security_id, security_name, isin, security_description,
                    issuer, ticker, industry, security_type, investment_type,
                    issuer_type, quoted_unquoted, country_of_incorporation,
                    country_of_exchange, exchange_code, currency_code,
                    shares_outstanding, fin_nonfin_ind, src_system, status,
                    is_active, created_by, created_at, updated_by, updated_at
                ) VALUES {', '.join(_value_rows)}
                """,
                database=DB
            )

    if _collision_rows:
        _coll_when = ' '.join(
            f"WHEN row_id = {rid} THEN {_sql_str(reason)}"
            for rid, reason in _collision_rows.items()
        )
        impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_tier_update", database=DB)
        impala_manager.execute_write(
            f"""
            CREATE TABLE pos_stage_4_tier_update
            STORED AS PARQUET AS
            SELECT
                row_id, upload_isin, security_full_name, security_short_name,
                desc_prefix, upload_exchange, portfolio_status, resolved_country,
                clean_ticker, final_security_id, final_security_name, final_isin,
                final_exchange, final_country, final_currency, security_match_method,
                CASE {_coll_when} ELSE security_status END AS security_status
            FROM pos_stage_4_security_fallback
            """,
            database=DB
        )
        impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_security_fallback", database=DB)
        impala_manager.execute_write(
            "CREATE TABLE pos_stage_4_security_fallback STORED AS PARQUET AS "
            "SELECT * FROM pos_stage_4_tier_update",
            database=DB
        )
        impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_4_tier_update", database=DB)

    print(
        f"[Step 5B] {len(_candidates) - len(_collision_rows)} new securities created, "
        f"{len(_collision_rows)} blocked as duplicates"
    )
    impala_manager.execute_write("DROP TABLE IF EXISTS pos_stage_5b_candidates", database=DB)

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
            p4.security_match_method,
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
            uncall_fc, uncall_lc, pipeline_fc, pipeline_lc, position_type, is_latest
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
            '{position_type}'                               AS position_type,
            true                                             AS is_latest
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
            -- Core identifiers (columns 1-4, matching DDL order)
            b.portfolio,
            COALESCE(b.security_full_name, b.security_short_name, b.isin) AS security_full_name,
            b.security_short_name,
            b.isin,
            -- Validation result columns (columns 5-13, matching DDL order)
            CASE
                WHEN p2.portfolio_status LIKE 'FAIL%'    THEN 'FAIL'
                WHEN p4.security_status  LIKE 'FAIL%'    THEN 'FAIL'
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
            s.price_status,
            s.quantity_status,
            s.exchange_status,
            CAST(s.final_security_id AS STRING) AS matched_security_id,
            s.matched_security_name,
            -- Original upload columns (columns 14+, matching DDL order)
            b.ticker,
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
            -- security_match_method is appended LAST: this INSERT OVERWRITE has
            -- no explicit column list, so it maps positionally against the live
            -- table schema — migration 85's ALTER TABLE ADD COLUMNS appends new
            -- columns at the end, and this SELECT must match that exact order.
            COALESCE(p4.security_match_method, s.security_match_method) AS security_match_method
        FROM pos_stage_1_base b
        LEFT JOIN pos_stage_2_portfolio         p2 ON b.row_id = p2.row_id
        LEFT JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
        LEFT JOIN position_upload_staging        s  ON b.row_id = s.row_id
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
