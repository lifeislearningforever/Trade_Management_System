#!/usr/bin/env python3
"""
UAT Backup to Local/HDFS (for SCP/SFTP transfer to SIT)

Auto-discovers ALL tables in gmp_cis (Kudu + Hive internal + Hive external)
via Impala JDBC and backs each one up as Parquet.

- Kudu tables     → read via Kudu Spark connector
- Hive tables     → read via spark.sql()
- External tables → read via spark.sql()

After backup completes, the script automatically:
  1. Copies the HDFS output to local disk
  2. Creates a tar.gz ready for SFTP/SCP

Flow:
    Impala SHOW TABLES → detect type → Spark read → HDFS Parquet
                       → hdfs dfs -get → tar.gz → ready for SCP

Usage:
    # Backup all tables (auto-discovered)
    spark-submit \\
        --master yarn --deploy-mode client \\
        --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \\
        backup_uat_to_local.py \\
        --kudu-master <uat-kudu-master>:7051 \\
        --impala-host <uat-impala-host> \\
        --output-dir /tmp/uat_backup

    # Dry run (discover + count rows, no write)
    spark-submit ... backup_uat_to_local.py \\
        --kudu-master <uat-kudu-master>:7051 \\
        --impala-host <uat-impala-host> \\
        --dry-run

Author: CIS Trade Hive Team
Version: 2.0
Date: 2026-04-22
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import List, Dict, Tuple

try:
    from pyspark.sql import SparkSession, DataFrame
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False
    print("WARNING: PySpark not available.")

DATABASE = "gmp_cis"

TYPE_KUDU     = "KUDU"
TYPE_HIVE     = "HIVE"
TYPE_EXTERNAL = "EXTERNAL"
TYPE_UNKNOWN  = "UNKNOWN"


# ============================================================================
# TABLE DISCOVERY
# ============================================================================

def discover_tables(spark: SparkSession, database: str, impala_host: str, impala_port: int) -> List[Dict]:
    """
    Auto-discover all tables in the database via Impala JDBC / spark.sql().
    Returns list of dicts: {name, type, location}
    """
    print(f"\n  Discovering tables in {database} via Impala ({impala_host}:{impala_port})...")

    jdbc_url = f"jdbc:impala://{impala_host}:{impala_port}/{database}"

    try:
        tables_df = (
            spark.read
            .format("jdbc")
            .option("url", jdbc_url)
            .option("query", f"SHOW TABLES IN {database}")
            .option("driver", "com.cloudera.impala.jdbc.Driver")
            .load()
        )
        table_names = [row[0] for row in tables_df.collect()]
        print(f"  Found {len(table_names)} tables via JDBC")
    except Exception as e:
        print(f"  WARNING: JDBC discovery failed ({e}), falling back to spark.sql()")
        spark.sql(f"USE {database}")
        tables_df = spark.sql(f"SHOW TABLES IN {database}")
        table_names = [row.tableName for row in tables_df.collect()]
        print(f"  Found {len(table_names)} tables via spark.sql()")

    tables = []
    for name in sorted(table_names):
        table_type, location = detect_table_type(spark, database, name)
        tables.append({"name": name, "type": table_type, "location": location})
        print(f"    {name:<50} [{table_type}]")

    return tables


def detect_table_type(spark: SparkSession, database: str, table: str) -> Tuple[str, str]:
    """Detect Kudu / Hive internal / Hive external via DESCRIBE FORMATTED."""
    try:
        desc_df = spark.sql(f"DESCRIBE FORMATTED {database}.{table}")
        rows = {row[0].strip(): (row[1].strip() if row[1] else "") for row in desc_df.collect()}

        table_type_raw  = rows.get("Table Type", "").upper()
        storage_handler = rows.get("Storage Handler", "").lower()
        location        = rows.get("Location", "")

        if "kudu" in storage_handler:
            return TYPE_KUDU, location
        elif "external" in table_type_raw:
            return TYPE_EXTERNAL, location
        else:
            return TYPE_HIVE, location

    except Exception as e:
        print(f"    WARNING: Could not describe {table}: {e}")
        return TYPE_UNKNOWN, ""


# ============================================================================
# BACKUP
# ============================================================================

def backup_table(
    spark: SparkSession,
    kudu_master: str,
    database: str,
    table_info: Dict,
    output_dir: str,
    dry_run: bool = False,
) -> Dict:
    """Backup one table to Parquet — Kudu connector for Kudu, spark.sql() for Hive/External."""
    table  = table_info["name"]
    ttype  = table_info["type"]
    result = {
        "table": table,
        "type": ttype,
        "status": "PENDING",
        "row_count": 0,
        "output_path": "",
        "error": None,
        "duration_sec": 0,
    }
    start    = datetime.now()
    out_path = os.path.join(output_dir, table)

    print(f"\n{'='*60}")
    print(f"  Table : {table}  [{ttype}]")
    print(f"  Output: {out_path}")

    try:
        if ttype == TYPE_KUDU:
            df = (
                spark.read
                .format("org.apache.kudu.spark.kudu")
                .option("kudu.master", kudu_master)
                .option("kudu.table", f"{database}.{table}")
                .load()
            )
        else:
            df = spark.sql(f"SELECT * FROM {database}.{table}")

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
        err = str(e)
        result["duration_sec"] = round((datetime.now() - start).total_seconds(), 1)
        if "does not exist" in err.lower() or "table not found" in err.lower() or "nosuchentityexception" in err.lower():
            result["status"] = "NOT_FOUND"
            result["error"] = f"Table not found: {database}.{table}"
            print(f"  NOT FOUND — skipping")
        else:
            result["status"] = "FAILED"
            result["error"] = err
            print(f"  FAILED: {err}")

    return result


# ============================================================================
# HDFS → LOCAL + ZIP
# ============================================================================

def copy_hdfs_to_local_and_zip(hdfs_path: str, local_base: str, timestamp: str) -> str:
    """
    Copy backup from HDFS to local disk and create tar.gz.
    Returns path to the tar.gz file.
    """
    folder_name = f"gmp_cis_{timestamp}"
    local_path  = os.path.join(local_base, folder_name)
    tar_path    = os.path.join(local_base, f"{folder_name}.tar.gz")

    print(f"\n{'='*60}")
    print(f"  Copying HDFS → local disk")
    print(f"  HDFS : {hdfs_path}")
    print(f"  Local: {local_path}")

    # hdfs dfs -get
    os.makedirs(local_base, exist_ok=True)
    ret = subprocess.call(["hdfs", "dfs", "-get", hdfs_path, local_path])
    if ret != 0:
        print(f"  ERROR: hdfs dfs -get failed (exit {ret})")
        return ""

    print(f"  Zipping → {tar_path}")
    ret = subprocess.call(
        ["tar", "-czf", tar_path, "-C", local_base, folder_name]
    )
    if ret != 0:
        print(f"  ERROR: tar failed (exit {ret})")
        return ""

    size = subprocess.check_output(["du", "-sh", tar_path]).decode().split()[0]
    print(f"  Done  : {tar_path}  ({size})")
    return tar_path


# ============================================================================
# MANIFEST
# ============================================================================

def write_manifest(output_dir, timestamp, kudu_master, database, results):
    manifest = {
        "backup_timestamp": timestamp,
        "source_env": "UAT",
        "uat_kudu_master": kudu_master,
        "database": database,
        "tables": results,
        "created_at": datetime.now().isoformat(),
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest written: {manifest_path}")


# ============================================================================
# ARGS
# ============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="Backup ALL tables in gmp_cis (Kudu + Hive) to Parquet, then zip for SCP"
    )
    p.add_argument("--kudu-master",    required=True, help="UAT Kudu master (host:port)")
    p.add_argument("--impala-host",    required=True, help="UAT Impala host for table discovery")
    p.add_argument("--impala-port",    type=int, default=21050, help="Impala port (default: 21050)")
    p.add_argument("--database",       default=DATABASE, help=f"Database to backup (default: {DATABASE})")
    p.add_argument("--output-dir",     default="/tmp/uat_backup",
                   help="HDFS output directory for Parquet files (default: /tmp/uat_backup)")
    p.add_argument("--local-dir",      default="/tmp/uat_backup_local",
                   help="Local dir to copy HDFS backup into + create tar.gz (default: /tmp/uat_backup_local)")
    p.add_argument("--skip-tables",    default=None, help="Comma-separated tables to skip")
    p.add_argument("--dry-run",        action="store_true", help="Discover + count rows, no write")
    p.add_argument("--no-zip",         action="store_true",
                   help="Skip HDFS→local copy and tar.gz step (keep Parquet on HDFS only)")
    return p.parse_args()


# ============================================================================
# MAIN
# ============================================================================

def main():
    if not SPARK_AVAILABLE:
        print("ERROR: PySpark required.")
        sys.exit(1)

    args      = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hdfs_output_dir = os.path.join(args.output_dir, f"gmp_cis_{timestamp}")

    print("=" * 60)
    print("  UAT Kudu + Hive → Parquet Backup")
    print("=" * 60)
    print(f"  UAT Kudu master : {args.kudu_master}")
    print(f"  Impala host     : {args.impala_host}:{args.impala_port}")
    print(f"  Database        : {args.database}")
    print(f"  HDFS output dir : {hdfs_output_dir}")
    print(f"  Local dir       : {args.local_dir}")
    print(f"  Dry run         : {args.dry_run}")
    print(f"  Auto zip        : {not args.no_zip}")
    print("=" * 60)

    spark = (
        SparkSession.builder
        .appName(f"CIS_UAT_Backup_{timestamp}")
        .master("yarn")
        .config("spark.submit.deployMode", "client")
        .config("spark.sql.crossJoin.enabled", "true")
        .config("spark.rpc.askTimeout", "300")
        .config("spark.network.timeout", "600")
        .config("spark.sql.extensions",
                "com.qubole.spark.hiveacid.HiveAcidAutoConvertExtension")
        .config("spark.sql.hive.hwc.execution.mode", "spark")
        .config("spark.datasource.hive.warehouse.read.jdbc.mode", "cluster")
        .config("spark.hadoop.hive.exec.dynamic.partition.mode", "nonstrict")
        .config("spark.kryo.registrator",
                "com.qubole.spark.hiveacid.util.HiveAcidKryoRegistrator")
        .config("spark.kudu.master", args.kudu_master)
        .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
        .enableHiveSupport()
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # Auto-discover all tables
    all_tables = discover_tables(spark, args.database, args.impala_host, args.impala_port)

    skip = set()
    if args.skip_tables:
        skip = {t.strip() for t in args.skip_tables.split(",")}
    tables = [t for t in all_tables if t["name"] not in skip]

    if skip:
        print(f"\n  Skipping {len(skip)} table(s): {', '.join(skip)}")

    print(f"\n  Backing up {len(tables)} tables "
          f"({sum(1 for t in tables if t['type']==TYPE_KUDU)} Kudu, "
          f"{sum(1 for t in tables if t['type']==TYPE_HIVE)} Hive, "
          f"{sum(1 for t in tables if t['type']==TYPE_EXTERNAL)} External)")

    results   = []
    start_all = datetime.now()

    for table_info in tables:
        result = backup_table(
            spark=spark,
            kudu_master=args.kudu_master,
            database=args.database,
            table_info=table_info,
            output_dir=hdfs_output_dir,
            dry_run=args.dry_run,
        )
        results.append(result)
        # Always continue — never abort mid-loop

    if not args.dry_run:
        write_manifest(hdfs_output_dir, timestamp, args.kudu_master, args.database, results)

    total_sec  = round((datetime.now() - start_all).total_seconds(), 1)
    success    = [r for r in results if r["status"] == "SUCCESS"]
    failed     = [r for r in results if r["status"] == "FAILED"]
    not_found  = [r for r in results if r["status"] == "NOT_FOUND"]
    empty      = [r for r in results if r["status"] == "EMPTY"]
    total_rows = sum(r["row_count"] for r in success)

    print("\n\n" + "=" * 60)
    print("  BACKUP SUMMARY")
    print("=" * 60)
    print(f"  HDFS output : {hdfs_output_dir}")
    print(f"  Total       : {len(results)}")
    print(f"  Success     : {len(success)}")
    print(f"  Failed      : {len(failed)}")
    print(f"  Not found   : {len(not_found)}")
    print(f"  Empty       : {len(empty)}")
    print(f"  Total rows  : {total_rows:,}")
    print(f"  Total time  : {total_sec}s")
    print(f"\n  {'Table':<45} {'Type':<10} {'Status':<12} {'Rows':>10}")
    print(f"  {'-'*45} {'-'*10} {'-'*12} {'-'*10}")
    for r in results:
        print(f"  {r['table']:<45} {r['type']:<10} {r['status']:<12} {r['row_count']:>10,}")

    if not_found:
        print(f"\n  NOT FOUND:")
        for r in not_found:
            print(f"    - {r['table']}: {r['error']}")

    if failed:
        print(f"\n  FAILED:")
        for r in failed:
            print(f"    - {r['table']}: {r['error']}")

    spark.stop()

    # ---- HDFS → local + zip (auto, unless --no-zip) ----
    tar_path = ""
    if not args.dry_run and not args.no_zip:
        tar_path = copy_hdfs_to_local_and_zip(
            hdfs_path=hdfs_output_dir,
            local_base=args.local_dir,
            timestamp=timestamp,
        )

    print(f"\n{'='*60}")
    print("  NEXT STEPS — Transfer to SIT:")
    print(f"{'='*60}")
    if tar_path:
        print(f"  tar.gz ready : {tar_path}")
        print(f"")
        print(f"  SCP to SIT:")
        print(f"    scp {tar_path} <user>@<sit-host>:/tmp/")
        print(f"")
        print(f"  On SIT — extract, push to HDFS, restore:")
        print(f"    tar -xzf /tmp/gmp_cis_{timestamp}.tar.gz -C /tmp/")
        print(f"    hdfs dfs -put /tmp/gmp_cis_{timestamp}/ /tmp/restore/")
        print(f"    spark-submit ... restore_sit_from_local.py \\")
        print(f"      --kudu-master <sit-kudu>:7051 \\")
        print(f"      --backup-dir hdfs:///tmp/restore/gmp_cis_{timestamp}/")
    else:
        print(f"  HDFS path : {hdfs_output_dir}")
        print(f"  Run manually:")
        print(f"    hdfs dfs -get {hdfs_output_dir} /tmp/gmp_cis_{timestamp}/")
        print(f"    tar -czf /tmp/gmp_cis_{timestamp}.tar.gz -C /tmp gmp_cis_{timestamp}/")
        print(f"    scp /tmp/gmp_cis_{timestamp}.tar.gz <user>@<sit-host>:/tmp/")
    print("=" * 60)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
