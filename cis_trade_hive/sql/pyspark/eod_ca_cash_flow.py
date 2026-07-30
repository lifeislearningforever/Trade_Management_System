"""
PySpark EOD Job: Corporate Action → Cash Flow Pipeline
=======================================================

Runs as a standalone edgenode job via Control-M (no Django dependency).

Two-step pipeline:
  Step 1 — Sync GMP CAs
    Read gmp_cis_sfa_dly_corporate_action
    → map GMP types to CIS types
    → UPSERT into cis_corporate_actions (src_system='GMP', status='VALIDATED')
    → UPSERT into cis_ca_cash_flow_queue (status='PENDING')

  Step 2 — Generate Cash Flows (EOD processing)
    Read PENDING queue entries
    → join with cis_trade_position to find portfolios holding the security
    → calculate amount_fc = quantity × price
    → lookup FX rate from cis_fx_rate for amount_lc
    → UPSERT into cis_cash_flow
    → mark queue entry COMPLETED

Control-M usage (edgenode):
  spark-submit --master yarn \\
    --conf spark.executor.memory=4g \\
    --conf spark.executor.cores=2 \\
    --conf spark.dynamicAllocation.enabled=true \\
    eod_ca_cash_flow.py \\
    --kudu-master kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251 \\
    --processing-date 2026-01-30 \\
    --run-by CONTROL-M

Optional flags:
    --dry-run              Preview without writing
    --step1-only           Only sync GMP CAs (skip cash flow generation)
    --step2-only           Only process queue (skip GMP sync)
    --processing-date      Filter GMP records by processing_date (YYYYMMDD)

Author: CisTrade Team
Created: 2026-04-11
"""

import argparse
import time
from datetime import datetime

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import LongType, StringType, DecimalType
import os


# ============================================================================
# Configuration
# ============================================================================

DATABASE = os.environ.get('IMPALA_DB', 'gmp_cis')

# GMP source (read-only — written by GMP ETL)
GMP_CA_TABLE        = f"impala::{DATABASE}.gmp_cis_sfa_dly_corporate_action"

# CIS target tables
CA_TABLE            = f"impala::{DATABASE}.cis_corporate_actions"
CA_QUEUE_TABLE      = f"impala::{DATABASE}.cis_ca_cash_flow_queue"
CASH_FLOW_TABLE     = f"impala::{DATABASE}.cis_cash_flow"
POSITION_TABLE      = f"impala::{DATABASE}.cis_trade_position"
FX_RATE_TABLE       = f"impala::{DATABASE}.cis_fx_rate"
PORTFOLIO_TABLE     = f"impala::{DATABASE}.cis_portfolio"


# ============================================================================
# GMP CA type → CIS CA type mapping
# ============================================================================

GMP_TYPE_MAP = {
    "cash dividend":        "DIVIDEND",
    "dividend":             "DIVIDEND",
    "div":                  "DIVIDEND",
    "d":                    "DIVIDEND",
    "special dividend":     "SPECIAL_DIVIDEND",
    "special div":          "SPECIAL_DIVIDEND",
    "interest":             "INTEREST",
    "i":                    "INTEREST",
    "coupon":               "COUPON",
    "coupon payment":       "COUPON",
    "c":                    "COUPON",
    "roc":                  "ROC",
    "return of capital":    "ROC",
    "capital distribution": "CAPITAL_DISTRIBUTION",
    "bonus issue":          "BONUS_ISSUE",
    "bonus":                "BONUS_ISSUE",
    "b":                    "BONUS_ISSUE",
    "stock split":          "STOCK_SPLIT",
    "split":                "SPLIT",
    "s":                    "SPLIT",
    "reverse split":        "REVERSE_SPLIT",
    "consolidation":        "CONSOLIDATION",
    "rights issue":         "RIGHTS_ISSUE",
    "rights entitlement":   "RIGHTS_ENTITLEMENT",
    "rights":               "RIGHTS_ENTITLEMENT",
    "warrant":              "WARRANT_ENTITLEMENT",
    "warrant entitlement":  "WARRANT_ENTITLEMENT",
    # GMP specific codes
    "clas sp":              "SPECIAL_DIVIDEND",
}

