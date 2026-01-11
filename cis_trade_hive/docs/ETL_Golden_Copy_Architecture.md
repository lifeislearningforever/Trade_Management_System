# ETL Golden Copy Architecture - CIS Trade Management System

## Executive Summary

This document outlines the data architecture for managing GMP upstream data and CIS internal data with a Golden Copy approach using Medallion Architecture (Bronze → Silver → Gold).

**Key Principles**:
- **Source System Tracking**: Every record tagged with source system (GMP/CIS)
- **Version Management**: SCD Type 2 for historical tracking
- **Golden Record**: Master data with conflict resolution rules
- **Performance First**: Kudu for real-time + Parquet for analytics
- **Minimal Complexity**: Standardized patterns across all entities

---

## 1. Architecture Overview

### 1.1 Data Flow Layers (Medallion Architecture)

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                              │
├──────────────────────────────┬───────────────────────────────────┤
│   GMP Upstream System        │   CIS Application (Django)        │
│   - SFTP/API/Database        │   - Direct Kudu Writes            │
│   - Batch (Daily/Hourly)     │   - Real-time Transactions        │
└──────────────────────────────┴───────────────────────────────────┘
                    ↓                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                    BRONZE LAYER (Raw Ingestion)                  │
│  Hive External Tables → Parquet, Partitioned by processing_date │
│  - gmp_raw_position_YYYYMMDD                                    │
│  - gmp_raw_trade_YYYYMMDD                                       │
│  - gmp_raw_portfolio_YYYYMMDD                                   │
│  - gmp_raw_security_YYYYMMDD                                    │
│  - gmp_raw_counterparty_YYYYMMDD                                │
│  Purpose: Immutable landing zone, audit trail                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   SILVER LAYER (Cleansed & Validated)            │
│  Hive Tables → Parquet, Partitioned by processing_date          │
│  - cleansed_position (dedupe, validation, type conversion)      │
│  - cleansed_trade                                               │
│  - cleansed_portfolio                                           │
│  - cleansed_security                                            │
│  - cleansed_counterparty                                        │
│  Purpose: Clean, validated, conformed data                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    GOLD LAYER (Golden Copy)                      │
│  Kudu Tables (via Impala) - Real-time Access                    │
│  - cis_position_kudu          (current + history tables)        │
│  - cis_trade_kudu                                               │
│  - cis_portfolio_kudu                                           │
│  - cis_security_kudu                                            │
│  - cis_counterparty_kudu                                        │
│  Purpose: Single source of truth, versioned, CIS app reads      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Table Design

### 2.1 Standard Schema Pattern (All Entities)

Every Gold table follows this structure:

```sql
CREATE TABLE gmp_cis.cis_{entity}_kudu (
    -- Business Keys
    {entity}_id BIGINT,                    -- Surrogate key (generated)
    {natural_key} STRING,                  -- Business key (e.g., trade_id, portfolio_name)

    -- Source System Tracking
    src_system STRING,                     -- 'GMP' or 'CIS'
    src_record_id STRING,                  -- Original ID from source system

    -- Data Fields
    {entity_specific_fields}               -- Domain columns

    -- Golden Copy Management
    is_golden_record BOOLEAN,              -- TRUE for active golden record
    golden_record_id BIGINT,               -- Reference to master golden record
    data_quality_score INT,                -- 0-100 (for conflict resolution)
    conflict_resolution_rule STRING,       -- 'GMP_WINS', 'CIS_WINS', 'LATEST', 'MANUAL'

    -- Version Control (SCD Type 2)
    version_number INT,                    -- Incremental version
    effective_from TIMESTAMP,              -- Version start date
    effective_to TIMESTAMP,                -- Version end date (NULL = current)
    is_current BOOLEAN,                    -- TRUE for active version

    -- Audit Fields
    created_at TIMESTAMP,
    created_by STRING,
    updated_at TIMESTAMP,
    updated_by STRING,
    processing_date STRING,                -- ETL batch date (YYYYMMDD)

    -- Soft Delete
    is_active BOOLEAN,
    is_deleted BOOLEAN,
    deleted_at TIMESTAMP,
    deleted_by STRING,

    PRIMARY KEY ({entity}_id, version_number)
)
PARTITION BY HASH ({entity}_id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '3');
```

