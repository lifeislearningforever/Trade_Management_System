# Data Ingestion Framework Architecture

## Overview

A metadata-driven, parameterized PySpark framework for ingesting daily business files (TXT/CSV) into Hive External Tables with Parquet format. The framework supports full load, delta load, and partition overwrite modes with comprehensive reconciliation.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           Data Ingestion Framework                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   Source Files              Ingestion Engine              Target Tables              │
│   ────────────              ────────────────              ─────────────              │
│                                                                                      │
│   ┌──────────┐             ┌─────────────────┐          ┌─────────────────┐         │
│   │ CSV/TXT  │────────────▶│  ingestion_     │          │  Hive External  │         │
│   │ Files    │             │  config         │          │  Table (Parquet)│         │
│   └──────────┘             │  (metadata)     │          └─────────────────┘         │
│        │                   └────────┬────────┘                   ▲                  │
│        │                            │                            │                  │
│        │                            ▼                            │                  │
│        │                   ┌─────────────────┐                   │                  │
│        └──────────────────▶│  generic_       │───────────────────┘                  │
│                            │  file_ingest.py │                                      │
│                            └────────┬────────┘                                      │
│                                     │                                               │
│                                     ▼                                               │
│                            ┌─────────────────┐                                      │
│                            │  ingestion_     │                                      │
│                            │  recon          │                                      │
│                            │  (audit table)  │                                      │
│                            └─────────────────┘                                      │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Metadata Configuration Table

### Table: `gmp_cis.cis_ingestion_config`

Stores all file ingestion configurations. **Hive External Table with Parquet format.**

```sql
-- ============================================================================
-- INGESTION CONFIGURATION TABLE (Hive External / Parquet)
-- ============================================================================
-- Stores metadata for all file ingestion jobs
-- Location: /data/gmp_cis/ingestion/cis_ingestion_config
-- ============================================================================

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_ingestion_config (
    -- Primary Key
    config_id               BIGINT,                    -- Unique config identifier

    -- Source Configuration
    source_id               STRING NOT NULL,           -- Unique source identifier (e.g., 'GMP_POSITIONS')
    source_name             STRING NOT NULL,           -- Human-readable name
    source_description      STRING,                    -- Description of the data source
    source_system           STRING NOT NULL,           -- Source system (GMP, AMS, IMS, CIS)

    -- File Configuration
    file_type               STRING NOT NULL,           -- FILE_TYPE: CSV, TXT, PIPE, FIXED_WIDTH
    file_name_pattern       STRING NOT NULL,           -- Regex pattern (e.g., 'positions_*.csv')
    file_path               STRING NOT NULL,           -- HDFS/local path pattern
    file_encoding           STRING DEFAULT 'UTF-8',    -- File encoding
    has_header              BOOLEAN DEFAULT TRUE,      -- First row is header
    skip_rows               INT DEFAULT 0,             -- Rows to skip at beginning
    skip_footer_rows        INT DEFAULT 0,             -- Rows to skip at end

    -- Delimiter Configuration
    column_delimiter        STRING DEFAULT ',',        -- Column separator
    quote_char              STRING DEFAULT '"',        -- Quote character
    escape_char             STRING DEFAULT '\\',       -- Escape character
    null_string             STRING DEFAULT '',         -- String representing NULL

    -- Column Definition (JSON array)
    column_schema           STRING NOT NULL,           -- JSON: [{"name": "col1", "type": "STRING", "source_position": 0}, ...]

    -- Target Configuration
    target_database         STRING NOT NULL,           -- Target database (gmp_cis)
    target_table            STRING NOT NULL,           -- Target table name
    target_location         STRING NOT NULL,           -- HDFS location for Parquet files

    -- Partition Configuration
    partition_columns       STRING,                    -- Comma-separated partition cols (e.g., 'processing_date,src_system')
    partition_type          STRING DEFAULT 'DYNAMIC',  -- STATIC or DYNAMIC partitioning

    -- Load Mode Configuration
    default_load_mode       STRING DEFAULT 'DELTA',    -- FULL, DELTA, OVERWRITE_PARTITION
    primary_key_columns     STRING,                    -- Comma-separated PK for delta detection
    watermark_column        STRING,                    -- Column for incremental/delta loads

    -- Validation Rules (JSON)
    validation_rules        STRING,                    -- JSON: [{"column": "amount", "rule": "NOT_NULL"}, ...]

    -- Transformation Rules (JSON)
    transformations         STRING,                    -- JSON: [{"column": "date", "transform": "TO_DATE(date, 'yyyyMMdd')"}, ...]

    -- Scheduling
    schedule_frequency      STRING DEFAULT 'DAILY',    -- HOURLY, DAILY, WEEKLY, MONTHLY, ON_DEMAND
    expected_arrival_time   STRING,                    -- Expected file arrival (HH:MM)
    sla_minutes             INT DEFAULT 60,            -- SLA in minutes from expected time

    -- Status
    is_active               BOOLEAN DEFAULT TRUE,      -- Active flag
    priority                INT DEFAULT 5,             -- Processing priority (1=highest)

    -- Audit
    created_by              STRING,
    created_at              STRING,
    updated_by              STRING,
    updated_at              STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/ingestion/cis_ingestion_config'
TBLPROPERTIES (
    'parquet.compression' = 'SNAPPY'
);
```

### Column Schema JSON Format

```json
[
    {
        "name": "portfolio_id",
        "type": "STRING",
        "source_position": 0,
        "source_name": "PORTFOLIO_ID",
        "nullable": false,
        "default_value": null,
        "description": "Portfolio identifier"
    },
    {
        "name": "security_label",
        "type": "STRING",
        "source_position": 1,
        "source_name": "SECURITY",
        "nullable": false
    },
    {
        "name": "quantity",
        "type": "DECIMAL(20,6)",
        "source_position": 2,
        "source_name": "QTY",
        "nullable": true,
        "default_value": "0"
    },
    {
        "name": "price_date",
        "type": "DATE",
        "source_position": 3,
        "source_name": "PRICE_DT",
        "format": "yyyyMMdd"
    }
]
```

### Validation Rules JSON Format

```json
[
    {"column": "portfolio_id", "rule": "NOT_NULL"},
    {"column": "quantity", "rule": "POSITIVE"},
    {"column": "price_date", "rule": "DATE_FORMAT", "format": "yyyy-MM-dd"},
    {"column": "isin", "rule": "REGEX", "pattern": "^[A-Z]{2}[A-Z0-9]{9}[0-9]$"},
    {"column": "currency", "rule": "IN_LIST", "values": ["USD", "EUR", "GBP", "SGD"]},
    {"column": "amount", "rule": "RANGE", "min": 0, "max": 999999999}
]
```

### Transformation Rules JSON Format

```json
[
    {"column": "price_date", "transform": "TO_DATE(price_date, 'yyyyMMdd')"},
    {"column": "amount", "transform": "CAST(REPLACE(amount, ',', '') AS DECIMAL(20,6))"},
    {"column": "security_label", "transform": "UPPER(TRIM(security_label))"},
    {"column": "processing_date", "transform": "CURRENT_DATE()"},
    {"column": "src_system", "transform": "LITERAL('GMP')"}
]
```

---

## 2. Reconciliation Table

### Table: `gmp_cis.cis_ingestion_recon`

Tracks every ingestion run with detailed metrics. **Hive External Table with Parquet format.**

