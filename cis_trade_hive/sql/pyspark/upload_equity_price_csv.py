"""
Upload Equity Price from CSV — src_system='CIS'
================================================
Standalone backend script that loads daily closing prices from a CSV file
into gmp_cis.cis_equity_price (Kudu), skipping rows that already exist.

Existence check (idempotent):
  A row is skipped when (currency_code, security_label, price_date) already
  exists in cis_equity_price with is_active = true.  This makes the script
  safe to re-run; only genuinely new prices are written.

Security resolution (to find security_label and currency_code):
  1. ISIN match   — cis_security.isin = csv.isin
  2. Name match   — cis_security.security_name = csv.security_name
  3. Desc match   — cis_security.security_description = csv.security_name
  If no match the row is flagged SKIP: Security not found in cis_security.

Expected CSV columns (header row required, order-independent):
  Required:
    price_date          YYYY-MM-DD  (also accepted: date, trade_date, nav_date)
    closing_price       closing price — also accepted: closing price, price,
                        close, close_price, main_closing_price, nav, unit_price
  At least one security identifier:
    isin                ISIN code          (preferred)
    security_name       Security name      (fallback)
  Optional (overrides resolved value from cis_security):
    currency_code       e.g. SGD, USD  (also: currency, ccy)

Example CSV:
  isin,security_name,price_date,closing_price,currency_code
  US0378331005,Apple Inc.,2026-05-23,189.50,USD
  ,DBS Group Holdings,2026-05-23,37.20,SGD

CLI usage:
  python upload_equity_price_csv.py --file prices_20260523.csv
  python upload_equity_price_csv.py --file prices.csv --price-date 2026-05-23
  python upload_equity_price_csv.py --file prices.csv --dry-run
  python upload_equity_price_csv.py --file prices.csv --overwrite

Options:
  --file            Path to the CSV file (required)
  --price-date      Override price_date for all rows (YYYY-MM-DD)
  --overwrite       UPSERT even if record already exists (update price)
  --dry-run         Show what would be written; no DB writes
  --batch-size      Rows per UPSERT batch (default: 100)

Author: CisTrade Team
"""

import argparse
import csv
import logging
import os
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Bootstrap Django so we can use impala_manager
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

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
logger = logging.getLogger('upload_equity_price_csv')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DB         = 'gmp_cis'
PRICE_TBL  = f'{DB}.cis_equity_price'
SEC_TBL    = f'{DB}.cis_security'
SRC_SYSTEM = 'CIS'

# Accepted column name aliases (lower-stripped, spaces/underscores normalised)
_COL_ALIASES = {
    'isin':           {'isin', 'isin_code', 'isin code', 'isincode'},
    'security_name':  {'security_name', 'security name', 'name', 'security',
                       'sec_name', 'secname', 'description', 'security_label',
                       'security label'},
    'price_date':     {'price_date', 'price date', 'date', 'pricedate',
                       'trade_date', 'trade date', 'nav_date', 'nav date',
                       'valuation_date', 'valuation date'},
    'price':          {'price', 'closing_price', 'closing price', 'closingprice',
                       'close_price', 'close price', 'closeprice',
                       'main_closing_price', 'main closing price',
                       'close', 'last_price', 'last price', 'nav',
                       'unit_price', 'unit price'},
    'currency_code':  {'currency_code', 'currency code', 'currency', 'ccy', 'curr'},
}


def _esc(val: str) -> str:
    """Impala C-style string escape."""
    if val is None:
        return "''"
    return "'" + str(val).replace('\\', '\\\\').replace("'", "\\'") + "'"


def _clean_price(raw: str) -> Optional[Decimal]:
    """Parse a raw price string; return Decimal or None on failure."""
    if not raw or not str(raw).strip():
        return None
    cleaned = re.sub(r'[,$£€¥%\s]', '', str(raw))
    # Handle parenthetical negatives: (1234.56) → -1234.56
    cleaned = re.sub(r'^\(([0-9.]+)\)$', r'-\1', cleaned)
    try:
        d = Decimal(cleaned)
        if d <= 0:
            return None
        return d
    except InvalidOperation:
        return None


