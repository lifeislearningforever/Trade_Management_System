#!/usr/bin/env python3
"""
UAT Backup to Local/HDFS (for SCP/SFTP transfer to SIT)

Two-pass backup strategy:
  Pass 1 — Kudu tables    → read via Kudu Spark connector (spark-submit)
  Pass 2 — Hive external  → read via Beeline INSERT OVERWRITE (beeline -e)

Both passes write Parquet to the same HDFS output directory, partitioned
per table.  After both passes the script copies HDFS → local and tars it up.

WHY TWO PASSES?
  Impala cannot read Hive external Parquet tables (different metastore context).
  Beeline connects directly to HiveServer2 and can read/write all Hive tables.
  Kudu tables cannot be read by Beeline; they need the Kudu Spark connector.

Flow:
  [Impala SHOW TABLES → classify Kudu vs Hive external]
    │
    ├─ KUDU tables ──► spark-submit (Kudu connector) ──► HDFS Parquet
    │
    └─ HIVE EXTERNAL ► beeline -e "INSERT OVERWRITE ... SELECT * FROM ..." ──► HDFS Parquet
         │
         └─ hdfs dfs -get ──► local dir ──► tar.gz ──► SCP to SIT

Usage:
    python backup_uat_to_local.py \\
        --kudu-master <uat-kudu>:7051 \\
        --impala-host <uat-impala-host> \\
        --beeline-url "jdbc:hive2://<hs2-host>:10000/gmp_cis;principal=hive/_HOST@REALM" \\
        --output-dir /tmp/uat_backup

    # Dry run (discover + classify, no write)
    python backup_uat_to_local.py ... --dry-run

    # Skip Kudu pass (Hive only)
    python backup_uat_to_local.py ... --skip-kudu

    # Skip Hive pass (Kudu only)
    python backup_uat_to_local.py ... --skip-hive

Author: CIS Trade Hive Team
Version: 3.0
Date: 2026-04-23
"""

import argparse
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime
from typing import List, Dict, Tuple, Optional

# ---------------------------------------------------------------------------
# Optional PySpark (only needed for Kudu pass)
# ---------------------------------------------------------------------------
try:
    from pyspark.sql import SparkSession
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Optional Impyla (used for table discovery)
# ---------------------------------------------------------------------------
try:
    from impala.dbapi import connect as impala_connect
    IMPYLA_AVAILABLE = True
except ImportError:
    IMPYLA_AVAILABLE = False

DATABASE = "gmp_cis"

TYPE_KUDU     = "KUDU"
TYPE_EXTERNAL = "EXTERNAL"   # Hive external table
TYPE_HIVE     = "HIVE"       # Hive managed/internal table
TYPE_UNKNOWN  = "UNKNOWN"


# ============================================================================
# TABLE DISCOVERY  (via Impala — works for Kudu + type detection)
# ============================================================================

def discover_tables_impala(impala_host: str, impala_port: int, database: str) -> List[Dict]:
    """
    Connect to Impala via impyla, run SHOW TABLES + DESCRIBE FORMATTED on each,
    and classify every table as KUDU, EXTERNAL, or HIVE.
    """
    print(f"\n  [Discovery] Connecting to Impala {impala_host}:{impala_port} ...")

    if not IMPYLA_AVAILABLE:
        print("  WARNING: impyla not installed. Falling back to beeline for discovery.")
        return discover_tables_beeline(impala_host, impala_port, database)

    try:
        conn   = impala_connect(host=impala_host, port=impala_port, database=database,
                                auth_mechanism="NOSASL")
        cursor = conn.cursor()

        cursor.execute(f"SHOW TABLES IN {database}")
        table_names = [row[0] for row in cursor.fetchall()]
        print(f"  Found {len(table_names)} tables")

        tables = []
        for name in sorted(table_names):
            ttype, location = _classify_impala(cursor, database, name)
            tables.append({"name": name, "type": ttype, "location": location})
            print(f"    {name:<55} [{ttype}]")

        cursor.close()
        conn.close()
        return tables

    except Exception as e:
        print(f"  ERROR connecting to Impala: {e}")
        sys.exit(1)