```sql
-- ============================================================================
-- INGESTION RECONCILIATION TABLE (Hive External / Parquet)
-- ============================================================================
-- Audit trail for all ingestion runs with detailed metrics
-- Partitioned by: processing_date
-- Location: /data/gmp_cis/ingestion/cis_ingestion_recon
-- ============================================================================

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_ingestion_recon (
    -- Primary Key
    recon_id                BIGINT,                    -- Unique recon identifier (timestamp-based)

    -- Job Reference
    config_id               BIGINT,                    -- FK to cis_ingestion_config
    source_id               STRING NOT NULL,           -- Source identifier
    batch_id                STRING NOT NULL,           -- Unique batch identifier (e.g., 'BATCH_20260210_001')

    -- Run Information
    run_mode                STRING NOT NULL,           -- FULL, DELTA, OVERWRITE_PARTITION
    run_environment         STRING,                    -- DEV, UAT, PROD
    spark_app_id            STRING,                    -- Spark application ID

    -- File Information
    file_name               STRING,                    -- Actual file processed
    file_path               STRING,                    -- Full path to file
    file_size_bytes         BIGINT,                    -- File size in bytes
    file_modified_time      STRING,                    -- File last modified timestamp
    file_checksum           STRING,                    -- MD5/SHA256 checksum

    -- Record Counts (Source)
    source_total_rows       BIGINT,                    -- Total rows in source file
    source_header_rows      INT DEFAULT 0,             -- Header rows skipped
    source_footer_rows      INT DEFAULT 0,             -- Footer rows skipped
    source_data_rows        BIGINT,                    -- Actual data rows (total - header - footer)

    -- Record Counts (Processing)
    rows_read               BIGINT,                    -- Rows successfully read
    rows_parsed             BIGINT,                    -- Rows successfully parsed
    rows_validated          BIGINT,                    -- Rows passing validation
    rows_transformed        BIGINT,                    -- Rows successfully transformed
    rows_rejected           BIGINT DEFAULT 0,          -- Rows failing validation
    rows_duplicate          BIGINT DEFAULT 0,          -- Duplicate rows found

    -- Record Counts (Target)
    rows_inserted           BIGINT DEFAULT 0,          -- New rows inserted
    rows_updated            BIGINT DEFAULT 0,          -- Existing rows updated (for delta)
    rows_deleted            BIGINT DEFAULT 0,          -- Rows deleted (for full refresh)
    rows_unchanged          BIGINT DEFAULT 0,          -- Rows with no changes (for delta)
    target_total_rows       BIGINT,                    -- Total rows in target after load

    -- Partition Information
    partitions_processed    STRING,                    -- JSON: [{"processing_date": "2026-02-10", "src_system": "GMP"}]
    partitions_overwritten  INT DEFAULT 0,             -- Number of partitions overwritten

    -- Data Quality Metrics
    null_count_by_column    STRING,                    -- JSON: {"col1": 10, "col2": 0}
    validation_errors       STRING,                    -- JSON: [{"row": 5, "column": "amount", "error": "NEGATIVE_VALUE"}]
    data_quality_score      DECIMAL(5,2),              -- 0-100% quality score

    -- Performance Metrics
    start_time              STRING NOT NULL,           -- Job start timestamp
    end_time                STRING,                    -- Job end timestamp
    duration_seconds        INT,                       -- Total duration
    read_time_seconds       INT,                       -- Time to read file
    transform_time_seconds  INT,                       -- Time for transformations
    write_time_seconds      INT,                       -- Time to write to target

    -- Spark Metrics
    executor_count          INT,                       -- Number of executors
    total_cores             INT,                       -- Total cores used
    peak_memory_mb          BIGINT,                    -- Peak memory usage
    shuffle_bytes           BIGINT,                    -- Shuffle data size

    -- Status
    status                  STRING NOT NULL,           -- RUNNING, SUCCESS, PARTIAL, FAILED
    error_message           STRING,                    -- Error details if failed
    error_stack_trace       STRING,                    -- Full stack trace
    warning_count           INT DEFAULT 0,             -- Number of warnings
    warnings                STRING,                    -- JSON array of warnings

    -- Reconciliation Checks
    recon_status            STRING,                    -- MATCHED, UNMATCHED, PENDING
    recon_notes             STRING,                    -- Manual recon notes
    recon_by                STRING,                    -- User who verified
    recon_at                STRING,                    -- Verification timestamp

    -- Retry Information
    retry_count             INT DEFAULT 0,             -- Number of retries
    is_rerun                BOOLEAN DEFAULT FALSE,     -- Is this a rerun
    original_batch_id       STRING,                    -- Original batch if rerun

    -- Audit
    created_at              STRING,
    created_by              STRING
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/data/gmp_cis/ingestion/cis_ingestion_recon'
TBLPROPERTIES (
    'parquet.compression' = 'SNAPPY'
);
```

---

## 3. Load Modes

### 3.1 FULL Load

Replaces all data in the target table/partition.

```
┌─────────────────────────────────────────────────────────────────┐
│                         FULL Load Mode                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Source File                           Target Table             │
│   ───────────                           ────────────             │
│   ┌─────────────┐                      ┌─────────────┐          │
│   │ All Records │─────────────────────▶│ OVERWRITE   │          │
│   │ (1000 rows) │                      │ All Data    │          │
│   └─────────────┘                      └─────────────┘          │
│                                                                  │
│   Use Cases:                                                     │
│   • Reference data refresh                                       │
│   • Initial loads                                                │
│   • Small dimension tables                                       │
│   • Daily position snapshots                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**
```python
df.write.mode("overwrite").format("parquet").save(target_location)
```

### 3.2 DELTA Load (Incremental/Append)

Appends new records based on watermark column.

```
┌─────────────────────────────────────────────────────────────────┐
│                        DELTA Load Mode                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Source File                           Target Table             │
│   ───────────                           ────────────             │
│   ┌─────────────┐                      ┌─────────────┐          │
│   │ All Records │                      │ Existing    │          │
│   │ (1000 rows) │                      │ (5000 rows) │          │
│   └──────┬──────┘                      └─────────────┘          │
│          │                                    │                  │
│          ▼                                    │                  │
│   ┌─────────────┐                             │                  │
│   │ Filter New  │                             │                  │
│   │ Records     │                             │                  │
│   │ (200 rows)  │                             │                  │
│   └──────┬──────┘                             │                  │
│          │                                    │                  │
│          └──────────── APPEND ────────────────┘                  │
│                                         (5200 rows)              │
│                                                                  │
│   Use Cases:                                                     │
│   • Transaction logs                                             │
│   • Event data                                                   │
│   • Audit trails                                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**
```python
# Get max watermark from target
max_watermark = spark.sql(f"SELECT MAX({watermark_col}) FROM {target_table}").first()[0]

# Filter new records
new_records_df = source_df.filter(col(watermark_col) > max_watermark)

# Append to target
new_records_df.write.mode("append").format("parquet").save(target_location)
```

### 3.3 OVERWRITE_PARTITION Mode

Overwrites only specified partitions, preserving others.

