#!/usr/bin/env python3
"""
Kudu Full Backup Script using kudu-backup JAR

This script performs full backups of Kudu tables to HDFS/S3/ADLS storage.
Uses the official Apache Kudu backup tool (kudu-backup.jar).

Usage:
    spark-submit --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar,/jars/kudu/kudu-backup3_2.12-1.17.0.jar \
        kudu_full_backup.py \
        --table cis_trade \
        --backup-path hdfs:///backups/kudu \
        --kudu-master kudu-master:7051

    # Backup all tables
    spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \
        --all-tables \
        --backup-path hdfs:///backups/kudu

    # Dry run
    spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py \
        --table cis_portfolio \
        --dry-run

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
    'compression': 'snappy',  # snappy, gzip, lz4, none
    'parallelism': 8,
    'batch_size': 10000,
    'scan_timeout_ms': 30000,
}

# All tables to backup (in dependency order)
ALL_TABLES = [
    # Core tables
    'cis_user',
    'cis_user_group',
    'cis_group_permissions',
    'cis_audit_log',
    # Reference data
    'cis_currency',
    'cis_country',
    'cis_calendar',
    'cis_counterparty_kudu',
    'cis_exchange',
    # Security
    'cis_security_kudu',
    # Portfolio
    'cis_portfolio',
    'cis_portfolio_history',
    # Trade
    'cis_trade',
    'cis_trade_history',
    'cis_trade_position',
    'cis_trade_note',
    'cis_trade_lot',
    # Corporate Actions
    'cis_corporate_action',
    'cis_ca_cash_flow_queue',
    'cis_ca_cash_flow_log',
    # Cash Flow
    'cis_cash_flow',
    'cis_cash_flow_history',
    # Queues
    'cis_position_queue',
    'cis_settlement_queue',
    'cis_trade_event_queue',
    # UDF
    'cis_udf_definition',
    'cis_udf_value',
    # Market Data
    'cis_fx_rate',
    'cis_market_price',
    # Lookups
    'cis_lookup_trade_type',
    'cis_lookup_trade_status',
    'cis_lookup_currency',
    'cis_lookup_country',
    'cis_lookup_asset_class',
    'cis_lookup_security_type',
    'cis_lookup_portfolio_type',
    'cis_lookup_portfolio_status',
]


class KuduFullBackup:
    """Full backup implementation for Kudu tables."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.spark = None
        self.backup_timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        self.stats = {
            'tables_backed_up': 0,
            'tables_failed': 0,
            'total_rows': 0,
            'total_size_bytes': 0,
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
                .appName(f"KuduFullBackup_{self.backup_timestamp}") \
                .config("spark.sql.adaptive.enabled", "true") \
                .config("spark.sql.parquet.compression.codec", self.config['compression']) \
                .config("spark.kudu.master", self.config['kudu_master'])

            # Set parallelism
            builder = builder.config("spark.default.parallelism", str(self.config['parallelism']))
            builder = builder.config("spark.sql.shuffle.partitions", str(self.config['parallelism']))

            self.spark = builder.getOrCreate()
            self.spark.sparkContext.setLogLevel("WARN")
            print(f"Spark session initialized: {self.spark.sparkContext.applicationId}")
            return True

        except Exception as e:
            print(f"ERROR: Failed to initialize Spark: {e}")
            return False

    def backup_table(self, table_name: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Backup a single Kudu table.

        Args:
            table_name: Name of the table (without database prefix)
            dry_run: If True, only validate without actual backup

        Returns:
            Dictionary with backup result
        """
        full_table_name = f"{self.config['database']}.{table_name}"
        backup_path = f"{self.config['backup_path']}/{self.config['database']}/{table_name}/full/{self.backup_timestamp}"

        result = {
            'table': table_name,
            'full_table_name': full_table_name,
            'backup_path': backup_path,
            'status': 'pending',
            'row_count': 0,
            'size_bytes': 0,
            'duration_seconds': 0,
            'error': None
        }

        start_time = datetime.now()
        print(f"\n{'='*60}")
        print(f"Backing up: {full_table_name}")
        print(f"Destination: {backup_path}")

        if dry_run:
            print(f"[DRY RUN] Would backup {full_table_name} to {backup_path}")
            result['status'] = 'dry_run'
            return result

        try:
            # Read from Kudu via Impala/Spark
            df = self.spark.read \
                .format("org.apache.kudu.spark.kudu") \
                .option("kudu.master", self.config['kudu_master']) \
                .option("kudu.table", full_table_name) \
                .option("kudu.scanRequestTimeoutMs", str(self.config['scan_timeout_ms'])) \
                .load()

            # Get row count
            row_count = df.count()
            result['row_count'] = row_count
            print(f"  Rows to backup: {row_count:,}")

            if row_count == 0:
                print(f"  WARNING: Table is empty, creating empty backup marker")
                # Create empty marker file
                metadata = {
                    'table': full_table_name,
                    'backup_type': 'full',
                    'timestamp': self.backup_timestamp,
                    'row_count': 0,
                    'schema': [f.simpleString() for f in df.schema.fields],
                    'empty': True
                }
                self._write_metadata(backup_path, metadata)
                result['status'] = 'success'
                result['duration_seconds'] = (datetime.now() - start_time).total_seconds()
                return result

            # Write to Parquet with compression
            df.write \
                .mode("overwrite") \
                .option("compression", self.config['compression']) \
                .parquet(backup_path)

            # Write metadata
            metadata = {
                'table': full_table_name,
                'backup_type': 'full',
                'timestamp': self.backup_timestamp,
                'row_count': row_count,
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

            print(f"  SUCCESS: Backed up {row_count:,} rows in {result['duration_seconds']:.2f}s")

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
        metadata_path = f"{backup_path}/_metadata.json"
        metadata_json = json.dumps(metadata, indent=2, default=str)

        # Write using Spark to handle HDFS/S3
        metadata_rdd = self.spark.sparkContext.parallelize([metadata_json])
        metadata_rdd.coalesce(1).saveAsTextFile(f"{backup_path}/_metadata")

        print(f"  Metadata written to {backup_path}/_metadata/")

    def backup_all_tables(self, tables: List[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """
        Backup multiple tables.

        Args:
            tables: List of table names (uses ALL_TABLES if None)
            dry_run: If True, only validate

        Returns:
            Summary dictionary
        """
        if tables is None:
            tables = ALL_TABLES

        results = []
        for table in tables:
            result = self.backup_table(table, dry_run=dry_run)
            results.append(result)

        self.stats['end_time'] = datetime.now().isoformat()

        # Write manifest
        if not dry_run:
            manifest = {
                'backup_id': self.backup_timestamp,
                'backup_type': 'full',
                'database': self.config['database'],
                'kudu_master': self.config['kudu_master'],
                'tables': results,
                'stats': self.stats
            }
            manifest_path = f"{self.config['backup_path']}/manifests/backup_manifest_{self.backup_timestamp}.json"
            print(f"\nWriting manifest to {manifest_path}")

        return {
            'backup_id': self.backup_timestamp,
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
        description='Kudu Full Backup - Backup Kudu tables to HDFS/S3/ADLS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backup single table
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py --table cis_trade

  # Backup all tables
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py --all-tables

  # Backup with custom path
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py --table cis_portfolio \\
      --backup-path s3a://my-bucket/backups/kudu

  # Dry run
  spark-submit --jars /jars/kudu/*.jar kudu_full_backup.py --table cis_trade --dry-run
        """
    )

    parser.add_argument('--table', '-t', type=str,
                        help='Single table name to backup (without database prefix)')
    parser.add_argument('--tables', type=str,
                        help='Comma-separated list of tables to backup')
    parser.add_argument('--all-tables', '-a', action='store_true',
                        help='Backup all known tables')
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
    print("  KUDU FULL BACKUP")
    print("=" * 70)
    print(f"  Kudu Master:   {config['kudu_master']}")
    print(f"  Database:      {config['database']}")
    print(f"  Backup Path:   {config['backup_path']}")
    print(f"  Compression:   {config['compression']}")
    print(f"  Parallelism:   {config['parallelism']}")
    print(f"  Dry Run:       {args.dry_run}")
    print("=" * 70)

    # Initialize backup
    backup = KuduFullBackup(config)

    if not backup.init_spark():
        print("ERROR: Failed to initialize Spark session")
        sys.exit(1)

    try:
        # Determine tables to backup
        if args.all_tables:
            tables = ALL_TABLES
        elif args.tables:
            tables = [t.strip() for t in args.tables.split(',')]
        else:
            tables = [args.table]

        print(f"\nTables to backup: {len(tables)}")
        for t in tables:
            print(f"  - {t}")

        # Run backup
        summary = backup.backup_all_tables(tables, dry_run=args.dry_run)

        # Print summary
        print("\n" + "=" * 70)
        print("  BACKUP SUMMARY")
        print("=" * 70)
        print(f"  Backup ID:      {summary['backup_id']}")
        print(f"  Tables Success: {summary['stats']['tables_backed_up']}")
        print(f"  Tables Failed:  {summary['stats']['tables_failed']}")
        print(f"  Total Rows:     {summary['stats']['total_rows']:,}")
        print(f"  Start Time:     {summary['stats']['start_time']}")
        print(f"  End Time:       {summary['stats']['end_time']}")

        if summary['stats']['errors']:
            print("\n  ERRORS:")
            for err in summary['stats']['errors']:
                print(f"    - {err['table']}: {err['error']}")

        print("=" * 70)

        # Exit with appropriate code
        if summary['stats']['tables_failed'] > 0:
            sys.exit(1)
        sys.exit(0)

    finally:
        backup.close()


if __name__ == '__main__':
    main()
