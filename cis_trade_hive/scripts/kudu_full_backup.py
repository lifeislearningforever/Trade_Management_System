#!/usr/bin/env python3
"""
Full Backup Script — Kudu tables + Hive/Parquet external tables

Backs up ALL tables in gmp_cis to HDFS/S3/ADLS as Parquet:
  - Kudu tables        → Kudu Spark connector
  - Hive external      → spark.sql() SELECT *
  - Hive internal      → spark.sql() SELECT *

Usage:
    spark-submit \\
        --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \\
        kudu_full_backup.py \\
        --all-tables \\
        --backup-path hdfs:///backups/gmp_cis \\
        --kudu-master kudu-master:7051

    # Backup single table
    spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
        --table cis_trade \\
        --backup-path hdfs:///backups/gmp_cis

    # Dry run (discover + count, no write)
    spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
        --all-tables --dry-run

Author: CIS Trade Hive Team
Version: 2.0
Date: 2026-05-28
"""

import argparse
import json
import sys
import os
from datetime import datetime
from typing import List, Dict, Any

try:
    from pyspark.sql import SparkSession
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False
    print("WARNING: PySpark not available.")


DATABASE = "gmp_cis"

DEFAULT_CONFIG = {
    'kudu_master':    'kudu-master:7051',
    'database':       DATABASE,
    'backup_path':    'hdfs:///backups/gmp_cis',
    'compression':    'snappy',
    'parallelism':    8,
    'scan_timeout_ms': 30000,
}

# ── Kudu tables (read via Kudu Spark connector) ──────────────────────────────
KUDU_TABLES = [
    # Core / ACL
    'cis_user',
    'cis_user_group',
    'cis_group_permissions',
    'cis_audit_log',
    'cis_sequence',
    # Reference data
    'cis_currency',
    'cis_country',
    'cis_calendar',
    'cis_counterparty_kudu',
    'cis_exchange',
    # Security
    'cis_security_kudu',
    'cis_security',
    # Portfolio
    'cis_portfolio',
    'cis_portfolio_history',
    # Trade
    'cis_trade',
    'cis_trade_history',
    'cis_trade_position',
    'cis_trade_note',
    'cis_trade_lot',
    # Position
    'cis_position',
    'cis_position_queue',
    'cis_settlement_queue',
    # Corporate Actions
    'cis_corporate_action',
    'cis_ca_cash_flow_queue',
    'cis_ca_cash_flow_log',
    # Cash Flow
    'cis_cash_flow',
    'cis_cash_flow_history',
    # Trade events
    'cis_trade_event_queue',
    # UDF
    'cis_udf_definition',
    'cis_udf_value',
    # Market Data
    'cis_fx_rate',
    'cis_market_price',
    'cis_equity_price',
    # Lookups
    'cis_lookup_trade_type',
    'cis_lookup_trade_status',
    'cis_lookup_currency',
    'cis_lookup_country',
    'cis_lookup_asset_class',
    'cis_lookup_security_type',
    'cis_lookup_portfolio_type',
    'cis_lookup_portfolio_status',
]

# ── Hive/Parquet external tables (read via spark.sql) ────────────────────────
HIVE_TABLES = [
    # Position upload pipeline
    'position_upload_standardized',
    'position_upload_report',
    'position_upload_staging',
    # Position master
    'cis_position_master',
    'cis_position_master_history',
    'cis_position_unmatched',
    # EOD source feeds
    'gmp_cis_sta_dly_position',
    'gmp_cis_sta_dly_ams_multi_dis_cif',
    'gmp_cis_sta_dly_ams_multi_hold',
    'gmp_cis_sta_dly_stat_street_ams_iceq',
    'gmp_cis_sta_mthly_stat_street_ams_iceq_end',
    'gmp_cis_sta_dly_stat_street_ams_daily_limit',
    # User upload staging
    'cis_user_sta_adhoc_position_1',
    'cis_user_sta_adhoc_position_2',
    'cis_user_sta_adhoc_position_3',
    'cis_user_sta_adhoc_position_4',
    'cis_user_sta_adhoc_position_5',
    # Upload tracking
    'cis_upload',
    'cis_upload_history',
    # Equity price history
    'cis_equity_price_history',
    # EOD CA cash flow
    'cis_eod_ca_cash_flow',
]

ALL_TABLES = {t: 'KUDU' for t in KUDU_TABLES}
ALL_TABLES.update({t: 'HIVE' for t in HIVE_TABLES})


# ─────────────────────────────────────────────────────────────────────────────