```
┌─────────────────────────────────────────────────────────────────┐
│                   OVERWRITE_PARTITION Mode                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Source File                           Target Table             │
│   (processing_date=2026-02-10)          (Partitioned)            │
│   ───────────────────────────           ─────────────            │
│   ┌─────────────┐                      ┌─────────────┐          │
│   │ 2026-02-10  │                      │ 2026-02-08  │ KEEP     │
│   │ (500 rows)  │                      │ 2026-02-09  │ KEEP     │
│   └──────┬──────┘                      │ 2026-02-10  │◀─REPLACE │
│          │                             └─────────────┘          │
│          │                                                       │
│          └─────────────────────────────────────────┘             │
│                                                                  │
│   Use Cases:                                                     │
│   • Re-running same day (fixes)                                  │
│   • Daily fact tables                                            │
│   • Time-series data                                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**
```python
# Dynamic partition overwrite
spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

df.write \
    .mode("overwrite") \
    .partitionBy(*partition_columns) \
    .format("parquet") \
    .save(target_location)
```

### 3.4 MERGE/UPSERT Mode (SCD Type 1)

Updates existing records, inserts new ones based on primary key.

```
┌─────────────────────────────────────────────────────────────────┐
│                      MERGE/UPSERT Mode                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Source: 1000 rows                     Target: 5000 rows        │
│   ─────────────────                     ────────────────         │
│                                                                  │
│   ┌─────────────┐     JOIN ON PK        ┌─────────────┐         │
│   │ Source Data │◀────────────────────▶ │ Target Data │         │
│   └──────┬──────┘                       └──────┬──────┘         │
│          │                                     │                 │
│          ▼                                     ▼                 │
│   ┌──────────────────────────────────────────────────┐          │
│   │  MATCHED (800 rows)          NOT MATCHED (200)   │          │
│   │  ─────────────────           ─────────────────   │          │
│   │  UPDATE existing             INSERT new          │          │
│   └──────────────────────────────────────────────────┘          │
│                                                                  │
│   Result: 5200 rows (5000 - 0 + 200)                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation (using temporary view approach for Parquet):**
```python
# Since Parquet doesn't support MERGE, we simulate it
existing_df = spark.read.parquet(target_location)
source_df = source_df.alias("source")
existing_df = existing_df.alias("target")

# Identify updates and inserts
updates = existing_df.join(source_df, pk_columns, "inner") \
    .select("source.*")

inserts = source_df.join(existing_df, pk_columns, "left_anti")

unchanged = existing_df.join(source_df, pk_columns, "left_anti")

# Union and write
final_df = updates.union(inserts).union(unchanged)
final_df.write.mode("overwrite").format("parquet").save(target_location)
```

---

## 4. Partition Handling Strategy

### 4.1 Partition Column Configuration

```json
{
    "partition_columns": "processing_date,src_system",
    "partition_type": "DYNAMIC"
}
```

### 4.2 Multi-Column Partitioning

```
/data/gmp_cis/positions/
├── processing_date=2026-02-08/
│   ├── src_system=GMP/
│   │   └── part-00000.parquet
│   ├── src_system=AMS/
│   │   └── part-00000.parquet
│   └── src_system=IMS/
│       └── part-00000.parquet
├── processing_date=2026-02-09/
│   ├── src_system=GMP/
│   └── ...
└── processing_date=2026-02-10/
    └── ...
```

### 4.3 Same-Day Rerun Logic

```python
def handle_same_day_rerun(processing_date, partition_columns, target_location):
    """
    If same processing_date is run again:
    1. Check if partition exists
    2. If exists and mode is OVERWRITE_PARTITION, replace it
    3. Log the overwrite in recon table with is_rerun=True
    """
    partition_path = f"{target_location}/processing_date={processing_date}"

    if path_exists(partition_path):
        logger.warning(f"Partition exists, will be overwritten: {partition_path}")
        # Dynamic partition overwrite will handle this automatically
        return True  # is_rerun = True

    return False  # is_rerun = False
```

---

## 5. PySpark Generic Ingestion Job

### 5.1 File: `sql/pyspark/generic_file_ingest.py`