### 2.2 Entity-Specific Examples

#### A. Portfolio (Already Exists - Needs Enhancement)

```sql
-- Current: cis_portfolio
-- Add these columns:
ALTER TABLE gmp_cis.cis_portfolio ADD COLUMNS (
    src_system STRING,                     -- 'GMP' or 'CIS'
    src_record_id STRING,                  -- Original portfolio code from GMP
    is_golden_record BOOLEAN DEFAULT TRUE,
    golden_record_id BIGINT,
    data_quality_score INT DEFAULT 100,
    version_number INT DEFAULT 1,
    effective_from TIMESTAMP,
    effective_to TIMESTAMP,
    is_current BOOLEAN DEFAULT TRUE
);
```

#### B. Trade (NEW - Critical for Trading Operations)

```sql
CREATE TABLE gmp_cis.cis_trade_kudu (
    -- Business Keys
    trade_id BIGINT,                       -- Surrogate
    trade_ref STRING,                      -- GMP trade reference

    -- Source Tracking
    src_system STRING,                     -- 'GMP' or 'CIS'
    src_record_id STRING,

    -- Trade Details
    portfolio_name STRING,                 -- FK to portfolio
    security_id STRING,                    -- FK to security
    counterparty_short_name STRING,        -- FK to counterparty
    trade_date DATE,
    settlement_date DATE,
    trade_type STRING,                     -- 'BUY', 'SELL', 'REPO', etc.
    quantity DECIMAL(18,4),
    price DECIMAL(18,6),
    gross_amount DECIMAL(18,2),
    net_amount DECIMAL(18,2),
    currency STRING,
    trader_name STRING,
    book STRING,
    status STRING,                         -- 'NEW', 'CONFIRMED', 'SETTLED', 'CANCELLED'

    -- Golden Copy Fields
    is_golden_record BOOLEAN,
    golden_record_id BIGINT,
    data_quality_score INT,

    -- Versioning
    version_number INT,
    effective_from TIMESTAMP,
    effective_to TIMESTAMP,
    is_current BOOLEAN,

    -- Audit
    created_at TIMESTAMP,
    created_by STRING,
    updated_at TIMESTAMP,
    updated_by STRING,
    processing_date STRING,

    -- Soft Delete
    is_active BOOLEAN,
    is_deleted BOOLEAN,

    PRIMARY KEY (trade_id, version_number)
)
PARTITION BY HASH (trade_id) PARTITIONS 16
STORED AS KUDU;
```

#### C. Position (NEW - Aggregated View)

```sql
CREATE TABLE gmp_cis.cis_position_kudu (
    position_id BIGINT,
    position_date DATE,

    -- Position Keys
    portfolio_name STRING,
    security_id STRING,

    -- Source
    src_system STRING,
    src_record_id STRING,

    -- Position Data
    quantity DECIMAL(18,4),
    market_value DECIMAL(18,2),
    book_cost DECIMAL(18,2),
    unrealized_pnl DECIMAL(18,2),
    currency STRING,

    -- Golden Copy
    is_golden_record BOOLEAN,
    golden_record_id BIGINT,
    data_quality_score INT,

    -- Versioning
    version_number INT,
    effective_from TIMESTAMP,
    effective_to TIMESTAMP,
    is_current BOOLEAN,

    -- Audit
    created_at TIMESTAMP,
    created_by STRING,
    updated_at TIMESTAMP,
    updated_by STRING,
    processing_date STRING,

    -- Soft Delete
    is_active BOOLEAN,
    is_deleted BOOLEAN,

    PRIMARY KEY (position_id, position_date, version_number)
)
PARTITION BY HASH (position_id) PARTITIONS 16,
             RANGE (position_date) (
                 PARTITION VALUES < '2024-01-01',
                 PARTITION '2024-01-01' <= VALUES < '2025-01-01',
                 PARTITION '2025-01-01' <= VALUES
             )
STORED AS KUDU;
```

