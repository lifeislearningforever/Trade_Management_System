"""
PySpark Job: Merge GMP Security Data into cis_security
=======================================================

Problem solved:
  The old approach generated security_id from a millisecond timestamp at
  insert time.  Because the ETL deleted all GMP rows and reinserted them every
  day, every GMP security received a brand-new ID on each run.  Downstream
  systems treat ID changes as data changes, causing false "updates".

Solution — Registry-based stable IDs:
  A permanent lookup table (cis_security_id_registry) maps each security's
  natural key to a fixed 12-digit numeric ID that is allocated exactly once
  and never changes.

  Natural key priority:
    1. ISIN  (globally unique — preferred)
    2. security_name + exchange_code  (for unlisted / OTC without ISIN)
    3. security_name alone            (last resort)

  On each ETL run:
    - Rows whose natural key is already in the registry  → reuse stored ID
    - Rows whose natural key is new                      → allocate next ID,
      write to registry, then write to cis_security

  No truncate-and-reload needed.  Pure UPSERT on cis_security means:
    - GMP rows are updated in place
    - CIS rows (src_system='CIS') are never touched by this job

ID range:
  100_000_000_001 – 999_999_999_999  (12 digits)
  Legacy timestamp IDs are 13 digits (1_700_000_000_000+) — no collision.

Tables:
  Read  : gmp_cis.stg_gmp_security_kudu   (staging, daily feed)
  Read  : gmp_cis.cis_security_id_registry (stable ID ledger — Kudu)
  Read  : gmp_cis.cis_security_id_counter  (next-ID counter — Kudu)
  Write : gmp_cis.cis_security_kudu        (live security master — Kudu)
  Write : gmp_cis.cis_security_id_registry (new entries only)
  Write : gmp_cis.cis_security_id_counter  (updated next_id)

Usage:
  spark-submit merge_gmp_security.py \\
    --kudu-master kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251 \\
    --batch-id BATCH_20260603_001

  For local Docker:
  spark-submit merge_gmp_security.py --kudu-master localhost:7051

Author: CisTrade Team
Created: 2026-02-02
Updated: 2026-06-02  — registry-based stable ID (no more truncate-reload)
"""

import argparse
from datetime import datetime

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window
import os


# ============================================================================
# Configuration
# ============================================================================

DATABASE = os.environ.get('IMPALA_DB', 'gmp_cis')

# Kudu table names (used by PySpark Kudu connector)
KUDU_SECURITY      = f"impala::{DATABASE}.cis_security_kudu"
KUDU_STAGING       = f"impala::{DATABASE}.stg_gmp_security_kudu"
KUDU_REGISTRY      = f"impala::{DATABASE}.cis_security_id_registry"
KUDU_COUNTER       = f"impala::{DATABASE}.cis_security_id_counter"

# 12-digit ID floor — IDs start at 100_000_000_001
ID_FLOOR = 100_000_000_000


# ============================================================================
# Helpers
# ============================================================================

def parse_args():
    p = argparse.ArgumentParser(description="Merge GMP security data into cis_security")
    p.add_argument("--kudu-master", required=True,
                   help="Kudu master addresses e.g. host1:7051,host2:7151")
    p.add_argument("--batch-id", default=None,
                   help="Filter staging to a specific ETL batch")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview without writing")
    return p.parse_args()


def create_spark_session():
    return (
        SparkSession.builder
        .appName("CIS_Merge_GMP_Security")
        .config("spark.sql.shuffle.partitions", "16")
        .getOrCreate()
    )


def kudu_read(spark, master: str, table: str) -> DataFrame:
    return (
        spark.read
        .format("kudu")
        .option("kudu.master", master)
        .option("kudu.table", table)
        .load()
    )


def kudu_upsert(df: DataFrame, master: str, table: str):
    (
        df.write
        .format("kudu")
        .option("kudu.master", master)
        .option("kudu.table", table)
        .option("kudu.operation", "upsert")
        .mode("append")
        .save()
    )