```python
#!/usr/bin/env python3
"""
Generic File Ingestion Framework
================================
Metadata-driven PySpark job for ingesting CSV/TXT files into Hive External Tables (Parquet).

Usage:
    spark-submit generic_file_ingest.py \
        --source-id GMP_POSITIONS \
        --processing-date 2026-02-10 \
        --load-mode OVERWRITE_PARTITION \
        --batch-id BATCH_20260210_001

Parameters:
    --source-id         : Source identifier from cis_ingestion_config (required)
    --processing-date   : Processing date YYYY-MM-DD (default: today)
    --load-mode         : FULL, DELTA, OVERWRITE_PARTITION (default: from config)
    --batch-id          : Unique batch identifier (default: auto-generated)
    --file-path         : Override file path (optional)
    --dry-run           : Preview without writing (default: False)
    --validate-only     : Only validate, don't load (default: False)
    --reprocess         : Force reprocess even if already loaded (default: False)
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, lit, current_timestamp, expr, when, trim, upper, lower,
    to_date, to_timestamp, regexp_replace, coalesce, count, sum as spark_sum,
    md5, concat_ws, row_number
)
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, LongType,
    DecimalType, DateType, TimestampType, BooleanType, DoubleType
)
from pyspark.sql.window import Window

# ============================================================================
# LOGGING SETUP
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("GenericFileIngest")


# ============================================================================
# CONSTANTS
# ============================================================================
CONFIG_TABLE = "gmp_cis.cis_ingestion_config"
RECON_TABLE = "gmp_cis.cis_ingestion_recon"

TYPE_MAPPING = {
    "STRING": StringType(),
    "INT": IntegerType(),
    "INTEGER": IntegerType(),
    "BIGINT": LongType(),
    "LONG": LongType(),
    "DECIMAL": DecimalType(20, 6),
    "DOUBLE": DoubleType(),
    "FLOAT": DoubleType(),
    "DATE": DateType(),
    "TIMESTAMP": TimestampType(),
    "BOOLEAN": BooleanType(),
    "BOOL": BooleanType()
}


# ============================================================================
# CONFIGURATION LOADER
# ============================================================================
class ConfigLoader:
    """Loads ingestion configuration from metadata table."""

    def __init__(self, spark: SparkSession):
        self.spark = spark

    def load_config(self, source_id: str) -> Dict:
        """Load configuration for a source."""
        query = f"""
            SELECT * FROM {CONFIG_TABLE}
            WHERE source_id = '{source_id}'
            AND is_active = TRUE
        """
        config_df = self.spark.sql(query)

        if config_df.count() == 0:
            raise ValueError(f"No active configuration found for source_id: {source_id}")

        config_row = config_df.first()
        return config_row.asDict()

    def parse_column_schema(self, schema_json: str) -> Tuple[StructType, List[Dict]]:
        """Parse column schema JSON into Spark StructType."""
        columns = json.loads(schema_json)

        fields = []
        for col_def in columns:
            col_name = col_def["name"]
            col_type_str = col_def["type"].upper()
            nullable = col_def.get("nullable", True)

            # Handle DECIMAL with precision
            if col_type_str.startswith("DECIMAL"):
                import re
                match = re.match(r"DECIMAL\((\d+),\s*(\d+)\)", col_type_str)
                if match:
                    precision, scale = int(match.group(1)), int(match.group(2))
                    spark_type = DecimalType(precision, scale)
                else:
                    spark_type = DecimalType(20, 6)
            else:
                spark_type = TYPE_MAPPING.get(col_type_str, StringType())

            fields.append(StructField(col_name, spark_type, nullable))

        return StructType(fields), columns

    def parse_validation_rules(self, rules_json: Optional[str]) -> List[Dict]:
        """Parse validation rules JSON."""
        if not rules_json:
            return []
        return json.loads(rules_json)

    def parse_transformations(self, transform_json: Optional[str]) -> List[Dict]:
        """Parse transformation rules JSON."""
        if not transform_json:
            return []
        return json.loads(transform_json)


# ============================================================================
# FILE READER
# ============================================================================
class FileReader:
    """Reads source files based on configuration."""

    def __init__(self, spark: SparkSession, config: Dict):
        self.spark = spark
        self.config = config

    def read_file(self, file_path: str) -> DataFrame:
        """Read file based on file type configuration."""
        file_type = self.config["file_type"].upper()

        options = {
            "header": str(self.config.get("has_header", True)).lower(),
            "encoding": self.config.get("file_encoding", "UTF-8"),
            "quote": self.config.get("quote_char", '"'),
            "escape": self.config.get("escape_char", "\\"),
            "nullValue": self.config.get("null_string", ""),
            "mode": "PERMISSIVE",
            "columnNameOfCorruptRecord": "_corrupt_record"
        }

        if file_type in ("CSV", "TXT"):
            options["sep"] = self.config.get("column_delimiter", ",")
        elif file_type == "PIPE":
            options["sep"] = "|"
        elif file_type == "TAB":
            options["sep"] = "\t"
        elif file_type == "FIXED_WIDTH":
            # For fixed-width, read as single column then parse
            return self._read_fixed_width(file_path)

        df = self.spark.read.options(**options).csv(file_path)

        # Skip rows if configured
        skip_rows = self.config.get("skip_rows", 0)
        skip_footer = self.config.get("skip_footer_rows", 0)

        if skip_rows > 0 or skip_footer > 0:
            df = self._skip_rows(df, skip_rows, skip_footer)

        return df

    def _read_fixed_width(self, file_path: str) -> DataFrame:
        """Read fixed-width format file."""
        # Read as text
        raw_df = self.spark.read.text(file_path)

        # Parse column positions from schema
        columns = json.loads(self.config["column_schema"])

        exprs = []
        for col_def in columns:
            start = col_def.get("start_position", 0)
            length = col_def.get("length", 10)
            name = col_def["name"]
            exprs.append(
                trim(raw_df.value.substr(start + 1, length)).alias(name)
            )

        return raw_df.select(*exprs)

    def _skip_rows(self, df: DataFrame, skip_header: int, skip_footer: int) -> DataFrame:
        """Skip header and footer rows."""
        if skip_header == 0 and skip_footer == 0:
            return df

        # Add row number
        w = Window.orderBy(lit(1))
        df_numbered = df.withColumn("_row_num", row_number().over(w))

        total_rows = df_numbered.count()

        # Filter
        return df_numbered.filter(
            (col("_row_num") > skip_header) &
            (col("_row_num") <= total_rows - skip_footer)
        ).drop("_row_num")


# ============================================================================
# DATA VALIDATOR
# ============================================================================
class DataValidator:
    """Validates data based on configuration rules."""

    def __init__(self, spark: SparkSession, rules: List[Dict]):
        self.spark = spark
        self.rules = rules

    def validate(self, df: DataFrame) -> Tuple[DataFrame, DataFrame, Dict]:
        """
        Validate DataFrame and separate valid/invalid records.
        Returns: (valid_df, rejected_df, validation_stats)
        """
        if not self.rules:
            return df, self.spark.createDataFrame([], df.schema), {"errors": []}

        # Build validation expression
        error_conditions = []

        for rule in self.rules:
            column = rule["column"]
            rule_type = rule["rule"].upper()

            if rule_type == "NOT_NULL":
                cond = col(column).isNull()
                msg = f"{column}_IS_NULL"

            elif rule_type == "POSITIVE":
                cond = col(column) <= 0
                msg = f"{column}_NOT_POSITIVE"

            elif rule_type == "REGEX":
                pattern = rule["pattern"]
                cond = ~col(column).rlike(pattern)
                msg = f"{column}_REGEX_FAIL"

            elif rule_type == "IN_LIST":
                values = rule["values"]
                cond = ~col(column).isin(values)
                msg = f"{column}_NOT_IN_LIST"

            elif rule_type == "RANGE":
                min_val = rule.get("min")
                max_val = rule.get("max")
                cond = (col(column) < min_val) | (col(column) > max_val)
                msg = f"{column}_OUT_OF_RANGE"

            elif rule_type == "DATE_FORMAT":
                # Attempt to parse, if fails it's invalid
                fmt = rule.get("format", "yyyy-MM-dd")
                cond = to_date(col(column), fmt).isNull()
                msg = f"{column}_INVALID_DATE"

            else:
                continue

            error_conditions.append((cond, msg))

        # Add validation error column
        if error_conditions:
            # Combine all conditions
            validation_error = lit(None).cast(StringType())
            for cond, msg in error_conditions:
                validation_error = when(cond, msg).otherwise(validation_error)

            df = df.withColumn("_validation_error", validation_error)

            valid_df = df.filter(col("_validation_error").isNull()).drop("_validation_error")
            rejected_df = df.filter(col("_validation_error").isNotNull())

            # Collect stats
            error_stats = rejected_df.groupBy("_validation_error").count().collect()
            validation_stats = {
                "errors": [{"error": row["_validation_error"], "count": row["count"]} for row in error_stats]
            }
        else:
            valid_df = df
            rejected_df = self.spark.createDataFrame([], df.schema)
            validation_stats = {"errors": []}

        return valid_df, rejected_df, validation_stats


# ============================================================================
# DATA TRANSFORMER
# ============================================================================
class DataTransformer:
    """Applies transformations based on configuration."""

    def __init__(self, spark: SparkSession, transformations: List[Dict]):
        self.spark = spark
        self.transformations = transformations

    def transform(self, df: DataFrame) -> DataFrame:
        """Apply all transformations."""
        for transform in self.transformations:
            column = transform["column"]
            transform_expr = transform["transform"]

            # Handle special cases
            if transform_expr.startswith("LITERAL("):
                # Extract literal value
                value = transform_expr[8:-1].strip("'\"")
                df = df.withColumn(column, lit(value))
            elif transform_expr == "CURRENT_DATE()":
                df = df.withColumn(column, expr("current_date()"))
            elif transform_expr == "CURRENT_TIMESTAMP()":
                df = df.withColumn(column, current_timestamp())
            else:
                # Use Spark SQL expression
                df = df.withColumn(column, expr(transform_expr))

        return df


# ============================================================================
# DATA WRITER
# ============================================================================
class DataWriter:
    """Writes data to target based on load mode."""

    def __init__(self, spark: SparkSession, config: Dict):
        self.spark = spark
        self.config = config

    def write(self, df: DataFrame, load_mode: str, processing_date: str) -> Dict:
        """
        Write DataFrame to target.
        Returns write statistics.
        """
        target_location = self.config["target_location"]
        partition_columns = self.config.get("partition_columns", "").split(",")
        partition_columns = [c.strip() for c in partition_columns if c.strip()]

        stats = {
            "rows_written": df.count(),
            "partitions_processed": [],
            "mode": load_mode
        }

        if load_mode == "FULL":
            # Full overwrite
            writer = df.write.mode("overwrite")

        elif load_mode == "DELTA":
            # Append only
            writer = df.write.mode("append")

        elif load_mode == "OVERWRITE_PARTITION":
            # Dynamic partition overwrite
            self.spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
            writer = df.write.mode("overwrite")

            # Get unique partition values
            if partition_columns:
                partition_values = df.select(partition_columns).distinct().collect()
                stats["partitions_processed"] = [
                    {col: str(row[col]) for col in partition_columns}
                    for row in partition_values
                ]

        elif load_mode == "MERGE":
            # Simulate MERGE for Parquet
            stats = self._merge_write(df, target_location, partition_columns)
            return stats

        else:
            raise ValueError(f"Unknown load mode: {load_mode}")

        # Apply partitioning if configured
        if partition_columns:
            writer = writer.partitionBy(*partition_columns)

        # Write as Parquet
        writer.format("parquet") \
            .option("compression", "snappy") \
            .save(target_location)

        return stats

    def _merge_write(self, source_df: DataFrame, target_location: str,
                     partition_columns: List[str]) -> Dict:
        """Simulate MERGE/UPSERT for Parquet tables."""
        pk_columns = self.config.get("primary_key_columns", "").split(",")
        pk_columns = [c.strip() for c in pk_columns if c.strip()]

        if not pk_columns:
            raise ValueError("MERGE mode requires primary_key_columns configuration")

        stats = {
            "rows_inserted": 0,
            "rows_updated": 0,
            "rows_unchanged": 0,
            "mode": "MERGE"
        }

        # Check if target exists
        try:
            existing_df = self.spark.read.parquet(target_location)
        except:
            # Target doesn't exist, just write
            source_df.write.mode("overwrite") \
                .partitionBy(*partition_columns) if partition_columns else source_df.write \
                .format("parquet") \
                .option("compression", "snappy") \
                .save(target_location)
            stats["rows_inserted"] = source_df.count()
            return stats

        # Perform merge logic
        source_df = source_df.alias("source")
        existing_df = existing_df.alias("target")

        # Matched records (updates)
        updates = source_df.join(existing_df, pk_columns, "inner").select("source.*")
        stats["rows_updated"] = updates.count()

        # New records (inserts)
        inserts = source_df.join(existing_df, pk_columns, "left_anti")
        stats["rows_inserted"] = inserts.count()

        # Unchanged records (not in source)
        unchanged = existing_df.join(source_df, pk_columns, "left_anti")
        stats["rows_unchanged"] = unchanged.count()

        # Combine and write
        final_df = updates.unionByName(inserts).unionByName(unchanged)

        writer = final_df.write.mode("overwrite")
        if partition_columns:
            writer = writer.partitionBy(*partition_columns)

        writer.format("parquet") \
            .option("compression", "snappy") \
            .save(target_location)

        return stats


# ============================================================================
# RECONCILIATION WRITER
# ============================================================================
class ReconWriter:
    """Writes reconciliation records."""

    def __init__(self, spark: SparkSession):
        self.spark = spark

    def write_recon(self, recon_data: Dict, processing_date: str):
        """Write reconciliation record."""
        recon_id = int(time.time() * 1000)
        recon_data["recon_id"] = recon_id
        recon_data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Convert to DataFrame
        recon_df = self.spark.createDataFrame([recon_data])

        # Write to recon table partition
        recon_location = f"/data/gmp_cis/ingestion/cis_ingestion_recon/processing_date={processing_date}"

        recon_df.write.mode("append") \
            .format("parquet") \
            .option("compression", "snappy") \
            .save(recon_location)

        logger.info(f"Reconciliation record written: {recon_id}")


# ============================================================================
# MAIN INGESTION ENGINE
# ============================================================================
class IngestionEngine:
    """Main orchestration engine for file ingestion."""

    def __init__(self, spark: SparkSession, args: argparse.Namespace):
        self.spark = spark
        self.args = args
        self.config_loader = ConfigLoader(spark)
        self.recon_writer = ReconWriter(spark)

        # Load configuration
        self.config = self.config_loader.load_config(args.source_id)

        # Parse schemas and rules
        self.schema, self.column_defs = self.config_loader.parse_column_schema(
            self.config["column_schema"]
        )
        self.validation_rules = self.config_loader.parse_validation_rules(
            self.config.get("validation_rules")
        )
        self.transformations = self.config_loader.parse_transformations(
            self.config.get("transformations")
        )

    def run(self) -> Dict:
        """Execute the ingestion pipeline."""
        start_time = datetime.now()
        recon_data = {
            "config_id": self.config["config_id"],
            "source_id": self.args.source_id,
            "batch_id": self.args.batch_id,
            "run_mode": self.args.load_mode or self.config["default_load_mode"],
            "run_environment": self._get_environment(),
            "spark_app_id": self.spark.sparkContext.applicationId,
            "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "RUNNING"
        }

        try:
            # 1. Determine file path
            file_path = self.args.file_path or self._resolve_file_path()
            recon_data["file_path"] = file_path
            recon_data["file_name"] = file_path.split("/")[-1]

            logger.info(f"Processing file: {file_path}")

            # 2. Read file
            read_start = time.time()
            file_reader = FileReader(self.spark, self.config)
            raw_df = file_reader.read_file(file_path)
            read_time = int(time.time() - read_start)

            recon_data["source_total_rows"] = raw_df.count()
            recon_data["rows_read"] = recon_data["source_total_rows"]
            recon_data["read_time_seconds"] = read_time

            logger.info(f"Read {recon_data['rows_read']} rows in {read_time}s")

            # 3. Validate
            validator = DataValidator(self.spark, self.validation_rules)
            valid_df, rejected_df, validation_stats = validator.validate(raw_df)

            recon_data["rows_validated"] = valid_df.count()
            recon_data["rows_rejected"] = rejected_df.count()
            recon_data["validation_errors"] = json.dumps(validation_stats["errors"])

            logger.info(f"Validated: {recon_data['rows_validated']} valid, {recon_data['rows_rejected']} rejected")

            # 4. Transform
            transform_start = time.time()
            transformer = DataTransformer(self.spark, self.transformations)
            transformed_df = transformer.transform(valid_df)
            transform_time = int(time.time() - transform_start)

            recon_data["rows_transformed"] = transformed_df.count()
            recon_data["transform_time_seconds"] = transform_time

            # 5. Add processing metadata
            processing_date = self.args.processing_date
            transformed_df = transformed_df \
                .withColumn("processing_date", lit(processing_date)) \
                .withColumn("batch_id", lit(self.args.batch_id)) \
                .withColumn("etl_load_timestamp", lit(int(time.time() * 1000)))

            # 6. Check for rerun
            is_rerun = self._check_rerun(processing_date)
            recon_data["is_rerun"] = is_rerun

            if self.args.dry_run:
                logger.info("DRY RUN - Preview of data:")
                transformed_df.show(20, truncate=False)
                recon_data["status"] = "DRY_RUN"
            elif self.args.validate_only:
                logger.info("VALIDATE ONLY - No data written")
                recon_data["status"] = "VALIDATED"
            else:
                # 7. Write to target
                write_start = time.time()
                writer = DataWriter(self.spark, self.config)
                load_mode = self.args.load_mode or self.config["default_load_mode"]
                write_stats = writer.write(transformed_df, load_mode, processing_date)
                write_time = int(time.time() - write_start)

                recon_data["rows_inserted"] = write_stats.get("rows_inserted", write_stats.get("rows_written", 0))
                recon_data["rows_updated"] = write_stats.get("rows_updated", 0)
                recon_data["write_time_seconds"] = write_time
                recon_data["partitions_processed"] = json.dumps(write_stats.get("partitions_processed", []))
                recon_data["status"] = "SUCCESS"

                logger.info(f"Write completed in {write_time}s")

                # 8. Refresh table metadata
                self._refresh_table()

            # Calculate totals
            end_time = datetime.now()
            recon_data["end_time"] = end_time.strftime("%Y-%m-%d %H:%M:%S")
            recon_data["duration_seconds"] = int((end_time - start_time).total_seconds())

            # Calculate quality score
            total = recon_data.get("source_total_rows", 0)
            valid = recon_data.get("rows_validated", 0)
            recon_data["data_quality_score"] = round((valid / total * 100) if total > 0 else 0, 2)

        except Exception as e:
            logger.error(f"Ingestion failed: {str(e)}")
            recon_data["status"] = "FAILED"
            recon_data["error_message"] = str(e)
            recon_data["error_stack_trace"] = traceback.format_exc()
            recon_data["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            raise

        finally:
            # Write reconciliation record
            self.recon_writer.write_recon(recon_data, self.args.processing_date)

        return recon_data

    def _resolve_file_path(self) -> str:
        """Resolve actual file path from pattern."""
        base_path = self.config["file_path"]
        pattern = self.config["file_name_pattern"]

        # Replace date placeholders
        processing_date = self.args.processing_date
        date_obj = datetime.strptime(processing_date, "%Y-%m-%d")

        path = base_path.replace("{YYYY}", date_obj.strftime("%Y"))
        path = path.replace("{MM}", date_obj.strftime("%m"))
        path = path.replace("{DD}", date_obj.strftime("%d"))
        path = path.replace("{YYYYMMDD}", date_obj.strftime("%Y%m%d"))

        # For wildcard patterns, use glob
        if "*" in pattern:
            import glob
            files = glob.glob(f"{path}/{pattern}")
            if not files:
                raise FileNotFoundError(f"No files found matching: {path}/{pattern}")
            return sorted(files)[-1]  # Return latest file

        return f"{path}/{pattern}"

    def _check_rerun(self, processing_date: str) -> bool:
        """Check if this is a rerun for the same processing date."""
        query = f"""
            SELECT COUNT(*) as cnt FROM {RECON_TABLE}
            WHERE source_id = '{self.args.source_id}'
            AND processing_date = '{processing_date}'
            AND status = 'SUCCESS'
        """
        try:
            result = self.spark.sql(query).first()
            return result["cnt"] > 0
        except:
            return False

    def _refresh_table(self):
        """Refresh Hive table metadata after write."""
        target_db = self.config["target_database"]
        target_table = self.config["target_table"]

        try:
            self.spark.sql(f"REFRESH {target_db}.{target_table}")
            logger.info(f"Refreshed table: {target_db}.{target_table}")
        except:
            try:
                self.spark.sql(f"MSCK REPAIR TABLE {target_db}.{target_table}")
                logger.info(f"Repaired partitions: {target_db}.{target_table}")
            except Exception as e:
                logger.warning(f"Could not refresh table metadata: {e}")

    def _get_environment(self) -> str:
        """Determine runtime environment."""
        # Check for environment indicators
        try:
            conf = self.spark.sparkContext.getConf()
            master = conf.get("spark.master", "")
            if "local" in master:
                return "DEV"
            elif "yarn" in master:
                return "PROD"
            else:
                return "UNKNOWN"
        except:
            return "UNKNOWN"


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Generic File Ingestion Framework")

    parser.add_argument("--source-id", required=True,
                        help="Source identifier from cis_ingestion_config")
    parser.add_argument("--processing-date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="Processing date (YYYY-MM-DD)")
    parser.add_argument("--load-mode", choices=["FULL", "DELTA", "OVERWRITE_PARTITION", "MERGE"],
                        help="Load mode (overrides config default)")
    parser.add_argument("--batch-id", default=None,
                        help="Batch identifier (auto-generated if not provided)")
    parser.add_argument("--file-path",
                        help="Override file path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing")
    parser.add_argument("--validate-only", action="store_true",
                        help="Only validate, don't load")
    parser.add_argument("--reprocess", action="store_true",
                        help="Force reprocess even if already loaded")

    args = parser.parse_args()

    # Generate batch ID if not provided
    if not args.batch_id:
        args.batch_id = f"BATCH_{args.processing_date.replace('-', '')}_{int(time.time()) % 1000:03d}"

    return args


def main():
    """Main entry point."""
    args = parse_args()

    logger.info("=" * 70)
    logger.info("GENERIC FILE INGESTION FRAMEWORK")
    logger.info("=" * 70)
    logger.info(f"Source ID      : {args.source_id}")
    logger.info(f"Processing Date: {args.processing_date}")
    logger.info(f"Load Mode      : {args.load_mode or 'FROM_CONFIG'}")
    logger.info(f"Batch ID       : {args.batch_id}")
    logger.info(f"Dry Run        : {args.dry_run}")
    logger.info("=" * 70)

    # Initialize Spark
    spark = SparkSession.builder \
        .appName(f"FileIngest_{args.source_id}_{args.processing_date}") \
        .enableHiveSupport() \
        .getOrCreate()

    try:
        engine = IngestionEngine(spark, args)
        result = engine.run()

        logger.info("=" * 70)
        logger.info("INGESTION COMPLETE")
        logger.info(f"Status         : {result['status']}")
        logger.info(f"Rows Read      : {result.get('rows_read', 0)}")
        logger.info(f"Rows Validated : {result.get('rows_validated', 0)}")
        logger.info(f"Rows Rejected  : {result.get('rows_rejected', 0)}")
        logger.info(f"Rows Written   : {result.get('rows_inserted', 0) + result.get('rows_updated', 0)}")
        logger.info(f"Duration       : {result.get('duration_seconds', 0)}s")
        logger.info(f"Quality Score  : {result.get('data_quality_score', 0)}%")
        logger.info("=" * 70)

        return 0 if result['status'] in ('SUCCESS', 'DRY_RUN', 'VALIDATED') else 1

    except Exception as e:
        logger.error(f"INGESTION FAILED: {str(e)}")
        return 1

    finally:
        spark.stop()


if __name__ == "__main__":
    import traceback
    sys.exit(main())
```

