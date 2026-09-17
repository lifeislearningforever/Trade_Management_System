# ETL Trade Data Integration - CIS Trade Management System

## Executive Summary

This document describes the ETL architecture for integrating **GMP downstream trade data** with **CIS application trades** into a unified Kudu table for display in the Trade List view.

### Key Points:
- **CIS Trades**: Created in UI, full lifecycle (Create → Validate → Settle), **editable**
- **GMP Trades**: Daily ETL from Hive, read-only reference, **view only**
- **Unified View**: Single `cis_trade` Kudu table shows both sources with `src_system` indicator
- **No Merging**: Records are independent - same trade can exist in both systems

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TRADE LIST VIEW                             │
├─────────────────────────────────────────────────────────────────────┤
│  Deal#     │ Portfolio │ Security │ Qty   │ src_system │ Actions   │
├────────────┼───────────┼──────────┼───────┼────────────┼───────────┤
│  CIS-001   │ UOB-SG    │ AAPL     │ 100   │ CIS        │ Edit|View │
│  GMP-001   │ UOB-SG    │ AAPL     │ 100   │ GMP        │ View      │
│  CIS-002   │ UOB-HK    │ MSFT     │ 50    │ CIS        │ Edit|View │
│  GMP-002   │ UOB-HK    │ GOOG     │ 200   │ GMP        │ View      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Architecture Overview

### 1.1 Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES                               │
├─────────────────────────────────┬───────────────────────────────────┤
│     GMP Downstream (Hive)       │     CIS Application (Django)      │
│     - Daily batch via ETL       │     - Real-time via UI            │
│     - 10-15 STRING columns      │     - 60+ typed columns           │
│     - Read-only in CIS          │     - Full CRUD lifecycle         │
│     - Partitioned by bus_date   │     - Maker-Checker workflow      │
└─────────────────────────────────┴───────────────────────────────────┘
           │                                    │
           │  ETL (Control-M)                   │  Direct Kudu Write
           │  Daily 6:00 AM                     │  Real-time
           ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     UNIFIED KUDU TABLE                              │
│                     gmp_cis.cis_trade                               │
│                                                                     │
│   - src_system = 'GMP' → View Only (no edit button)                │
│   - src_system = 'CIS' → Full Edit (CRUD + workflow)               │
│   - Trade List shows both, sorted by src_system (CIS first)        │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Source Table: GMP Hive

```sql
-- GMP source table (Hive, partitioned by business_date)
-- All columns are STRING type (raw data from upstream)

CREATE EXTERNAL TABLE gmp_cis_staging.gmp_trade_daily (
    trade_ref           STRING,     -- Unique trade reference
    portfolio_code      STRING,     -- Portfolio identifier
    security_code       STRING,     -- Security identifier
    trade_type          STRING,     -- BUY/SELL
    trade_date          STRING,     -- YYYY-MM-DD
    settle_date         STRING,     -- YYYY-MM-DD
    quantity            STRING,     -- Trade quantity
    price               STRING,     -- Execution price
    amount              STRING,     -- Total amount
    currency            STRING,     -- Trade currency
    counterparty        STRING,     -- Counterparty name
    broker              STRING,     -- Broker name
    status              STRING,     -- GMP status
    created_timestamp   STRING,     -- GMP creation time
    file_name           STRING      -- Source file name
)
PARTITIONED BY (business_date STRING)
STORED AS PARQUET
LOCATION '/data/gmp/trades/';
```

---

## 2. ETL Design

### 2.1 Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Idempotent** | Re-running for same date produces same result |
| **Incremental** | Process only new/changed records for business_date |
| **Atomic** | All-or-nothing writes per batch |
| **Auditable** | Full logging with before/after counts |
| **Recoverable** | Failed runs can be restarted safely |
| **Observable** | Metrics, alerts, reconciliation |

### 2.2 ETL Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DAILY ETL PIPELINE                               │
│                    Control-M: CIS_ETL_GMP_TRADE                     │
└─────────────────────────────────────────────────────────────────────┘

STEP 1: VALIDATE
┌────────────────────┐
│ • Check Hive partition exists for business_date
│ • Validate record count > 0
│ • Check for required columns
│ • Fail fast if validation fails
└────────────────────┘
         │
         ▼
STEP 2: EXTRACT
┌────────────────────┐
│ • Read from Hive partition
│ • Apply data type conversions (STRING → proper types)
│ • Handle NULL/empty values
│ • Add metadata columns (src_system, etl_timestamp)
└────────────────────┘
         │
         ▼
STEP 3: TRANSFORM
┌────────────────────┐
│ • Map GMP columns to CIS schema
│ • Generate trade_id (if new record)
│ • Set default values for CIS-only columns
│ • Apply business rules (status mapping)
└────────────────────┘
         │
         ▼
