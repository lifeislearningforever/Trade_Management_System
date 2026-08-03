#!/usr/bin/env python
"""
Migration Data Loader — cis_party, cis_party_cif, cis_security, cis_trade,
cis_portfolio, cis_cash_flow, cis_corporate_actions
Loads records from CSV files with src_system = 'CIS'.

Usage:
    python scripts/load_migration_data.py --table party             --file /path/to/party.csv
    python scripts/load_migration_data.py --table party_cif         --file /path/to/party_cif.csv
    python scripts/load_migration_data.py --table security          --file /path/to/security.csv
    python scripts/load_migration_data.py --table trade             --file /path/to/trade.csv
    python scripts/load_migration_data.py --table portfolio         --file /path/to/portfolio.csv
    python scripts/load_migration_data.py --table cash_flow         --file /path/to/cashflows.csv
    python scripts/load_migration_data.py --table corporate_action  --file /path/to/corporate_actions.csv

    # Generic loader for any cis_*_lookup / cis_*_lut table — no per-table
    # Python needed, CSV header names map straight to column names:
    python scripts/load_migration_data.py --table lut --file /path/to/lut.csv \\
        --lut-table cis_delivery_type_lookup --lut-pk delivery_type_code \\
        --lut-bool-cols is_active --lut-int-cols display_order

Options:
    --dry-run                  Parse + validate only, no writes to Kudu
    --delimiter ","            CSV delimiter (default comma)
    --batch 100                Rows per UPSERT batch (default 100)
    --status ACTIVE            Override status field (default ACTIVE)
    --processing-date 2026-05-20  Set processing_date on every row (default: today).
                               If the CSV already has a processing_date column that
                               value takes priority over this argument.

Output:
    Prints a summary of loaded / skipped / failed rows.
    Errors are written to load_migration_errors_<table>_<timestamp>.csv
"""

import csv
import sys
import os
import argparse
import hashlib
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from core.repositories.impala_connection import impala_manager

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DATABASE = os.environ.get('IMPALA_DB', 'gmp_cis')
SRC_SYSTEM = 'CIS'


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _escape(value: Any) -> str:
    """Return SQL-safe quoted string or NULL.

    Impala uses backslash escaping inside single-quoted strings (not doubled quotes).
    Handles:
      - backslash      →  \\\\ (must be first)
      - single quote   →  \\'  (A'dam → A\\'dam)
      - newline / CR   →  space
      - null byte      →  removed
    """
    if value is None or str(value).strip() == '':
        return 'NULL'
    s = str(value)
    s = s.replace('\\', '\\\\')   # backslash first
    s = s.replace("'", "\\'")     # single quote → backslash-escaped
    s = s.replace('\n', ' ')
    s = s.replace('\r', ' ')
    s = s.replace('\t', ' ')
    s = s.replace('\x00', '')
    return "'" + s + "'"