---

## 6. DDL Files

### 6.1 Create DDL: `sql/ddl/20_ingestion_framework.sql`

```sql
-- ============================================================================
-- DATA INGESTION FRAMEWORK DDL
-- ============================================================================
-- Creates metadata and reconciliation tables for the ingestion framework
-- All tables use Hive External with Parquet format
-- Database: gmp_cis
-- Created: 2026-02-10
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- HDFS DIRECTORY SETUP
-- ============================================================================
-- Run these commands before creating tables:
-- hdfs dfs -mkdir -p /data/gmp_cis/ingestion/cis_ingestion_config
-- hdfs dfs -mkdir -p /data/gmp_cis/ingestion/cis_ingestion_recon
-- hdfs dfs -chmod 777 /data/gmp_cis/ingestion/cis_ingestion_config
-- hdfs dfs -chmod 777 /data/gmp_cis/ingestion/cis_ingestion_recon
-- ============================================================================


-- ============================================================================
-- TABLE 1: cis_ingestion_config (Metadata Configuration)
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_ingestion_config;

CREATE EXTERNAL TABLE gmp_cis.cis_ingestion_config (
    config_id               BIGINT,
    source_id               STRING,
    source_name             STRING,
    source_description      STRING,
    source_system           STRING,
    file_type               STRING,
    file_name_pattern       STRING,
    file_path               STRING,
    file_encoding           STRING,
    has_header              BOOLEAN,
    skip_rows               INT,
    skip_footer_rows        INT,
    column_delimiter        STRING,
    quote_char              STRING,
    escape_char             STRING,
    null_string             STRING,
    column_schema           STRING,
    target_database         STRING,
    target_table            STRING,
    target_location         STRING,
    partition_columns       STRING,
    partition_type          STRING,
    default_load_mode       STRING,
    primary_key_columns     STRING,
    watermark_column        STRING,
    validation_rules        STRING,
    transformations         STRING,
    schedule_frequency      STRING,
    expected_arrival_time   STRING,
    sla_minutes             INT,
    is_active               BOOLEAN,
    priority                INT,
    created_by              STRING,
    created_at              STRING,
    updated_by              STRING,
    updated_at              STRING
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/ingestion/cis_ingestion_config'
TBLPROPERTIES (
    'parquet.compression' = 'SNAPPY'
);


-- ============================================================================
-- TABLE 2: cis_ingestion_recon (Reconciliation/Audit)
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_ingestion_recon;

CREATE EXTERNAL TABLE gmp_cis.cis_ingestion_recon (
    recon_id                BIGINT,
    config_id               BIGINT,
    source_id               STRING,
    batch_id                STRING,
    run_mode                STRING,
    run_environment         STRING,
    spark_app_id            STRING,
    file_name               STRING,
    file_path               STRING,
    file_size_bytes         BIGINT,
    file_modified_time      STRING,
    file_checksum           STRING,
    source_total_rows       BIGINT,
    source_header_rows      INT,
    source_footer_rows      INT,
    source_data_rows        BIGINT,
    rows_read               BIGINT,
    rows_parsed             BIGINT,
    rows_validated          BIGINT,
    rows_transformed        BIGINT,
    rows_rejected           BIGINT,
    rows_duplicate          BIGINT,
    rows_inserted           BIGINT,
    rows_updated            BIGINT,
    rows_deleted            BIGINT,
    rows_unchanged          BIGINT,
    target_total_rows       BIGINT,
    partitions_processed    STRING,
    partitions_overwritten  INT,
    null_count_by_column    STRING,
    validation_errors       STRING,
    data_quality_score      DECIMAL(5,2),
    start_time              STRING,
    end_time                STRING,
    duration_seconds        INT,
    read_time_seconds       INT,
    transform_time_seconds  INT,
    write_time_seconds      INT,
    executor_count          INT,
    total_cores             INT,
    peak_memory_mb          BIGINT,
    shuffle_bytes           BIGINT,
    status                  STRING,
    error_message           STRING,
    error_stack_trace       STRING,
    warning_count           INT,
    warnings                STRING,
    recon_status            STRING,
    recon_notes             STRING,
    recon_by                STRING,
    recon_at                STRING,
    retry_count             INT,
    is_rerun                BOOLEAN,
    original_batch_id       STRING,
    created_at              STRING,
    created_by              STRING
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/data/gmp_cis/ingestion/cis_ingestion_recon'
TBLPROPERTIES (
    'parquet.compression' = 'SNAPPY'
);


-- ============================================================================
-- SEQUENCE INITIALIZATION
-- ============================================================================

UPSERT INTO gmp_cis.cis_sequence VALUES ('ingestion_config_id', 1000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('ingestion_recon_id', 1000000, 1);


-- ============================================================================
-- VERIFICATION
-- ============================================================================

DESCRIBE gmp_cis.cis_ingestion_config;
DESCRIBE gmp_cis.cis_ingestion_recon;

SELECT * FROM gmp_cis.cis_sequence WHERE sequence_name LIKE 'ingestion%';


-- ============================================================================
-- END OF DDL
-- ============================================================================
```