---

## 3. ETL Flow Design

### 3.1 Bronze Layer Ingestion (PySpark)

**Job**: `bronze_ingest_gmp_data.py`
**Frequency**: Daily 6:00 AM (after GMP EOD batch)
**Control-M Job**: `CIS_ETL_BRONZE_INGEST`

```python
# bronze_ingest_gmp_data.py
from pyspark.sql import SparkSession
from pyspark.sql.functions import lit, current_timestamp
from datetime import datetime

class BronzeIngestion:
    """
    Raw data ingestion from GMP source to Bronze layer.
    No transformations - just raw copy with audit metadata.
    """

    def __init__(self, processing_date):
        self.processing_date = processing_date  # YYYYMMDD
        self.spark = SparkSession.builder \
            .appName(f"Bronze_Ingest_{processing_date}") \
            .enableHiveSupport() \
            .getOrCreate()

    def ingest_entity(self, entity_name, source_path, schema):
        """
        Generic ingestion for any entity.

        Args:
            entity_name: 'portfolio', 'trade', 'position', etc.
            source_path: GMP export path (SFTP/HDFS/S3)
            schema: StructType for validation
        """
        # Read from source
        df = self.spark.read \
            .schema(schema) \
            .option("header", "true") \
            .csv(source_path)

        # Add audit metadata
        df_with_metadata = df \
            .withColumn("ingestion_timestamp", current_timestamp()) \
            .withColumn("processing_date", lit(self.processing_date)) \
            .withColumn("src_system", lit("GMP")) \
            .withColumn("file_path", lit(source_path))

        # Write to Bronze (Hive Parquet, partitioned by date)
        output_path = f"hdfs://namenode/cis/bronze/gmp_raw_{entity_name}"

        df_with_metadata.write \
            .mode("overwrite") \
            .partitionBy("processing_date") \
            .parquet(output_path)

        # Register as Hive external table
        self.spark.sql(f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis_bronze.gmp_raw_{entity_name} (
                {self._generate_hive_schema(df_with_metadata)}
            )
            PARTITIONED BY (processing_date STRING)
            STORED AS PARQUET
            LOCATION '{output_path}'
        """)

        # Add partition
        self.spark.sql(f"""
            ALTER TABLE gmp_cis_bronze.gmp_raw_{entity_name}
            ADD IF NOT EXISTS PARTITION (processing_date='{self.processing_date}')
        """)

        print(f"✓ Ingested {df.count()} records for {entity_name}")
        return df.count()

    def run_all(self):
        """Execute full bronze ingestion"""
        entities = {
            'portfolio': '/gmp/export/portfolio_{}.csv',
            'trade': '/gmp/export/trade_{}.csv',
            'position': '/gmp/export/position_{}.csv',
            'security': '/gmp/export/security_{}.csv',
            'counterparty': '/gmp/export/counterparty_{}.csv'
        }

        results = {}
        for entity, path_template in entities.items():
            source_path = path_template.format(self.processing_date)
            schema = self._get_entity_schema(entity)
            count = self.ingest_entity(entity, source_path, schema)
            results[entity] = count

        return results

if __name__ == "__main__":
    import sys
    processing_date = sys.argv[1]  # YYYYMMDD from Control-M

    ingestion = BronzeIngestion(processing_date)
    results = ingestion.run_all()

    print(f"Bronze Ingestion Complete: {results}")
```

### 3.2 Silver Layer Processing (PySpark)

**Job**: `silver_cleanse_and_validate.py`
**Frequency**: Daily 7:00 AM (after Bronze)
**Control-M Job**: `CIS_ETL_SILVER_CLEANSE`

