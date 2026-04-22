#!/usr/bin/env python3
"""
SIT Backup to Local Disk (rollback safety net before UAT migration)

Reads all gmp_cis tables from SIT Kudu and saves each table as
Parquet files on the local filesystem.

Run this BEFORE running 99_sit_clean_gmp_cis.sql so you can roll back
SIT to its previous state if the UAT restore fails or goes wrong.

Flow:
    SIT Kudu  →  Spark  →  Local Parquet  →  (optional) tar.gz for archival

Usage:
    # Backup all tables
    spark-submit \\
        --master yarn --deploy-mode client \\
        --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \\
        backup_sit_to_local.py \\
        --kudu-master <sit-kudu-master>:7051 \\
        --output-dir /tmp/sit_backup

    # Skip audit log (faster — rarely needed for rollback)
    spark-submit \\
        --master yarn --deploy-mode client \\
        --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \\
        backup_sit_to_local.py \\
        --kudu-master <sit-kudu-master>:7051 \\
        --output-dir /tmp/sit_backup \\
        --skip-tables cis_audit_log

    # Dry run (row counts only, no write)
    spark-submit \\
        --master yarn --deploy-mode client \\
        --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \\
        backup_sit_to_local.py \\
        --kudu-master <sit-kudu-master>:7051 \\
        --dry-run

Rollback procedure (if UAT migration fails):
    1. Recreate SIT schema:
       impala-shell -i <sit-host>:21050 -f sql/ddl/99_sit_clean_gmp_cis.sql
       impala-shell -i <sit-host>:21050 -f sql/ddl/00_all_kudu_tables_sit.sql

    2. Restore from this backup:
       spark-submit --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \\
           restore_sit_from_local.py \\
           --kudu-master <sit-kudu-master>:7051 \\
           --backup-dir /tmp/sit_backup/gmp_cis_<timestamp>/

Author: CIS Trade Hive Team
Version: 1.0
Date: 2026-04-22
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import List

try:
    from pyspark.sql import SparkSession
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False
    print("WARNING: PySpark not available.")


# ============================================================================
# TABLE LIST — dependency order
# ============================================================================
ALL_TABLES = [
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

DATABASE = "gmp_cis"


def backup_table(spark, kudu_master, database, table, output_dir, dry_run=False):
    result = {
        "table": table,
        "status": "PENDING",
        "row_count": 0,
        "output_path": "",
        "error": None,
        "duration_sec": 0,
    }
    start = datetime.now()
    kudu_table = f"impala::{database}.{table}"
    out_path = os.path.join(output_dir, table)

    print(f"\n{'='*60}")
    print(f"  Table : {table}")
    print(f"  Output: {out_path}")

    try:
        df = (
            spark.read
            .format("org.apache.kudu.spark.kudu")
            .option("kudu.master", kudu_master)
            .option("kudu.table", kudu_table)
            .load()
        )

        row_count = df.count()
        result["row_count"] = row_count
        result["output_path"] = out_path
        print(f"  Rows  : {row_count:,}")

        if dry_run:
            result["status"] = "DRY_RUN"
            print(f"  DRY RUN — skipping write")
            return result

        if row_count == 0:
            df.write.mode("overwrite").parquet(out_path)
            result["status"] = "EMPTY"
            print(f"  Empty table — wrote empty Parquet marker")
            return result

        df.coalesce(1).write.mode("overwrite").parquet(out_path)
        result["status"] = "SUCCESS"
        result["duration_sec"] = round((datetime.now() - start).total_seconds(), 1)
        print(f"  SUCCESS — {row_count:,} rows in {result['duration_sec']}s")

    except Exception as e:
        result["status"] = "FAILED"
        result["error"] = str(e)
        result["duration_sec"] = round((datetime.now() - start).total_seconds(), 1)
        print(f"  FAILED: {e}")

    return result


def write_manifest(output_dir, timestamp, kudu_master, results):
    manifest = {
        "backup_timestamp": timestamp,
        "source_env": "SIT",
        "sit_kudu_master": kudu_master,
        "database": DATABASE,
        "tables": results,
        "created_at": datetime.now().isoformat(),
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest written: {manifest_path}")


def parse_args():
    p = argparse.ArgumentParser(
        description="Backup SIT Kudu tables to local Parquet (rollback safety net)"
    )
    p.add_argument("--kudu-master", required=True, help="SIT Kudu master (host:port)")
    p.add_argument("--output-dir", default="/tmp/sit_backup",
                   help="Local output directory (default: /tmp/sit_backup)")
    p.add_argument("--database", default=DATABASE,
                   help=f"Database name (default: {DATABASE})")
    p.add_argument("--tables", default=None,
                   help="Comma-separated tables to backup (default: all)")
    p.add_argument("--skip-tables", default=None,
                   help="Comma-separated tables to skip")
    p.add_argument("--dry-run", action="store_true",
                   help="Count rows only, no write")
    p.add_argument("--continue-on-error", action="store_true",
                   help="Continue even if a table fails")
    return p.parse_args()


def main():
    if not SPARK_AVAILABLE:
        print("ERROR: PySpark required.")
        sys.exit(1)

    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(args.output_dir, f"gmp_cis_sit_{timestamp}")

    tables = ALL_TABLES
    if args.tables:
        tables = [t.strip() for t in args.tables.split(",")]
    if args.skip_tables:
        skip = {t.strip() for t in args.skip_tables.split(",")}
        tables = [t for t in tables if t not in skip]

    print("=" * 60)
    print("  SIT Kudu → Local Backup (Rollback Safety Net)")
    print("=" * 60)
    print(f"  SIT Kudu master : {args.kudu_master}")
    print(f"  Output dir      : {output_dir}")
    print(f"  Tables          : {len(tables)}")
    print(f"  Dry run         : {args.dry_run}")
    print("=" * 60)

    if not args.dry_run:
        os.makedirs(output_dir, exist_ok=True)

    spark = (
        SparkSession.builder
        .appName(f"CIS_SIT_Backup_{timestamp}")
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
        # Kudu master (override per env via --kudu-master arg at runtime)
        .config("spark.kudu.master", args.kudu_master)
        # Legacy time parser for STRING date columns
        .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    results = []
    start_all = datetime.now()

    for table in tables:
        result = backup_table(
            spark=spark,
            kudu_master=args.kudu_master,
            database=args.database,
            table=table,
            output_dir=output_dir,
            dry_run=args.dry_run,
        )
        results.append(result)

        if result["status"] == "FAILED" and not args.continue_on_error:
            print(f"\nAborting — table {table} failed. Use --continue-on-error to skip.")
            break

    if not args.dry_run:
        write_manifest(output_dir, timestamp, args.kudu_master, results)

    total_sec = round((datetime.now() - start_all).total_seconds(), 1)
    success = [r for r in results if r["status"] == "SUCCESS"]
    failed  = [r for r in results if r["status"] == "FAILED"]
    total_rows = sum(r["row_count"] for r in success)

    print("\n\n" + "=" * 60)
    print("  BACKUP SUMMARY")
    print("=" * 60)
    print(f"  Output dir  : {output_dir}")
    print(f"  Success     : {len(success)}")
    print(f"  Failed      : {len(failed)}")
    print(f"  Total rows  : {total_rows:,}")
    print(f"  Total time  : {total_sec}s")
    print(f"\n  {'Table':<45} {'Status':<12} {'Rows':>10}")
    print(f"  {'-'*45} {'-'*12} {'-'*10}")
    for r in results:
        print(f"  {r['table']:<45} {r['status']:<12} {r['row_count']:>10,}")

    if failed:
        print("\n  FAILED TABLES:")
        for r in failed:
            print(f"    - {r['table']}: {r['error']}")

    if not args.dry_run:
        print(f"\n{'='*60}")
        print("  ROLLBACK INSTRUCTIONS (if migration fails):")
        print(f"{'='*60}")
        print(f"  1. Drop and recreate SIT schema:")
        print(f"     impala-shell -i <sit-host>:21050 -f sql/ddl/99_sit_clean_gmp_cis.sql")
        print(f"     impala-shell -i <sit-host>:21050 -f sql/ddl/00_all_kudu_tables_sit.sql")
        print(f"")
        print(f"  2. Restore this SIT backup:")
        print(f"     spark-submit --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \\")
        print(f"       restore_sit_from_local.py \\")
        print(f"       --kudu-master <sit-kudu-master>:7051 \\")
        print(f"       --backup-dir {output_dir}/")
        print("=" * 60)

    spark.stop()

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