---

## 7. Example Configuration

### 7.1 Sample Configuration Insert

```sql
-- Insert sample configuration for GMP Positions file
INSERT INTO gmp_cis.cis_ingestion_config VALUES (
    1001,                                    -- config_id
    'GMP_POSITIONS',                         -- source_id
    'GMP Daily Positions',                   -- source_name
    'Daily position file from Global Markets Platform', -- source_description
    'GMP',                                   -- source_system
    'CSV',                                   -- file_type
    'gmp_positions_{YYYYMMDD}.csv',          -- file_name_pattern
    '/data/incoming/gmp',                    -- file_path
    'UTF-8',                                 -- file_encoding
    TRUE,                                    -- has_header
    0,                                       -- skip_rows
    0,                                       -- skip_footer_rows
    ',',                                     -- column_delimiter
    '"',                                     -- quote_char
    '\\',                                    -- escape_char
    '',                                      -- null_string
    '[
        {"name": "portfolio_id", "type": "STRING", "source_position": 0, "nullable": false},
        {"name": "security_label", "type": "STRING", "source_position": 1, "nullable": false},
        {"name": "isin", "type": "STRING", "source_position": 2},
        {"name": "quantity", "type": "DECIMAL(20,6)", "source_position": 3},
        {"name": "market_value", "type": "DECIMAL(20,6)", "source_position": 4},
        {"name": "price_date", "type": "STRING", "source_position": 5, "format": "yyyyMMdd"}
    ]',                                      -- column_schema
    'gmp_cis',                               -- target_database
    'stg_gmp_positions',                     -- target_table
    '/data/gmp_cis/staging/stg_gmp_positions', -- target_location
    'processing_date,src_system',            -- partition_columns
    'DYNAMIC',                               -- partition_type
    'OVERWRITE_PARTITION',                   -- default_load_mode
    'portfolio_id,security_label,price_date', -- primary_key_columns
    'price_date',                            -- watermark_column
    '[
        {"column": "portfolio_id", "rule": "NOT_NULL"},
        {"column": "security_label", "rule": "NOT_NULL"},
        {"column": "quantity", "rule": "POSITIVE"}
    ]',                                      -- validation_rules
    '[
        {"column": "security_label", "transform": "UPPER(TRIM(security_label))"},
        {"column": "src_system", "transform": "LITERAL(''GMP'')"},
        {"column": "price_date", "transform": "TO_DATE(price_date, ''yyyyMMdd'')"}
    ]',                                      -- transformations
    'DAILY',                                 -- schedule_frequency
    '06:00',                                 -- expected_arrival_time
    60,                                      -- sla_minutes
    TRUE,                                    -- is_active
    5,                                       -- priority
    'SYSTEM',                                -- created_by
    '2026-02-10 00:00:00',                   -- created_at
    NULL,                                    -- updated_by
    NULL                                     -- updated_at
);
```

