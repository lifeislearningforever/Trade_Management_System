#!/usr/bin/env python3
"""
UAT → SIT Full Data Migration using Spark + Kudu Connector

Reads every table from UAT Kudu, writes to SIT Kudu via UPSERT.
Runs table-by-table in dependency order so FK references are satisfied.

Usage:
    # Dry run (print row counts only, no writes)
    spark-submit --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \\
        migrate_uat_to_sit.py --dry-run

    # Migrate all tables
    spark-submit --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \\
        migrate_uat_to_sit.py \\
        --uat-master <uat-kudu-master>:7051 \\
        --sit-master <sit-kudu-master>:7051

    # Migrate specific tables only
    spark-submit --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \\
        migrate_uat_to_sit.py \\
        --uat-master <uat-kudu-master>:7051 \\
        --sit-master <sit-kudu-master>:7051 \\
        --tables cis_portfolio,cis_trade,cis_trade_history

    # Skip audit/queue tables (migrate master data only)
    spark-submit --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \\
        migrate_uat_to_sit.py \\
        --uat-master <uat-kudu-master>:7051 \\
        --sit-master <sit-kudu-master>:7051 \\
        --skip-tables cis_audit_log,cis_position_queue,cis_settlement_queue,cis_trade_event_queue

Author: CIS Trade Hive Team
Version: 1.0
Date: 2026-04-22
"""

import argparse
import sys
from datetime import datetime
from typing import List, Optional
import os

try:
    from pyspark.sql import SparkSession, DataFrame
    from pyspark.sql.functions import col
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False
    print("WARNING: PySpark not available.")


# ============================================================================
# TABLE LIST — in dependency order (reference data first, queues last)
# ============================================================================

ALL_TABLES = [
    # 1. Reference data
    "gmp_cis_sta_dly_currency",
    "gmp_cis_sta_dly_country",
    "gmp_cis_sta_dly_calendar",

    # 2. ACL / Users (v1)
    "cis_user",
    "cis_user_group",
    "cis_group",
    "cis_group_permissions",

    # 3. RBAC v2
    "cis_user_info",
    "cis_user_group_info",
    "cis_permission_info",
    "cis_user_group_mapping_info",
    "cis_group_permission_map",

    # 4. Counterparty
    "cis_counterparty_kudu",

    # 5. Security
    "cis_security",
    "cis_security_history",

    # 6. Market data
    "cis_equity_price_kudu",
    "cis_equity_price_history",
    "gmp_cis_sta_dly_fx_rates",

    # 7. UDF definitions
    "cis_udf_definition",
    "cis_udf_option",
    "cis_udf_field",

    # 8. Portfolio
    "cis_portfolio",
    "cis_portfolio_history",

    # 9. Trade
    "cis_trade",
    "cis_trade_history",
    "cis_trade_note",

    # 10. UDF values (depend on trade + portfolio)
    "cis_udf_value",
    "cis_udf_value_multi",

    # 11. Position / AVP
    "cis_trade_position",
    "cis_trade_lot",

    # 12. Corporate actions
    "cis_corporate_actions",
    "cis_corporate_actions_history",

    # 13. Cash flow
    "cis_cash_flow",
    "cis_cash_flow_history",

    # 14. Queues / processing
    "cis_ca_cash_flow_queue",
    "cis_ca_cash_flow_log",
    "cis_trade_event_queue",
    "cis_position_queue",
    "cis_settlement_queue",

    # 15. System / operational
    "cis_sequence",
    "cis_system_date",
    "cis_file_upload",

    # 16. Audit log (large — migrate last)
    "cis_audit_log",
]

# Tables to skip by default (transient/queue data not needed in SIT)
DEFAULT_SKIP = []

# Kudu table name format on Cloudera CML: <database>.<table> (no impala:: prefix)
DATABASE = os.environ.get('IMPALA_DB', 'gmp_cis')


# ============================================================================
# HELPERS
# ============================================================================

def kudu_table_name(table: str, database: str = DATABASE) -> str:
    """Returns the Kudu table name as seen by the Spark connector."""
    return f"{database}.{table}"


def read_kudu_table(spark: SparkSession, master: str, table: str) -> DataFrame:
    """Read a full table from a Kudu master."""
    return (
        spark.read
        .format("org.apache.kudu.spark.kudu")
        .option("kudu.master", master)
        .option("kudu.table", kudu_table_name(table))
        .load()
    )


def write_kudu_table(df: DataFrame, master: str, table: str) -> None:
    """Write (upsert) a DataFrame into a Kudu table on the target master."""
    (
        df.write
        .format("org.apache.kudu.spark.kudu")
        .option("kudu.master", master)
        .option("kudu.table", kudu_table_name(table))
        .option("kudu.operation", "upsert")      # safe: insert or update
        .option("kudu.ignoreDuplicateRowErrors", "false")
        .mode("append")
        .save()
    )