def _bool(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if str(value).strip().lower() in ('1', 'true', 'yes', 'y'):
        return 'true'
    return 'false'


def _decimal(value: Any, scale: int = 6) -> str:
    """Round to `scale` decimal places to match DECIMAL(20,scale) column."""
    if value is None or str(value).strip() == '':
        return 'NULL'
    try:
        quantize_str = Decimal(10) ** -scale
        return str(Decimal(str(value).strip()).quantize(quantize_str))
    except InvalidOperation:
        return 'NULL'


def _bigint(value: Any) -> str:
    if value is None or str(value).strip() == '':
        return 'NULL'
    try:
        return str(int(float(str(value).strip())))
    except (ValueError, TypeError):
        return 'NULL'


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _normalise_date(val: Any) -> str:
    """
    Convert any recognisable date format to YYYY-MM-DD.
    Handles: DD/MM/YYYY, DD-MM-YYYY, YYYYMMDD, YYYY-MM-DD, datetime objects.
    Returns '' if unparseable (caller should treat as missing).
    """
    if not val:
        return ''
    if hasattr(val, 'strftime'):          # date / datetime object
        return val.strftime('%Y-%m-%d')
    s = str(val).strip()
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%Y%m%d',
                '%m/%d/%Y', '%d/%m/%y', '%d-%m-%y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return s  # return as-is if already correct or unrecognised


def _timestamp_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


def _security_id(security_name: str, isin: str = '') -> int:
    """Return a stable 12-digit BIGINT derived from security_name + isin.

    Using a deterministic hash means re-running the loader UPSERTs (updates)
    the same row rather than inserting duplicates. The ID is consistent across
    runs as long as security_name (and isin when present) don't change.
    """
    key = f"{security_name.strip().upper()}|{isin.strip().upper()}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    # Take first 15 hex digits → fits in BIGINT (max ~922 trillion)
    return int(digest[:15], 16)


def _normalise_header(raw: str) -> str:
    return raw.strip().lower().replace(' ', '_').replace('-', '_').replace('/', '_')


def _read_csv(path: str, delimiter: str) -> Tuple[List[str], List[Dict[str, str]]]:
    # Auto-detect: if the given/default delimiter doesn't split the header at
    # all but another common delimiter clearly would, switch to it instead of
    # silently parsing the whole file as one giant column. Confirmed live:
    # a pipe-delimited corporate_actions.csv run with the default ','
    # produced a single "column" containing the entire header text joined by
    # '|', so ca_number/security_name never matched any alias and every row
    # failed mandatory-field checks with no indication the delimiter was wrong.
    with open(path, newline='', encoding='utf-8-sig') as fh:
        first_line = fh.readline()
    if delimiter and first_line.count(delimiter) == 0:
        for candidate in ('|', '\t', ';', ','):
            if candidate != delimiter and first_line.count(candidate) > 0:
                logger.warning(
                    "Delimiter %r produced a single header column — auto-switching to %r "
                    "(detected in the header line). Pass --delimiter explicitly to override.",
                    delimiter, candidate,
                )
                delimiter = candidate
                break

    rows = []
    with open(path, newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        headers = [_normalise_header(h) for h in (reader.fieldnames or [])]
        for raw_row in reader:
            rows.append({_normalise_header(k): v for k, v in raw_row.items()})
    return headers, rows


def _run_upsert(table: str, col_names: List[str], value_rows: List[List[str]]) -> Tuple[int, int]:
    """Execute UPSERT in batches; return (ok, fail)."""
    ok = fail = 0
    cols = ', '.join(col_names)
    for row_vals in value_rows:
        vals = ', '.join(row_vals)
        sql = f"UPSERT INTO {DATABASE}.{table} ({cols}) VALUES ({vals})"
        try:
            impala_manager.execute_write(sql, database=DATABASE)
            ok += 1
        except Exception as exc:
            logger.error("UPSERT failed: %s | SQL: %s", exc, sql[:200])
            fail += 1
    return ok, fail


# ---------------------------------------------------------------------------
# cis_party
# ---------------------------------------------------------------------------

PARTY_ALIASES: Dict[str, str] = {
    'party_short_name': 'party_short_name',
    'short_name':       'party_short_name',
    'party_name':       'party_short_name',
    'code':             'party_short_name',

    'party_full_name':  'party_full_name',
    'full_name':        'party_full_name',
    'name':             'party_full_name',

    'm_label':          'm_label',
    'label':            'm_label',

    'record_type':      'record_type',
    'type':             'record_type',

    'address_line_0':   'address_line_0',
    'address1':         'address_line_0',
    'address_line_1':   'address_line_1',
    'address2':         'address_line_1',
    'address_line_2':   'address_line_2',
    'address3':         'address_line_2',
    'address_line_3':   'address_line_3',
    'address4':         'address_line_3',

    'city':                 'city',
    'country':              'country',
    'postal_code':          'postal_code',
    'zip':                  'postal_code',

    'fax_number':           'fax_number',
    'fax':                  'fax_number',
    'telex_number':         'telex_number',
    'telex':                'telex_number',

    'primary_contact':      'primary_contact',
    'primary_number':       'primary_number',
    'primary_phone':        'primary_number',
    'other_contact':        'other_contact',
    'other_number':         'other_number',

    'industry':             'industry',
    'industry_group':       'industry_group',

    'is_broker':            'is_broker',
    'broker':               'is_broker',
    'is_custodian':         'is_custodian',
    'custodian':            'is_custodian',
    'is_issuer':            'is_issuer',
    'issuer':               'is_issuer',
    'is_bank':              'is_bank',
    'bank':                 'is_bank',
    'is_subsidiary':        'is_subsidiary',
    'subsidiary':           'is_subsidiary',
    'is_corporate':         'is_corporate',
    'corporate':            'is_corporate',

    'subsidiary_level':         'subsidiary_level',
    'party_grandparent':        'party_grandparent',
    'grandparent':              'party_grandparent',
    'party_parent':             'party_parent',
    'parent':                   'party_parent',

    'resident_y_n':             'resident_y_n',
    'resident':                 'resident_y_n',
    'mas_industry_code':        'mas_industry_code',
    'country_of_incorporation': 'country_of_incorporation',
    'cels_code':                'cels_code',
    'cels':                     'cels_code',

    'sub_system':       'sub_system',
    'data_cat':         'data_cat',
    'data_frq':         'data_frq',
    'src_id':           'src_id',
    'processing_date':  'processing_date',

    'status':           'status',
    'is_active':        'is_active',
    'created_by':       'created_by',
    'updated_by':       'updated_by',
}

PARTY_BOOL_COLS = {'is_broker', 'is_custodian', 'is_issuer', 'is_bank', 'is_subsidiary', 'is_corporate', 'is_active', 'is_deleted'}


def load_party(rows: List[Dict], status: str, dry_run: bool, processing_date: str = '') -> Tuple[int, int, List[str]]:
    ok = fail = 0
    errors: List[str] = []
    ts = _now()

    for i, raw in enumerate(rows, 1):
        mapped: Dict[str, Any] = {}
        for raw_col, raw_val in raw.items():
            db_col = PARTY_ALIASES.get(raw_col)
            if db_col:
                mapped[db_col] = raw_val

        pk = mapped.get('party_short_name', '').strip()
        if not pk:
            msg = f"Row {i}: missing party_short_name — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        # fixed / derived fields
        mapped['src_system'] = SRC_SYSTEM
        mapped.setdefault('status', status)
        mapped.setdefault('is_active', True)
        mapped.setdefault('is_deleted', False)
        mapped.setdefault('created_by', SRC_SYSTEM)
        mapped.setdefault('updated_by', SRC_SYSTEM)
        mapped['created_at'] = ts
        mapped['updated_at'] = ts
        mapped.setdefault('processing_date', processing_date)

        col_names = []
        col_vals = []
        for col, val in mapped.items():
            col_names.append(col)
            if col in PARTY_BOOL_COLS:
                col_vals.append(_bool(val))
            else:
                col_vals.append(_escape(val))

        if dry_run:
            logger.info("[DRY-RUN] party row %d: %s", i, pk)
            ok += 1
            continue

        sql = f"UPSERT INTO {DATABASE}.cis_party ({', '.join(col_names)}) VALUES ({', '.join(col_vals)})"
        try:
            impala_manager.execute_write(sql, database=DATABASE)
            ok += 1
        except Exception as exc:
            msg = f"Row {i} ({pk}): {exc}"
            logger.error(msg)
            errors.append(msg)
            fail += 1

    return ok, fail, errors


# ---------------------------------------------------------------------------
# cis_party_cif
# ---------------------------------------------------------------------------

PARTY_CIF_ALIASES: Dict[str, str] = {
    'party_name':   'party_name',
    'name':         'party_name',
    'short_name':   'party_name',
    'code':         'party_name',

    'm_label':      'm_label',
    'label':        'm_label',

    'country':      'country',
    'isin':         'isin',
    'description':  'description',
    'desc':         'description',

    'record_type':  'record_type',
    'type':         'record_type',

    'sub_system':       'sub_system',
    'data_cat':         'data_cat',
    'data_frq':         'data_frq',
    'src_id':           'src_id',
    'processing_date':  'processing_date',

    'is_active':    'is_active',
    'is_deleted':   'is_deleted',
    'created_by':   'created_by',
    'updated_by':   'updated_by',
}

PARTY_CIF_BOOL_COLS = {'is_active', 'is_deleted'}


def load_party_cif(rows: List[Dict], status: str, dry_run: bool, processing_date: str = '') -> Tuple[int, int, List[str]]:
    ok = fail = 0
    errors: List[str] = []
    ts = _now()

    for i, raw in enumerate(rows, 1):
        mapped: Dict[str, Any] = {}
        for raw_col, raw_val in raw.items():
            db_col = PARTY_CIF_ALIASES.get(raw_col)
            if db_col:
                mapped[db_col] = raw_val

        pk = mapped.get('party_name', '').strip()
        if not pk:
            msg = f"Row {i}: missing party_name — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        mapped['src_system'] = SRC_SYSTEM
        mapped.setdefault('is_active', True)
        mapped.setdefault('is_deleted', False)
        mapped.setdefault('created_by', SRC_SYSTEM)
        mapped.setdefault('updated_by', SRC_SYSTEM)
        mapped['created_at'] = ts
        mapped['updated_at'] = ts
        mapped.setdefault('processing_date', processing_date)

        col_names = []
        col_vals = []
        for col, val in mapped.items():
            col_names.append(col)
            if col in PARTY_CIF_BOOL_COLS:
                col_vals.append(_bool(val))
            else:
                col_vals.append(_escape(val))

        if dry_run:
            logger.info("[DRY-RUN] party_cif row %d: %s", i, pk)
            ok += 1
            continue

        sql = f"UPSERT INTO {DATABASE}.cis_party_cif ({', '.join(col_names)}) VALUES ({', '.join(col_vals)})"
        try:
            impala_manager.execute_write(sql, database=DATABASE)
            ok += 1
        except Exception as exc:
            msg = f"Row {i} ({pk}): {exc}"
            logger.error(msg)
            errors.append(msg)
            fail += 1

    return ok, fail, errors


# ---------------------------------------------------------------------------
# cis_security
# ---------------------------------------------------------------------------

SECURITY_ALIASES: Dict[str, str] = {
    # Core identification
    'security_name':        'security_name',
    'name':                 'security_name',

    'isin':                 'isin',
    'security_description': 'security_description',
    'description':          'security_description',
    'desc':                 'security_description',

    'issuer':               'issuer',
    'ticker':               'ticker',
    'symbol':               'ticker',

    # Classification
    'record_type':          'record_type',
    'industry':             'industry',
    'security_type':        'security_type',
    'investment_type':      'investment_type',
    'issuer_type':          'issuer_type',
    'quoted_unquoted':      'quoted_unquoted',
    'quoted':               'quoted_unquoted',

    # Geographic
    'country_of_incorporation': 'country_of_incorporation',
    'country_of_exchange':      'country_of_exchange',
    'country_of_issue':         'country_of_issue',
    'exchange_code':            'exchange_code',

    # Trading & pricing
    'currency_code':      'currency_code',
    'currency':           'currency_code',
    'price':              'price',

    # Numeric / statistical
    'shares_outstanding': 'shares_outstanding',
    'beta':               'beta',
    'par_value':          'par_value',

    # Shareholding — live table uses pct_hld_* column names
    'pct_hld_entity_1':       'pct_hld_entity_1',
    'shareholding_entity_1':  'pct_hld_entity_1',
    'pct_hld_entity_2':       'pct_hld_entity_2',
    'shareholding_entity_2':  'pct_hld_entity_2',
    'pct_hld_entity_3':       'pct_hld_entity_3',
    'shareholding_entity_3':  'pct_hld_entity_3',
    'pct_hld_entity_aggr':    'pct_hld_entity_aggr',
    'shareholding_aggregated': 'pct_hld_entity_aggr',
    'substantial_10_pct':     'substantial_10_pct',
    'substantial':            'substantial_10_pct',

    # Regulatory & compliance
    'cels':                 'cels',
    'cels_code':            'cels',
    'pevc_s32_devest':      'pevc_s32_devest',
    's32_representative':   's32_representative',
    'approved_s32':         'approved_s32',          # silently dropped — not in live table
    'basel_iv_fund':        'basel_iv_fund',
    'mas_643_entity_type':  'mas_643_entity_type',
    'mas_6d_code':          'mas_6d_code',
    'fin_nonfin_ind':       'fin_nonfin_ind',

    # Management & operational
    'business_unit_head':              'business_unit_head',
    'person_in_charge':                'person_in_charge',
    'core_noncore':                    'core_noncore',
    'fund_index_fund':                 'fund_index_fund',
    'management_limit_classification': 'management_limit_classification',
    'relative_index':                  'relative_index',

    # Status & audit
    'status':           'status',
    'is_active':        'is_active',
    'created_by':       'created_by',
    'updated_by':       'updated_by',

    # Silently dropped — not in live table (ignored via SECURITY_VALID_COLS)
    'src_id':                    'src_id',
    'processing_date':           'processing_date',
    'price_date':                'price_date',
    'price_source':              'price_source',
    'country_of_primary_exchange': 'country_of_primary_exchange',
    'bwciif':                    'bwciif',
    'bwciif_others':             'bwciif_others',
    'submitted_for_approval_at': 'submitted_for_approval_at',
    'submitted_by':              'submitted_by',
    'reviewed_at':               'reviewed_at',
    'reviewed_by':               'reviewed_by',
    'review_comments':           'review_comments',
    # Extra CSV columns not in live table — silently ignored
    'market':                    'market',
    'security_sub_type':         'security_sub_type',
    'security_investment':       'security_investment',
    'udf_country_issue':         'udf_country_issue',
    'fintech':                   'fintech',
    'speculative':               'speculative',
    'unlisted_speculative':      'unlisted_speculative',
    'unlisted_special_ive':      'unlisted_speculative',
    'related_company':           'related_company',
}

# All columns are STRING in the live table except these
SECURITY_DECIMAL_COLS = {'price', 'beta', 'par_value'}
SECURITY_BIGINT_COLS  = {'shares_outstanding'}
SECURITY_BOOL_COLS    = {'is_active'}

# Exact columns that exist in the live cis_security Kudu table (original schema).
# Any mapped key NOT in this set is silently dropped before the UPSERT
# to avoid "Unknown column" analysis errors.
SECURITY_VALID_COLS = {
    # PK
    'security_id',
    # Identification
    'record_type', 'security_name', 'isin', 'security_description', 'issuer', 'ticker',
    # Classification
    'industry', 'security_type', 'investment_type', 'issuer_type', 'quoted_unquoted',
    # Geographic
    'country_of_incorporation', 'country_of_exchange', 'country_of_issue', 'exchange_code',
    # Trading & pricing
    'currency_code', 'price',
    # Numeric / statistical
    'shares_outstanding', 'beta', 'par_value',
    # Shareholding — live table uses pct_hld_* names
    'pct_hld_entity_1', 'pct_hld_entity_2', 'pct_hld_entity_3',
    'pct_hld_entity_aggr', 'substantial_10_pct',
    # Regulatory & compliance
    'cels', 'pevc_s32_devest', 's32_representative',
    'basel_iv_fund', 'mas_643_entity_type', 'mas_6d_code', 'fin_nonfin_ind',
    # Management & operational
    'business_unit_head', 'person_in_charge', 'core_noncore',
    'fund_index_fund', 'management_limit_classification', 'relative_index',
    # Status & audit
    'status', 'src_system', 'is_active',
    'created_by', 'created_at', 'updated_by', 'updated_at',
}


def load_security(rows: List[Dict], status: str, dry_run: bool, processing_date: str = '') -> Tuple[int, int, List[str]]:
    ok = fail = 0
    would_insert = would_update = 0
    errors: List[str] = []

    # For dry-run: pre-fetch existing security_ids to report INSERT vs UPDATE.
    existing_ids: set = set()
    if dry_run:
        try:
            result = impala_manager.execute_query(
                f"SELECT security_id FROM {DATABASE}.cis_security",
                database=DATABASE,
            )
            existing_ids = {row['security_id'] for row in (result or [])}
            logger.info("[DRY-RUN] %d existing rows fetched for INSERT/UPDATE check", len(existing_ids))
        except Exception as exc:
            logger.warning("[DRY-RUN] Could not fetch existing IDs (DB unreachable?): %s", exc)

    for i, raw in enumerate(rows, 1):
        mapped: Dict[str, Any] = {}
        for raw_col, raw_val in raw.items():
            db_col = SECURITY_ALIASES.get(raw_col)
            if db_col:
                mapped[db_col] = raw_val

        security_name = mapped.get('security_name', '').strip()
        if not security_name:
            msg = f"Row {i}: missing security_name — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        # Stable PK: hash of security_name + isin — same value every run so
        # UPSERT updates the existing row instead of inserting a duplicate.
        isin_val = mapped.get('isin', '') or ''
        security_id = _security_id(security_name, isin_val)
        ts = _now()

        mapped['security_id'] = security_id
        mapped['src_system']  = SRC_SYSTEM
        mapped.setdefault('status', status)
        mapped.setdefault('is_active', True)
        mapped.setdefault('created_by', SRC_SYSTEM)
        mapped.setdefault('updated_by', SRC_SYSTEM)
        mapped.setdefault('created_at', ts)
        mapped['updated_at'] = ts

        # Drop any keys not in the live cis_security schema
        mapped = {k: v for k, v in mapped.items() if k in SECURITY_VALID_COLS}

        col_names = []
        col_vals  = []
        for col, val in mapped.items():
            col_names.append(col)
            if col in SECURITY_DECIMAL_COLS:
                col_vals.append(_decimal(val))
            elif col in SECURITY_BIGINT_COLS or col == 'security_id':
                col_vals.append(_bigint(val))
            elif col in SECURITY_BOOL_COLS:
                col_vals.append(_bool(val))
            else:
                col_vals.append(_escape(val))

        if dry_run:
            action = 'UPDATE' if security_id in existing_ids else 'INSERT'
            if action == 'UPDATE':
                would_update += 1
            else:
                would_insert += 1
            logger.info("[DRY-RUN] row %d: would %-6s %s (security_id=%s isin=%s)",
                        i, action, security_name, security_id, isin_val or '—')
            ok += 1
            continue

        sql = f"UPSERT INTO {DATABASE}.cis_security ({', '.join(col_names)}) VALUES ({', '.join(col_vals)})"
        try:
            impala_manager.execute_write(sql, database=DATABASE)
            ok += 1
        except Exception as exc:
            msg = f"Row {i} ({security_name}): {exc}"
            logger.error(msg)
            errors.append(msg)
            fail += 1

    if dry_run:
        logger.info("[DRY-RUN] Summary: would INSERT=%d  would UPDATE=%d  skipped=%d",
                    would_insert, would_update, fail)
    return ok, fail, errors


# ---------------------------------------------------------------------------
# cis_trade
# ---------------------------------------------------------------------------

TRADE_ALIASES: Dict[str, str] = {
    # Primary key — must be in CSV (source system ID)
    'trade_id':                 'trade_id',
    'id':                       'trade_id',

    # Core trade fields
    'trade_type':               'trade_type',
    'type':                     'trade_type',
    'deal_number':              'deal_number',
    'deal_no':                  'deal_number',
    'deal_num':                 'deal_number',

    'portfolio_short_name':     'portfolio_short_name',
    'portfolio':                'portfolio_short_name',
    'portfolio_name':           'portfolio_short_name',
    'portfolio_full_name':      'portfolio_full_name',

    'security_label':           'security_label',
    'security':                 'security_label',
    'security_name':            'security_label',
    'security_full_name':       'security_full_name',
    'security_type':            'security_type',

    'currency_code':            'currency_code',
    'currency':                 'currency_code',
    'portfolio_currency':       'portfolio_currency',

    'trade_status':             'trade_status',
    'trade_date':               'trade_date',
    'settle_date':              'settle_date',
    'settlement_date':          'settle_date',
    'expiry_date':              'expiry_date',

    # Numeric fields
    'quantity':                 'quantity',
    'qty':                      'quantity',
    'face_value':               'face_value',
    'lot':                      'lot',
    'price':                    'price',
    'commission':               'commission',
    'accrued_interest':         'accrued_interest',
    'sec_fee':                  'sec_fee',
    'other_charges':            'other_charges',
    'total_amount':             'total_amount',
    'total_amount_fc':          'total_amount_fc',
    'total_amount_lc':          'total_amount_lc',
    'gross_amount_fc':          'gross_amount_fc',
    'gross_amount_lc':          'gross_amount_lc',

    'charge_fee_type':          'charge_fee_type',
    'charge_exchange':          'charge_exchange',
    'charge_country':           'charge_country',
    'charge_fee_rule':          'charge_fee_rule',
    'charge_fee_value':         'charge_fee_value',
    'calculated_commission':    'calculated_commission',
    'calculated_clearing_fee':  'calculated_clearing_fee',
    'calculated_trading_fee':   'calculated_trading_fee',
    'calculated_gst':           'calculated_gst',
    'calculated_other_fees':    'calculated_other_fees',
    'total_calculated_charges': 'total_calculated_charges',
    'charges_auto_calculated':  'charges_auto_calculated',

    'open_close_position':      'open_close_position',
    'open_close':               'open_close_position',
    'extension':                'extension',
    'brokers':                  'brokers',
    'broker_name':              'broker_name',
    'broker':                   'broker_name',
    'gl_fund_type':             'gl_fund_type',
    'gl_cost_centre':           'gl_cost_centre',
    'gl_account_code':          'gl_account_code',
    'contract_ref':             'contract_ref',
    'fd_receipt':               'fd_receipt',
    'org_pur_date':             'org_pur_date',
    'open_fx_rate':             'open_fx_rate',
    'curr_dealing':             'curr_dealing',
    'open_dealing':             'open_dealing',
    'input_tax_oth':            'input_tax_oth',
    'qty_entitled':             'qty_entitled',
    'selling_rule':             'selling_rule',
    'cash_balance':             'cash_balance',
    'custodian':                'custodian',
    'amor_accr_method':         'amor_accr_method',
    'lots_held':                'lots_held',
    'quantity_held':            'quantity_held',
    'remarks':                  'remarks',

    # UDF fields
    'udf_fund_type':            'udf_fund_type',
    'udf_sub_custodian':        'udf_sub_custodian',
    'udf_disclosure_req':       'udf_disclosure_req',
    'udf_counter_pledged':      'udf_counter_pledged',
    'udf_revision_code':        'udf_revision_code',
    'udf_uobn_uobn_hk':         'udf_uobn_uobn_hk',
    'udf_income_exp_type':      'udf_income_exp_type',
    'udf_currency_hedge':       'udf_currency_hedge',

    # CA / split / delivery fields
    'realized_pnl':             'realized_pnl',
    'parent_trade_id':          'parent_trade_id',
    'delivery_type':            'delivery_type',
    'counterparty':             'counterparty',
    'reduction_type':           'reduction_type',
    'reduction_amount':         'reduction_amount',
    'units_affected':           'units_affected',
    'income_type':              'income_type',
    'ex_date':                  'ex_date',
    'record_date':              'record_date',
    'pay_date':                 'pay_date',
    'amount_per_unit':          'amount_per_unit',
    'gross_amount':             'gross_amount',
    'withholding_tax':          'withholding_tax',
    'net_amount':               'net_amount',
    'split_type':               'split_type',
    'split_ratio_new':          'split_ratio_new',
    'split_ratio_old':          'split_ratio_old',
    'effective_date':           'effective_date',

    # Workflow / audit
    'status':                   'status',
    'internal_ref':             'internal_ref',
    'external_ref':             'external_ref',
    'submitted_by':             'submitted_by',
    'submitted_at':             'submitted_at',
    'validated_by':             'validated_by',
    'validated_at':             'validated_at',
    'validation_comments':      'validation_comments',
    'settled_by':               'settled_by',
    'settled_at':               'settled_at',
    'settlement_comments':      'settlement_comments',
    'cancelled_by':             'cancelled_by',
    'cancelled_at':             'cancelled_at',
    'cancel_reason':            'cancel_reason',

    'is_active':                'is_active',
    'is_deleted':               'is_deleted',
    'created_by':               'created_by',
    'updated_by':               'updated_by',
    'created_at':               'created_at',
    'updated_at':               'updated_at',
}

TRADE_DECIMAL_COLS = {
    'quantity', 'face_value', 'lot', 'price', 'commission', 'accrued_interest',
    'sec_fee', 'other_charges', 'total_amount', 'total_amount_fc', 'total_amount_lc',
    'gross_amount_fc', 'gross_amount_lc',
    'charge_fee_value', 'calculated_commission', 'calculated_clearing_fee',
    'calculated_trading_fee', 'calculated_gst', 'calculated_other_fees',
    'total_calculated_charges', 'open_fx_rate', 'curr_dealing', 'open_dealing',
    'input_tax_oth', 'qty_entitled', 'cash_balance', 'lots_held', 'quantity_held',
    'realized_pnl', 'reduction_amount', 'units_affected', 'amount_per_unit',
    'gross_amount', 'withholding_tax', 'net_amount',
}
TRADE_BIGINT_COLS = {'trade_id', 'parent_trade_id', 'split_ratio_new', 'split_ratio_old'}
TRADE_BOOL_COLS   = {'is_active', 'is_deleted', 'charges_auto_calculated',
                     'udf_disclosure_req', 'udf_counter_pledged', 'udf_currency_hedge'}


def load_trade(
    rows: List[Dict],
    status: str,
    dry_run: bool,
    processing_date: str = '',
    with_positions: bool = False,
    position_basis: str = 'BOTH',
) -> Tuple[int, int, List[str]]:
    ok = fail = 0
    pos_ok = pos_fail = 0
    errors: List[str] = []
    ts = _now()

    # Broker code -> display name, from cis_party (mirrors how the trade UI's
    # broker dropdown resolves party_short_name -> party_full_name). Migration
    # CSVs typically carry only a broker code/short name column (mapped to
    # `brokers`), never a separate display-name column, so broker_name is left
    # NULL unless we resolve it here ourselves -- built once, not per row.
    _broker_name_map: Dict[str, str] = {}
    try:
        _broker_rows = impala_manager.execute_query(
            f"SELECT party_short_name, party_full_name FROM {DATABASE}.cis_party "
            f"WHERE is_broker = true AND (is_deleted = false OR is_deleted IS NULL)",
            database=DATABASE
        ) or []
        for _br in _broker_rows:
            _short = str(_br.get('party_short_name', '') or '').strip().upper()
            _full = str(_br.get('party_full_name', '') or '').strip()
            if _short and _full:
                _broker_name_map[_short] = _full
        logger.info("Loaded %d broker name(s) from cis_party", len(_broker_name_map))
    except Exception as _be:
        logger.warning("Could not load broker names from cis_party: %s", _be)

    for i, raw in enumerate(rows, 1):
        mapped: Dict[str, Any] = {}
        for raw_col, raw_val in raw.items():
            db_col = TRADE_ALIASES.get(raw_col)
            if db_col:
                mapped[db_col] = raw_val

        # trade_id: use CSV value if present, otherwise auto-generate
        raw_id = str(mapped.get('trade_id', '') or '').strip()
        if not raw_id:
            raw_id = str(_timestamp_ms() + i)
            mapped['trade_id'] = raw_id
            logger.debug("Row %d: trade_id not in CSV, auto-generated %s", i, raw_id)

        # Required business fields
        if not mapped.get('trade_type', '').strip():
            msg = f"Row {i} (trade_id={raw_id}): missing trade_type — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue
        if not mapped.get('portfolio_short_name', '').strip():
            msg = f"Row {i} (trade_id={raw_id}): missing portfolio_short_name — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue
        if not mapped.get('security_label', '').strip():
            msg = f"Row {i} (trade_id={raw_id}): missing security_label — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue
        if not mapped.get('trade_date', '').strip():
            msg = f"Row {i} (trade_id={raw_id}): missing trade_date — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        # Normalise date columns to YYYY-MM-DD (CSV may use DD/MM/YYYY etc.)
        for _dcol in ('trade_date', 'settle_date', 'expiry_date',
                      'org_pur_date', 'ex_date', 'record_date', 'pay_date',
                      'effective_date'):
            if mapped.get(_dcol):
                mapped[_dcol] = _normalise_date(mapped[_dcol])

        # Fixed / derived fields
        mapped['src_system'] = SRC_SYSTEM
        # Always force status — setdefault skips if CSV has a blank status col
        if not str(mapped.get('status', '') or '').strip():
            mapped['status'] = status
        mapped.setdefault('is_active', True)
        mapped.setdefault('is_deleted', False)
        mapped.setdefault('created_by', SRC_SYSTEM)
        mapped.setdefault('updated_by', SRC_SYSTEM)
        mapped.setdefault('created_at', ts)
        mapped.setdefault('updated_at', ts)
        # deal_number: match CIS UI format DEAL-YYYYMMDD-<last4 of trade_id>
        if not mapped.get('deal_number', '').strip():
            trade_date_str = mapped.get('trade_date', ts[:10]).replace('-', '')[:8]
            mapped['deal_number'] = f"DEAL-{trade_date_str}-{str(raw_id)[-4:].zfill(4)}"

        # gross_amount_fc/lc: migration CSVs carry total_amount_fc/lc, not a
        # separate gross_amount_fc/lc column. Default from the total_amount
        # figure whenever the CSV didn't supply gross_amount_fc/lc explicitly,
        # so cis_trade.gross_amount_fc/lc (used as the AVP cost-basis override
        # -- see sql/ddl/80_trade_add_gross_amount_fc_lc.sql) is populated for
        # every migrated trade instead of being left NULL.
        if not str(mapped.get('gross_amount_fc', '') or '').strip():
            if mapped.get('total_amount_fc'):
                mapped['gross_amount_fc'] = mapped['total_amount_fc']
        if not str(mapped.get('gross_amount_lc', '') or '').strip():
            if mapped.get('total_amount_lc'):
                mapped['gross_amount_lc'] = mapped['total_amount_lc']

        # broker_name: resolve from `brokers` (broker code) via cis_party when
        # the CSV didn't supply a separate display-name column. Falls back to
        # the code itself if no matching broker is found in cis_party, rather
        # than leaving broker_name NULL.
        if not str(mapped.get('broker_name', '') or '').strip():
            _brokers_val = str(mapped.get('brokers', '') or '').strip()
            if _brokers_val:
                mapped['broker_name'] = _broker_name_map.get(_brokers_val.upper(), _brokers_val)

        col_names = []
        col_vals = []
        for col, val in mapped.items():
            col_names.append(col)
            if col in TRADE_BOOL_COLS:
                col_vals.append(_bool(val))
            elif col in TRADE_DECIMAL_COLS:
                col_vals.append(_decimal(val))
            elif col in TRADE_BIGINT_COLS:
                col_vals.append(_bigint(val))
            else:
                col_vals.append(_escape(val))

        if dry_run:
            logger.info("[DRY-RUN] trade row %d: trade_id=%s type=%s portfolio=%s security=%s",
                        i, raw_id, mapped.get('trade_type'), mapped.get('portfolio_short_name'), mapped.get('security_label'))
            ok += 1
            continue

        sql = f"UPSERT INTO {DATABASE}.cis_trade ({', '.join(col_names)}) VALUES ({', '.join(col_vals)})"
        try:
            impala_manager.execute_write(sql, database=DATABASE)
            ok += 1
        except Exception as exc:
            msg = f"Row {i} (trade_id={raw_id}): {exc}"
            logger.error(msg)
            errors.append(msg)
            fail += 1
            continue

        # Optionally trigger position calculation — same path as UI settle button
        if with_positions:
            p_ok, p_err = _trigger_position(mapped, raw_id, position_basis=position_basis)
            if p_ok:
                pos_ok += 1
            else:
                pos_fail += 1
                errors.append(p_err)

    if with_positions:
        logger.info("Position results: queued=%d  failed=%d", pos_ok, pos_fail)
    return ok, fail, errors


# ---------------------------------------------------------------------------
# Position trigger helper — mirrors the UI settle button logic exactly
# ---------------------------------------------------------------------------

POSITION_TRADE_TYPES = {'BUY', 'SELL'}


def _trigger_position(
    mapped: Dict[str, Any],
    raw_id: str,
    position_basis: str = 'BOTH',
) -> Tuple[bool, str]:
    """
    Call settlement_service.process_trade_settlement for one trade row.
    Returns (success, error_message).
    Only BUY / SELL trade types create positions; others are skipped silently.

    position_basis:
        'BOTH'       — create TRADED + SETTLED (default, normal behaviour)
        'TRADED' — only the trade-date position (legacy migration behaviour)
        'SETTLED'— only the settle-date position (backfill missing SETTLE rows)
    """
    trade_type = str(mapped.get('trade_type', '') or '').strip().upper()
    if trade_type not in POSITION_TRADE_TYPES:
        logger.debug("trade_id=%s type=%s — not BUY/SELL, position skipped", raw_id, trade_type)
        return True, ''

    try:
        from decimal import Decimal
        from trade.services.settlement_service import settlement_service

        charges = (
            Decimal(str(mapped.get('commission', 0) or 0)) +
            Decimal(str(mapped.get('sec_fee', 0) or 0)) +
            Decimal(str(mapped.get('other_charges', 0) or 0))
        )

        # settle_date defaults to trade_date when absent (T+0 migration data)
        settle_date = str(mapped.get('settle_date', '') or '').strip()
        trade_date  = str(mapped.get('trade_date', '') or '').strip()
        if not settle_date:
            settle_date = trade_date

        # Map --basis CLI value to what settlement_service expects:
        #   'BOTH'        → None   (service creates TRADED + SETTLED)
        #   'TRADED'  → 'TRADED'
        #   'SETTLED' → 'SETTLED'
        svc_basis = None if position_basis == 'BOTH' else position_basis

        # trade_lc / gross_amount_lc / gross_amount_fc — same extraction as the
        # UI settle path (trade_event_queue_service.py, position_queue_service.py):
        # without these, cost_fc/lc gets recomputed from quantity * price / the FX
        # table instead of using the migrated amounts, so migrated positions
        # silently stop tallying with the migrated trade amounts (SA feedback,
        # Venkata Narayana Adisetty, 30/07/2026).
        _raw_glc = mapped.get('gross_amount_lc')
        _raw_tlc = mapped.get('total_amount_lc')
        _raw_gfc = mapped.get('gross_amount_fc')
        gross_amount_lc = Decimal(str(_raw_glc)) if _raw_glc else None
        trade_lc = Decimal(str(_raw_tlc)) if _raw_tlc else None
        gross_amount_fc = Decimal(str(_raw_gfc)) if _raw_gfc else None

        ok, msg, _ = settlement_service.process_trade_settlement(
            trade_id=int(raw_id),
            portfolio_id=mapped.get('portfolio_short_name', ''),
            security_id=mapped.get('security_label', ''),
            trade_type=trade_type,
            quantity=Decimal(str(mapped.get('quantity', 0) or 0)),
            price=Decimal(str(mapped.get('price', 0) or 0)),
            charges=charges,
            trade_date=trade_date,
            settle_date=settle_date,
            updated_by=SRC_SYSTEM,
            security_currency=mapped.get('currency_code'),
            portfolio_currency=mapped.get('portfolio_currency'),
            isin=mapped.get('isin'),
            security_name=mapped.get('security_full_name') or mapped.get('security_label'),
            async_mode=False,
            position_basis=svc_basis,
            trade_lc=trade_lc,
            gross_amount_lc=gross_amount_lc,
            gross_amount_fc=gross_amount_fc,
        )
        if ok:
            logger.info("Position OK  trade_id=%s %s %s qty=%s basis=%s",
                        raw_id, trade_type, mapped.get('security_label'),
                        mapped.get('quantity'), position_basis)
        else:
            logger.warning("Position FAIL trade_id=%s basis=%s: %s", raw_id, position_basis, msg)
        return ok, '' if ok else f"trade_id={raw_id}: {msg}"

    except Exception as exc:
        msg = f"trade_id={raw_id} position error: {exc}"
        logger.error(msg, exc_info=True)
        return False, msg


# ---------------------------------------------------------------------------
# load_position  — backfill positions for trades ALREADY in cis_trade
# ---------------------------------------------------------------------------

def load_position(
    portfolio_filter: str = '',
    trade_type_filter: str = '',
    trade_date_from: str = '',
    trade_date_to: str = '',
    dry_run: bool = False,
    position_basis: str = 'BOTH',
) -> Tuple[int, int, List[str]]:
    """
    Read SETTLED or VALIDATED BUY/SELL trades from cis_trade and create positions.
    Useful for backfilling positions after trades were migrated without --positions.

    GMP-migrated trades arrive as VALIDATED (GMP has no separate SETTLE step).
    CIS-native trades that completed settlement arrive as SETTLED.
    Both represent confirmed positions and are included here.

    Filters (all optional):
        portfolio_filter  — only this portfolio_short_name
        trade_type_filter — 'BUY' or 'SELL' (default: both)
        trade_date_from   — YYYY-MM-DD lower bound on trade_date
        trade_date_to     — YYYY-MM-DD upper bound on trade_date

    position_basis:
        'BOTH'        — create TRADED + SETTLED positions (default)
        'TRADED'  — only TRADED positions
        'SETTLED' — only SETTLED positions (use this to backfill
                        missing SETTLED rows for already-migrated trades)
    """
    ok = fail = 0
    errors: List[str] = []

    # Build WHERE clause — date filters applied in Python after normalising
    # because legacy migrations may have stored dates as DD/MM/YYYY (string
    # comparison against YYYY-MM-DD bounds gives wrong results in SQL).
    # Include VALIDATED: GMP trades land as VALIDATED (no separate settle step).
    conditions = ["status IN ('SETTLED', 'VALIDATED')", "trade_type IN ('BUY','SELL')",
                  "is_deleted = false"]
    if portfolio_filter:
        conditions.append(f"portfolio_short_name = '{portfolio_filter.replace(chr(39), chr(92)+chr(39))}'")
    if trade_type_filter:
        conditions.append(f"trade_type = '{trade_type_filter.upper()}'")

    where = ' AND '.join(conditions)
    sql = (
        f"SELECT trade_id, trade_type, portfolio_short_name, security_label, "
        f"security_full_name, currency_code, portfolio_currency, isin, "
        f"quantity, price, commission, sec_fee, other_charges, "
        f"gross_amount_lc, total_amount_lc, gross_amount_fc, "
        f"trade_date, settle_date "
        f"FROM {DATABASE}.cis_trade WHERE {where} "
        f"ORDER BY trade_date, trade_id"
    )

    logger.info("Fetching trades: %s", sql)
    rows = impala_manager.execute_query(sql, database=DATABASE)
    if not rows:
        logger.info("No SETTLED/VALIDATED BUY/SELL trades found matching the filter.")
        return 0, 0, []

    # Apply date-range filters in Python after normalising stored date strings
    from datetime import date as _date
    _from_dt = datetime.strptime(trade_date_from, '%Y-%m-%d').date() if trade_date_from else None
    _to_dt   = datetime.strptime(trade_date_to,   '%Y-%m-%d').date() if trade_date_to   else None
    if _from_dt or _to_dt:
        filtered = []
        for r in rows:
            _td = _normalise_date(r.get('trade_date', ''))
            try:
                _td_dt = datetime.strptime(_td, '%Y-%m-%d').date()
            except ValueError:
                filtered.append(r)   # can't parse — include and let settlement_service handle
                continue
            if _from_dt and _td_dt < _from_dt:
                continue
            if _to_dt and _td_dt > _to_dt:
                continue
            filtered.append(r)
        logger.info("Date filter applied: %d → %d rows", len(rows), len(filtered))
        rows = filtered

    logger.info("Found %d trades to process for positions", len(rows))

    for i, row in enumerate(rows, 1):
        raw_id = str(row.get('trade_id', ''))
        # Normalise dates from DB — may be stored as DD/MM/YYYY from old migration
        row = dict(row)
        row['trade_date']  = _normalise_date(row.get('trade_date',  ''))
        row['settle_date'] = _normalise_date(row.get('settle_date', ''))
        if not row['settle_date']:
            row['settle_date'] = row['trade_date']

        if dry_run:
            logger.info("[DRY-RUN] position row %d: trade_id=%s %s %s qty=%s trade_date=%s",
                        i, raw_id, row.get('trade_type'), row.get('security_label'),
                        row.get('quantity'), row.get('trade_date'))
            ok += 1
            continue

        p_ok, p_err = _trigger_position(row, raw_id, position_basis=position_basis)
        if p_ok:
            ok += 1
        else:
            fail += 1
            errors.append(p_err)

        if i % 50 == 0:
            logger.info("Progress: %d / %d  (ok=%d fail=%d)", i, len(rows), ok, fail)

    return ok, fail, errors


# ---------------------------------------------------------------------------
# cis_portfolio
# ---------------------------------------------------------------------------

PORTFOLIO_ALIASES: Dict[str, str] = {
    # Primary key
    'name':                 'name',
    'portfolio_name':       'name',
    'portfolio_short_name': 'name',
    'short_name':           'name',
    'code':                 'name',

    'description':          'description',
    'desc':                 'description',
    'portfolio_full_name':  'description',
    'full_name':            'description',

    # Currency / settlement
    'currency':             'currency',
    'currency_code':        'currency',
    'base_currency':        'currency',
    'settlement_ccy':       'settlement_ccy',
    'settlement_currency':  'settlement_ccy',

    # People
    'manager':              'manager',
    'portfolio_manager':    'manager',
    'desk_head':            'desk_head',
    'portfolio_owner':      'portfolio_owner',
    'portfolio_client':     'portfolio_client',
    'client':               'portfolio_client',

    # Grouping / classification
    'account_group':        'account_group',
    'portfolio_group':      'portfolio_group',
    'report_group':         'report_group',
    'entity_group':         'entity_group',
    'entity':               'entity',
    'business_line':        'business_line',
    'investment_type':      'investment_type',
    'accounting_section':   'accounting_section',

    # Codes
    'cost_centre_code':     'cost_centre_code',
    'cost_centre':          'cost_centre_code',
    'corp_code':            'corp_code',
    'branch_code':          'branch_code',
    'country':              'country',

    # Settings
    'revaluation_status':   'revaluation_status',
    'revaluation':          'revaluation_status',
    'cash_balance_list':    'cash_balance_list',
    'closure_date':         'closure_date',

    # Workflow & audit
    'status':               'status',
    'is_active':            'is_active',
    'is_deleted':           'is_deleted',
    'created_by':           'created_by',
    'updated_by':           'updated_by',
    'created_at':           'created_at',
    'updated_at':           'updated_at',
    'src_system':           'src_system',
    'submitted_by':         'submitted_by',
    'submitted_at':         'submitted_at',
    'validated_by':         'validated_by',
    'validated_at':         'validated_at',
    'settled_by':           'settled_by',
    'settled_at':           'settled_at',
    'cancelled_by':         'cancelled_by',
    'cancelled_at':         'cancelled_at',
    'cancel_reason':        'cancel_reason',
}

PORTFOLIO_BOOL_COLS = {'is_active', 'is_deleted'}

# All columns that exist in the live cis_portfolio Kudu table.
# Any mapped key NOT in this set is silently dropped before the UPSERT.
PORTFOLIO_VALID_COLS = {
    'name', 'description', 'currency', 'manager', 'portfolio_client',
    'settlement_ccy', 'cash_balance_list', 'status', 'cost_centre_code', 'corp_code',
    'account_group', 'portfolio_group', 'report_group', 'entity_group',
    'revaluation_status', 'is_active', 'is_deleted', 'accounting_section', 'src_system',
    'created_by', 'created_at', 'updated_by', 'updated_at',
    'submitted_by', 'submitted_at', 'validated_by', 'validated_at',
    'settled_by', 'settled_at', 'cancelled_by', 'cancelled_at', 'cancel_reason',
    'entity', 'business_line', 'investment_type', 'branch_code',
    'desk_head', 'portfolio_owner', 'closure_date', 'country',
}


def load_portfolio(rows: List[Dict], status: str, dry_run: bool, processing_date: str = '') -> Tuple[int, int, List[str]]:
    ok = fail = 0
    errors: List[str] = []
    ts = _now()

    for i, raw in enumerate(rows, 1):
        mapped: Dict[str, Any] = {}
        for raw_col, raw_val in raw.items():
            db_col = PORTFOLIO_ALIASES.get(raw_col)
            if db_col:
                mapped[db_col] = raw_val

        pk = mapped.get('name', '').strip()
        if not pk:
            msg = f"Row {i}: missing portfolio name — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        # Fixed / derived fields
        mapped['src_system'] = SRC_SYSTEM
        mapped.setdefault('status', status)
        mapped.setdefault('is_active', True)
        mapped.setdefault('is_deleted', False)
        mapped.setdefault('created_by', SRC_SYSTEM)
        mapped.setdefault('updated_by', SRC_SYSTEM)
        mapped.setdefault('created_at', ts)
        mapped['updated_at'] = ts

        # Normalise closure_date if present
        if mapped.get('closure_date'):
            mapped['closure_date'] = _normalise_date(mapped['closure_date'])

        # Drop columns not in live schema
        mapped = {k: v for k, v in mapped.items() if k in PORTFOLIO_VALID_COLS}

        col_names = []
        col_vals = []
        for col, val in mapped.items():
            col_names.append(col)
            if col in PORTFOLIO_BOOL_COLS:
                col_vals.append(_bool(val))
            else:
                col_vals.append(_escape(val))

        if dry_run:
            logger.info("[DRY-RUN] portfolio row %d: name=%s status=%s currency=%s",
                        i, pk, mapped.get('status'), mapped.get('currency'))
            ok += 1
            continue

        sql = f"UPSERT INTO {DATABASE}.cis_portfolio ({', '.join(col_names)}) VALUES ({', '.join(col_vals)})"
        try:
            impala_manager.execute_write(sql, database=DATABASE)
            logger.info("Loaded portfolio row %d: name=%s", i, pk)
            ok += 1
        except Exception as exc:
            msg = f"Row {i} ({pk}): {exc}"
            logger.error(msg)
            errors.append(msg)
            fail += 1

    return ok, fail, errors


# ---------------------------------------------------------------------------
# cis_cash_flow
# ---------------------------------------------------------------------------

CASH_FLOW_ALIASES: Dict[str, str] = {
    # Identifiers (both auto-generated; CSV values ignored for PK)
    'cash_flow_id':         'cash_flow_id',        # ignored — always auto-generated
    'cash_flow_number':     'cash_flow_number',    # ignored — always auto-generated

    # Required business fields
    'portfolio_short_name': 'portfolio_short_name',
    'portfolio':            'portfolio_short_name',
    'portfolio_name':       'portfolio_short_name',

    'security_label':       'security_label',
    'security':             'security_label',
    'security_name':        'security_label',

    'cash_flow_type':       'cash_flow_type',
    'type':                 'cash_flow_type',
    'cf_type':              'cash_flow_type',

    'send_receive':         'send_receive',
    'direction':            'send_receive',

    # Amount fields
    'foreign_ccy':          'foreign_ccy',
    'foreign_currency':     'foreign_ccy',
    'local_ccy':            'local_ccy',
    'local_currency':       'local_ccy',

    'local_ccy_amt':        'local_ccy_amt',
    'local_amount':         'local_ccy_amt',
    'amount_lc':            'local_ccy_amt',

    'foreign_ccy_amt':      'foreign_ccy_amt',
    'foreign_amount':       'foreign_ccy_amt',
    'amount_fc':            'foreign_ccy_amt',
    'amount':               'foreign_ccy_amt',

    'flow_amount_local':    'flow_amount_local',
    'dividend_price':       'dividend_price',
    'quantity':             'quantity',
    'qty':                  'quantity',
    'fx_rate':              'fx_rate',

    'gl_acc_no':            'gl_acc_no',
    'gl_account':           'gl_acc_no',

    # Date fields
    'payment_date':         'payment_date',
    'pay_date':             'payment_date',
    'trade_date':           'trade_date',
    'value_date':           'value_date',
    'dividend_date':        'dividend_date',
    'ex_date':              'ex_date',
    'record_date':          'record_date',

    # CA reference (optional — leave blank for user-created migrations)
    'ca_id':                'ca_id',
    'ca_number':            'ca_number',

    # Workflow
    'status':               'status',
    'is_active':            'is_active',
    'is_deleted':           'is_deleted',
    'created_by':           'created_by',
    'updated_by':           'updated_by',
}

CASH_FLOW_DECIMAL_COLS = {
    'local_ccy_amt', 'foreign_ccy_amt', 'flow_amount_local',
    'dividend_price', 'quantity', 'fx_rate',
}
CASH_FLOW_BIGINT_COLS = {'ca_id'}
CASH_FLOW_BOOL_COLS   = {'is_active', 'is_deleted', 'cf_processed'}


def _next_cf_number(index: int) -> str:
    """Generate a cash_flow_number in the same format as the UI: CF-YYYYMMDD-NNNN."""
    date_str = datetime.now().strftime('%Y%m%d')
    return f"CF-{date_str}-{str(index).zfill(4)}"


def load_cash_flow(rows: List[Dict], status: str, dry_run: bool, processing_date: str = '') -> Tuple[int, int, List[str]]:
    ok = fail = 0
    errors: List[str] = []
    ts = _now()

    for i, raw in enumerate(rows, 1):
        mapped: Dict[str, Any] = {}
        for raw_col, raw_val in raw.items():
            db_col = CASH_FLOW_ALIASES.get(raw_col)
            if db_col:
                mapped[db_col] = raw_val

        # Validate required fields
        portfolio = str(mapped.get('portfolio_short_name', '') or '').strip()
        if not portfolio:
            msg = f"Row {i}: missing portfolio_short_name — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        security = str(mapped.get('security_label', '') or '').strip()
        if not security:
            msg = f"Row {i}: missing security_label — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        cf_type = str(mapped.get('cash_flow_type', '') or '').strip()
        if not cf_type:
            msg = f"Row {i} ({portfolio}/{security}): missing cash_flow_type — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        payment_date = _normalise_date(mapped.get('payment_date', ''))
        if not payment_date:
            msg = f"Row {i} ({portfolio}/{security}): missing payment_date — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        # Auto-generate PK and number — always, regardless of CSV content
        cash_flow_id = _timestamp_ms() + i
        cash_flow_number = _next_cf_number(cash_flow_id % 10000)  # last 4 digits of ms timestamp

        # Normalise all date columns
        for _dcol in ('payment_date', 'trade_date', 'value_date', 'dividend_date',
                      'ex_date', 'record_date'):
            if mapped.get(_dcol):
                mapped[_dcol] = _normalise_date(mapped[_dcol])

        # Fixed / derived fields
        mapped['cash_flow_id']     = cash_flow_id
        mapped['cash_flow_number'] = cash_flow_number
        mapped['src_system']       = SRC_SYSTEM
        mapped['cf_processed'] = False
        mapped.setdefault('status',     status)
        mapped.setdefault('is_active',  True)
        mapped.setdefault('is_deleted', False)
        mapped.setdefault('send_receive', 'SEND')
        mapped.setdefault('created_by', 'SYSTEM')
        mapped.setdefault('updated_by', 'SYSTEM')
        mapped['created_at'] = ts
        mapped['updated_at'] = ts

        if dry_run:
            logger.info(
                "[DRY-RUN] cash_flow row %d: cf_id=%s cf_number=%s portfolio=%s security=%s type=%s payment_date=%s",
                i, cash_flow_id, cash_flow_number, portfolio, security, cf_type, payment_date
            )
            ok += 1
            continue

        col_names = []
        col_vals  = []
        for col, val in mapped.items():
            col_names.append(col)
            if col in CASH_FLOW_BOOL_COLS:
                col_vals.append(_bool(val))
            elif col in CASH_FLOW_DECIMAL_COLS:
                col_vals.append(_decimal(val))
            elif col in CASH_FLOW_BIGINT_COLS:
                col_vals.append(_bigint(val))
            elif col == 'cash_flow_id':
                col_vals.append(str(val))          # bare BIGINT — no quotes
            else:
                col_vals.append(_escape(val))

        sql = (
            f"UPSERT INTO {DATABASE}.cis_cash_flow "
            f"({', '.join(col_names)}) VALUES ({', '.join(col_vals)})"
        )
        try:
            impala_manager.execute_write(sql, database=DATABASE)
            logger.info(
                "Loaded cash_flow row %d: cf_id=%s cf_number=%s portfolio=%s security=%s type=%s",
                i, cash_flow_id, cash_flow_number, portfolio, security, cf_type
            )
            ok += 1
        except Exception as exc:
            msg = f"Row {i} ({portfolio}/{security}): {exc}"
            logger.error(msg)
            errors.append(msg)
            fail += 1

    return ok, fail, errors


# ---------------------------------------------------------------------------
# cis_corporate_actions
# ---------------------------------------------------------------------------
# Mirrors reference_data/management/commands/sync_gmp_corporate_actions.py —
# same target table (cis_corporate_actions), same ca_type normalisation
# (GMP_CA_TYPE_MAP) and date/price parsing, reused directly from that module
# rather than duplicated here, so the two stay in sync.

CA_ALIASES: Dict[str, str] = {
    'ca_number':                 'ca_number',
    'number':                    'ca_number',
    # ca_id is the source system's own reference — kept distinct from
    # ca_number (confirmed via a real migration CSV that carries both as
    # separate, independently-populated columns). It isn't written anywhere
    # today (corporate_action_repository.insert() generates its own internal
    # ca_id), so it's mapped through for visibility/logging only.
    'ca_id':                     'source_ca_id',

    'ca_type':                   'ca_type',
    'type':                      'ca_type',

    'security_name':             'security_name',
    'security':                  'security_name',
    'security_label':            'security_name',

    'announcement_date':         'announcement_date',
    'ex_date':                   'ex_date',
    'record_date':               'record_date',
    'payment_date':              'payment_date',
    'pay_date':                  'payment_date',
    'effective_date':            'effective_date',
    'subscription_start_date':   'subscription_start_date',
    'subscription_end_date':     'subscription_end_date',

    'price':                     'price',
    'rate':                      'price',

    'currency':                  'currency',
    'currency_code':             'currency',

    'status':                    'status',
    'is_deleted':                'is_deleted',
}

CA_DATE_FIELDS = (
    'announcement_date', 'ex_date', 'record_date', 'payment_date',
    'effective_date', 'subscription_start_date', 'subscription_end_date',
)


def load_corporate_action(
    rows: List[Dict],
    status: str,
    dry_run: bool,
    processing_date: str = '',
    with_queue: bool = False,
) -> Tuple[int, int, List[str]]:
    """
    Load corporate actions from CSV into cis_corporate_actions, same target
    table and ca_type/date/price normalisation as sync_gmp_corporate_actions.py
    (that command syncs from the GMP source table; this loads from a
    migration CSV instead — both funnel through the same
    corporate_action_repository.insert()).

    with_queue: if True, also queue each inserted CA for cash flow processing
    via ca_cash_flow_service.queue_ca_for_processing() — same as the UI/GMP
    sync path. Leave off (default) for historical migration rows that should
    NOT trigger new cash flow generation (use --table cash_flow to load the
    already-known historical cash flows directly instead).
    """
    from reference_data.repositories.corporate_action_repository import corporate_action_repository
    from reference_data.management.commands.sync_gmp_corporate_actions import (
        map_gmp_ca_type, parse_gmp_date, parse_gmp_price, GMP_CA_TYPE_MAP,
    )

    KNOWN_CA_TYPES = set(GMP_CA_TYPE_MAP.values())

    ok = fail = queued = 0
    errors: List[str] = []

    for i, raw in enumerate(rows, 1):
        mapped: Dict[str, Any] = {}
        for raw_col, raw_val in raw.items():
            db_col = CA_ALIASES.get(raw_col)
            if db_col:
                mapped[db_col] = raw_val

        # ca_number: use CSV value if present, otherwise auto-generate — same
        # fallback load_trade uses for a missing trade_id. Confirmed via a
        # real migration CSV that ca_number (and ca_id) can arrive blank for
        # every row, so skipping on missing ca_number silently dropped the
        # entire file.
        ca_number = str(mapped.get('ca_number', '') or '').strip()
        if not ca_number:
            ca_number = f"CIS-CA-{_timestamp_ms() + i}"
            logger.debug("Row %d: ca_number not in CSV, auto-generated %s", i, ca_number)

        security_name = str(mapped.get('security_name', '') or '').strip()
        if not security_name:
            msg = f"Row {i} (ca_number={ca_number}): missing security_name — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        # ca_type: accept an already-canonical CIS type as-is (case-insensitive),
        # otherwise fall back to the same GMP_CA_TYPE_MAP sync_gmp_corporate_actions.py
        # uses, so a migration CSV can carry either form.
        raw_type = str(mapped.get('ca_type', '') or '').strip()
        cis_type = raw_type.upper() if raw_type.upper() in KNOWN_CA_TYPES else map_gmp_ca_type(raw_type)
        if not cis_type:
            msg = (f"Row {i} (ca_number={ca_number}): unrecognised ca_type={raw_type!r} — "
                   f"not a known CIS type and not in GMP_CA_TYPE_MAP — skipped")
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        # Normalise date columns — parse_gmp_date handles DD/MM/YYYY, YYYYMMDD,
        # YYYY-MM-DD etc; keep the raw value if it can't be parsed rather than
        # dropping the row (matches load_trade's _normalise_date behaviour).
        for dcol in CA_DATE_FIELDS:
            if mapped.get(dcol):
                mapped[dcol] = parse_gmp_date(mapped[dcol]) or mapped[dcol]

        price = parse_gmp_price(mapped.get('price')) if mapped.get('price') else None

        ca_data = {
            'ca_number':          ca_number,
            'ca_type':            cis_type,
            'security_name':      security_name,
            'announcement_date':  mapped.get('announcement_date'),
            'ex_date':            mapped.get('ex_date'),
            'record_date':        mapped.get('record_date'),
            'payment_date':       mapped.get('payment_date'),
            'effective_date':     mapped.get('effective_date'),
            'subscription_start_date': mapped.get('subscription_start_date'),
            'subscription_end_date':   mapped.get('subscription_end_date'),
            'price':              price,
            'currency':           mapped.get('currency'),
            'src_system':         SRC_SYSTEM,
            'status':             str(mapped.get('status', '') or '').strip() or status,
        }

        if dry_run:
            logger.info("[DRY-RUN] CA row %d: ca_number=%s type=%s security=%s",
                        i, ca_number, cis_type, security_name)
            ok += 1
            continue

        try:
            success, ca_id = corporate_action_repository.insert(ca_data, created_by=SRC_SYSTEM)
        except Exception as exc:
            msg = f"Row {i} (ca_number={ca_number}): {exc}"
            logger.error(msg)
            errors.append(msg)
            fail += 1
            continue

        if not success:
            msg = f"Row {i} (ca_number={ca_number}): insert failed"
            logger.error(msg)
            errors.append(msg)
            fail += 1
            continue

        ok += 1
        logger.info("Loaded CA row %d: ca_number=%s type=%s security=%s", i, ca_number, cis_type, security_name)

        if with_queue:
            try:
                from reference_data.services.ca_cash_flow_service import ca_cash_flow_service
                q_success, queue_id = ca_cash_flow_service.queue_ca_for_processing(
                    ca_id=ca_id, ca_data=ca_data, username=SRC_SYSTEM,
                )
                if q_success:
                    queued += 1
                    logger.info("  → Queued ca_number=%s (queue_id=%s)", ca_number, queue_id)
            except Exception as exc:
                logger.warning("Queue error for %s: %s", ca_number, exc)

    if with_queue:
        logger.info("Cash flow queue results: queued=%d", queued)
    return ok, fail, errors


# ---------------------------------------------------------------------------
# generic LUT (lookup table) loader
# ---------------------------------------------------------------------------
# Unlike the loaders above (party/security/trade/...), this one has no
# hardcoded column alias map. It targets the common shape shared by every
# cis_*_lookup table (see sql/ddl/08_trade_lookup_tables_kudu.sql):
#   <pk_code> STRING NOT NULL PRIMARY KEY, ...STRING columns..., is_active
#   BOOLEAN, display_order INT
# CSV header names are taken as-is (normalised the same way as every other
# loader) and UPSERTed straight into whichever table --lut-table names, so
# one implementation works for any of them without new Python per table.

def load_lut(
    rows: List[Dict],
    dry_run: bool,
    lut_table: str,
    pk_column: str,
    bool_columns: Optional[List[str]] = None,
    int_columns: Optional[List[str]] = None,
) -> Tuple[int, int, List[str]]:
    """
    Generic loader for cis_*_lookup / cis_*_lut tables.

    Args:
        rows: parsed CSV rows (headers already normalised by _read_csv)
        dry_run: parse/validate only, no writes
        lut_table: target table name, e.g. 'cis_delivery_type_lookup'
                   (bare name — DATABASE prefix is added automatically)
        pk_column: CSV column that holds the primary key (e.g. 'delivery_type_code')
        bool_columns: CSV columns to coerce with _bool() (e.g. ['is_active'])
        int_columns: CSV columns to coerce with _bigint() (e.g. ['display_order'])

    Returns:
        (ok, fail, errors)
    """
    ok = fail = 0
    errors: List[str] = []
    bool_cols = set(bool_columns or [])
    int_cols = set(int_columns or [])

    for i, raw in enumerate(rows, 1):
        pk_val = str(raw.get(pk_column, '') or '').strip()
        if not pk_val:
            msg = f"Row {i}: missing {pk_column} — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        # Drop columns with no header value at all (blank trailing columns etc.)
        mapped = {col: val for col, val in raw.items() if col}

        # is_active defaults to true when the CSV doesn't supply it — matches
        # every seeded lookup table, which is always active-by-default.
        if 'is_active' in bool_cols:
            mapped.setdefault('is_active', True)

        if dry_run:
            logger.info("[DRY-RUN] %s row %d: %s=%s", lut_table, i, pk_column, pk_val)
            ok += 1
            continue

        col_names = []
        col_vals = []
        for col, val in mapped.items():
            col_names.append(col)
            if col in bool_cols:
                col_vals.append(_bool(val))
            elif col in int_cols:
                col_vals.append(_bigint(val))
            else:
                col_vals.append(_escape(val))

        sql = f"UPSERT INTO {DATABASE}.{lut_table} ({', '.join(col_names)}) VALUES ({', '.join(col_vals)})"
        try:
            impala_manager.execute_write(sql, database=DATABASE)
            ok += 1
        except Exception as exc:
            msg = f"Row {i} ({pk_val}): {exc}"
            logger.error(msg)
            errors.append(msg)
            fail += 1

    return ok, fail, errors


# ---------------------------------------------------------------------------
# error report
# ---------------------------------------------------------------------------

def _write_error_csv(table: str, errors: List[str]) -> Optional[str]:
    if not errors:
        return None
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = f"load_migration_errors_{table}_{ts}.csv"
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['error'])
        for e in errors:
            w.writerow([e])
    return path


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

LOADERS = {
    'party':             load_party,
    'party_cif':          load_party_cif,
    'security':           load_security,
    'trade':              load_trade,
    'portfolio':          load_portfolio,
    'cash_flow':          load_cash_flow,
    'corporate_action':   load_corporate_action,
}

# Default status per table (can be overridden with --status)
DEFAULT_STATUS = {
    'party':             'ACTIVE',
    'party_cif':          'ACTIVE',
    'security':           'ACTIVE',
    'trade':              'SETTLED',
    'portfolio':          'SETTLED',
    'cash_flow':          'VALIDATED',
    'corporate_action':   'VALIDATED',
}

ALL_TABLES = list(LOADERS) + ['position', 'lut']


def main():
    today_yyyymmdd = datetime.now().strftime('%Y%m%d')
    today_iso      = datetime.now().strftime('%Y-%m-%d')

    parser = argparse.ArgumentParser(
        description='CIS migration data loader',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load portfolios from CSV
  python scripts/load_migration_data.py --table portfolio --file portfolios.csv

  # Dry-run: validate portfolio CSV without writing
  python scripts/load_migration_data.py --table portfolio --file portfolios.csv --dry-run

  # Load portfolios with a specific status (default: SETTLED)
  python scripts/load_migration_data.py --table portfolio --file portfolios.csv --status ACTIVE

  # Load trades from CSV (no positions)
  python scripts/load_migration_data.py --table trade --file trades.csv

  # Load trades AND create BOTH positions (TRADED + SETTLED) in one pass
  python scripts/load_migration_data.py --table trade --file trades.csv --positions

  # Load cash flows from CSV (cash_flow_id + cash_flow_number auto-generated, src_system=CIS)
  python scripts/load_migration_data.py --table cash_flow --file cashflows.csv

  # Load cash flows with a specific status override (default: APPROVED)
  python scripts/load_migration_data.py --table cash_flow --file cashflows.csv --status INITIAL

  # Dry-run: validate cash flow CSV without writing
  python scripts/load_migration_data.py --table cash_flow --file cashflows.csv --dry-run

  # Load corporate actions from CSV (into cis_corporate_actions, src_system=CIS)
  # ca_type accepts either a canonical CIS type (DIVIDEND, BONUS_ISSUE, ...) or
  # a raw GMP-style code (Cash dividend, CLAS SP, ...) via GMP_CA_TYPE_MAP.
  python scripts/load_migration_data.py --table corporate_action --file corporate_actions.csv

  # Load corporate actions AND queue each one for cash flow processing
  # (same as the UI/GMP sync path — use only if these CAs' cash flows have
  # NOT already been migrated separately via --table cash_flow)
  python scripts/load_migration_data.py --table corporate_action --file corporate_actions.csv --queue-cashflow

  # Dry-run: validate corporate action CSV without writing
  python scripts/load_migration_data.py --table corporate_action --file corporate_actions.csv --dry-run

  # Backfill BOTH positions for all trades already in cis_trade
  python scripts/load_migration_data.py --table position

  # Backfill ONLY missing SETTLED positions (trades were already migrated
  # with TRADED only — this fills in the SETTLED gap for src_system=CIS)
  python scripts/load_migration_data.py --table position --basis SETTLED

  # Backfill SETTLED positions for one portfolio only
  python scripts/load_migration_data.py --table position --basis SETTLED \\
      --portfolio UOB-KH-PTE-LTD

  # Backfill SETTLED positions for a date range
  python scripts/load_migration_data.py --table position --basis SETTLED \\
      --trade-date-from 2026-01-01 --trade-date-to 2026-05-23

  # Dry-run: see what would be processed without writing
  python scripts/load_migration_data.py --table position --basis SETTLED --dry-run

  # Load ANY lookup table generically — CSV header names are used as-is,
  # no per-table Python needed. Column names must match the target table.
  python scripts/load_migration_data.py --table lut \\
      --lut-table cis_delivery_type_lookup --lut-pk delivery_type_code \\
      --lut-bool-cols is_active --lut-int-cols display_order \\
      --file delivery_types.csv

  # Dry-run a LUT load
  python scripts/load_migration_data.py --table lut \\
      --lut-table cis_broker_lookup --lut-pk broker_code \\
      --lut-bool-cols is_active --lut-int-cols display_order \\
      --file brokers.csv --dry-run
""")
    parser.add_argument('--table',           required=True, choices=ALL_TABLES,
                        help='Target table. Use "position" to backfill positions from existing cis_trade rows.')
    parser.add_argument('--file',            default='',
                        help='Path to CSV file (required for party/party_cif/security/trade)')
    parser.add_argument('--delimiter',       default=',',   help='CSV delimiter (default: ,)')
    parser.add_argument('--status',          default=None,
                        help='status value to set. Defaults: party/party_cif/security=ACTIVE, trade=SETTLED')
    parser.add_argument('--processing-date', default=today_yyyymmdd,
                        help='processing_date in YYYYMMDD format (default: today). '
                             'CSV column value takes priority if present.')
    parser.add_argument('--dry-run',         action='store_true', help='Parse and validate only, no writes')

    # Trade-specific: generate positions after loading
    parser.add_argument('--positions',       action='store_true',
                        help='(--table trade only) Also trigger position calculation for each loaded trade')

    # Corporate-action-specific: queue for cash flow generation after loading
    parser.add_argument('--queue-cashflow',  action='store_true',
                        help='(--table corporate_action only) Also queue each loaded CA for cash flow '
                             'processing via ca_cash_flow_service (same as the UI/GMP sync path). '
                             'Leave off for historical CAs whose cash flows are being migrated '
                             'directly via --table cash_flow instead.')

    # Position backfill filters
    parser.add_argument('--portfolio',       default='',
                        help='(--table position) Filter by portfolio_short_name')
    parser.add_argument('--trade-type',      default='', choices=['', 'BUY', 'SELL'],
                        help='(--table position) Filter by trade_type (default: both BUY and SELL)')
    parser.add_argument('--trade-date-from', default='',
                        help='(--table position) Lower bound on trade_date (YYYY-MM-DD)')
    parser.add_argument('--trade-date-to',   default='',
                        help='(--table position) Upper bound on trade_date (YYYY-MM-DD, default: today)')
    # Generic LUT loader options
    parser.add_argument('--lut-table',       default='',
                        help='(--table lut) Target table name, e.g. cis_delivery_type_lookup')
    parser.add_argument('--lut-pk',          default='',
                        help='(--table lut) CSV column holding the primary key, e.g. delivery_type_code')
    parser.add_argument('--lut-bool-cols',   default='',
                        help='(--table lut) Comma-separated CSV columns to treat as boolean, e.g. is_active')
    parser.add_argument('--lut-int-cols',    default='',
                        help='(--table lut) Comma-separated CSV columns to treat as integer, e.g. display_order')

    parser.add_argument('--basis',           default='BOTH',
                        choices=['BOTH', 'TRADED', 'SETTLED'],
                        help='Which position basis to create. '
                             'BOTH=TRADED+SETTLED (default). '
                             'Use SETTLED to backfill missing settle-date '
                             'positions for trades already migrated with TRADED only.')

    args = parser.parse_args()

    # ------------------------------------------------------------------ #
    # --table position: backfill positions from existing cis_trade rows   #
    # ------------------------------------------------------------------ #
    if args.table == 'position':
        date_to = args.trade_date_to or today_iso
        logger.info(
            "Backfilling positions from cis_trade "
            "(portfolio=%r type=%r from=%r to=%r basis=%s dry_run=%s)",
            args.portfolio, args.trade_type, args.trade_date_from,
            date_to, args.basis, args.dry_run
        )
        ok, fail, errors = load_position(
            portfolio_filter=args.portfolio,
            trade_type_filter=args.trade_type,
            trade_date_from=args.trade_date_from,
            trade_date_to=date_to,
            dry_run=args.dry_run,
            position_basis=args.basis,
        )
        print()
        print("=" * 55)
        print(f"  Mode             : Position backfill from cis_trade")
        print(f"  Portfolio filter : {args.portfolio or '(all)'}")
        print(f"  Trade type       : {args.trade_type or 'BUY + SELL'}")
        print(f"  Date range       : {args.trade_date_from or '(any)'} → {date_to}")
        print(f"  Position basis   : {args.basis}")
        print(f"  Positions queued : {ok}")
        print(f"  Failed           : {fail}")
        if args.dry_run:
            print("  Mode             : DRY RUN — no data written")
        print("=" * 55)
        if errors:
            err_file = _write_error_csv('position', errors)
            if err_file:
                print(f"  Errors  → {err_file}")
        sys.exit(0 if fail == 0 else 1)

    # ------------------------------------------------------------------ #
    # --table lut: generic lookup-table loader                           #
    # ------------------------------------------------------------------ #
    if args.table == 'lut':
        if not args.lut_table:
            parser.error('--lut-table is required for --table lut')
        if not args.lut_pk:
            parser.error('--lut-pk is required for --table lut')
        if not args.file:
            parser.error('--file is required for --table lut')
        if not os.path.isfile(args.file):
            logger.error("File not found: %s", args.file)
            sys.exit(1)

        bool_cols = [c.strip() for c in args.lut_bool_cols.split(',') if c.strip()]
        int_cols = [c.strip() for c in args.lut_int_cols.split(',') if c.strip()]

        logger.info(
            "Loading LUT %s from %s (pk=%s bool_cols=%s int_cols=%s dry_run=%s)",
            args.lut_table, args.file, args.lut_pk, bool_cols, int_cols, args.dry_run
        )
        headers, rows = _read_csv(args.file, args.delimiter)
        logger.info("Read %d rows, columns: %s", len(rows), headers)

        if args.lut_pk not in headers:
            logger.error(
                "--lut-pk %r not found in CSV headers %s", args.lut_pk, headers
            )
            sys.exit(1)

        ok, fail, errors = load_lut(
            rows,
            dry_run=args.dry_run,
            lut_table=args.lut_table,
            pk_column=args.lut_pk,
            bool_columns=bool_cols,
            int_columns=int_cols,
        )
        print()
        print("=" * 55)
        print(f"  Table            : {DATABASE}.{args.lut_table}")
        print(f"  File             : {args.file}")
        print(f"  PK column        : {args.lut_pk}")
        print(f"  Total rows       : {len(rows)}")
        if args.dry_run:
            print("  Mode             : DRY RUN — no data written")
            print(f"  Would process    : {ok}")
        else:
            print(f"  Loaded           : {ok}")
        print(f"  Failed/Skipped   : {fail}")
        print("=" * 55)
        if errors:
            err_file = _write_error_csv(args.lut_table, errors)
            if err_file:
                print(f"  Errors  → {err_file}")
        sys.exit(0 if fail == 0 else 1)

    # ------------------------------------------------------------------ #
    # All other tables: standard CSV load                                  #
    # ------------------------------------------------------------------ #

    # Validate YYYYMMDD format
    proc_date = args.processing_date
    try:
        datetime.strptime(proc_date, '%Y%m%d')
    except ValueError:
        logger.error("--processing-date must be YYYYMMDD, got: %s", proc_date)
        sys.exit(1)

    if not args.file:
        parser.error(f"--file is required for --table {args.table}")

    if not os.path.isfile(args.file):
        logger.error("File not found: %s", args.file)
        sys.exit(1)

    effective_status = args.status or DEFAULT_STATUS[args.table]
    logger.info("Loading %s from %s (dry_run=%s, status=%s, processing_date=%s, positions=%s)",
                args.table, args.file, args.dry_run, effective_status, proc_date,
                args.positions if args.table == 'trade' else 'N/A')
    headers, rows = _read_csv(args.file, args.delimiter)
    logger.info("Read %d rows, columns: %s", len(rows), headers)

    if args.table == 'trade':
        ok, fail, errors = load_trade(
            rows, effective_status, args.dry_run, proc_date,
            with_positions=args.positions,
            position_basis=args.basis,
        )
    elif args.table == 'corporate_action':
        ok, fail, errors = load_corporate_action(
            rows, effective_status, args.dry_run, proc_date,
            with_queue=args.queue_cashflow,
        )
    else:
        loader = LOADERS[args.table]
        ok, fail, errors = loader(rows, effective_status, args.dry_run, proc_date)

    # cis_corporate_actions is the one target table that doesn't match cis_<table> (singular)
    display_table = 'cis_corporate_actions' if args.table == 'corporate_action' else f'cis_{args.table}'
    print()
    print("=" * 55)
    print(f"  Table            : {DATABASE}.{display_table}")
    print(f"  File             : {args.file}")
    print(f"  processing_date  : {proc_date}")
    print(f"  Total rows       : {len(rows)}")
    if args.dry_run:
        print("  Mode             : DRY RUN — no data written")
        if args.table == 'security':
            print(f"  Would INSERT     : (see log — rows not yet in DB)")
            print(f"  Would UPDATE     : (see log — rows already in DB)")
        else:
            print(f"  Would process    : {ok}")
    else:
        print(f"  Loaded           : {ok}")
    print(f"  Failed/Skipped   : {fail}")
    if args.table == 'trade' and args.positions:
        print(f"  Positions        : triggered alongside each trade")
    if args.table == 'corporate_action' and args.queue_cashflow:
        print(f"  Cash flow queue  : triggered alongside each CA")
    print("=" * 55)

    if errors:
        err_file = _write_error_csv(args.table, errors)
        if err_file:
            print(f"  Errors  → {err_file}")

    sys.exit(0 if fail == 0 else 1)


if __name__ == '__main__':
    main()
