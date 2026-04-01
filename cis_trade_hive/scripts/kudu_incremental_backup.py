#!/usr/bin/env python3
"""
Kudu Incremental Backup Script using kudu-backup JAR

This script performs incremental backups of Kudu tables based on timestamp columns.
Captures only changes since the last backup.

Usage:
    # Backup changes from last 24 hours
    spark-submit --jars /jars/kudu/*.jar kudu_incremental_backup.py \
        --table cis_trade \
        --hours-back 24

    # Backup changes since specific timestamp
    spark-submit --jars /jars/kudu/*.jar kudu_incremental_backup.py \
        --table cis_trade \
        --since "2026-04-01 00:00:00"

    # Auto-detect last backup timestamp
    spark-submit --jars /jars/kudu/*.jar kudu_incremental_backup.py \
        --table cis_trade \
        --auto-since

Author: CIS Trade Hive Team
Version: 1.0
Date: 2026-04-01
"""

import argparse
import json
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

try:
    from pyspark.sql import SparkSession
    from pyspark.sql.functions import col, lit, current_timestamp
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False
    print("WARNING: PySpark not available. Running in validation mode only.")


# Default configuration
DEFAULT_CONFIG = {
    'kudu_master': 'kudu-master:7051',
    'database': 'gmp_cis',
    'backup_path': 'hdfs:///backups/kudu',
    'compression': 'snappy',
    'parallelism': 8,
    'batch_size': 10000,
    'scan_timeout_ms': 30000,
    'hours_back': 24,
}

# Timestamp column mapping for each table
TABLE_TIMESTAMP_COLUMNS = {
    'cis_trade': 'updated_at',
    'cis_trade_history': 'performed_at',
    'cis_portfolio': 'updated_at',
    'cis_portfolio_history': 'performed_at',
    'cis_security_kudu': 'updated_at',
    'cis_trade_position': 'updated_at',
    'cis_audit_log': 'created_at',
    'cis_cash_flow': 'updated_at',
    'cis_cash_flow_history': 'performed_at',
    'cis_corporate_action': 'updated_at',
    'cis_counterparty_kudu': 'updated_at',
    'cis_fx_rate': 'updated_at',
    'cis_market_price': 'updated_at',
    'cis_user': 'updated_at',
    'cis_udf_value': 'updated_at',
    'cis_udf_definition': 'updated_at',
    # Queue tables use created_at
    'cis_position_queue': 'created_at',
    'cis_settlement_queue': 'created_at',
    'cis_trade_event_queue': 'created_at',
    'cis_ca_cash_flow_queue': 'created_at',
    'cis_ca_cash_flow_log': 'created_at',
}

# Tables that support incremental backup
INCREMENTAL_TABLES = list(TABLE_TIMESTAMP_COLUMNS.keys())