def _normalise_date(raw: str) -> Optional[str]:
    """Return YYYY-MM-DD or None."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y%m%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _map_headers(headers: List[str]) -> Dict[str, int]:
    """Map canonical column names to CSV column indices.

    Normalises each header to lowercase with leading/trailing spaces stripped.
    Checks both the raw normalised form and an underscore-collapsed form so that
    'Closing Price', 'closing_price', and 'closing price' all match.
    """
    mapping = {}
    for idx, h in enumerate(headers):
        h_norm = h.strip().lower()
        h_ul   = h_norm.replace(' ', '_')   # 'closing price' → 'closing_price'
        for canonical, aliases in _COL_ALIASES.items():
            if canonical in mapping:
                continue
            if h_norm in aliases or h_ul in aliases:
                mapping[canonical] = idx
    return mapping


# ---------------------------------------------------------------------------
# Security resolution — bulk fetch into an in-memory dict
# ---------------------------------------------------------------------------

def load_security_map() -> Dict[str, dict]:
    """
    Fetch all active securities from cis_security.
    Returns dict keyed by ISIN (upper) and by security_name (lower).
    Value: {'security_name': ..., 'currency_code': ..., 'isin': ...}
    """
    logger.info("Loading security master from cis_security …")
    rows = impala_manager.execute_query(
        f"""
        SELECT security_name, isin, currency_code, security_description
        FROM {SEC_TBL}
        WHERE is_active = true
        """,
        database=DB
    )
    by_isin = {}
    by_name = {}
    by_desc = {}
    for r in (rows or []):
        entry = {
            'security_name': r.get('security_name', ''),
            'currency_code': r.get('currency_code', ''),
            'isin':          r.get('isin', '') or '',
        }
        isin = (r.get('isin') or '').strip().upper()
        name = (r.get('security_name') or '').strip().lower()
        desc = (r.get('security_description') or '').strip().lower()
        if isin:
            by_isin[isin] = entry
        if name:
            by_name.setdefault(name, entry)
        if desc:
            by_desc.setdefault(desc, entry)
    logger.info(f"Loaded {len(by_isin)} securities by ISIN, {len(by_name)} by name")
    return {'isin': by_isin, 'name': by_name, 'desc': by_desc}


def resolve_security(csv_isin: str, csv_name: str, sec_map: dict) -> Optional[dict]:
    """Return matched security dict or None."""
    if csv_isin:
        hit = sec_map['isin'].get(csv_isin.strip().upper())
        if hit:
            return hit
    if csv_name:
        hit = sec_map['name'].get(csv_name.strip().lower())
        if hit:
            return hit
        # Try description match
        hit = sec_map['desc'].get(csv_name.strip().lower())
        if hit:
            return hit
    return None


# ---------------------------------------------------------------------------
# Existence check — bulk fetch existing (currency_code, security_label, price_date)
# ---------------------------------------------------------------------------

def load_existing_keys(price_date: Optional[str] = None) -> set:
    """
    Return set of (currency_code, security_label, price_date) tuples already
    in cis_equity_price (is_active=true).  If price_date is given, only fetch
    that date's rows (faster for daily runs).
    """
    where = "WHERE (is_active = true OR is_active IS NULL)"
    if price_date:
        where += f" AND price_date = '{price_date}'"
    rows = impala_manager.execute_query(
        f"SELECT currency_code, security_label, price_date FROM {PRICE_TBL} {where}",
        database=DB
    )
    keys = set()
    for r in (rows or []):
        keys.add((
            (r.get('currency_code') or '').strip(),
            (r.get('security_label') or '').strip(),
            (r.get('price_date') or '').strip(),
        ))
    logger.info(f"Loaded {len(keys)} existing price keys from cis_equity_price")
    return keys


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def parse_csv(filepath: str, override_date: Optional[str]) -> List[dict]:
    """
    Read CSV and return list of raw row dicts with canonical keys:
      isin, security_name, price_date, price, currency_code
    """
    rows = []
    with open(filepath, newline='', encoding='utf-8-sig') as fh:
        reader = csv.reader(fh)
        headers = next(reader)
        col_map = _map_headers(headers)

        if 'price' not in col_map:
            raise ValueError(
                f"CSV missing required price column. Accepted names: "
                f"closing_price, closing price, price, close, close_price, "
                f"main_closing_price, nav, unit_price, last_price. "
                f"Found columns: {[h.strip() for h in headers]}"
            )
        if 'price_date' not in col_map and not override_date:
            raise ValueError(
                "CSV missing 'price_date' column and --price-date not provided."
            )
        if 'isin' not in col_map and 'security_name' not in col_map:
            raise ValueError(
                "CSV must have at least one of: isin, security_name / security_label. "
                f"Found columns: {[h.strip() for h in headers]}"
            )

        # Show which columns were recognised — helps debug mapping issues
        mapped_display = {c: headers[i].strip() for c, i in col_map.items()}
        logger.info(f"Column mapping: {mapped_display}")
        if 'currency_code' not in col_map:
            logger.info("No currency_code column — will use cis_security.currency_code for each row")

        for lineno, row in enumerate(reader, start=2):
            if not any(c.strip() for c in row):
                continue  # skip blank lines

            def get(col):
                idx = col_map.get(col)
                return row[idx].strip() if idx is not None and idx < len(row) else ''

            rows.append({
                'lineno':        lineno,
                'isin':          get('isin'),
                'security_name': get('security_name'),
                'price_date':    override_date or get('price_date'),
                'price':         get('price'),
                'currency_code': get('currency_code'),
            })

    logger.info(f"Parsed {len(rows)} data rows from {filepath}")
    return rows


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_rows(
    raw_rows: List[dict],
    sec_map: dict,
    existing_keys: set,
    overwrite: bool,
    dry_run: bool,
    batch_size: int,
) -> dict:
    now_ts  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    summary = {
        'total':   len(raw_rows),
        'upsert':  0,
        'skip':    0,
        'invalid': 0,
        'errors':  [],
    }

    upsert_batch: List[dict] = []

    def flush_batch():
        if not upsert_batch:
            return
        _upsert_batch(upsert_batch, dry_run)
        summary['upsert'] += len(upsert_batch)
        upsert_batch.clear()

    for r in raw_rows:
        lineno = r['lineno']

        # --- Validate price ---
        price = _clean_price(r['price'])
        if price is None:
            msg = f"Line {lineno}: invalid/zero price '{r['price']}' — skipped"
            logger.warning(msg)
            summary['errors'].append(msg)
            summary['invalid'] += 1
            continue

        # --- Validate date ---
        price_date = _normalise_date(r['price_date'])
        if not price_date:
            msg = f"Line {lineno}: invalid date '{r['price_date']}' — skipped"
            logger.warning(msg)
            summary['errors'].append(msg)
            summary['invalid'] += 1
            continue

        # --- Resolve security ---
        sec = resolve_security(r['isin'], r['security_name'], sec_map)
        if sec is None:
            msg = (
                f"Line {lineno}: security not found in cis_security "
                f"(isin='{r['isin']}', name='{r['security_name']}') — skipped"
            )
            logger.warning(msg)
            summary['errors'].append(msg)
            summary['invalid'] += 1
            continue

        security_label = sec['security_name']
        # CSV currency_code overrides resolved value if provided
        currency_code = r['currency_code'] or sec['currency_code']
        if not currency_code:
            msg = (
                f"Line {lineno}: no currency_code for '{security_label}' "
                f"and cis_security has none either — skipped"
            )
            logger.warning(msg)
            summary['errors'].append(msg)
            summary['invalid'] += 1
            continue

        isin = r['isin'] or sec['isin']

        # --- Existence check ---
        key = (currency_code.strip(), security_label.strip(), price_date.strip())
        if key in existing_keys and not overwrite:
            logger.debug(f"Line {lineno}: already exists {key} — skipped")
            summary['skip'] += 1
            continue

        upsert_batch.append({
            'currency_code':     currency_code,
            'security_label':    security_label,
            'price_date':        price_date,
            'isin':              isin,
            'main_closing_price': str(price),
            'now_ts':            now_ts,
        })

        if len(upsert_batch) >= batch_size:
            flush_batch()

    flush_batch()
    return summary


def _upsert_batch(batch: List[dict], dry_run: bool):
    """Build and execute a multi-row UPSERT for the given batch."""
    value_rows = []
    for b in batch:
        isin_sql = _esc(b['isin']) if b['isin'] else 'NULL'
        value_rows.append(
            f"({_esc(b['currency_code'])}, {_esc(b['security_label'])}, "
            f"{_esc(b['price_date'])}, {isin_sql}, "
            f"{b['main_closing_price']}, "
            f"'{b['now_ts']}', '{SRC_SYSTEM}', true, "
            f"'CSV_UPLOAD', '{b['now_ts']}', NULL, NULL)"
        )

    sql = (
        f"UPSERT INTO {PRICE_TBL} "
        f"(currency_code, security_label, price_date, isin, "
        f"main_closing_price, price_timestamp, src_system, is_active, "
        f"created_by, created_at, updated_by, updated_at) VALUES "
        + ',\n'.join(value_rows)
    )

    if dry_run:
        logger.info(f"[DRY RUN] Would UPSERT {len(batch)} rows")
        return

    ok = impala_manager.execute_write(sql, database=DB)
    if ok:
        logger.info(f"UPSERTed {len(batch)} rows into {PRICE_TBL}")
    else:
        logger.error(f"UPSERT failed for batch of {len(batch)} rows")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description='Upload equity prices from CSV into cis_equity_price (src_system=CIS)'
    )
    p.add_argument('--file',        required=True,  help='Path to CSV file')
    p.add_argument('--price-date',  default=None,   help='Override price_date for all rows (YYYY-MM-DD)')
    p.add_argument('--overwrite',   action='store_true',
                   help='UPSERT even if (currency_code, security_label, price_date) already exists')
    p.add_argument('--dry-run',     action='store_true',
                   help='Parse and validate without writing to the database')
    p.add_argument('--batch-size',  type=int, default=500,
                   help='Rows per UPSERT statement (default: 500). '
                        'All rows in the file are always processed — this only '
                        'controls how many are grouped into each SQL statement.')
    return p.parse_args()


def main():
    args = parse_args()

    if not os.path.isfile(args.file):
        print(f"ERROR: file not found: {args.file}")
        sys.exit(1)

    override_date = None
    if args.price_date:
        override_date = _normalise_date(args.price_date)
        if not override_date:
            print(f"ERROR: invalid --price-date '{args.price_date}' — expected YYYY-MM-DD")
            sys.exit(1)

    print('\n' + '=' * 70)
    print('  CIS Trade Hive — Equity Price CSV Upload')
    print('=' * 70)
    print(f'  file        : {args.file}')
    print(f'  price_date  : {override_date or "(from CSV)"}')
    print(f'  overwrite   : {args.overwrite}')
    print(f'  dry_run     : {args.dry_run}')
    print(f'  batch_size  : {args.batch_size}')
    print(f'  started     : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 70)

    # 1. Parse CSV
    try:
        raw_rows = parse_csv(args.file, override_date)
    except (ValueError, OSError) as exc:
        print(f"ERROR reading CSV: {exc}")
        sys.exit(1)

    if not raw_rows:
        print("No data rows found in CSV — nothing to do.")
        sys.exit(0)

    # 2. Load security master
    sec_map = load_security_map()

    # 3. Load existing price keys (scoped to date if all rows share one date)
    dates_in_file = {r['price_date'] for r in raw_rows if r['price_date']}
    lookup_date = list(dates_in_file)[0] if len(dates_in_file) == 1 else None
    existing_keys = load_existing_keys(
        price_date=_normalise_date(lookup_date) if lookup_date else None
    )

    # 4. Process
    summary = process_rows(
        raw_rows=raw_rows,
        sec_map=sec_map,
        existing_keys=existing_keys,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )

    # 5. Report
    print('\n' + '=' * 70)
    print('  RESULTS')
    print('=' * 70)
    print(f"  Total rows  : {summary['total']}")
    print(f"  Upserted    : {summary['upsert']}{' (dry-run — not written)' if args.dry_run else ''}")
    print(f"  Skipped     : {summary['skip']}  (already exist in cis_equity_price)")
    print(f"  Invalid     : {summary['invalid']}  (bad price/date/security)")
    if summary['errors']:
        print(f"\n  Issues ({len(summary['errors'])}):")
        for e in summary['errors'][:20]:
            print(f"    • {e}")
        if len(summary['errors']) > 20:
            print(f"    … and {len(summary['errors']) - 20} more")
    print(f"\n  finished    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print('=' * 70)

    if summary['invalid'] > 0 and summary['upsert'] == 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
