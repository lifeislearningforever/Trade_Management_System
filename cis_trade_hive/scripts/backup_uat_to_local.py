#!/usr/bin/env python3
"""
UAT Backup to Local Disk (for SCP/SFTP transfer to SIT)

Reads all gmp_cis tables from UAT Kudu and saves each table as
Parquet files on the local filesystem. The output directory is then
zipped and transferred to SIT via SCP/SFTP.

Flow:
    UAT Kudu  →  Spark  →  Local Parquet files  →  ZIP  →  SCP to SIT

Usage:
    # Backup all tables to /tmp/uat_backup/
    spark-submit \\
        --master yarn --deploy-mode client \\
        --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \\
        backup_uat_to_local.py \\
        --kudu-master <uat-kudu-master>:7051 \\
        --output-dir /tmp/uat_backup

    # Backup specific tables
    spark-submit \\
        --master yarn --deploy-mode client \\
        --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \\
        backup_uat_to_local.py \\
        --kudu-master <uat-kudu-master>:7051 \\
        --output-dir /tmp/uat_backup \\
        --tables cis_portfolio,cis_trade,cis_trade_history

    # Dry run (print row counts, no write)
    spark-submit \\
        --master yarn --deploy-mode client \\
        --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \\
        backup_uat_to_local.py \\
        --kudu-master <uat-kudu-master>:7051 \\
        --output-dir /tmp/uat_backup \\
        --dry-run

After this script completes, zip and transfer:
    tar -czf uat_backup_<timestamp>.tar.gz /tmp/uat_backup/
    scp uat_backup_<timestamp>.tar.gz <sit-user>@<sit-host>:/tmp/

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
# TABLE LIST — dependency order (reference data first, queues/audit last)
# ============================================================================
ALL_TABLES = [
    # Reference data
    "gmp_cis_sta_dly_currency",
    "gmp_cis_sta_dly_country",
    "gmp_cis_sta_dly_calendar",
    # ACL v1
    "cis_user",
    "cis_user_group",
    "cis_group",
    "cis_group_permissions",
    # RBAC v2
    "cis_user_info",
    "cis_user_group_info",
    "cis_permission_info",
    "cis_user_group_mapping_info",
    "cis_group_permission_map",
    # Counterparty
    "cis_counterparty_kudu",
    # Security
    "cis_security",
    "cis_security_history",
    # Market data
    "cis_equity_price_kudu",
    "cis_equity_price_history",
    "gmp_cis_sta_dly_fx_rates",
    # UDF definitions
    "cis_udf_definition",
    "cis_udf_option",
    "cis_udf_field",
    # Portfolio
    "cis_portfolio",
    "cis_portfolio_history",
    # Trade
    "cis_trade",
    "cis_trade_history",
    "cis_trade_note",
    # UDF values
    "cis_udf_value",
    "cis_udf_value_multi",
    # Position / AVP
    "cis_trade_position",
    "cis_trade_lot",
    # Corporate actions
    "cis_corporate_actions",
    "cis_corporate_actions_history",
    # Cash flow
    "cis_cash_flow",
    "cis_cash_flow_history",
    # Queues
    "cis_ca_cash_flow_queue",
    "cis_ca_cash_flow_log",
    "cis_trade_event_queue",
    "cis_position_queue",
    "cis_settlement_queue",
    # System / operational
    "cis_sequence",
    "cis_system_date",
    "cis_file_upload",
    # Audit log (large — last)
    "cis_audit_log",
]

DATABASE = "gmp_cis"


def backup_table(spark, kudu_master, database, table, output_dir, dry_run=False):
    """Backup one table to local Parquet. Returns result dict."""
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
            # Write empty parquet so restore script knows table exists
            df.write.mode("overwrite").parquet(out_path)
            result["status"] = "EMPTY"
            print(f"  Empty table — wrote empty Parquet marker")
            return result

        # Write as single-file Parquet (coalesce for easier SCP transfer)
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
    """Write a manifest JSON so restore script knows what to load."""
    manifest = {
        "backup_timestamp": timestamp,
        "uat_kudu_master": kudu_master,
        "database": DATABASE,
        "tables": results,
        "created_at": datetime.now().isoformat(),
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest written: {manifest_path}")


def parse_args():
    p = argparse.ArgumentParser(description="Backup UAT Kudu tables to local Parquet for SCP transfer")
    p.add_argument("--kudu-master", required=True, help="UAT Kudu master (host:port)")
    p.add_argument("--output-dir", default="/tmp/uat_backup", help="Local output directory (default: /tmp/uat_backup)")
    p.add_argument("--database", default=DATABASE, help=f"Database name (default: {DATABASE})")
    p.add_argument("--tables", default=None, help="Comma-separated tables to backup (default: all)")
    p.add_argument("--skip-tables", default=None, help="Comma-separated tables to skip")
    p.add_argument("--dry-run", action="store_true", help="Count rows only, no write")
    p.add_argument("--continue-on-error", action="store_true", help="Continue even if a table fails")
    return p.parse_args()


def main():
    if not SPARK_AVAILABLE:
        print("ERROR: PySpark required.")
        sys.exit(1)

    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(args.output_dir, f"gmp_cis_{timestamp}")

    # Build table list
    tables = ALL_TABLES
    if args.tables:
        tables = [t.strip() for t in args.tables.split(",")]
    if args.skip_tables:
        skip = {t.strip() for t in args.skip_tables.split(",")}
        tables = [t for t in tables if t not in skip]

    print("=" * 60)
    print("  UAT → Local Backup (for SCP to SIT)")
    print("=" * 60)
    print(f"  UAT Kudu master : {args.kudu_master}")
    print(f"  Output dir      : {output_dir}")
    print(f"  Tables          : {len(tables)}")
    print(f"  Dry run         : {args.dry_run}")
    print("=" * 60)

    if not args.dry_run:
        os.makedirs(output_dir, exist_ok=True)

    spark = (
        SparkSession.builder
        .appName(f"CIS_UAT_Backup_{timestamp}")
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
        print("  NEXT STEPS — Transfer to SIT:")
        print(f"{'='*60}")
        print(f"  1. Zip the backup:")
        print(f"     tar -czf gmp_cis_{timestamp}.tar.gz -C {args.output_dir} gmp_cis_{timestamp}/")
        print(f"")
        print(f"  2. SCP to SIT:")
        print(f"     scp gmp_cis_{timestamp}.tar.gz <sit-user>@<sit-host>:/tmp/")
        print(f"")
        print(f"  3. On SIT server, extract and restore:")
        print(f"     tar -xzf /tmp/gmp_cis_{timestamp}.tar.gz -C /tmp/")
        print(f"     spark-submit restore_sit_from_local.py \\")
        print(f"       --kudu-master <sit-kudu-master>:7051 \\")
        print(f"       --backup-dir /tmp/gmp_cis_{timestamp}/")
        print("=" * 60)

    spark.stop()

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
