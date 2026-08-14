#!/usr/bin/env python3
"""
Kudu Full Restore Script using kudu-backup JAR

This script restores Kudu tables from full backups stored in HDFS/S3/ADLS.
Supports multiple restore modes: truncate_insert, upsert, insert_ignore, create_new.

Usage:
    # Restore single table (truncate and insert)
    spark-submit --jars /jars/kudu/*.jar kudu_full_restore.py \
        --table cis_trade \
        --backup-path hdfs:///backups/kudu/gmp_cis/cis_trade/full/2026-04-01_000000

    # Restore with upsert mode (update existing, insert new)
    spark-submit --jars /jars/kudu/*.jar kudu_full_restore.py \
        --table cis_trade \
        --backup-path hdfs:///backups/kudu/gmp_cis/cis_trade/full/2026-04-01_000000 \
        --mode upsert

    # Restore to different table
    spark-submit --jars /jars/kudu/*.jar kudu_full_restore.py \
        --table cis_trade_restored \
        --backup-path hdfs:///backups/kudu/gmp_cis/cis_trade/full/2026-04-01_000000 \
        --mode create_new

Author: CIS Trade Hive Team
Version: 1.0
Date: 2026-04-01
"""

import argparse
import json
import shlex
import subprocess
import sys
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    from pyspark.sql import SparkSession
    from pyspark.sql.functions import col
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False
    print("WARNING: PySpark not available. Running in validation mode only.")


# Default configuration
DEFAULT_CONFIG = {
    'kudu_master': 'kudu-master:7051',
    'database': 'gmp_cis',
    'parallelism': 8,
    'batch_size': 10000,
    'operation_timeout_ms': 60000,
    'impala_host': os.environ.get('IMPALA_HOST', ''),
    # Every real environment in this codebase (SIT/UAT/PROD/DR) uses GSSAPI
    # Kerberos + TLS (config/environments.py) -- default to what a plain
    # `impala-shell -i host -d db` needs on those clusters. Override to ''
    # for a NOSASL/local cluster.
    'impala_shell_flags': os.environ.get('IMPALA_SHELL_FLAGS', '-k --ssl'),
}