# CA types that generate cash flows
CASH_FLOW_CA_TYPES = {
    "DIVIDEND", "SPECIAL_DIVIDEND", "INTEREST", "COUPON", "ROC", "CAPITAL_DISTRIBUTION"
}

# CA type → Cash flow type
CA_TO_CF_TYPE = {
    "DIVIDEND":             "DIVIDEND",
    "SPECIAL_DIVIDEND":     "SPECIAL_DIVIDEND",
    "INTEREST":             "INTEREST",
    "COUPON":               "COUPON",
    "ROC":                  "ROC",
    "CAPITAL_DISTRIBUTION": "CAPITAL_DISTRIBUTION",
}


# ============================================================================
# Helpers
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(description="EOD Corporate Action → Cash Flow pipeline")
    parser.add_argument("--kudu-master",      required=True, help="Kudu master addresses")
    parser.add_argument("--processing-date",  default=None,  help="GMP processing_date filter (YYYYMMDD or YYYY-MM-DD)")
    parser.add_argument("--run-by",           default="CONTROL-M", help="Job runner identity for audit")
    parser.add_argument("--dry-run",          action="store_true",  help="Preview without writing")
    parser.add_argument("--step1-only",       action="store_true",  help="Only run Step 1: GMP CA sync")
    parser.add_argument("--step2-only",       action="store_true",  help="Only run Step 2: cash flow generation")
    return parser.parse_args()


def create_spark_session() -> SparkSession:
    return (
        SparkSession.builder
        .appName("CIS_EOD_CA_CashFlow")
        .config("spark.sql.shuffle.partitions", "16")
        .config("spark.sql.adaptive.enabled", "true")
        .getOrCreate()
    )


def kudu_read(spark: SparkSession, kudu_master: str, table: str) -> DataFrame:
    return (
        spark.read
        .format("kudu")
        .option("kudu.master", kudu_master)
        .option("kudu.table", table)
        .load()
    )


def kudu_upsert(df: DataFrame, kudu_master: str, table: str):
    (
        df.write
        .format("kudu")
        .option("kudu.master", kudu_master)
        .option("kudu.table", table)
        .option("kudu.operation", "upsert")
        .mode("append")
        .save()
    )


def now_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


def normalise_date(col_name: str) -> F.Column:
    """
    Try multiple GMP date formats → unified YYYY-MM-DD string.
    GMP delivers dates as DD/MM/YYYY, YYYYMMDD integers, or YYYY-MM-DD.
    """
    return (
        F.when(
            F.col(col_name).rlike(r"^\d{8}$"),
            F.date_format(F.to_date(F.col(col_name).cast(StringType()), "yyyyMMdd"), "yyyy-MM-dd")
        ).when(
            F.col(col_name).rlike(r"^\d{2}/\d{2}/\d{4}$"),
            F.date_format(F.to_date(F.col(col_name), "dd/MM/yyyy"), "yyyy-MM-dd")
        ).otherwise(
            F.date_format(F.to_date(F.col(col_name)), "yyyy-MM-dd")
        )
    )


# ============================================================================
# Step 1: Sync GMP CAs into cis_corporate_actions + cis_ca_cash_flow_queue
# ============================================================================