def migrate_table(
    spark: SparkSession,
    uat_master: str,
    sit_master: str,
    table: str,
    dry_run: bool = False,
    batch_size: int = 50000,
) -> dict:
    """Migrate one table from UAT to SIT. Returns a result summary dict."""
    result = {
        "table": table,
        "status": "SKIPPED",
        "row_count": 0,
        "error": None,
        "duration_sec": 0,
    }

    start = datetime.now()
    print(f"\n{'='*60}")
    print(f"  Table: {table}")
    print(f"  Started: {start.strftime('%H:%M:%S')}")

    try:
        # Read from UAT
        print(f"  Reading from UAT ({uat_master})...")
        df = read_kudu_table(spark, uat_master, table)

        row_count = df.count()
        result["row_count"] = row_count
        print(f"  Rows found: {row_count:,}")

        if row_count == 0:
            print(f"  SKIPPED (empty table)")
            result["status"] = "EMPTY"
            return result

        if dry_run:
            print(f"  DRY RUN — skipping write")
            result["status"] = "DRY_RUN"
            return result

        # Write to SIT in batches (repartition to control memory)
        num_partitions = max(1, row_count // batch_size)
        print(f"  Writing to SIT ({sit_master}) in {num_partitions} partition(s)...")
        write_kudu_table(df.repartition(num_partitions), sit_master, table)

        duration = (datetime.now() - start).total_seconds()
        result["status"] = "SUCCESS"
        result["duration_sec"] = round(duration, 1)
        print(f"  SUCCESS — {row_count:,} rows in {duration:.1f}s")

    except Exception as e:
        duration = (datetime.now() - start).total_seconds()
        result["status"] = "FAILED"
        result["error"] = str(e)
        result["duration_sec"] = round(duration, 1)
        print(f"  FAILED: {e}")

    return result


# ============================================================================
# MAIN
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Migrate all gmp_cis tables from UAT Kudu to SIT Kudu"
    )
    parser.add_argument(
        "--uat-master",
        default="uat-kudu-master:7051",
        help="UAT Kudu master address (host:port)"
    )
    parser.add_argument(
        "--sit-master",
        default="sit-kudu-master:7051",
        help="SIT Kudu master address (host:port)"
    )
    parser.add_argument(
        "--database",
        default=DATABASE,
        help=f"Kudu database name (default: {DATABASE})"
    )
    parser.add_argument(
        "--tables",
        default=None,
        help="Comma-separated list of tables to migrate (default: all)"
    )
    parser.add_argument(
        "--skip-tables",
        default=None,
        help="Comma-separated list of tables to skip"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read from UAT and print row counts only, no writes to SIT"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50000,
        help="Rows per Spark partition when writing (default: 50000)"
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue migrating remaining tables even if one fails"
    )
    return parser.parse_args()


def main():
    if not SPARK_AVAILABLE:
        print("ERROR: PySpark is required.")
        sys.exit(1)

    args = parse_args()

    # Build table list
    tables = ALL_TABLES
    if args.tables:
        tables = [t.strip() for t in args.tables.split(",")]
        print(f"Migrating specific tables: {tables}")

    skip = set(DEFAULT_SKIP)
    if args.skip_tables:
        skip.update(t.strip() for t in args.skip_tables.split(","))
    if skip:
        print(f"Skipping tables: {skip}")
        tables = [t for t in tables if t not in skip]

    print("\n" + "="*60)
    print("  CIS Trade Hive — UAT → SIT Migration")
    print("="*60)
    print(f"  UAT Kudu master : {args.uat_master}")
    print(f"  SIT Kudu master : {args.sit_master}")
    print(f"  Database        : {args.database}")
    print(f"  Tables          : {len(tables)}")
    print(f"  Dry run         : {args.dry_run}")
    print(f"  Continue on err : {args.continue_on_error}")
    print("="*60)

    # Spark session
    spark = (
        SparkSession.builder
        .appName("CIS_UAT_to_SIT_Migration")
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
        # Legacy time parser for STRING date columns
        .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # Run migration
    results = []
    start_all = datetime.now()

    for table in tables:
        result = migrate_table(
            spark=spark,
            uat_master=args.uat_master,
            sit_master=args.sit_master,
            table=table,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
        results.append(result)

        if result["status"] == "FAILED" and not args.continue_on_error:
            print(f"\nAborting migration due to failure on {table}.")
            print("Use --continue-on-error to skip failed tables.")
            break

    # Summary report
    total_duration = (datetime.now() - start_all).total_seconds()
    success  = [r for r in results if r["status"] == "SUCCESS"]
    failed   = [r for r in results if r["status"] == "FAILED"]
    empty    = [r for r in results if r["status"] == "EMPTY"]
    dry_runs = [r for r in results if r["status"] == "DRY_RUN"]
    total_rows = sum(r["row_count"] for r in success)

    print("\n\n" + "="*60)
    print("  MIGRATION SUMMARY")
    print("="*60)
    print(f"  Total tables    : {len(results)}")
    print(f"  Success         : {len(success)}")
    print(f"  Failed          : {len(failed)}")
    print(f"  Empty (skipped) : {len(empty)}")
    print(f"  Dry run         : {len(dry_runs)}")
    print(f"  Total rows      : {total_rows:,}")
    print(f"  Total time      : {total_duration:.1f}s")

    if failed:
        print("\n  FAILED TABLES:")
        for r in failed:
            print(f"    - {r['table']}: {r['error']}")

    print("\n  PER-TABLE RESULTS:")
    print(f"  {'Table':<45} {'Status':<12} {'Rows':>10} {'Sec':>6}")
    print(f"  {'-'*45} {'-'*12} {'-'*10} {'-'*6}")
    for r in results:
        print(f"  {r['table']:<45} {r['status']:<12} {r['row_count']:>10,} {r['duration_sec']:>6.1f}")

    print("="*60)

    spark.stop()

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
