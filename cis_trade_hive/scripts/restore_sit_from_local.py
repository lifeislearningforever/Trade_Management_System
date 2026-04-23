#!/usr/bin/env python3
"""
Restore SIT from UAT Backup (received via SCP/SFTP)

Two-pass restore strategy — mirrors the two-pass backup:
  Pass 1 — Kudu tables    → Spark reads Parquet → UPSERT into SIT Kudu
  Pass 2 — Hive external  → Beeline repairs partition metadata pointing at
                             the Parquet that already lives in the backup dir
                             (no data copy needed — data is already on HDFS)

WHY TWO PASSES?
  Kudu tables need the Kudu Spark connector to write.
  Hive external tables already have their data in the backup HDFS directory.
  Beeline just needs to:
    1. DROP the old external table metadata (data stays in HDFS)
    2. CREATE EXTERNAL TABLE ... LOCATION '<backup_parquet_dir>'
    3. MSCK REPAIR TABLE to register partitions (if partitioned)
  That is all — no data movement needed for Hive external tables.

Flow:
    tar.gz  →  extract  →  hdfs dfs -put  →  HDFS backup dir
                                │
                    ┌───────────┴───────────┐
                    │                       │
              [Kudu tables]         [Hive external tables]
              spark-submit           beeline -f HQL
              UPSERT → SIT Kudu     CREATE EXTERNAL TABLE
                                    LOCATION '<hdfs_backup_dir>/<table>'
                                    MSCK REPAIR TABLE

Pre-requisites:
  - SIT gmp_cis schema must exist (Kudu tables created):
      impala-shell -i <sit-impala>:21050 -f sql/ddl/00_all_kudu_tables.sql
  - Hive external table DDL must exist on SIT metastore:
      beeline -u ... -f sql/ddl/25_position_upload_standardized.sql
  - Backup extracted and pushed to HDFS:
      tar -xzf gmp_cis_<ts>.tar.gz -C /tmp/
      hdfs dfs -put /tmp/gmp_cis_<ts>/ /tmp/restore/

Usage:
    python restore_sit_from_local.py \\
        --kudu-master  <sit-kudu>:7051 \\
        --impala-host  <sit-impala-host> \\
        --beeline-url  "jdbc:hive2://<sit-hs2>:10000/gmp_cis;principal=hive/_HOST@REALM" \\
        --backup-dir   hdfs:///tmp/restore/gmp_cis_20260423_120000

    # Dry run (no writes)
    python restore_sit_from_local.py ... --dry-run

    # Specific tables only
    python restore_sit_from_local.py ... --tables cis_portfolio,cis_trade

    # Kudu pass only
    python restore_sit_from_local.py ... --skip-hive

    # Hive pass only (data already in HDFS, just fix metadata)
    python restore_sit_from_local.py ... --skip-kudu

Author: CIS Trade Hive Team
Version: 2.0
Date: 2026-04-23
"""

import argparse
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime
from typing import List, Dict, Optional, Tuple

try:
    from pyspark.sql import SparkSession
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False

try:
    from impala.dbapi import connect as impala_connect
    IMPYLA_AVAILABLE = True
except ImportError:
    IMPYLA_AVAILABLE = False

DATABASE = "gmp_cis"

TYPE_KUDU     = "KUDU"
TYPE_EXTERNAL = "EXTERNAL"
TYPE_HIVE     = "HIVE"
TYPE_UNKNOWN  = "UNKNOWN"

