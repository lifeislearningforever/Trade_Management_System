"""
PySpark Job: Merge Position Data from 12 Staging Tables into Position Master
=============================================================================

Overview:
  Consolidates position data from 12 staging tables (4 source systems × 3 sub-tables)
  into a unified cis_position_master table with security validation.

Source Systems (12 staging tables):
  1. CIS - Cooperative Investment System (stg_cis_positions, stg_cis_summary, stg_cis_history)
  2. GMP - Global Markets Platform (stg_gmp_positions, stg_gmp_summary, stg_gmp_history)
  3. AMS - Asset Management System (stg_ams_positions, stg_ams_summary, stg_ams_history)
  4. IMS - Investment Management System (stg_ims_positions, stg_ims_summary, stg_ims_history)

Data Flow:
  Staging Tables → Security Validation → cis_position_master (matched)
                                      → cis_position_unmatched (unmatched for review)

Storage:
  - Target tables: Hive External Tables with Parquet format
  - Security master: Kudu (cis_security_kudu)
  - Staging tables: Hive External Tables with Parquet format

Security Validation Logic:
  1. Match on security_label + isin against cis_security_kudu
  2. If matched: set is_matched=True, security_id=matched_id, match_status=EXACT
  3. If partial match (isin only): is_matched=True, match_status=ISIN_MATCH
  4. If no match: is_matched=False, move to cis_position_unmatched for:
     a) Manual review, OR
     b) Auto-creation in cis_security_kudu (future enhancement)

Usage:
  # Cloudera/YARN
  spark-submit --master yarn \\
    --conf spark.executor.memory=4g \\
    --conf spark.executor.cores=2 \\
    merge_position_master.py \\
    --kudu-master kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251 \\
    --source all \\
    --valuation-date 2026-02-09 \\
    --batch-id BATCH_20260209_001

  # Local Docker
  spark-submit merge_position_master.py \\
    --kudu-master localhost:7051 \\
    --source gmp \\
    --batch-id BATCH_20260209_001

Parameters:
  --kudu-master    : Kudu master addresses (required for security master lookup)
  --source         : Source system to process: cis, gmp, ams, ims, or 'all' (default: all)
  --valuation-date : Filter by valuation date (YYYY-MM-DD)
  --batch-id       : Filter by ETL batch ID
  --dry-run        : Preview without writing
  --auto-create    : Auto-create missing securities in cis_security (placeholder)

Author: CisTrade Team
Created: 2026-02-09
Updated: 2026-02-10 (Converted from Kudu to Hive/Parquet)
"""

import argparse
import time
from datetime import datetime
from typing import List, Optional, Tuple

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import StructType, StructField, StringType, DecimalType, LongType, BooleanType, IntegerType


# ============================================================================
# Configuration
# ============================================================================

DATABASE = "gmp_cis"

# Target tables (Hive/Parquet)
TARGET_TABLE = f"{DATABASE}.cis_position_master"
UNMATCHED_TABLE = f"{DATABASE}.cis_position_unmatched"
HISTORY_TABLE = f"{DATABASE}.cis_position_master_history"

# HDFS locations for Parquet files
TARGET_LOCATION = "/data/gmp_cis/cis_position_master"
UNMATCHED_LOCATION = "/data/gmp_cis/cis_position_unmatched"
HISTORY_LOCATION = "/data/gmp_cis/cis_position_master_history"

# Security master (still Kudu for atomic lookups)
SECURITY_TABLE = f"{DATABASE}.cis_security_kudu"
IMPALA_SECURITY_TABLE = f"impala::{DATABASE}.cis_security_kudu"

# Staging tables by source (Hive/Parquet)
STAGING_TABLES = {
    "cis": {
        "positions": f"{DATABASE}.stg_cis_positions",
        "summary": f"{DATABASE}.stg_cis_summary",
        "history": f"{DATABASE}.stg_cis_history",
    },
    "gmp": {
        "positions": f"{DATABASE}.stg_gmp_positions",
        "summary": f"{DATABASE}.stg_gmp_summary",
        "history": f"{DATABASE}.stg_gmp_history",
    },
    "ams": {
        "positions": f"{DATABASE}.stg_ams_positions",
        "summary": f"{DATABASE}.stg_ams_summary",
        "history": f"{DATABASE}.stg_ams_history",
    },
    "ims": {
        "positions": f"{DATABASE}.stg_ims_positions",
        "summary": f"{DATABASE}.stg_ims_summary",
        "history": f"{DATABASE}.stg_ims_history",
    },
}

