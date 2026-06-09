#!/usr/bin/env python3
"""
Local Database Full Backup — Kudu + Hive (internal & external)

Connects to the local Docker Impala/Kudu instance, discovers ALL tables in
gmp_cis, classifies each as KUDU / HIVE_INTERNAL / HIVE_EXTERNAL, and dumps
every table to CSV (one file per table).

No Spark, no HDFS, no Beeline required — pure PyHive / impyla over NOSASL.

Output layout:
    <output_dir>/
        gmp_cis_backup_<YYYYMMDD_HHMMSS>/
            manifest.json                 ← table list, row counts, status
            kudu/
                cis_trade.csv
                cis_portfolio.csv
                ...
            hive_internal/
                <table>.csv
                ...
            hive_external/
                <table>.csv
                ...

Usage:
    # Full backup (default: ./backups/)
    python scripts/backup_local_db.py

    # Custom host/port/output
    python scripts/backup_local_db.py \\
        --impala-host localhost --impala-port 21050 \\
        --database gmp_cis \\
        --output-dir /tmp/my_backup

    # Dry run — discover + count only, no CSV files written
    python scripts/backup_local_db.py --dry-run

    # Skip specific tables
    python scripts/backup_local_db.py --skip-tables cis_audit_log,logs

    # Single table only
    python scripts/backup_local_db.py --table cis_trade

    # Kudu tables only
    python scripts/backup_local_db.py --only-kudu

    # Hive tables only (internal + external)
    python scripts/backup_local_db.py --only-hive

Author: CIS Trade Hive Team
Version: 1.0
Date: 2026-06-09
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Impala connection (impyla preferred; falls back to PyHive)
# ---------------------------------------------------------------------------
try:
    from impala.dbapi import connect as _impyla_connect
    _BACKEND = "impyla"
except ImportError:
    try:
        from pyhive import hive as _pyhive
        _BACKEND = "pyhive"
    except ImportError:
        print("ERROR: Neither impyla nor pyhive is installed.")
        print("  pip install impyla   OR   pip install pyhive thrift thrift-sasl")
        sys.exit(1)

DATABASE   = "gmp_cis"
TYPE_KUDU     = "KUDU"
TYPE_INTERNAL = "HIVE_INTERNAL"
TYPE_EXTERNAL = "HIVE_EXTERNAL"
TYPE_UNKNOWN  = "UNKNOWN"


# ============================================================================
# CONNECTION
# ============================================================================

def _connect(host: str, port: int, database: str, auth: str = "NOSASL",
             username: str = "", password: str = ""):
    """Open a raw DB-API connection to Impala."""
    if _BACKEND == "impyla":
        kwargs = dict(host=host, port=port, database=database, auth_mechanism=auth)
        if username:
            kwargs["user"] = username
        if password:
            kwargs["password"] = password
        return _impyla_connect(**kwargs)
    else:
        # pyhive falls back — NOSASL only
        return _pyhive.connect(host=host, port=port, database=database,
                               auth="NONE", username=username or "impala")


# ============================================================================
# TABLE DISCOVERY & CLASSIFICATION
# ============================================================================

def discover_tables(conn, database: str) -> List[Dict]:
    """
    Return a list of dicts:
        { name, type (KUDU/HIVE_INTERNAL/HIVE_EXTERNAL/UNKNOWN), location }
    """
    cursor = conn.cursor()
    cursor.execute(f"SHOW TABLES IN {database}")
    rows = cursor.fetchall()
    # impyla returns tuples; pyhive may return dicts
    table_names = [
        r[0] if isinstance(r, (list, tuple)) else r.get("tab_name", list(r.values())[0])
        for r in rows
    ]

    tables = []
    for name in sorted(table_names):
        ttype, location = _classify(cursor, database, name)
        tables.append({"name": name, "type": ttype, "location": location})

    cursor.close()
    return tables


def _classify(cursor, database: str, table: str) -> Tuple[str, str]:
    """Classify table type via DESCRIBE FORMATTED."""
    try:
        cursor.execute(f"DESCRIBE FORMATTED {database}.{table}")
        rows = cursor.fetchall()
        kv = {}
        for r in rows:
            if isinstance(r, (list, tuple)):
                k = (r[0] or "").strip()
                v = (r[1] or "").strip() if len(r) > 1 else ""
            else:
                k = str(r.get("name", r.get("col_name", ""))).strip()
                v = str(r.get("type", r.get("data_type", ""))).strip()
            if k:
                kv[k] = v

        storage_handler = kv.get("Storage Handler", "").lower()
        table_type_raw  = kv.get("Table Type",      "").upper()
        location        = kv.get("Location",         "")

        if "kudu" in storage_handler:
            return TYPE_KUDU, location
        elif "external" in table_type_raw:
            return TYPE_EXTERNAL, location
        else:
            return TYPE_INTERNAL, location

    except Exception as exc:
        print(f"    WARNING: DESCRIBE FORMATTED {table} failed: {exc}")
        return TYPE_UNKNOWN, ""


# ============================================================================
# ROW COUNT
# ============================================================================

def count_rows(conn, database: str, table: str) -> int:
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {database}.{table}")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    except Exception as exc:
        print(f"    WARNING: COUNT failed for {table}: {exc}")
        return -1
    finally:
        cursor.close()


# ============================================================================
# CSV DUMP
# ============================================================================

def dump_table_to_csv(conn, database: str, table: str, csv_path: str,
                      batch_size: int = 5000) -> Tuple[bool, int, Optional[str]]:
    """
    Dump all rows of a table to a CSV file.
    Returns (success, row_count, error_message).
    Uses streaming fetchmany() to avoid OOM on large tables.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT * FROM {database}.{table}")

        # Get column names from cursor description
        if cursor.description:
            col_names = [d[0] for d in cursor.description]
        else:
            return False, 0, "No cursor description — empty result or query failed"

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
                        writer.writerow([row.get(c, "") for c in col_names])
                    else:
                        writer.writerow([_safe_val(v) for v in row])
                    row_count += 1

        return True, row_count, None

    except Exception as exc:
        return False, 0, str(exc)
    finally:
        cursor.close()