def step1_sync_gmp_ca(spark: SparkSession, kudu_master: str, processing_date: str,
                      run_by: str, dry_run: bool):
    print("\n" + "=" * 70)
    print("  STEP 1: Sync GMP Corporate Actions")
    print("=" * 70)

    # -- Read GMP source table --
    gmp_df = kudu_read(spark, kudu_master, GMP_CA_TABLE)

    if processing_date:
        pd_norm = processing_date.replace("-", "")   # YYYYMMDD
        gmp_df = gmp_df.filter(
            F.col("processing_date").cast(StringType()) == pd_norm
        )

    raw_count = gmp_df.count()
    print(f"[STEP1] GMP records read       : {raw_count}")
    if raw_count == 0:
        print("[STEP1] No GMP records found for this date. Skipping.")
        return

    # -- Map GMP type → CIS type using a Spark UDF --
    gmp_type_map_broadcast = spark.sparkContext.broadcast(GMP_TYPE_MAP)

    @F.udf(StringType())
    def map_ca_type(gmp_type):
        if not gmp_type:
            return None
        return gmp_type_map_broadcast.value.get(gmp_type.strip().lower())

    # -- Build ca_number = GMP-<ca_id> --
    # Use ca_number as dedup key
    gmp_mapped = (
        gmp_df
        .withColumn("ca_number",   F.concat(F.lit("GMP-"), F.col("ca_id").cast(StringType())))
        .withColumn("cis_ca_type", map_ca_type(F.col("ca_type")))
        .withColumn("ex_date_str", normalise_date("ex_date"))
        .withColumn("record_date_str", normalise_date("record_date"))
        .withColumn("payment_date_str", normalise_date("payment_date"))
        .withColumn("announcement_date_str", normalise_date("announcement_date"))
        .filter(F.col("cis_ca_type").isNotNull())   # drop unmapped types
    )

    unmapped = raw_count - gmp_mapped.count()
    if unmapped > 0:
        print(f"[STEP1] Skipped (unmapped type) : {unmapped}")

    # -- Exclude already-synced ca_numbers --
    existing_df = (
        kudu_read(spark, kudu_master, CA_TABLE)
        .filter(F.col("src_system") == "GMP")
        .select("ca_number")
    )
    new_cas = gmp_mapped.join(existing_df, on="ca_number", how="left_anti")
    new_count = new_cas.count()
    print(f"[STEP1] New CAs to insert       : {new_count}")

    if new_count == 0:
        print("[STEP1] All GMP records already synced. Nothing to do.")
        return

    ts = now_ms()

    # -- Build cis_corporate_actions rows --
    # ca_id: timestamp_ms + monotonically_increasing_id to ensure uniqueness across partitions
    ca_rows = (
        new_cas
        .withColumn("_row_id", F.monotonically_increasing_id())
        .withColumn("ca_id",
            (F.lit(ts).cast(LongType()) + F.col("_row_id").cast(LongType()))
        )
        .select(
            F.col("ca_id"),
            F.col("ca_number"),
            F.col("cis_ca_type").alias("ca_type"),
            F.col("security").alias("security_name"),
            F.col("announcement_date_str").alias("announcement_date"),
            F.col("ex_date_str").alias("ex_date"),
            F.col("record_date_str").alias("record_date"),
            F.col("payment_date_str").alias("payment_date"),
            F.col("price").cast(DecimalType(30, 8)).alias("price"),
            F.lit(None).cast(StringType()).alias("currency"),       # GMP has no currency col
            F.lit("GMP").alias("src_system"),
            F.lit("VALIDATED").alias("status"),                     # pre-validated upstream
            F.lit(True).alias("is_active"),
            F.lit(False).alias("is_deleted"),
            F.lit(run_by).alias("created_by"),
            F.lit(ts).cast(LongType()).alias("created_at"),
            F.lit(run_by).alias("updated_by"),
            F.lit(ts).cast(LongType()).alias("updated_at"),
        )
    )

    if dry_run:
        print("[DRY RUN] cis_corporate_actions rows that would be inserted:")
        ca_rows.show(10, truncate=False)
    else:
        kudu_upsert(ca_rows, kudu_master, CA_TABLE)
        print(f"[STEP1] ✓ Inserted {new_count} rows into cis_corporate_actions")

    # -- Build cis_ca_cash_flow_queue rows (only for cash-flow-generating types) --
    cf_types_list = list(CASH_FLOW_CA_TYPES)
    queue_rows = (
        ca_rows
        .filter(F.col("ca_type").isin(cf_types_list))
        .withColumn("queue_id",
            (F.lit(ts + 1).cast(LongType()) + F.monotonically_increasing_id().cast(LongType()))
        )
        .select(
            F.col("queue_id"),
            F.col("ca_id"),
            F.col("ca_number"),
            F.col("ca_type"),
            F.col("security_name"),
            F.col("ex_date"),
            F.col("record_date"),
            F.col("payment_date"),
            F.col("price"),
            F.col("currency"),
            F.lit("PENDING").alias("status"),
            F.lit(0).cast(LongType()).alias("retry_count"),
            F.lit(None).cast(StringType()).alias("error_message"),
            F.lit(0).cast(LongType()).alias("cash_flows_created"),
            F.lit(None).cast(DecimalType(30, 8)).alias("total_amount"),
            F.lit(None).cast(LongType()).alias("processed_at"),
            F.lit(ts).cast(LongType()).alias("created_at"),
            F.lit(run_by).alias("created_by"),
        )
    )

    q_count = queue_rows.count()
    if dry_run:
        print(f"[DRY RUN] cis_ca_cash_flow_queue rows that would be inserted ({q_count}):")
        queue_rows.show(10, truncate=False)
    else:
        if q_count > 0:
            kudu_upsert(queue_rows, kudu_master, CA_QUEUE_TABLE)
            print(f"[STEP1] ✓ Queued {q_count} CAs for cash flow processing")
        else:
            print("[STEP1] No cash-flow-type CAs in this batch (position adjustment types only)")