STEP 4: LOAD (UPSERT)
┌────────────────────┐
│ • Delete existing GMP records for business_date (idempotent)
│ • Insert transformed records
│ • Use Kudu UPSERT for atomic write
└────────────────────┘
         │
         ▼
STEP 5: RECONCILE
┌────────────────────┐
│ • Compare source count vs target count
│ • Log statistics
│ • Alert if variance > threshold
└────────────────────┘
```

---

## 3. PySpark ETL Implementation

### 3.1 Project Structure

```
cis_trade_hive/
├── etl/
│   ├── __init__.py
│   ├── gmp_trade_etl.py           # Main ETL class
│   ├── config.py                   # Configuration
│   ├── transformers/
│   │   ├── __init__.py
│   │   └── gmp_to_cis_transformer.py
│   ├── validators/
│   │   ├── __init__.py
│   │   └── source_validator.py
│   ├── writers/
│   │   ├── __init__.py
│   │   └── kudu_writer.py
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       └── metrics.py
└── controlm/
    └── CIS_ETL_GMP_TRADE.json
```

### 3.2 Configuration (`config.py`)

```python
"""
ETL Configuration
-----------------
Centralized configuration for GMP Trade ETL.
"""

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class ETLConfig:
    """ETL configuration settings."""

    # Spark
    app_name: str = "GMP_Trade_ETL"

    # Source (Hive)
    source_database: str = "gmp_cis_staging"
    source_table: str = "gmp_trade_daily"

    # Target (Kudu)
    target_database: str = "gmp_cis"
    target_table: str = "cis_trade"
    kudu_masters: str = "kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251"

    # Processing
    batch_size: int = 10000
    max_retries: int = 3
    retry_delay_seconds: int = 30

    # Reconciliation
    count_variance_threshold_pct: float = 0.01  # 0.01% tolerance

    # Logging
    log_level: str = "INFO"
    log_path: str = "/var/log/cis_etl/gmp_trade"


# Column mapping: GMP column -> CIS column
COLUMN_MAPPING: Dict[str, str] = {
    'trade_ref': 'deal_number',
    'portfolio_code': 'portfolio_short_name',
    'security_code': 'security_label',
    'trade_type': 'trade_type',
    'trade_date': 'trade_date',
    'settle_date': 'settle_date',
    'quantity': 'quantity',
    'price': 'price',
    'amount': 'total_amount',
    'currency': 'currency',
    'counterparty': 'counterparty',
    'broker': 'broker_name',
    'status': 'trade_status',
    'created_timestamp': 'gmp_timestamp',
}

# GMP status to CIS status mapping
STATUS_MAPPING: Dict[str, str] = {
    'NEW': 'SETTLED',           # GMP NEW = already executed, SETTLED in CIS
    'CONFIRMED': 'SETTLED',
    'SETTLED': 'SETTLED',
    'CANCELLED': 'CANCELLED',
    'PENDING': 'VALIDATED',     # Rare - GMP pending = CIS validated
}

# Default values for CIS-only columns (not in GMP)
CIS_DEFAULTS: Dict[str, any] = {
    'status': 'SETTLED',        # GMP trades are pre-settled
    'is_active': True,
    'is_deleted': False,
    'src_system': 'GMP',
    'created_by': 'ETL_GMP',
    'updated_by': 'ETL_GMP',
}
```

### 3.3 Main ETL Class (`gmp_trade_etl.py`)

```python
"""
GMP Trade ETL
-------------
Extract trades from GMP Hive table and load into CIS Kudu table.

Design Pattern: Pipeline with Strategy for each step
Error Handling: Fail-fast with detailed logging
Idempotency: Delete-then-insert for business_date partition

Usage:
    spark-submit gmp_trade_etl.py --business-date 2026-01-19
"""

import sys
import argparse
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, lit, when, trim, upper,
    to_date, to_timestamp, current_timestamp,
    coalesce, regexp_replace
)
from pyspark.sql.types import (
    DecimalType, BooleanType, LongType
)

from config import ETLConfig, COLUMN_MAPPING, STATUS_MAPPING, CIS_DEFAULTS


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging(config: ETLConfig, business_date: str) -> logging.Logger:
    """Configure structured logging."""
    logger = logging.getLogger("GMP_Trade_ETL")
    logger.setLevel(getattr(logging, config.log_level))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # File handler
    log_file = f"{config.log_path}/gmp_trade_etl_{business_date}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)

    # Format
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# =============================================================================
# ETL RESULT
# =============================================================================

@dataclass
class ETLResult:
    """Result of ETL execution."""
    success: bool
    business_date: str
    source_count: int
    target_count: int
    inserted_count: int
    deleted_count: int
    start_time: datetime
    end_time: datetime
    error_message: Optional[str] = None

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'business_date': self.business_date,
            'source_count': self.source_count,
            'target_count': self.target_count,
            'inserted_count': self.inserted_count,
            'deleted_count': self.deleted_count,
            'duration_seconds': self.duration_seconds,
            'error_message': self.error_message,
        }