# Restore order — FK dependencies: reference data first, transactions last
RESTORE_ORDER = [
    # Reference / lookup tables
    "gmp_cis_sta_dly_currency",
    "gmp_cis_sta_dly_country",
    "gmp_cis_sta_dly_calendar",
    "gmp_cis_sta_dly_fx_rates",
    # Users / ACL
    "cis_user",
    "cis_user_group",
    "cis_group",
    "cis_group_permissions",
    "cis_user_info",
    "cis_user_group_info",
    "cis_permission_info",
    "cis_user_group_mapping_info",
    "cis_group_permission_map",
    # Masters
    "cis_counterparty_kudu",
    "cis_security_kudu",
    "cis_security_history",
    "cis_equity_price",
    "cis_equity_price_history",
    # UDF
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
    "cis_udf_value",
    "cis_udf_value_multi",
    # Position / settlement
    "cis_trade_position",
    "cis_trade_lot",
    "cis_position",
    "cis_position_queue",
    "cis_settlement_queue",
    # Corporate actions
    "cis_corporate_actions",
    "cis_corporate_actions_history",
    "cis_cash_flow",
    "cis_cash_flow_history",
    "cis_ca_cash_flow_queue",
    "cis_ca_cash_flow_log",
    "cis_trade_event_queue",
    # System
    "cis_sequence",
    "cis_system_date",
    "cis_audit_log",
    "cis_file_upload",
    "cis_upload_mng",
    "cis_datasource_mng",
    # Hive external (position upload pipeline)
    "cis_user_sta_adhoc_position_1",
    "cis_user_sta_adhoc_position_2",
    "cis_user_sta_adhoc_position_3",
    "cis_user_sta_adhoc_position_4",
    "cis_user_sta_adhoc_position_5",
    "position_upload_standardized",
    "position_upload_report",
]


# ============================================================================
# HELPERS — path, HDFS, manifest
# ============================================================================

def is_hdfs(path: str) -> bool:
    return path.startswith("hdfs://") or path.startswith("webhdfs://")


def pjoin(base: str, name: str) -> str:
    return base.rstrip("/") + "/" + name