```python
# silver_cleanse_and_validate.py
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *

class SilverProcessing:
    """
    Cleansing, validation, and standardization.
    Prepares data for golden record creation.
    """

    def __init__(self, processing_date):
        self.processing_date = processing_date
        self.spark = SparkSession.builder \
            .appName(f"Silver_Cleanse_{processing_date}") \
            .enableHiveSupport() \
            .getOrCreate()

    def cleanse_portfolio(self):
        """Portfolio-specific cleansing logic"""
        # Read from Bronze
        df = self.spark.table(f"gmp_cis_bronze.gmp_raw_portfolio") \
            .filter(f"processing_date = '{self.processing_date}'")

        # Data Quality Rules
        df_clean = df \
            .filter(col("portfolio_code").isNotNull()) \
            .filter(length(col("portfolio_code")) > 0) \
            .dropDuplicates(["portfolio_code", "processing_date"]) \
            .withColumn("portfolio_name", trim(col("portfolio_name"))) \
            .withColumn("currency", upper(trim(col("currency")))) \
            .withColumn("cash_balance",
                when(col("cash_balance").isNull(), 0.0)
                .otherwise(col("cash_balance").cast("decimal(18,2)"))) \
            .withColumn("is_active",
                when(col("status") == "ACTIVE", True)
                .otherwise(False)) \
            .withColumn("data_quality_score",
                self._calculate_quality_score("portfolio"))

        # Write to Silver
        df_clean.write \
            .mode("overwrite") \
            .partitionBy("processing_date") \
            .parquet("hdfs://namenode/cis/silver/cleansed_portfolio")

        return df_clean.count()

    def _calculate_quality_score(self, entity_type):
        """
        Calculate data quality score (0-100) based on completeness.
        Higher score = better quality data.
        """
        # Example: Portfolio quality score
        score = lit(100)

        # Deduct points for missing critical fields
        score = when(col("portfolio_name").isNull(), score - 20).otherwise(score)
        score = when(col("currency").isNull(), score - 15).otherwise(score)
        score = when(col("manager").isNull(), score - 10).otherwise(score)
        score = when(col("description").isNull(), score - 5).otherwise(score)

        return score

    def cleanse_trade(self):
        """Trade-specific cleansing"""
        df = self.spark.table(f"gmp_cis_bronze.gmp_raw_trade") \
            .filter(f"processing_date = '{self.processing_date}'")

        df_clean = df \
            .filter(col("trade_ref").isNotNull()) \
            .dropDuplicates(["trade_ref", "processing_date"]) \
            .withColumn("trade_date", to_date(col("trade_date"), "yyyy-MM-dd")) \
            .withColumn("settlement_date", to_date(col("settlement_date"), "yyyy-MM-dd")) \
            .withColumn("quantity", col("quantity").cast("decimal(18,4)")) \
            .withColumn("price", col("price").cast("decimal(18,6)")) \
            .withColumn("currency", upper(trim(col("currency")))) \
            .withColumn("trade_type", upper(trim(col("trade_type")))) \
            .withColumn("status",
                when(col("status").isNull(), "NEW")
                .otherwise(upper(trim(col("status"))))) \
            .withColumn("data_quality_score",
                self._calculate_quality_score("trade"))

        # Validate referential integrity (lookup existence)
        df_with_validation = df_clean \
            .join(
                broadcast(self.spark.table("gmp_cis.cis_portfolio_kudu")
                         .select("name").distinct()),
                df_clean.portfolio_code == col("name"),
                "left"
            ) \
            .withColumn("data_quality_score",
                when(col("name").isNull(), col("data_quality_score") - 30)
                .otherwise(col("data_quality_score")))

        df_with_validation.write \
            .mode("overwrite") \
            .partitionBy("processing_date") \
            .parquet("hdfs://namenode/cis/silver/cleansed_trade")

        return df_with_validation.count()
```

### 3.3 Gold Layer Upsert (PySpark → Kudu)

**Job**: `gold_create_golden_records.py`
**Frequency**: Daily 8:00 AM (after Silver)
**Control-M Job**: `CIS_ETL_GOLD_UPSERT`

