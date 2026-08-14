#!/usr/bin/env python3
"""
Full Backup Script — Kudu tables + Hive/Parquet external tables

Auto-discovers ALL tables in the database via DESCRIBE FORMATTED and backs
each one up as Parquet:
  - Kudu tables     → Kudu Spark connector (org.apache.kudu.spark.kudu)
  - Hive internal   → spark.sql() SELECT *
  - Hive external   → spark.sql() SELECT *

No hardcoded table lists — any new table added to the database is picked up
automatically on the next backup run.

Table type detection (Kudu vs Hive/external) runs DESCRIBE FORMATTED via
the impala-shell binary, NOT spark.sql() -- Spark isolates its Hive
Metastore client in its own classloader, which lacks
org.apache.hadoop.hive.kudu.KuduSerDe regardless of what's passed via
--jars, so describing a Kudu-backed table through Spark's Hive catalog
fails with a ClassNotFoundException. --impala-host is therefore required
for every mode below except when impala-shell isn't needed at all (it
always is, for now).

Usage:
    # Backup everything (auto-discover Kudu + Hive)
    spark-submit \\
        --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \\
        kudu_full_backup.py \\
        --backup-path hdfs:///backups/gmp_cis \\
        --kudu-master kudu-master:7051 \\
        --impala-host impalad:21050

    # Hive/external tables only (no Kudu JAR needed)
    spark-submit kudu_full_backup.py \\
        --hive-only \\
        --backup-path hdfs:///backups/gmp_cis \\
        --impala-host impalad:21050

    # Kudu tables only
    spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
        --kudu-only \\
        --backup-path hdfs:///backups/gmp_cis \\
        --impala-host impalad:21050

    # Single table
    spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
        --table cis_trade \\
        --backup-path hdfs:///backups/gmp_cis \\
        --impala-host impalad:21050

    # Dry run (discover + count rows, no write)
    spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
        --backup-path hdfs:///backups/gmp_cis --dry-run \\
        --impala-host impalad:21050

    # Skip specific tables
    spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
        --backup-path hdfs:///backups/gmp_cis \\
        --skip-tables pos_stage_1_base,pos_stage_2_portfolio \\
        --impala-host impalad:21050

Author: CIS Trade Hive Team
Version: 3.0
Date: 2026-05-28
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import os

try:
    from pyspark.sql import SparkSession
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False
    print("WARNING: PySpark not available.")


DATABASE = os.environ.get('IMPALA_DB', 'gmp_cis')

DEFAULT_CONFIG = {
    'kudu_master':     'kudu-master:7051',
    'database':        DATABASE,
    'backup_path':     'hdfs:///backups/gmp_cis',
    'compression':     'snappy',
    'parallelism':     8,
    'scan_timeout_ms': 30000,
    'impala_host':     os.environ.get('IMPALA_HOST', ''),
}

TYPE_KUDU     = 'KUDU'
TYPE_HIVE     = 'HIVE'
TYPE_EXTERNAL = 'EXTERNAL'
TYPE_UNKNOWN  = 'UNKNOWN'


# ─────────────────────────────────────────────────────────────────────────────
# Table discovery
# ─────────────────────────────────────────────────────────────────────────────

def discover_tables(spark: SparkSession, database: str, impala_host: str) -> List[Dict]:
    """
    Auto-discover all tables in the database via SHOW TABLES + DESCRIBE FORMATTED.
    Returns list of {name, type, location}.
    No hardcoded list — picks up every table that exists in the database.
    """
    print(f"\n  Discovering tables in {database}...")

    try:
        tables_df = spark.sql(f"SHOW TABLES IN {database}")
        table_names = [row.tableName for row in tables_df.collect()]
    except Exception as e:
        print(f"  ERROR: SHOW TABLES failed: {e}")
        return []

    print(f"  Found {len(table_names)} tables")

    tables = []
    for name in sorted(table_names):
        ttype, location = _detect_type(database, name, impala_host)
        tables.append({"name": name, "type": ttype, "location": location})
        print(f"    {name:<55} [{ttype}]")

    return tables


def _describe_formatted_via_impala(database: str, table: str, impala_host: str) -> Optional[str]:
    """
    Run DESCRIBE FORMATTED via the impala-shell binary and return its raw
    tab-delimited output, or None on failure.

    NOT spark.sql("DESCRIBE FORMATTED ...") -- Spark isolates its Hive
    Metastore client in a separate classloader (controlled by
    spark.sql.hive.metastore.jars), independent of whatever is passed via
    --jars. Resolving a Kudu-backed table's metadata through that isolated
    client requires org.apache.hadoop.hive.kudu.KuduSerDe to be on ITS
    classpath specifically -- adding the kudu-hive jar to --jars does not
    reach it, so every Kudu table describe fails with
    "MetaException(message:java.lang.ClassNotFoundException
    org.apache.hadoop.hive.kudu.KuduSerDe)" regardless of --jars content.
    impala-shell talks to the Impala coordinator directly and never touches
    Spark's Hive client, sidestepping the issue entirely.
    """
    if not impala_host:
        print("    ERROR: --impala-host not set — required for table type detection")
        return None
    cmd = [
        'impala-shell', '-i', impala_host, '-d', database,
        '-B', '--output_delimiter=\t', '--print_header=false',
        '-q', f'DESCRIBE FORMATTED {table}',
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"    WARNING: impala-shell DESCRIBE FORMATTED {table} failed: {result.stderr.strip()}")
            return None
        return result.stdout
    except Exception as e:
        print(f"    WARNING: Could not run impala-shell for {table}: {e}")
        return None


def _detect_type(database: str, table: str, impala_host: str) -> Tuple[str, str]:
    """Detect table type via DESCRIBE FORMATTED (through impala-shell — see
    _describe_formatted_via_impala for why not spark.sql).

    Returns (type, kudu_table_name_or_location).
    For Kudu tables the second element is the internal Kudu table name
    (e.g. 'impala::gmp_cis.cis_trade') extracted from table properties,
    which is what the Kudu Spark connector requires.
    """
    raw = _describe_formatted_via_impala(database, table, impala_host)
    if raw is None:
        return TYPE_UNKNOWN, ""

    try:
        rows = {}
        for line in raw.splitlines():
            fields = line.split('\t')
            if len(fields) >= 2:
                key = fields[0].strip()
                val = fields[1].strip() if fields[1] else ""
                if key:
                    rows[key] = val

        storage_handler = rows.get("Storage Handler", "").lower()
        table_type_raw  = rows.get("Table Type", "").upper()
        location        = rows.get("Location", "")

        # Both open-source KuduStorageHandler and Cloudera variant contain 'kudu'
        if "kudu" in storage_handler:
            # Extract the internal Kudu table name from table properties.
            # DESCRIBE FORMATTED lists it as 'kudu.table_name' in the
            # Storage Desc Params / Table Parameters section.
            # Fall back to 'impala::<db>.<table>' if not found — Impala's
            # default naming convention for Kudu tables created via Impala.
            kudu_table = (
                rows.get("kudu.table_name")
                or rows.get("kudu.table")
                or f"impala::{database}.{table}"
            )
            return TYPE_KUDU, kudu_table
        elif "external" in table_type_raw:
            return TYPE_EXTERNAL, location
        else:
            return TYPE_HIVE, location

    except Exception as e:
        print(f"    WARNING: Could not parse DESCRIBE FORMATTED for {table}: {e}")
        return TYPE_UNKNOWN, ""


# ─────────────────────────────────────────────────────────────────────────────
# Backup
# ─────────────────────────────────────────────────────────────────────────────

class FullBackup:

    def __init__(self, config: Dict):
        self.config = config
        self.spark  = None
        self.ts     = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.stats  = {
            'kudu_ok': 0, 'kudu_fail': 0,
            'hive_ok': 0, 'hive_fail': 0,
            'not_found': 0,
            'total_rows': 0,
            'start': datetime.now().isoformat(),
            'end': None,
            'errors': [],
        }

    # ── Spark ─────────────────────────────────────────────────────────────────

    def init_spark(self) -> bool:
        if not SPARK_AVAILABLE:
            print("ERROR: PySpark not available")
            return False
        try:
            self.spark = (
                SparkSession.builder
                .appName(f"CIS_FullBackup_{self.ts}")
                .master("yarn")
                .config("spark.submit.deployMode", "client")
                .config("spark.sql.adaptive.enabled", "true")
                .config("spark.sql.parquet.compression.codec", self.config['compression'])
                .config("spark.default.parallelism", str(self.config['parallelism']))
                .config("spark.sql.shuffle.partitions", str(self.config['parallelism']))
                .config("spark.kudu.master", self.config['kudu_master'])
                .config("spark.hadoop.hive.exec.dynamic.partition.mode", "nonstrict")
                .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
                .enableHiveSupport()
                .getOrCreate()
            )
            self.spark.sparkContext.setLogLevel("WARN")
            print(f"  Spark app: {self.spark.sparkContext.applicationId}")
            return True
        except Exception as e:
            print(f"ERROR: Spark init failed: {e}")
            return False

    # ── Per-table backup ──────────────────────────────────────────────────────

    def backup_table(self, table_info: Dict, dry_run: bool) -> Dict:
        table  = table_info["name"]
        ttype  = table_info["type"]
        result = {
            "table": table, "type": ttype, "status": "PENDING",
            "row_count": 0, "error": None, "duration_sec": 0,
        }
        start    = datetime.now()
        out_path = (
            f"{self.config['backup_path']}"
            f"/{self.config['database']}"
            f"/{table}/full/{self.ts}"
        )
        full = f"{self.config['database']}.{table}"

        try:
            if ttype == TYPE_KUDU:
                # table_info["location"] holds the internal Kudu table name
                # (e.g. 'impala::gmp_cis.cis_trade') extracted by _detect_type.
                # The Kudu Spark connector requires this name, NOT the Hive
                # database-qualified name 'gmp_cis.cis_trade'.
                kudu_table_name = table_info.get("location") or f"impala::{full}"
                print(f"  Kudu table name: {kudu_table_name}")
                df = (
                    self.spark.read
                    .format("org.apache.kudu.spark.kudu")
                    .option("kudu.master", self.config['kudu_master'])
                    .option("kudu.table", kudu_table_name)
                    .option("kudu.scanRequestTimeoutMs",
                            str(self.config['scan_timeout_ms']))
                    .load()
                )
            else:
                # Hive internal, external, or unknown — spark.sql covers all
                df = self.spark.sql(f"SELECT * FROM {full}")

            result["row_count"] = df.count()

            if not dry_run:
                df.coalesce(1).write.mode("overwrite").option(
                    "compression", self.config['compression']
                ).parquet(out_path)
                self._write_meta(out_path, table, ttype, result["row_count"])

            result["status"] = "DRY_RUN" if dry_run else "SUCCESS"
            if ttype == TYPE_KUDU:
                self.stats['kudu_ok'] += 1
            else:
                self.stats['hive_ok'] += 1
            self.stats['total_rows'] += result["row_count"]

        except Exception as e:
            err = str(e)
            if any(k in err.lower() for k in (
                    'does not exist', 'table not found',
                    'nosuchentity', 'no such table')):
                result["status"] = "NOT_FOUND"
                result["error"]  = f"Table not found: {full}"
                self.stats['not_found'] += 1
            else:
                result["status"] = "FAILED"
                result["error"]  = err
                if ttype == TYPE_KUDU:
                    self.stats['kudu_fail'] += 1
                else:
                    self.stats['hive_fail'] += 1
                self.stats['errors'].append({"table": table, "error": err})

        result["duration_sec"] = round(
            (datetime.now() - start).total_seconds(), 1
        )
        return result

    # ── Manifest ──────────────────────────────────────────────────────────────

    def _write_meta(self, out_path: str, table: str, ttype: str, rows: int):
        meta = {
            "table": table, "type": ttype,
            "backup_timestamp": self.ts,
            "row_count": rows,
            "database": self.config['database'],
            "kudu_master": self.config['kudu_master'],
        }
        rdd = self.spark.sparkContext.parallelize([json.dumps(meta, indent=2)])
        rdd.coalesce(1).saveAsTextFile(f"{out_path}/_meta")

    def write_manifest(self, results: List[Dict]):
        manifest = {
            "backup_id":   self.ts,
            "backup_type": "full",
            "database":    self.config['database'],
            "kudu_master": self.config['kudu_master'],
            "backup_path": self.config['backup_path'],
            "created_at":  datetime.now().isoformat(),
            "stats":       self.stats,
            "tables":      results,
        }
        path = (
            f"{self.config['backup_path']}"
            f"/manifests/manifest_{self.ts}.json"
        )
        rdd = self.spark.sparkContext.parallelize(
            [json.dumps(manifest, indent=2)]
        )
        rdd.coalesce(1).saveAsTextFile(path)
        print(f"\n  Manifest → {path}")

    def close(self):
        if self.spark:
            self.spark.stop()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description='Full backup — auto-discovers all Kudu + Hive tables in database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backup everything (auto-discovered)
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
      --backup-path hdfs:///backups/gmp_cis --kudu-master kudu-master:7051

  # Hive/external only (no Kudu JAR needed)
  spark-submit kudu_full_backup.py --hive-only \\
      --backup-path hdfs:///backups/gmp_cis

  # Kudu only
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py --kudu-only \\
      --backup-path hdfs:///backups/gmp_cis

  # Single table
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
      --table cis_trade --backup-path hdfs:///backups/gmp_cis

  # Skip tables (comma-separated)
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
      --backup-path hdfs:///backups/gmp_cis \\
      --skip-tables cis_audit_log,pos_stage_1_base

  # Dry run
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
      --backup-path hdfs:///backups/gmp_cis --dry-run
        """
    )
    p.add_argument('--table',       help='Single table name to backup')
    p.add_argument('--kudu-only',   action='store_true',
                   help='Backup only Kudu tables (skip Hive/external)')
    p.add_argument('--hive-only',   action='store_true',
                   help='Backup only Hive/external tables (skip Kudu)')
    p.add_argument('--skip-tables', default='',
                   help='Comma-separated table names to skip')
    p.add_argument('--kudu-master', default=DEFAULT_CONFIG['kudu_master'])
    p.add_argument('--impala-host', default=DEFAULT_CONFIG['impala_host'],
                    help='Impala coordinator host:port (e.g. impalad:21050) used for table type '
                         'detection via impala-shell. Required — DESCRIBE FORMATTED cannot go '
                         'through Spark for Kudu tables (see _describe_formatted_via_impala).')
    p.add_argument('--database',    default=DEFAULT_CONFIG['database'])
    p.add_argument('--backup-path', default=DEFAULT_CONFIG['backup_path'])
    p.add_argument('--compression', default=DEFAULT_CONFIG['compression'],
                   choices=['snappy', 'gzip', 'lz4', 'none'])
    p.add_argument('--parallelism', type=int, default=DEFAULT_CONFIG['parallelism'])
    p.add_argument('--dry-run',     action='store_true',
                   help='Discover + count rows; do not write')
    return p.parse_args()