---

## 8. Usage Examples

### 8.1 Full Load

```bash
spark-submit --master yarn \
    --deploy-mode cluster \
    --conf spark.executor.memory=4g \
    --conf spark.executor.cores=2 \
    --conf spark.dynamicAllocation.enabled=true \
    generic_file_ingest.py \
    --source-id GMP_POSITIONS \
    --processing-date 2026-02-10 \
    --load-mode FULL \
    --batch-id BATCH_20260210_001
```

### 8.2 Delta Load (Incremental)

```bash
spark-submit generic_file_ingest.py \
    --source-id TRADE_EVENTS \
    --processing-date 2026-02-10 \
    --load-mode DELTA
```

### 8.3 Partition Overwrite (Same Day Rerun)

```bash
spark-submit generic_file_ingest.py \
    --source-id GMP_POSITIONS \
    --processing-date 2026-02-10 \
    --load-mode OVERWRITE_PARTITION \
    --reprocess
```

### 8.4 Dry Run (Preview)

```bash
spark-submit generic_file_ingest.py \
    --source-id GMP_POSITIONS \
    --processing-date 2026-02-10 \
    --dry-run
```

### 8.5 Validate Only

```bash
spark-submit generic_file_ingest.py \
    --source-id GMP_POSITIONS \
    --processing-date 2026-02-10 \
    --validate-only
```