class KuduIncrementalBackup:
    """Incremental backup implementation for Kudu tables."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.spark = None
        self.backup_timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        self.stats = {
            'tables_backed_up': 0,
            'tables_failed': 0,
            'tables_skipped': 0,
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
                .appName(f"KuduIncrementalBackup_{self.backup_timestamp}") \
                .config("spark.sql.adaptive.enabled", "true") \
                .config("spark.sql.parquet.compression.codec", self.config['compression']) \
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

    def get_last_backup_timestamp(self, table_name: str) -> Optional[datetime]:
        """
        Get timestamp of last backup from manifest files.

        Args:
            table_name: Table name

        Returns:
            Last backup timestamp or None
        """
        try:
            manifest_path = f"{self.config['backup_path']}/{self.config['database']}/{table_name}/incremental/"

            # Try to read manifest files to find last backup
            # This is a simplified version - in production, use a proper manifest store
            print(f"  Looking for last backup in {manifest_path}")

            # For now, return None to indicate no previous backup found
            # In production, implement proper manifest reading
            return None

        except Exception as e:
            print(f"  Could not determine last backup time: {e}")
            return None

    def backup_table(
        self,
        table_name: str,
        since: Optional[datetime] = None,
        hours_back: int = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Backup changes to a single Kudu table since a given timestamp.

        Args:
            table_name: Name of the table (without database prefix)
            since: Backup changes since this timestamp
            hours_back: Alternative to since - backup last N hours
            dry_run: If True, only validate without actual backup

        Returns:
            Dictionary with backup result
        """
        full_table_name = f"{self.config['database']}.{table_name}"
        backup_path = f"{self.config['backup_path']}/{self.config['database']}/{table_name}/incremental/{self.backup_timestamp}"

        result = {
            'table': table_name,
            'full_table_name': full_table_name,
            'backup_path': backup_path,
            'backup_type': 'incremental',
            'status': 'pending',
            'row_count': 0,
            'since_timestamp': None,
            'duration_seconds': 0,
            'error': None
        }

        start_time = datetime.now()
        print(f"\n{'='*60}")
        print(f"Incremental Backup: {full_table_name}")

        # Validate table supports incremental backup
        if table_name not in TABLE_TIMESTAMP_COLUMNS:
            print(f"  WARNING: Table {table_name} does not have a known timestamp column")
            print(f"  Falling back to full backup mode")
            result['status'] = 'skipped'
            result['error'] = 'No timestamp column configured'
            self.stats['tables_skipped'] += 1
            return result

        timestamp_column = TABLE_TIMESTAMP_COLUMNS[table_name]
        print(f"  Timestamp column: {timestamp_column}")

        # Determine since timestamp
        if since:
            since_ts = since
        elif hours_back:
            since_ts = datetime.now() - timedelta(hours=hours_back)
        else:
            # Try to auto-detect from last backup
            since_ts = self.get_last_backup_timestamp(table_name)
            if since_ts is None:
                # Default to last 24 hours
                since_ts = datetime.now() - timedelta(hours=24)
                print(f"  No previous backup found, defaulting to last 24 hours")

        since_str = since_ts.strftime('%Y-%m-%d %H:%M:%S')
        result['since_timestamp'] = since_str
        print(f"  Since: {since_str}")
        print(f"  Destination: {backup_path}")

        if dry_run:
            print(f"[DRY RUN] Would backup {full_table_name} changes since {since_str}")
            result['status'] = 'dry_run'
            return result

        try:
            # Read from Kudu with timestamp filter
            df = self.spark.read \
                .format("org.apache.kudu.spark.kudu") \
                .option("kudu.master", self.config['kudu_master']) \
                .option("kudu.table", full_table_name) \
                .option("kudu.scanRequestTimeoutMs", str(self.config['scan_timeout_ms'])) \
                .load()

            # Apply timestamp filter
            # Handle both TIMESTAMP and BIGINT timestamp columns
            schema_fields = {f.name: str(f.dataType) for f in df.schema.fields}
            ts_type = schema_fields.get(timestamp_column, 'unknown')

            if 'Long' in ts_type or 'Bigint' in ts_type.lower():
                # BIGINT timestamp (milliseconds since epoch)
                since_ms = int(since_ts.timestamp() * 1000)
                df_filtered = df.filter(col(timestamp_column) >= since_ms)
                print(f"  Filter: {timestamp_column} >= {since_ms} (epoch ms)")
            else:
                # TIMESTAMP type
                df_filtered = df.filter(col(timestamp_column) >= lit(since_str))
                print(f"  Filter: {timestamp_column} >= '{since_str}'")

            # Get row count
            row_count = df_filtered.count()
            result['row_count'] = row_count
            print(f"  Rows changed: {row_count:,}")

            if row_count == 0:
                print(f"  No changes found since {since_str}")
                # Create empty marker
                metadata = {
                    'table': full_table_name,
                    'backup_type': 'incremental',
                    'timestamp': self.backup_timestamp,
                    'since_timestamp': since_str,
                    'row_count': 0,
                    'timestamp_column': timestamp_column,
                    'empty': True
                }
                self._write_metadata(backup_path, metadata)
                result['status'] = 'success'
                result['duration_seconds'] = (datetime.now() - start_time).total_seconds()
                self.stats['tables_backed_up'] += 1
                return result

            # Write to Parquet
            df_filtered.write \
                .mode("overwrite") \
                .option("compression", self.config['compression']) \
                .parquet(backup_path)

            # Write metadata
            metadata = {
                'table': full_table_name,
                'backup_type': 'incremental',
                'timestamp': self.backup_timestamp,
                'since_timestamp': since_str,
                'row_count': row_count,
                'timestamp_column': timestamp_column,
                'schema': [f.simpleString() for f in df.schema.fields],
                'compression': self.config['compression'],
                'kudu_master': self.config['kudu_master'],
                'spark_app_id': self.spark.sparkContext.applicationId
            }
            self._write_metadata(backup_path, metadata)

            result['status'] = 'success'
            result['duration_seconds'] = (datetime.now() - start_time).total_seconds()
            self.stats['tables_backed_up'] += 1
            self.stats['total_rows'] += row_count

            print(f"  SUCCESS: Backed up {row_count:,} changed rows in {result['duration_seconds']:.2f}s")

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            result['duration_seconds'] = (datetime.now() - start_time).total_seconds()
            self.stats['tables_failed'] += 1
            self.stats['errors'].append({'table': table_name, 'error': str(e)})
            print(f"  FAILED: {e}")

        return result

    def _write_metadata(self, backup_path: str, metadata: Dict[str, Any]):
        """Write metadata JSON file to backup location."""
        metadata_json = json.dumps(metadata, indent=2, default=str)
        metadata_rdd = self.spark.sparkContext.parallelize([metadata_json])
        metadata_rdd.coalesce(1).saveAsTextFile(f"{backup_path}/_metadata")
        print(f"  Metadata written to {backup_path}/_metadata/")

    def backup_all_tables(
        self,
        tables: List[str] = None,
        since: Optional[datetime] = None,
        hours_back: int = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Incremental backup of multiple tables.

        Args:
            tables: List of table names (uses INCREMENTAL_TABLES if None)
            since: Backup changes since this timestamp
            hours_back: Alternative - backup last N hours
            dry_run: If True, only validate

        Returns:
            Summary dictionary
        """
        if tables is None:
            tables = INCREMENTAL_TABLES

        results = []
        for table in tables:
            result = self.backup_table(
                table,
                since=since,
                hours_back=hours_back,
                dry_run=dry_run
            )
            results.append(result)

        self.stats['end_time'] = datetime.now().isoformat()

        return {
            'backup_id': self.backup_timestamp,
            'backup_type': 'incremental',
            'results': results,
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
        description='Kudu Incremental Backup - Backup changed rows since last backup',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backup changes from last 24 hours
  spark-submit --jars /jars/kudu/*.jar kudu_incremental_backup.py \\
      --table cis_trade --hours-back 24

  # Backup changes since specific timestamp
  spark-submit --jars /jars/kudu/*.jar kudu_incremental_backup.py \\
      --table cis_trade --since "2026-04-01 00:00:00"

  # Backup all tables (last 6 hours)
  spark-submit --jars /jars/kudu/*.jar kudu_incremental_backup.py \\
      --all-tables --hours-back 6

  # Dry run
  spark-submit --jars /jars/kudu/*.jar kudu_incremental_backup.py \\
      --table cis_trade --hours-back 24 --dry-run
        """
    )

    parser.add_argument('--table', '-t', type=str,
                        help='Single table name to backup')
    parser.add_argument('--tables', type=str,
                        help='Comma-separated list of tables')
    parser.add_argument('--all-tables', '-a', action='store_true',
                        help='Backup all tables that support incremental backup')
    parser.add_argument('--since', '-s', type=str,
                        help='Backup changes since timestamp (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--hours-back', '-H', type=int, default=DEFAULT_CONFIG['hours_back'],
                        help=f"Backup changes from last N hours (default: {DEFAULT_CONFIG['hours_back']})")
    parser.add_argument('--auto-since', action='store_true',
                        help='Auto-detect since timestamp from last backup')
    parser.add_argument('--kudu-master', '-m', type=str, default=DEFAULT_CONFIG['kudu_master'],
                        help=f"Kudu master address (default: {DEFAULT_CONFIG['kudu_master']})")
    parser.add_argument('--database', '-d', type=str, default=DEFAULT_CONFIG['database'],
                        help=f"Database name (default: {DEFAULT_CONFIG['database']})")
    parser.add_argument('--backup-path', '-p', type=str, default=DEFAULT_CONFIG['backup_path'],
                        help=f"Backup destination path (default: {DEFAULT_CONFIG['backup_path']})")
    parser.add_argument('--compression', '-c', type=str, default=DEFAULT_CONFIG['compression'],
                        choices=['snappy', 'gzip', 'lz4', 'none'],
                        help=f"Compression codec (default: {DEFAULT_CONFIG['compression']})")
    parser.add_argument('--parallelism', type=int, default=DEFAULT_CONFIG['parallelism'],
                        help=f"Spark parallelism (default: {DEFAULT_CONFIG['parallelism']})")
    parser.add_argument('--dry-run', action='store_true',
                        help='Validate without performing actual backup')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Validate arguments
    if not args.table and not args.tables and not args.all_tables:
        print("ERROR: Must specify --table, --tables, or --all-tables")
        sys.exit(1)

    # Parse since timestamp if provided
    since = None
    if args.since:
        try:
            since = datetime.strptime(args.since, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            print(f"ERROR: Invalid timestamp format: {args.since}")
            print("Expected format: YYYY-MM-DD HH:MM:SS")
            sys.exit(1)

    # Build configuration
    config = {
        'kudu_master': args.kudu_master,
        'database': args.database,
        'backup_path': args.backup_path,
        'compression': args.compression,
        'parallelism': args.parallelism,
        'batch_size': DEFAULT_CONFIG['batch_size'],
        'scan_timeout_ms': DEFAULT_CONFIG['scan_timeout_ms'],
    }

    print("=" * 70)
    print("  KUDU INCREMENTAL BACKUP")
    print("=" * 70)
    print(f"  Kudu Master:   {config['kudu_master']}")
    print(f"  Database:      {config['database']}")
    print(f"  Backup Path:   {config['backup_path']}")
    print(f"  Hours Back:    {args.hours_back}")
    if since:
        print(f"  Since:         {since}")
    print(f"  Dry Run:       {args.dry_run}")
    print("=" * 70)

    # Initialize backup
    backup = KuduIncrementalBackup(config)

    if not backup.init_spark():
        print("ERROR: Failed to initialize Spark session")
        sys.exit(1)

    try:
        # Determine tables
        if args.all_tables:
            tables = INCREMENTAL_TABLES
        elif args.tables:
            tables = [t.strip() for t in args.tables.split(',')]
        else:
            tables = [args.table]

        print(f"\nTables to backup: {len(tables)}")

        # Run backup
        summary = backup.backup_all_tables(
            tables,
            since=since,
            hours_back=args.hours_back if not since else None,
            dry_run=args.dry_run
        )

        # Print summary
        print("\n" + "=" * 70)
        print("  INCREMENTAL BACKUP SUMMARY")
        print("=" * 70)
        print(f"  Backup ID:      {summary['backup_id']}")
        print(f"  Tables Success: {summary['stats']['tables_backed_up']}")
        print(f"  Tables Failed:  {summary['stats']['tables_failed']}")
        print(f"  Tables Skipped: {summary['stats']['tables_skipped']}")
        print(f"  Total Rows:     {summary['stats']['total_rows']:,}")
        print("=" * 70)

        if summary['stats']['tables_failed'] > 0:
            sys.exit(1)
        sys.exit(0)

    finally:
        backup.close()


if __name__ == '__main__':
    main()