def build_natural_key(df: DataFrame) -> DataFrame:
    """
    Add `natural_key` and `key_type` columns to the staging dataframe.

    IMPORTANT — cross-listed securities:
      The same ISIN can represent different securities on different exchanges.
      Example: ANZ Banking Group is listed on both ASX (AU) and NZX (NZ) with
      the same ISIN.  They are distinct instruments (different currency, price,
      corporate actions).  ISIN alone is therefore NOT a unique natural key.

    Priority (first matching rule wins):
      1. ISIN + exchange_code          → "ISIN_EXCH:<isin>:<exch>"
      2. ISIN + country_of_exchange    → "ISIN_CTY:<isin>:<country>"
      3. ISIN only                     → "ISIN:<isin>"          (bonds, private)
      4. name + exchange_code          → "NAME_EXCH:<name>:<exch>"
      5. name + country_of_exchange    → "NAME_CTY:<name>:<country>"
      6. name only                     → "NAME:<name>"          (last resort)

    All components are upper-cased and trimmed for consistent matching.
    """
    isin_c  = F.upper(F.trim(F.col("isin")))
    name_c  = F.upper(F.trim(F.col("security_name")))
    exch_c  = F.upper(F.trim(F.coalesce(F.col("exchange_code"),       F.lit(""))))
    cty_c   = F.upper(F.trim(F.coalesce(F.col("country_of_exchange"), F.lit(""))))

    has_isin = F.col("isin").isNotNull()            & (F.trim(F.col("isin")) != "")
    has_exch = F.col("exchange_code").isNotNull()   & (F.trim(F.col("exchange_code")) != "")
    has_cty  = F.col("country_of_exchange").isNotNull() & (F.trim(F.col("country_of_exchange")) != "")

    natural_key = (
        F.when(has_isin & has_exch,
               F.concat(F.lit("ISIN_EXCH:"), isin_c, F.lit(":"), exch_c))
         .when(has_isin & has_cty,
               F.concat(F.lit("ISIN_CTY:"),  isin_c, F.lit(":"), cty_c))
         .when(has_isin,
               F.concat(F.lit("ISIN:"), isin_c))
         .when(has_exch,
               F.concat(F.lit("NAME_EXCH:"), name_c, F.lit(":"), exch_c))
         .when(has_cty,
               F.concat(F.lit("NAME_CTY:"),  name_c, F.lit(":"), cty_c))
         .otherwise(
               F.concat(F.lit("NAME:"), name_c))
    )

    key_type = (
        F.when(has_isin & has_exch, F.lit("ISIN_EXCH"))
         .when(has_isin & has_cty,  F.lit("ISIN_CTY"))
         .when(has_isin,            F.lit("ISIN"))
         .when(has_exch,            F.lit("NAME_EXCH"))
         .when(has_cty,             F.lit("NAME_CTY"))
         .otherwise(                F.lit("NAME"))
    )

    return df.withColumn("natural_key", natural_key) \
             .withColumn("key_type",    key_type)


# ============================================================================
# Main merge
# ============================================================================