# =============================================================================
# VALIDATORS
# =============================================================================

class SourceValidator:
    """Validate source data before processing."""

    def __init__(self, spark: SparkSession, config: ETLConfig, logger: logging.Logger):
        self.spark = spark
        self.config = config
        self.logger = logger

    def validate_partition_exists(self, business_date: str) -> bool:
        """Check if Hive partition exists for business_date."""
        self.logger.info(f"Validating partition exists for business_date={business_date}")

        query = f"""
            SELECT COUNT(*) as cnt
            FROM {self.config.source_database}.{self.config.source_table}
            WHERE business_date = '{business_date}'
        """

        try:
            result = self.spark.sql(query).collect()[0]['cnt']
            exists = result > 0

            if exists:
                self.logger.info(f"✓ Partition exists with {result} records")
            else:
                self.logger.error(f"✗ No data found for business_date={business_date}")

            return exists

        except Exception as e:
            self.logger.error(f"✗ Failed to check partition: {str(e)}")
            return False

    def validate_required_columns(self, df: DataFrame) -> Tuple[bool, list]:
        """Validate all required columns are present."""
        required_columns = list(COLUMN_MAPPING.keys())
        missing = [c for c in required_columns if c not in df.columns]

        if missing:
            self.logger.error(f"✗ Missing required columns: {missing}")
            return False, missing

        self.logger.info(f"✓ All {len(required_columns)} required columns present")
        return True, []

    def validate_data_quality(self, df: DataFrame) -> Tuple[bool, Dict[str, int]]:
        """Check data quality - nulls in critical fields."""
        quality_report = {}

        critical_fields = ['trade_ref', 'portfolio_code', 'security_code', 'trade_date']

        for field in critical_fields:
            null_count = df.filter(col(field).isNull() | (trim(col(field)) == '')).count()
            quality_report[field] = null_count

            if null_count > 0:
                self.logger.warning(f"⚠ {field} has {null_count} null/empty values")

        total_nulls = sum(quality_report.values())
        is_valid = total_nulls == 0

        if is_valid:
            self.logger.info("✓ Data quality check passed - no nulls in critical fields")
        else:
            self.logger.warning(f"⚠ Data quality issues found: {quality_report}")

        return is_valid, quality_report


# =============================================================================
# TRANSFORMER
# =============================================================================