# Staging HDFS locations
STAGING_LOCATIONS = {
    "cis": {
        "positions": "/data/gmp_cis/staging/stg_cis_positions",
        "summary": "/data/gmp_cis/staging/stg_cis_summary",
        "history": "/data/gmp_cis/staging/stg_cis_history",
    },
    "gmp": {
        "positions": "/data/gmp_cis/staging/stg_gmp_positions",
        "summary": "/data/gmp_cis/staging/stg_gmp_summary",
        "history": "/data/gmp_cis/staging/stg_gmp_history",
    },
    "ams": {
        "positions": "/data/gmp_cis/staging/stg_ams_positions",
        "summary": "/data/gmp_cis/staging/stg_ams_summary",
        "history": "/data/gmp_cis/staging/stg_ams_history",
    },
    "ims": {
        "positions": "/data/gmp_cis/staging/stg_ims_positions",
        "summary": "/data/gmp_cis/staging/stg_ims_summary",
        "history": "/data/gmp_cis/staging/stg_ims_history",
    },
}


# ============================================================================
# Common Position Schema
# ============================================================================
# All staging tables map to this common schema for the master table

COMMON_POSITION_COLUMNS = [
    "portfolio_short_name",
    "security_label",
    "valuation_date",
    "isin",
    "security_name",
    "security_type",
    "ticker",
    "security_currency",
    "portfolio_currency",
    "quantity",
    "face_value",
    "lots_held",
    "average_cost",
    "total_cost",
    "cost_value_local",
    "cost_value_base",
    "market_unit_price",
    "market_value",
    "market_value_local",
    "market_value_base",
    "unrealized_pnl",
    "unrealized_pnl_local",
    "unrealized_pnl_base",
    "realized_pnl",
    "pct_ratio",
    "country",
    "asset_class",
    "listing_status",
    "custodian",
    "sub_custodian",
    "status",
    "src_position_id",
    "etl_batch_id",
]


# ============================================================================
# Argument Parsing
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Merge position data from staging tables into Position Master"
    )
    parser.add_argument(
        "--kudu-master",
        required=True,
        help="Kudu master addresses for security master lookup (e.g., kudu-master-1:7051)",
    )
    parser.add_argument(
        "--source",
        default="all",
        choices=["cis", "gmp", "ams", "ims", "all"],
        help="Source system to process (default: all)",
    )
    parser.add_argument(
        "--valuation-date",
        default=None,
        help="Filter by valuation date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--batch-id",
        default=None,
        help="Filter by ETL batch ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to target",
    )
    parser.add_argument(
        "--auto-create",
        action="store_true",
        help="Auto-create missing securities in cis_security (PLACEHOLDER - not yet implemented)",
    )
    return parser.parse_args()


# ============================================================================
# Spark Session
# ============================================================================

def create_spark_session() -> SparkSession:
    return (
        SparkSession.builder
        .appName("CIS_Merge_Position_Master")
        .config("spark.sql.shuffle.partitions", "32")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .enableHiveSupport()
        .getOrCreate()
    )


# ============================================================================
# Data Loading Functions
# ============================================================================

def read_staging_positions(
    spark: SparkSession,
    source: str,
    valuation_date: Optional[str] = None,
    batch_id: Optional[str] = None
) -> DataFrame:
    """Read position data from a single source staging table (Hive/Parquet)."""

    table = STAGING_TABLES[source]["positions"]

    try:
        df = spark.table(table)
    except Exception as e:
        # Fallback to reading from HDFS location directly
        location = STAGING_LOCATIONS[source]["positions"]
        print(f"[INFO] Reading from HDFS location: {location}")
        df = spark.read.parquet(location)

    # Add source system identifier
    df = df.withColumn("src_system", F.lit(source.upper()))
    df = df.withColumn("src_table", F.lit(table))

    # Apply filters
    if valuation_date:
        df = df.filter(F.col("valuation_date") == valuation_date)
    if batch_id:
        df = df.filter(F.col("etl_batch_id") == batch_id)

    # Select common columns + source-specific additions
    available_cols = set(df.columns)
    select_cols = [c for c in COMMON_POSITION_COLUMNS if c in available_cols]
    select_cols.extend(["src_system", "src_table"])

    # Add missing columns as NULL
    for col in COMMON_POSITION_COLUMNS:
        if col not in available_cols:
            df = df.withColumn(col, F.lit(None))

    return df