```python
# gold_create_golden_records.py
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from datetime import datetime

class GoldenRecordManager:
    """
    Creates and maintains golden records with version history.
    Implements conflict resolution between GMP and CIS sources.
    """

    CONFLICT_RULES = {
        'portfolio': 'GMP_WINS',      # GMP is source of truth
        'trade': 'GMP_WINS',          # GMP is authoritative
        'position': 'GMP_WINS',       # GMP calculates positions
        'security': 'LATEST',         # Take most recent update
        'counterparty': 'MANUAL'      # Requires human review
    }

    def __init__(self, processing_date):
        self.processing_date = processing_date
        self.spark = SparkSession.builder \
            .appName(f"Gold_Golden_Records_{processing_date}") \
            .config("spark.sql.extensions", "org.apache.kudu.spark.kudu.KuduSparkExtension") \
            .enableHiveSupport() \
            .getOrCreate()

    def upsert_portfolio(self):
        """
        Create golden records for portfolios.
        Logic: GMP_WINS - GMP data takes precedence over CIS.
        """
        # Read cleansed GMP data
        gmp_data = self.spark.read \
            .parquet("hdfs://namenode/cis/silver/cleansed_portfolio") \
            .filter(f"processing_date = '{self.processing_date}'") \
            .withColumn("src_system", lit("GMP"))

        # Read current CIS data (data created directly in CIS app)
        cis_data = self.spark.table("gmp_cis.cis_portfolio_kudu") \
            .filter("src_system = 'CIS' AND is_current = TRUE")

        # Union both sources
        all_data = gmp_data.unionByName(cis_data, allowMissingColumns=True)

        # Apply conflict resolution
        golden_records = self._resolve_conflicts(
            all_data,
            key_columns=["name"],  # Portfolio name is natural key
            rule=self.CONFLICT_RULES['portfolio']
        )

        # Implement SCD Type 2 versioning
        versioned_records = self._apply_scd_type2(
            golden_records,
            existing_table="gmp_cis.cis_portfolio_kudu",
            key_columns=["name"]
        )

        # Write to Kudu (UPSERT mode)
        self._write_to_kudu(
            versioned_records,
            table="gmp_cis.cis_portfolio_kudu",
            mode="upsert"
        )

        return versioned_records.count()

    def _resolve_conflicts(self, df, key_columns, rule):
        """
        Resolve conflicts when same record exists from multiple sources.

        Rules:
        - GMP_WINS: GMP data takes precedence
        - CIS_WINS: CIS data takes precedence
        - LATEST: Most recent update_timestamp wins
        - MANUAL: Flag for human review (store both)
        """
        from pyspark.sql.window import Window

        if rule == "GMP_WINS":
            # Rank: GMP=1, CIS=2
            window = Window.partitionBy(key_columns).orderBy(
                when(col("src_system") == "GMP", 1).otherwise(2),
                col("data_quality_score").desc()
            )
        elif rule == "CIS_WINS":
            window = Window.partitionBy(key_columns).orderBy(
                when(col("src_system") == "CIS", 1).otherwise(2),
                col("data_quality_score").desc()
            )
        elif rule == "LATEST":
            window = Window.partitionBy(key_columns).orderBy(
                col("updated_at").desc()
            )
        else:  # MANUAL
            # Don't resolve - keep all for review
            return df.withColumn("requires_manual_review", lit(True))

        # Select winning record
        df_ranked = df.withColumn("rank", row_number().over(window))

        golden = df_ranked \
            .filter(col("rank") == 1) \
            .drop("rank") \
            .withColumn("is_golden_record", lit(True)) \
            .withColumn("conflict_resolution_rule", lit(rule))

        return golden

    def _apply_scd_type2(self, new_data, existing_table, key_columns):
        """
        Slowly Changing Dimension Type 2 implementation.
        Maintains full history of changes.
        """
        # Read existing current records
        existing = self.spark.table(existing_table) \
            .filter("is_current = TRUE")

        # Detect changes
        changes = new_data.alias("new").join(
            existing.alias("old"),
            key_columns,
            "left_outer"
        )

        # New records (INSERT)
        new_records = changes \
            .filter(col("old.{0}".format(key_columns[0])).isNull()) \
            .select("new.*") \
            .withColumn("version_number", lit(1)) \
            .withColumn("effective_from", current_timestamp()) \
            .withColumn("effective_to", lit(None).cast("timestamp")) \
            .withColumn("is_current", lit(True))

        # Changed records (UPDATE - expire old + insert new)
        changed_records = changes \
            .filter(col("old.{0}".format(key_columns[0])).isNotNull()) \
            .filter(self._has_changes(new_data.columns))

        # Expire old versions
        expired = changed_records \
            .select("old.*") \
            .withColumn("effective_to", current_timestamp()) \
            .withColumn("is_current", lit(False))

        # Insert new versions
        new_versions = changed_records \
            .select("new.*") \
            .withColumn("version_number", col("old.version_number") + 1) \
            .withColumn("effective_from", current_timestamp()) \
            .withColumn("effective_to", lit(None).cast("timestamp")) \
            .withColumn("is_current", lit(True))

        # Unchanged records (keep as-is)
        unchanged = changes \
            .filter(col("old.{0}".format(key_columns[0])).isNotNull()) \
            .filter(~self._has_changes(new_data.columns)) \
            .select("old.*")

        # Combine all
        final = new_records \
            .unionByName(expired) \
            .unionByName(new_versions) \
            .unionByName(unchanged)

        return final

    def _write_to_kudu(self, df, table, mode="upsert"):
        """Write DataFrame to Kudu table via Impala"""
        # Use Kudu connector
        df.write \
            .format("org.apache.kudu.spark.kudu") \
            .option("kudu.master", "kudu-master:7051") \
            .option("kudu.table", table) \
            .mode(mode) \
            .save()
```