class GMPToCISTransformer:
    """Transform GMP data to CIS schema."""

    def __init__(self, config: ETLConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def transform(self, df: DataFrame, business_date: str) -> DataFrame:
        """
        Transform GMP DataFrame to CIS schema.

        Steps:
        1. Rename columns (GMP -> CIS names)
        2. Convert data types (STRING -> proper types)
        3. Map status values
        4. Add CIS-only columns with defaults
        5. Generate trade_id
        """
        self.logger.info("Starting transformation...")

        # Step 1: Rename columns
        self.logger.debug("Step 1: Renaming columns")
        for gmp_col, cis_col in COLUMN_MAPPING.items():
            if gmp_col in df.columns:
                df = df.withColumnRenamed(gmp_col, cis_col)

        # Step 2: Convert data types (STRING -> proper types)
        self.logger.debug("Step 2: Converting data types")
        df = self._convert_data_types(df)

        # Step 3: Map status values
        self.logger.debug("Step 3: Mapping status values")
        df = self._map_status(df)

        # Step 4: Add CIS-only columns with defaults
        self.logger.debug("Step 4: Adding CIS default columns")
        df = self._add_cis_defaults(df, business_date)

        # Step 5: Generate trade_id
        self.logger.debug("Step 5: Generating trade_id")
        df = self._generate_trade_id(df)

        self.logger.info(f"✓ Transformation complete - {df.count()} records")
        return df

    def _convert_data_types(self, df: DataFrame) -> DataFrame:
        """Convert STRING columns to proper data types."""

        # Numeric conversions with NULL handling
        df = df.withColumn(
            'quantity',
            when(col('quantity').isNotNull() & (trim(col('quantity')) != ''),
                 regexp_replace(col('quantity'), ',', '').cast(DecimalType(20, 6)))
            .otherwise(lit(0).cast(DecimalType(20, 6)))
        )

        df = df.withColumn(
            'price',
            when(col('price').isNotNull() & (trim(col('price')) != ''),
                 regexp_replace(col('price'), ',', '').cast(DecimalType(20, 6)))
            .otherwise(lit(0).cast(DecimalType(20, 6)))
        )

        df = df.withColumn(
            'total_amount',
            when(col('total_amount').isNotNull() & (trim(col('total_amount')) != ''),
                 regexp_replace(col('total_amount'), ',', '').cast(DecimalType(20, 6)))
            .otherwise(lit(0).cast(DecimalType(20, 6)))
        )

        # Date conversions
        df = df.withColumn(
            'trade_date',
            when(col('trade_date').isNotNull(),
                 col('trade_date'))  # Keep as STRING for Kudu compatibility
            .otherwise(lit(None))
        )

        df = df.withColumn(
            'settle_date',
            when(col('settle_date').isNotNull(),
                 col('settle_date'))
            .otherwise(lit(None))
        )

        # Uppercase normalization
        df = df.withColumn('trade_type', upper(trim(col('trade_type'))))
        df = df.withColumn('currency', upper(trim(col('currency'))))

        return df

    def _map_status(self, df: DataFrame) -> DataFrame:
        """Map GMP status to CIS workflow status."""

        # Build CASE WHEN expression for status mapping
        status_expr = col('trade_status')
        for gmp_status, cis_status in STATUS_MAPPING.items():
            status_expr = when(
                upper(trim(col('trade_status'))) == gmp_status,
                lit(cis_status)
            ).otherwise(status_expr)

        # Default to SETTLED if no mapping found
        df = df.withColumn(
            'status',
            coalesce(
                when(upper(trim(col('trade_status'))).isin(list(STATUS_MAPPING.keys())),
                     status_expr)
                .otherwise(lit('SETTLED')),
                lit('SETTLED')
            )
        )

        return df

    def _add_cis_defaults(self, df: DataFrame, business_date: str) -> DataFrame:
        """Add CIS-only columns with default values."""

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Source system indicator
        df = df.withColumn('src_system', lit('GMP'))

        # Workflow columns
        df = df.withColumn('is_active', lit(True))
        df = df.withColumn('is_deleted', lit(False))

        # Audit columns
        df = df.withColumn('created_by', lit('ETL_GMP'))
        df = df.withColumn('created_at', lit(timestamp))
        df = df.withColumn('updated_by', lit('ETL_GMP'))
        df = df.withColumn('updated_at', lit(timestamp))

        # Processing metadata
        df = df.withColumn('processing_date', lit(business_date))
        df = df.withColumn('etl_timestamp', current_timestamp())

        # Set all CIS-workflow columns to NULL (GMP trades are view-only)
        cis_workflow_columns = [
            'submitted_by', 'submitted_at',
            'validated_by', 'validated_at', 'validation_comments',
            'settled_by', 'settled_at', 'settlement_comments',
            'cancelled_by', 'cancelled_at', 'cancel_reason'
        ]

        for col_name in cis_workflow_columns:
            df = df.withColumn(col_name, lit(None).cast('string'))

        return df

    def _generate_trade_id(self, df: DataFrame) -> DataFrame:
        """Generate unique trade_id for each record."""
        from pyspark.sql.functions import monotonically_increasing_id, unix_timestamp

        # Generate ID: timestamp_millis + monotonic_id
        # This ensures uniqueness across runs
        df = df.withColumn(
            'trade_id',
            (unix_timestamp() * 1000000 + monotonically_increasing_id()).cast(LongType())
        )

        return df


# =============================================================================
# KUDU WRITER
# =============================================================================

class KuduWriter:
    """Write data to Kudu table."""

    def __init__(self, spark: SparkSession, config: ETLConfig, logger: logging.Logger):
        self.spark = spark
        self.config = config
        self.logger = logger

    def delete_existing_gmp_records(self, business_date: str) -> int:
        """
        Delete existing GMP records for business_date (idempotency).

        Returns number of deleted records.
        """
        self.logger.info(f"Deleting existing GMP records for business_date={business_date}")

        # Count existing records first
        count_query = f"""
            SELECT COUNT(*) as cnt
            FROM {self.config.target_database}.{self.config.target_table}
            WHERE src_system = 'GMP'
              AND processing_date = '{business_date}'
        """

        try:
            existing_count = self.spark.sql(count_query).collect()[0]['cnt']

            if existing_count > 0:
                # Delete via Impala (Kudu doesn't support Spark DELETE)
                delete_query = f"""
                    DELETE FROM {self.config.target_database}.{self.config.target_table}
                    WHERE src_system = 'GMP'
                      AND processing_date = '{business_date}'
                """
                self.spark.sql(delete_query)
                self.logger.info(f"✓ Deleted {existing_count} existing GMP records")
            else:
                self.logger.info("✓ No existing GMP records to delete")

            return existing_count

        except Exception as e:
            self.logger.error(f"✗ Failed to delete existing records: {str(e)}")
            raise

    def write_to_kudu(self, df: DataFrame) -> int:
        """
        Write DataFrame to Kudu table using UPSERT.

        Returns number of inserted records.
        """
        self.logger.info("Writing to Kudu...")

        record_count = df.count()

        try:
            df.write \
                .format("org.apache.kudu.spark.kudu") \
                .option("kudu.master", self.config.kudu_masters) \
                .option("kudu.table", f"impala::{self.config.target_database}.{self.config.target_table}") \
                .option("kudu.operation", "upsert") \
                .mode("append") \
                .save()

            self.logger.info(f"✓ Inserted {record_count} records to Kudu")
            return record_count

        except Exception as e:
            self.logger.error(f"✗ Failed to write to Kudu: {str(e)}")
            raise


# =============================================================================
# RECONCILIATION
# =============================================================================

class Reconciler:
    """Reconcile source vs target counts."""

    def __init__(self, spark: SparkSession, config: ETLConfig, logger: logging.Logger):
        self.spark = spark
        self.config = config
        self.logger = logger

    def reconcile(self, source_count: int, business_date: str) -> Tuple[bool, int]:
        """
        Compare source count with target count.

        Returns (is_reconciled, target_count)
        """
        self.logger.info("Running reconciliation...")

        target_query = f"""
            SELECT COUNT(*) as cnt
            FROM {self.config.target_database}.{self.config.target_table}
            WHERE src_system = 'GMP'
              AND processing_date = '{business_date}'
        """

        target_count = self.spark.sql(target_query).collect()[0]['cnt']

        variance = abs(source_count - target_count)
        variance_pct = (variance / source_count * 100) if source_count > 0 else 0

        is_reconciled = variance_pct <= self.config.count_variance_threshold_pct

        if is_reconciled:
            self.logger.info(f"✓ Reconciliation PASSED")
            self.logger.info(f"  Source: {source_count}, Target: {target_count}, Variance: {variance} ({variance_pct:.4f}%)")
        else:
            self.logger.error(f"✗ Reconciliation FAILED")
            self.logger.error(f"  Source: {source_count}, Target: {target_count}, Variance: {variance} ({variance_pct:.4f}%)")
            self.logger.error(f"  Threshold: {self.config.count_variance_threshold_pct}%")

        return is_reconciled, target_count


# =============================================================================
# MAIN ETL CLASS
# =============================================================================

class GMPTradeETL:
    """
    Main ETL orchestrator for GMP Trade data.

    Follows Pipeline pattern with clear separation of concerns:
    - Validator: Checks source data
    - Transformer: Converts GMP to CIS schema
    - Writer: Loads to Kudu
    - Reconciler: Verifies results
    """

    def __init__(self, config: ETLConfig = None):
        self.config = config or ETLConfig()
        self.spark = None
        self.logger = None

    def _init_spark(self, business_date: str) -> None:
        """Initialize Spark session."""
        self.spark = SparkSession.builder \
            .appName(f"{self.config.app_name}_{business_date}") \
            .config("spark.sql.extensions", "org.apache.kudu.spark.kudu.KuduSparkExtension") \
            .enableHiveSupport() \
            .getOrCreate()

        self.spark.sparkContext.setLogLevel("WARN")

    def run(self, business_date: str) -> ETLResult:
        """
        Execute ETL pipeline.

        Args:
            business_date: Processing date in YYYY-MM-DD format

        Returns:
            ETLResult with execution details
        """
        start_time = datetime.now()
        source_count = 0
        target_count = 0
        inserted_count = 0
        deleted_count = 0

        try:
            # Initialize
            self._init_spark(business_date)
            self.logger = setup_logging(self.config, business_date.replace('-', ''))

            self.logger.info("=" * 70)
            self.logger.info(f"GMP TRADE ETL - Business Date: {business_date}")
            self.logger.info("=" * 70)

            # Create components
            validator = SourceValidator(self.spark, self.config, self.logger)
            transformer = GMPToCISTransformer(self.config, self.logger)
            writer = KuduWriter(self.spark, self.config, self.logger)
            reconciler = Reconciler(self.spark, self.config, self.logger)

            # STEP 1: Validate partition exists
            self.logger.info("-" * 70)
            self.logger.info("STEP 1: VALIDATE SOURCE")
            self.logger.info("-" * 70)

            if not validator.validate_partition_exists(business_date):
                raise ValueError(f"No data found for business_date={business_date}")

            # STEP 2: Extract from Hive
            self.logger.info("-" * 70)
            self.logger.info("STEP 2: EXTRACT FROM HIVE")
            self.logger.info("-" * 70)

            source_df = self.spark.sql(f"""
                SELECT *
                FROM {self.config.source_database}.{self.config.source_table}
                WHERE business_date = '{business_date}'
            """)

            source_count = source_df.count()
            self.logger.info(f"Extracted {source_count} records from Hive")

            # Validate columns and quality
            is_valid, missing = validator.validate_required_columns(source_df)
            if not is_valid:
                raise ValueError(f"Missing required columns: {missing}")

            is_quality_ok, quality_report = validator.validate_data_quality(source_df)
            if not is_quality_ok:
                self.logger.warning(f"Data quality issues: {quality_report}")
                # Continue with warning - don't fail

            # STEP 3: Transform
            self.logger.info("-" * 70)
            self.logger.info("STEP 3: TRANSFORM")
            self.logger.info("-" * 70)

            transformed_df = transformer.transform(source_df, business_date)

            # STEP 4: Load to Kudu
            self.logger.info("-" * 70)
            self.logger.info("STEP 4: LOAD TO KUDU")
            self.logger.info("-" * 70)

            # Delete existing (idempotency)
            deleted_count = writer.delete_existing_gmp_records(business_date)

            # Insert new records
            inserted_count = writer.write_to_kudu(transformed_df)

            # STEP 5: Reconcile
            self.logger.info("-" * 70)
            self.logger.info("STEP 5: RECONCILE")
            self.logger.info("-" * 70)

            is_reconciled, target_count = reconciler.reconcile(source_count, business_date)

            if not is_reconciled:
                raise ValueError("Reconciliation failed - count mismatch")

            # SUCCESS
            end_time = datetime.now()

            self.logger.info("=" * 70)
            self.logger.info("ETL COMPLETED SUCCESSFULLY")
            self.logger.info(f"  Business Date: {business_date}")
            self.logger.info(f"  Source Count:  {source_count}")
            self.logger.info(f"  Target Count:  {target_count}")
            self.logger.info(f"  Duration:      {(end_time - start_time).total_seconds():.2f} seconds")
            self.logger.info("=" * 70)

            return ETLResult(
                success=True,
                business_date=business_date,
                source_count=source_count,
                target_count=target_count,
                inserted_count=inserted_count,
                deleted_count=deleted_count,
                start_time=start_time,
                end_time=end_time
            )

        except Exception as e:
            end_time = datetime.now()
            error_msg = str(e)

            if self.logger:
                self.logger.error("=" * 70)
                self.logger.error("ETL FAILED")
                self.logger.error(f"  Error: {error_msg}")
                self.logger.error("=" * 70)
            else:
                print(f"ETL FAILED: {error_msg}")

            return ETLResult(
                success=False,
                business_date=business_date,
                source_count=source_count,
                target_count=target_count,
                inserted_count=inserted_count,
                deleted_count=deleted_count,
                start_time=start_time,
                end_time=end_time,
                error_message=error_msg
            )

        finally:
            if self.spark:
                self.spark.stop()


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='GMP Trade ETL')
    parser.add_argument(
        '--business-date', '-d',
        required=True,
        help='Business date in YYYY-MM-DD format'
    )
    parser.add_argument(
        '--config-file', '-c',
        required=False,
        help='Path to configuration file (optional)'
    )

    args = parser.parse_args()

    # Validate date format
    try:
        datetime.strptime(args.business_date, '%Y-%m-%d')
    except ValueError:
        print(f"ERROR: Invalid date format. Use YYYY-MM-DD")
        sys.exit(1)

    # Run ETL
    etl = GMPTradeETL()
    result = etl.run(args.business_date)

    # Exit code
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
```

---

## 4. Control-M Job Definition

### 4.1 Job Configuration

**File**: `controlm/CIS_ETL_GMP_TRADE.json`

```json
{
  "jobDefinition": {
    "jobName": "CIS_ETL_GMP_TRADE",
    "application": "CIS_ETL",
    "subApplication": "TRADE",
    "description": "Load GMP trade data into CIS Kudu table",

    "schedule": {
      "runCalendar": "BUSINESS_DAYS",
      "time": "06:00",
      "timezone": "Asia/Singapore"
    },

    "execution": {
      "runAs": "cis_etl_svc",
      "host": "spark-edge-node",
      "command": "spark-submit --master yarn --deploy-mode cluster --packages org.apache.kudu:kudu-spark3_2.12:1.17.0 --conf spark.dynamicAllocation.enabled=true --conf spark.executor.memory=4g --conf spark.driver.memory=2g /opt/cis/etl/gmp_trade_etl.py --business-date %%ODATE"
    },

    "conditions": {
      "inConditions": [
        "GMP_TRADE_FILE_ARRIVED"
      ],
      "outConditions": {
        "onSuccess": "CIS_GMP_TRADE_LOAD_SUCCESS",
        "onFailure": "CIS_GMP_TRADE_LOAD_FAILED"
      }
    },

    "alerts": {
      "onFailure": {
        "type": "EMAIL",
        "recipients": ["cis-support@company.com", "etl-oncall@company.com"],
        "subject": "ALERT: CIS GMP Trade ETL Failed - %%ODATE"
      },
      "onLateStart": {
        "threshold": "30",
        "unit": "MINUTES",
        "type": "EMAIL",
        "recipients": ["cis-support@company.com"]
      }
    },

    "retry": {
      "maxRetries": 2,
      "retryInterval": 300
    },

    "timeout": 3600
  }
}
```

### 4.2 Dependency Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CONTROL-M JOB FLOW                               │
└─────────────────────────────────────────────────────────────────────┘

05:30 AM  ┌──────────────────────────────────────┐
          │  GMP_FILE_WATCHER                    │
          │  Watch for: /data/gmp/trades/*.csv   │
          │  On Arrival → Set GMP_TRADE_FILE_ARRIVED
          └──────────────────────────────────────┘
                         │
                         ▼ (condition met)
06:00 AM  ┌──────────────────────────────────────┐
          │  CIS_ETL_GMP_TRADE                   │
          │  spark-submit gmp_trade_etl.py       │
          │  --business-date %%ODATE             │
          │                                      │
          │  On Success → CIS_GMP_TRADE_LOAD_SUCCESS
          │  On Failure → CIS_GMP_TRADE_LOAD_FAILED
          └──────────────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
    (Success)                     (Failure)
┌─────────────────┐         ┌─────────────────┐
│ CIS_ETL_RECON   │         │ ALERT_ONCALL    │
│ Run reconcile   │         │ Page support    │
└─────────────────┘         └─────────────────┘
```