def read_all_staging_positions(
    spark: SparkSession,
    sources: List[str],
    valuation_date: Optional[str] = None,
    batch_id: Optional[str] = None
) -> DataFrame:
    """Read and union position data from multiple staging tables (Hive/Parquet)."""

    dfs = []

    for source in sources:
        try:
            df = read_staging_positions(spark, source, valuation_date, batch_id)
            count = df.count()
            print(f"[INFO] {source.upper()}: {count} staging records loaded")
            if count > 0:
                dfs.append(df)
        except Exception as e:
            print(f"[WARN] Failed to read {source} staging: {e}")

    if not dfs:
        print("[WARN] No staging data found from any source")
        return None

    # Union all sources
    result = dfs[0]
    for df in dfs[1:]:
        result = result.unionByName(df, allowMissingColumns=True)

    return result


def read_security_master(spark: SparkSession, kudu_master: str) -> DataFrame:
    """Read security master from Kudu for matching."""

    df = (
        spark.read
        .format("kudu")
        .option("kudu.master", kudu_master)
        .option("kudu.table", IMPALA_SECURITY_TABLE)
        .load()
        .select(
            F.col("security_id"),
            F.col("security_name").alias("sec_name"),
            F.col("isin").alias("sec_isin"),
            F.col("security_type").alias("sec_type"),
            F.col("ticker").alias("sec_ticker"),
            F.col("currency_code").alias("sec_currency"),
            F.col("country_of_issue").alias("sec_country"),
        )
        .filter(F.col("is_active") == True)
    )

    print(f"[INFO] Security master: {df.count()} active securities loaded")
    return df


def read_existing_positions(spark: SparkSession) -> DataFrame:
    """Read existing position master from Hive/Parquet for updates."""

    try:
        df = (
            spark.table(TARGET_TABLE)
            .select(
                "position_master_id",
                "portfolio_short_name",
                "security_label",
                "valuation_date",
                "src_system",
            )
        )
        print(f"[INFO] Existing positions: {df.count()} records")
        return df
    except Exception as e:
        print(f"[WARN] Could not read existing positions (table may not exist): {e}")
        # Try reading from HDFS directly
        try:
            df = (
                spark.read.parquet(TARGET_LOCATION)
                .select(
                    "position_master_id",
                    "portfolio_short_name",
                    "security_label",
                    "valuation_date",
                    "src_system",
                )
            )
            print(f"[INFO] Existing positions from HDFS: {df.count()} records")
            return df
        except Exception as e2:
            print(f"[WARN] Could not read existing positions from HDFS: {e2}")
            return None


# ============================================================================
# Security Validation Logic
# ============================================================================

def validate_securities(
    stg_df: DataFrame,
    security_df: DataFrame
) -> Tuple[DataFrame, DataFrame]:
    """
    Validate staging positions against security master.

    Returns:
        - matched_df: Positions with valid security match
        - unmatched_df: Positions that need review

    ========================================================================
    SECURITY VALIDATION PLACEHOLDER
    ========================================================================

    Current Implementation:
    - Exact match on security_label (primary) or isin (secondary)
    - Sets is_matched=True/False and match_status accordingly

    Future Enhancement:
    - Fuzzy matching on security_name using Levenshtein distance
    - Auto-creation of missing securities in cis_security_kudu
    - Integration with external security master APIs

    To implement auto-creation:
    1. Extract unique unmatched securities
    2. Generate new security_id values
    3. UPSERT into cis_security_kudu with src_system='ETL'
    4. Re-match the positions

    ========================================================================
    """

    # Join staging with security master
    # Match priorities: security_label > isin

    joined_df = stg_df.alias("stg").join(
        security_df.alias("sec"),
        (F.col("stg.security_label") == F.col("sec.sec_name")) |
        (F.col("stg.isin") == F.col("sec.sec_isin")),
        "left"
    )

    # Determine match type
    matched_df = (
        joined_df
        .withColumn(
            "is_matched",
            F.when(F.col("sec.security_id").isNotNull(), True).otherwise(False)
        )
        .withColumn(
            "match_status",
            F.when(
                F.col("stg.security_label") == F.col("sec.sec_name"),
                F.lit("EXACT")
            ).when(
                F.col("stg.isin") == F.col("sec.sec_isin"),
                F.lit("ISIN_MATCH")
            ).otherwise(
                F.lit("UNMATCHED")
            )
        )
        .withColumn(
            "security_id",
            F.col("sec.security_id")
        )
    )

    # Split into matched and unmatched
    valid_positions = matched_df.filter(F.col("is_matched") == True)
    invalid_positions = matched_df.filter(F.col("is_matched") == False)

    match_count = valid_positions.count()
    unmatch_count = invalid_positions.count()

    print(f"[INFO] Security validation results:")
    print(f"       Matched:   {match_count}")
    print(f"       Unmatched: {unmatch_count}")

    return valid_positions, invalid_positions