def merge_securities(spark, kudu_master: str, batch_id=None, dry_run=False):
    now_ms = int(datetime.now().timestamp() * 1000)

    # ------------------------------------------------------------------
    # 1. Read staging data
    # ------------------------------------------------------------------
    stg_raw = kudu_read(spark, kudu_master, KUDU_STAGING)
    if batch_id:
        stg_raw = stg_raw.filter(F.col("etl_batch_id") == batch_id)

    stg_raw.cache()
    stg_count = stg_raw.count()
    if stg_count == 0:
        print("[INFO] No staging records — nothing to merge.")
        return
    print(f"[INFO] Staging records to process: {stg_count}")

    # ------------------------------------------------------------------
    # 2. Attach natural_key to each staging row
    # ------------------------------------------------------------------
    stg = build_natural_key(stg_raw)

    # ------------------------------------------------------------------
    # 3. Read the existing registry
    #    (small table — all security IDs ever allocated)
    # ------------------------------------------------------------------
    registry = kudu_read(spark, kudu_master, KUDU_REGISTRY) \
                   .select("natural_key", "security_id") \
                   .cache()
    print(f"[INFO] Registry entries: {registry.count()}")

    # ------------------------------------------------------------------
    # 4. Join staging against registry to split known / new
    # ------------------------------------------------------------------
    joined = stg.alias("stg").join(
        registry.alias("reg"),
        F.col("stg.natural_key") == F.col("reg.natural_key"),
        "left"
    )

    known_df = joined.filter(F.col("reg.security_id").isNotNull())
    new_df   = joined.filter(F.col("reg.security_id").isNull())

    known_count = known_df.count()
    print(f"[INFO] Known (registry hit):  {known_count}")
    print(f"[INFO] New   (no registry entry, pre-dedup): {new_df.count()}")

    # ------------------------------------------------------------------
    # 4b. ISIN dedup: for GMP "new" rows that have an ISIN, check whether
    #     cis_security_kudu already has a CIS row with the same ISIN.
    #     If so, skip — we do NOT create a duplicate GMP security record.
    #     The trade label (e.g. "ANET UN") resolves to the CIS security
    #     via the counterparty/security label mapping, not via a duplicate row.
    # ------------------------------------------------------------------
    existing_cis = kudu_read(spark, kudu_master, KUDU_SECURITY) \
        .filter(F.col("src_system") == "CIS") \
        .filter(F.col("isin").isNotNull() & (F.trim(F.col("isin")) != "")) \
        .select(F.upper(F.trim(F.col("isin"))).alias("cis_isin")) \
        .distinct() \
        .cache()

    cis_isin_count = existing_cis.count()
    print(f"[INFO] Existing CIS securities with ISIN: {cis_isin_count}")

    new_with_isin    = new_df.filter(
        F.col("stg.isin").isNotNull() & (F.trim(F.col("stg.isin")) != "")
    )
    new_without_isin = new_df.filter(
        F.col("stg.isin").isNull() | (F.trim(F.col("stg.isin")) == "")
    )

    # Anti-join: keep only GMP new rows whose ISIN does NOT exist in CIS
    new_isin_not_in_cis = new_with_isin.alias("gmp").join(
        existing_cis.alias("cis"),
        F.upper(F.trim(F.col("gmp.stg.isin"))) == F.col("cis.cis_isin"),
        "left_anti"
    )

    # GMP rows that duplicate a CIS ISIN — log and skip
    new_isin_duplicate_cis = new_with_isin.alias("gmp").join(
        existing_cis.alias("cis"),
        F.upper(F.trim(F.col("gmp.stg.isin"))) == F.col("cis.cis_isin"),
        "inner"
    )
    dup_count = new_isin_duplicate_cis.count()
    if dup_count > 0:
        print(f"[INFO] Skipping {dup_count} GMP security(ies) — ISIN already exists in CIS:")
        new_isin_duplicate_cis.select(
            F.col("stg.security_name"), F.col("stg.isin"), F.col("stg.exchange_code")
        ).show(50, truncate=False)

    # Recombine: truly-new = no ISIN match in CIS + records without ISIN
    new_df    = new_isin_not_in_cis.unionByName(new_without_isin)
    new_count = new_df.count()
    print(f"[INFO] New   (after CIS ISIN dedup): {new_count}")

    # ------------------------------------------------------------------
    # 5. Allocate IDs for new records
    #    Read the counter, calculate IDs, then write counter back.
    # ------------------------------------------------------------------
    new_registry_rows = None

    if new_count > 0:
        counter_df = kudu_read(spark, kudu_master, KUDU_COUNTER)
        current_next_id = counter_df.filter(F.col("counter_id") == 1) \
                                     .select("next_id") \
                                     .collect()[0]["next_id"]

        # Assign IDs: current_next_id, current_next_id+1, ...
        window = Window.orderBy("stg.natural_key")
        new_with_ids = new_df.withColumn(
            "security_id",
            (F.lit(current_next_id) + F.row_number().over(window) - 1).cast("long")
        )

        # Build new registry entries (append-only, src_system='GMP')
        new_registry_rows = new_with_ids.select(
            F.col("stg.natural_key"),
            F.col("security_id"),
            F.col("stg.key_type"),
            F.upper(F.trim(F.col("stg.isin"))).alias("isin"),
            F.col("stg.security_name"),
            F.col("stg.exchange_code"),
            F.col("stg.country_of_exchange"),
            F.lit("GMP").alias("src_system"),
            F.lit("GMP_ETL").alias("created_by"),
            F.lit(now_ms).alias("created_at"),
        )

        # Advance the counter
        updated_counter = spark.createDataFrame(
            [(1, current_next_id + new_count, now_ms)],
            ["counter_id", "next_id", "updated_at"]
        )

        if not dry_run:
            kudu_upsert(new_registry_rows, kudu_master, KUDU_REGISTRY)
            kudu_upsert(updated_counter,   kudu_master, KUDU_COUNTER)
            print(f"[INFO] Registry: added {new_count} new entries "
                  f"(IDs {current_next_id} – {current_next_id + new_count - 1})")

    # ------------------------------------------------------------------
    # 6. Build the final security records for cis_security
    #    Known rows use existing security_id from registry.
    #    New rows use freshly allocated security_id.
    # ------------------------------------------------------------------
    def build_security_record(df: DataFrame, id_col: str) -> DataFrame:
        """Select all cis_security columns from a joined staging dataframe."""
        return df.select(
            F.col(id_col).cast("long").alias("security_id"),
            F.col("stg.record_type"),
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
            F.col("stg.exchange_code"),
            F.col("stg.currency_code"),
            F.col("stg.price"),
            F.col("stg.shares_outstanding"),
            F.col("stg.beta"),
            F.col("stg.par_value"),
            F.col("stg.pct_hld_entity_1"),
            F.col("stg.pct_hld_entity_2"),
            F.col("stg.pct_hld_entity_3"),
            F.col("stg.pct_hld_entity_aggr"),
            F.col("stg.substantial_10_pct"),
            F.col("stg.cels"),
            F.col("stg.pevc_s32_devest"),
            F.col("stg.s32_representative"),
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
            F.lit("GMP").alias("src_system"),
            F.lit(True).alias("is_active"),
            F.lit("GMP_ETL").alias("created_by"),
            F.lit(now_ms).alias("created_at"),
            F.lit("GMP_ETL").alias("updated_by"),
            F.lit(now_ms).alias("updated_at"),
        )

    known_records = build_security_record(known_df, "reg.security_id")

    if new_count > 0:
        new_records = build_security_record(
            new_with_ids.alias("stg"),   # already has security_id column
            "security_id"
        )
        # new_with_ids uses "stg.*" alias so re-alias correctly
        new_records = new_with_ids.select(
            F.col("security_id").cast("long"),
            F.col("stg.record_type"),
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
            F.col("stg.exchange_code"),
            F.col("stg.currency_code"),
            F.col("stg.price"),
            F.col("stg.shares_outstanding"),
            F.col("stg.beta"),
            F.col("stg.par_value"),
            F.col("stg.pct_hld_entity_1"),
            F.col("stg.pct_hld_entity_2"),
            F.col("stg.pct_hld_entity_3"),
            F.col("stg.pct_hld_entity_aggr"),
            F.col("stg.substantial_10_pct"),
            F.col("stg.cels"),
            F.col("stg.pevc_s32_devest"),
            F.col("stg.s32_representative"),
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
            F.lit("GMP").alias("src_system"),
            F.lit(True).alias("is_active"),
            F.lit("GMP_ETL").alias("created_by"),
            F.lit(now_ms).alias("created_at"),
            F.lit("GMP_ETL").alias("updated_by"),
            F.lit(now_ms).alias("updated_at"),
        )
        final_df = known_records.unionByName(new_records)
    else:
        final_df = known_records

    total = final_df.count()
    print(f"[INFO] Total records to UPSERT into cis_security: {total}")

    # ------------------------------------------------------------------
    # 7. Dry-run preview
    # ------------------------------------------------------------------
    if dry_run:
        print("[DRY RUN] Sample of records to write:")
        final_df.select(
            "security_id", "isin", "security_name",
            "currency_code", "src_system"
        ).show(20, truncate=False)
        return

    # ------------------------------------------------------------------
    # 8. UPSERT into cis_security — no DELETE, CIS rows are untouched
    #    because the Kudu UPSERT only touches rows whose security_id
    #    matches what we send (all GMP IDs).
    # ------------------------------------------------------------------
    kudu_upsert(final_df, kudu_master, KUDU_SECURITY)

    print(f"[SUCCESS] Updated {known_count} + inserted {new_count} "
          f"GMP securities into cis_security")


# ============================================================================
# Entry point
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
