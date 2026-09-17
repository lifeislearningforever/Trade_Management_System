"""
PySpark Job: Merge GMP Equity Price Data into CIS Equity Price Table
=====================================================================
Problem:
  - GMP ETL sends equity price data
  - cis_equity_price PK = (currency_code, security_label, price_date)
  - This is a NATURAL composite key - GMP provides all PK fields
  - No surrogate key gap (unlike security table)

Strategy:
  - Simple: Read staging -> Add src_system='GMP' + audit columns -> UPSERT
  - UPSERT handles both INSERT (new) and UPDATE (existing date+security)

Usage:
  spark-submit --master yarn \
    --conf spark.executor.memory=4g \
    --conf spark.executor.cores=2 \
    merge_gmp_equity_price.py \
    --kudu-master kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251 \
    --batch-id BATCH_20260202_001

For local Docker:
  spark-submit merge_gmp_equity_price.py \
    --kudu-master localhost:7051 \
    --batch-id BATCH_20260202_001

Author: CisTrade Team
Created: 2026-02-02
"""

import argparse
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
import os


# ============================================================================
# Configuration
# ============================================================================

DATABASE = os.environ.get('IMPALA_DB', 'gmp_cis')
STAGING_TABLE = f"{DATABASE}.stg_gmp_equity_price"
TARGET_TABLE = f"{DATABASE}.cis_equity_price"
IMPALA_STAGING_TABLE = f"impala::{DATABASE}.stg_gmp_equity_price_kudu"
IMPALA_TARGET_TABLE = f"impala::{DATABASE}.cis_equity_price_kudu"
IMPALA_SECURITY_TABLE = f"impala::{DATABASE}.cis_security_kudu"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Merge GMP equity price data into CIS"
    )
    parser.add_argument(
        "--kudu-master",
        required=True,
        help="Kudu master addresses",
    )
    parser.add_argument(
        "--batch-id",
        default=None,
        help="Optional batch ID to filter staging data",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to target",
    )
    return parser.parse_args()


def create_spark_session():
    return (
        SparkSession.builder
        .appName("CIS_Merge_GMP_Equity_Price")
        .config("spark.sql.shuffle.partitions", "16")
        .getOrCreate()
    )


def merge_equity_prices(spark, kudu_master, batch_id=None, dry_run=False):
    """Merge GMP equity prices into CIS target table.

    Since cis_equity_price uses a natural composite PK
    (currency_code, security_label, price_date), there is no ID gap.
    GMP provides all PK fields, so this is a straightforward UPSERT.

    currency_code enrichment:
      GMP does not always send currency_code in the equity price feed.
      When it is blank/null we enrich from cis_security_kudu.currency_code
      (matched on security_name = security_label).  If the security is also
      not yet in the security master the row is still written with
      currency_code = '' so it is not silently dropped, but it will show
      as a disabled row on the equity price list page until the security sync
      populates the master and the next equity price sync run enriches it.
    """

    now_ms = int(datetime.now().timestamp() * 1000)

    # Step 1: Read staging data
    stg_df = (
        spark.read
        .format("kudu")
        .option("kudu.master", kudu_master)
        .option("kudu.table", IMPALA_STAGING_TABLE)
        .load()
    )

    if batch_id:
        stg_df = stg_df.filter(F.col("etl_batch_id") == batch_id)

    record_count = stg_df.count()
    print(f"[INFO] Staging equity price records: {record_count}")

    if record_count == 0:
        print("[INFO] No staging records found. Nothing to merge.")
        return

    # Step 1b: Read security master for currency enrichment.
    #
    # The staging SQL (ingestion_commands.txt) joins:
    #   gmp_cis_sta_dly_equity_prices.security = gmp_cis_sta_dly_security.security_label
    # But eq.security holds the security FULL NAME (e.g. "YNSMK 7 1/2 PERP"),
    # while gmp_cis_sta_dly_security.security_label is the short code — they don't match,
    # so the LEFT JOIN returns NULL and currency_code lands blank in cis_equity_price.
    #
    # Fix: in our PySpark merge we enrich currency_code by joining cis_security_kudu
    # on security_name (full name) = security_label (from equity price staging).
    # This mirrors what the staging SQL intended but couldn't achieve with security_label.
    sec_df = (
        spark.read
        .format("kudu")
        .option("kudu.master", kudu_master)
        .option("kudu.table", IMPALA_SECURITY_TABLE)
        .load()
        .select(
            F.col("security_name").alias("sec_security_name"),
            F.col("currency_code").alias("sec_currency_code"),
        )
    )
    print(f"[INFO] Security master records for currency lookup: {sec_df.count()}")

    # Step 2: LEFT JOIN on security_name (full name) = security_label
    # COALESCE: GMP-provided currency first → security master fallback → '' last resort
    enriched_df = (
        stg_df
        .join(sec_df, stg_df["security_label"] == sec_df["sec_security_name"], how="left")
        .withColumn(
            "resolved_currency_code",
            F.when(
                F.col("currency_code").isNotNull() & (F.trim(F.col("currency_code")) != ""),
                F.col("currency_code")
            ).otherwise(
                F.coalesce(F.col("sec_currency_code"), F.lit(""))
            )
        )
    )

    missing_ccy = enriched_df.filter(
        F.col("resolved_currency_code").isNull() | (F.trim(F.col("resolved_currency_code")) == "")
    ).count()
    if missing_ccy > 0:
        print(f"[WARN] {missing_ccy} equity price records have no currency_code "
              f"(not in GMP feed and not in security master) — written with blank currency.")

    # Step 3: Build target records
    target_df = (
        enriched_df
        .select(
            # PK fields — use enriched currency_code
            F.col("resolved_currency_code").alias("currency_code"),
            F.col("security_label"),
            F.col("price_date"),
            # Business fields
            F.col("isin"),
            F.col("main_closing_price"),
            F.col("price_timestamp"),
        )
        .withColumn("src_system", F.lit("GMP"))
        .withColumn("is_active", F.lit(True))
        .withColumn("created_by", F.lit("GMP_ETL"))
        .withColumn("created_at", F.lit(now_ms))
        .withColumn("updated_by", F.lit("GMP_ETL"))
        .withColumn("updated_at", F.lit(now_ms))
    )

    print(f"[INFO] Records to UPSERT: {target_df.count()} (missing_ccy={missing_ccy})")

    if dry_run:
        print("[DRY RUN] Preview of records to write:")
        target_df.show(20, truncate=False)
        return

    # Step 3: UPSERT into target Kudu table
    # Kudu UPSERT: insert new rows, update existing rows by PK match
    (
        target_df.write
        .format("kudu")
        .option("kudu.master", kudu_master)
        .option("kudu.table", IMPALA_TARGET_TABLE)
        .option("kudu.operation", "upsert")
        .mode("append")
        .save()
    )

    print(f"[SUCCESS] Upserted {record_count} equity price records into {TARGET_TABLE}")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    args = parse_args()

    spark = create_spark_session()

    try:
        merge_equity_prices(
            spark,
            kudu_master=args.kudu_master,
            batch_id=args.batch_id,
            dry_run=args.dry_run,
        )
    except Exception as e:
        print(f"[ERROR] Merge failed: {e}")
        raise
    finally:
        spark.stop()