# ============================================================================
# Step 2: Process PENDING queue → generate cash flows
# ============================================================================

def step2_generate_cash_flows(spark: SparkSession, kudu_master: str,
                               run_by: str, dry_run: bool):
    print("\n" + "=" * 70)
    print("  STEP 2: Generate Cash Flows from CA Queue")
    print("=" * 70)

    ts = now_ms()

    # -- Read PENDING queue entries --
    queue_df = (
        kudu_read(spark, kudu_master, CA_QUEUE_TABLE)
        .filter(
            (F.col("status") == "PENDING") &
            (F.col("retry_count") < 3)
        )
    )
    q_count = queue_df.count()
    print(f"[STEP2] Pending queue entries   : {q_count}")
    if q_count == 0:
        print("[STEP2] No pending queue entries. Nothing to process.")
        return

    # -- Read positions: latest open position per portfolio+security --
    # Join with portfolio table to get portfolio base currency
    positions_raw = (
        kudu_read(spark, kudu_master, POSITION_TABLE)
        .filter(
            (F.col("quantity") > 0) &
            (F.col("status") == "OPEN") &
            (F.col("is_active") == True) &
            (F.col("position_basis") == "TRADED")    # use trade-date basis for CA holdings
        )
    )

    # Latest position per portfolio+security
    w = Window.partitionBy("portfolio_short_name", "security_label").orderBy(F.col("position_date").desc())
    latest_positions = (
        positions_raw
        .withColumn("_rn", F.row_number().over(w))
        .filter(F.col("_rn") == 1)
        .drop("_rn")
        .select(
            "portfolio_short_name",
            "security_label",
            "quantity",
            F.coalesce(F.col("security_currency"), F.col("foreign_ccy")).alias("security_currency"),
            F.coalesce(F.col("portfolio_currency"), F.col("local_ccy")).alias("portfolio_currency"),
        )
    )

    # -- Join queue with positions on security_name --
    holdings = (
        queue_df
        .join(
            latest_positions,
            queue_df["security_name"] == latest_positions["security_label"],
            how="inner"
        )
        .filter(F.col("quantity") > 0)
    )

    holdings_count = holdings.count()
    print(f"[STEP2] Portfolio holdings found: {holdings_count}")
    if holdings_count == 0:
        print("[STEP2] No holdings match queued CAs. Marking queue entries completed with 0 CFs.")
        if not dry_run:
            _mark_queue_completed(queue_df, spark, kudu_master, ts, run_by, cash_flows_created=0)
        return

    # -- Compute amount_fc = quantity × price --
    holdings = holdings.withColumn(
        "amount_fc",
        (F.col("quantity").cast(DecimalType(30, 8)) * F.col("price").cast(DecimalType(30, 8)))
        .cast(DecimalType(30, 8))
    )

    # -- FX rate lookup for amount_lc --
    # Get latest FX rate where from_currency=security_currency, to_currency=portfolio_currency
    fx_df = (
        kudu_read(spark, kudu_master, FX_RATE_TABLE)
        .select(
            F.col("from_currency"),
            F.col("to_currency"),
            F.col("rate").cast(DecimalType(30, 8)).alias("fx_rate"),
            F.col("rate_date"),
        )
    )

    # Latest rate per pair
    w_fx = Window.partitionBy("from_currency", "to_currency").orderBy(F.col("rate_date").desc())
    latest_fx = (
        fx_df
        .withColumn("_rn", F.row_number().over(w_fx))
        .filter(F.col("_rn") == 1)
        .drop("_rn")
        .select("from_currency", "to_currency", "fx_rate")
    )

    # Join holdings with FX rates
    with_fx = (
        holdings
        .join(
            latest_fx,
            (holdings["security_currency"] == latest_fx["from_currency"]) &
            (holdings["portfolio_currency"] == latest_fx["to_currency"]),
            how="left"
        )
        .withColumn(
            "fx_rate_used",
            F.coalesce(F.col("fx_rate"), F.lit(1.0).cast(DecimalType(30, 8)))
        )
        .withColumn(
            "amount_lc",
            (F.col("amount_fc") * F.col("fx_rate_used")).cast(DecimalType(30, 8))
        )
    )

    # -- Map CA type → CF type --
    ca_cf_map = spark.sparkContext.broadcast(CA_TO_CF_TYPE)

    @F.udf(StringType())
    def get_cf_type(ca_type):
        return ca_cf_map.value.get(ca_type, ca_type)

    # -- Build cash flow rows --
    cf_rows = (
        with_fx
        .withColumn("_row_id", F.monotonically_increasing_id())
        .withColumn("cash_flow_id",
            (F.lit(ts + 2).cast(LongType()) + F.col("_row_id").cast(LongType()))
        )
        .withColumn(
            "cash_flow_number",
            F.concat(
                F.lit("CF-"),
                F.date_format(F.current_date(), "yyyyMMdd"),
                F.lit("-"),
                F.lpad(F.col("_row_id").cast(StringType()), 5, "0")
            )
        )
        .withColumn("cf_type", get_cf_type(F.col("ca_type")))
        .withColumn(
            "dividend_price",
            F.when(
                F.col("quantity") > 0,
                (F.col("amount_fc") / F.col("quantity").cast(DecimalType(30, 8))).cast(DecimalType(30, 8))
            ).otherwise(F.lit(0).cast(DecimalType(30, 8)))
        )
        .select(
            F.col("cash_flow_id"),
            F.col("cash_flow_number"),
            F.col("portfolio_short_name"),
            F.col("security_label"),
            F.col("cf_type").alias("cash_flow_type"),
            F.lit("RECEIVE").alias("send_receive"),
            F.lit(False).alias("cf_processed"),
            # Foreign currency (security currency)
            F.col("security_currency").alias("foreign_ccy"),
            F.col("amount_fc").alias("foreign_ccy_amt"),
            # Local currency (portfolio currency)
            F.col("portfolio_currency").alias("local_ccy"),
            F.col("amount_lc").alias("local_ccy_amt"),
            F.col("amount_lc").alias("flow_amount_local"),
            F.col("dividend_price"),
            F.col("quantity").cast(DecimalType(30, 8)),
            F.col("fx_rate_used").alias("fx_rate"),
            # Dates
            F.col("ex_date").alias("value_date"),
            F.col("ex_date"),
            F.col("record_date"),
            F.col("payment_date"),
            F.col("record_date").alias("dividend_date"),
            # CA reference
            F.col("ca_id").cast(LongType()),
            F.col("ca_number"),
            # Status: CA-generated CFs are auto-validated
            F.lit("VALIDATED").alias("status"),
            F.lit("CA").alias("src_system"),
            # Audit
            F.lit(True).alias("is_active"),
            F.lit(False).alias("is_deleted"),
            F.lit(run_by).alias("created_by"),
            F.lit(ts).cast(LongType()).alias("created_at"),
            F.lit(run_by).alias("updated_by"),
            F.lit(ts).cast(LongType()).alias("updated_at"),
        )
    )

    cf_count = cf_rows.count()
    print(f"[STEP2] Cash flows to create    : {cf_count}")

    if dry_run:
        print("[DRY RUN] Sample cash flow rows that would be created:")
        cf_rows.show(10, truncate=False)
        return

    # -- Deduplicate: skip if CF already exists for same portfolio+security+ex_date --
    existing_cfs = (
        kudu_read(spark, kudu_master, CASH_FLOW_TABLE)
        .filter(
            (F.col("src_system") == "CA") &
            (F.col("is_deleted") == False)
        )
        .select("portfolio_short_name", "security_label", "ex_date")
        .withColumnRenamed("portfolio_short_name", "_ex_pf")
        .withColumnRenamed("security_label", "_ex_sec")
        .withColumnRenamed("ex_date", "_ex_date")
    )

    new_cfs = (
        cf_rows
        .join(
            existing_cfs,
            (cf_rows["portfolio_short_name"] == existing_cfs["_ex_pf"]) &
            (cf_rows["security_label"] == existing_cfs["_ex_sec"]) &
            (cf_rows["ex_date"] == existing_cfs["_ex_date"]),
            how="left_anti"
        )
    )

    final_count = new_cfs.count()
    skipped = cf_count - final_count
    if skipped > 0:
        print(f"[STEP2] Skipped (already exist) : {skipped}")
    print(f"[STEP2] Net new cash flows      : {final_count}")

    if final_count > 0:
        kudu_upsert(new_cfs, kudu_master, CASH_FLOW_TABLE)
        print(f"[STEP2] ✓ Created {final_count} cash flows in cis_cash_flow")

    # -- Mark queue entries COMPLETED --
    _mark_queue_completed(queue_df, spark, kudu_master, ts, run_by,
                          cash_flows_created=final_count)