---

## 4. Control-M Job Flow

### 4.1 Job Dependencies

```
┌─────────────────────────────────────────────────────────────┐
│                    DAILY ETL WORKFLOW                        │
│                 Control-M Job Orchestration                  │
└─────────────────────────────────────────────────────────────┘

06:00 AM  ┌──────────────────────────────────────┐
          │  CIS_ETL_BRONZE_INGEST               │
          │  Job: bronze_ingest_gmp_data.py      │
          │  Timeout: 30 min                     │
          │  On Success → Silver                 │
          └──────────────────────────────────────┘
                        ↓
07:00 AM  ┌──────────────────────────────────────┐
          │  CIS_ETL_SILVER_CLEANSE              │
          │  Job: silver_cleanse_validate.py     │
          │  Timeout: 45 min                     │
          │  On Success → Gold                   │
          └──────────────────────────────────────┘
                        ↓
08:00 AM  ┌──────────────────────────────────────┐
          │  CIS_ETL_GOLD_UPSERT                 │
          │  Job: gold_create_golden_records.py  │
          │  Timeout: 60 min                     │
          │  On Success → Reconciliation         │
          └──────────────────────────────────────┘
                        ↓
09:00 AM  ┌──────────────────────────────────────┐
          │  CIS_ETL_RECONCILIATION              │
          │  Job: reconcile_gmp_cis.py           │
          │  Compare GMP vs CIS counts/totals    │
          │  On Failure → Alert + Email          │
          └──────────────────────────────────────┘
                        ↓
09:30 AM  ┌──────────────────────────────────────┐
          │  CIS_ETL_NOTIFICATION                │
          │  Email: ETL Success Report           │
          │  Includes: Counts, Quality Scores    │
          └──────────────────────────────────────┘
```

### 4.2 Control-M Job Definitions

**File**: `controlm_jobs.json`