---

## 9. Corner Cases & Error Handling

### 9.1 Empty File

```python
if raw_df.count() == 0:
    logger.warning("Source file is empty")
    recon_data["status"] = "SUCCESS"
    recon_data["warning_count"] = 1
    recon_data["warnings"] = json.dumps(["Source file is empty"])
    # Still write recon, but skip data write
```

### 9.2 File Not Found

```python
except FileNotFoundError as e:
    logger.error(f"File not found: {e}")
    recon_data["status"] = "FAILED"
    recon_data["error_message"] = f"File not found: {str(e)}"
    # Write recon with FAILED status
```

### 9.3 Schema Mismatch

```python
# Validate column count matches
expected_cols = len(json.loads(config["column_schema"]))
actual_cols = len(raw_df.columns)

if expected_cols != actual_cols:
    raise ValueError(
        f"Schema mismatch: expected {expected_cols} columns, got {actual_cols}"
    )
```

### 9.4 Duplicate Records

```python
# Detect duplicates based on PK
pk_cols = config.get("primary_key_columns", "").split(",")
if pk_cols:
    window = Window.partitionBy(*pk_cols).orderBy(lit(1))
    df_with_rn = df.withColumn("_dup_rn", row_number().over(window))

    duplicates = df_with_rn.filter(col("_dup_rn") > 1)
    recon_data["rows_duplicate"] = duplicates.count()

    # Keep only first occurrence
    df = df_with_rn.filter(col("_dup_rn") == 1).drop("_dup_rn")
```

### 9.5 All Rows Rejected

```python
if recon_data["rows_validated"] == 0 and recon_data["rows_rejected"] > 0:
    logger.error("All rows failed validation")
    recon_data["status"] = "FAILED"
    recon_data["error_message"] = "All rows failed validation"
```

### 9.6 Partial Success

```python
rejection_rate = recon_data["rows_rejected"] / recon_data["source_total_rows"]
if rejection_rate > 0.1:  # More than 10% rejected
    recon_data["status"] = "PARTIAL"
    recon_data["warnings"] = json.dumps([
        f"High rejection rate: {rejection_rate*100:.2f}%"
    ])
```

### 9.7 Target Table Locked

```python
max_retries = 3
for attempt in range(max_retries):
    try:
        writer.write(df, load_mode, processing_date)
        break
    except Exception as e:
        if "lock" in str(e).lower() and attempt < max_retries - 1:
            logger.warning(f"Table locked, retrying in 30s (attempt {attempt+1})")
            time.sleep(30)
            recon_data["retry_count"] = attempt + 1
        else:
            raise
```

---

## 10. Monitoring & Alerts

### 10.1 Reconciliation Queries

```sql
-- Daily ingestion summary
SELECT
    source_id,
    processing_date,
    status,
    rows_read,
    rows_validated,
    rows_rejected,
    data_quality_score,
    duration_seconds
FROM gmp_cis.cis_ingestion_recon
WHERE processing_date = '2026-02-10'
ORDER BY source_id;

-- Failed jobs
SELECT
    source_id,
    batch_id,
    error_message,
    start_time
FROM gmp_cis.cis_ingestion_recon
WHERE processing_date = CURRENT_DATE()
AND status = 'FAILED';

-- High rejection rate
SELECT
    source_id,
    batch_id,
    rows_rejected,
    rows_read,
    ROUND(rows_rejected * 100.0 / rows_read, 2) as rejection_pct
FROM gmp_cis.cis_ingestion_recon
WHERE processing_date = CURRENT_DATE()
AND rows_rejected > 0
ORDER BY rejection_pct DESC;

-- SLA breaches
SELECT
    c.source_id,
    c.expected_arrival_time,
    c.sla_minutes,
    r.start_time,
    r.status
FROM gmp_cis.cis_ingestion_config c
LEFT JOIN gmp_cis.cis_ingestion_recon r
    ON c.source_id = r.source_id
    AND r.processing_date = CURRENT_DATE()
WHERE c.is_active = TRUE
AND (r.status IS NULL OR r.status = 'FAILED');
```

---

## 11. Extensibility

### 11.1 Adding New File Types

To add support for new file types (e.g., JSON, XML, Excel):

1. Add to `FileReader.read_file()`:
```python
elif file_type == "JSON":
    df = self.spark.read.json(file_path)
elif file_type == "XML":
    df = self.spark.read.format("xml").option("rowTag", "record").load(file_path)
elif file_type == "EXCEL":
    # Requires spark-excel library
    df = self.spark.read.format("excel").option("header", "true").load(file_path)
```

2. Add configuration for new file type in `cis_ingestion_config`.

### 11.2 Adding Custom Validation Rules

Add new rule types in `DataValidator.validate()`:
```python
elif rule_type == "UNIQUE":
    # Check for uniqueness
    ...
elif rule_type == "FOREIGN_KEY":
    # Check against reference table
    ...
```

### 11.3 Adding Custom Transformations

Add new transform types in `DataTransformer.transform()`:
```python
elif transform_expr.startswith("LOOKUP("):
    # Lookup from reference table
    ...
elif transform_expr.startswith("ENCRYPT("):
    # Encrypt sensitive data
    ...
```

---

## 12. HDFS Directory Structure

```
/data/gmp_cis/
├── ingestion/
│   ├── cis_ingestion_config/           # Metadata configuration
│   │   └── *.parquet
│   └── cis_ingestion_recon/            # Reconciliation/audit
│       ├── processing_date=2026-02-08/
│       ├── processing_date=2026-02-09/
│       └── processing_date=2026-02-10/
│
├── incoming/                           # Source file landing zone
│   ├── gmp/
│   │   └── gmp_positions_20260210.csv
│   ├── ams/
│   └── ims/
│
├── staging/                            # Staging tables (Hive/Parquet)
│   ├── stg_gmp_positions/
│   │   └── processing_date=2026-02-10/
│   │       └── src_system=GMP/
│   ├── stg_ams_positions/
│   └── stg_ims_positions/
│
├── master/                             # Master tables (Hive/Parquet)
│   ├── cis_position_master/
│   └── cis_security_master/
│
└── archive/                            # Archived source files
    ├── 2026/
    │   ├── 02/
    │   │   ├── 08/
    │   │   ├── 09/
    │   │   └── 10/
```

---

## 13. Best Practices

1. **Always use OVERWRITE_PARTITION for daily loads** - Enables easy reruns without data duplication

2. **Configure validation rules** - Catch data quality issues early

3. **Use appropriate compression** - SNAPPY for balance of speed/size

4. **Monitor reconciliation table** - Set up alerts for failures and high rejection rates

5. **Partition wisely** - Use `processing_date` as primary partition for time-series data

6. **Document column schemas** - Include descriptions in column_schema JSON

7. **Test with dry-run first** - Validate before writing to production

8. **Archive source files** - Move processed files to archive after successful load

9. **Set appropriate SLAs** - Configure expected arrival times and SLA minutes

10. **Use batch IDs consistently** - Enables traceability across runs

---

Last updated: 2026-02-10
