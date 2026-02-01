"""
PySpark Job: Merge GMP Security Data into CIS Security Table
=============================================================
Problem:
  - GMP ETL sends security data WITHOUT security_id (surrogate key)
  - CIS cis_security_kudu table requires security_id as PK (BIGINT)
  - Need to match on natural key (ISIN) and generate IDs for new records

Strategy:
  1. Read staging data from stg_gmp_security
  2. LEFT JOIN with cis_security_kudu on isin to find existing records
  3. For existing records: reuse their security_id (UPDATE via UPSERT)
  4. For new records: generate new security_id (timestamp-based)
  5. UPSERT all records into cis_security_kudu with src_system = 'GMP'

Usage:
  spark-submit --master yarn \
    --conf spark.executor.memory=4g \
    --conf spark.executor.cores=2 \
    merge_gmp_security.py \
    --kudu-master kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251 \
    --batch-id BATCH_20260202_001

For local Docker:
  spark-submit merge_gmp_security.py \
    --kudu-master localhost:7051 \
    --batch-id BATCH_20260202_001

Author: CisTrade Team
Created: 2026-02-02
"""

import argparse
import time
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window


# ============================================================================
# Configuration
# ============================================================================

DATABASE = "gmp_cis"
STAGING_TABLE = f"{DATABASE}.stg_gmp_security"
TARGET_TABLE = f"{DATABASE}.cis_security_kudu"
IMPALA_TARGET_TABLE = f"impala::{DATABASE}.cis_security_kudu"


def parse_args():
    parser = argparse.ArgumentParser(description="Merge GMP security data into CIS")
    parser.add_argument(
        "--kudu-master",
        required=True,
        help="Kudu master addresses (e.g., kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251)",
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
        .appName("CIS_Merge_GMP_Security")
        .config("spark.sql.shuffle.partitions", "16")
        .getOrCreate()
    )


def read_staging_data(spark, kudu_master, batch_id=None):
    """Read GMP security data from staging table."""
    df = (
        spark.read
        .format("kudu")
        .option("kudu.master", kudu_master)
        .option("kudu.table", IMPALA_TARGET_TABLE.replace("cis_security_kudu", "stg_gmp_security_kudu"))
        .load()
    )

    if batch_id:
        df = df.filter(F.col("etl_batch_id") == batch_id)

    print(f"[INFO] Staging records to process: {df.count()}")
    return df


def read_existing_securities(spark, kudu_master):
    """Read existing CIS securities for ISIN matching."""
    df = (
        spark.read
        .format("kudu")
        .option("kudu.master", kudu_master)
        .option("kudu.table", IMPALA_TARGET_TABLE)
        .load()
        .select("security_id", "isin")
        .filter(F.col("is_active") == True)
        .filter(F.col("isin").isNotNull())
    )

    print(f"[INFO] Existing CIS securities with ISIN: {df.count()}")
    return df


def generate_security_ids(df_new, start_id):
    """Generate timestamp-based security_id for new records.

    Uses a base timestamp + row_number to ensure unique IDs.
    This matches the CIS pattern: int(datetime.now().timestamp() * 1000)
    """
    window = Window.orderBy("isin")
    df_with_ids = df_new.withColumn(
        "security_id",
        F.lit(start_id) + F.row_number().over(window)
    )
    return df_with_ids


