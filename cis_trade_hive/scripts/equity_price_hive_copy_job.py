"""
Daily ETL: cis_equity_price (Kudu) → hive_cis_equity_price (Hive)

Logic:
  1. DEDUPLICATE — cis_equity_price can have multiple rows per
     (security_label, price_date) from different src_system or edits.
     Keep only the latest by price_timestamp DESC.

  2. CARRY-FORWARD — For each security, pick the most recent price_date
     that is <= processing_date. If ABC has a price on 27-Apr but none on
     28th/29th/30th, the 27-Apr price is written into all three partitions
     (original price_date is kept so downstream knows the actual price date).

Usage:
  spark-submit \\
    --master yarn --deploy-mode cluster \\
    --archives hdfs://sitnameservice1/cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env \\
    --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3 \\
    --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3 \\
    --conf spark.pyspark.python=./cis_etl_env/bin/python3 \\
    equity_price_hive_copy_job.py --processing-date 20260430

  Omit --processing-date to default to today.
"""

import argparse
import sys
import logging
from datetime import datetime, date

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description='Equity price Kudu→Hive copy job')
    parser.add_argument(
        '--processing-date',
        default=None,
        help='Run date as YYYYMMDD (default: today)',
    )
    return parser.parse_args()


def to_date_fmt(yyyymmdd: str) -> str:
    """'20260430' → '2026-04-30'"""
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def main():
    args = parse_args()
    processing_date = args.processing_date or date.today().strftime('%Y%m%d')
    processing_date_fmt = to_date_fmt(processing_date)

    logger.info(f"=== Equity Price Hive Copy Job ===")
    logger.info(f"Processing date : {processing_date} ({processing_date_fmt})")

    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    spark = (
        SparkSession.builder
        .appName(f"CIS_EquityPrice_HiveCopy_{processing_date}")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .enableHiveSupport()
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    logger.info(f"[DRIVER] Python: {sys.executable}")
    logger.info(f"Spark version : {spark.version}")

    SOURCE_TABLE = "gmp_cis.cis_equity_price"
    TARGET_TABLE = "gmp_cis.hive_cis_equity_price"
    HDFS_BASE    = "/mrw/cis/hive/cis_equity_price"

    # -------------------------------------------------------------------------
    # 1. Read source — only records with price_date <= processing_date
    # -------------------------------------------------------------------------
    logger.info(f"Reading {SOURCE_TABLE} where price_date <= {processing_date_fmt} ...")

    raw_df = spark.sql(f"""
        SELECT
            currency_code,
            security_label,
            price_date,
            isin,
            main_closing_price,
            price_timestamp,
            src_system,
            is_active,
            created_by,
            created_at,
            updated_by,
            updated_at
        FROM {SOURCE_TABLE}
        WHERE is_active = true
          AND CAST(REPLACE(price_date, '-', '') AS INT)
              <= CAST('{processing_date}' AS INT)
    """)

    raw_count = raw_df.count()
    logger.info(f"Raw rows from source : {raw_count}")

    if raw_count == 0:
        logger.warning("No source rows found — nothing to write. Exiting.")
        spark.stop()
        return

    # -------------------------------------------------------------------------
    # 2. Deduplicate: one row per (security_label, price_date)
    #    Multiple rows exist when GMP + CIS both wrote for the same date,
    #    or when a user edited the price (price_timestamp changes each edit).
    #    Keep the latest by price_timestamp DESC.
    # -------------------------------------------------------------------------
    w_dedup = Window.partitionBy("security_label", "price_date") \
                    .orderBy(F.col("price_timestamp").desc())

    deduped_df = (
        raw_df
        .withColumn("rn_dedup", F.row_number().over(w_dedup))
        .filter(F.col("rn_dedup") == 1)
        .drop("rn_dedup")
    )

    deduped_count = deduped_df.count()
    logger.info(f"After dedup (one row per security+price_date): {deduped_count}")

    # -------------------------------------------------------------------------
    # 3. Carry-forward: one record per security
    #    Among all deduplicated dates per security, pick the most recent
    #    price_date (which is <= processing_date by the WHERE above).
    #    This is the carry-forward: if no price for today, last known is used.
    # -------------------------------------------------------------------------
    w_latest = Window.partitionBy("security_label") \
                     .orderBy(F.col("price_date").desc(), F.col("price_timestamp").desc())

    final_df = (
        deduped_df
        .withColumn("rn_latest", F.row_number().over(w_latest))
        .filter(F.col("rn_latest") == 1)
        .drop("rn_latest")
    )

    final_count = final_df.count()
    logger.info(f"Final rows to write (one per security): {final_count}")

    # Log carry-forward stats
    carried = final_df.filter(F.col("price_date") < F.lit(processing_date_fmt)).count()
    fresh   = final_count - carried
    logger.info(f"  Fresh prices (price_date = today)  : {fresh}")
    logger.info(f"  Carried-forward (price_date < today): {carried}")

    # -------------------------------------------------------------------------
    # 4. Ensure Hive partition exists for processing_date
    # -------------------------------------------------------------------------
    partition_path = f"{HDFS_BASE}/processing_date={processing_date}"
    logger.info(f"Adding Hive partition: {partition_path}")

    spark.sql(f"""
        ALTER TABLE {TARGET_TABLE}
        ADD IF NOT EXISTS PARTITION (processing_date='{processing_date}')
        LOCATION '{partition_path}'
    """)

    # -------------------------------------------------------------------------
    # 5. Write — INSERT OVERWRITE makes the job re-runnable (idempotent)
    # -------------------------------------------------------------------------
    logger.info(f"Writing {final_count} rows to {TARGET_TABLE} partition={processing_date} ...")

    final_df.createOrReplaceTempView("equity_price_final")

    spark.sql(f"""
        INSERT OVERWRITE TABLE {TARGET_TABLE}
        PARTITION (processing_date='{processing_date}')
        SELECT
            currency_code,
            security_label,
            price_date,
            isin,
            main_closing_price,
            price_timestamp,
            src_system,
            is_active,
            created_by,
            created_at,
            updated_by,
            updated_at
        FROM equity_price_final
    """)

    # -------------------------------------------------------------------------
    # 6. Verify
    # -------------------------------------------------------------------------
    verify_df = spark.sql(f"""
        SELECT
            src_system,
            COUNT(*) AS securities_written,
            MIN(price_date) AS oldest_price_date,
            MAX(price_date) AS newest_price_date
        FROM {TARGET_TABLE}
        WHERE processing_date = '{processing_date}'
        GROUP BY src_system
        ORDER BY src_system
    """)
    logger.info("=== Verification — rows written ===")
    verify_df.show(truncate=False)

    # Carry-forward spot-check
    carryforward_df = spark.sql(f"""
        SELECT
            security_label,
            price_date AS last_known_price_date,
            main_closing_price,
            src_system,
            DATEDIFF(TO_DATE('{processing_date_fmt}'), TO_DATE(price_date)) AS days_carried
        FROM {TARGET_TABLE}
        WHERE processing_date = '{processing_date}'
          AND price_date < '{processing_date_fmt}'
        ORDER BY days_carried DESC, security_label
        LIMIT 20
    """)
    logger.info("=== Carry-forward spot-check (price_date < today) ===")
    carryforward_df.show(truncate=False)

    logger.info("=== Job complete ===")
    spark.stop()


if __name__ == "__main__":
    main()