# ============================================================================
# Auto-Create Securities (PLACEHOLDER)
# ============================================================================

def auto_create_securities(
    spark: SparkSession,
    kudu_master: str,
    unmatched_df: DataFrame
) -> DataFrame:
    """
    ========================================================================
    PLACEHOLDER: Auto-create missing securities in cis_security
    ========================================================================

    This function is a placeholder for future implementation.

    When implemented, it will:
    1. Extract unique unmatched security_label + isin combinations
    2. Generate new security_id values (timestamp-based)
    3. Create minimal security records with:
       - security_name = security_label from position
       - isin = isin from position
       - security_type = inferred or 'UNKNOWN'
       - currency_code = security_currency from position
       - src_system = 'ETL_AUTO_CREATED'
       - is_active = True
    4. UPSERT into cis_security_kudu
    5. Return the newly created security IDs for re-matching

    For now, this function is a no-op and returns an empty DataFrame.
    ========================================================================
    """

    print("[PLACEHOLDER] Auto-create securities is not yet implemented")
    print("             Unmatched securities will be written to cis_position_unmatched")
    print("             for manual review or future batch processing.")

    # Return empty DataFrame - no securities created
    return spark.createDataFrame([], StructType([
        StructField("security_id", LongType(), False),
        StructField("security_label", StringType(), True),
        StructField("isin", StringType(), True),
    ]))


# ============================================================================
# ID Generation
# ============================================================================

def generate_position_ids(df: DataFrame, start_id: int) -> DataFrame:
    """Generate timestamp-based position_master_id for new records."""

    window = Window.orderBy("portfolio_short_name", "security_label", "valuation_date")
    return df.withColumn(
        "position_master_id",
        F.lit(start_id) + F.row_number().over(window)
    )


def generate_unmatched_ids(df: DataFrame, start_id: int) -> DataFrame:
    """Generate timestamp-based unmatched_id for unmatched records."""

    window = Window.orderBy("portfolio_short_name", "security_label", "valuation_date")
    return df.withColumn(
        "unmatched_id",
        F.lit(start_id) + F.row_number().over(window)
    )


# ============================================================================
# Build Final DataFrames
# ============================================================================

def build_master_records(
    matched_df: DataFrame,
    existing_df: Optional[DataFrame],
    now_ms: int,
    now_str: str
) -> DataFrame:
    """Build final position master records for merge."""

    # If we have existing positions, join to reuse position_master_id
    if existing_df is not None and existing_df.count() > 0:
        result = (
            matched_df.alias("new").join(
                existing_df.alias("old"),
                (F.col("new.portfolio_short_name") == F.col("old.portfolio_short_name")) &
                (F.col("new.security_label") == F.col("old.security_label")) &
                (F.col("new.valuation_date") == F.col("old.valuation_date")) &
                (F.col("new.src_system") == F.col("old.src_system")),
                "left"
            )
            .withColumn(
                "position_master_id",
                F.coalesce(F.col("old.position_master_id"), F.lit(None))
            )
        )

        # Generate IDs for new records
        needs_id = result.filter(F.col("position_master_id").isNull())
        has_id = result.filter(F.col("position_master_id").isNotNull())

        if needs_id.count() > 0:
            needs_id = generate_position_ids(needs_id, now_ms)
            result = has_id.unionByName(needs_id, allowMissingColumns=True)
        else:
            result = has_id
    else:
        result = generate_position_ids(matched_df, now_ms)

    # Add metadata columns
    result = (
        result
        .withColumn("created_at", F.lit(now_str))
        .withColumn("updated_at", F.lit(now_str))
        .withColumn("etl_load_timestamp", F.lit(now_ms))
        .withColumn("is_active", F.lit(True))
    )

    return result


