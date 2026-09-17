"""
Simple PySpark Trade Ingestion: Hive to Kudu via Impala
======================================================

Purpose: Read trade records from Hive and insert into Kudu using Impala SQL.
         This version uses simple SQL INSERT statements instead of Kudu connector.
         Handles NULL values gracefully for all columns.

Features:
- No Kudu Spark connector required - uses Impala SQL
- Handles 250,000+ records with batch processing
- NULL-safe transformations for all columns
- Generates unique trade_id
- Progress tracking and logging

Usage (Cloudera CML):
    spark-submit ingest_trade_simple.py \
        --source-db gmp_source \
        --source-table trade_hive \
        --target-db gmp_cis \
        --target-table cis_trade

Author: Claude Code
Date: 2026-01-16
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType, BooleanType, LongType, IntegerType
from pyspark.sql.window import Window
import argparse
import logging
from datetime import datetime
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_spark_session():
    """Create Spark session with Hive support."""
    return SparkSession.builder \
        .appName("TradeHiveToKuduIngestion") \
        .config("spark.sql.hive.metastore.version", "2.1.1") \
        .enableHiveSupport() \
        .getOrCreate()


def get_safe_string_col(df, col_name, default=''):
    """Get column value with NULL safety for strings."""
    if col_name in df.columns:
        return F.coalesce(F.col(col_name), F.lit(default))
    return F.lit(default)


def get_safe_decimal_col(df, col_name, default=0):
    """Get column value with NULL safety for decimals."""
    if col_name in df.columns:
        return F.coalesce(F.col(col_name).cast(DecimalType(20, 6)), F.lit(default).cast(DecimalType(20, 6)))
    return F.lit(default).cast(DecimalType(20, 6))


def get_safe_boolean_col(df, col_name, default=False):
    """Get column value with NULL safety for booleans."""
    if col_name in df.columns:
        return F.coalesce(F.col(col_name).cast(BooleanType()), F.lit(default))
    return F.lit(default)


def get_safe_long_col(df, col_name, default=None):
    """Get column value with NULL safety for long integers."""
    if col_name in df.columns:
        return F.col(col_name).cast(LongType())
    return F.lit(default).cast(LongType())


def get_safe_int_col(df, col_name, default=None):
    """Get column value with NULL safety for integers."""
    if col_name in df.columns:
        return F.col(col_name).cast(IntegerType())
    return F.lit(default).cast(IntegerType())


def transform_trades(df, base_timestamp):
    """
    Transform source trade data with NULL-safe handling.

    Args:
        df: Source DataFrame
        base_timestamp: Base timestamp for trade_id generation

    Returns:
        Transformed DataFrame
    """
    logger.info(f"Transforming {df.count():,} records...")
    logger.info(f"Source columns: {df.columns}")

    current_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Generate unique trade_id
    window_spec = Window.orderBy(F.monotonically_increasing_id())
    df = df.withColumn("_row_num", F.row_number().over(window_spec))
    df = df.withColumn("trade_id", (F.lit(base_timestamp) + F.col("_row_num")).cast(LongType()))

    # Build transformed DataFrame with NULL-safe columns
    transformed = df.select(
        # Primary key
        F.col("trade_id"),

        # Core fields - use COALESCE for NULL safety
        F.coalesce(get_safe_string_col(df, 'trade_type'), F.lit('UNKNOWN')).alias('trade_type'),
        get_safe_string_col(df, 'deal_number', '').alias('deal_number'),

        # Portfolio & Security - allow NULL (many records have NULL)
        get_safe_string_col(df, 'portfolio_short_name', '').alias('portfolio_short_name'),
        get_safe_string_col(df, 'portfolio_full_name', '').alias('portfolio_full_name'),
        get_safe_string_col(df, 'security_label', '').alias('security_label'),
        get_safe_string_col(df, 'security_full_name', '').alias('security_full_name'),
        get_safe_string_col(df, 'security_type', '').alias('security_type'),

        # Trade info
        get_safe_string_col(df, 'trade_status', '').alias('trade_status'),
        F.coalesce(get_safe_string_col(df, 'trade_date'), F.lit('1900-01-01')).alias('trade_date'),
        get_safe_string_col(df, 'settle_date', '').alias('settle_date'),
        get_safe_string_col(df, 'expiry_date', '').alias('expiry_date'),

        # Numeric fields - default to 0
        get_safe_decimal_col(df, 'quantity', 0).alias('quantity'),
        get_safe_decimal_col(df, 'face_value', 0).alias('face_value'),
        get_safe_decimal_col(df, 'lot', 0).alias('lot'),
        get_safe_decimal_col(df, 'price', 0).alias('price'),
        get_safe_decimal_col(df, 'commission', 0).alias('commission'),
        get_safe_decimal_col(df, 'accrued_interest', 0).alias('accrued_interest'),
        get_safe_decimal_col(df, 'sec_fee', 0).alias('sec_fee'),
        get_safe_decimal_col(df, 'other_charges', 0).alias('other_charges'),
        get_safe_decimal_col(df, 'total_amount', 0).alias('total_amount'),

        # GL & Accounting
        get_safe_string_col(df, 'open_close_position', '').alias('open_close_position'),
        get_safe_string_col(df, 'extension', '').alias('extension'),
        get_safe_string_col(df, 'brokers', '').alias('brokers'),
        get_safe_string_col(df, 'broker_name', '').alias('broker_name'),
        get_safe_string_col(df, 'gl_fund_type', '').alias('gl_fund_type'),
        get_safe_string_col(df, 'gl_cost_centre', '').alias('gl_cost_centre'),
        get_safe_string_col(df, 'gl_account_code', '').alias('gl_account_code'),
        get_safe_string_col(df, 'contract_ref', '').alias('contract_ref'),
        get_safe_string_col(df, 'fd_receipt', '').alias('fd_receipt'),

        # FX & Dealing
        get_safe_string_col(df, 'org_pur_date', '').alias('org_pur_date'),
        get_safe_decimal_col(df, 'open_fx_rate', 0).alias('open_fx_rate'),
        get_safe_decimal_col(df, 'curr_dealing', 0).alias('curr_dealing'),
        get_safe_decimal_col(df, 'open_dealing', 0).alias('open_dealing'),
        get_safe_decimal_col(df, 'input_tax_oth', 0).alias('input_tax_oth'),
        get_safe_decimal_col(df, 'qty_entitled', 0).alias('qty_entitled'),

        # Post-trade
        get_safe_string_col(df, 'selling_rule', '').alias('selling_rule'),
        get_safe_decimal_col(df, 'cash_balance', 0).alias('cash_balance'),
        get_safe_string_col(df, 'custodian', '').alias('custodian'),
        get_safe_string_col(df, 'amor_accr_method', '').alias('amor_accr_method'),
        get_safe_decimal_col(df, 'lots_held', 0).alias('lots_held'),
        get_safe_decimal_col(df, 'quantity_held', 0).alias('quantity_held'),
        get_safe_string_col(df, 'remarks', '').alias('remarks'),

        # UDF fields
        get_safe_string_col(df, 'udf_fund_type', '').alias('udf_fund_type'),
        get_safe_string_col(df, 'udf_section_31_26', '').alias('udf_section_31_26'),
        get_safe_string_col(df, 'udf_sub_custodian', '').alias('udf_sub_custodian'),
        get_safe_boolean_col(df, 'udf_disclosure_req', False).alias('udf_disclosure_req'),
        get_safe_boolean_col(df, 'udf_counter_pledged', False).alias('udf_counter_pledged'),
        get_safe_string_col(df, 'udf_revision_code', '').alias('udf_revision_code'),
        get_safe_string_col(df, 'udf_uobn_uobn_hk', '').alias('udf_uobn_uobn_hk'),
        get_safe_string_col(df, 'udf_income_exp_type', '').alias('udf_income_exp_type'),
        get_safe_boolean_col(df, 'udf_currency_hedge', False).alias('udf_currency_hedge'),

        # Trade type specific
        get_safe_decimal_col(df, 'realized_pnl', 0).alias('realized_pnl'),
        get_safe_long_col(df, 'parent_trade_id').alias('parent_trade_id'),
        get_safe_string_col(df, 'delivery_type', '').alias('delivery_type'),
        get_safe_string_col(df, 'counterparty', '').alias('counterparty'),
        get_safe_string_col(df, 'reduction_type', '').alias('reduction_type'),
        get_safe_decimal_col(df, 'reduction_amount', 0).alias('reduction_amount'),
        get_safe_decimal_col(df, 'units_affected', 0).alias('units_affected'),
        get_safe_string_col(df, 'income_type', '').alias('income_type'),
        get_safe_string_col(df, 'ex_date', '').alias('ex_date'),
        get_safe_string_col(df, 'record_date', '').alias('record_date'),
        get_safe_string_col(df, 'pay_date', '').alias('pay_date'),
        get_safe_decimal_col(df, 'amount_per_unit', 0).alias('amount_per_unit'),
        get_safe_decimal_col(df, 'gross_amount', 0).alias('gross_amount'),
        get_safe_decimal_col(df, 'withholding_tax', 0).alias('withholding_tax'),
        get_safe_decimal_col(df, 'net_amount', 0).alias('net_amount'),
        get_safe_string_col(df, 'split_type', '').alias('split_type'),
        get_safe_int_col(df, 'split_ratio_new').alias('split_ratio_new'),
        get_safe_int_col(df, 'split_ratio_old').alias('split_ratio_old'),
        get_safe_string_col(df, 'effective_date', '').alias('effective_date'),

        # Workflow status - with defaults
        F.coalesce(get_safe_string_col(df, 'status'), F.lit('SETTLED')).alias('status'),
        F.coalesce(get_safe_boolean_col(df, 'is_active'), F.lit(True)).alias('is_active'),
        F.coalesce(get_safe_boolean_col(df, 'is_deleted'), F.lit(False)).alias('is_deleted'),
        F.coalesce(get_safe_string_col(df, 'src_system'), F.lit('GMP')).alias('src_system'),

        # Audit fields
        F.coalesce(get_safe_string_col(df, 'created_by'), F.lit('ETL_SYSTEM')).alias('created_by'),
        F.coalesce(get_safe_string_col(df, 'created_at'), F.lit(current_ts)).alias('created_at'),
        F.coalesce(get_safe_string_col(df, 'updated_by'), F.lit('ETL_SYSTEM')).alias('updated_by'),
        F.coalesce(get_safe_string_col(df, 'updated_at'), F.lit(current_ts)).alias('updated_at'),

        # Workflow audit fields (nullable)
        get_safe_string_col(df, 'submitted_by', '').alias('submitted_by'),
        get_safe_string_col(df, 'submitted_at', '').alias('submitted_at'),
        get_safe_string_col(df, 'validated_by', '').alias('validated_by'),
        get_safe_string_col(df, 'validated_at', '').alias('validated_at'),
        get_safe_string_col(df, 'validation_comments', '').alias('validation_comments'),
        get_safe_string_col(df, 'settled_by', '').alias('settled_by'),
        get_safe_string_col(df, 'settled_at', '').alias('settled_at'),
        get_safe_string_col(df, 'settlement_comments', '').alias('settlement_comments'),
        get_safe_string_col(df, 'cancelled_by', '').alias('cancelled_by'),
        get_safe_string_col(df, 'cancelled_at', '').alias('cancelled_at'),
        get_safe_string_col(df, 'cancel_reason', '').alias('cancel_reason'),
        get_safe_string_col(df, 'internal_ref', '').alias('internal_ref'),
        get_safe_string_col(df, 'external_ref', '').alias('external_ref'),
    )

    logger.info(f"Transformation complete. Output columns: {len(transformed.columns)}")
    return transformed


def write_to_kudu_via_insert(spark, df, target_table, batch_size=10000):
    """
    Write DataFrame to Kudu using INSERT INTO via Impala.

    Args:
        spark: SparkSession
        df: Transformed DataFrame
        target_table: Target Kudu table name
        batch_size: Records per batch

    Returns:
        Number of records written
    """
    total = df.count()
    logger.info(f"Writing {total:,} records to {target_table} in batches of {batch_size:,}")

    # Register as temp view
    df.createOrReplaceTempView("trade_staging")

    try:
        # Try direct INSERT INTO (most efficient)
        logger.info("Attempting direct INSERT INTO...")

        insert_sql = f"""
            INSERT INTO TABLE {target_table}
            SELECT * FROM trade_staging
        """

        spark.sql(insert_sql)
        logger.info(f"Successfully inserted {total:,} records via direct INSERT")
        return total

    except Exception as e:
        logger.warning(f"Direct INSERT failed: {str(e)}")
        logger.info("Falling back to batched INSERT...")

        # Fallback: Batch processing
        written = 0
        batch_num = 0

        # Add batch ID
        df = df.withColumn("_batch_id",
            (F.monotonically_increasing_id() / batch_size).cast(IntegerType()))

        max_batch = df.agg(F.max("_batch_id")).collect()[0][0] or 0

        for batch_id in range(int(max_batch) + 1):
            batch_num += 1
            batch_df = df.filter(F.col("_batch_id") == batch_id).drop("_batch_id")
            batch_count = batch_df.count()

            if batch_count == 0:
                continue

            try:
                # Register batch as temp view
                batch_df.createOrReplaceTempView("batch_staging")

                spark.sql(f"""
                    INSERT INTO TABLE {target_table}
                    SELECT * FROM batch_staging
                """)

                written += batch_count
                logger.info(f"Batch {batch_num}: {batch_count:,} records ({written:,}/{total:,})")

            except Exception as batch_error:
                logger.error(f"Batch {batch_num} failed: {str(batch_error)}")
                continue

        return written


def main():
    parser = argparse.ArgumentParser(description='Ingest trade data from Hive to Kudu')
    parser.add_argument('--source-db', default='gmp_cis', help='Source database')
    parser.add_argument('--source-table', default='cis_trade_hive', help='Source table')
    parser.add_argument('--target-db', default='gmp_cis', help='Target database')
    parser.add_argument('--target-table', default='cis_trade', help='Target table')
    parser.add_argument('--batch-size', type=int, default=10000, help='Batch size')
    parser.add_argument('--limit', type=int, default=None, help='Limit records (for testing)')

    args = parser.parse_args()

    source_full = f"{args.source_db}.{args.source_table}"
    target_full = f"{args.target_db}.{args.target_table}"

    logger.info("=" * 70)
    logger.info("TRADE DATA INGESTION: Hive -> Kudu")
    logger.info("=" * 70)
    logger.info(f"Source: {source_full}")
    logger.info(f"Target: {target_full}")
    logger.info(f"Batch Size: {args.batch_size:,}")
    logger.info("=" * 70)

    start_time = time.time()

    # Create Spark session
    spark = create_spark_session()

    try:
        # Read source data
        logger.info(f"Reading from {source_full}...")

        query = f"SELECT * FROM {source_full}"
        if args.limit:
            query += f" LIMIT {args.limit}"

        source_df = spark.sql(query)
        source_count = source_df.count()
        logger.info(f"Read {source_count:,} records from source")

        if source_count == 0:
            logger.info("No records to process. Exiting.")
            return

        # Generate base timestamp for trade_id
        base_timestamp = int(datetime.now().timestamp() * 1000)

        # Transform data
        transformed_df = transform_trades(source_df, base_timestamp)

        # Write to Kudu
        written = write_to_kudu_via_insert(spark, transformed_df, target_full, args.batch_size)

        # Summary
        duration = time.time() - start_time

        logger.info("=" * 70)
        logger.info("INGESTION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Source Records: {source_count:,}")
        logger.info(f"Written Records: {written:,}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Rate: {written/duration:.0f} records/second" if duration > 0 else "N/A")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Ingestion failed: {str(e)}")
        raise

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