```json
{
  "CIS_ETL_BRONZE_INGEST": {
    "Application": "CIS_ETL",
    "SubApplication": "BRONZE",
    "JobName": "CIS_ETL_BRONZE_INGEST",
    "RunAs": "cis_etl_user",
    "Command": "spark-submit --master yarn --deploy-mode cluster --conf spark.dynamicAllocation.enabled=true bronze_ingest_gmp_data.py %%ODATE",
    "Schedule": {
      "Days": ["MON", "TUE", "WED", "THU", "FRI"],
      "Time": "06:00"
    },
    "Conditions": {
      "In": "GMP_EOD_COMPLETE"
    },
    "Actions": {
      "OnSuccess": "SET CIS_BRONZE_COMPLETE",
      "OnFailure": "NOTIFY SUPPORT_TEAM"
    },
    "MaxReruns": 2,
    "Timeout": 1800
  },

  "CIS_ETL_SILVER_CLEANSE": {
    "Application": "CIS_ETL",
    "SubApplication": "SILVER",
    "JobName": "CIS_ETL_SILVER_CLEANSE",
    "RunAs": "cis_etl_user",
    "Command": "spark-submit --master yarn --deploy-mode cluster silver_cleanse_validate.py %%ODATE",
    "Conditions": {
      "In": "CIS_BRONZE_COMPLETE"
    },
    "Actions": {
      "OnSuccess": "SET CIS_SILVER_COMPLETE",
      "OnFailure": "NOTIFY SUPPORT_TEAM"
    },
    "MaxReruns": 2,
    "Timeout": 2700
  },

  "CIS_ETL_GOLD_UPSERT": {
    "Application": "CIS_ETL",
    "SubApplication": "GOLD",
    "JobName": "CIS_ETL_GOLD_UPSERT",
    "RunAs": "cis_etl_user",
    "Command": "spark-submit --master yarn --deploy-mode cluster --packages org.apache.kudu:kudu-spark3_2.12:1.17.0 gold_create_golden_records.py %%ODATE",
    "Conditions": {
      "In": "CIS_SILVER_COMPLETE"
    },
    "Actions": {
      "OnSuccess": "SET CIS_GOLD_COMPLETE",
      "OnFailure": "NOTIFY SUPPORT_TEAM"
    },
    "MaxReruns": 1,
    "Timeout": 3600
  }
}
```

---

## 5. Performance Optimization Strategies

### 5.1 Partitioning Strategy

```sql
-- Time-based partitioning for Position (most queried by date)
CREATE TABLE gmp_cis.cis_position_kudu (
    ...
)
PARTITION BY HASH (position_id) PARTITIONS 16,
             RANGE (position_date) (
                 -- Historical (read-only, compressed)
                 PARTITION VALUES < '2024-01-01',

                 -- Current year (active writes)
                 PARTITION '2024-01-01' <= VALUES < '2025-01-01',

                 -- Future (active writes)
                 PARTITION '2025-01-01' <= VALUES
             )
STORED AS KUDU;
```

### 5.2 Indexing Strategy (Kudu Primary Keys)

```python
# Composite primary keys for fast lookups
ENTITY_KEYS = {
    'portfolio': ['name', 'version_number'],
    'trade': ['trade_ref', 'version_number'],
    'position': ['position_id', 'position_date', 'version_number'],
    'security': ['security_id', 'version_number'],
    'counterparty': ['counterparty_short_name', 'version_number']
}
```

### 5.3 Query Optimization

```sql
-- Materialized view for current golden records (no versioning overhead)
CREATE VIEW gmp_cis.v_current_portfolios AS
SELECT *
FROM gmp_cis.cis_portfolio_kudu
WHERE is_current = TRUE
  AND is_deleted = FALSE
  AND is_golden_record = TRUE;

-- Django ORM can query this view for better performance
```

### 5.4 Caching Strategy

```python
# Django settings.py - add Redis cache for golden records
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://redis:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'cis_golden',
        'TIMEOUT': 3600  # 1 hour TTL for golden records
    }
}

# Cache invalidation on ETL completion
# Add to gold_create_golden_records.py:
import redis
r = redis.Redis(host='redis', port=6379, db=1)
r.flushdb()  # Clear cache after golden record update
```

---

## 6. Data Quality & Reconciliation

### 6.1 Reconciliation Job

**Job**: `reconcile_gmp_cis.py`