def main():
    args = parse_args()

    config = {
        'kudu_master':     args.kudu_master,
        'database':        args.database,
        'backup_path':     args.backup_path,
        'compression':     args.compression,
        'parallelism':     args.parallelism,
        'scan_timeout_ms': DEFAULT_CONFIG['scan_timeout_ms'],
        'impala_host':     args.impala_host,
    }

    skip = {t.strip() for t in args.skip_tables.split(',') if t.strip()}

    print("=" * 70)
    print("  FULL BACKUP — Auto-discover Kudu + Hive/Parquet")
    print("=" * 70)
    print(f"  Kudu master  : {config['kudu_master']}")
    print(f"  Impala host  : {config['impala_host'] or '(NOT SET — type detection will fail)'}")
    print(f"  Database     : {config['database']}")
    print(f"  Backup path  : {config['backup_path']}")
    print(f"  Compression  : {config['compression']}")
    print(f"  Kudu only    : {args.kudu_only}")
    print(f"  Hive only    : {args.hive_only}")
    print(f"  Skip tables  : {', '.join(skip) or 'none'}")
    print(f"  Dry run      : {args.dry_run}")
    print("=" * 70)

    backup = FullBackup(config)
    if not backup.init_spark():
        sys.exit(1)

    try:
        if args.table:
            # Single table — detect type via DESCRIBE FORMATTED
            ttype, loc = _detect_type(config['database'], args.table, config['impala_host'])
            tables = [{"name": args.table, "type": ttype, "location": loc}]
        else:
            # Auto-discover ALL tables in the database
            tables = discover_tables(backup.spark, config['database'], config['impala_host'])

            # Apply type filter
            if args.kudu_only:
                tables = [t for t in tables if t["type"] == TYPE_KUDU]
            elif args.hive_only:
                tables = [t for t in tables if t["type"] != TYPE_KUDU]

            # Apply skip filter
            if skip:
                tables = [t for t in tables if t["name"] not in skip]

        kudu_n = sum(1 for t in tables if t["type"] == TYPE_KUDU)
        hive_n = len(tables) - kudu_n

        print(f"\n  Backing up {len(tables)} tables  "
              f"({kudu_n} Kudu, {hive_n} Hive/External)")

        results = []
        for i, tinfo in enumerate(tables, 1):
            print(f"\n[{i}/{len(tables)}] {tinfo['name']}  [{tinfo['type']}]")
            r = backup.backup_table(tinfo, dry_run=args.dry_run)
            print(f"  {r['status']}  rows={r['row_count']:,}  {r['duration_sec']}s"
                  + (f"  — {r['error']}" if r['error'] else ""))
            results.append(r)

        if not args.dry_run:
            backup.write_manifest(results)

    finally:
        backup.close()

    # Summary
    ok      = [r for r in results if r['status'] in ('SUCCESS', 'DRY_RUN')]
    failed  = [r for r in results if r['status'] == 'FAILED']
    missing = [r for r in results if r['status'] == 'NOT_FOUND']

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  {'Table':<50} {'Type':<10} {'Status':<12} {'Rows':>10}")
    print(f"  {'-'*50} {'-'*10} {'-'*12} {'-'*10}")
    for r in results:
        print(f"  {r['table']:<50} {r['type']:<10} {r['status']:<12}"
              f" {r['row_count']:>10,}")
    print(f"\n  OK        : {len(ok)}")
    print(f"  Failed    : {len(failed)}")
    print(f"  Not found : {len(missing)}")
    print(f"  Total rows: {backup.stats['total_rows']:,}")
    print(f"  Kudu  OK={backup.stats['kudu_ok']}  Fail={backup.stats['kudu_fail']}")
    print(f"  Hive  OK={backup.stats['hive_ok']}  Fail={backup.stats['hive_fail']}")
    if failed:
        print("\n  ERRORS:")
        for r in failed:
            print(f"    {r['table']}: {r['error']}")
    print("=" * 70)

    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