---

## 5. UI Integration

### 5.1 Trade List View Changes

The Trade List view already supports filtering by `src_system`. Key behaviors:

| src_system | Edit Button | View Button | Status Editable |
|------------|-------------|-------------|-----------------|
| CIS | ✓ Enabled | ✓ Enabled | ✓ Yes |
| GMP | ✗ Hidden | ✓ Enabled | ✗ No (View only) |

### 5.2 Query for Trade List

```python
# In trade_kudu_repository.py - get_all_trades_multi_filter()

query = f"""
SELECT *
FROM {self.DATABASE}.{self.TABLE_NAME}
WHERE {where_clause}
ORDER BY
    CASE WHEN UPPER(src_system) = 'CIS' THEN 0 ELSE 1 END,  -- CIS first
    created_at DESC
LIMIT {limit}
"""
```

### 5.3 Template Check for Edit Button

```html
<!-- In trade_list.html -->
{% for trade in trades %}
<tr>
    <td>{{ trade.deal_number }}</td>
    <td>{{ trade.portfolio_short_name }}</td>
    <td>{{ trade.security_label }}</td>
    <td>{{ trade.quantity }}</td>
    <td>
        <span class="badge bg-{{ trade.src_system|lower == 'cis' and 'primary' or 'secondary' }}">
            {{ trade.src_system }}
        </span>
    </td>
    <td>
        <a href="{% url 'trade:detail' trade.trade_id %}" class="btn btn-sm btn-outline-info">
            <i class="bi bi-eye"></i> View
        </a>
        {% if trade.src_system == 'CIS' %}
        <a href="{% url 'trade:edit' trade.trade_id %}" class="btn btn-sm btn-outline-primary">
            <i class="bi bi-pencil"></i> Edit
        </a>
        {% endif %}
    </td>
</tr>
{% endfor %}
```

