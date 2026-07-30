"""
Upload Equity Price from CSV — src_system='CIS'
================================================
Loads daily closing prices from a CSV into gmp_cis.cis_equity_price (Kudu).

Logic:
  1. GMP guard  — if cis_equity_price already has src_system='GMP' rows for
                  any price_date in the CSV, abort (GMP is authoritative).
                  Use --force-gmp-override to bypass.
  2. Existence  — for each row, check if (security_label, price_date) already
                  exists in cis_equity_price.  If yes → skip.
  3. Insert     — insert new rows as src_system='CIS'.

security_label comes directly from the CSV column 'Security label' (or alias).
No lookup against cis_security is performed.

Expected CSV columns (header row required, order-independent):
  Required:
    security_label      (also: security label, security_name, security name,
                         name, security, sec_name)
    price_date          YYYY-MM-DD  (also: price date, date, trade_date,
                                    nav_date, valuation_date)
    closing_price       (also: closing price, price, close, close_price,
                         main_closing_price, nav, unit_price, last_price)
  Optional:
    isin                stored as-is if present
    currency_code       (also: currency, ccy)

Example CSV:
  Security label,Price Date,Closing Price,ISIN,Currency
  ZIMI LTD,2026-05-23,1.25,AU000000ZIM7,AUD
  DBS GROUP,2026-05-23,37.20,,SGD

CLI usage:
  python upload_equity_price_csv.py --file prices.csv
  python upload_equity_price_csv.py --file prices.csv --price-date 2026-05-23
  python upload_equity_price_csv.py --file prices.csv --dry-run
  python upload_equity_price_csv.py --file prices.csv --overwrite
  python upload_equity_price_csv.py --file prices.csv --force-gmp-override

Options:
  --file                Path to CSV file (required)
  --price-date          Override price_date for all rows (YYYY-MM-DD)
  --overwrite           Insert even if (security_label, price_date) already exists
  --dry-run             Validate without writing to the database
  --batch-size          Rows per UPSERT statement (default: 500)
  --force-gmp-override  Bypass the GMP guard (authorised use only)

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
from typing import Dict, List, Optional

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
DB        = os.environ.get('IMPALA_DB', 'gmp_cis')
PRICE_TBL = f'{DB}.cis_equity_price'
SRC_SYSTEM = 'CIS'

# Accepted column name aliases — normalised to lowercase, spaces→underscores
_COL_ALIASES = {
    'security_label': {'security_label', 'security label', 'security_name',
                       'security name', 'name', 'security', 'sec_name', 'secname',
                       'security_short_name', 'security short name'},
    'price_date':     {'price_date', 'price date', 'date', 'pricedate',
                       'trade_date', 'trade date', 'nav_date', 'nav date',
                       'valuation_date', 'valuation date'},
    'price':          {'price', 'closing_price', 'closing price', 'closingprice',
                       'close_price', 'close price', 'closeprice',
                       'main_closing_price', 'main closing price',
                       'close', 'last_price', 'last price', 'nav',
                       'unit_price', 'unit price'},
    'isin':           {'isin', 'isin_code', 'isin code', 'isincode'},
    'currency_code':  {'currency_code', 'currency code', 'currency', 'ccy', 'curr'},
}


def _esc(val: str) -> str:
    """Impala C-style string escape."""
    if val is None:
        return "''"
    return "'" + str(val).replace('\\', '\\\\').replace("'", "\\'") + "'"


def _clean_price(raw: str) -> Optional[Decimal]:
    if not raw or not str(raw).strip():
        return None
    cleaned = re.sub(r'[,$£€¥%\s]', '', str(raw))
    cleaned = re.sub(r'^\(([0-9.]+)\)$', r'-\1', cleaned)
    try:
        d = Decimal(cleaned)
        if d <= 0:
            return None
        return d
    except InvalidOperation:
        return None


def _normalise_date(raw: str) -> Optional[str]:
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
    """Map canonical column names to CSV column indices (case/space insensitive)."""
    mapping = {}
    for idx, h in enumerate(headers):
        h_norm = h.strip().lower()
        h_ul   = h_norm.replace(' ', '_')
        for canonical, aliases in _COL_ALIASES.items():
            if canonical in mapping:
                continue
            if h_norm in aliases or h_ul in aliases:
                mapping[canonical] = idx
    return mapping


# ---------------------------------------------------------------------------
# GMP guard
# ---------------------------------------------------------------------------

def check_gmp_conflict(price_dates: set) -> List[str]:
    """Return price_dates that already have src_system='GMP' in cis_equity_price."""
    if not price_dates:
        return []
    date_list = ', '.join(f"'{d}'" for d in sorted(price_dates))
    rows = impala_manager.execute_query(
        f"""
        SELECT DISTINCT price_date
        FROM {PRICE_TBL}
        WHERE src_system = 'GMP'
          AND price_date IN ({date_list})
        """,
        database=DB,
    )
    return [(r.get('price_date') or '').strip() for r in (rows or []) if r.get('price_date')]


# ---------------------------------------------------------------------------
# Existence check — fetch (security_label, price_date) already in cis_equity_price
# ---------------------------------------------------------------------------

def load_existing_keys(price_dates: Optional[set] = None) -> set:
    """
    Return set of (security_label, price_date) tuples already in cis_equity_price.
    Scoped to the given price_dates for efficiency.
    """
    where = 'WHERE 1=1'
    if price_dates:
        if len(price_dates) == 1:
            where += f" AND price_date = '{next(iter(price_dates))}'"
        else:
            date_list = ', '.join(f"'{d}'" for d in sorted(price_dates))
            where += f" AND price_date IN ({date_list})"
    rows = impala_manager.execute_query(
        f"SELECT security_label, price_date FROM {PRICE_TBL} {where}",
        database=DB,
    )
    keys = set()
    for r in (rows or []):
        keys.add((
            (r.get('security_label') or '').strip(),
            (r.get('price_date') or '').strip(),
        ))
    logger.info(f"Loaded {len(keys)} existing (security_label, price_date) keys from cis_equity_price")
    return keys


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def parse_csv(filepath: str, override_date: Optional[str]) -> List[dict]:
    rows = []
    with open(filepath, newline='', encoding='utf-8-sig') as fh:
        reader = csv.reader(fh)
        headers = next(reader)
        col_map = _map_headers(headers)

        if 'security_label' not in col_map:
            raise ValueError(
                f"CSV missing required security_label column. "
                f"Accepted names: security_label, security label, security_name, name, security. "
                f"Found columns: {[h.strip() for h in headers]}"
            )
        if 'price' not in col_map:
            raise ValueError(
                f"CSV missing required price column. "
                f"Accepted names: closing_price, closing price, price, close, nav, unit_price. "
                f"Found columns: {[h.strip() for h in headers]}"
            )
        if 'price_date' not in col_map and not override_date:
            raise ValueError(
                "CSV missing 'price_date' column and --price-date not provided."
            )

        mapped_display = {c: headers[i].strip() for c, i in col_map.items()}
        logger.info(f"Column mapping: {mapped_display}")

        for lineno, row in enumerate(reader, start=2):
            if not any(c.strip() for c in row):
                continue

            def get(col):
                idx = col_map.get(col)
                return row[idx].strip() if idx is not None and idx < len(row) else ''

            rows.append({
                'lineno':         lineno,
                'security_label': get('security_label'),
                'price_date':     override_date or get('price_date'),
                'price':          get('price'),
                'isin':           get('isin'),
                'currency_code':  get('currency_code'),
            })

    logger.info(f"Parsed {len(rows)} data rows from {filepath}")
    return rows


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_rows(
    raw_rows: List[dict],
    existing_keys: set,
    overwrite: bool,
    dry_run: bool,
    batch_size: int,
) -> dict:
    now_ts  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    summary = {'total': len(raw_rows), 'upsert': 0, 'skip': 0, 'invalid': 0, 'errors': []}

    upsert_batch: List[dict] = []

    def flush_batch():
        if not upsert_batch:
            return
        _upsert_batch(upsert_batch, dry_run)
        summary['upsert'] += len(upsert_batch)
        upsert_batch.clear()

    for r in raw_rows:
        lineno = r['lineno']

        # Validate security_label
        security_label = r['security_label'].strip()
        if not security_label:
            msg = f"Line {lineno}: empty security_label — skipped"
            logger.warning(msg)
            summary['errors'].append(msg)
            summary['invalid'] += 1
            continue

        # Validate price
        price = _clean_price(r['price'])
        if price is None:
            msg = f"Line {lineno}: invalid/zero price '{r['price']}' for '{security_label}' — skipped"
            logger.warning(msg)
            summary['errors'].append(msg)
            summary['invalid'] += 1
            continue

        # Validate date
        price_date = _normalise_date(r['price_date'])
        if not price_date:
            msg = f"Line {lineno}: invalid date '{r['price_date']}' for '{security_label}' — skipped"
            logger.warning(msg)
            summary['errors'].append(msg)
            summary['invalid'] += 1
            continue

        # Existence check — (security_label, price_date) already in cis_equity_price?
        key = (security_label, price_date)
        if key in existing_keys and not overwrite:
            logger.debug(f"Line {lineno}: already exists ({security_label}, {price_date}) — skipped")
            summary['skip'] += 1
            continue

        upsert_batch.append({
            'security_label': security_label,
            'price_date':     price_date,
            'isin':           r['isin'],
            'currency_code':  r['currency_code'],
            'price':          str(price),
            'now_ts':         now_ts,
        })

        if len(upsert_batch) >= batch_size:
            flush_batch()

    flush_batch()
    return summary


def _upsert_batch(batch: List[dict], dry_run: bool):
    value_rows = []
    for b in batch:
        isin_sql     = _esc(b['isin']) if b['isin'] else 'NULL'
        ccy_sql      = _esc(b['currency_code']) if b['currency_code'] else 'NULL'
        value_rows.append(
            f"({_esc(b['security_label'])}, {_esc(b['price_date'])}, "
            f"{isin_sql}, {ccy_sql}, "
            f"{b['price']}, "
            f"'{b['now_ts']}', '{SRC_SYSTEM}', true, "
            f"'CSV_UPLOAD', '{b['now_ts']}', NULL, NULL)"
        )

    sql = (
        f"UPSERT INTO {PRICE_TBL} "
        f"(security_label, price_date, isin, currency_code, "
        f"main_closing_price, price_timestamp, src_system, is_active, "
        f"created_by, created_at, updated_by, updated_at) VALUES "
        + ',\n'.join(value_rows)
    )

    if dry_run:
        logger.info(f"[DRY RUN] Would UPSERT {len(batch)} rows")
        logger.debug(f"[DRY RUN] SQL:\n{sql[:500]}")
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
    p.add_argument('--file',       required=True, help='Path to CSV file')
    p.add_argument('--price-date', default=None,  help='Override price_date for all rows (YYYY-MM-DD)')
    p.add_argument('--overwrite',  action='store_true',
                   help='Insert even if (security_label, price_date) already exists')
    p.add_argument('--dry-run',    action='store_true',
                   help='Validate without writing to the database')
    p.add_argument('--batch-size', type=int, default=500,
                   help='Rows per UPSERT statement (default: 500)')
    p.add_argument('--force-gmp-override', action='store_true',
                   help='Bypass the GMP guard (authorised use only)')
    p.add_argument('--debug',      action='store_true',
                   help='Enable DEBUG logging for per-row detail')
    return p.parse_args()


def main():
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

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
    print(f'  file              : {args.file}')
    print(f'  price_date        : {override_date or "(from CSV)"}')
    print(f'  overwrite         : {args.overwrite}')
    print(f'  dry_run           : {args.dry_run}')
    print(f'  batch_size        : {args.batch_size}')
    print(f'  force_gmp_override: {args.force_gmp_override}')
    print(f'  started           : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
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

    # 2. Collect all price_dates from the file
    dates_in_file = {
        _normalise_date(r['price_date'])
        for r in raw_rows if r['price_date']
    } - {None}

    # 3. GMP guard
    if not args.force_gmp_override:
        gmp_conflicts = check_gmp_conflict(dates_in_file)
        if gmp_conflicts:
            conflict_str = ', '.join(sorted(gmp_conflicts))
            print(
                f"\nERROR: GMP prices already exist in cis_equity_price for: {conflict_str}\n"
                f"       CIS manual upload is blocked to protect GMP data.\n"
                f"       Use --force-gmp-override to bypass (authorised use only)."
            )
            logger.error(f"GMP conflict for dates: {conflict_str} — upload aborted")
            sys.exit(1)

    # 4. Load existing (security_label, price_date) keys
    existing_keys = load_existing_keys(price_dates=dates_in_file if dates_in_file else None)

    # 5. Process rows
    summary = process_rows(
        raw_rows=raw_rows,
        existing_keys=existing_keys,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )

    # 6. Report
    print('\n' + '=' * 70)
    print('  RESULTS')
    print('=' * 70)
    print(f"  Total rows  : {summary['total']}")
    print(f"  Inserted    : {summary['upsert']}{' (dry-run — not written)' if args.dry_run else ''}")
    print(f"  Skipped     : {summary['skip']}  (already in cis_equity_price)")
    print(f"  Invalid     : {summary['invalid']}  (bad price/date/security_label)")
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
