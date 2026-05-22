#!/usr/bin/env python
"""
Migration Data Loader — cis_party, cis_party_cif, cis_security, cis_trade
Loads records from CSV files with src_system = 'CIS'.

Usage:
    python scripts/load_migration_data.py --table party      --file /path/to/party.csv
    python scripts/load_migration_data.py --table party_cif  --file /path/to/party_cif.csv
    python scripts/load_migration_data.py --table security   --file /path/to/security.csv
    python scripts/load_migration_data.py --table trade      --file /path/to/trade.csv

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

DATABASE = 'gmp_cis'
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


def _decimal(value: Any) -> str:
    if value is None or str(value).strip() == '':
        return 'NULL'
    try:
        return str(Decimal(str(value).strip()))
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


def _timestamp_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


def _normalise_header(raw: str) -> str:
    return raw.strip().lower().replace(' ', '_').replace('-', '_').replace('/', '_')


def _read_csv(path: str, delimiter: str) -> Tuple[List[str], List[Dict[str, str]]]:
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
    'security_name':        'security_name',
    'name':                 'security_name',

    'isin':                 'isin',
    'security_description': 'security_description',
    'description':          'security_description',
    'desc':                 'security_description',

    'issuer':               'issuer',
    'ticker':               'ticker',
    'symbol':               'ticker',

    'record_type':          'record_type',
    'type':                 'record_type',

    'industry':             'industry',
    'security_type':        'security_type',
    'investment_type':      'investment_type',
    'issuer_type':          'issuer_type',
    'quoted_unquoted':      'quoted_unquoted',
    'quoted':               'quoted_unquoted',

    'country_of_incorporation': 'country_of_incorporation',
    'country_of_exchange':      'country_of_exchange',
    'country_of_issue':         'country_of_issue',
    'exchange_code':            'exchange_code',

    'currency_code':    'currency_code',
    'currency':         'currency_code',

    'price':            'price',
    'shares_outstanding': 'shares_outstanding',
    'beta':             'beta',
    'par_value':        'par_value',

    'pct_hld_entity_1': 'pct_hld_entity_1',
    'pct_hld_entity_2': 'pct_hld_entity_2',
    'pct_hld_entity_3': 'pct_hld_entity_3',
    'pct_hld_entity_aggr': 'pct_hld_entity_aggr',
    'substantial_10_pct': 'substantial_10_pct',
    'substantial':      'substantial_10_pct',

    'cels':             'cels',
    'cels_code':        'cels',
    'pevc_s32_devest':  'pevc_s32_devest',
    's32_representative': 's32_representative',
    'basel_iv_fund':    'basel_iv_fund',
    'mas_643_entity_type': 'mas_643_entity_type',
    'mas_6d_code':      'mas_6d_code',
    'fin_nonfin_ind':   'fin_nonfin_ind',
    'business_unit_head': 'business_unit_head',
    'person_in_charge': 'person_in_charge',
    'core_noncore':     'core_noncore',
    'fund_index_fund':  'fund_index_fund',
    'management_limit_classification': 'management_limit_classification',
    'relative_index':   'relative_index',

    'status':           'status',
    'is_active':        'is_active',
    'created_by':       'created_by',
    'updated_by':       'updated_by',
    'src_id':           'src_id',
    'processing_date':  'processing_date',
}

SECURITY_DECIMAL_COLS = {'price', 'beta', 'par_value'}
SECURITY_BIGINT_COLS  = {'shares_outstanding'}
SECURITY_BOOL_COLS    = {'is_active'}


def load_security(rows: List[Dict], status: str, dry_run: bool, processing_date: str = '') -> Tuple[int, int, List[str]]:
    ok = fail = 0
    errors: List[str] = []

    for i, raw in enumerate(rows, 1):
        mapped: Dict[str, Any] = {}
        for raw_col, raw_val in raw.items():
            db_col = SECURITY_ALIASES.get(raw_col)
            if db_col:
                mapped[db_col] = raw_val

        if not mapped.get('security_name', '').strip():
            msg = f"Row {i}: missing security_name — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

        # PK: unique ms timestamp per row; add small offset to avoid collision
        security_id = _timestamp_ms() + i
        ts = _now()

        mapped['security_id'] = str(security_id)
        mapped['src_system'] = SRC_SYSTEM
        mapped.setdefault('status', status)
        mapped.setdefault('is_active', True)
        mapped.setdefault('created_by', SRC_SYSTEM)
        mapped.setdefault('updated_by', SRC_SYSTEM)
        mapped['created_at'] = str(security_id)   # BIGINT ms, same convention as repo
        mapped['updated_at'] = str(security_id)
        mapped.setdefault('processing_date', processing_date)

        col_names = []
        col_vals = []
        for col, val in mapped.items():
            col_names.append(col)
            if col in SECURITY_DECIMAL_COLS:
                col_vals.append(_decimal(val))
            elif col in SECURITY_BIGINT_COLS:
                col_vals.append(_bigint(val))
            elif col in SECURITY_BOOL_COLS:
                col_vals.append(_bool(val))
            elif col in ('security_id', 'created_at', 'updated_at'):
                col_vals.append(str(val))          # bare integer, no quotes
            else:
                col_vals.append(_escape(val))

        if dry_run:
            logger.info("[DRY-RUN] security row %d: %s", i, mapped.get('security_name'))
            ok += 1
            continue

        sql = f"UPSERT INTO {DATABASE}.cis_security ({', '.join(col_names)}) VALUES ({', '.join(col_vals)})"
        try:
            impala_manager.execute_write(sql, database=DATABASE)
            ok += 1
        except Exception as exc:
            msg = f"Row {i} ({mapped.get('security_name')}): {exc}"
            logger.error(msg)
            errors.append(msg)
            fail += 1

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


def load_trade(rows: List[Dict], status: str, dry_run: bool, processing_date: str = '') -> Tuple[int, int, List[str]]:
    ok = fail = 0
    errors: List[str] = []
    ts = _now()

    for i, raw in enumerate(rows, 1):
        mapped: Dict[str, Any] = {}
        for raw_col, raw_val in raw.items():
            db_col = TRADE_ALIASES.get(raw_col)
            if db_col:
                mapped[db_col] = raw_val

        # trade_id is required — must come from CSV
        raw_id = mapped.get('trade_id', '').strip() if mapped.get('trade_id') else ''
        if not raw_id:
            msg = f"Row {i}: missing trade_id — skipped"
            logger.warning(msg)
            errors.append(msg)
            fail += 1
            continue

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

        # Fixed / derived fields
        mapped['src_system'] = SRC_SYSTEM
        mapped.setdefault('status', status)
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
    'party':     load_party,
    'party_cif': load_party_cif,
    'security':  load_security,
    'trade':     load_trade,
}

# Default status per table (can be overridden with --status)
DEFAULT_STATUS = {
    'party':     'ACTIVE',
    'party_cif': 'ACTIVE',
    'security':  'ACTIVE',
    'trade':     'SETTLED',
}


def main():
    today_yyyymmdd = datetime.now().strftime('%Y%m%d')

    parser = argparse.ArgumentParser(description='CIS migration data loader')
    parser.add_argument('--table',           required=True, choices=list(LOADERS), help='Target table')
    parser.add_argument('--file',            required=True, help='Path to CSV file')
    parser.add_argument('--delimiter',       default=',',   help='CSV delimiter (default: ,)')
    parser.add_argument('--status',          default=None,
                        help='status value to set. Defaults: party/party_cif/security=ACTIVE, trade=SETTLED')
    parser.add_argument('--processing-date', default=today_yyyymmdd,
                        help='processing_date in YYYYMMDD format (default: today). '
                             'CSV column value takes priority if present.')
    parser.add_argument('--dry-run',         action='store_true', help='Parse and validate only, no writes')
    args = parser.parse_args()

    # Validate YYYYMMDD format
    proc_date = args.processing_date
    try:
        datetime.strptime(proc_date, '%Y%m%d')
    except ValueError:
        logger.error("--processing-date must be YYYYMMDD, got: %s", proc_date)
        sys.exit(1)

    if not os.path.isfile(args.file):
        logger.error("File not found: %s", args.file)
        sys.exit(1)

    effective_status = args.status or DEFAULT_STATUS[args.table]
    logger.info("Loading %s from %s (dry_run=%s, status=%s, processing_date=%s)",
                args.table, args.file, args.dry_run, effective_status, proc_date)
    headers, rows = _read_csv(args.file, args.delimiter)
    logger.info("Read %d rows, columns: %s", len(rows), headers)

    loader = LOADERS[args.table]
    ok, fail, errors = loader(rows, effective_status, args.dry_run, proc_date)

    print()
    print("=" * 50)
    print(f"  Table            : {DATABASE}.cis_{args.table}")
    print(f"  File             : {args.file}")
    print(f"  processing_date  : {proc_date}")
    print(f"  Total            : {len(rows)}")
    print(f"  Loaded           : {ok}")
    print(f"  Failed           : {fail}")
    if args.dry_run:
        print("  Mode             : DRY RUN — no data written")
    print("=" * 50)

    if errors:
        err_file = _write_error_csv(args.table, errors)
        if err_file:
            print(f"  Errors  → {err_file}")

    sys.exit(0 if fail == 0 else 1)


if __name__ == '__main__':
    main()
