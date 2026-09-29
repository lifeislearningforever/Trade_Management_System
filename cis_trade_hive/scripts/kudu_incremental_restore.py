#!/usr/bin/env python3
"""
Kudu Incremental Restore Script using kudu-backup JAR

This script applies incremental backups to restore point-in-time state.
Can apply multiple incremental backups in sequence after a full restore.

Usage:
    # Apply single incremental backup
    spark-submit --jars /jars/kudu/*.jar kudu_incremental_restore.py \
        --table cis_trade \
        --backup-path hdfs:///backups/kudu/gmp_cis/cis_trade/incremental/2026-04-01_060000

    # Apply all incremental backups since a full backup
    spark-submit --jars /jars/kudu/*.jar kudu_incremental_restore.py \
        --table cis_trade \
        --backup-base hdfs:///backups/kudu/gmp_cis/cis_trade/incremental \
        --since "2026-04-01_000000" \
        --until "2026-04-01_180000"

    # Point-in-time restore
    spark-submit --jars /jars/kudu/*.jar kudu_incremental_restore.py \
        --table cis_trade \
        --backup-base hdfs:///backups/kudu/gmp_cis/cis_trade/incremental \
        --point-in-time "2026-04-01 15:30:00"

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
    from pyspark.sql.functions import col, max as spark_max
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


class KuduIncrementalRestore:
    """Incremental restore implementation for Kudu tables."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.spark = None
        self.restore_timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        self.stats = {
            'backups_applied': 0,
            'backups_failed': 0,
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
                .appName(f"KuduIncrementalRestore_{self.restore_timestamp}") \
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

    def list_incremental_backups(
        self,
        backup_base: str,
        since: str = None,
        until: str = None
    ) -> List[Dict[str, Any]]:
        """
        List available incremental backups in a directory.

        Args:
            backup_base: Base path containing incremental backups
            since: Only include backups after this timestamp (YYYY-MM-DD_HHMMSS)
            until: Only include backups before this timestamp

        Returns:
            List of backup info dictionaries, sorted by timestamp
        """
        backups = []

        try:
            # List directories in backup base using Hadoop FileSystem
            hadoop_conf = self.spark.sparkContext._jsc.hadoopConfiguration()
            fs = self.spark._jvm.org.apache.hadoop.fs.FileSystem.get(
                self.spark._jvm.java.net.URI.create(backup_base),
                hadoop_conf
            )
            path = self.spark._jvm.org.apache.hadoop.fs.Path(backup_base)

            if not fs.exists(path):
                print(f"  WARNING: Backup path does not exist: {backup_base}")
                return []

            status_list = fs.listStatus(path)

            for status in status_list:
                if status.isDirectory():
                    dir_name = status.getPath().getName()
                    # Expect format: YYYY-MM-DD_HHMMSS
                    if len(dir_name) == 17 and dir_name[10] == '_':
                        backup_info = {
                            'timestamp': dir_name,
                            'path': f"{backup_base}/{dir_name}",
                            'size': status.getLen()
                        }

                        # Filter by since/until
                        if since and dir_name < since:
                            continue
                        if until and dir_name > until:
                            continue

                        backups.append(backup_info)

            # Sort by timestamp
            backups.sort(key=lambda x: x['timestamp'])
            print(f"  Found {len(backups)} incremental backups")

        except Exception as e:
            print(f"  ERROR listing backups: {e}")

        return backups

    def read_backup_metadata(self, backup_path: str) -> Optional[Dict[str, Any]]:
        """Read metadata from backup location."""
        try:
            metadata_path = f"{backup_path}/_metadata"
            metadata_rdd = self.spark.sparkContext.textFile(f"{metadata_path}/part-*")
            metadata_lines = metadata_rdd.collect()

            if metadata_lines:
                metadata_json = '\n'.join(metadata_lines)
                return json.loads(metadata_json)
            return None

        except Exception as e:
            print(f"  WARNING: Could not read metadata: {e}")
            return None

    def apply_incremental_backup(
        self,
        table_name: str,
        backup_path: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Apply a single incremental backup to a table.

        Args:
            table_name: Target table name
            backup_path: Path to incremental backup
            dry_run: If True, only validate

        Returns:
            Result dictionary
        """
        full_table_name = f"{self.config['database']}.{table_name}"

        result = {
            'table': table_name,
            'backup_path': backup_path,
            'status': 'pending',
            'rows_applied': 0,
            'duration_seconds': 0,
            'error': None
        }

        start_time = datetime.now()
        print(f"\n  Applying: {backup_path}")

        # Read metadata
        metadata = self.read_backup_metadata(backup_path)
        if metadata:
            print(f"    Backup timestamp: {metadata.get('timestamp', 'unknown')}")
            print(f"    Since: {metadata.get('since_timestamp', 'unknown')}")
            print(f"    Rows: {metadata.get('row_count', 0):,}")
            result['rows_applied'] = metadata.get('row_count', 0)

            if metadata.get('empty', False):
                print(f"    Backup is empty, skipping")
                result['status'] = 'skipped'
                return result

        if dry_run:
            print(f"    [DRY RUN] Would apply incremental backup")
            result['status'] = 'dry_run'
            return result

        try:
            # Read backup data
            df = self.spark.read.parquet(backup_path)
            row_count = df.count()

            if row_count == 0:
                print(f"    No rows to apply")
                result['status'] = 'success'
                result['rows_applied'] = 0
                return result

            # Apply using upsert mode
            df.write \
                .format("org.apache.kudu.spark.kudu") \
                .option("kudu.master", self.config['kudu_master']) \
                .option("kudu.table", full_table_name) \
                .option("kudu.operation", "upsert") \
                .mode("append") \
                .save()

            result['status'] = 'success'
            result['rows_applied'] = row_count
            result['duration_seconds'] = (datetime.now() - start_time).total_seconds()

            self.stats['backups_applied'] += 1
            self.stats['total_rows'] += row_count

            print(f"    SUCCESS: Applied {row_count:,} rows")

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            result['duration_seconds'] = (datetime.now() - start_time).total_seconds()
            self.stats['backups_failed'] += 1
            self.stats['errors'].append({'backup': backup_path, 'error': str(e)})
            print(f"    FAILED: {e}")

        return result

    def restore_point_in_time(
        self,
        table_name: str,
        backup_base: str,
        full_backup_path: str,
        target_time: datetime,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Restore to a specific point in time.

        This requires:
        1. Restore from the most recent full backup before target_time
        2. Apply all incremental backups up to target_time

        Args:
            table_name: Target table name
            backup_base: Base path for incremental backups
            full_backup_path: Path to full backup to restore first
            target_time: Target point in time
            dry_run: If True, only validate

        Returns:
            Summary dictionary
        """
        print(f"\n{'='*60}")
        print(f"Point-in-Time Restore: {table_name}")
        print(f"Target Time: {target_time}")
        print(f"Full Backup: {full_backup_path}")
        print(f"Incremental Base: {backup_base}")

        results = []

        # Step 1: First restore from full backup
        # (This would typically call kudu_full_restore.py)
        print(f"\nStep 1: Full backup restore should be done first")
        print(f"  Run: kudu_full_restore.py --table {table_name} --backup-path {full_backup_path}")

        # Step 2: List and apply incremental backups
        target_ts = target_time.strftime('%Y-%m-%d_%H%M%S')
        backups = self.list_incremental_backups(
            backup_base,
            until=target_ts
        )

        print(f"\nStep 2: Applying {len(backups)} incremental backups")

        for backup in backups:
            result = self.apply_incremental_backup(
                table_name,
                backup['path'],
                dry_run=dry_run
            )
            results.append(result)

            if result['status'] == 'failed':
                print(f"  Stopping due to failure")
                break

        self.stats['end_time'] = datetime.now().isoformat()

        return {
            'table': table_name,
            'target_time': str(target_time),
            'backups_applied': results,
            'stats': self.stats
        }

    def restore_incremental_range(
        self,
        table_name: str,
        backup_base: str,
        since: str = None,
        until: str = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Apply a range of incremental backups.

        Args:
            table_name: Target table name
            backup_base: Base path for incremental backups
            since: Apply backups after this timestamp
            until: Apply backups before this timestamp
            dry_run: If True, only validate

        Returns:
            Summary dictionary
        """
        print(f"\n{'='*60}")
        print(f"Incremental Range Restore: {table_name}")
        print(f"Base Path: {backup_base}")
        print(f"Since: {since or 'beginning'}")
        print(f"Until: {until or 'latest'}")

        # List backups in range
        backups = self.list_incremental_backups(backup_base, since=since, until=until)

        if not backups:
            print("  No incremental backups found in range")
            return {
                'table': table_name,
                'backups_applied': [],
                'stats': self.stats
            }

        print(f"  Will apply {len(backups)} incremental backups")
        results = []

        for backup in backups:
            result = self.apply_incremental_backup(
                table_name,
                backup['path'],
                dry_run=dry_run
            )
            results.append(result)

            if result['status'] == 'failed':
                print(f"  Stopping due to failure")
                break

        self.stats['end_time'] = datetime.now().isoformat()

        return {
            'table': table_name,
            'since': since,
            'until': until,
            'backups_applied': results,
            'stats': self.stats
        }

    def close(self):
        """Close Spark session."""
        if self.spark:
            self.spark.stop()
            print("Spark session closed")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Kudu Incremental Restore - Apply incremental backups',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Apply single incremental backup
  spark-submit --jars /jars/kudu/*.jar kudu_incremental_restore.py \\
      --table cis_trade \\
      --backup-path hdfs:///backups/kudu/gmp_cis/cis_trade/incremental/2026-04-01_060000

  # Apply range of incremental backups
  spark-submit --jars /jars/kudu/*.jar kudu_incremental_restore.py \\
      --table cis_trade \\
      --backup-base hdfs:///backups/kudu/gmp_cis/cis_trade/incremental \\
      --since 2026-04-01_000000 --until 2026-04-01_180000

  # Point-in-time restore
  spark-submit --jars /jars/kudu/*.jar kudu_incremental_restore.py \\
      --table cis_trade \\
      --backup-base hdfs:///backups/kudu/gmp_cis/cis_trade/incremental \\
      --full-backup hdfs:///backups/kudu/gmp_cis/cis_trade/full/2026-03-31_000000 \\
      --point-in-time "2026-04-01 15:30:00"
        """
    )

    parser.add_argument('--table', '-t', type=str, required=True,
                        help='Target table name')
    parser.add_argument('--backup-path', '-b', type=str,
                        help='Path to single incremental backup')
    parser.add_argument('--backup-base', type=str,
                        help='Base path containing multiple incremental backups')
    parser.add_argument('--since', type=str,
                        help='Apply backups after this timestamp (YYYY-MM-DD_HHMMSS)')
    parser.add_argument('--until', type=str,
                        help='Apply backups before this timestamp')
    parser.add_argument('--point-in-time', type=str,
                        help='Target point in time (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--full-backup', type=str,
                        help='Full backup path (for point-in-time restore)')
    parser.add_argument('--kudu-master', '-m', type=str, default=DEFAULT_CONFIG['kudu_master'],
                        help=f"Kudu master address (default: {DEFAULT_CONFIG['kudu_master']})")
    parser.add_argument('--database', '-d', type=str, default=DEFAULT_CONFIG['database'],
                        help=f"Database name (default: {DEFAULT_CONFIG['database']})")
    parser.add_argument('--parallelism', type=int, default=DEFAULT_CONFIG['parallelism'],
                        help=f"Spark parallelism (default: {DEFAULT_CONFIG['parallelism']})")
    parser.add_argument('--dry-run', action='store_true',
                        help='Validate without applying')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Validate arguments
    if not args.backup_path and not args.backup_base:
        print("ERROR: Must specify --backup-path or --backup-base")
        sys.exit(1)

    if args.point_in_time and not args.full_backup:
        print("WARNING: Point-in-time restore requires --full-backup for complete restore")

    # Build configuration
    config = {
        'kudu_master': args.kudu_master,
        'database': args.database,
        'parallelism': args.parallelism,
        'batch_size': DEFAULT_CONFIG['batch_size'],
        'operation_timeout_ms': DEFAULT_CONFIG['operation_timeout_ms'],
    }

    print("=" * 70)
    print("  KUDU INCREMENTAL RESTORE")
    print("=" * 70)
    print(f"  Kudu Master: {config['kudu_master']}")
    print(f"  Database:    {config['database']}")
    print(f"  Table:       {args.table}")
    print(f"  Dry Run:     {args.dry_run}")
    print("=" * 70)

    # Initialize restore
    restore = KuduIncrementalRestore(config)

    if not restore.init_spark():
        print("ERROR: Failed to initialize Spark session")
        sys.exit(1)

    try:
        if args.backup_path:
            # Single backup restore
            result = restore.apply_incremental_backup(
                args.table,
                args.backup_path,
                dry_run=args.dry_run
            )
            summary = {
                'table': args.table,
                'backups_applied': [result],
                'stats': restore.stats
            }

        elif args.point_in_time:
            # Point-in-time restore
            target_time = datetime.strptime(args.point_in_time, '%Y-%m-%d %H:%M:%S')
            summary = restore.restore_point_in_time(
                args.table,
                args.backup_base,
                args.full_backup or '',
                target_time,
                dry_run=args.dry_run
            )

        else:
            # Range restore
            summary = restore.restore_incremental_range(
                args.table,
                args.backup_base,
                since=args.since,
                until=args.until,
                dry_run=args.dry_run
            )

        # Print summary
        print("\n" + "=" * 70)
        print("  INCREMENTAL RESTORE SUMMARY")
        print("=" * 70)
        print(f"  Table:           {args.table}")
        print(f"  Backups Applied: {summary['stats']['backups_applied']}")
        print(f"  Backups Failed:  {summary['stats']['backups_failed']}")
        print(f"  Total Rows:      {summary['stats']['total_rows']:,}")
        print("=" * 70)

        if summary['stats']['backups_failed'] > 0:
            sys.exit(1)
        sys.exit(0)

    finally:
        restore.close()


if __name__ == '__main__':
    main()