def _describe_formatted_via_impala(database: str, table: str, impala_host: str, impala_shell_flags: str = '') -> Optional[str]:
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
    Same fix as scripts/kudu_full_backup.py's _describe_formatted_via_impala.
    """
    if not impala_host:
        print("    WARNING: --impala-host not set — table type detection will fail")
        return None
    cmd = ['impala-shell', '-i', impala_host, '-d', database]
    cmd += shlex.split(impala_shell_flags) if impala_shell_flags else []
    # -B (batch mode) already suppresses the header row by default -- see
    # kudu_full_backup.py's _describe_formatted_via_impala for why
    # --print_header=false is deliberately not passed here.
    cmd += ['-B', '--output_delimiter=\t', '-q', f'DESCRIBE FORMATTED {table}']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return None
        return result.stdout
    except Exception:
        return None


def _parse_describe_formatted(raw: str) -> Dict[str, str]:
    """
    Parse impala-shell's tab-delimited DESCRIBE FORMATTED output into a flat
    {key: value} dict.

    Confirmed against a real impalad v4.0.0.7.1.9.1054-4 response for a
    native Kudu table -- Impala reuses the same 3-column (name, type,
    comment) layout for two structurally different row shapes:
      - Top-level metadata, e.g. `Location:  <TAB>  hdfs://...  <TAB>` --
        key is column 1 (WITH a trailing colon Impala includes as literal
        text), value is column 2.
      - Table Parameters sub-rows, e.g. `<TAB>  storage_handler  <TAB>
        org.apache.hadoop.hive.kudu.KuduStorageHandler` -- column 1 (name)
        is BLANK, key is column 2, value is column 3. This is where
        storage_handler/kudu.table_name/kudu.master_addresses live -- there
        is no top-level "Storage Handler:" row the way Hive CLI/Spark's
        DESCRIBE FORMATTED has, which is what the original (broken)
        2-column-only parser assumed.
    Trailing colons on top-level keys are stripped so callers don't need to
    know which shape produced a given key.
    """
    rows: Dict[str, str] = {}
    for line in raw.splitlines():
        fields = [f.strip() for f in line.split('\t')]
        while len(fields) < 3:
            fields.append('')
        name, type_col, comment = fields[0], fields[1], fields[2]
        if name.startswith('#'):
            continue
        if name:
            key = name.rstrip(':').strip()
            if key:
                rows[key] = type_col
        elif type_col:
            rows[type_col] = comment
    return rows

# Restore modes
RESTORE_MODES = {
    'truncate_insert': 'Delete all existing data, then insert from backup',
    'upsert': 'Update existing rows, insert new rows (preserves non-backed-up data) — Kudu tables only',
    'insert_ignore': 'Insert only rows that do not exist (skip duplicates) — Kudu tables only',
    'create_new': 'Create a new table with backup data (table must not exist)',
}

# Kudu's upsert/insert_ignore rely on native per-row primary-key semantics.
# A Hive/external (plain Parquet/ORC) table has no equivalent without knowing
# it's an ACID transactional table, which this script has no reliable way to
# detect -- so these modes are refused for non-Kudu tables rather than
# silently doing something that isn't really an upsert.
HIVE_SUPPORTED_MODES = {'truncate_insert', 'create_new'}

TYPE_KUDU = 'KUDU'
TYPE_HIVE = 'HIVE'
TYPE_EXTERNAL = 'EXTERNAL'
TYPE_UNKNOWN = 'UNKNOWN'


class KuduFullRestore:
    """Full restore implementation for Kudu tables."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.spark = None
        self.restore_timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        self.stats = {
            'tables_restored': 0,
            'tables_failed': 0,
            'total_rows': 0,
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'errors': []
        }

    def init_spark(self) -> bool:
        """Initialize Spark session with Kudu configuration."""
        if not SPARK_AVAILABLE:
            print("ERROR: PySpark is not available")
            return False

        try:
            builder = SparkSession.builder \
                .appName(f"KuduFullRestore_{self.restore_timestamp}") \
                .config("spark.sql.adaptive.enabled", "true") \
                .config("spark.kudu.master", self.config['kudu_master'])

            builder = builder.config("spark.default.parallelism", str(self.config['parallelism']))
            builder = builder.config("spark.sql.shuffle.partitions", str(self.config['parallelism']))
            # Hive catalog access (DESCRIBE FORMATTED for type detection, and
            # spark.sql()-based writes for Hive/external tables).
            builder = builder.enableHiveSupport()

            self.spark = builder.getOrCreate()
            self.spark.sparkContext.setLogLevel("WARN")
            print(f"Spark session initialized: {self.spark.sparkContext.applicationId}")
            return True

        except Exception as e:
            print(f"ERROR: Failed to initialize Spark: {e}")
            return False

    def read_backup_metadata(self, backup_path: str) -> Optional[Dict[str, Any]]:
        """
        Read metadata from backup location.

        Args:
            backup_path: Path to backup directory

        Returns:
            Metadata dictionary or None
        """
        try:
            # kudu_full_backup.py writes per-table metadata to "_meta" (see its
            # _write_meta()) -- NOT "_metadata". Existing backups on disk were
            # written with that name, so the reader must match it rather than
            # the other way around.
            metadata_path = f"{backup_path}/_meta"
            print(f"  Reading metadata from {metadata_path}")

            # Read metadata file
            metadata_rdd = self.spark.sparkContext.textFile(f"{metadata_path}/part-*")
            metadata_lines = metadata_rdd.collect()

            if metadata_lines:
                metadata_json = '\n'.join(metadata_lines)
                return json.loads(metadata_json)
            return None

        except Exception as e:
            print(f"  WARNING: Could not read metadata: {e}")
            return None

    def detect_table_type(self, table_name: str) -> str:
        """
        Detect whether the RESTORE TARGET is a Kudu table or a Hive/external
        table, via DESCRIBE FORMATTED -- same technique kudu_full_backup.py
        uses when deciding how to READ a table. Here it decides how to WRITE
        the restored data back.

        If the table doesn't exist yet (e.g. 'create_new' mode against a
        brand-new name), DESCRIBE FORMATTED fails and this falls back to
        TYPE_KUDU, since 'create_new' historically only ever targeted Kudu --
        callers that want a new Hive table should let auto-detection find an
        existing Hive table by that name instead.
        """
        full_table_name = f"{self.config['database']}.{table_name}"
        raw = _describe_formatted_via_impala(
            self.config['database'], table_name,
            self.config.get('impala_host', ''), self.config.get('impala_shell_flags', '')
        )
        if raw is None:
            print(f"  Could not DESCRIBE {full_table_name} — assuming Kudu (new table)")
            return TYPE_KUDU

        try:
            rows = _parse_describe_formatted(raw)
            storage_handler = rows.get("storage_handler", "").lower()
            table_type_raw = rows.get("Table Type", "").upper()

            if "kudu" in storage_handler:
                return TYPE_KUDU
            elif "external" in table_type_raw:
                return TYPE_EXTERNAL
            else:
                return TYPE_HIVE

        except Exception as e:
            print(f"  Could not parse DESCRIBE {full_table_name} ({e}) — assuming Kudu (new table)")
            return TYPE_KUDU

    def _resolve_kudu_table_name(self, table_name: str) -> str:
        """
        Resolve the RAW/internal Kudu table name (e.g. 'impala::gmp_cis.cis_trade')
        via the 'kudu.table_name' table property in DESCRIBE FORMATTED -- same
        lookup kudu_full_backup.py's _detect_type() already relies on for reads.

        This matters because the Kudu Spark connector's 'kudu.table' option
        needs the table's actual Kudu-side name, which is not guaranteed to
        equal the Hive-catalog 'database.table' string depending on how the
        table was originally created. Used for operations that read/modify an
        EXISTING Kudu table (truncate_insert's delete step, upsert,
        insert_ignore, validate) -- not for create_new, which creates a brand
        new Kudu table under whatever name it's given.
        """
        full_table_name = f"{self.config['database']}.{table_name}"
        raw = _describe_formatted_via_impala(
            self.config['database'], table_name,
            self.config.get('impala_host', ''), self.config.get('impala_shell_flags', '')
        )
        if raw is None:
            print(f"  Could not DESCRIBE {full_table_name}, "
                  f"falling back to impala::{full_table_name}")
            return f"impala::{full_table_name}"

        try:
            rows = _parse_describe_formatted(raw)
            return (
                rows.get("kudu.table_name")
                or rows.get("kudu.table")
                or f"impala::{full_table_name}"
            )
        except Exception as e:
            print(f"  Could not resolve Kudu table name for {full_table_name} ({e}), "
                  f"falling back to impala::{full_table_name}")
            return f"impala::{full_table_name}"

    def _get_kudu_primary_key_columns(self, kudu_table_name: str) -> List[str]:
        """
        Get primary key column names directly from the Kudu table's own
        schema, via the native Java Kudu client -- bypasses Impala/Hive
        metadata text parsing entirely (unreliable across Impala versions
        for this), going straight to the source of truth. Same JVM-bridge
        pattern kudu_incremental_restore.py already uses for HDFS
        FileSystem access.
        """
        jvm = self.spark._jvm
        client = jvm.org.apache.kudu.client.KuduClient.KuduClientBuilder(
            self.config['kudu_master']
        ).build()
        try:
            table = client.openTable(kudu_table_name)
            schema = table.getSchema()
            return [c.getName() for c in schema.getPrimaryKeyColumns()]
        finally:
            client.close()

    def restore_table(
        self,
        table_name: str,
        backup_path: str,
        mode: str = 'truncate_insert',
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Restore a single Kudu table from backup.

        Args:
            table_name: Target table name (without database prefix)
            backup_path: Path to backup directory
            mode: Restore mode (truncate_insert, upsert, insert_ignore, create_new)
            dry_run: If True, only validate without actual restore

        Returns:
            Dictionary with restore result
        """
        full_table_name = f"{self.config['database']}.{table_name}"

        result = {
            'table': table_name,
            'full_table_name': full_table_name,
            'backup_path': backup_path,
            'mode': mode,
            'status': 'pending',
            'rows_restored': 0,
            'rows_in_backup': 0,
            'rows_deleted': 0,
            'duration_seconds': 0,
            'error': None
        }

        start_time = datetime.now()
        print(f"\n{'='*60}")
        print(f"Restoring: {full_table_name}")
        print(f"Source: {backup_path}")
        print(f"Mode: {mode} - {RESTORE_MODES.get(mode, 'Unknown')}")

        table_type = self.detect_table_type(table_name)
        print(f"Target table type: {table_type}")

        if table_type != TYPE_KUDU and mode not in HIVE_SUPPORTED_MODES:
            result['status'] = 'failed'
            result['error'] = (
                f"Mode '{mode}' is not supported for {table_type} tables "
                f"(no native per-row upsert without Kudu's primary-key "
                f"semantics). Use one of: {sorted(HIVE_SUPPORTED_MODES)}."
            )
            print(f"  FAILED: {result['error']}")
            self.stats['tables_failed'] += 1
            self.stats['errors'].append({'table': table_name, 'error': result['error']})
            return result

        # Read and validate backup metadata
        metadata = self.read_backup_metadata(backup_path)
        if metadata:
            print(f"  Backup timestamp: {metadata.get('timestamp', 'unknown')}")
            print(f"  Backup row count: {metadata.get('row_count', 'unknown'):,}")
            result['rows_in_backup'] = metadata.get('row_count', 0)

            if metadata.get('empty', False):
                print(f"  WARNING: Backup is marked as empty")

        if dry_run:
            print(f"[DRY RUN] Would restore {full_table_name} from {backup_path} using mode {mode}")
            result['status'] = 'dry_run'
            return result

        try:
            # Read backup data
            print(f"  Reading backup data...")
            df = self.spark.read.parquet(backup_path)
            row_count = df.count()
            result['rows_in_backup'] = row_count
            print(f"  Rows in backup: {row_count:,}")

            if row_count == 0:
                print(f"  WARNING: No data in backup")
                if mode == 'truncate_insert':
                    print(f"  Skipping truncate to preserve existing data")
                result['status'] = 'success'
                result['rows_restored'] = 0
                return result

            # Execute restore based on mode + target table type
            if table_type == TYPE_KUDU:
                if mode == 'create_new':
                    result = self._restore_create_new(df, full_table_name, result)
                else:
                    # These target an EXISTING Kudu table -- resolve its real
                    # Kudu-side name rather than assuming it equals the
                    # Hive-catalog 'database.table' string (see
                    # _resolve_kudu_table_name's docstring).
                    kudu_table_name = self._resolve_kudu_table_name(table_name)
                    if mode == 'truncate_insert':
                        result = self._restore_truncate_insert(df, kudu_table_name, result)
                    elif mode == 'upsert':
                        result = self._restore_upsert(df, kudu_table_name, result)
                    elif mode == 'insert_ignore':
                        result = self._restore_insert_ignore(df, kudu_table_name, result)
                    else:
                        raise ValueError(f"Unknown restore mode: {mode}")
            else:
                # Hive / external table -- writes go through spark.sql's
                # catalog, not the Kudu connector. HIVE_SUPPORTED_MODES was
                # already enforced above, so only these two reach here.
                if mode == 'truncate_insert':
                    result = self._restore_hive_truncate_insert(df, full_table_name, result)
                elif mode == 'create_new':
                    result = self._restore_hive_create_new(df, full_table_name, result)
                else:
                    raise ValueError(f"Unknown restore mode: {mode}")

            result['duration_seconds'] = (datetime.now() - start_time).total_seconds()

            if result['status'] == 'success':
                self.stats['tables_restored'] += 1
                self.stats['total_rows'] += result['rows_restored']
                print(f"  SUCCESS: Restored {result['rows_restored']:,} rows in {result['duration_seconds']:.2f}s")
            else:
                self.stats['tables_failed'] += 1

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            result['duration_seconds'] = (datetime.now() - start_time).total_seconds()
            self.stats['tables_failed'] += 1
            self.stats['errors'].append({'table': table_name, 'error': str(e)})
            print(f"  FAILED: {e}")

        return result

    def _restore_truncate_insert(
        self,
        df,
        full_table_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Truncate table and insert all rows from backup.

        Previously this only upserted the backup data (identical to
        _restore_upsert) -- there was no actual delete step, despite the
        name and the 5-second destructive-operation warning printed in
        main(). Any row already in the target table that wasn't in the
        backup was silently left behind forever. This now does a real
        delete-then-upsert: existing primary keys not present in the
        backup are deleted first via the Kudu connector's native
        'kudu.operation=delete', THEN the backup data is upserted.
        """
        print(f"  Mode: TRUNCATE_INSERT - Identifying stale rows to delete...")

        try:
            pk_cols = self._get_kudu_primary_key_columns(full_table_name)
            print(f"  Primary key columns: {pk_cols}")

            existing_df = (
                self.spark.read
                .format("org.apache.kudu.spark.kudu")
                .option("kudu.master", self.config['kudu_master'])
                .option("kudu.table", full_table_name)
                .load()
                .select(*pk_cols)
            )
            backup_keys_df = df.select(*pk_cols).distinct()

            # Existing rows whose primary key does NOT appear in the backup
            # -- these are the stale rows truncate_insert is supposed to remove.
            stale_keys_df = existing_df.distinct().join(
                backup_keys_df, on=pk_cols, how="left_anti"
            )
            stale_count = stale_keys_df.count()
            print(f"  Deleting {stale_count:,} stale row(s) not present in backup...")

            if stale_count > 0:
                stale_keys_df.write \
                    .format("org.apache.kudu.spark.kudu") \
                    .option("kudu.master", self.config['kudu_master']) \
                    .option("kudu.table", full_table_name) \
                    .option("kudu.operation", "delete") \
                    .mode("append") \
                    .save()

            print(f"  Upserting {result['rows_in_backup']:,} row(s) from backup...")
            df.write \
                .format("org.apache.kudu.spark.kudu") \
                .option("kudu.master", self.config['kudu_master']) \
                .option("kudu.table", full_table_name) \
                .option("kudu.operation", "upsert") \
                .mode("append") \
                .save()

            result['status'] = 'success'
            result['rows_restored'] = result['rows_in_backup']
            result['rows_deleted'] = stale_count

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)

        return result

    def _restore_upsert(
        self,
        df,
        full_table_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Upsert rows - update existing, insert new."""
        print(f"  Mode: UPSERT - Updating/inserting rows...")

        try:
            df.write \
                .format("org.apache.kudu.spark.kudu") \
                .option("kudu.master", self.config['kudu_master']) \
                .option("kudu.table", full_table_name) \
                .option("kudu.operation", "upsert") \
                .mode("append") \
                .save()

            result['status'] = 'success'
            result['rows_restored'] = result['rows_in_backup']

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)

        return result

    def _restore_insert_ignore(
        self,
        df,
        full_table_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Insert only non-existing rows (skip duplicates)."""
        print(f"  Mode: INSERT_IGNORE - Inserting new rows only...")

        try:
            df.write \
                .format("org.apache.kudu.spark.kudu") \
                .option("kudu.master", self.config['kudu_master']) \
                .option("kudu.table", full_table_name) \
                .option("kudu.operation", "insert_ignore") \
                .mode("append") \
                .save()

            result['status'] = 'success'
            result['rows_restored'] = result['rows_in_backup']  # May be less due to ignores

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)

        return result

    def _restore_create_new(
        self,
        df,
        full_table_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new table and insert all rows."""
        print(f"  Mode: CREATE_NEW - Creating new table...")

        try:
            # Create table using Kudu Spark connector
            # Note: Table schema will be inferred from backup data
            df.write \
                .format("org.apache.kudu.spark.kudu") \
                .option("kudu.master", self.config['kudu_master']) \
                .option("kudu.table", full_table_name) \
                .mode("errorifexists") \
                .save()

            result['status'] = 'success'
            result['rows_restored'] = result['rows_in_backup']

        except Exception as e:
            if "already exists" in str(e).lower():
                result['error'] = f"Table {full_table_name} already exists. Use a different name or mode."
            else:
                result['error'] = str(e)
            result['status'] = 'failed'

        return result

    def _restore_hive_truncate_insert(
        self,
        df,
        full_table_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Overwrite all data in an existing Hive/external table.

        Uses insertInto() rather than saveAsTable() because the target table
        already exists (this is a restore-into-known-schema scenario, e.g.
        DR already has the table shell from DDL) -- insertInto() matches by
        column position against the existing table/partition scheme instead
        of trying to redefine it.
        """
        print(f"  Mode: TRUNCATE_INSERT (Hive) — overwriting existing data...")

        try:
            df.write.mode("overwrite").insertInto(full_table_name)

            result['status'] = 'success'
            result['rows_restored'] = result['rows_in_backup']

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)

        return result

    def _restore_hive_create_new(
        self,
        df,
        full_table_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new Hive-catalog table (managed) and insert all rows."""
        print(f"  Mode: CREATE_NEW (Hive) — creating new table...")

        try:
            df.write.mode("errorifexists").saveAsTable(full_table_name)

            result['status'] = 'success'
            result['rows_restored'] = result['rows_in_backup']

        except Exception as e:
            if "already exists" in str(e).lower():
                result['error'] = f"Table {full_table_name} already exists. Use a different name or mode."
            else:
                result['error'] = str(e)
            result['status'] = 'failed'

        return result

    def validate_restore(self, table_name: str, expected_rows: int) -> bool:
        """
        Validate restore by counting rows in restored table.

        Args:
            table_name: Table name
            expected_rows: Expected row count

        Returns:
            True if validation passes
        """
        try:
            full_table_name = f"{self.config['database']}.{table_name}"
            table_type = self.detect_table_type(table_name)

            if table_type == TYPE_KUDU:
                df = self.spark.read \
                    .format("org.apache.kudu.spark.kudu") \
                    .option("kudu.master", self.config['kudu_master']) \
                    .option("kudu.table", full_table_name) \
                    .load()
                actual_rows = df.count()
            else:
                actual_rows = self.spark.sql(f"SELECT COUNT(*) AS c FROM {full_table_name}").collect()[0]['c']
            print(f"  Validation: Expected {expected_rows:,} rows, found {actual_rows:,}")

            if actual_rows >= expected_rows:
                print(f"  Validation PASSED")
                return True
            else:
                print(f"  Validation FAILED: Missing {expected_rows - actual_rows:,} rows")
                return False

        except Exception as e:
            print(f"  Validation ERROR: {e}")
            return False

    def close(self):
        """Close Spark session."""
        if self.spark:
            self.spark.stop()
            print("Spark session closed")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Kudu Full Restore - Restore Kudu tables from backups',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Restore Modes:
  truncate_insert  Delete all existing data, insert from backup (DEFAULT)
  upsert           Update existing rows, insert new rows
  insert_ignore    Insert only rows that do not exist (skip duplicates)
  create_new       Create a new table with backup data

Examples:
  # Restore single table
  spark-submit --jars /jars/kudu/*.jar kudu_full_restore.py \\
      --table cis_trade \\
      --backup-path hdfs:///backups/kudu/gmp_cis/cis_trade/full/2026-04-01_000000

  # Restore with upsert mode
  spark-submit --jars /jars/kudu/*.jar kudu_full_restore.py \\
      --table cis_trade --mode upsert \\
      --backup-path hdfs:///backups/kudu/gmp_cis/cis_trade/full/2026-04-01_000000

  # Dry run
  spark-submit --jars /jars/kudu/*.jar kudu_full_restore.py \\
      --table cis_trade --dry-run \\
      --backup-path hdfs:///backups/kudu/gmp_cis/cis_trade/full/2026-04-01_000000
        """
    )

    parser.add_argument('--table', '-t', type=str, required=True,
                        help='Target table name to restore to')
    parser.add_argument('--backup-path', '-b', type=str, required=True,
                        help='Path to backup directory')
    parser.add_argument('--mode', '-M', type=str, default='truncate_insert',
                        choices=list(RESTORE_MODES.keys()),
                        help='Restore mode (default: truncate_insert)')
    parser.add_argument('--kudu-master', '-m', type=str, default=DEFAULT_CONFIG['kudu_master'],
                        help=f"Kudu master address (default: {DEFAULT_CONFIG['kudu_master']})")
    parser.add_argument('--impala-host', type=str, default=DEFAULT_CONFIG['impala_host'],
                        help='Impala coordinator host:port (e.g. impalad:21050), used for table '
                             'type detection via impala-shell instead of spark.sql (Spark cannot '
                             'DESCRIBE FORMATTED a Kudu table -- see _describe_formatted_via_impala)')
    parser.add_argument('--impala-shell-flags', type=str, default=DEFAULT_CONFIG['impala_shell_flags'],
                        help="Extra flags passed to impala-shell for type detection "
                             f"(default: {DEFAULT_CONFIG['impala_shell_flags']!r} for Kerberos+TLS "
                             "clusters; pass '' for NOSASL/local)")
    parser.add_argument('--database', '-d', type=str, default=DEFAULT_CONFIG['database'],
                        help=f"Database name (default: {DEFAULT_CONFIG['database']})")
    parser.add_argument('--parallelism', type=int, default=DEFAULT_CONFIG['parallelism'],
                        help=f"Spark parallelism (default: {DEFAULT_CONFIG['parallelism']})")
    parser.add_argument('--validate', action='store_true',
                        help='Validate restore by counting rows')
    parser.add_argument('--dry-run', action='store_true',
                        help='Validate without performing actual restore')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Build configuration
    config = {
        'kudu_master': args.kudu_master,
        'database': args.database,
        'parallelism': args.parallelism,
        'batch_size': DEFAULT_CONFIG['batch_size'],
        'operation_timeout_ms': DEFAULT_CONFIG['operation_timeout_ms'],
        'impala_host': args.impala_host,
        'impala_shell_flags': args.impala_shell_flags,
    }

    print("=" * 70)
    print("  KUDU FULL RESTORE")
    print("=" * 70)
    print(f"  Kudu Master:   {config['kudu_master']}")
    print(f"  Impala Host:   {config['impala_host'] or '(NOT SET — type detection will fail)'}")
    print(f"  Database:      {config['database']}")
    print(f"  Table:         {args.table}")
    print(f"  Backup Path:   {args.backup_path}")
    print(f"  Mode:          {args.mode}")
    print(f"  Dry Run:       {args.dry_run}")
    print("=" * 70)

    # Confirmation for destructive operations
    if args.mode == 'truncate_insert' and not args.dry_run:
        print("\n  WARNING: truncate_insert mode will DELETE any existing row whose")
        print("  primary key is not present in this backup (Kudu tables), or")
        print("  OVERWRITE all data in the target table (Hive/external tables)!")
        print("  Press Ctrl+C within 5 seconds to abort...")
        import time
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n  Aborted by user")
            sys.exit(0)

    # Initialize restore
    restore = KuduFullRestore(config)

    if not restore.init_spark():
        print("ERROR: Failed to initialize Spark session")
        sys.exit(1)

    try:
        # Run restore
        result = restore.restore_table(
            args.table,
            args.backup_path,
            mode=args.mode,
            dry_run=args.dry_run
        )

        # Validate if requested
        if args.validate and result['status'] == 'success':
            restore.validate_restore(args.table, result['rows_restored'])

        # Print summary
        print("\n" + "=" * 70)
        print("  RESTORE SUMMARY")
        print("=" * 70)
        print(f"  Table:          {result['full_table_name']}")
        print(f"  Status:         {result['status']}")
        print(f"  Rows in Backup: {result['rows_in_backup']:,}")
        print(f"  Rows Restored:  {result['rows_restored']:,}")
        if result.get('rows_deleted'):
            print(f"  Rows Deleted:   {result['rows_deleted']:,}  (stale, not in backup)")
        print(f"  Duration:       {result['duration_seconds']:.2f}s")
        if result['error']:
            print(f"  Error:          {result['error']}")
        print("=" * 70)

        if result['status'] == 'failed':
            sys.exit(1)
        sys.exit(0)

    finally:
        restore.close()


if __name__ == '__main__':
    main()