def _safe_val(v: Any) -> Any:
    """Normalise values for CSV serialisation."""
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


# ============================================================================
# MANIFEST
# ============================================================================

def write_manifest(backup_dir: str, results: List[Dict], args, timestamp: str):
    manifest = {
        "backup_timestamp": timestamp,
        "source_env":       "LOCAL",
        "impala_host":      args.impala_host,
        "impala_port":      args.impala_port,
        "database":         args.database,
        "dry_run":          args.dry_run,
        "tables":           results,
        "created_at":       datetime.now().isoformat(),
    }
    path = os.path.join(backup_dir, "manifest.json")
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"\n  Manifest → {path}")


# ============================================================================
# MAIN BACKUP LOGIC
# ============================================================================

def run_backup(args):
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(args.output_dir, f"gmp_cis_backup_{timestamp}")

    print("=" * 65)
    print("  CIS Trade Hive — Full Local Database Backup")
    print("=" * 65)
    print(f"  Impala      : {args.impala_host}:{args.impala_port}")
    print(f"  Database    : {args.database}")
    print(f"  Output dir  : {backup_dir}")
    print(f"  Dry run     : {args.dry_run}")
    print(f"  Backend     : {_BACKEND}")
    print("=" * 65)

    # --- Connect ---
    print(f"\n  Connecting to Impala...")
    try:
        conn = _connect(
            host=args.impala_host,
            port=args.impala_port,
            database=args.database,
            auth=args.auth,
            username=args.username or "",
            password=args.password or "",
        )
        print(f"  Connected OK")
    except Exception as exc:
        print(f"  ERROR: Cannot connect to Impala: {exc}")
        sys.exit(1)

    # --- Discover ---
    print(f"\n  Discovering tables in {args.database}...")
    all_tables = discover_tables(conn, args.database)

    # --- Apply filters ---
    skip_set = {t.strip() for t in args.skip_tables.split(",") if t.strip()}
    if args.table:
        all_tables = [t for t in all_tables if t["name"] == args.table]
        if not all_tables:
            print(f"  ERROR: Table '{args.table}' not found in {args.database}")
            sys.exit(1)
    elif skip_set:
        all_tables = [t for t in all_tables if t["name"] not in skip_set]

    if args.only_kudu:
        all_tables = [t for t in all_tables if t["type"] == TYPE_KUDU]
    elif args.only_hive:
        all_tables = [t for t in all_tables if t["type"] in (TYPE_INTERNAL, TYPE_EXTERNAL)]

    kudu_tables     = [t for t in all_tables if t["type"] == TYPE_KUDU]
    internal_tables = [t for t in all_tables if t["type"] == TYPE_INTERNAL]
    external_tables = [t for t in all_tables if t["type"] == TYPE_EXTERNAL]
    unknown_tables  = [t for t in all_tables if t["type"] == TYPE_UNKNOWN]

    print(f"\n  Total : {len(all_tables)} tables")
    print(f"          {len(kudu_tables)} Kudu  |  "
          f"{len(internal_tables)} Hive internal  |  "
          f"{len(external_tables)} Hive external  |  "
          f"{len(unknown_tables)} Unknown")
    if skip_set:
        print(f"  Skipped: {', '.join(sorted(skip_set))}")

    if args.dry_run:
        print("\n  DRY RUN — counting rows only, no files written\n")

    # --- Process each table ---
    results = []

    type_dirs = {
        TYPE_KUDU:     os.path.join(backup_dir, "kudu"),
        TYPE_INTERNAL: os.path.join(backup_dir, "hive_internal"),
        TYPE_EXTERNAL: os.path.join(backup_dir, "hive_external"),
        TYPE_UNKNOWN:  os.path.join(backup_dir, "unknown"),
    }

    total_rows = 0
    succeeded  = 0
    failed     = 0

    print(f"\n  {'Table':<50} {'Type':<15} {'Rows':>8}  Status")
    print(f"  {'-'*50} {'-'*15} {'-'*8}  ------")

    for tbl in all_tables:
        name   = tbl["name"]
        ttype  = tbl["type"]
        start  = datetime.now()
        result = {
            "table":       name,
            "type":        ttype,
            "status":      "PENDING",
            "row_count":   0,
            "csv_path":    "",
            "error":       None,
            "duration_sec": 0,
        }

        row_count = count_rows(conn, args.database, name)
        result["row_count"] = row_count

        if args.dry_run:
            result["status"] = "DRY_RUN"
            print(f"  {name:<50} {ttype:<15} {max(row_count,0):>8,}  DRY_RUN")
            results.append(result)
            total_rows += max(row_count, 0)
            continue

        csv_path = os.path.join(type_dirs[ttype], f"{name}.csv")
        result["csv_path"] = csv_path

        ok, dumped_rows, err = dump_table_to_csv(conn, args.database, name, csv_path)
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

    conn.close()

    # --- Manifest ---
    if not args.dry_run:
        os.makedirs(backup_dir, exist_ok=True)
        write_manifest(backup_dir, results, args, timestamp)

    # --- Summary ---
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

    # Disk usage if files were written
    if not args.dry_run and succeeded > 0:
        try:
            import shutil
            size_bytes = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fnames in os.walk(backup_dir)
                for f in fnames
            )
            size_mb = size_bytes / (1024 * 1024)
            print(f"  Backup size  : {size_mb:.1f} MB")
        except Exception:
            pass

    if failed > 0:
        print(f"\n  FAILED TABLES:")
        for r in results:
            if r["status"] == "FAILED":
                print(f"    - {r['table']}: {r['error']}")

    if not args.dry_run and succeeded > 0:
        print(f"\n  CSV files written to:")
        for ttype, label in [(TYPE_KUDU, "Kudu"), (TYPE_INTERNAL, "Hive internal"),
                             (TYPE_EXTERNAL, "Hive external")]:
            d = type_dirs[ttype]
            files = [r for r in results if r["type"] == ttype and r["status"] == "SUCCESS"]
            if files:
                print(f"    {label:<16}: {d}/")

        print(f"\n  To restore from this backup:")
        print(f"    python scripts/load_migration_data.py --table <name> \\")
        print(f"      --file {backup_dir}/kudu/<name>.csv")

    print("=" * 65)

    return 1 if failed > 0 else 0


