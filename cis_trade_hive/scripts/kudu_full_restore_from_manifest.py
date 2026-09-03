#!/usr/bin/env python3
"""
Kudu + Hive Full Restore — Manifest-Driven (multi-table)

Restores every table listed in a kudu_full_backup.py manifest in ONE
spark-submit invocation, reusing KuduFullRestore.restore_table() from
kudu_full_restore.py (same directory) for each table — no restore logic
is duplicated here.

Built for the PROD -> DR daily full-sync Control-M job (see
docs/CONTROL_M_DR_SYNC_JOB.md): a single "kudu_full_backup.py --all-tables"
run on PROD discovers and backs up everything in the database into one
manifest; this script is what actually walks that manifest and restores
each table into DR in a single job step, instead of needing one Control-M
job per table.

Usage:
    # Restore from a specific manifest
    spark-submit --jars /jars/kudu/*.jar kudu_full_restore_from_manifest.py \
        --manifest hdfs:///backups/gmp_cis/manifests/manifest_20260807_020000.json \
        --kudu-master <DR_KUDU_MASTER>:7051

    # Auto-discover and restore from the LATEST manifest under --backup-path
    spark-submit --jars /jars/kudu/*.jar kudu_full_restore_from_manifest.py \
        --backup-path hdfs:///backups/gmp_cis \
        --kudu-master <DR_KUDU_MASTER>:7051 \
        --latest

    # Dry run
    spark-submit --jars /jars/kudu/*.jar kudu_full_restore_from_manifest.py \
        --backup-path hdfs:///backups/gmp_cis --latest --dry-run

    # Skip specific tables
    spark-submit --jars /jars/kudu/*.jar kudu_full_restore_from_manifest.py \
        --backup-path hdfs:///backups/gmp_cis --latest \
        --skip-tables pos_stage_1_base,pos_stage_2_portfolio

Author: CIS Trade Hive Team
Version: 1.0
Date: 2026-08-07
"""

import argparse
import json
import sys
import os
from typing import Any, Dict, Optional

try:
    from pyspark.sql import SparkSession  # noqa: F401
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False
    print("WARNING: PySpark not available.")

# Reuse the already-fixed single-table restore logic (Hive support, real
# truncate-delete, _meta fix) -- see kudu_full_restore.py. Not duplicated.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from kudu_full_restore import (  # noqa: E402
    KuduFullRestore,
    RESTORE_MODES,
    DEFAULT_CONFIG as _RESTORE_DEFAULTS,
)


def find_latest_manifest(spark, backup_path: str) -> Optional[str]:
    """
    List {backup_path}/manifests/ and return the path to the most recent
    manifest_<ts>.json entry (itself a directory -- kudu_full_backup.py
    writes it via saveAsTextFile), or None if none found.
    """
    manifests_dir = f"{backup_path}/manifests"
    try:
        hadoop_conf = spark.sparkContext._jsc.hadoopConfiguration()
        fs = spark._jvm.org.apache.hadoop.fs.FileSystem.get(
            spark._jvm.java.net.URI.create(manifests_dir), hadoop_conf
        )
        path = spark._jvm.org.apache.hadoop.fs.Path(manifests_dir)
        if not fs.exists(path):
            print(f"  No manifests directory at {manifests_dir}")
            return None

        names = [s.getPath().getName() for s in fs.listStatus(path) if s.isDirectory()]
        candidates = sorted(n for n in names if n.startswith("manifest_") and n.endswith(".json"))
        if not candidates:
            print(f"  No manifest_*.json entries found under {manifests_dir}")
            return None

        latest = candidates[-1]
        print(f"  Latest manifest: {latest}")
        return f"{manifests_dir}/{latest}"
    except Exception as e:
        print(f"  ERROR listing manifests: {e}")
        return None


def read_manifest(spark, manifest_path: str) -> Optional[Dict[str, Any]]:
    """Read a manifest directory written by kudu_full_backup.py's write_manifest()."""
    try:
        rdd = spark.sparkContext.textFile(f"{manifest_path}/part-*")
        lines = rdd.collect()
        if not lines:
            return None
        return json.loads('\n'.join(lines))
    except Exception as e:
        print(f"  ERROR reading manifest {manifest_path}: {e}")
        return None


