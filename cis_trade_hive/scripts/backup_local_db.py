#!/usr/bin/env python3
"""
CIS Trade Hive — Full Database Backup

Uses the application's own Impala connection pool (ImpalaConnectionManager)
and Django settings so connection config is read from .env exactly as the app
does — no duplicate host/port/auth arguments needed.

Output layout:
    backups/
        gmp_cis_backup_<YYYYMMDD_HHMMSS>/
            manifest.json
            kudu/
                cis_trade.csv  ...
            hive_internal/
                <table>.csv  ...
            hive_external/
                <table>.csv  ...

Usage (run from project root with venv active):

    # Full backup
    python scripts/backup_local_db.py

    # Dry run — discover + count only, no files
    python scripts/backup_local_db.py --dry-run

    # Custom output dir
    python scripts/backup_local_db.py --output-dir /tmp/cis_backup

    # Single table
    python scripts/backup_local_db.py --table cis_trade

    # Kudu tables only
    python scripts/backup_local_db.py --only-kudu

    # Hive tables only
    python scripts/backup_local_db.py --only-hive

    # Skip heavy tables
    python scripts/backup_local_db.py --skip-tables cis_audit_log,cis_trade_history

    # Bigger fetch batches for faster export
    python scripts/backup_local_db.py --batch-size 10000
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Bootstrap Django so we can use app settings + connection manager
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)          # .../cis_trade_hive/
sys.path.insert(0, _PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

# Now safe to import app modules
from django.conf import settings
from core.repositories.impala_connection import impala_manager

# ---------------------------------------------------------------------------
DATABASE      = getattr(settings, 'IMPALA_CONFIG', {}).get('DATABASE', 'gmp_cis')
TYPE_KUDU     = "KUDU"
TYPE_INTERNAL = "HIVE_INTERNAL"
TYPE_EXTERNAL = "HIVE_EXTERNAL"
TYPE_UNKNOWN  = "UNKNOWN"


# ============================================================================
# TABLE DISCOVERY & CLASSIFICATION
# ============================================================================

def discover_tables(database: str) -> List[Dict]:
    """Return list of {name, type, location} for every table in database."""
    rows = impala_manager.execute_query(f"SHOW TABLES IN {database}")
    table_names = []
    for row in rows:
        if isinstance(row, dict):
            name = row.get('tab_name') or row.get('name') or (list(row.values())[0] if row else '')
        else:
            name = row[0] if row else ''
        name = str(name).strip()
        if name:
            table_names.append(name)

    tables = []
    for name in sorted(table_names):
        ttype, location = _classify(database, name)
        tables.append({"name": name, "type": ttype, "location": location})
    return tables


def _classify(database: str, table: str) -> Tuple[str, str]:
    """Classify table as KUDU / HIVE_INTERNAL / HIVE_EXTERNAL via DESCRIBE FORMATTED."""
    try:
        rows = impala_manager.execute_query(f"DESCRIBE FORMATTED {database}.{table}")
        kv: Dict[str, str] = {}
        for row in rows:
            if isinstance(row, dict):
                k = str(row.get('name') or row.get('col_name') or '').strip()
                v = str(row.get('type') or row.get('data_type') or '').strip()
            else:
                k = str(row[0] or '').strip() if len(row) > 0 else ''
                v = str(row[1] or '').strip() if len(row) > 1 else ''
            if k:
                kv[k] = v

        storage_handler = kv.get("Storage Handler", "").lower()
        table_type_raw  = kv.get("Table Type", "").upper()
        location        = kv.get("Location", "")

        if "kudu" in storage_handler:
            return TYPE_KUDU, location
        elif "external" in table_type_raw:
            return TYPE_EXTERNAL, location
        else:
            return TYPE_INTERNAL, location

    except Exception as exc:
        print(f"    WARNING: DESCRIBE FORMATTED {table} failed: {exc}")
        return TYPE_UNKNOWN, ""


def count_rows(database: str, table: str) -> int:
    rows = impala_manager.execute_query(f"SELECT COUNT(*) AS cnt FROM {database}.{table}")
    if not rows:
        return -1
    row = rows[0]
    if isinstance(row, dict):
        val = row.get('cnt') or row.get('count(*)') or (list(row.values())[0] if row else 0)
    else:
        val = row[0] if row else 0
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return -1


# ============================================================================
# CSV DUMP  (uses get_cursor for streaming to avoid OOM on large tables)
# ============================================================================

def dump_table_to_csv(database: str, table: str, csv_path: str,
                      batch_size: int = 5000) -> Tuple[bool, int, Optional[str]]:
    """
    Dump all rows to CSV using the app's connection pool.
    Streams via fetchmany() so large tables don't exhaust memory.
    Returns (success, row_count, error_message).
    """
    connection = None
    cursor     = None
    try:
        connection = impala_manager.get_connection(database)
        if connection is None:
            return False, 0, "Could not obtain Impala connection from pool"

        cursor = connection.cursor()
        cursor.execute(f"SELECT * FROM {database}.{table}")

        if not cursor.description:
            return False, 0, "No cursor description — query returned nothing"

        col_names = [d[0] for d in cursor.description]

        os.makedirs(os.path.dirname(csv_path), exist_ok=True)

        row_count = 0
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(col_names)

            while True:
                batch = cursor.fetchmany(batch_size)
                if not batch:
                    break
                for row in batch:
                    if isinstance(row, dict):
                        writer.writerow([_safe_val(row.get(c, "")) for c in col_names])
                    else:
                        writer.writerow([_safe_val(v) for v in row])
                    row_count += 1

        return True, row_count, None

    except Exception as exc:
        return False, 0, str(exc)
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if connection:
            impala_manager.return_connection(connection)


def _safe_val(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


# ============================================================================
# MANIFEST
# ============================================================================

def write_manifest(backup_dir: str, results: List[Dict], database: str,
                   timestamp: str, dry_run: bool):
    cfg = getattr(settings, 'IMPALA_CONFIG', {})
    manifest = {
        "backup_timestamp": timestamp,
        "impala_host":      cfg.get('HOST', 'unknown'),
        "impala_port":      cfg.get('PORT', 21050),
        "database":         database,
        "dry_run":          dry_run,
        "tables":           results,
        "created_at":       datetime.now().isoformat(),
    }
    path = os.path.join(backup_dir, "manifest.json")
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    print(f"\n  Manifest → {path}")


# ============================================================================
# MAIN
# ============================================================================

def run_backup(args):
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(args.output_dir, f"gmp_cis_backup_{timestamp}")
    database   = args.database

    cfg = getattr(settings, 'IMPALA_CONFIG', {})

    print("=" * 65)
    print("  CIS Trade Hive — Full Database Backup")
    print("=" * 65)
    print(f"  Impala      : {cfg.get('HOST', '?')}:{cfg.get('PORT', '?')}")
    print(f"  Auth        : {cfg.get('AUTH_MECHANISM', cfg.get('AUTH', '?'))}")
    print(f"  Database    : {database}")
    print(f"  Output dir  : {backup_dir}")
    print(f"  Dry run     : {args.dry_run}")
    print("=" * 65)

    # Verify connection
    print("\n  Testing Impala connection...")
    if not impala_manager.test_connection():
        print("  ERROR: Cannot connect to Impala. Check Docker / .env settings.")
        sys.exit(1)
    print("  Connected OK")

    # Discover tables
    print(f"\n  Discovering tables in {database}...")
    all_tables = discover_tables(database)

    # Apply filters
    skip_set = {t.strip() for t in args.skip_tables.split(",") if t.strip()}

    if args.table:
        all_tables = [t for t in all_tables if t["name"] == args.table]
        if not all_tables:
            print(f"  ERROR: Table '{args.table}' not found in {database}")
            sys.exit(1)
    elif skip_set:
        all_tables = [t for t in all_tables if t["name"] not in skip_set]

    if args.only_kudu:
        all_tables = [t for t in all_tables if t["type"] == TYPE_KUDU]
    elif args.only_hive:
        all_tables = [t for t in all_tables if t["type"] in (TYPE_INTERNAL, TYPE_EXTERNAL)]

    kudu_count     = sum(1 for t in all_tables if t["type"] == TYPE_KUDU)
    internal_count = sum(1 for t in all_tables if t["type"] == TYPE_INTERNAL)
    external_count = sum(1 for t in all_tables if t["type"] == TYPE_EXTERNAL)
    unknown_count  = sum(1 for t in all_tables if t["type"] == TYPE_UNKNOWN)

    print(f"\n  Total : {len(all_tables)} tables  "
          f"({kudu_count} Kudu | {internal_count} Hive internal | "
          f"{external_count} Hive external | {unknown_count} Unknown)")
    if skip_set:
        print(f"  Skipped: {', '.join(sorted(skip_set))}")

    if args.dry_run:
        print("\n  DRY RUN — counting rows only, no files written\n")

    type_dirs = {
        TYPE_KUDU:     os.path.join(backup_dir, "kudu"),
        TYPE_INTERNAL: os.path.join(backup_dir, "hive_internal"),
        TYPE_EXTERNAL: os.path.join(backup_dir, "hive_external"),
        TYPE_UNKNOWN:  os.path.join(backup_dir, "unknown"),
    }

    results    = []
    total_rows = 0
    succeeded  = 0
    failed     = 0

    print(f"\n  {'Table':<50} {'Type':<15} {'Rows':>8}  Status")
    print(f"  {'-'*50} {'-'*15} {'-'*8}  ------")

    for tbl in all_tables:
        name  = tbl["name"]
        ttype = tbl["type"]
        start = datetime.now()

        result = {
            "table":        name,
            "type":         ttype,
            "status":       "PENDING",
            "row_count":    0,
            "csv_path":     "",
            "error":        None,
            "duration_sec": 0,
        }

        row_count = count_rows(database, name)
        result["row_count"] = row_count

        if args.dry_run:
            result["status"] = "DRY_RUN"
            print(f"  {name:<50} {ttype:<15} {max(row_count, 0):>8,}  DRY_RUN")
            results.append(result)
            total_rows += max(row_count, 0)
            continue

        csv_path = os.path.join(type_dirs[ttype], f"{name}.csv")
        result["csv_path"] = csv_path

        ok, dumped_rows, err = dump_table_to_csv(database, name, csv_path, args.batch_size)
        duration = round((datetime.now() - start).total_seconds(), 1)
        result["duration_sec"] = duration

        if ok:
            result["status"] = "SUCCESS"
            total_rows += dumped_rows
            succeeded  += 1
            print(f"  {name:<50} {ttype:<15} {dumped_rows:>8,}  OK  ({duration}s)")
        else:
            result["status"] = "FAILED"
            result["error"]  = err
            failed += 1
            print(f"  {name:<50} {ttype:<15} {'ERR':>8}  FAILED: {err}")

        results.append(result)

    # Manifest
    if not args.dry_run:
        os.makedirs(backup_dir, exist_ok=True)
        write_manifest(backup_dir, results, database, timestamp, args.dry_run)

    # Summary
    print("\n" + "=" * 65)
    print("  BACKUP SUMMARY")
    print("=" * 65)
    if args.dry_run:
        print(f"  Mode         : DRY RUN — no files written")
    else:
        print(f"  Backup dir   : {backup_dir}")
    print(f"  Tables total : {len(all_tables)}")
    if not args.dry_run:
        print(f"  Succeeded    : {succeeded}")
        print(f"  Failed       : {failed}")
    print(f"  Total rows   : {total_rows:,}")

    if not args.dry_run and succeeded > 0:
        try:
            size_bytes = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fnames in os.walk(backup_dir)
                for f in fnames
            )
            print(f"  Backup size  : {size_bytes / (1024*1024):.1f} MB")
        except Exception:
            pass

    if failed > 0:
        print(f"\n  FAILED TABLES:")
        for r in results:
            if r["status"] == "FAILED":
                print(f"    - {r['table']}: {r['error']}")

    if not args.dry_run and succeeded > 0:
        print(f"\n  CSV files written to:")
        for ttype, label in [
            (TYPE_KUDU,     "Kudu"),
            (TYPE_INTERNAL, "Hive internal"),
            (TYPE_EXTERNAL, "Hive external"),
        ]:
            files = [r for r in results if r["type"] == ttype and r["status"] == "SUCCESS"]
            if files:
                print(f"    {label:<16}: {type_dirs[ttype]}/")

    print("=" * 65)
    return 1 if failed > 0 else 0


# ============================================================================
# CLI
# ============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="Full database backup using the app's Impala connection — Kudu + Hive → CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/backup_local_db.py                          # full backup
  python scripts/backup_local_db.py --dry-run                # discover + count only
  python scripts/backup_local_db.py --only-kudu              # Kudu tables only
  python scripts/backup_local_db.py --only-hive              # Hive tables only
  python scripts/backup_local_db.py --table cis_trade        # single table
  python scripts/backup_local_db.py --skip-tables cis_audit_log,cis_trade_history
  python scripts/backup_local_db.py --output-dir /tmp/backup
""",
    )
    p.add_argument("--database",    default=DATABASE,
                   help=f"Database name (default: {DATABASE})")
    p.add_argument("--output-dir",  default="backups",
                   help="Output directory (default: ./backups)")
    p.add_argument("--table",       default="",
                   help="Back up a single table only")
    p.add_argument("--skip-tables", default="",
                   help="Comma-separated table names to skip")
    p.add_argument("--only-kudu",   action="store_true",
                   help="Back up Kudu tables only")
    p.add_argument("--only-hive",   action="store_true",
                   help="Back up Hive tables only (internal + external)")
    p.add_argument("--dry-run",     action="store_true",
                   help="Discover + count rows only — no CSV files written")
    p.add_argument("--batch-size",  type=int, default=5000,
                   help="Rows per fetch batch (default: 5000)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(run_backup(args))