def _mark_queue_completed(queue_df: DataFrame, spark: SparkSession,
                          kudu_master: str, ts: int, run_by: str,
                          cash_flows_created: int):
    """Update all processed queue entries to COMPLETED."""
    completed = (
        queue_df
        .select("queue_id", "ca_id", "ca_number", "ca_type", "security_name",
                "ex_date", "record_date", "payment_date", "price", "currency",
                "retry_count", "created_at", "created_by")
        .withColumn("status",              F.lit("COMPLETED"))
        .withColumn("error_message",       F.lit(None).cast(StringType()))
        .withColumn("cash_flows_created",  F.lit(cash_flows_created).cast(LongType()))
        .withColumn("total_amount",        F.lit(None).cast(DecimalType(30, 8)))
        .withColumn("processed_at",        F.lit(ts).cast(LongType()))
    )
    kudu_upsert(completed, kudu_master, CA_QUEUE_TABLE)
    print(f"[STEP2] ✓ Marked {queue_df.count()} queue entries as COMPLETED")


# ============================================================================
# Main
# ============================================================================

def main():
    args = parse_args()

    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    kudu_master = args.kudu_master
    processing_date = args.processing_date
    run_by = args.run_by
    dry_run = args.dry_run

    print("\n" + "=" * 70)
    print("  CIS Trade Hive — EOD Corporate Action → Cash Flow Pipeline")
    print("=" * 70)
    print(f"  Started         : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Run by          : {run_by}")
    print(f"  Processing date : {processing_date or 'all pending'}")
    print(f"  Kudu master     : {kudu_master}")
    if dry_run:
        print("  Mode            : DRY RUN (no writes)")
    print("=" * 70)

    try:
        if not args.step2_only:
            step1_sync_gmp_ca(spark, kudu_master, processing_date, run_by, dry_run)

        if not args.step1_only:
            step2_generate_cash_flows(spark, kudu_master, run_by, dry_run)

        print(f"\n[DONE] Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
