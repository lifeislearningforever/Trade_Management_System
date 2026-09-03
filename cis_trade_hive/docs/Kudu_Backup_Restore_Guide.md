# Kudu Backup and Restore Guide
## PySpark Jobs with kudu-backup.jar

**Document Version:** 1.0
**Date:** 2026-01-22
**Domain:** Banking / Trade Management System
**Author:** CIS Trade Hive Team

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Prerequisites](#3-prerequisites)
4. [Backup Strategies](#4-backup-strategies)
5. [PySpark Job Implementations](#5-pyspark-job-implementations)
6. [Job Parameters Reference](#6-job-parameters-reference)
7. [Scheduling and Automation](#7-scheduling-and-automation)
8. [Monitoring and Validation](#8-monitoring-and-validation)
9. [Disaster Recovery Procedures](#9-disaster-recovery-procedures)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview

This document provides a comprehensive guide for implementing Kudu backup and restore operations using PySpark with the official `kudu-backup.jar` library. The solution supports:

- **Full Backup**: Complete table snapshot
- **Incremental Backup**: Changes since last backup (using timestamps)
- **Full Restore**: Complete table restoration
- **Incremental Restore**: Apply incremental changes
- **Cross-Cluster Migration**: Move data between environments

### Key Benefits

| Feature | Description |
|---------|-------------|
| Parameterized Jobs | Flexible configuration via command-line arguments |
| Parallel Processing | Leverages Spark's distributed computing |
| Checkpoint Support | Resume interrupted backups |
| Compression | Reduces storage costs (Snappy/GZIP/LZ4) |
| Schema Evolution | Handles schema changes gracefully |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     KUDU BACKUP/RESTORE ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────┐     ┌─────────────────┐     ┌─────────────────────┐   │
│   │   Kudu      │     │   PySpark Job   │     │   HDFS/S3/ADLS      │   │
│   │   Cluster   │◄───►│   (Backup/      │◄───►│   (Backup Storage)  │   │
│   │             │     │    Restore)     │     │                     │   │
│   └─────────────┘     └─────────────────┘     └─────────────────────┘   │
│         │                     │                         │               │
│         │              ┌──────┴──────┐                  │               │
│         │              │             │                  │               │
│         ▼              ▼             ▼                  ▼               │
│   ┌───────────┐  ┌───────────┐ ┌───────────┐  ┌─────────────────┐      │
│   │  Tablet   │  │ kudu-     │ │  Spark    │  │  Backup Files   │      │
│   │  Servers  │  │ backup.jar│ │  Executor │  │  (Parquet +     │      │
│   │           │  │           │ │  Nodes    │  │   Metadata)     │      │
│   └───────────┘  └───────────┘ └───────────┘  └─────────────────┘      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Backup File Structure

```
/backups/kudu/
├── gmp_cis/
│   ├── cis_portfolio/
│   │   ├── full/
│   │   │   ├── 2026-01-22_000000/
│   │   │   │   ├── _metadata.json
│   │   │   │   ├── part-00000.parquet
│   │   │   │   └── part-00001.parquet
│   │   │   └── 2026-01-15_000000/
│   │   └── incremental/
│   │       ├── 2026-01-22_060000/
│   │       │   ├── _metadata.json
│   │       │   └── part-00000.parquet
│   │       └── 2026-01-21_060000/
│   ├── cis_trade/
│   │   ├── full/
│   │   └── incremental/
│   └── cis_security/
│       ├── full/
│       └── incremental/
└── manifests/
    ├── backup_manifest_2026-01-22.json
    └── restore_manifest_2026-01-22.json
```

---

## 3. Prerequisites

### 3.1 Required JAR Files

```bash
# Download Kudu Spark connector and backup JAR
# Version should match your Kudu cluster version

# For Kudu 1.17.x with Spark 3.x
wget https://repo1.maven.org/maven2/org/apache/kudu/kudu-spark3_2.12/1.17.0/kudu-spark3_2.12-1.17.0.jar
wget https://repo1.maven.org/maven2/org/apache/kudu/kudu-backup3_2.12/1.17.0/kudu-backup3_2.12-1.17.0.jar

# Place in HDFS for cluster access
hdfs dfs -mkdir -p /jars/kudu
hdfs dfs -put kudu-spark3_2.12-1.17.0.jar /jars/kudu/
hdfs dfs -put kudu-backup3_2.12-1.17.0.jar /jars/kudu/
```

### 3.2 Environment Configuration

```bash
# spark-env.sh additions
export KUDU_MASTER="kudu-master-1:7051,kudu-master-2:7051,kudu-master-3:7051"
export BACKUP_PATH="hdfs:///backups/kudu"
export SPARK_JARS="/jars/kudu/kudu-spark3_2.12-1.17.0.jar,/jars/kudu/kudu-backup3_2.12-1.17.0.jar"
```

### 3.3 Python Dependencies

```bash
pip install pyspark==3.4.0
pip install argparse
pip install json
pip install datetime
```

---

## 4. Backup Strategies

### 4.1 Backup Schedule Matrix

| Table | Full Backup | Incremental | Retention |
|-------|-------------|-------------|-----------|
| cis_portfolio | Weekly (Sunday 00:00) | Daily 06:00 | 30 days |
| cis_trade | Weekly (Sunday 00:00) | Every 6 hours | 30 days |
| cis_security | Weekly (Sunday 00:00) | Daily 06:00 | 30 days |
| cis_audit_log | Monthly (1st 00:00) | Daily 00:00 | 90 days |
| cis_counterparty | Weekly (Sunday 00:00) | Daily 06:00 | 30 days |

### 4.2 Storage Estimation

| Table | Rows | Full Backup Size | Daily Incremental |
|-------|------|------------------|-------------------|
| cis_portfolio | 10K | ~50 MB | ~5 MB |
| cis_trade | 1M | ~5 GB | ~500 MB |
| cis_security | 50K | ~200 MB | ~20 MB |
| cis_audit_log | 10M | ~50 GB | ~1 GB |

---

## 5. PySpark Job Implementations

### 5.1 Full Backup Job

**File:** `kudu_full_backup.py`

```python
#!/usr/bin/env python3
"""
Kudu Full Backup PySpark Job
============================
Performs a complete backup of specified Kudu tables to HDFS/S3.

Usage:
    spark-submit --jars kudu-spark3_2.12-1.17.0.jar,kudu-backup3_2.12-1.17.0.jar \
        kudu_full_backup.py \
        --kudu-master kudu-master-1:7051,kudu-master-2:7051 \
        --tables cis_portfolio,cis_trade \
        --database gmp_cis \
        --backup-path hdfs:///backups/kudu \
        --compression snappy \
        --parallelism 16
"""

import argparse
import json
import sys
from datetime import datetime
from pyspark.sql import SparkSession


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Kudu Full Backup Job',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Required arguments
    parser.add_argument(
        '--kudu-master',
        required=True,
        help='Kudu master addresses (comma-separated)'
    )
    parser.add_argument(
        '--tables',
        required=True,
        help='Tables to backup (comma-separated) or "ALL" for all tables'
    )
    parser.add_argument(
        '--database',
        required=True,
        help='Database name (e.g., gmp_cis)'
    )
    parser.add_argument(
        '--backup-path',
        required=True,
        help='Base backup path (HDFS/S3/ADLS)'
    )

    # Optional arguments
    parser.add_argument(
        '--compression',
        default='snappy',
        choices=['snappy', 'gzip', 'lz4', 'none'],
        help='Compression codec (default: snappy)'
    )
    parser.add_argument(
        '--parallelism',
        type=int,
        default=8,
        help='Number of parallel tasks (default: 8)'
    )
    parser.add_argument(
        '--scan-batch-size',
        type=int,
        default=1024,
        help='Kudu scan batch size (default: 1024)'
    )
    parser.add_argument(
        '--scan-request-timeout',
        type=int,
        default=30000,
        help='Kudu scan timeout in ms (default: 30000)'
    )
    parser.add_argument(
        '--partition-by',
        default=None,
        help='Column to partition backup files by (optional)'
    )
    parser.add_argument(
        '--where-clause',
        default=None,
        help='Filter condition for backup (optional)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print backup plan without executing'
    )

    return parser.parse_args()


def create_spark_session(app_name, kudu_master):
    """Create and configure Spark session."""
    return SparkSession.builder \
        .appName(app_name) \
        .config("spark.kudu.master", kudu_master) \
        .config("spark.sql.parquet.compression.codec", "snappy") \
        .config("spark.sql.shuffle.partitions", "200") \
        .getOrCreate()


def get_table_list(spark, kudu_master, database, tables_arg):
    """Get list of tables to backup."""
    if tables_arg.upper() == 'ALL':
        # Query Kudu for all tables in database
        # Using Impala catalog or Kudu client
        df = spark.read \
            .format("kudu") \
            .option("kudu.master", kudu_master) \
            .option("kudu.table", f"impala::{database}.information_schema.tables") \
            .load()
        return [row.table_name for row in df.collect()]
    else:
        return [t.strip() for t in tables_arg.split(',')]


def backup_table(spark, kudu_master, database, table, backup_path, args):
    """Perform full backup of a single table."""
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    full_table_name = f"impala::{database}.{table}"
    output_path = f"{backup_path}/{database}/{table}/full/{timestamp}"

    print(f"\n{'='*60}")
    print(f"Backing up: {full_table_name}")
    print(f"Output: {output_path}")
    print(f"{'='*60}")

    # Read from Kudu
    reader = spark.read \
        .format("kudu") \
        .option("kudu.master", kudu_master) \
        .option("kudu.table", full_table_name) \
        .option("kudu.scanRequestTimeoutMs", str(args.scan_request_timeout)) \
        .option("kudu.batchSize", str(args.scan_batch_size))

    df = reader.load()

    # Apply filter if specified
    if args.where_clause:
        df = df.where(args.where_clause)

    # Get row count
    row_count = df.count()
    print(f"Total rows to backup: {row_count:,}")

    if args.dry_run:
        print(f"DRY RUN: Would backup {row_count:,} rows")
        return {
            'table': table,
            'status': 'DRY_RUN',
            'rows': row_count,
            'path': output_path
        }

    # Write backup
    writer = df.repartition(args.parallelism)

    if args.partition_by:
        writer = writer.partitionBy(args.partition_by)

    writer.write \
        .mode('overwrite') \
        .option("compression", args.compression) \
        .parquet(output_path)

    # Write metadata
    metadata = {
        'table': full_table_name,
        'backup_type': 'FULL',
        'timestamp': timestamp,
        'row_count': row_count,
        'schema': df.schema.json(),
        'compression': args.compression,
        'partitions': args.parallelism,
        'filter': args.where_clause
    }

    metadata_path = f"{output_path}/_metadata.json"
    spark.sparkContext.parallelize([json.dumps(metadata, indent=2)]) \
        .coalesce(1) \
        .saveAsTextFile(metadata_path)

    print(f"Backup completed: {row_count:,} rows written to {output_path}")

    return {
        'table': table,
        'status': 'SUCCESS',
        'rows': row_count,
        'path': output_path,
        'metadata': metadata
    }


def main():
    """Main entry point."""
    args = parse_arguments()

    print("\n" + "="*60)
    print("KUDU FULL BACKUP JOB")
    print("="*60)
    print(f"Kudu Master: {args.kudu_master}")
    print(f"Database: {args.database}")
    print(f"Tables: {args.tables}")
    print(f"Backup Path: {args.backup_path}")
    print(f"Compression: {args.compression}")
    print(f"Parallelism: {args.parallelism}")
    print(f"Dry Run: {args.dry_run}")
    print("="*60 + "\n")

    # Create Spark session
    spark = create_spark_session(
        f"KuduFullBackup_{args.database}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        args.kudu_master
    )

    try:
        # Get table list
        tables = get_table_list(spark, args.kudu_master, args.database, args.tables)
        print(f"Tables to backup: {tables}")

        # Backup each table
        results = []
        for table in tables:
            try:
                result = backup_table(
                    spark, args.kudu_master, args.database,
                    table, args.backup_path, args
                )
                results.append(result)
            except Exception as e:
                print(f"ERROR backing up {table}: {str(e)}")
                results.append({
                    'table': table,
                    'status': 'FAILED',
                    'error': str(e)
                })

        # Print summary
        print("\n" + "="*60)
        print("BACKUP SUMMARY")
        print("="*60)

        success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
        total_rows = sum(r.get('rows', 0) for r in results if r['status'] == 'SUCCESS')

        for result in results:
            status_icon = "✓" if result['status'] == 'SUCCESS' else "✗"
            print(f"{status_icon} {result['table']}: {result['status']} - {result.get('rows', 'N/A')} rows")

        print(f"\nTotal: {success_count}/{len(tables)} tables backed up")
        print(f"Total rows: {total_rows:,}")
        print("="*60)

        # Return exit code based on results
        if success_count == len(tables):
            sys.exit(0)
        else:
            sys.exit(1)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
```

### 5.2 Incremental Backup Job

**File:** `kudu_incremental_backup.py`

```python
#!/usr/bin/env python3
"""
Kudu Incremental Backup PySpark Job
====================================
Backs up only rows changed since the last backup timestamp.

Usage:
    spark-submit --jars kudu-spark3_2.12-1.17.0.jar,kudu-backup3_2.12-1.17.0.jar \
        kudu_incremental_backup.py \
        --kudu-master kudu-master-1:7051,kudu-master-2:7051 \
        --tables cis_portfolio,cis_trade \
        --database gmp_cis \
        --backup-path hdfs:///backups/kudu \
        --timestamp-column updated_at \
        --since "2026-01-21 00:00:00" \
        --compression snappy
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, max as spark_max


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Kudu Incremental Backup Job',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Required arguments
    parser.add_argument(
        '--kudu-master',
        required=True,
        help='Kudu master addresses (comma-separated)'
    )
    parser.add_argument(
        '--tables',
        required=True,
        help='Tables to backup (comma-separated)'
    )
    parser.add_argument(
        '--database',
        required=True,
        help='Database name (e.g., gmp_cis)'
    )
    parser.add_argument(
        '--backup-path',
        required=True,
        help='Base backup path (HDFS/S3/ADLS)'
    )
    parser.add_argument(
        '--timestamp-column',
        required=True,
        help='Column to use for incremental detection (e.g., updated_at)'
    )

    # Optional arguments
    parser.add_argument(
        '--since',
        default=None,
        help='Backup changes since this timestamp (YYYY-MM-DD HH:MM:SS). '
             'If not specified, reads from last backup manifest.'
    )
    parser.add_argument(
        '--hours-back',
        type=int,
        default=None,
        help='Alternative to --since: backup last N hours'
    )
    parser.add_argument(
        '--compression',
        default='snappy',
        choices=['snappy', 'gzip', 'lz4', 'none'],
        help='Compression codec (default: snappy)'
    )
    parser.add_argument(
        '--parallelism',
        type=int,
        default=8,
        help='Number of parallel tasks (default: 8)'
    )
    parser.add_argument(
        '--include-deletes',
        action='store_true',
        help='Also capture deleted records (requires delete tracking column)'
    )
    parser.add_argument(
        '--delete-column',
        default='is_deleted',
        help='Column that marks deleted records'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print backup plan without executing'
    )

    return parser.parse_args()


def create_spark_session(app_name, kudu_master):
    """Create and configure Spark session."""
    return SparkSession.builder \
        .appName(app_name) \
        .config("spark.kudu.master", kudu_master) \
        .config("spark.sql.parquet.compression.codec", "snappy") \
        .getOrCreate()


def get_last_backup_timestamp(spark, backup_path, database, table):
    """Get the timestamp of the last successful backup."""
    try:
        # Check incremental backups first
        inc_path = f"{backup_path}/{database}/{table}/incremental"

        # Read metadata from latest backup
        from pyspark.sql.functions import input_file_name

        metadata_df = spark.read.json(f"{inc_path}/*/_metadata.json")
        if metadata_df.count() > 0:
            latest = metadata_df.agg(spark_max("timestamp")).collect()[0][0]
            return datetime.strptime(latest, '%Y-%m-%d_%H%M%S')
    except Exception as e:
        print(f"No previous incremental backup found: {e}")

    try:
        # Fall back to full backup
        full_path = f"{backup_path}/{database}/{table}/full"
        metadata_df = spark.read.json(f"{full_path}/*/_metadata.json")
        if metadata_df.count() > 0:
            latest = metadata_df.agg(spark_max("timestamp")).collect()[0][0]
            return datetime.strptime(latest, '%Y-%m-%d_%H%M%S')
    except Exception as e:
        print(f"No previous full backup found: {e}")

    return None


def incremental_backup_table(spark, kudu_master, database, table, backup_path,
                              timestamp_col, since_timestamp, args):
    """Perform incremental backup of a single table."""
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    full_table_name = f"impala::{database}.{table}"
    output_path = f"{backup_path}/{database}/{table}/incremental/{timestamp}"

    print(f"\n{'='*60}")
    print(f"Incremental Backup: {full_table_name}")
    print(f"Changes since: {since_timestamp}")
    print(f"Output: {output_path}")
    print(f"{'='*60}")

    # Read from Kudu with filter
    df = spark.read \
        .format("kudu") \
        .option("kudu.master", kudu_master) \
        .option("kudu.table", full_table_name) \
        .load()

    # Apply incremental filter
    df_incremental = df.filter(col(timestamp_col) >= since_timestamp)

    # Include deletes if requested
    if args.include_deletes and args.delete_column in df.columns:
        df_deleted = df.filter(
            (col(args.delete_column) == True) &
            (col(timestamp_col) >= since_timestamp)
        )
        df_incremental = df_incremental.union(df_deleted)

    # Get counts
    row_count = df_incremental.count()
    print(f"Rows changed since {since_timestamp}: {row_count:,}")

    if row_count == 0:
        print("No changes detected, skipping backup")
        return {
            'table': table,
            'status': 'NO_CHANGES',
            'rows': 0,
            'since': str(since_timestamp)
        }

    if args.dry_run:
        print(f"DRY RUN: Would backup {row_count:,} changed rows")
        return {
            'table': table,
            'status': 'DRY_RUN',
            'rows': row_count,
            'path': output_path
        }

    # Write backup
    df_incremental.repartition(args.parallelism) \
        .write \
        .mode('overwrite') \
        .option("compression", args.compression) \
        .parquet(output_path)

    # Write metadata
    metadata = {
        'table': full_table_name,
        'backup_type': 'INCREMENTAL',
        'timestamp': timestamp,
        'since_timestamp': str(since_timestamp),
        'row_count': row_count,
        'schema': df.schema.json(),
        'timestamp_column': timestamp_col,
        'compression': args.compression,
        'include_deletes': args.include_deletes
    }

    metadata_path = f"{output_path}/_metadata.json"
    spark.sparkContext.parallelize([json.dumps(metadata, indent=2)]) \
        .coalesce(1) \
        .saveAsTextFile(metadata_path)

    print(f"Incremental backup completed: {row_count:,} rows")

    return {
        'table': table,
        'status': 'SUCCESS',
        'rows': row_count,
        'path': output_path,
        'since': str(since_timestamp),
        'metadata': metadata
    }


def main():
    """Main entry point."""
    args = parse_arguments()

    print("\n" + "="*60)
    print("KUDU INCREMENTAL BACKUP JOB")
    print("="*60)
    print(f"Kudu Master: {args.kudu_master}")
    print(f"Database: {args.database}")
    print(f"Tables: {args.tables}")
    print(f"Timestamp Column: {args.timestamp_column}")
    print(f"Backup Path: {args.backup_path}")
    print("="*60 + "\n")

    # Create Spark session
    spark = create_spark_session(
        f"KuduIncrementalBackup_{args.database}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        args.kudu_master
    )

    try:
        tables = [t.strip() for t in args.tables.split(',')]
        results = []

        for table in tables:
            # Determine since timestamp
            if args.since:
                since_ts = datetime.strptime(args.since, '%Y-%m-%d %H:%M:%S')
            elif args.hours_back:
                since_ts = datetime.now() - timedelta(hours=args.hours_back)
            else:
                # Get from last backup
                since_ts = get_last_backup_timestamp(
                    spark, args.backup_path, args.database, table
                )
                if not since_ts:
                    print(f"WARNING: No previous backup found for {table}, using 24 hours ago")
                    since_ts = datetime.now() - timedelta(hours=24)

            try:
                result = incremental_backup_table(
                    spark, args.kudu_master, args.database, table,
                    args.backup_path, args.timestamp_column, since_ts, args
                )
                results.append(result)
            except Exception as e:
                print(f"ERROR backing up {table}: {str(e)}")
                results.append({
                    'table': table,
                    'status': 'FAILED',
                    'error': str(e)
                })

        # Print summary
        print("\n" + "="*60)
        print("INCREMENTAL BACKUP SUMMARY")
        print("="*60)

        success_count = sum(1 for r in results if r['status'] in ['SUCCESS', 'NO_CHANGES'])
        total_rows = sum(r.get('rows', 0) for r in results)

        for result in results:
            status_icon = "✓" if result['status'] in ['SUCCESS', 'NO_CHANGES'] else "✗"
            print(f"{status_icon} {result['table']}: {result['status']} - {result.get('rows', 'N/A')} rows")

        print(f"\nTotal: {success_count}/{len(tables)} tables processed")
        print(f"Total incremental rows: {total_rows:,}")
        print("="*60)

        sys.exit(0 if success_count == len(tables) else 1)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
```

### 5.3 Full Restore Job

**File:** `kudu_full_restore.py`

```python
#!/usr/bin/env python3
"""
Kudu Full Restore PySpark Job
==============================
Restores a complete table from a full backup.

Usage:
    spark-submit --jars kudu-spark3_2.12-1.17.0.jar,kudu-backup3_2.12-1.17.0.jar \
        kudu_full_restore.py \
        --kudu-master kudu-master-1:7051,kudu-master-2:7051 \
        --tables cis_portfolio,cis_trade \
        --database gmp_cis \
        --backup-path hdfs:///backups/kudu \
        --backup-timestamp "2026-01-22_000000" \
        --restore-mode truncate_insert
"""

import argparse
import json
import sys
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Kudu Full Restore Job',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Required arguments
    parser.add_argument(
        '--kudu-master',
        required=True,
        help='Kudu master addresses (comma-separated)'
    )
    parser.add_argument(
        '--tables',
        required=True,
        help='Tables to restore (comma-separated)'
    )
    parser.add_argument(
        '--database',
        required=True,
        help='Database name (e.g., gmp_cis)'
    )
    parser.add_argument(
        '--backup-path',
        required=True,
        help='Base backup path (HDFS/S3/ADLS)'
    )

    # Optional arguments
    parser.add_argument(
        '--backup-timestamp',
        default='LATEST',
        help='Backup timestamp to restore (YYYY-MM-DD_HHMMSS) or LATEST'
    )
    parser.add_argument(
        '--restore-mode',
        default='truncate_insert',
        choices=['truncate_insert', 'upsert', 'insert_ignore', 'create_new'],
        help='Restore mode (default: truncate_insert)'
    )
    parser.add_argument(
        '--target-table-suffix',
        default='',
        help='Suffix for target table name (e.g., _restored)'
    )
    parser.add_argument(
        '--parallelism',
        type=int,
        default=8,
        help='Number of parallel tasks (default: 8)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10000,
        help='Write batch size (default: 10000)'
    )
    parser.add_argument(
        '--validate-count',
        action='store_true',
        help='Validate row count after restore'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print restore plan without executing'
    )

    return parser.parse_args()


def create_spark_session(app_name, kudu_master):
    """Create and configure Spark session."""
    return SparkSession.builder \
        .appName(app_name) \
        .config("spark.kudu.master", kudu_master) \
        .getOrCreate()


def get_latest_backup_timestamp(spark, backup_path, database, table):
    """Find the latest full backup timestamp."""
    full_path = f"{backup_path}/{database}/{table}/full"

    try:
        # List directories and find latest
        hadoop_conf = spark._jsc.hadoopConfiguration()
        fs = spark._jvm.org.apache.hadoop.fs.FileSystem.get(
            spark._jvm.java.net.URI(backup_path), hadoop_conf
        )
        path = spark._jvm.org.apache.hadoop.fs.Path(full_path)

        if fs.exists(path):
            statuses = fs.listStatus(path)
            timestamps = []
            for status in statuses:
                if status.isDirectory():
                    dir_name = status.getPath().getName()
                    if not dir_name.startswith('_'):
                        timestamps.append(dir_name)

            if timestamps:
                return sorted(timestamps)[-1]  # Latest
    except Exception as e:
        print(f"Error finding latest backup: {e}")

    return None


def restore_table(spark, kudu_master, database, table, backup_path,
                  backup_timestamp, args):
    """Restore a single table from backup."""
    target_table = f"{table}{args.target_table_suffix}"
    full_table_name = f"impala::{database}.{target_table}"
    source_path = f"{backup_path}/{database}/{table}/full/{backup_timestamp}"

    print(f"\n{'='*60}")
    print(f"Restoring: {table}")
    print(f"Source: {source_path}")
    print(f"Target: {full_table_name}")
    print(f"Mode: {args.restore_mode}")
    print(f"{'='*60}")

    # Read backup data
    try:
        df_backup = spark.read.parquet(source_path)
    except Exception as e:
        print(f"ERROR: Cannot read backup from {source_path}: {e}")
        return {
            'table': table,
            'status': 'FAILED',
            'error': f"Cannot read backup: {e}"
        }

    backup_count = df_backup.count()
    print(f"Backup contains: {backup_count:,} rows")

    # Read metadata
    try:
        metadata_path = f"{source_path}/_metadata.json"
        metadata_df = spark.read.text(metadata_path)
        metadata = json.loads(metadata_df.first()[0])
        print(f"Backup timestamp: {metadata.get('timestamp')}")
        print(f"Original row count: {metadata.get('row_count')}")
    except Exception as e:
        print(f"Warning: Could not read metadata: {e}")
        metadata = {}

    if args.dry_run:
        print(f"DRY RUN: Would restore {backup_count:,} rows to {full_table_name}")
        return {
            'table': table,
            'status': 'DRY_RUN',
            'rows': backup_count
        }

    # Perform restore based on mode
    if args.restore_mode == 'truncate_insert':
        # Delete all existing data first
        print("Truncating target table...")

        # Read current table to get primary key
        try:
            df_current = spark.read \
                .format("kudu") \
                .option("kudu.master", kudu_master) \
                .option("kudu.table", full_table_name) \
                .load()

            # Kudu doesn't support TRUNCATE, so we delete all rows
            # This is done by reading and writing empty DataFrame
            # Or using Impala: TRUNCATE TABLE

            # For safety, using upsert mode which will overwrite
            df_backup.repartition(args.parallelism) \
                .write \
                .format("kudu") \
                .option("kudu.master", kudu_master) \
                .option("kudu.table", full_table_name) \
                .option("kudu.operation", "upsert") \
                .mode("append") \
                .save()

        except Exception as e:
            print(f"Table may not exist, creating new: {e}")
            args.restore_mode = 'create_new'

    if args.restore_mode == 'upsert':
        print("Upserting backup data...")
        df_backup.repartition(args.parallelism) \
            .write \
            .format("kudu") \
            .option("kudu.master", kudu_master) \
            .option("kudu.table", full_table_name) \
            .option("kudu.operation", "upsert") \
            .mode("append") \
            .save()

    elif args.restore_mode == 'insert_ignore':
        print("Inserting with ignore duplicates...")
        df_backup.repartition(args.parallelism) \
            .write \
            .format("kudu") \
            .option("kudu.master", kudu_master) \
            .option("kudu.table", full_table_name) \
            .option("kudu.operation", "insert_ignore") \
            .mode("append") \
            .save()

    elif args.restore_mode == 'create_new':
        print("Creating new table from backup...")
        # Note: This requires the table to be created first via Impala
        # Kudu Spark connector cannot create tables directly
        print("WARNING: Table must be created via Impala DDL first")
        df_backup.repartition(args.parallelism) \
            .write \
            .format("kudu") \
            .option("kudu.master", kudu_master) \
            .option("kudu.table", full_table_name) \
            .option("kudu.operation", "insert") \
            .mode("append") \
            .save()

    # Validate if requested
    restored_count = 0
    if args.validate_count:
        print("Validating restore...")
        df_restored = spark.read \
            .format("kudu") \
            .option("kudu.master", kudu_master) \
            .option("kudu.table", full_table_name) \
            .load()
        restored_count = df_restored.count()
        print(f"Restored row count: {restored_count:,}")

        if restored_count != backup_count:
            print(f"WARNING: Row count mismatch! Backup: {backup_count}, Restored: {restored_count}")

    print(f"Restore completed for {table}")

    return {
        'table': table,
        'status': 'SUCCESS',
        'rows_backup': backup_count,
        'rows_restored': restored_count if args.validate_count else backup_count,
        'backup_timestamp': backup_timestamp,
        'mode': args.restore_mode
    }


def main():
    """Main entry point."""
    args = parse_arguments()

    print("\n" + "="*60)
    print("KUDU FULL RESTORE JOB")
    print("="*60)
    print(f"Kudu Master: {args.kudu_master}")
    print(f"Database: {args.database}")
    print(f"Tables: {args.tables}")
    print(f"Backup Timestamp: {args.backup_timestamp}")
    print(f"Restore Mode: {args.restore_mode}")
    print(f"Target Suffix: {args.target_table_suffix or '(none)'}")
    print("="*60 + "\n")

    # Create Spark session
    spark = create_spark_session(
        f"KuduFullRestore_{args.database}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        args.kudu_master
    )

    try:
        tables = [t.strip() for t in args.tables.split(',')]
        results = []

        for table in tables:
            # Get backup timestamp
            if args.backup_timestamp == 'LATEST':
                backup_ts = get_latest_backup_timestamp(
                    spark, args.backup_path, args.database, table
                )
                if not backup_ts:
                    print(f"ERROR: No backup found for {table}")
                    results.append({
                        'table': table,
                        'status': 'FAILED',
                        'error': 'No backup found'
                    })
                    continue
            else:
                backup_ts = args.backup_timestamp

            try:
                result = restore_table(
                    spark, args.kudu_master, args.database, table,
                    args.backup_path, backup_ts, args
                )
                results.append(result)
            except Exception as e:
                print(f"ERROR restoring {table}: {str(e)}")
                results.append({
                    'table': table,
                    'status': 'FAILED',
                    'error': str(e)
                })

        # Print summary
        print("\n" + "="*60)
        print("RESTORE SUMMARY")
        print("="*60)

        success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
        total_rows = sum(r.get('rows_restored', 0) for r in results if r['status'] == 'SUCCESS')

        for result in results:
            status_icon = "✓" if result['status'] == 'SUCCESS' else "✗"
            print(f"{status_icon} {result['table']}: {result['status']} - {result.get('rows_restored', 'N/A')} rows")

        print(f"\nTotal: {success_count}/{len(tables)} tables restored")
        print(f"Total rows: {total_rows:,}")
        print("="*60)

        sys.exit(0 if success_count == len(tables) else 1)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
```

### 5.4 Incremental Restore Job

**File:** `kudu_incremental_restore.py`

```python
#!/usr/bin/env python3
"""
Kudu Incremental Restore PySpark Job
=====================================
Applies incremental backup changes to restore point-in-time state.

Usage:
    spark-submit --jars kudu-spark3_2.12-1.17.0.jar,kudu-backup3_2.12-1.17.0.jar \
        kudu_incremental_restore.py \
        --kudu-master kudu-master-1:7051,kudu-master-2:7051 \
        --tables cis_portfolio,cis_trade \
        --database gmp_cis \
        --backup-path hdfs:///backups/kudu \
        --restore-to-time "2026-01-22 12:00:00" \
        --apply-mode upsert
"""

import argparse
import json
import sys
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Kudu Incremental Restore Job',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Required arguments
    parser.add_argument(
        '--kudu-master',
        required=True,
        help='Kudu master addresses (comma-separated)'
    )
    parser.add_argument(
        '--tables',
        required=True,
        help='Tables to restore (comma-separated)'
    )
    parser.add_argument(
        '--database',
        required=True,
        help='Database name (e.g., gmp_cis)'
    )
    parser.add_argument(
        '--backup-path',
        required=True,
        help='Base backup path (HDFS/S3/ADLS)'
    )

    # Optional arguments
    parser.add_argument(
        '--restore-to-time',
        default=None,
        help='Point-in-time to restore to (YYYY-MM-DD HH:MM:SS). '
             'If not specified, applies all available incremental backups.'
    )
    parser.add_argument(
        '--full-backup-timestamp',
        default='LATEST',
        help='Full backup to start from (default: LATEST)'
    )
    parser.add_argument(
        '--apply-mode',
        default='upsert',
        choices=['upsert', 'insert_ignore'],
        help='How to apply incremental changes (default: upsert)'
    )
    parser.add_argument(
        '--parallelism',
        type=int,
        default=8,
        help='Number of parallel tasks (default: 8)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print restore plan without executing'
    )

    return parser.parse_args()


def create_spark_session(app_name, kudu_master):
    """Create and configure Spark session."""
    return SparkSession.builder \
        .appName(app_name) \
        .config("spark.kudu.master", kudu_master) \
        .getOrCreate()


def list_incremental_backups(spark, backup_path, database, table,
                              since_timestamp=None, until_timestamp=None):
    """List all incremental backups in timestamp order."""
    inc_path = f"{backup_path}/{database}/{table}/incremental"
    backups = []

    try:
        hadoop_conf = spark._jsc.hadoopConfiguration()
        fs = spark._jvm.org.apache.hadoop.fs.FileSystem.get(
            spark._jvm.java.net.URI(backup_path), hadoop_conf
        )
        path = spark._jvm.org.apache.hadoop.fs.Path(inc_path)

        if fs.exists(path):
            statuses = fs.listStatus(path)
            for status in statuses:
                if status.isDirectory():
                    dir_name = status.getPath().getName()
                    if not dir_name.startswith('_'):
                        try:
                            ts = datetime.strptime(dir_name, '%Y-%m-%d_%H%M%S')

                            # Filter by time range
                            if since_timestamp and ts < since_timestamp:
                                continue
                            if until_timestamp and ts > until_timestamp:
                                continue

                            backups.append({
                                'timestamp': dir_name,
                                'datetime': ts,
                                'path': f"{inc_path}/{dir_name}"
                            })
                        except ValueError:
                            pass
    except Exception as e:
        print(f"Error listing incremental backups: {e}")

    # Sort by timestamp
    backups.sort(key=lambda x: x['datetime'])
    return backups


def incremental_restore_table(spark, kudu_master, database, table,
                               backup_path, args):
    """Restore a table by applying full + incremental backups."""
    full_table_name = f"impala::{database}.{table}"

    print(f"\n{'='*60}")
    print(f"Point-in-Time Restore: {table}")
    print(f"Restore to: {args.restore_to_time or 'LATEST'}")
    print(f"{'='*60}")

    # 1. Get full backup timestamp
    if args.full_backup_timestamp == 'LATEST':
        full_path = f"{backup_path}/{database}/{table}/full"
        hadoop_conf = spark._jsc.hadoopConfiguration()
        fs = spark._jvm.org.apache.hadoop.fs.FileSystem.get(
            spark._jvm.java.net.URI(backup_path), hadoop_conf
        )
        path = spark._jvm.org.apache.hadoop.fs.Path(full_path)

        timestamps = []
        if fs.exists(path):
            statuses = fs.listStatus(path)
            for status in statuses:
                if status.isDirectory():
                    dir_name = status.getPath().getName()
                    if not dir_name.startswith('_'):
                        timestamps.append(dir_name)

        if not timestamps:
            print(f"ERROR: No full backup found for {table}")
            return {'table': table, 'status': 'FAILED', 'error': 'No full backup'}

        full_backup_ts = sorted(timestamps)[-1]
    else:
        full_backup_ts = args.full_backup_timestamp

    full_backup_path = f"{backup_path}/{database}/{table}/full/{full_backup_ts}"
    full_backup_dt = datetime.strptime(full_backup_ts, '%Y-%m-%d_%H%M%S')

    print(f"Full backup: {full_backup_ts}")

    # 2. Find applicable incremental backups
    restore_to_dt = None
    if args.restore_to_time:
        restore_to_dt = datetime.strptime(args.restore_to_time, '%Y-%m-%d %H:%M:%S')

    incremental_backups = list_incremental_backups(
        spark, backup_path, database, table,
        since_timestamp=full_backup_dt,
        until_timestamp=restore_to_dt
    )

    print(f"Incremental backups to apply: {len(incremental_backups)}")
    for inc in incremental_backups:
        print(f"  - {inc['timestamp']}")

    if args.dry_run:
        print(f"\nDRY RUN: Would restore from {full_backup_ts} + {len(incremental_backups)} incrementals")
        return {
            'table': table,
            'status': 'DRY_RUN',
            'full_backup': full_backup_ts,
            'incrementals': len(incremental_backups)
        }

    # 3. Restore full backup first
    print(f"\nRestoring full backup from {full_backup_path}...")
    df_full = spark.read.parquet(full_backup_path)
    full_count = df_full.count()
    print(f"Full backup rows: {full_count:,}")

    df_full.repartition(args.parallelism) \
        .write \
        .format("kudu") \
        .option("kudu.master", kudu_master) \
        .option("kudu.table", full_table_name) \
        .option("kudu.operation", "upsert") \
        .mode("append") \
        .save()

    # 4. Apply each incremental backup in order
    total_incremental_rows = 0
    for inc_backup in incremental_backups:
        print(f"\nApplying incremental: {inc_backup['timestamp']}...")

        df_inc = spark.read.parquet(inc_backup['path'])
        inc_count = df_inc.count()
        total_incremental_rows += inc_count
        print(f"Incremental rows: {inc_count:,}")

        df_inc.repartition(args.parallelism) \
            .write \
            .format("kudu") \
            .option("kudu.master", kudu_master) \
            .option("kudu.table", full_table_name) \
            .option("kudu.operation", args.apply_mode) \
            .mode("append") \
            .save()

    # 5. Verify final state
    df_final = spark.read \
        .format("kudu") \
        .option("kudu.master", kudu_master) \
        .option("kudu.table", full_table_name) \
        .load()
    final_count = df_final.count()

    print(f"\nRestore completed!")
    print(f"Final row count: {final_count:,}")

    return {
        'table': table,
        'status': 'SUCCESS',
        'full_backup': full_backup_ts,
        'full_rows': full_count,
        'incrementals_applied': len(incremental_backups),
        'incremental_rows': total_incremental_rows,
        'final_rows': final_count
    }


def main():
    """Main entry point."""
    args = parse_arguments()

    print("\n" + "="*60)
    print("KUDU INCREMENTAL RESTORE JOB")
    print("="*60)
    print(f"Kudu Master: {args.kudu_master}")
    print(f"Database: {args.database}")
    print(f"Tables: {args.tables}")
    print(f"Restore To: {args.restore_to_time or 'LATEST'}")
    print(f"Apply Mode: {args.apply_mode}")
    print("="*60 + "\n")

    # Create Spark session
    spark = create_spark_session(
        f"KuduIncrementalRestore_{args.database}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        args.kudu_master
    )

    try:
        tables = [t.strip() for t in args.tables.split(',')]
        results = []

        for table in tables:
            try:
                result = incremental_restore_table(
                    spark, args.kudu_master, args.database, table,
                    args.backup_path, args
                )
                results.append(result)
            except Exception as e:
                print(f"ERROR restoring {table}: {str(e)}")
                results.append({
                    'table': table,
                    'status': 'FAILED',
                    'error': str(e)
                })

        # Print summary
        print("\n" + "="*60)
        print("INCREMENTAL RESTORE SUMMARY")
        print("="*60)

        success_count = sum(1 for r in results if r['status'] == 'SUCCESS')

        for result in results:
            status_icon = "✓" if result['status'] == 'SUCCESS' else "✗"
            if result['status'] == 'SUCCESS':
                print(f"{status_icon} {result['table']}: {result['status']}")
                print(f"   Full: {result['full_rows']:,} rows | "
                      f"Incrementals: {result['incrementals_applied']} ({result['incremental_rows']:,} rows) | "
                      f"Final: {result['final_rows']:,} rows")
            else:
                print(f"{status_icon} {result['table']}: {result['status']} - {result.get('error', 'Unknown error')}")

        print(f"\nTotal: {success_count}/{len(tables)} tables restored")
        print("="*60)

        sys.exit(0 if success_count == len(tables) else 1)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
```

### 5.5 Cross-Cluster Migration Job

**File:** `kudu_migration.py`

```python
#!/usr/bin/env python3
"""
Kudu Cross-Cluster Migration PySpark Job
==========================================
Migrates tables between Kudu clusters (e.g., PROD to UAT, PROD to DR).

Usage:
    spark-submit --jars kudu-spark3_2.12-1.17.0.jar,kudu-backup3_2.12-1.17.0.jar \
        kudu_migration.py \
        --source-kudu-master prod-kudu-master:7051 \
        --target-kudu-master uat-kudu-master:7051 \
        --tables cis_portfolio,cis_trade \
        --source-database gmp_cis \
        --target-database gmp_cis_uat \
        --migration-mode full \
        --apply-masking
"""

import argparse
import json
import sys
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, md5, concat, substring


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Kudu Cross-Cluster Migration Job',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Required arguments
    parser.add_argument(
        '--source-kudu-master',
        required=True,
        help='Source Kudu master addresses'
    )
    parser.add_argument(
        '--target-kudu-master',
        required=True,
        help='Target Kudu master addresses'
    )
    parser.add_argument(
        '--tables',
        required=True,
        help='Tables to migrate (comma-separated)'
    )
    parser.add_argument(
        '--source-database',
        required=True,
        help='Source database name'
    )
    parser.add_argument(
        '--target-database',
        required=True,
        help='Target database name'
    )

    # Optional arguments
    parser.add_argument(
        '--migration-mode',
        default='full',
        choices=['full', 'incremental', 'schema_only'],
        help='Migration mode (default: full)'
    )
    parser.add_argument(
        '--timestamp-column',
        default='updated_at',
        help='Column for incremental migration'
    )
    parser.add_argument(
        '--since',
        default=None,
        help='Migrate changes since (for incremental mode)'
    )
    parser.add_argument(
        '--apply-masking',
        action='store_true',
        help='Apply data masking for non-production environments'
    )
    parser.add_argument(
        '--masking-config',
        default=None,
        help='Path to masking configuration JSON'
    )
    parser.add_argument(
        '--parallelism',
        type=int,
        default=16,
        help='Number of parallel tasks (default: 16)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50000,
        help='Batch size for writing (default: 50000)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print migration plan without executing'
    )

    return parser.parse_args()


def create_spark_session(app_name):
    """Create Spark session for migration."""
    return SparkSession.builder \
        .appName(app_name) \
        .config("spark.sql.shuffle.partitions", "200") \
        .getOrCreate()


def get_default_masking_config():
    """Default masking configuration for banking data."""
    return {
        'columns': {
            'manager': {'type': 'hash_prefix', 'prefix': 'MGR_'},
            'portfolio_client': {'type': 'hash_prefix', 'prefix': 'CLIENT_'},
            'created_by': {'type': 'hash_prefix', 'prefix': 'USER_'},
            'updated_by': {'type': 'hash_prefix', 'prefix': 'USER_'},
            'submitted_by': {'type': 'hash_prefix', 'prefix': 'USER_'},
            'validated_by': {'type': 'hash_prefix', 'prefix': 'USER_'},
            'settled_by': {'type': 'hash_prefix', 'prefix': 'USER_'},
            'cancelled_by': {'type': 'hash_prefix', 'prefix': 'USER_'},
            'cash_balance': {'type': 'scale', 'factor': 0.01},
            'quantity': {'type': 'scale', 'factor': 0.01},
            'price': {'type': 'scale', 'factor': 0.01},
            'total_amount': {'type': 'scale', 'factor': 0.01},
        },
        'global_replacements': {
            'src_system': 'UAT_MIGRATED'
        }
    }


def apply_data_masking(df, masking_config):
    """Apply data masking transformations."""
    masked_df = df

    # Get column list
    columns = df.columns

    # Apply column-specific masking
    for col_name, mask_config in masking_config.get('columns', {}).items():
        if col_name in columns:
            mask_type = mask_config.get('type')

            if mask_type == 'hash_prefix':
                prefix = mask_config.get('prefix', '')
                masked_df = masked_df.withColumn(
                    col_name,
                    concat(lit(prefix), substring(md5(col(col_name)), 1, 8))
                )

            elif mask_type == 'scale':
                factor = mask_config.get('factor', 1.0)
                masked_df = masked_df.withColumn(
                    col_name,
                    col(col_name) * lit(factor)
                )

            elif mask_type == 'replace':
                value = mask_config.get('value', '')
                masked_df = masked_df.withColumn(
                    col_name,
                    lit(value)
                )

    # Apply global replacements
    for col_name, value in masking_config.get('global_replacements', {}).items():
        if col_name in columns:
            masked_df = masked_df.withColumn(col_name, lit(value))

    return masked_df


def migrate_table(spark, source_master, target_master, source_db, target_db,
                  table, args, masking_config=None):
    """Migrate a single table."""
    source_table = f"impala::{source_db}.{table}"
    target_table = f"impala::{target_db}.{table}"

    print(f"\n{'='*60}")
    print(f"Migrating: {source_table} -> {target_table}")
    print(f"Mode: {args.migration_mode}")
    print(f"Masking: {'Enabled' if args.apply_masking else 'Disabled'}")
    print(f"{'='*60}")

    # Read from source
    reader = spark.read \
        .format("kudu") \
        .option("kudu.master", source_master) \
        .option("kudu.table", source_table)

    df = reader.load()

    # Apply incremental filter if needed
    if args.migration_mode == 'incremental' and args.since:
        since_ts = datetime.strptime(args.since, '%Y-%m-%d %H:%M:%S')
        df = df.filter(col(args.timestamp_column) >= since_ts)
        print(f"Filtered to changes since: {since_ts}")

    # Get counts
    source_count = df.count()
    print(f"Source rows: {source_count:,}")

    if source_count == 0:
        print("No rows to migrate")
        return {
            'table': table,
            'status': 'NO_DATA',
            'source_rows': 0
        }

    # Apply masking if requested
    if args.apply_masking and masking_config:
        print("Applying data masking...")
        df = apply_data_masking(df, masking_config)

    if args.dry_run:
        print(f"DRY RUN: Would migrate {source_count:,} rows")
        if args.apply_masking:
            print("Sample masked data:")
            df.show(5, truncate=False)
        return {
            'table': table,
            'status': 'DRY_RUN',
            'source_rows': source_count
        }

    # Write to target
    print(f"Writing to target: {target_table}")

    operation = 'upsert' if args.migration_mode in ['full', 'incremental'] else 'insert'

    df.repartition(args.parallelism) \
        .write \
        .format("kudu") \
        .option("kudu.master", target_master) \
        .option("kudu.table", target_table) \
        .option("kudu.operation", operation) \
        .mode("append") \
        .save()

    # Verify
    df_target = spark.read \
        .format("kudu") \
        .option("kudu.master", target_master) \
        .option("kudu.table", target_table) \
        .load()
    target_count = df_target.count()

    print(f"Target rows after migration: {target_count:,}")

    return {
        'table': table,
        'status': 'SUCCESS',
        'source_rows': source_count,
        'target_rows': target_count,
        'masked': args.apply_masking
    }


def main():
    """Main entry point."""
    args = parse_arguments()

    print("\n" + "="*60)
    print("KUDU CROSS-CLUSTER MIGRATION JOB")
    print("="*60)
    print(f"Source: {args.source_kudu_master} / {args.source_database}")
    print(f"Target: {args.target_kudu_master} / {args.target_database}")
    print(f"Tables: {args.tables}")
    print(f"Mode: {args.migration_mode}")
    print(f"Masking: {args.apply_masking}")
    print("="*60 + "\n")

    # Create Spark session
    spark = create_spark_session(
        f"KuduMigration_{args.source_database}_to_{args.target_database}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    # Load masking config
    masking_config = None
    if args.apply_masking:
        if args.masking_config:
            with open(args.masking_config, 'r') as f:
                masking_config = json.load(f)
        else:
            masking_config = get_default_masking_config()
        print(f"Masking config loaded: {len(masking_config.get('columns', {}))} column rules")

    try:
        tables = [t.strip() for t in args.tables.split(',')]
        results = []

        for table in tables:
            try:
                result = migrate_table(
                    spark,
                    args.source_kudu_master,
                    args.target_kudu_master,
                    args.source_database,
                    args.target_database,
                    table,
                    args,
                    masking_config
                )
                results.append(result)
            except Exception as e:
                print(f"ERROR migrating {table}: {str(e)}")
                results.append({
                    'table': table,
                    'status': 'FAILED',
                    'error': str(e)
                })

        # Print summary
        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)

        success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
        total_rows = sum(r.get('target_rows', 0) for r in results if r['status'] == 'SUCCESS')

        for result in results:
            status_icon = "✓" if result['status'] == 'SUCCESS' else "✗"
            rows_info = f"{result.get('source_rows', 'N/A')} -> {result.get('target_rows', 'N/A')} rows"
            masked_info = " (masked)" if result.get('masked') else ""
            print(f"{status_icon} {result['table']}: {result['status']} - {rows_info}{masked_info}")

        print(f"\nTotal: {success_count}/{len(tables)} tables migrated")
        print(f"Total rows: {total_rows:,}")
        print("="*60)

        sys.exit(0 if success_count == len(tables) else 1)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
```

---

## 6. Job Parameters Reference

### 6.1 Common Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--kudu-master` | String | Yes | - | Kudu master addresses |
| `--tables` | String | Yes | - | Tables to process (comma-separated) |
| `--database` | String | Yes | - | Database name |
| `--backup-path` | String | Yes | - | HDFS/S3 backup location |
| `--parallelism` | Integer | No | 8 | Spark partitions |
| `--dry-run` | Flag | No | False | Preview without executing |

### 6.2 Full Backup Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--compression` | String | snappy | Compression codec |
| `--scan-batch-size` | Integer | 1024 | Kudu scan batch size |
| `--scan-request-timeout` | Integer | 30000 | Scan timeout (ms) |
| `--partition-by` | String | None | Partition column |
| `--where-clause` | String | None | Filter condition |

### 6.3 Incremental Backup Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--timestamp-column` | String | Required | Column for change detection |
| `--since` | String | Auto | Start timestamp |
| `--hours-back` | Integer | None | Alternative to --since |
| `--include-deletes` | Flag | False | Track deletions |
| `--delete-column` | String | is_deleted | Deletion marker column |

### 6.4 Restore Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--backup-timestamp` | String | LATEST | Backup to restore |
| `--restore-mode` | String | truncate_insert | Restore strategy |
| `--target-table-suffix` | String | "" | Suffix for restored table |
| `--validate-count` | Flag | False | Verify row counts |

### 6.5 Migration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--source-kudu-master` | String | Required | Source cluster |
| `--target-kudu-master` | String | Required | Target cluster |
| `--source-database` | String | Required | Source database |
| `--target-database` | String | Required | Target database |
| `--apply-masking` | Flag | False | Enable data masking |
| `--masking-config` | String | None | Custom masking rules |

---

## 7. Scheduling and Automation

### 7.1 Oozie Coordinator for Scheduled Backups

**File:** `oozie/backup_coordinator.xml`

```xml
<coordinator-app name="kudu-backup-coordinator"
                 frequency="${coord:days(1)}"
                 start="${startTime}"
                 end="${endTime}"
                 timezone="UTC"
                 xmlns="uri:oozie:coordinator:0.4">

    <controls>
        <timeout>120</timeout>
        <concurrency>1</concurrency>
        <execution>FIFO</execution>
    </controls>

    <datasets>
        <dataset name="backup-output"
                 frequency="${coord:days(1)}"
                 initial-instance="${startTime}"
                 timezone="UTC">
            <uri-template>${backupPath}/${database}/${YEAR}/${MONTH}/${DAY}</uri-template>
        </dataset>
    </datasets>

    <action>
        <workflow>
            <app-path>${workflowPath}</app-path>
            <configuration>
                <property>
                    <name>kuduMaster</name>
                    <value>${kuduMaster}</value>
                </property>
                <property>
                    <name>database</name>
                    <value>${database}</value>
                </property>
                <property>
                    <name>tables</name>
                    <value>${tables}</value>
                </property>
                <property>
                    <name>backupPath</name>
                    <value>${backupPath}</value>
                </property>
                <property>
                    <name>backupDate</name>
                    <value>${coord:formatTime(coord:nominalTime(), 'yyyy-MM-dd')}</value>
                </property>
            </configuration>
        </workflow>
    </action>
</coordinator-app>
```

### 7.2 Airflow DAG for Backup Pipeline

**File:** `airflow/kudu_backup_dag.py`

```python
"""
Airflow DAG for Kudu Backup Pipeline
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.utils.task_group import TaskGroup

default_args = {
    'owner': 'data-platform',
    'depends_on_past': False,
    'email': ['ops-team@bank.com'],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

# Configuration
KUDU_MASTER = "kudu-master-1:7051,kudu-master-2:7051,kudu-master-3:7051"
DATABASE = "gmp_cis"
BACKUP_PATH = "hdfs:///backups/kudu"
SPARK_JARS = "/jars/kudu/kudu-spark3_2.12-1.17.0.jar,/jars/kudu/kudu-backup3_2.12-1.17.0.jar"

# Tables with their backup configurations
TABLE_CONFIGS = {
    'cis_portfolio': {'full_schedule': 'weekly', 'incremental_schedule': 'daily'},
    'cis_trade': {'full_schedule': 'weekly', 'incremental_schedule': '6hours'},
    'cis_security': {'full_schedule': 'weekly', 'incremental_schedule': 'daily'},
    'cis_audit_log': {'full_schedule': 'monthly', 'incremental_schedule': 'daily'},
}


with DAG(
    'kudu_backup_pipeline',
    default_args=default_args,
    description='Kudu table backup pipeline',
    schedule_interval='0 6 * * *',  # Daily at 6 AM
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['kudu', 'backup', 'data-platform'],
) as dag:

    # Incremental backup tasks
    with TaskGroup(group_id='incremental_backups') as incremental_group:
        for table, config in TABLE_CONFIGS.items():
            SparkSubmitOperator(
                task_id=f'incremental_backup_{table}',
                application='/opt/spark/jobs/kudu_incremental_backup.py',
                jars=SPARK_JARS,
                application_args=[
                    '--kudu-master', KUDU_MASTER,
                    '--tables', table,
                    '--database', DATABASE,
                    '--backup-path', BACKUP_PATH,
                    '--timestamp-column', 'updated_at',
                    '--hours-back', '24',
                    '--compression', 'snappy',
                ],
                conf={
                    'spark.executor.memory': '4g',
                    'spark.executor.cores': '2',
                    'spark.dynamicAllocation.enabled': 'true',
                },
            )

    # Weekly full backup (runs on Sunday)
    with TaskGroup(group_id='weekly_full_backups') as weekly_group:
        for table, config in TABLE_CONFIGS.items():
            if config['full_schedule'] == 'weekly':
                SparkSubmitOperator(
                    task_id=f'full_backup_{table}',
                    application='/opt/spark/jobs/kudu_full_backup.py',
                    jars=SPARK_JARS,
                    application_args=[
                        '--kudu-master', KUDU_MASTER,
                        '--tables', table,
                        '--database', DATABASE,
                        '--backup-path', BACKUP_PATH,
                        '--compression', 'snappy',
                        '--parallelism', '16',
                    ],
                    conf={
                        'spark.executor.memory': '8g',
                        'spark.executor.cores': '4',
                    },
                    trigger_rule='all_done',  # Run even if incremental fails
                )

    # Notification
    send_notification = EmailOperator(
        task_id='send_notification',
        to='ops-team@bank.com',
        subject='Kudu Backup Pipeline - {{ ds }}',
        html_content="""
        <h3>Kudu Backup Pipeline Completed</h3>
        <p>Execution Date: {{ ds }}</p>
        <p>Check Airflow UI for detailed status.</p>
        """,
        trigger_rule='all_done',
    )

    incremental_group >> weekly_group >> send_notification
```

---

## 8. Monitoring and Validation

### 8.1 Validation Script

**File:** `kudu_backup_validation.py`

```python
#!/usr/bin/env python3
"""
Kudu Backup Validation Script
"""

import argparse
import json
from datetime import datetime
from pyspark.sql import SparkSession


def validate_backup(spark, kudu_master, database, table, backup_path, backup_type, timestamp):
    """Validate a backup by comparing row counts and checksums."""

    results = {
        'table': table,
        'backup_type': backup_type,
        'timestamp': timestamp,
        'validations': []
    }

    # 1. Read backup data
    if backup_type == 'full':
        backup_data_path = f"{backup_path}/{database}/{table}/full/{timestamp}"
    else:
        backup_data_path = f"{backup_path}/{database}/{table}/incremental/{timestamp}"

    try:
        df_backup = spark.read.parquet(backup_data_path)
        backup_count = df_backup.count()
        results['backup_row_count'] = backup_count
        results['validations'].append({
            'check': 'backup_readable',
            'status': 'PASS',
            'message': f'Backup contains {backup_count:,} rows'
        })
    except Exception as e:
        results['validations'].append({
            'check': 'backup_readable',
            'status': 'FAIL',
            'message': str(e)
        })
        return results

    # 2. Read metadata
    try:
        metadata_path = f"{backup_data_path}/_metadata.json"
        metadata_df = spark.read.text(metadata_path)
        metadata = json.loads(metadata_df.first()[0])
        expected_count = metadata.get('row_count', 0)

        if backup_count == expected_count:
            results['validations'].append({
                'check': 'row_count_metadata',
                'status': 'PASS',
                'message': f'Row count matches metadata: {backup_count:,}'
            })
        else:
            results['validations'].append({
                'check': 'row_count_metadata',
                'status': 'WARN',
                'message': f'Row count mismatch: backup={backup_count}, metadata={expected_count}'
            })
    except Exception as e:
        results['validations'].append({
            'check': 'metadata_readable',
            'status': 'WARN',
            'message': f'Could not read metadata: {e}'
        })

    # 3. Compare with source (for full backup only)
    if backup_type == 'full':
        try:
            full_table_name = f"impala::{database}.{table}"
            df_source = spark.read \
                .format("kudu") \
                .option("kudu.master", kudu_master) \
                .option("kudu.table", full_table_name) \
                .load()
            source_count = df_source.count()

            # Allow small variance for active tables
            variance = abs(source_count - backup_count) / max(source_count, 1) * 100

            if variance < 1:  # Less than 1% difference
                results['validations'].append({
                    'check': 'source_comparison',
                    'status': 'PASS',
                    'message': f'Source: {source_count:,}, Backup: {backup_count:,}, Variance: {variance:.2f}%'
                })
            else:
                results['validations'].append({
                    'check': 'source_comparison',
                    'status': 'WARN',
                    'message': f'High variance: Source: {source_count:,}, Backup: {backup_count:,}, Variance: {variance:.2f}%'
                })
        except Exception as e:
            results['validations'].append({
                'check': 'source_comparison',
                'status': 'SKIP',
                'message': f'Could not compare with source: {e}'
            })

    # 4. Schema validation
    try:
        schema_valid = len(df_backup.columns) > 0
        results['validations'].append({
            'check': 'schema_valid',
            'status': 'PASS' if schema_valid else 'FAIL',
            'message': f'Schema has {len(df_backup.columns)} columns'
        })
        results['columns'] = df_backup.columns
    except Exception as e:
        results['validations'].append({
            'check': 'schema_valid',
            'status': 'FAIL',
            'message': str(e)
        })

    # Overall status
    failed_checks = [v for v in results['validations'] if v['status'] == 'FAIL']
    results['overall_status'] = 'FAIL' if failed_checks else 'PASS'

    return results


def main():
    parser = argparse.ArgumentParser(description='Validate Kudu backups')
    parser.add_argument('--kudu-master', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--tables', required=True)
    parser.add_argument('--backup-path', required=True)
    parser.add_argument('--backup-type', choices=['full', 'incremental'], required=True)
    parser.add_argument('--timestamp', default='LATEST')
    parser.add_argument('--output', default=None, help='Output file for results')

    args = parser.parse_args()

    spark = SparkSession.builder \
        .appName(f"KuduBackupValidation_{args.database}") \
        .config("spark.kudu.master", args.kudu_master) \
        .getOrCreate()

    try:
        tables = [t.strip() for t in args.tables.split(',')]
        all_results = []

        for table in tables:
            # Get timestamp
            if args.timestamp == 'LATEST':
                # Find latest backup
                backup_type_path = f"{args.backup_path}/{args.database}/{table}/{args.backup_type}"
                hadoop_conf = spark._jsc.hadoopConfiguration()
                fs = spark._jvm.org.apache.hadoop.fs.FileSystem.get(
                    spark._jvm.java.net.URI(args.backup_path), hadoop_conf
                )
                path = spark._jvm.org.apache.hadoop.fs.Path(backup_type_path)

                timestamps = []
                if fs.exists(path):
                    for status in fs.listStatus(path):
                        if status.isDirectory():
                            dir_name = status.getPath().getName()
                            if not dir_name.startswith('_'):
                                timestamps.append(dir_name)

                timestamp = sorted(timestamps)[-1] if timestamps else None
            else:
                timestamp = args.timestamp

            if timestamp:
                result = validate_backup(
                    spark, args.kudu_master, args.database, table,
                    args.backup_path, args.backup_type, timestamp
                )
                all_results.append(result)

                # Print results
                print(f"\n{'='*60}")
                print(f"Table: {table}")
                print(f"Backup: {args.backup_type}/{timestamp}")
                print(f"Overall: {result['overall_status']}")
                print("-"*40)
                for v in result['validations']:
                    status_icon = "✓" if v['status'] == 'PASS' else "✗" if v['status'] == 'FAIL' else "?"
                    print(f"  {status_icon} {v['check']}: {v['message']}")
            else:
                print(f"No backup found for {table}")

        # Save results if output specified
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(all_results, f, indent=2)
            print(f"\nResults saved to: {args.output}")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
```

---

## 9. Disaster Recovery Procedures

### 9.1 DR Restore Runbook

```bash
#!/bin/bash
# dr_restore_runbook.sh
# Emergency DR restore procedure

set -e

echo "=========================================="
echo "KUDU DR RESTORE PROCEDURE"
echo "=========================================="
echo "Started: $(date)"
echo ""

# Configuration
PROD_KUDU_MASTER="prod-kudu-master-1:7051,prod-kudu-master-2:7051"
DR_KUDU_MASTER="dr-kudu-master-1:7051,dr-kudu-master-2:7051"
DATABASE="gmp_cis"
BACKUP_PATH="hdfs:///backups/kudu"
SPARK_JARS="/jars/kudu/kudu-spark3_2.12-1.17.0.jar,/jars/kudu/kudu-backup3_2.12-1.17.0.jar"

# Critical tables in restore order
CRITICAL_TABLES=(
    "cis_portfolio"
    "cis_security"
    "cis_counterparty"
    "cis_trade"
    "cis_udf_field"
)

# Step 1: Verify DR cluster health
echo "Step 1: Verifying DR cluster health..."
kudu cluster ksck $DR_KUDU_MASTER || {
    echo "ERROR: DR cluster is not healthy!"
    exit 1
}

# Step 2: Get latest backup timestamps
echo ""
echo "Step 2: Finding latest backups..."
for table in "${CRITICAL_TABLES[@]}"; do
    latest=$(hdfs dfs -ls ${BACKUP_PATH}/${DATABASE}/${table}/full/ 2>/dev/null | tail -1 | awk '{print $NF}' | xargs basename)
    echo "  $table: $latest"
done

# Step 3: Restore each table
echo ""
echo "Step 3: Restoring tables..."

for table in "${CRITICAL_TABLES[@]}"; do
    echo ""
    echo "Restoring: $table"

    spark-submit \
        --master yarn \
        --deploy-mode cluster \
        --jars $SPARK_JARS \
        --conf spark.executor.memory=8g \
        --conf spark.executor.cores=4 \
        /opt/spark/jobs/kudu_full_restore.py \
        --kudu-master $DR_KUDU_MASTER \
        --tables $table \
        --database $DATABASE \
        --backup-path $BACKUP_PATH \
        --backup-timestamp LATEST \
        --restore-mode upsert \
        --validate-count

    if [ $? -eq 0 ]; then
        echo "✓ $table restored successfully"
    else
        echo "✗ $table restore FAILED"
        # Continue with other tables, don't exit
    fi
done

# Step 4: Apply incremental backups
echo ""
echo "Step 4: Applying incremental backups..."

spark-submit \
    --master yarn \
    --deploy-mode cluster \
    --jars $SPARK_JARS \
    --conf spark.executor.memory=4g \
    /opt/spark/jobs/kudu_incremental_restore.py \
    --kudu-master $DR_KUDU_MASTER \
    --tables $(IFS=,; echo "${CRITICAL_TABLES[*]}") \
    --database $DATABASE \
    --backup-path $BACKUP_PATH \
    --apply-mode upsert

# Step 5: Validate restore
echo ""
echo "Step 5: Validating restore..."

spark-submit \
    --master yarn \
    --deploy-mode client \
    --jars $SPARK_JARS \
    /opt/spark/jobs/kudu_backup_validation.py \
    --kudu-master $DR_KUDU_MASTER \
    --database $DATABASE \
    --tables $(IFS=,; echo "${CRITICAL_TABLES[*]}") \
    --backup-path $BACKUP_PATH \
    --backup-type full \
    --output /tmp/dr_restore_validation_$(date +%Y%m%d_%H%M%S).json

echo ""
echo "=========================================="
echo "DR RESTORE COMPLETED"
echo "Finished: $(date)"
echo "=========================================="
```

---

## 10. Troubleshooting

### 10.1 Common Issues and Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| `KuduException: Master not found` | Incorrect master address | Verify `--kudu-master` parameter |
| `Timeout during scan` | Large table, slow network | Increase `--scan-request-timeout` |
| `Out of memory` | Too much data per partition | Increase `--parallelism`, reduce `--batch-size` |
| `Table not found` | Wrong database prefix | Use `impala::database.table` format |
| `Permission denied` | Kerberos/ACL issues | Check keytab, run kinit |
| `Backup incomplete` | Job killed/failed | Use checkpoint recovery |

### 10.2 Performance Tuning

```bash
# Optimal Spark configuration for large backups
spark-submit \
    --master yarn \
    --deploy-mode cluster \
    --num-executors 20 \
    --executor-memory 8g \
    --executor-cores 4 \
    --driver-memory 4g \
    --conf spark.dynamicAllocation.enabled=true \
    --conf spark.dynamicAllocation.minExecutors=5 \
    --conf spark.dynamicAllocation.maxExecutors=50 \
    --conf spark.sql.shuffle.partitions=200 \
    --conf spark.kudu.scanLocality=leader_only \
    --conf spark.kudu.batchSize=2048 \
    --jars $SPARK_JARS \
    kudu_full_backup.py \
    --parallelism 32 \
    ...
```

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-22 | CIS Trade Hive Team | Initial version |

---

## Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Technical Lead | | | |
| Data Platform Lead | | | |
| DBA Lead | | | |