def merge_securities(spark, kudu_master, batch_id=None, dry_run=False):
    """Main merge logic."""

    now_ms = int(datetime.now().timestamp() * 1000)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Step 1: Read staging data
    stg_df = read_staging_data(spark, kudu_master, batch_id)

    if stg_df.count() == 0:
        print("[INFO] No staging records found. Nothing to merge.")
        return

    # Step 2: Read existing securities for ISIN lookup
    existing_df = read_existing_securities(spark, kudu_master)

    # Step 3: LEFT JOIN staging with existing on isin
    joined_df = stg_df.alias("stg").join(
        existing_df.alias("existing"),
        F.col("stg.isin") == F.col("existing.isin"),
        "left"
    )

    # Step 4: Split into updates (existing ISIN match) and inserts (new)
    updates_df = joined_df.filter(F.col("existing.security_id").isNotNull())
    inserts_df = joined_df.filter(F.col("existing.security_id").isNull())

    update_count = updates_df.count()
    insert_count = inserts_df.count()

    print(f"[INFO] Records to UPDATE (existing ISIN match): {update_count}")
    print(f"[INFO] Records to INSERT (new securities):      {insert_count}")

    # Step 5: Build UPDATE records (reuse existing security_id)
    update_records = (
        updates_df
        .select(
            F.col("existing.security_id").alias("security_id"),
            F.col("stg.security_name"),
            F.col("stg.isin"),
            F.col("stg.security_description"),
            F.col("stg.issuer"),
            F.col("stg.ticker"),
            F.col("stg.industry"),
            F.col("stg.security_type"),
            F.col("stg.investment_type"),
            F.col("stg.issuer_type"),
            F.col("stg.quoted_unquoted"),
            F.col("stg.country_of_incorporation"),
            F.col("stg.country_of_exchange"),
            F.col("stg.country_of_issue"),
            F.col("stg.country_of_primary_exchange"),
            F.col("stg.exchange_code"),
            F.col("stg.currency_code"),
            F.col("stg.price"),
            F.col("stg.price_date"),
            F.col("stg.price_source"),
            F.col("stg.shares_outstanding"),
            F.col("stg.beta"),
            F.col("stg.par_value"),
            F.col("stg.shareholding_entity_1"),
            F.col("stg.shareholding_entity_2"),
            F.col("stg.shareholding_entity_3"),
            F.col("stg.shareholding_aggregated"),
            F.col("stg.substantial_10_pct"),
            F.col("stg.bwciif"),
            F.col("stg.bwciif_others"),
            F.col("stg.cels"),
            F.col("stg.approved_s32"),
            F.col("stg.basel_iv_fund"),
            F.col("stg.mas_643_entity_type"),
            F.col("stg.mas_6d_code"),
            F.col("stg.fin_nonfin_ind"),
            F.col("stg.business_unit_head"),
            F.col("stg.person_in_charge"),
            F.col("stg.core_noncore"),
            F.col("stg.fund_index_fund"),
            F.col("stg.management_limit_classification"),
            F.col("stg.relative_index"),
        )
        .withColumn("src_system", F.lit("GMP"))
        .withColumn("is_active", F.lit(True))
        .withColumn("created_by", F.lit("GMP_ETL"))
        .withColumn("created_at", F.lit(now_ms))
        .withColumn("updated_by", F.lit("GMP_ETL"))
        .withColumn("updated_at", F.lit(now_ms))
    )

    # Step 6: Build INSERT records (generate new security_id)
    insert_records = None
    if insert_count > 0:
        new_records_base = (
            inserts_df
            .select(
                F.col("stg.security_name"),
                F.col("stg.isin"),
                F.col("stg.security_description"),
                F.col("stg.issuer"),
                F.col("stg.ticker"),
                F.col("stg.industry"),
                F.col("stg.security_type"),
                F.col("stg.investment_type"),
                F.col("stg.issuer_type"),
                F.col("stg.quoted_unquoted"),
                F.col("stg.country_of_incorporation"),
                F.col("stg.country_of_exchange"),
                F.col("stg.country_of_issue"),
                F.col("stg.country_of_primary_exchange"),
                F.col("stg.exchange_code"),
                F.col("stg.currency_code"),
                F.col("stg.price"),
                F.col("stg.price_date"),
                F.col("stg.price_source"),
                F.col("stg.shares_outstanding"),
                F.col("stg.beta"),
                F.col("stg.par_value"),
                F.col("stg.shareholding_entity_1"),
                F.col("stg.shareholding_entity_2"),
                F.col("stg.shareholding_entity_3"),
                F.col("stg.shareholding_aggregated"),
                F.col("stg.substantial_10_pct"),
                F.col("stg.bwciif"),
                F.col("stg.bwciif_others"),
                F.col("stg.cels"),
                F.col("stg.approved_s32"),
                F.col("stg.basel_iv_fund"),
                F.col("stg.mas_643_entity_type"),
                F.col("stg.mas_6d_code"),
                F.col("stg.fin_nonfin_ind"),
                F.col("stg.business_unit_head"),
                F.col("stg.person_in_charge"),
                F.col("stg.core_noncore"),
                F.col("stg.fund_index_fund"),
                F.col("stg.management_limit_classification"),
                F.col("stg.relative_index"),
            )
            .withColumn("src_system", F.lit("GMP"))
            .withColumn("is_active", F.lit(True))
            .withColumn("created_by", F.lit("GMP_ETL"))
            .withColumn("created_at", F.lit(now_ms))
            .withColumn("updated_by", F.lit("GMP_ETL"))
            .withColumn("updated_at", F.lit(now_ms))
        )

        # Generate security_id: base_timestamp + row_number
        insert_records = generate_security_ids(new_records_base, now_ms)

    # Step 7: Union updates and inserts
    if insert_records is not None and insert_count > 0:
        # Ensure column order matches
        final_df = update_records.unionByName(insert_records)
    else:
        final_df = update_records

    print(f"[INFO] Total records to UPSERT: {final_df.count()}")

    if dry_run:
        print("[DRY RUN] Preview of records to write:")
        final_df.select(
            "security_id", "isin", "security_name", "currency_code", "src_system"
        ).show(20, truncate=False)
        return

    # Step 8: Write to target Kudu table via UPSERT
    (
        final_df.write
        .format("kudu")
        .option("kudu.master", kudu_master)
        .option("kudu.table", IMPALA_TARGET_TABLE)
        .option("kudu.operation", "upsert")
        .mode("append")
        .save()
    )

    print(f"[SUCCESS] Merged {update_count} updates + {insert_count} inserts into {TARGET_TABLE}")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    args = parse_args()

    spark = create_spark_session()

    try:
        merge_securities(
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
