#!/usr/bin/env python3
"""
Restore SIT Kudu from Local Parquet Backup (received via SCP/SFTP from UAT)

Reads Parquet files from the extracted backup directory and upserts
each table into the SIT Kudu cluster.

Flow:
    SCP/SFTP  →  Extract tar.gz  →  Local Parquet  →  Spark  →  SIT Kudu

Usage:
    # Restore all tables from backup
    spark-submit \\
        --master yarn --deploy-mode client \\
        --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \\
        restore_sit_from_local.py \\
        --kudu-master <sit-kudu-master>:7051 \\
        --backup-dir /tmp/gmp_cis_20260422_103000/

    # Dry run (validate parquet files exist, no writes)
    spark-submit \\
        --master yarn --deploy-mode client \\
        --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \\
        restore_sit_from_local.py \\
        --kudu-master <sit-kudu-master>:7051 \\
        --backup-dir /tmp/gmp_cis_20260422_103000/ \\
        --dry-run

    # Restore specific tables only
    spark-submit \\
        --master yarn --deploy-mode client \\
        --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \\
        restore_sit_from_local.py \\
        --kudu-master <sit-kudu-master>:7051 \\
        --backup-dir /tmp/gmp_cis_20260422_103000/ \\
        --tables cis_portfolio,cis_trade

Pre-requisite:
    SIT gmp_cis schema must already be created before restoring.
    Run: impala-shell -i <sit-host>:21050 -f sql/ddl/00_all_kudu_tables_sit.sql

Author: CIS Trade Hive Team
Version: 1.0
Date: 2026-04-22
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import List, Optional

try:
    from pyspark.sql import SparkSession, DataFrame
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False
    print("WARNING: PySpark not available.")

DATABASE = "gmp_cis"

# Restore order — same dependency order as backup
RESTORE_ORDER = [
    "gmp_cis_sta_dly_currency",
    "gmp_cis_sta_dly_country",
    "gmp_cis_sta_dly_calendar",
    "cis_user",
    "cis_user_group",
    "cis_group",
    "cis_group_permissions",
    "cis_user_info",
    "cis_user_group_info",
    "cis_permission_info",
    "cis_user_group_mapping_info",
    "cis_group_permission_map",
    "cis_counterparty_kudu",
    "cis_security",
    "cis_security_history",
    "cis_equity_price_kudu",
    "cis_equity_price_history",
    "gmp_cis_sta_dly_fx_rates",
    "cis_udf_definition",
    "cis_udf_option",
    "cis_udf_field",
    "cis_portfolio",
    "cis_portfolio_history",
    "cis_trade",
    "cis_trade_history",
    "cis_trade_note",
    "cis_udf_value",
    "cis_udf_value_multi",
    "cis_trade_position",
    "cis_trade_lot",
    "cis_corporate_actions",
    "cis_corporate_actions_history",
    "cis_cash_flow",
    "cis_cash_flow_history",
    "cis_ca_cash_flow_queue",
    "cis_ca_cash_flow_log",
    "cis_trade_event_queue",
    "cis_position_queue",
    "cis_settlement_queue",
    "cis_sequence",
    "cis_system_date",
    "cis_file_upload",
    "cis_audit_log",
]


def read_manifest(backup_dir: str) -> Optional[dict]:
    """Read manifest.json written by backup script."""
    manifest_path = os.path.join(backup_dir, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            return json.load(f)
    return None


def discover_tables(backup_dir: str) -> List[str]:
    """
    Return tables found in the backup dir, in RESTORE_ORDER.
    Tables not in RESTORE_ORDER are appended at the end.
    """
    available = {
        d for d in os.listdir(backup_dir)
        if os.path.isdir(os.path.join(backup_dir, d))
    }
    ordered = [t for t in RESTORE_ORDER if t in available]
    extras  = [t for t in available if t not in RESTORE_ORDER]
    return ordered + extras


def restore_table(
    spark: SparkSession,
    kudu_master: str,
    database: str,
    table: str,
    backup_dir: str,
    dry_run: bool = False,
) -> dict:
    """Restore one table from local Parquet into SIT Kudu. Returns result dict."""
    result = {
        "table": table,
        "status": "PENDING",
        "row_count": 0,
        "error": None,
        "duration_sec": 0,
    }
    start = datetime.now()
    parquet_path = os.path.join(backup_dir, table)
    kudu_table = f"{database}.{table}"

    print(f"\n{'='*60}")
    print(f"  Table  : {table}")
    print(f"  Source : {parquet_path}")

    if not os.path.exists(parquet_path):
        result["status"] = "SKIPPED"
        result["error"] = "Parquet directory not found in backup"
        print(f"  SKIPPED — not found in backup")
        return result

    try:
        df: DataFrame = spark.read.parquet(parquet_path)
        row_count = df.count()
        result["row_count"] = row_count
        print(f"  Rows   : {row_count:,}")

        if dry_run:
            result["status"] = "DRY_RUN"
            print(f"  DRY RUN — skipping write")
            return result

        if row_count == 0:
            result["status"] = "EMPTY"
            print(f"  Empty backup — nothing to restore")
            return result

        # UPSERT into SIT Kudu
        (
            df.write
            .format("org.apache.kudu.spark.kudu")
            .option("kudu.master", kudu_master)
            .option("kudu.table", kudu_table)
            .option("kudu.operation", "upsert")
            .mode("append")
            .save()
        )

        result["status"] = "SUCCESS"
        result["duration_sec"] = round((datetime.now() - start).total_seconds(), 1)
        print(f"  SUCCESS — {row_count:,} rows in {result['duration_sec']}s")

    except Exception as e:
        result["status"] = "FAILED"
        result["error"] = str(e)
        result["duration_sec"] = round((datetime.now() - start).total_seconds(), 1)
        print(f"  FAILED: {e}")

    return result


def parse_args():
    p = argparse.ArgumentParser(description="Restore SIT Kudu from local Parquet backup (from UAT via SCP)")
    p.add_argument("--kudu-master", required=True, help="SIT Kudu master (host:port)")
    p.add_argument("--backup-dir", required=True, help="Path to extracted backup directory")
    p.add_argument("--database", default=DATABASE, help=f"Database name (default: {DATABASE})")
    p.add_argument("--tables", default=None, help="Comma-separated tables to restore (default: all in backup)")
    p.add_argument("--skip-tables", default=None, help="Comma-separated tables to skip")
    p.add_argument("--dry-run", action="store_true", help="Validate files exist, no writes")
    p.add_argument("--continue-on-error", action="store_true", help="Continue even if a table fails")
    return p.parse_args()


def main():
    if not SPARK_AVAILABLE:
        print("ERROR: PySpark required.")
        sys.exit(1)

    args = parse_args()

    if not os.path.isdir(args.backup_dir):
        print(f"ERROR: backup-dir does not exist: {args.backup_dir}")
        sys.exit(1)

    # Read manifest (if available)
    manifest = read_manifest(args.backup_dir)
    if manifest:
        print(f"\nManifest found:")
        print(f"  Backup timestamp : {manifest.get('backup_timestamp', 'unknown')}")
        print(f"  UAT Kudu master  : {manifest.get('uat_kudu_master', 'unknown')}")
        print(f"  Database         : {manifest.get('database', 'unknown')}")

    # Build table list
    if args.tables:
        tables = [t.strip() for t in args.tables.split(",")]
    else:
        tables = discover_tables(args.backup_dir)

    if args.skip_tables:
        skip = {t.strip() for t in args.skip_tables.split(",")}
        tables = [t for t in tables if t not in skip]

    print("\n" + "=" * 60)
    print("  Local Parquet → SIT Kudu Restore")
    print("=" * 60)
    print(f"  SIT Kudu master : {args.kudu_master}")
    print(f"  Backup dir      : {args.backup_dir}")
    print(f"  Tables          : {len(tables)}")
    print(f"  Dry run         : {args.dry_run}")
    print("=" * 60)

    spark = (
        SparkSession.builder
        .appName(f"CIS_SIT_Restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        .master("yarn")
        .config("spark.submit.deployMode", "client")
        # Cloudera CML — cross-join & timeouts
        .config("spark.sql.crossJoin.enabled", "true")
        .config("spark.rpc.askTimeout", "300")
        .config("spark.network.timeout", "600")
        # Hive Warehouse Connector (HWC) — required on Cloudera
        .config("spark.sql.extensions",
                "com.qubole.spark.hiveacid.HiveAcidAutoConvertExtension")
        .config("spark.sql.hive.hwc.execution.mode", "spark")
        .config("spark.datasource.hive.warehouse.read.jdbc.mode", "cluster")
        .config("spark.hadoop.hive.exec.dynamic.partition.mode", "nonstrict")
        .config("spark.kryo.registrator",
                "com.qubole.spark.hiveacid.util.HiveAcidKryoRegistrator")
        # Kudu master (SIT)
        .config("spark.kudu.master", args.kudu_master)
        # Legacy time parser for STRING date columns
        .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    results = []
    start_all = datetime.now()

    for table in tables:
        result = restore_table(
            spark=spark,
            kudu_master=args.kudu_master,
            database=args.database,
            table=table,
            backup_dir=args.backup_dir,
            dry_run=args.dry_run,
        )
        results.append(result)

        if result["status"] == "FAILED" and not args.continue_on_error:
            print(f"\nAborting — table {table} failed. Use --continue-on-error to skip.")
            break

    total_sec = round((datetime.now() - start_all).total_seconds(), 1)
    success  = [r for r in results if r["status"] == "SUCCESS"]
    failed   = [r for r in results if r["status"] == "FAILED"]
    skipped  = [r for r in results if r["status"] in ("SKIPPED", "EMPTY", "DRY_RUN")]
    total_rows = sum(r["row_count"] for r in success)

    print("\n\n" + "=" * 60)
    print("  RESTORE SUMMARY")
    print("=" * 60)
    print(f"  Success     : {len(success)}")
    print(f"  Failed      : {len(failed)}")
    print(f"  Skipped     : {len(skipped)}")
    print(f"  Total rows  : {total_rows:,}")
    print(f"  Total time  : {total_sec}s")
    print(f"\n  {'Table':<45} {'Status':<12} {'Rows':>10} {'Sec':>6}")
    print(f"  {'-'*45} {'-'*12} {'-'*10} {'-'*6}")
    for r in results:
        print(f"  {r['table']:<45} {r['status']:<12} {r['row_count']:>10,} {r['duration_sec']:>6.1f}")

    if failed:
        print("\n  FAILED TABLES:")
        for r in failed:
            print(f"    - {r['table']}: {r['error']}")

    spark.stop()

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