def hdfs_exists(path: str) -> bool:
    try:
        ret = subprocess.call(
            ["hdfs", "dfs", "-test", "-e", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return ret == 0
    except Exception:
        return False


def hdfs_ls_dirs(path: str) -> List[str]:
    """Return directory names directly under an HDFS path."""
    try:
        out = subprocess.check_output(
            ["hdfs", "dfs", "-ls", path], stderr=subprocess.DEVNULL
        ).decode()
        dirs = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 8 and parts[0].startswith("d"):
                dirs.append(parts[-1].rstrip("/").split("/")[-1])
        return dirs
    except Exception:
        return []


def local_ls_dirs(path: str) -> List[str]:
    try:
        return [d for d in os.listdir(path)
                if os.path.isdir(os.path.join(path, d))]
    except Exception:
        return []


def read_manifest(backup_dir: str) -> Optional[Dict]:
    manifest_path = pjoin(backup_dir, "manifest.json")
    try:
        if is_hdfs(backup_dir):
            out = subprocess.check_output(
                ["hdfs", "dfs", "-cat", manifest_path],
                stderr=subprocess.DEVNULL
            ).decode()
            return json.loads(out)
        else:
            if os.path.exists(manifest_path):
                with open(manifest_path) as f:
                    return json.load(f)
    except Exception as e:
        print(f"  WARNING: Could not read manifest: {e}")
    return None


# ============================================================================
# TABLE CLASSIFICATION  (read manifest or probe Impala)
# ============================================================================

def classify_tables_from_manifest(manifest: Dict) -> Dict[str, str]:
    """
    Extract {table_name: type} from the backup manifest (written by backup script v3).
    Falls back to TYPE_UNKNOWN for older manifests that didn't record type.
    """
    mapping = {}
    for entry in manifest.get("tables", []):
        name  = entry.get("table", "")
        ttype = entry.get("type", TYPE_UNKNOWN)
        if name:
            mapping[name] = ttype
    return mapping


def classify_tables_impala(
    impala_host: str, impala_port: int, database: str, table_names: List[str]
) -> Dict[str, str]:
    """
    Classify each table by querying SIT Impala with DESCRIBE FORMATTED.
    Used when manifest doesn't have type info.
    """
    if not IMPYLA_AVAILABLE:
        print("  WARNING: impyla not installed — all tables classified as UNKNOWN")
        return {t: TYPE_UNKNOWN for t in table_names}

    mapping = {}
    try:
        conn   = impala_connect(host=impala_host, port=impala_port,
                                database=database, auth_mechanism="NOSASL")
        cursor = conn.cursor()
        for table in table_names:
            try:
                cursor.execute(f"DESCRIBE FORMATTED {database}.{table}")
                rows = cursor.fetchall()
                kv   = {(r[0] or "").strip(): (r[1] or "").strip() for r in rows}
                sh   = kv.get("Storage Handler", "").lower()
                tt   = kv.get("Table Type", "").upper()
                if "kudu" in sh:
                    mapping[table] = TYPE_KUDU
                elif "external" in tt:
                    mapping[table] = TYPE_EXTERNAL
                else:
                    mapping[table] = TYPE_HIVE
            except Exception:
                mapping[table] = TYPE_UNKNOWN
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"  WARNING: Impala classification failed: {e}")
        mapping = {t: TYPE_UNKNOWN for t in table_names}

    return mapping


def discover_tables(backup_dir: str) -> List[str]:
    """List all table directories in the backup, in RESTORE_ORDER."""
    if is_hdfs(backup_dir):
        available = set(hdfs_ls_dirs(backup_dir))
    else:
        available = set(local_ls_dirs(backup_dir))

    # Remove manifest file from set
    available.discard("manifest.json")

    ordered = [t for t in RESTORE_ORDER if t in available]
    extras  = sorted(t for t in available if t not in RESTORE_ORDER)
    return ordered + extras


# ============================================================================
# PASS 1 — KUDU RESTORE  (Spark UPSERT)
# ============================================================================

def restore_kudu_tables(
    kudu_master: str,
    database: str,
    tables: List[str],
    backup_dir: str,
    spark_jars: str,
    dry_run: bool,
) -> List[Dict]:
    if not tables:
        print("\n  [Kudu pass] No Kudu tables to restore — skipping")
        return []

    print(f"\n{'='*60}")
    print(f"  [Kudu pass] Restoring {len(tables)} Kudu tables via Spark")
    print(f"{'='*60}")

    results = []
    for table in tables:
        result = _restore_kudu_one(
            kudu_master=kudu_master,
            database=database,
            table=table,
            backup_dir=backup_dir,
            spark_jars=spark_jars,
            dry_run=dry_run,
        )
        results.append(result)
    return results


def _restore_kudu_one(
    kudu_master: str,
    database: str,
    table: str,
    backup_dir: str,
    spark_jars: str,
    dry_run: bool,
) -> Dict:
    parquet_path = pjoin(backup_dir, table)
    start  = datetime.now()
    result = {
        "table": table, "type": TYPE_KUDU,
        "status": "PENDING", "row_count": 0,
        "error": None, "duration_sec": 0,
    }

    print(f"\n  {table}")
    print(f"  Source: {parquet_path}")

    # Check backup exists
    exists = hdfs_exists(parquet_path) if is_hdfs(backup_dir) else os.path.exists(parquet_path)
    if not exists:
        result["status"] = "NOT_FOUND"
        result["error"]  = f"No backup at {parquet_path}"
        print(f"  NOT FOUND — skipping")
        return result

    if dry_run:
        result["status"] = "DRY_RUN"
        print(f"  DRY RUN — skipping")
        return result

    pyspark_code = textwrap.dedent(f"""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.appName("restore_{table}").getOrCreate()
        spark.sparkContext.setLogLevel("WARN")
        df = spark.read.parquet("{parquet_path}")
        count = df.count()
        print(f"ROWS:{{count}}")
        if count > 0:
            (df.write
               .format("org.apache.kudu.spark.kudu")
               .option("kudu.master", "{kudu_master}")
               .option("kudu.table", "{database}.{table}")
               .option("kudu.operation", "upsert")
               .mode("append")
               .save())
        spark.stop()
    """).strip()

    tmp_script = f"/tmp/restore_kudu_{table}_{datetime.now().strftime('%H%M%S')}.py"
    with open(tmp_script, "w") as f:
        f.write(pyspark_code)

    cmd = ["spark-submit", "--master", "yarn", "--deploy-mode", "client"]
    if spark_jars:
        cmd += ["--jars", spark_jars]
    cmd.append(tmp_script)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        os.remove(tmp_script)

        if proc.returncode != 0:
            result["status"] = "FAILED"
            result["error"]  = proc.stderr[-2000:] if proc.stderr else "spark-submit failed"
            print(f"  FAILED: {result['error'][-200:]}")
        else:
            row_count = 0
            for line in proc.stdout.splitlines():
                if line.startswith("ROWS:"):
                    row_count = int(line.split(":")[1])
            result["status"]      = "SUCCESS"
            result["row_count"]   = row_count
            result["duration_sec"] = round((datetime.now() - start).total_seconds(), 1)
            print(f"  SUCCESS — {row_count:,} rows in {result['duration_sec']}s")

    except subprocess.TimeoutExpired:
        result["status"] = "FAILED"
        result["error"]  = "spark-submit timed out (600s)"
        print(f"  FAILED: timeout")
    except Exception as e:
        result["status"] = "FAILED"
        result["error"]  = str(e)
        print(f"  FAILED: {e}")

    return result


# ============================================================================
# PASS 2 — HIVE EXTERNAL RESTORE  (Beeline — metadata repair only)
# ============================================================================

def restore_hive_external_tables(
    beeline_url: str,
    database: str,
    tables: List[str],
    backup_dir: str,
    beeline_extra_args: str,
    dry_run: bool,
) -> List[Dict]:
    """
    Restore Hive external tables.

    The Parquet data already exists in the backup HDFS directory — the backup
    script wrote it there.  We do NOT move data.  We just:
      1. DROP TABLE IF EXISTS <table>  (removes stale metadata)
      2. CREATE EXTERNAL TABLE <table>
             LIKE gmp_cis.<table>          -- copies schema from existing DDL
             STORED AS PARQUET
             LOCATION '<backup_parquet_dir>'
         OR — if the table doesn't exist on SIT yet — CREATE it from scratch
         using the backup Parquet schema.
      3. MSCK REPAIR TABLE <table>         -- registers partitions

    The table's LOCATION now points directly at the backup Parquet files,
    so queries immediately return the UAT data.

    If you later want the data at a canonical HDFS path, run:
      ALTER TABLE <table> SET LOCATION '/data/gmp_cis/<table>';
      MSCK REPAIR TABLE <table>;
    """
    if not tables:
        print("\n  [Hive pass] No Hive external tables to restore — skipping")
        return []

    print(f"\n{'='*60}")
    print(f"  [Hive pass] Restoring {len(tables)} Hive external tables via Beeline")
    print(f"  Strategy: point LOCATION at backup dir (no data copy)")
    print(f"  Beeline URL: {beeline_url}")
    print(f"{'='*60}")

    results = []
    for table in tables:
        result = _restore_hive_one(
            beeline_url=beeline_url,
            database=database,
            table=table,
            backup_dir=backup_dir,
            beeline_extra_args=beeline_extra_args,
            dry_run=dry_run,
        )
        results.append(result)
    return results


def _restore_hive_one(
    beeline_url: str,
    database: str,
    table: str,
    backup_dir: str,
    beeline_extra_args: str,
    dry_run: bool,
) -> Dict:
    parquet_path = pjoin(backup_dir, table)
    start  = datetime.now()
    result = {
        "table": table, "type": TYPE_EXTERNAL,
        "status": "PENDING", "row_count": 0,
        "error": None, "duration_sec": 0,
    }

    print(f"\n  {table}")
    print(f"  Source: {parquet_path}")

    # Check backup exists
    exists = hdfs_exists(parquet_path) if is_hdfs(backup_dir) else os.path.exists(parquet_path)
    if not exists:
        result["status"] = "NOT_FOUND"
        result["error"]  = f"No backup at {parquet_path}"
        print(f"  NOT FOUND — skipping")
        return result

    if dry_run:
        result["status"] = "DRY_RUN"
        print(f"  DRY RUN — would point {table} LOCATION → {parquet_path}")
        return result

    # HiveQL: drop old metadata, re-create pointing at backup HDFS path,
    # repair partitions so all partition dirs are registered.
    hql = textwrap.dedent(f"""
        USE {database};

        -- Step 1: drop stale metadata (data stays in HDFS)
        DROP TABLE IF EXISTS {table};

        -- Step 2: re-create external table pointing at backup Parquet
        -- LIKE copies the schema (column names + types) from the original DDL
        -- if the DDL table no longer exists, this will fail — see note below
        CREATE EXTERNAL TABLE IF NOT EXISTS {table}
        LIKE {database}.{table}
        STORED AS PARQUET
        LOCATION '{parquet_path}';

        -- Step 3: register all partition directories found under LOCATION
        MSCK REPAIR TABLE {table};
    """).strip()

    # NOTE: If the SIT metastore doesn't have the original DDL (i.e. the table
    # was never created on SIT), the LIKE clause will fail.
    # In that case run the DDL file first:
    #   beeline -u ... -f sql/ddl/25_position_upload_standardized.sql
    # Then re-run this restore pass.

    tmp_hql = f"/tmp/restore_hive_{table}_{datetime.now().strftime('%H%M%S')}.hql"
    with open(tmp_hql, "w") as f:
        f.write(hql)

    # Count rows for reporting (quick beeline SELECT COUNT)
    count_cmd = _beeline_cmd(
        beeline_url, beeline_extra_args,
        sql=f"SELECT COUNT(*) FROM {database}.{table};"
    )

    run_cmd = _beeline_cmd(beeline_url, beeline_extra_args, hql_file=tmp_hql)

    try:
        proc = subprocess.run(run_cmd, capture_output=True, text=True, timeout=600)
        os.remove(tmp_hql)

        stderr = proc.stderr or ""
        if proc.returncode != 0 or ("Error" in stderr and "FAILED" in stderr):
            result["status"] = "FAILED"
            result["error"]  = stderr[-2000:]
            print(f"  FAILED: {stderr[-300:]}")
        else:
            result["status"]      = "SUCCESS"
            result["duration_sec"] = round((datetime.now() - start).total_seconds(), 1)

            # Try to get row count after repair
            try:
                count_out = subprocess.check_output(
                    count_cmd, stderr=subprocess.DEVNULL, timeout=60
                ).decode()
                for line in count_out.splitlines():
                    line = line.strip().replace("|", "").strip()
                    if line.isdigit():
                        result["row_count"] = int(line)
                        break
            except Exception:
                pass

            print(f"  SUCCESS — {result['row_count']:,} rows, "
                  f"LOCATION={parquet_path} in {result['duration_sec']}s")

    except subprocess.TimeoutExpired:
        result["status"] = "FAILED"
        result["error"]  = "beeline timed out (600s)"
        print(f"  FAILED: timeout")
    except Exception as e:
        result["status"] = "FAILED"
        result["error"]  = str(e)
        print(f"  FAILED: {e}")

    return result


def _beeline_cmd(
    beeline_url: str,
    extra_args: str,
    sql: Optional[str] = None,
    hql_file: Optional[str] = None,
) -> List[str]:
    cmd = [
        "beeline", "-u", beeline_url,
        "--silent=true", "--outputformat=csv2", "--fastConnect=true",
    ]
    if extra_args:
        cmd += extra_args.split()
    if sql:
        cmd += ["-e", sql]
    elif hql_file:
        cmd += ["-f", hql_file]
    return cmd


# ============================================================================
# ARGS
# ============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="Restore SIT from UAT backup — Kudu via Spark, Hive external via Beeline"
    )
    # Connectivity
    p.add_argument("--kudu-master",   required=True,
                   help="SIT Kudu master host:port")
    p.add_argument("--impala-host",   default="",
                   help="SIT Impala host (used to classify tables if manifest missing)")
    p.add_argument("--impala-port",   type=int, default=21050)
    p.add_argument("--beeline-url",   required=True,
                   help='SIT HiveServer2 JDBC URL for Beeline')
    p.add_argument("--beeline-args",  default="",
                   help="Extra beeline args")
    p.add_argument("--spark-jars",    default="",
                   help="Comma-separated JARs for spark-submit (Kudu connector)")

    # Input
    p.add_argument("--backup-dir",    required=True,
                   help="Backup directory — local path or hdfs:// URI")
    p.add_argument("--database",      default=DATABASE)

    # Selection
    p.add_argument("--tables",        default="",
                   help="Comma-separated tables to restore (default: all in backup)")
    p.add_argument("--skip-tables",   default="",
                   help="Comma-separated tables to skip")
    p.add_argument("--skip-kudu",     action="store_true",
                   help="Skip Pass 1 — Hive external tables only")
    p.add_argument("--skip-hive",     action="store_true",
                   help="Skip Pass 2 — Kudu tables only")
    p.add_argument("--dry-run",       action="store_true",
                   help="Validate files exist, no writes")
    return p.parse_args()