```python
# reconcile_gmp_cis.py
class Reconciliation:
    """
    Daily reconciliation between GMP source and CIS golden records.
    Generates exception report for manual review.
    """

    def reconcile_counts(self, entity):
        """Compare record counts"""
        gmp_count = spark.table(f"gmp_cis_bronze.gmp_raw_{entity}") \
            .filter(f"processing_date = '{self.processing_date}'") \
            .count()

        gold_count = spark.table(f"gmp_cis.cis_{entity}_kudu") \
            .filter("is_current = TRUE AND src_system = 'GMP'") \
            .count()

        variance = abs(gmp_count - gold_count)

        if variance > 0:
            self.log_exception(entity, "COUNT_MISMATCH",
                              f"GMP: {gmp_count}, Gold: {gold_count}")

        return variance == 0

    def reconcile_amounts(self, entity):
        """Compare aggregate amounts (for trades, positions)"""
        if entity not in ['trade', 'position']:
            return True

        gmp_total = spark.table(f"gmp_cis_bronze.gmp_raw_{entity}") \
            .filter(f"processing_date = '{self.processing_date}'") \
            .agg(sum("net_amount").alias("total")) \
            .collect()[0]['total']

        gold_total = spark.table(f"gmp_cis.cis_{entity}_kudu") \
            .filter("is_current = TRUE AND src_system = 'GMP'") \
            .agg(sum("net_amount").alias("total")) \
            .collect()[0]['total']

        variance_pct = abs((gmp_total - gold_total) / gmp_total) * 100

        if variance_pct > 0.01:  # 0.01% tolerance
            self.log_exception(entity, "AMOUNT_MISMATCH",
                              f"Variance: {variance_pct:.4f}%")

        return variance_pct <= 0.01
```

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- ✅ Enhance existing Kudu tables (add versioning columns)
- ✅ Create Bronze/Silver Hive databases
- ✅ Implement Bronze ingestion job
- ✅ Set up Control-M jobs framework

### Phase 2: Core ETL (Week 3-4)
- ⬜ Implement Silver cleansing logic
- ⬜ Develop golden record creation
- ⬜ Test SCD Type 2 versioning
- ⬜ End-to-end testing with sample data

### Phase 3: Production Rollout (Week 5-6)
- ⬜ Migrate Portfolio entity first
- ⬜ Add Trade entity
- ⬜ Add Position entity
- ⬜ Security & Counterparty enhancement
- ⬜ Performance testing (10M+ records)

### Phase 4: Monitoring & Optimization (Week 7-8)
- ⬜ Set up reconciliation reports
- ⬜ Implement data quality dashboards
- ⬜ Query optimization
- ⬜ User training

---

## 8. Key Benefits

✅ **Single Source of Truth**: Golden copy ensures data consistency
✅ **Full Audit Trail**: SCD Type 2 preserves all historical changes
✅ **Source Transparency**: Every record tagged with GMP/CIS origin
✅ **Conflict Resolution**: Automated rules + manual review for exceptions
✅ **Performance**: Kudu for real-time + Parquet for analytics
✅ **Scalability**: Partitioning supports 100M+ records
✅ **Data Quality**: Built-in scoring and validation
✅ **Minimal Complexity**: Standardized pattern across all entities

---

## Appendix A: File Structure

```
cis_trade_hive/
├── etl/
│   ├── bronze/
│   │   ├── bronze_ingest_gmp_data.py
│   │   └── schemas/
│   │       ├── portfolio_schema.py
│   │       ├── trade_schema.py
│   │       └── position_schema.py
│   ├── silver/
│   │   ├── silver_cleanse_validate.py
│   │   └── validation_rules.yaml
│   ├── gold/
│   │   ├── gold_create_golden_records.py
│   │   └── conflict_resolution.py
│   ├── reconciliation/
│   │   └── reconcile_gmp_cis.py
│   └── utils/
│       ├── kudu_writer.py
│       ├── scd_type2.py
│       └── quality_score.py
├── controlm/
│   └── controlm_jobs.json
└── docs/
    └── ETL_Golden_Copy_Architecture.md
```

---

**Document Version**: 1.0
**Last Updated**: 2026-01-09
**Author**: CIS Development Team
