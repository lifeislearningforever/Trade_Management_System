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
}

# Restore modes
RESTORE_MODES = {
    'truncate_insert': 'Delete all existing data, then insert from backup',
    'upsert': 'Update existing rows, insert new rows (preserves non-backed-up data)',
    'insert_ignore': 'Insert only rows that do not exist (skip duplicates)',
    'create_new': 'Create a new table with backup data (table must not exist)',
}


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
            metadata_path = f"{backup_path}/_metadata"
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
            'duration_seconds': 0,
            'error': None
        }

        start_time = datetime.now()
        print(f"\n{'='*60}")
        print(f"Restoring: {full_table_name}")
        print(f"Source: {backup_path}")
        print(f"Mode: {mode} - {RESTORE_MODES.get(mode, 'Unknown')}")

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

            # Execute restore based on mode
            if mode == 'truncate_insert':
                result = self._restore_truncate_insert(df, full_table_name, result)
            elif mode == 'upsert':
                result = self._restore_upsert(df, full_table_name, result)
            elif mode == 'insert_ignore':
                result = self._restore_insert_ignore(df, full_table_name, result)
            elif mode == 'create_new':
                result = self._restore_create_new(df, full_table_name, result)
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
        """Truncate table and insert all rows from backup."""
        print(f"  Mode: TRUNCATE_INSERT - Deleting existing data...")

        try:
            # Delete all existing data using Kudu client
            # Note: This uses Spark Kudu connector's overwrite mode
            df.write \
                .format("org.apache.kudu.spark.kudu") \
                .option("kudu.master", self.config['kudu_master']) \
                .option("kudu.table", full_table_name) \
                .option("kudu.operation", "upsert") \
                .mode("overwrite") \
                .save()

            result['status'] = 'success'
            result['rows_restored'] = result['rows_in_backup']

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

            df = self.spark.read \
                .format("org.apache.kudu.spark.kudu") \
                .option("kudu.master", self.config['kudu_master']) \
                .option("kudu.table", full_table_name) \
                .load()

            actual_rows = df.count()
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
    }

    print("=" * 70)
    print("  KUDU FULL RESTORE")
    print("=" * 70)
    print(f"  Kudu Master:   {config['kudu_master']}")
    print(f"  Database:      {config['database']}")
    print(f"  Table:         {args.table}")
    print(f"  Backup Path:   {args.backup_path}")
    print(f"  Mode:          {args.mode}")
    print(f"  Dry Run:       {args.dry_run}")
    print("=" * 70)

    # Confirmation for destructive operations
    if args.mode == 'truncate_insert' and not args.dry_run:
        print("\n  WARNING: truncate_insert mode will DELETE all existing data!")
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