def build_unmatched_records(
    unmatched_df: DataFrame,
    now_ms: int,
    now_str: str
) -> DataFrame:
    """Build unmatched position records for review."""

    result = (
        unmatched_df
        .withColumn("attempted_match_key",
            F.concat_ws("|", F.col("security_label"), F.col("isin")))
        .withColumn("match_attempt_count", F.lit(1))
        .withColumn("last_match_attempt", F.lit(now_str))
        .withColumn("resolution_status", F.lit("PENDING"))
        .withColumn("resolution_notes", F.lit(None))
        .withColumn("resolved_by", F.lit(None))
        .withColumn("resolved_at", F.lit(None))
        .withColumn("created_at", F.lit(now_str))
    )

    result = generate_unmatched_ids(result, now_ms)

    return result


# ============================================================================
# Main Merge Function
# ============================================================================

def merge_positions(
    spark: SparkSession,
    kudu_master: str,
    sources: List[str],
    valuation_date: Optional[str] = None,
    batch_id: Optional[str] = None,
    dry_run: bool = False,
    auto_create: bool = False
):
    """Main merge logic."""

    now_ms = int(datetime.now().timestamp() * 1000)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 70)
    print("Position Master Merge (Hive/Parquet)")
    print("=" * 70)
    print(f"Timestamp:       {now_str}")
    print(f"Sources:         {', '.join(sources)}")
    print(f"Valuation Date:  {valuation_date or 'ALL'}")
    print(f"Batch ID:        {batch_id or 'ALL'}")
    print(f"Dry Run:         {dry_run}")
    print(f"Auto Create:     {auto_create}")
    print(f"Target Table:    {TARGET_TABLE}")
    print(f"Target Location: {TARGET_LOCATION}")
    print("=" * 70)

    # Step 1: Load staging data from all sources (Hive/Parquet)
    print("\n[STEP 1] Loading staging data from Hive/Parquet...")
    stg_df = read_all_staging_positions(spark, sources, valuation_date, batch_id)

    if stg_df is None or stg_df.count() == 0:
        print("[INFO] No staging records found. Nothing to merge.")
        return

    total_staging = stg_df.count()
    print(f"[INFO] Total staging records: {total_staging}")

    # Step 2: Load security master (Kudu)
    print("\n[STEP 2] Loading security master from Kudu...")
    security_df = read_security_master(spark, kudu_master)

    # Step 3: Validate securities
    print("\n[STEP 3] Validating securities...")
    matched_df, unmatched_df = validate_securities(stg_df, security_df)

    # Step 4: Auto-create securities (if enabled and unmatched exist)
    if auto_create and unmatched_df.count() > 0:
        print("\n[STEP 4] Auto-creating missing securities...")
        new_securities = auto_create_securities(spark, kudu_master, unmatched_df)

        # Re-validate unmatched with new securities
        # TODO: Implement re-matching after auto-creation
    else:
        print("\n[STEP 4] Skipping auto-creation (disabled or no unmatched)")

    # Step 5: Load existing positions for ID reuse (Hive/Parquet)
    print("\n[STEP 5] Loading existing positions from Hive/Parquet...")
    existing_df = read_existing_positions(spark)

    # Step 6: Build final records
    print("\n[STEP 6] Building final records...")
    master_records = build_master_records(matched_df, existing_df, now_ms, now_str)
    unmatched_records = build_unmatched_records(unmatched_df, now_ms, now_str)

    master_count = master_records.count()
    unmatched_count = unmatched_records.count()

    print(f"[INFO] Records to write to position_master:   {master_count}")
    print(f"[INFO] Records to write to position_unmatched: {unmatched_count}")

    # Dry run preview
    if dry_run:
        print("\n[DRY RUN] Preview of position master records:")
        master_records.select(
            "position_master_id", "portfolio_short_name", "security_label",
            "valuation_date", "src_system", "is_matched", "match_status"
        ).show(20, truncate=False)

        if unmatched_count > 0:
            print("\n[DRY RUN] Preview of unmatched records:")
            unmatched_records.select(
                "unmatched_id", "portfolio_short_name", "security_label",
                "isin", "valuation_date", "src_system"
            ).show(20, truncate=False)

        return

    # Step 7: Write to Hive/Parquet
    print("\n[STEP 7] Writing to Hive/Parquet...")

    # Write matched positions
    if master_count > 0:
        # Select only columns that exist in target table
        master_cols = [
            "position_master_id", "portfolio_short_name", "security_label",
            "valuation_date", "src_system", "isin", "security_id", "security_name",
            "security_type", "ticker", "portfolio_full_name", "portfolio_id",
            "fund_type", "security_currency", "portfolio_currency", "quantity",
            "face_value", "lots_held", "average_cost", "total_cost",
            "cost_value_local", "cost_value_base", "market_unit_price",
            "current_price", "market_value", "market_value_local",
            "market_value_base", "unrealized_pnl", "unrealized_pnl_local",
            "unrealized_pnl_base", "realized_pnl", "pct_ratio", "country",
            "asset_class", "listing_status", "industry", "sector", "custodian",
            "sub_custodian", "status", "is_active", "is_matched", "match_status",
            "src_table", "src_position_id", "src_batch_id", "created_at",
            "updated_at", "etl_load_timestamp"
        ]

        # Add missing columns as NULL
        for col in master_cols:
            if col not in master_records.columns:
                master_records = master_records.withColumn(col, F.lit(None))

        # Write to Parquet (overwrite mode for full refresh)
        # For incremental, use append or partitioned writes
        (
            master_records.select(master_cols).write
            .format("parquet")
            .option("compression", "snappy")
            .mode("overwrite")
            .save(TARGET_LOCATION)
        )
        print(f"[SUCCESS] Wrote {master_count} records to {TARGET_LOCATION}")

        # Refresh Hive table metadata
        try:
            spark.sql(f"MSCK REPAIR TABLE {TARGET_TABLE}")
        except Exception as e:
            print(f"[WARN] Could not repair table metadata: {e}")

    # Write unmatched positions
    if unmatched_count > 0:
        unmatched_cols = [
            "unmatched_id", "portfolio_short_name", "security_label", "isin",
            "valuation_date", "src_system", "src_table", "attempted_match_key",
            "match_attempt_count", "last_match_attempt", "security_name",
            "security_type", "currency_code", "country", "exchange_code",
            "quantity", "market_value", "cost_value", "resolution_status",
            "resolution_notes", "resolved_by", "resolved_at", "created_at",
            "etl_batch_id"
        ]

        # Map columns
        unmatched_records = (
            unmatched_records
            .withColumnRenamed("security_currency", "currency_code")
            .withColumnRenamed("market_value_local", "market_value")
            .withColumnRenamed("cost_value_local", "cost_value")
        )

        # Add missing columns as NULL
        for col in unmatched_cols:
            if col not in unmatched_records.columns:
                unmatched_records = unmatched_records.withColumn(col, F.lit(None))

        # Write to Parquet
        (
            unmatched_records.select(unmatched_cols).write
            .format("parquet")
            .option("compression", "snappy")
            .mode("overwrite")
            .save(UNMATCHED_LOCATION)
        )
        print(f"[SUCCESS] Wrote {unmatched_count} records to {UNMATCHED_LOCATION}")

        # Refresh Hive table metadata
        try:
            spark.sql(f"MSCK REPAIR TABLE {UNMATCHED_TABLE}")
        except Exception as e:
            print(f"[WARN] Could not repair table metadata: {e}")

    print("\n" + "=" * 70)
    print("Position Master Merge Complete")
    print("=" * 70)


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    args = parse_args()

    # Determine sources to process
    if args.source == "all":
        sources = list(STAGING_TABLES.keys())
    else:
        sources = [args.source]

    spark = create_spark_session()

    try:
        merge_positions(
            spark,
            kudu_master=args.kudu_master,
            sources=sources,
            valuation_date=args.valuation_date,
            batch_id=args.batch_id,
            dry_run=args.dry_run,
            auto_create=args.auto_create,
        )
    except Exception as e:
        print(f"[ERROR] Merge failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        spark.stop()
