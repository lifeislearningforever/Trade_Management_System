"""
PySpark Trade Data Ingestion: Hive to Kudu
==========================================

Purpose: Read trade records from Hive table and insert into Kudu cis_trade table
         Handles NULL values gracefully for all columns

Features:
- Reads from Hive source table with 250,000+ records
- Handles NULL portfolio, security, and other columns gracefully
- Generates unique trade_id using timestamp + row number
- Batch processing for performance
- Configurable batch size and parallelism
- Comprehensive logging and error handling
- Supports both full load and incremental load

Usage:
    spark-submit --master yarn \
        --deploy-mode cluster \
        --conf spark.executor.memory=4g \
        --conf spark.driver.memory=2g \
        ingest_trade_hive_to_kudu.py \
        --source-table gmp_cis.cis_trade_hive \
        --target-table gmp_cis.cis_trade \
        --batch-size 5000

Author: Claude Code
Date: 2026-01-16
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, LongType,
    DecimalType, BooleanType, IntegerType
)
from pyspark.sql.window import Window
import argparse
import logging
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TradeHiveToKuduIngestion:
    """
    PySpark job to ingest trade data from Hive to Kudu.
    Handles NULL values gracefully across all columns.
    """

    # Kudu master addresses (configure based on environment)
    KUDU_MASTERS = "kudu-master-1:7051,kudu-master-2:7051,kudu-master-3:7051"

    # Default values for required fields when NULL
    DEFAULT_VALUES = {
        'trade_type': 'UNKNOWN',
        'portfolio_short_name': 'UNKNOWN',
        'security_label': 'UNKNOWN',
        'trade_date': '1900-01-01',
        'status': 'INITIAL',
        'src_system': 'GMP',
        'is_active': False,
        'is_deleted': False,
    }

    # Column mappings: source column -> target column (if different)
    # Use None for columns that don't exist in source
    COLUMN_MAPPINGS = {
        # These are auto-generated
        'trade_id': None,  # Will be generated

        # Core fields - map from source or use defaults
        'trade_type': 'trade_type',
        'deal_number': 'deal_number',
        'portfolio_short_name': 'portfolio_short_name',
        'portfolio_full_name': 'portfolio_full_name',
        'security_label': 'security_label',
        'security_full_name': 'security_full_name',
        'security_type': 'security_type',
        'trade_status': 'trade_status',
        'trade_date': 'trade_date',
        'settle_date': 'settle_date',
        'expiry_date': 'expiry_date',

        # Numeric fields
        'quantity': 'quantity',
        'face_value': 'face_value',
        'lot': 'lot',
        'price': 'price',
        'commission': 'commission',
        'accrued_interest': 'accrued_interest',
        'sec_fee': 'sec_fee',
        'other_charges': 'other_charges',
        'total_amount': 'total_amount',

        # Additional fields
        'open_close_position': 'open_close_position',
        'extension': 'extension',
        'brokers': 'brokers',
        'broker_name': 'broker_name',
        'gl_fund_type': 'gl_fund_type',
        'gl_cost_centre': 'gl_cost_centre',
        'gl_account_code': 'gl_account_code',
        'contract_ref': 'contract_ref',
        'fd_receipt': 'fd_receipt',
        'org_pur_date': 'org_pur_date',
        'open_fx_rate': 'open_fx_rate',
        'curr_dealing': 'curr_dealing',
        'open_dealing': 'open_dealing',
        'input_tax_oth': 'input_tax_oth',
        'qty_entitled': 'qty_entitled',
        'selling_rule': 'selling_rule',
        'cash_balance': 'cash_balance',
        'custodian': 'custodian',
        'amor_accr_method': 'amor_accr_method',
        'lots_held': 'lots_held',
        'quantity_held': 'quantity_held',
        'remarks': 'remarks',

        # UDF fields
        'udf_fund_type': 'udf_fund_type',
        'udf_section_31_26': 'udf_section_31_26',
        'udf_sub_custodian': 'udf_sub_custodian',
        'udf_disclosure_req': 'udf_disclosure_req',
        'udf_counter_pledged': 'udf_counter_pledged',
        'udf_revision_code': 'udf_revision_code',
        'udf_uobn_uobn_hk': 'udf_uobn_uobn_hk',
        'udf_income_exp_type': 'udf_income_exp_type',
        'udf_currency_hedge': 'udf_currency_hedge',

        # Trade type specific fields
        'realized_pnl': 'realized_pnl',
        'parent_trade_id': 'parent_trade_id',
        'delivery_type': 'delivery_type',
        'counterparty': 'counterparty',
        'reduction_type': 'reduction_type',
        'reduction_amount': 'reduction_amount',
        'units_affected': 'units_affected',
        'income_type': 'income_type',
        'ex_date': 'ex_date',
        'record_date': 'record_date',
        'pay_date': 'pay_date',
        'amount_per_unit': 'amount_per_unit',
        'gross_amount': 'gross_amount',
        'withholding_tax': 'withholding_tax',
        'net_amount': 'net_amount',
        'split_type': 'split_type',
        'split_ratio_new': 'split_ratio_new',
        'split_ratio_old': 'split_ratio_old',
        'effective_date': 'effective_date',

        # Workflow fields
        'status': 'status',
        'is_active': 'is_active',
        'is_deleted': 'is_deleted',
        'src_system': 'src_system',

        # Audit fields
        'created_by': 'created_by',
        'created_at': 'created_at',
        'updated_by': 'updated_by',
        'updated_at': 'updated_at',
        'submitted_by': 'submitted_by',
        'submitted_at': 'submitted_at',
        'validated_by': 'validated_by',
        'validated_at': 'validated_at',
        'validation_comments': 'validation_comments',
        'settled_by': 'settled_by',
        'settled_at': 'settled_at',
        'settlement_comments': 'settlement_comments',
        'cancelled_by': 'cancelled_by',
        'cancelled_at': 'cancelled_at',
        'cancel_reason': 'cancel_reason',
        'internal_ref': 'internal_ref',
        'external_ref': 'external_ref',
    }

    # Numeric columns (DECIMAL type)
    NUMERIC_COLUMNS = [
        'quantity', 'face_value', 'lot', 'price', 'commission',
        'accrued_interest', 'sec_fee', 'other_charges', 'total_amount',
        'open_fx_rate', 'curr_dealing', 'open_dealing', 'input_tax_oth',
        'qty_entitled', 'cash_balance', 'lots_held', 'quantity_held',
        'realized_pnl', 'reduction_amount', 'units_affected',
        'amount_per_unit', 'gross_amount', 'withholding_tax', 'net_amount'
    ]

    # Boolean columns
    BOOLEAN_COLUMNS = [
        'is_active', 'is_deleted', 'udf_disclosure_req',
        'udf_counter_pledged', 'udf_currency_hedge'
    ]

    # Integer columns
    INTEGER_COLUMNS = ['split_ratio_new', 'split_ratio_old']

    # Long columns
    LONG_COLUMNS = ['trade_id', 'parent_trade_id']

    def __init__(self, spark: SparkSession, config: dict):
        """
        Initialize the ingestion job.

        Args:
            spark: SparkSession instance
            config: Configuration dictionary with source_table, target_table, etc.
        """
        self.spark = spark
        self.config = config
        self.source_table = config.get('source_table', 'gmp_cis.cis_trade_hive')
        self.target_table = config.get('target_table', 'gmp_cis.cis_trade')
        self.batch_size = config.get('batch_size', 5000)
        self.kudu_masters = config.get('kudu_masters', self.KUDU_MASTERS)

        # Generate base timestamp for trade_id generation
        self.base_timestamp = int(datetime.now().timestamp() * 1000)

        logger.info(f"Initialized ingestion: {self.source_table} -> {self.target_table}")
        logger.info(f"Batch size: {self.batch_size}")

    def get_source_columns(self) -> list:
        """Get list of columns available in source table."""
        try:
            df = self.spark.sql(f"DESCRIBE {self.source_table}")
            columns = [row['col_name'] for row in df.collect()
                      if not row['col_name'].startswith('#')]
            logger.info(f"Source table has {len(columns)} columns")
            return columns
        except Exception as e:
            logger.error(f"Error getting source columns: {str(e)}")
            return []

    def read_source_data(self, where_clause: str = None) -> 'DataFrame':
        """
        Read data from source Hive table.

        Args:
            where_clause: Optional WHERE clause for incremental load

        Returns:
            Spark DataFrame with source data
        """
        logger.info(f"Reading from source table: {self.source_table}")

        query = f"SELECT * FROM {self.source_table}"
        if where_clause:
            query += f" WHERE {where_clause}"

        df = self.spark.sql(query)
        count = df.count()
        logger.info(f"Read {count:,} records from source")

        return df

    def transform_data(self, df: 'DataFrame') -> 'DataFrame':
        """
        Transform source data for Kudu target.
        Handles NULL values, generates trade_id, applies defaults.

        Args:
            df: Source DataFrame

        Returns:
            Transformed DataFrame ready for Kudu
        """
        logger.info("Starting data transformation...")

        # Get source columns
        source_columns = df.columns
        logger.info(f"Source columns: {source_columns[:10]}...")  # Log first 10

        # Add row number for trade_id generation
        window_spec = Window.orderBy(F.monotonically_increasing_id())
        df = df.withColumn("_row_num", F.row_number().over(window_spec))

        # Generate unique trade_id: base_timestamp + row_number
        df = df.withColumn(
            "trade_id",
            (F.lit(self.base_timestamp) + F.col("_row_num")).cast(LongType())
        )

        # Process each column
        for target_col, source_col in self.COLUMN_MAPPINGS.items():
            if target_col == 'trade_id':
                continue  # Already generated

            # Check if source column exists
            if source_col and source_col in source_columns:
                # Map source column to target
                if target_col != source_col:
                    df = df.withColumnRenamed(source_col, target_col)
            else:
                # Column doesn't exist in source - add with default/NULL
                default_value = self.DEFAULT_VALUES.get(target_col)

                if target_col in self.NUMERIC_COLUMNS:
                    df = df.withColumn(target_col, F.lit(default_value).cast(DecimalType(20, 6)))
                elif target_col in self.BOOLEAN_COLUMNS:
                    df = df.withColumn(target_col, F.lit(default_value if default_value is not None else False))
                elif target_col in self.INTEGER_COLUMNS:
                    df = df.withColumn(target_col, F.lit(default_value).cast(IntegerType()))
                elif target_col in self.LONG_COLUMNS:
                    df = df.withColumn(target_col, F.lit(default_value).cast(LongType()))
                else:
                    df = df.withColumn(target_col, F.lit(default_value))

        # Apply default values for NULL required fields
        for col_name, default_value in self.DEFAULT_VALUES.items():
            if col_name in df.columns and default_value is not None:
                df = df.withColumn(
                    col_name,
                    F.when(F.col(col_name).isNull(), F.lit(default_value))
                     .otherwise(F.col(col_name))
                )

        # Handle NULL numeric columns - replace with 0
        for col_name in self.NUMERIC_COLUMNS:
            if col_name in df.columns:
                df = df.withColumn(
                    col_name,
                    F.when(F.col(col_name).isNull(), F.lit(0))
                     .otherwise(F.col(col_name))
                     .cast(DecimalType(20, 6))
                )

        # Handle NULL boolean columns - replace with False
        for col_name in self.BOOLEAN_COLUMNS:
            if col_name in df.columns:
                df = df.withColumn(
                    col_name,
                    F.when(F.col(col_name).isNull(), F.lit(False))
                     .otherwise(F.col(col_name))
                     .cast(BooleanType())
                )

        # Add audit fields if not present
        current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if 'created_by' not in df.columns or df.filter(F.col('created_by').isNull()).count() > 0:
            df = df.withColumn(
                'created_by',
                F.when(F.col('created_by').isNull(), F.lit('ETL_SYSTEM'))
                 .otherwise(F.col('created_by'))
            )

        if 'created_at' not in df.columns or df.filter(F.col('created_at').isNull()).count() > 0:
            df = df.withColumn(
                'created_at',
                F.when(F.col('created_at').isNull(), F.lit(current_timestamp))
                 .otherwise(F.col('created_at'))
            )

        if 'updated_by' not in df.columns or df.filter(F.col('updated_by').isNull()).count() > 0:
            df = df.withColumn(
                'updated_by',
                F.when(F.col('updated_by').isNull(), F.lit('ETL_SYSTEM'))
                 .otherwise(F.col('updated_by'))
            )

        if 'updated_at' not in df.columns or df.filter(F.col('updated_at').isNull()).count() > 0:
            df = df.withColumn(
                'updated_at',
                F.when(F.col('updated_at').isNull(), F.lit(current_timestamp))
                 .otherwise(F.col('updated_at'))
            )

        # Ensure src_system is set
        df = df.withColumn(
            'src_system',
            F.when(F.col('src_system').isNull(), F.lit('GMP'))
             .otherwise(F.col('src_system'))
        )

        # Drop temporary columns
        df = df.drop("_row_num")

        # Select only target columns in correct order
        target_columns = list(self.COLUMN_MAPPINGS.keys())
        existing_cols = [c for c in target_columns if c in df.columns]
        df = df.select(existing_cols)

        logger.info(f"Transformation complete. Output columns: {len(existing_cols)}")
        return df

    def write_to_kudu(self, df: 'DataFrame') -> int:
        """
        Write transformed data to Kudu table.

        Args:
            df: Transformed DataFrame

        Returns:
            Number of records written
        """
        logger.info(f"Writing to Kudu table: {self.target_table}")

        total_count = df.count()
        logger.info(f"Total records to write: {total_count:,}")

        try:
            # Write to Kudu using Impala (UPSERT mode)
            df.write \
                .format("kudu") \
                .option("kudu.master", self.kudu_masters) \
                .option("kudu.table", self.target_table) \
                .option("kudu.operation", "upsert") \
                .mode("append") \
                .save()

            logger.info(f"Successfully wrote {total_count:,} records to Kudu")
            return total_count

        except Exception as e:
            logger.error(f"Error writing to Kudu: {str(e)}")

            # Fallback: Write via Impala SQL
            logger.info("Attempting fallback write via Impala SQL...")
            return self.write_via_impala(df)

    def write_via_impala(self, df: 'DataFrame') -> int:
        """
        Fallback method: Write to Kudu via Impala INSERT statements.
        Uses batch processing for large datasets.

        Args:
            df: Transformed DataFrame

        Returns:
            Number of records written
        """
        logger.info("Using Impala SQL fallback for Kudu write...")

        # Register DataFrame as temp view
        df.createOrReplaceTempView("trade_staging")

        # Insert in batches
        total_count = df.count()
        written = 0

        try:
            # Use INSERT INTO with SELECT
            insert_query = f"""
                INSERT INTO {self.target_table}
                SELECT * FROM trade_staging
            """

            self.spark.sql(insert_query)
            written = total_count
            logger.info(f"Impala SQL write complete: {written:,} records")

        except Exception as e:
            logger.error(f"Impala SQL write failed: {str(e)}")
            # Continue with batch processing as last resort
            written = self.write_batched(df)

        return written

    def write_batched(self, df: 'DataFrame') -> int:
        """
        Write data in smaller batches for reliability.

        Args:
            df: DataFrame to write

        Returns:
            Number of records written
        """
        logger.info(f"Starting batched write with batch_size={self.batch_size}")

        total_count = df.count()
        written = 0
        batch_num = 0

        # Add batch column
        df = df.withColumn("_batch_id",
            (F.monotonically_increasing_id() / self.batch_size).cast(IntegerType()))

        max_batch = df.agg(F.max("_batch_id")).collect()[0][0]

        for batch_id in range(max_batch + 1):
            batch_num += 1
            batch_df = df.filter(F.col("_batch_id") == batch_id).drop("_batch_id")
            batch_count = batch_df.count()

            try:
                batch_df.write \
                    .format("kudu") \
                    .option("kudu.master", self.kudu_masters) \
                    .option("kudu.table", self.target_table) \
                    .option("kudu.operation", "upsert") \
                    .mode("append") \
                    .save()

                written += batch_count
                logger.info(f"Batch {batch_num}: Wrote {batch_count:,} records "
                           f"({written:,}/{total_count:,})")

            except Exception as e:
                logger.error(f"Batch {batch_num} failed: {str(e)}")
                continue

        return written

    def run(self, incremental_column: str = None, last_value: str = None) -> dict:
        """
        Execute the full ingestion pipeline.

        Args:
            incremental_column: Column for incremental load (e.g., 'created_at')
            last_value: Last processed value for incremental load

        Returns:
            Dictionary with execution statistics
        """
        start_time = time.time()

        stats = {
            'source_table': self.source_table,
            'target_table': self.target_table,
            'start_time': datetime.now().isoformat(),
            'source_count': 0,
            'written_count': 0,
            'status': 'FAILED',
            'error': None
        }

        try:
            # Build where clause for incremental load
            where_clause = None
            if incremental_column and last_value:
                where_clause = f"{incremental_column} > '{last_value}'"
                logger.info(f"Incremental load: {where_clause}")

            # Read source data
            source_df = self.read_source_data(where_clause)
            stats['source_count'] = source_df.count()

            if stats['source_count'] == 0:
                logger.info("No records to process")
                stats['status'] = 'SUCCESS'
                return stats

            # Transform data
            transformed_df = self.transform_data(source_df)

            # Write to Kudu
            stats['written_count'] = self.write_to_kudu(transformed_df)

            stats['status'] = 'SUCCESS'

        except Exception as e:
            logger.error(f"Ingestion failed: {str(e)}")
            stats['error'] = str(e)
            stats['status'] = 'FAILED'

        finally:
            end_time = time.time()
            stats['end_time'] = datetime.now().isoformat()
            stats['duration_seconds'] = round(end_time - start_time, 2)

            logger.info("=" * 60)
            logger.info("INGESTION SUMMARY")
            logger.info("=" * 60)
            for key, value in stats.items():
                logger.info(f"  {key}: {value}")
            logger.info("=" * 60)

        return stats


def create_spark_session(app_name: str = "TradeHiveToKuduIngestion") -> SparkSession:
    """
    Create and configure SparkSession for Kudu operations.

    Args:
        app_name: Application name for Spark

    Returns:
        Configured SparkSession
    """
    return SparkSession.builder \
        .appName(app_name) \
        .config("spark.sql.hive.metastore.version", "2.1.1") \
        .config("spark.sql.hive.metastore.jars", "maven") \
        .enableHiveSupport() \
        .getOrCreate()


def main():
    """Main entry point for the ingestion job."""

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Ingest trade data from Hive to Kudu'
    )
    parser.add_argument(
        '--source-table',
        default='gmp_cis.cis_trade_hive',
        help='Source Hive table (default: gmp_cis.cis_trade_hive)'
    )
    parser.add_argument(
        '--target-table',
        default='gmp_cis.cis_trade',
        help='Target Kudu table (default: gmp_cis.cis_trade)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=5000,
        help='Batch size for writing (default: 5000)'
    )
    parser.add_argument(
        '--kudu-masters',
        default='kudu-master-1:7051,kudu-master-2:7051,kudu-master-3:7051',
        help='Kudu master addresses'
    )
    parser.add_argument(
        '--incremental-column',
        default=None,
        help='Column for incremental load (e.g., created_at)'
    )
    parser.add_argument(
        '--last-value',
        default=None,
        help='Last processed value for incremental load'
    )

    args = parser.parse_args()

    # Create Spark session
    logger.info("Creating Spark session...")
    spark = create_spark_session()

    try:
        # Configuration
        config = {
            'source_table': args.source_table,
            'target_table': args.target_table,
            'batch_size': args.batch_size,
            'kudu_masters': args.kudu_masters,
        }

        # Create and run ingestion
        ingestion = TradeHiveToKuduIngestion(spark, config)
        stats = ingestion.run(
            incremental_column=args.incremental_column,
            last_value=args.last_value
        )

        # Exit with appropriate code
        if stats['status'] == 'SUCCESS':
            logger.info("Ingestion completed successfully!")
            exit(0)
        else:
            logger.error("Ingestion failed!")
            exit(1)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