---

## 6. Error Handling & Edge Cases

### 6.1 Edge Cases Handled

| Edge Case | Handling |
|-----------|----------|
| Empty source partition | Fail fast with clear error message |
| Missing required columns | Fail with list of missing columns |
| NULL/empty critical fields | Log warning, continue processing |
| Duplicate trade_ref in source | Allow (GMP may have duplicates) |
| Re-run same business_date | Delete existing + re-insert (idempotent) |
| Kudu write failure | Rollback (no partial writes) |
| Network timeout | Retry up to 3 times |
| Invalid date format | Fail with validation error |

### 6.2 Logging Levels

```
DEBUG  - Detailed transformation steps
INFO   - High-level progress (step completion, counts)
WARNING - Data quality issues (non-fatal)
ERROR  - Failures requiring attention
```

### 6.3 Sample Log Output

```
2026-01-19 06:00:01 | INFO     | GMP_Trade_ETL | ======================================================================
2026-01-19 06:00:01 | INFO     | GMP_Trade_ETL | GMP TRADE ETL - Business Date: 2026-01-19
2026-01-19 06:00:01 | INFO     | GMP_Trade_ETL | ======================================================================
2026-01-19 06:00:01 | INFO     | GMP_Trade_ETL | ----------------------------------------------------------------------
2026-01-19 06:00:01 | INFO     | GMP_Trade_ETL | STEP 1: VALIDATE SOURCE
2026-01-19 06:00:01 | INFO     | GMP_Trade_ETL | ----------------------------------------------------------------------
2026-01-19 06:00:02 | INFO     | GMP_Trade_ETL | Validating partition exists for business_date=2026-01-19
2026-01-19 06:00:03 | INFO     | GMP_Trade_ETL | ✓ Partition exists with 1,523 records
2026-01-19 06:00:03 | INFO     | GMP_Trade_ETL | ----------------------------------------------------------------------
2026-01-19 06:00:03 | INFO     | GMP_Trade_ETL | STEP 2: EXTRACT FROM HIVE
2026-01-19 06:00:03 | INFO     | GMP_Trade_ETL | ----------------------------------------------------------------------
2026-01-19 06:00:05 | INFO     | GMP_Trade_ETL | Extracted 1,523 records from Hive
2026-01-19 06:00:05 | INFO     | GMP_Trade_ETL | ✓ All 14 required columns present
2026-01-19 06:00:06 | INFO     | GMP_Trade_ETL | ✓ Data quality check passed - no nulls in critical fields
2026-01-19 06:00:06 | INFO     | GMP_Trade_ETL | ----------------------------------------------------------------------
2026-01-19 06:00:06 | INFO     | GMP_Trade_ETL | STEP 3: TRANSFORM
2026-01-19 06:00:06 | INFO     | GMP_Trade_ETL | ----------------------------------------------------------------------
2026-01-19 06:00:06 | INFO     | GMP_Trade_ETL | Starting transformation...
2026-01-19 06:00:08 | INFO     | GMP_Trade_ETL | ✓ Transformation complete - 1,523 records
2026-01-19 06:00:08 | INFO     | GMP_Trade_ETL | ----------------------------------------------------------------------
2026-01-19 06:00:08 | INFO     | GMP_Trade_ETL | STEP 4: LOAD TO KUDU
2026-01-19 06:00:08 | INFO     | GMP_Trade_ETL | ----------------------------------------------------------------------
2026-01-19 06:00:08 | INFO     | GMP_Trade_ETL | Deleting existing GMP records for business_date=2026-01-19
2026-01-19 06:00:09 | INFO     | GMP_Trade_ETL | ✓ Deleted 1,520 existing GMP records
2026-01-19 06:00:09 | INFO     | GMP_Trade_ETL | Writing to Kudu...
2026-01-19 06:00:15 | INFO     | GMP_Trade_ETL | ✓ Inserted 1,523 records to Kudu
2026-01-19 06:00:15 | INFO     | GMP_Trade_ETL | ----------------------------------------------------------------------
2026-01-19 06:00:15 | INFO     | GMP_Trade_ETL | STEP 5: RECONCILE
2026-01-19 06:00:15 | INFO     | GMP_Trade_ETL | ----------------------------------------------------------------------
2026-01-19 06:00:15 | INFO     | GMP_Trade_ETL | Running reconciliation...
2026-01-19 06:00:16 | INFO     | GMP_Trade_ETL | ✓ Reconciliation PASSED
2026-01-19 06:00:16 | INFO     | GMP_Trade_ETL |   Source: 1,523, Target: 1,523, Variance: 0 (0.0000%)
2026-01-19 06:00:16 | INFO     | GMP_Trade_ETL | ======================================================================
2026-01-19 06:00:16 | INFO     | GMP_Trade_ETL | ETL COMPLETED SUCCESSFULLY
2026-01-19 06:00:16 | INFO     | GMP_Trade_ETL |   Business Date: 2026-01-19
2026-01-19 06:00:16 | INFO     | GMP_Trade_ETL |   Source Count:  1,523
2026-01-19 06:00:16 | INFO     | GMP_Trade_ETL |   Target Count:  1,523
2026-01-19 06:00:16 | INFO     | GMP_Trade_ETL |   Duration:      15.42 seconds
2026-01-19 06:00:16 | INFO     | GMP_Trade_ETL | ======================================================================
```

---

## 7. Quick Reference

### 7.1 Key Points

| Item | Value |
|------|-------|
| Source | `gmp_cis_staging.gmp_trade_daily` (Hive, partitioned by business_date) |
| Target | `gmp_cis.cis_trade` (Kudu) |
| Schedule | Daily 6:00 AM SGT |
| Idempotency | Delete-then-insert for business_date |
| CIS Trades | Full CRUD, src_system='CIS' |
| GMP Trades | View only, src_system='GMP' |

### 7.2 Commands

```bash
# Manual run
spark-submit \
    --master yarn \
    --deploy-mode cluster \
    --packages org.apache.kudu:kudu-spark3_2.12:1.17.0 \
    gmp_trade_etl.py \
    --business-date 2026-01-19

# Check logs
tail -f /var/log/cis_etl/gmp_trade/gmp_trade_etl_20260119.log

# Verify in Impala
SELECT src_system, COUNT(*)
FROM gmp_cis.cis_trade
WHERE processing_date = '2026-01-19'
GROUP BY src_system;
```

---

**Document Version**: 2.0
**Last Updated**: 2026-01-19
**Author**: CIS Development Team