# ============================================================================
# ARGUMENT PARSER
# ============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="Full local database backup — Kudu + Hive internal + Hive external → CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backup everything (default settings — localhost:21050)
  python scripts/backup_local_db.py

  # Dry run: discover tables and count rows only, no files written
  python scripts/backup_local_db.py --dry-run

  # Custom output directory
  python scripts/backup_local_db.py --output-dir /tmp/my_backup

  # Single table
  python scripts/backup_local_db.py --table cis_trade

  # Kudu tables only
  python scripts/backup_local_db.py --only-kudu

  # Hive tables only (internal + external)
  python scripts/backup_local_db.py --only-hive

  # Skip audit/log tables (they can be huge)
  python scripts/backup_local_db.py --skip-tables cis_audit_log,cis_trade_history

  # Remote Impala (Cloudera LDAP)
  python scripts/backup_local_db.py \\
      --impala-host cloudera-host --impala-port 21050 \\
      --auth LDAP --username myuser --password mypass
""",
    )

    p.add_argument("--impala-host",  default="localhost",   help="Impala host (default: localhost)")
    p.add_argument("--impala-port",  type=int, default=21050, help="Impala port (default: 21050)")
    p.add_argument("--database",     default=DATABASE,       help="Database name (default: gmp_cis)")
    p.add_argument("--auth",         default="NOSASL",
                   choices=["NOSASL", "PLAIN", "GSSAPI", "LDAP"],
                   help="Auth mechanism (default: NOSASL for local Docker)")
    p.add_argument("--username",     default="",  help="Username (for LDAP/PLAIN auth)")
    p.add_argument("--password",     default="",  help="Password (for LDAP/PLAIN auth)")
    p.add_argument("--output-dir",   default="backups",
                   help="Local directory for backup output (default: ./backups)")
    p.add_argument("--table",        default="",  help="Back up a single table only")
    p.add_argument("--skip-tables",  default="",
                   help="Comma-separated table names to skip")
    p.add_argument("--only-kudu",    action="store_true", help="Back up Kudu tables only")
    p.add_argument("--only-hive",    action="store_true", help="Back up Hive tables only")
    p.add_argument("--dry-run",      action="store_true",
                   help="Discover + count rows only — no CSV files written")
    p.add_argument("--batch-size",   type=int, default=5000,
                   help="Rows fetched per batch (default: 5000)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(run_backup(args))