def _classify_impala(cursor, database: str, table: str) -> Tuple[str, str]:
    """Run DESCRIBE FORMATTED via Impala cursor and classify table type."""
    try:
        cursor.execute(f"DESCRIBE FORMATTED {database}.{table}")
        rows = cursor.fetchall()
        kv   = {(r[0] or "").strip(): (r[1] or "").strip() for r in rows}

        storage_handler = kv.get("Storage Handler", "").lower()
        table_type_raw  = kv.get("Table Type",      "").upper()
        location        = kv.get("Location",         "")

        if "kudu" in storage_handler:
            return TYPE_KUDU, location
        elif "external" in table_type_raw:
            return TYPE_EXTERNAL, location
        else:
            return TYPE_HIVE, location
    except Exception as e:
        print(f"    WARNING: DESCRIBE FORMATTED {table} failed: {e}")
        return TYPE_UNKNOWN, ""


def discover_tables_beeline(impala_host: str, impala_port: int, database: str) -> List[Dict]:
    """
    Fallback discovery using beeline + Impala JDBC if impyla is not installed.
    Parses text output of SHOW TABLES.
    """
    jdbc = f"jdbc:impala://{impala_host}:{impala_port}/{database}"
    cmd  = [
        "beeline", "-u", jdbc,
        "--silent=true", "--outputformat=csv2",
        "-e", f"SHOW TABLES IN {database}"
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
        names = [line.strip() for line in out.splitlines()
                 if line.strip() and line.strip() != "tab_name"]
        print(f"  Found {len(names)} tables via beeline fallback")
        # Without DESCRIBE FORMATTED we can't classify — mark all UNKNOWN
        return [{"name": n, "type": TYPE_UNKNOWN, "location": ""} for n in sorted(names)]
    except Exception as e:
        print(f"  ERROR: beeline discovery also failed: {e}")
        sys.exit(1)


# ============================================================================
# PASS 1 — KUDU TABLES  (Spark + Kudu connector)
# ============================================================================

def backup_kudu_tables(
    kudu_master: str,
    database: str,
    tables: List[Dict],
    hdfs_output_dir: str,
    spark_jars: str,
    dry_run: bool,
) -> List[Dict]:
    """
    Backup all KUDU tables using the Kudu Spark connector.
    Spawns a separate spark-submit process per table to avoid JAR conflicts.
    Returns list of result dicts.
    """
    kudu_tables = [t for t in tables if t["type"] == TYPE_KUDU]
    if not kudu_tables:
        print("\n  [Kudu pass] No Kudu tables found — skipping")
        return []

    print(f"\n{'='*60}")
    print(f"  [Kudu pass] Backing up {len(kudu_tables)} Kudu tables via Spark")
    print(f"{'='*60}")

    results = []
    for t in kudu_tables:
        result = _backup_kudu_one(
            kudu_master=kudu_master,
            database=database,
            table=t["name"],
            hdfs_output_dir=hdfs_output_dir,
            spark_jars=spark_jars,
            dry_run=dry_run,
        )
        results.append(result)

    return results


def _backup_kudu_one(
    kudu_master: str,
    database: str,
    table: str,
    hdfs_output_dir: str,
    spark_jars: str,
    dry_run: bool,
) -> Dict:
    """Run a small inline PySpark script via spark-submit for one Kudu table."""
    out_path = os.path.join(hdfs_output_dir, table)
    start    = datetime.now()
    result   = {
        "table": table, "type": TYPE_KUDU,
        "status": "PENDING", "row_count": 0,
        "output_path": out_path, "error": None, "duration_sec": 0,
    }

    print(f"\n  {table}  →  {out_path}")

    if dry_run:
        result["status"] = "DRY_RUN"
        print(f"  DRY RUN — skipping")
        return result

    # Inline PySpark script passed via -c to spark-submit
    pyspark_code = textwrap.dedent(f"""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.appName("backup_{table}").getOrCreate()
        spark.sparkContext.setLogLevel("WARN")
        df = (spark.read
              .format("org.apache.kudu.spark.kudu")
              .option("kudu.master", "{kudu_master}")
              .option("kudu.table", "{database}.{table}")
              .load())
        count = df.count()
        print(f"ROWS:{count}")
        df.coalesce(1).write.mode("overwrite").parquet("{out_path}")
        spark.stop()
    """).strip()

    # Write to a temp file (spark-submit needs a file path)
    tmp_script = f"/tmp/backup_kudu_{table}_{datetime.now().strftime('%H%M%S')}.py"
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
            # Extract row count from stdout
            row_count = 0
            for line in proc.stdout.splitlines():
                if line.startswith("ROWS:"):
                    row_count = int(line.split(":")[1])
            result["status"]    = "SUCCESS"
            result["row_count"] = row_count
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
# PASS 2 — HIVE EXTERNAL TABLES  (Beeline INSERT OVERWRITE)
# ============================================================================

def backup_hive_external_tables(
    beeline_url: str,
    database: str,
    tables: List[Dict],
    hdfs_output_dir: str,
    beeline_extra_args: str,
    dry_run: bool,
) -> List[Dict]:
    """
    Backup all EXTERNAL (and HIVE managed) tables using Beeline.

    Strategy per table:
      CREATE EXTERNAL TABLE IF NOT EXISTS backup_<table>
        LIKE {database}.{table}
        STORED AS PARQUET
        LOCATION '<hdfs_output_dir>/<table>';

      INSERT OVERWRITE TABLE backup_<table>
        SELECT * FROM {database}.{table};

      DROP TABLE backup_<table>;   -- drops metadata only, data stays in HDFS

    Returns list of result dicts.
    """
    hive_tables = [t for t in tables if t["type"] in (TYPE_EXTERNAL, TYPE_HIVE)]
    if not hive_tables:
        print("\n  [Hive pass] No Hive external/managed tables found — skipping")
        return []

    print(f"\n{'='*60}")
    print(f"  [Hive pass] Backing up {len(hive_tables)} Hive tables via Beeline")
    print(f"  Beeline URL: {beeline_url}")
    print(f"{'='*60}")

    results = []
    for t in hive_tables:
        result = _backup_hive_one(
            beeline_url=beeline_url,
            database=database,
            table=t["name"],
            hdfs_output_dir=hdfs_output_dir,
            beeline_extra_args=beeline_extra_args,
            dry_run=dry_run,
        )
        results.append(result)

    return results


def _backup_hive_one(
    beeline_url: str,
    database: str,
    table: str,
    hdfs_output_dir: str,
    beeline_extra_args: str,
    dry_run: bool,
) -> Dict:
    """Backup one Hive table via Beeline INSERT OVERWRITE into a temp external table."""
    out_path    = os.path.join(hdfs_output_dir, table)
    backup_tbl  = f"backup_tmp_{table}"
    start       = datetime.now()
    result      = {
        "table": table, "type": TYPE_EXTERNAL,
        "status": "PENDING", "row_count": 0,
        "output_path": out_path, "error": None, "duration_sec": 0,
    }

    print(f"\n  {table}  →  {out_path}")

    if dry_run:
        result["status"] = "DRY_RUN"
        print(f"  DRY RUN — skipping")
        return result

    # Build HiveQL script
    hql = textwrap.dedent(f"""
        USE {database};

        DROP TABLE IF EXISTS {backup_tbl};

        CREATE EXTERNAL TABLE {backup_tbl}
        LIKE {database}.{table}
        STORED AS PARQUET
        LOCATION '{out_path}';

        SET hive.exec.dynamic.partition=true;
        SET hive.exec.dynamic.partition.mode=nonstrict;

        INSERT OVERWRITE TABLE {backup_tbl}
        SELECT * FROM {database}.{table};

        DROP TABLE IF EXISTS {backup_tbl};
    """).strip()

    tmp_hql = f"/tmp/backup_hive_{table}_{datetime.now().strftime('%H%M%S')}.hql"
    with open(tmp_hql, "w") as f:
        f.write(hql)

    # Count rows first (separate beeline call)
    count_hql = f"SELECT COUNT(*) FROM {database}.{table};"
    count_cmd = _beeline_cmd(beeline_url, beeline_extra_args, sql=count_hql)

    try:
        count_out = subprocess.check_output(count_cmd, stderr=subprocess.DEVNULL,
                                            timeout=120).decode()
        row_count = 0
        for line in count_out.splitlines():
            line = line.strip().replace("|", "").strip()
            if line.isdigit():
                row_count = int(line)
                break
        result["row_count"] = row_count
        print(f"  Rows: {row_count:,}")
    except Exception:
        print(f"  WARNING: Could not get row count for {table}")

    # Run INSERT OVERWRITE via beeline file
    run_cmd = _beeline_cmd(beeline_url, beeline_extra_args, hql_file=tmp_hql)

    try:
        proc = subprocess.run(run_cmd, capture_output=True, text=True, timeout=1800)
        os.remove(tmp_hql)

        if proc.returncode != 0:
            # Beeline often writes errors to stderr but exits 0 — check stderr too
            stderr = proc.stderr or ""
            if "Error" in stderr or "FAILED" in stderr:
                result["status"] = "FAILED"
                result["error"]  = stderr[-2000:]
                print(f"  FAILED: {stderr[-200:]}")
            else:
                result["status"]    = "SUCCESS"
                result["duration_sec"] = round((datetime.now() - start).total_seconds(), 1)
                print(f"  SUCCESS in {result['duration_sec']}s")
        else:
            result["status"]    = "SUCCESS"
            result["duration_sec"] = round((datetime.now() - start).total_seconds(), 1)
            print(f"  SUCCESS in {result['duration_sec']}s")

    except subprocess.TimeoutExpired:
        result["status"] = "FAILED"
        result["error"]  = "beeline timed out (1800s)"
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
    """Build a beeline command list."""
    cmd = [
        "beeline",
        "-u", beeline_url,
        "--silent=true",
        "--outputformat=csv2",
        "--fastConnect=true",
    ]
    if extra_args:
        cmd += extra_args.split()
    if sql:
        cmd += ["-e", sql]
    elif hql_file:
        cmd += ["-f", hql_file]
    return cmd


# ============================================================================
# HDFS → LOCAL + ZIP
# ============================================================================

def copy_hdfs_to_local_and_zip(hdfs_path: str, local_base: str, timestamp: str) -> str:
    folder_name = f"gmp_cis_{timestamp}"
    local_path  = os.path.join(local_base, folder_name)
    tar_path    = os.path.join(local_base, f"{folder_name}.tar.gz")

    print(f"\n{'='*60}")
    print(f"  Copying HDFS → local disk")
    print(f"  HDFS : {hdfs_path}")
    print(f"  Local: {local_path}")

    os.makedirs(local_base, exist_ok=True)
    ret = subprocess.call(["hdfs", "dfs", "-get", hdfs_path, local_path])
    if ret != 0:
        print(f"  ERROR: hdfs dfs -get failed (exit {ret})")
        return ""

    print(f"  Zipping → {tar_path}")
    ret = subprocess.call(["tar", "-czf", tar_path, "-C", local_base, folder_name])
    if ret != 0:
        print(f"  ERROR: tar failed (exit {ret})")
        return ""

    size = subprocess.check_output(["du", "-sh", tar_path]).decode().split()[0]
    print(f"  Done  : {tar_path}  ({size})")
    return tar_path


# ============================================================================
# MANIFEST
# ============================================================================

def write_manifest(output_dir: str, timestamp: str, args, results: List[Dict]):
    manifest = {
        "backup_timestamp": timestamp,
        "source_env": "UAT",
        "kudu_master": args.kudu_master,
        "impala_host": args.impala_host,
        "beeline_url": args.beeline_url,
        "database": args.database,
        "tables": results,
        "created_at": datetime.now().isoformat(),
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n  Manifest written: {manifest_path}")


# ============================================================================
# ARGS
# ============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="Backup ALL gmp_cis tables (Kudu via Spark, Hive external via Beeline)"
    )
    # Connectivity
    p.add_argument("--kudu-master",   required=True,
                   help="UAT Kudu master host:port (e.g. kudu-master:7051)")
    p.add_argument("--impala-host",   required=True,
                   help="UAT Impala host for table discovery")
    p.add_argument("--impala-port",   type=int, default=21050)
    p.add_argument("--beeline-url",   required=True,
                   help='HiveServer2 JDBC URL for Beeline '
                        '(e.g. "jdbc:hive2://hs2-host:10000/gmp_cis;principal=hive/_HOST@REALM")')
    p.add_argument("--beeline-args",  default="",
                   help="Extra beeline args (e.g. '--hiveconf mapred.job.queue.name=root.users')")

    # Spark
    p.add_argument("--spark-jars",    default="",
                   help="Comma-separated JARs for spark-submit (kudu + hwc connectors)")

    # Output
    p.add_argument("--database",      default=DATABASE)
    p.add_argument("--output-dir",    default="/tmp/uat_backup",
                   help="HDFS root for Parquet output (default: /tmp/uat_backup)")
    p.add_argument("--local-dir",     default="/tmp/uat_backup_local",
                   help="Local dir for tar.gz (default: /tmp/uat_backup_local)")

    # Control
    p.add_argument("--skip-tables",   default="",
                   help="Comma-separated table names to skip")
    p.add_argument("--skip-kudu",     action="store_true",
                   help="Skip Pass 1 (Kudu tables) — only run Hive pass")
    p.add_argument("--skip-hive",     action="store_true",
                   help="Skip Pass 2 (Hive external tables) — only run Kudu pass")
    p.add_argument("--dry-run",       action="store_true",
                   help="Discover + classify only, no writes")
    p.add_argument("--no-zip",        action="store_true",
                   help="Skip HDFS→local copy and tar.gz")
    return p.parse_args()


# ============================================================================
# MAIN
# ============================================================================

def main():
    args      = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hdfs_out  = os.path.join(args.output_dir, f"gmp_cis_{timestamp}")

    print("=" * 60)
    print("  UAT Backup — Kudu (Spark) + Hive External (Beeline)")
    print("=" * 60)
    print(f"  Kudu master  : {args.kudu_master}")
    print(f"  Impala host  : {args.impala_host}:{args.impala_port}")
    print(f"  Beeline URL  : {args.beeline_url}")
    print(f"  Database     : {args.database}")
    print(f"  HDFS out     : {hdfs_out}")
    print(f"  Local dir    : {args.local_dir}")
    print(f"  Dry run      : {args.dry_run}")
    print(f"  Skip Kudu    : {args.skip_kudu}")
    print(f"  Skip Hive    : {args.skip_hive}")
    print("=" * 60)

    # ---- Discovery ----
    all_tables = discover_tables_impala(args.impala_host, args.impala_port, args.database)

    skip = {t.strip() for t in args.skip_tables.split(",") if t.strip()}
    tables = [t for t in all_tables if t["name"] not in skip]
    if skip:
        print(f"\n  Skipping: {', '.join(skip)}")

    kudu_tables = [t for t in tables if t["type"] == TYPE_KUDU]
    hive_tables = [t for t in tables if t["type"] in (TYPE_EXTERNAL, TYPE_HIVE)]
    unk_tables  = [t for t in tables if t["type"] == TYPE_UNKNOWN]

    print(f"\n  Total: {len(tables)} tables — "
          f"{len(kudu_tables)} Kudu, {len(hive_tables)} Hive external, "
          f"{len(unk_tables)} Unknown")

    # ---- Pass 1: Kudu ----
    kudu_results = []
    if not args.skip_kudu:
        kudu_results = backup_kudu_tables(
            kudu_master=args.kudu_master,
            database=args.database,
            tables=kudu_tables,
            hdfs_output_dir=hdfs_out,
            spark_jars=args.spark_jars,
            dry_run=args.dry_run,
        )
    else:
        print("\n  [Kudu pass] SKIPPED (--skip-kudu)")

    # ---- Pass 2: Hive external ----
    hive_results = []
    if not args.skip_hive:
        hive_results = backup_hive_external_tables(
            beeline_url=args.beeline_url,
            database=args.database,
            tables=hive_tables,
            hdfs_output_dir=hdfs_out,
            beeline_extra_args=args.beeline_args,
            dry_run=args.dry_run,
        )
    else:
        print("\n  [Hive pass] SKIPPED (--skip-hive)")

    all_results = kudu_results + hive_results

    # ---- Manifest ----
    if not args.dry_run:
        write_manifest(hdfs_out, timestamp, args, all_results)

    # ---- Summary ----
    success   = [r for r in all_results if r["status"] == "SUCCESS"]
    failed    = [r for r in all_results if r["status"] == "FAILED"]
    not_found = [r for r in all_results if r["status"] == "NOT_FOUND"]
    total_sec = round((datetime.now() - datetime.strptime(timestamp, "%Y%m%d_%H%M%S")).total_seconds(), 1)
    total_rows = sum(r["row_count"] for r in success)

    print("\n\n" + "=" * 60)
    print("  BACKUP SUMMARY")
    print("=" * 60)
    print(f"  HDFS output  : {hdfs_out}")
    print(f"  Success      : {len(success)}")
    print(f"  Failed       : {len(failed)}")
    print(f"  Not found    : {len(not_found)}")
    print(f"  Total rows   : {total_rows:,}")
    print(f"\n  {'Table':<45} {'Type':<10} {'Status':<12} {'Rows':>10}")
    print(f"  {'-'*45} {'-'*10} {'-'*12} {'-'*10}")
    for r in sorted(all_results, key=lambda x: x["table"]):
        print(f"  {r['table']:<45} {r['type']:<10} {r['status']:<12} {r['row_count']:>10,}")

    if failed:
        print(f"\n  FAILED:")
        for r in failed:
            print(f"    - {r['table']}: {r['error']}")

    # ---- HDFS → local + zip ----
    tar_path = ""
    if not args.dry_run and not args.no_zip:
        tar_path = copy_hdfs_to_local_and_zip(
            hdfs_path=hdfs_out,
            local_base=args.local_dir,
            timestamp=timestamp,
        )

    print(f"\n{'='*60}")
    print("  NEXT STEPS — Transfer to SIT:")
    print(f"{'='*60}")
    if tar_path:
        print(f"  tar.gz ready : {tar_path}")
        print(f"  SCP to SIT:")
        print(f"    scp {tar_path} <user>@<sit-host>:/tmp/")
        print(f"  On SIT — restore:")
        print(f"    tar -xzf /tmp/gmp_cis_{timestamp}.tar.gz -C /tmp/")
        print(f"    hdfs dfs -put /tmp/gmp_cis_{timestamp}/ /tmp/restore/")
        print(f"    python restore_sit_from_local.py \\")
        print(f"      --kudu-master <sit-kudu>:7051 \\")
        print(f"      --beeline-url 'jdbc:hive2://<sit-hs2>:10000/gmp_cis' \\")
        print(f"      --backup-dir hdfs:///tmp/restore/gmp_cis_{timestamp}/")
    else:
        print(f"  HDFS path    : {hdfs_out}")
        print(f"  Run manually:")
        print(f"    hdfs dfs -get {hdfs_out} /tmp/gmp_cis_{timestamp}/")
        print(f"    tar -czf /tmp/gmp_cis_{timestamp}.tar.gz -C /tmp gmp_cis_{timestamp}/")
    print("=" * 60)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