def parse_args():
    parser = argparse.ArgumentParser(
        description='Restore every table in a kudu_full_backup.py manifest (Kudu + Hive)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Restore from a specific manifest
  spark-submit --jars /jars/kudu/*.jar kudu_full_restore_from_manifest.py \\
      --manifest hdfs:///backups/gmp_cis/manifests/manifest_20260807_020000.json \\
      --kudu-master kudu-dr-master:7051

  # Auto-discover and restore from the latest manifest
  spark-submit --jars /jars/kudu/*.jar kudu_full_restore_from_manifest.py \\
      --backup-path hdfs:///backups/gmp_cis --latest \\
      --kudu-master kudu-dr-master:7051
        """
    )
    parser.add_argument('--manifest', type=str,
                         help='Path to a specific manifest_<ts>.json directory')
    parser.add_argument('--backup-path', type=str,
                         help='Backup root (used with --latest to find manifests/)')
    parser.add_argument('--latest', action='store_true',
                         help='Auto-discover the most recent manifest under --backup-path/manifests/')
    parser.add_argument('--mode', type=str, default='truncate_insert',
                         choices=list(RESTORE_MODES.keys()),
                         help='Restore mode applied to every table (default: truncate_insert)')
    parser.add_argument('--kudu-master', type=str, default=_RESTORE_DEFAULTS['kudu_master'])
    parser.add_argument('--impala-host', type=str, default=_RESTORE_DEFAULTS.get('impala_host', ''),
                         help='Impala coordinator host:port, used for table type detection via '
                              'impala-shell instead of spark.sql (required — see kudu_full_restore.py)')
    parser.add_argument('--impala-shell-flags', type=str,
                         default=_RESTORE_DEFAULTS.get('impala_shell_flags', '-k --ssl'),
                         help="Extra flags passed to impala-shell for type detection "
                              "(default: '-k --ssl' for Kerberos+TLS clusters; pass '' for NOSASL/local)")
    parser.add_argument('--database', type=str, default=_RESTORE_DEFAULTS['database'])
    parser.add_argument('--parallelism', type=int, default=_RESTORE_DEFAULTS['parallelism'])
    parser.add_argument('--skip-tables', default='',
                         help='Comma-separated table names to skip')
    parser.add_argument('--validate', action='store_true',
                         help='Validate each restored table by counting rows')
    parser.add_argument('--dry-run', action='store_true',
                         help='Validate without performing actual restores')
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.manifest and not (args.backup_path and args.latest):
        print("ERROR: Must specify --manifest, or --backup-path together with --latest")
        sys.exit(1)

    config = {
        'kudu_master': args.kudu_master,
        'database': args.database,
        'parallelism': args.parallelism,
        'batch_size': _RESTORE_DEFAULTS['batch_size'],
        'operation_timeout_ms': _RESTORE_DEFAULTS['operation_timeout_ms'],
        'impala_host': args.impala_host,
        'impala_shell_flags': args.impala_shell_flags,
    }

    skip = {t.strip() for t in args.skip_tables.split(',') if t.strip()}

    print("=" * 70)
    print("  FULL RESTORE FROM MANIFEST (Kudu + Hive)")
    print("=" * 70)
    print(f"  Kudu Master: {config['kudu_master']}")
    print(f"  Impala Host: {config['impala_host'] or '(NOT SET — type detection will fail)'}")
    print(f"  Database:    {config['database']}")
    print(f"  Mode:        {args.mode}")
    print(f"  Dry Run:     {args.dry_run}")
    print("=" * 70)

    restore = KuduFullRestore(config)
    if not restore.init_spark():
        print("ERROR: Failed to initialize Spark session")
        sys.exit(1)

    try:
        manifest_path = args.manifest
        if not manifest_path:
            manifest_path = find_latest_manifest(restore.spark, args.backup_path)
            if not manifest_path:
                print("ERROR: Could not find a manifest to restore from")
                sys.exit(1)

        manifest = read_manifest(restore.spark, manifest_path)
        if not manifest:
            print(f"ERROR: Could not read manifest at {manifest_path}")
            sys.exit(1)

        backup_id = manifest.get('backup_id')
        backup_root = manifest.get('backup_path')
        tables = manifest.get('tables', [])
        print(f"\n  Manifest backup_id:   {backup_id}")
        print(f"  Manifest backup_path: {backup_root}")
        print(f"  Tables in manifest:   {len(tables)}")

        restorable = [
            t for t in tables
            if t.get('status') == 'SUCCESS' and t.get('table') not in skip
        ]
        skipped_not_ok = [t for t in tables if t.get('status') != 'SUCCESS']
        skipped_by_flag = [
            t for t in tables
            if t.get('status') == 'SUCCESS' and t.get('table') in skip
        ]

        print(f"  Restorable (backup was SUCCESS): {len(restorable)}")
        print(f"  Skipped (backup was not SUCCESS): {len(skipped_not_ok)}")
        print(f"  Skipped (--skip-tables):          {len(skipped_by_flag)}")

        results = []
        for i, tinfo in enumerate(restorable, 1):
            table_name = tinfo.get('table')
            table_backup_path = f"{backup_root}/{config['database']}/{table_name}/full/{backup_id}"
            print(f"\n[{i}/{len(restorable)}] {table_name}")
            r = restore.restore_table(table_name, table_backup_path, mode=args.mode, dry_run=args.dry_run)
            if args.validate and r['status'] == 'success' and not args.dry_run:
                restore.validate_restore(table_name, r['rows_restored'])
            results.append(r)

        ok = [r for r in results if r['status'] in ('success', 'dry_run')]
        failed = [r for r in results if r['status'] == 'failed']

        print("\n" + "=" * 70)
        print("  MANIFEST RESTORE SUMMARY")
        print("=" * 70)
        print(f"  {'Table':<50} {'Status':<10} {'Rows':>10} {'Deleted':>10}")
        print(f"  {'-'*50} {'-'*10} {'-'*10} {'-'*10}")
        for r in results:
            print(f"  {r['table']:<50} {r['status']:<10} {r['rows_restored']:>10,} {r.get('rows_deleted', 0):>10,}")

        print(f"\n  Restored : {len(ok)}")
        print(f"  Failed   : {len(failed)}")
        print(f"  Skipped  : {len(skipped_not_ok) + len(skipped_by_flag)}")
        print(f"  Total rows restored: {restore.stats['total_rows']:,}")
        if failed:
            print("\n  ERRORS:")
            for r in failed:
                print(f"    {r['table']}: {r['error']}")
        print("=" * 70)

        sys.exit(1 if failed else 0)

    finally:
        restore.close()


if __name__ == '__main__':
    main()