class FullBackup:

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.spark = None
        self.ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.stats = {
            'kudu_ok': 0, 'kudu_fail': 0,
            'hive_ok': 0, 'hive_fail': 0,
            'total_rows': 0,
            'start': datetime.now().isoformat(),
            'end': None,
            'errors': [],
        }

    # ── Spark init ────────────────────────────────────────────────────────────

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

    # ── Kudu backup ───────────────────────────────────────────────────────────

    def _backup_kudu(self, table: str, out_path: str, dry_run: bool) -> Dict:
        result = {'table': table, 'type': 'KUDU', 'status': 'PENDING',
                  'row_count': 0, 'error': None, 'duration_sec': 0}
        start = datetime.now()
        full  = f"{self.config['database']}.{table}"
        try:
            df = (
                self.spark.read
                .format("org.apache.kudu.spark.kudu")
                .option("kudu.master", self.config['kudu_master'])
                .option("kudu.table", full)
                .option("kudu.scanRequestTimeoutMs", str(self.config['scan_timeout_ms']))
                .load()
            )
            result['row_count'] = df.count()
            if not dry_run:
                df.write.mode("overwrite").option(
                    "compression", self.config['compression']
                ).parquet(out_path)
                self._write_meta(out_path, table, 'KUDU', result['row_count'])
            result['status'] = 'DRY_RUN' if dry_run else 'SUCCESS'
            self.stats['kudu_ok'] += 1
            self.stats['total_rows'] += result['row_count']
        except Exception as e:
            result['status'] = 'FAILED'
            result['error'] = str(e)
            self.stats['kudu_fail'] += 1
            self.stats['errors'].append({'table': table, 'error': str(e)})
        result['duration_sec'] = round((datetime.now() - start).total_seconds(), 1)
        return result

    # ── Hive/external backup ──────────────────────────────────────────────────

    def _backup_hive(self, table: str, out_path: str, dry_run: bool) -> Dict:
        result = {'table': table, 'type': 'HIVE', 'status': 'PENDING',
                  'row_count': 0, 'error': None, 'duration_sec': 0}
        start = datetime.now()
        full  = f"{self.config['database']}.{table}"
        try:
            df = self.spark.sql(f"SELECT * FROM {full}")
            result['row_count'] = df.count()
            if not dry_run:
                df.coalesce(1).write.mode("overwrite").option(
                    "compression", self.config['compression']
                ).parquet(out_path)
                self._write_meta(out_path, table, 'HIVE', result['row_count'])
            result['status'] = 'DRY_RUN' if dry_run else 'SUCCESS'
            self.stats['hive_ok'] += 1
            self.stats['total_rows'] += result['row_count']
        except Exception as e:
            err = str(e)
            # Table may not exist in this environment — treat as NOT_FOUND, not fatal
            if any(k in err.lower() for k in ('does not exist', 'table not found',
                                               'nosuchentity', 'no such table')):
                result['status'] = 'NOT_FOUND'
                result['error'] = f"Table not found: {full}"
            else:
                result['status'] = 'FAILED'
                result['error'] = err
                self.stats['hive_fail'] += 1
                self.stats['errors'].append({'table': table, 'error': err})
        result['duration_sec'] = round((datetime.now() - start).total_seconds(), 1)
        return result

    # ── Metadata sidecar ──────────────────────────────────────────────────────

    def _write_meta(self, out_path: str, table: str, ttype: str, rows: int):
        meta = {
            'table': table, 'type': ttype,
            'backup_timestamp': self.ts,
            'row_count': rows,
            'database': self.config['database'],
            'kudu_master': self.config['kudu_master'],
        }
        rdd = self.spark.sparkContext.parallelize([json.dumps(meta, indent=2)])
        rdd.coalesce(1).saveAsTextFile(f"{out_path}/_meta")

    # ── Orchestrator ──────────────────────────────────────────────────────────

    def run(self, tables: Dict[str, str], dry_run: bool = False) -> List[Dict]:
        """
        tables: {table_name: 'KUDU'|'HIVE'}
        """
        results = []
        total = len(tables)
        for i, (table, ttype) in enumerate(tables.items(), 1):
            out_path = (
                f"{self.config['backup_path']}"
                f"/{self.config['database']}"
                f"/{table}/full/{self.ts}"
            )
            print(f"\n[{i}/{total}] {table}  [{ttype}]")
            print(f"  → {out_path}")

            if ttype == 'KUDU':
                r = self._backup_kudu(table, out_path, dry_run)
            else:
                r = self._backup_hive(table, out_path, dry_run)

            print(f"  {r['status']}  rows={r['row_count']:,}  {r['duration_sec']}s"
                  + (f"  ERROR: {r['error']}" if r['error'] else ""))
            results.append(r)

        self.stats['end'] = datetime.now().isoformat()
        return results

    def write_manifest(self, results: List[Dict]):
        manifest = {
            'backup_id':       self.ts,
            'backup_type':     'full',
            'database':        self.config['database'],
            'kudu_master':     self.config['kudu_master'],
            'backup_path':     self.config['backup_path'],
            'created_at':      datetime.now().isoformat(),
            'stats':           self.stats,
            'tables':          results,
        }
        path = (f"{self.config['backup_path']}"
                f"/manifests/manifest_{self.ts}.json")
        rdd = self.spark.sparkContext.parallelize([json.dumps(manifest, indent=2)])
        rdd.coalesce(1).saveAsTextFile(path)
        print(f"\n  Manifest → {path}")

    def close(self):
        if self.spark:
            self.spark.stop()


# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description='Full backup — Kudu tables + Hive/Parquet external tables',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backup everything (Kudu + Hive)
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
      --all-tables --backup-path hdfs:///backups/gmp_cis \\
      --kudu-master kudu-master:7051

  # Kudu tables only
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
      --kudu-only --backup-path hdfs:///backups/gmp_cis

  # Hive/external tables only (no Kudu JAR needed)
  spark-submit kudu_full_backup.py \\
      --hive-only --backup-path hdfs:///backups/gmp_cis

  # Single table
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
      --table cis_trade --backup-path hdfs:///backups/gmp_cis

  # Dry run
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \\
      --all-tables --dry-run
        """
    )
    p.add_argument('--table',       help='Single table name')
    p.add_argument('--tables',      help='Comma-separated table names')
    p.add_argument('--all-tables',  action='store_true', help='Backup Kudu + Hive tables')
    p.add_argument('--kudu-only',   action='store_true', help='Backup Kudu tables only')
    p.add_argument('--hive-only',   action='store_true', help='Backup Hive/external tables only')
    p.add_argument('--kudu-master', default=DEFAULT_CONFIG['kudu_master'])
    p.add_argument('--database',    default=DEFAULT_CONFIG['database'])
    p.add_argument('--backup-path', default=DEFAULT_CONFIG['backup_path'])
    p.add_argument('--compression', default=DEFAULT_CONFIG['compression'],
                   choices=['snappy', 'gzip', 'lz4', 'none'])
    p.add_argument('--parallelism', type=int, default=DEFAULT_CONFIG['parallelism'])
    p.add_argument('--dry-run',     action='store_true')
    return p.parse_args()


def main():
    args = parse_args()

    if not any([args.table, args.tables, args.all_tables, args.kudu_only, args.hive_only]):
        print("ERROR: Specify --all-tables, --kudu-only, --hive-only, --table, or --tables")
        sys.exit(1)

    config = {
        'kudu_master':     args.kudu_master,
        'database':        args.database,
        'backup_path':     args.backup_path,
        'compression':     args.compression,
        'parallelism':     args.parallelism,
        'scan_timeout_ms': DEFAULT_CONFIG['scan_timeout_ms'],
    }

    # Build table→type map
    if args.all_tables:
        tables = dict(ALL_TABLES)
    elif args.kudu_only:
        tables = {t: 'KUDU' for t in KUDU_TABLES}
    elif args.hive_only:
        tables = {t: 'HIVE' for t in HIVE_TABLES}
    elif args.tables:
        names = [t.strip() for t in args.tables.split(',')]
        tables = {t: ALL_TABLES.get(t, 'HIVE') for t in names}
    else:
        t = args.table
        tables = {t: ALL_TABLES.get(t, 'HIVE')}

    kudu_count = sum(1 for v in tables.values() if v == 'KUDU')
    hive_count = sum(1 for v in tables.values() if v == 'HIVE')

    print("=" * 70)
    print("  FULL BACKUP — Kudu + Hive/Parquet")
    print("=" * 70)
    print(f"  Kudu master  : {config['kudu_master']}")
    print(f"  Database     : {config['database']}")
    print(f"  Backup path  : {config['backup_path']}")
    print(f"  Compression  : {config['compression']}")
    print(f"  Kudu tables  : {kudu_count}")
    print(f"  Hive tables  : {hive_count}")
    print(f"  Total tables : {len(tables)}")
    print(f"  Dry run      : {args.dry_run}")
    print("=" * 70)

    backup = FullBackup(config)
    if not backup.init_spark():
        sys.exit(1)

    try:
        results = backup.run(tables, dry_run=args.dry_run)
        if not args.dry_run:
            backup.write_manifest(results)
    finally:
        backup.close()

    # Summary
    ok       = [r for r in results if r['status'] in ('SUCCESS', 'DRY_RUN')]
    failed   = [r for r in results if r['status'] == 'FAILED']
    missing  = [r for r in results if r['status'] == 'NOT_FOUND']

    print("\n" + "=" * 70)
    print("  BACKUP SUMMARY")
    print("=" * 70)
    print(f"  {'Table':<50} {'Type':<6} {'Status':<12} {'Rows':>10}")
    print(f"  {'-'*50} {'-'*6} {'-'*12} {'-'*10}")
    for r in results:
        print(f"  {r['table']:<50} {r['type']:<6} {r['status']:<12} {r['row_count']:>10,}")
    print(f"\n  OK       : {len(ok)}")
    print(f"  Failed   : {len(failed)}")
    print(f"  Missing  : {len(missing)}")
    print(f"  Total rows: {backup.stats['total_rows']:,}")
    print(f"  Kudu OK  : {backup.stats['kudu_ok']}  Fail: {backup.stats['kudu_fail']}")
    print(f"  Hive OK  : {backup.stats['hive_ok']}  Fail: {backup.stats['hive_fail']}")
    if failed:
        print("\n  ERRORS:")
        for r in failed:
            print(f"    {r['table']}: {r['error']}")
    print("=" * 70)

    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