# ============================================================================
# MAIN
# ============================================================================

def main():
    args = parse_args()

    # Validate backup dir
    if not is_hdfs(args.backup_dir):
        if not os.path.isdir(args.backup_dir):
            print(f"ERROR: backup-dir does not exist: {args.backup_dir}")
            sys.exit(1)

    print("=" * 60)
    print("  SIT Restore — Kudu (Spark) + Hive External (Beeline)")
    print("=" * 60)
    print(f"  Kudu master  : {args.kudu_master}")
    print(f"  Beeline URL  : {args.beeline_url}")
    print(f"  Backup dir   : {args.backup_dir}")
    print(f"  Database     : {args.database}")
    print(f"  Dry run      : {args.dry_run}")
    print(f"  Skip Kudu    : {args.skip_kudu}")
    print(f"  Skip Hive    : {args.skip_hive}")
    print("=" * 60)

    # ---- Read manifest ----
    manifest = read_manifest(args.backup_dir)
    type_map  = {}
    if manifest:
        print(f"\n  Manifest:")
        print(f"    Backup timestamp : {manifest.get('backup_timestamp', '?')}")
        print(f"    Source env       : {manifest.get('source_env', '?')}")
        print(f"    Database         : {manifest.get('database', '?')}")
        type_map = classify_tables_from_manifest(manifest)
    else:
        print("\n  WARNING: No manifest found — will classify via Impala")

    # ---- Discover tables ----
    if args.tables:
        all_tables = [t.strip() for t in args.tables.split(",") if t.strip()]
    else:
        all_tables = discover_tables(args.backup_dir)

    skip = {t.strip() for t in args.skip_tables.split(",") if t.strip()}
    all_tables = [t for t in all_tables if t not in skip]

    if skip:
        print(f"\n  Skipping: {', '.join(skip)}")

    # ---- Classify ----
    # Fill in any missing types from Impala if needed
    unclassified = [t for t in all_tables if type_map.get(t, TYPE_UNKNOWN) == TYPE_UNKNOWN]
    if unclassified and args.impala_host:
        print(f"\n  Classifying {len(unclassified)} unclassified tables via Impala...")
        extra = classify_tables_impala(
            args.impala_host, args.impala_port, args.database, unclassified
        )
        type_map.update(extra)

    kudu_tables = [t for t in all_tables if type_map.get(t) == TYPE_KUDU]
    hive_tables = [t for t in all_tables if type_map.get(t) in (TYPE_EXTERNAL, TYPE_HIVE)]
    unk_tables  = [t for t in all_tables if type_map.get(t, TYPE_UNKNOWN) == TYPE_UNKNOWN]

    if unk_tables:
        print(f"\n  WARNING: {len(unk_tables)} tables have unknown type — "
              f"defaulting to Kudu pass: {', '.join(unk_tables)}")
        kudu_tables += unk_tables  # safe default: Spark read is harmless if table is not Kudu

    print(f"\n  Total: {len(all_tables)} tables — "
          f"{len(kudu_tables)} Kudu, {len(hive_tables)} Hive external")

    # ---- Pass 1: Kudu ----
    kudu_results = []
    if not args.skip_kudu:
        kudu_results = restore_kudu_tables(
            kudu_master=args.kudu_master,
            database=args.database,
            tables=kudu_tables,
            backup_dir=args.backup_dir,
            spark_jars=args.spark_jars,
            dry_run=args.dry_run,
        )
    else:
        print("\n  [Kudu pass] SKIPPED (--skip-kudu)")

    # ---- Pass 2: Hive external ----
    hive_results = []
    if not args.skip_hive:
        hive_results = restore_hive_external_tables(
            beeline_url=args.beeline_url,
            database=args.database,
            tables=hive_tables,
            backup_dir=args.backup_dir,
            beeline_extra_args=args.beeline_args,
            dry_run=args.dry_run,
        )
    else:
        print("\n  [Hive pass] SKIPPED (--skip-hive)")

    # ---- Summary ----
    all_results = kudu_results + hive_results
    success     = [r for r in all_results if r["status"] == "SUCCESS"]
    failed      = [r for r in all_results if r["status"] == "FAILED"]
    not_found   = [r for r in all_results if r["status"] == "NOT_FOUND"]
    total_rows  = sum(r["row_count"] for r in success)

    print("\n\n" + "=" * 60)
    print("  RESTORE SUMMARY")
    print("=" * 60)
    print(f"  Success    : {len(success)}")
    print(f"  Failed     : {len(failed)}")
    print(f"  Not found  : {len(not_found)}")
    print(f"  Total rows : {total_rows:,}")
    print(f"\n  {'Table':<50} {'Type':<10} {'Status':<12} {'Rows':>10}")
    print(f"  {'-'*50} {'-'*10} {'-'*12} {'-'*10}")
    for r in all_results:
        print(f"  {r['table']:<50} {r['type']:<10} {r['status']:<12} {r['row_count']:>10,}")

    if not_found:
        print(f"\n  NOT FOUND (no backup — skipped):")
        for r in not_found:
            print(f"    - {r['table']}")

    if failed:
        print(f"\n  FAILED:")
        for r in failed:
            print(f"    - {r['table']}: {r['error']}")

    print(f"\n{'='*60}")
    print("  POST-RESTORE CHECKS (run on SIT):")
    print(f"{'='*60}")
    print("  -- Verify Kudu row counts match UAT:")
    print(f"  impala-shell -i <sit-impala>:21050 -q \"SELECT COUNT(*) FROM {DATABASE}.cis_trade\"")
    print("  -- Verify Hive external table partitions:")
    print(f"  beeline -u ... -e \"SHOW PARTITIONS {DATABASE}.position_upload_report\"")
    print("  -- If Hive table LOCATION needs to move to canonical path:")
    print(f"  beeline -u ... -e \"ALTER TABLE {DATABASE}.position_upload_standardized")
    print(f"    SET LOCATION '/data/gmp_cis/position_upload_standardized';")
    print(f"    MSCK REPAIR TABLE {DATABASE}.position_upload_standardized;\"")
    print("=" * 60)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
