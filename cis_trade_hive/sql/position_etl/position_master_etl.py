"""
Position Master ETL Job - PySpark Implementation
=================================================
Transforms 10 source tables (5 USER_UPLOAD + 5 AMS_STREET) into unified position_master table.

Source Systems:
- USER_UPLOAD (src_system='USER_UPLOAD'): user_upload_1 to user_upload_5
- AMS_STREET (src_system='AMS_STREET'): ams_street_1 to ams_street_5

Target: gmp_cis.position_master (Hive external table, Parquet format)

Usage:
    spark-submit --master yarn position_master_etl.py --processing-date 03032026

Author: CIS Trade Hive ETL Team
Date: 2026-03-03
"""

import argparse
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, lit, when, coalesce, current_timestamp,
    concat, trim, upper, lower, regexp_replace
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DecimalType, TimestampType
)
import uuid


# =============================================================================
# FIELD MAPPINGS: Source Field -> Master Field
# =============================================================================

# USER_UPLOAD_1 Mappings
USER_UPLOAD_1_MAPPING = {
    'portfolio': 'portfolio',
    'exchange_quoted': 'exchange',
    'isin_code': 'isin',
    'counter': 'security_full_name',
    'quantity_today': 'quantity',
    'trade_date': 'position_basis'
}

# USER_UPLOAD_2 Mappings
USER_UPLOAD_2_MAPPING = {
    'portfolio_name': 'portfolio',
    'stock_name': 'security_short_name',
    'security_description': 'security_full_name',
    'isin_code': 'isin',
    'qty_held': 'quantity',
    'shares_issued': 'shares_outstanding',
    'pct_holding': 'pct_holding',
    'country': 'country_of_exchange',
    'country_id': 'country_code',
    'trade_date': 'position_basis'
}

# USER_UPLOAD_3 Mappings
USER_UPLOAD_3_MAPPING = {
    'account_name': 'portfolio',
    'asset_description_short': 'security_short_name',
    'isin': 'isin',
    'shares_outstanding_total': 'quantity',
    'country_of_listing_code': 'country_code',
    'trade_date': 'position_basis'
}

# USER_UPLOAD_4 Mappings
USER_UPLOAD_4_MAPPING = {
    'portfolio': 'portfolio',
    'security_full_name': 'security_full_name',
    'product_type': 'product_type',
    'security_type': 'security_type',
    'quoted_unquoted': 'quoted_unquoted',
    'security_currency': 'security_currency',
    'quantity': 'quantity',
    'cost_fc': 'cost_fc',
    'net_book_value_fc': 'net_book_value_fc',
    'cost_lc': 'cost_lc',
    'pct_holdings': 'pct_holding',
    'no_of_shares_issues_by_the_company': 'shares_issued',
    'country_of_incorporation': 'country_of_incorporation',
    'country_of_exchange': 'country_of_exchange',
    'isin_code': 'isin',
    'ticker_code': 'ticker',
    'industry': 'industry',
    'financial_non_financial_co': 'fin_nonfin_co',
    'settled_date': 'position_basis'
}

# USER_UPLOAD_5 Mappings (most comprehensive)
USER_UPLOAD_5_MAPPING = {
    'reporting_date': 'reporting_date',
    'portfolio_name': 'portfolio',
    'security_full_name': 'security_full_name',
    'product_type': 'product_type',
    'security_type': 'security_type',
    'quoted_unquoted': 'quoted_unquoted',
    'security_currency_fc': 'security_currency',
    'quantity': 'quantity',
    'unit_avg_cost_unit_fc': 'average_cost',
    'market_price_unit_fc': 'market_price',
    'cost_fc': 'cost_fc',
    'unrealised_gain_loss_fc': 'unrealized_pnl_fc',
    'net_book_value_fc': 'net_book_value_fc',
    'market_value_fc': 'market_value_fc',
    'cost_lc': 'cost_lc',
    'provision_lc': 'provision_lc',
    'unrealised_gain_loss_lc': 'unrealized_pnl_lc',
    'net_book_value_lc': 'net_book_value_lc',
    'market_value_lc': 'market_value_lc',
    'corp_code': 'corp_code',
    'branch_code': 'branch_code',
    'cost_centre': 'cost_centre',
    'country_of_risk': 'country_of_risk',
    'country_of_operation': 'country_of_operation',
    'country_of_incorporation': 'country_of_incorporation',
    'country_of_exchange': 'country_of_exchange',
    'isin_code': 'isin',
    'ticker_code': 'ticker',
    'issuer_type': 'issuer_type',
    'reits_or_fund_y_n': 'reits_or_fund_y_n',
    'industry': 'industry',
    'no_of_shares_issues_by_the_company': 'shares_issued',
    'pct_holdings': 'pct_holding',
    'cels_code': 'cels',
    'bwcif_number_sg': 'bwcif_sg',
    'mas_6d_code_sg': 'mas_6d_code_sg',
    'bwcif_number_overseas': 'bwcif_ovs',
    'mas_6d_code_overseas': 'mas_6d_code_ovs',
    'settled_date': 'position_basis'
}

# AMS_STREET_1 Mappings
AMS_STREET_1_MAPPING = {
    'portfolio': 'portfolio',
    'security_name': 'security_full_name',
    'isin': 'isin',
    'price': 'market_price',
    'units': 'quantity',
    'country_code': 'country_code',
    'trade_date': 'position_basis'
}

# AMS_STREET_2 Mappings
AMS_STREET_2_MAPPING = {
    'portfolio_code': 'portfolio',
    'security_name': 'security_full_name',
    'isin': 'isin',
    'quantity': 'quantity',
    'country_code': 'country_code',
    'trade_date': 'position_basis'
}

# AMS_STREET_3 Mappings
AMS_STREET_3_MAPPING = {
    'portfolio_code': 'portfolio',
    'security_name_long': 'security_full_name',
    'country_name': 'country_of_exchange',
    'security_currency': 'security_currency',
    'asset_class': 'product_type',
    'listing_status': 'quoted_unquoted',
    'quantity': 'quantity',
    'pct_ratio_reserved': 'pct_holding',
    'cost_unit_price_local': 'average_cost',
    'market_unit_price_local': 'market_price',
    'cost_value_local': 'cost_fc',
    'market_value_local': 'market_value_fc',
    'cost_value_base': 'cost_lc',
    'market_value_base': 'market_value_lc',
    'unrealized_pl_local': 'unrealized_pnl_fc',
    'unrealized_pl_base': 'unrealized_pnl_lc',
    'isin': 'isin',
    'valuation_date': 'reporting_date',
    'settled_date': 'position_basis'
}

# AMS_STREET_4 Mappings (same as AMS_STREET_3)
AMS_STREET_4_MAPPING = AMS_STREET_3_MAPPING.copy()

# AMS_STREET_5 Mappings
AMS_STREET_5_MAPPING = {
    'ticker': 'ticker',
    'security_desc': 'security_full_name',
    'portfolio': 'portfolio',
    'quoted_unquoted': 'quoted_unquoted',
    'quantity_units': 'quantity',
    'ccy': 'security_currency',
    'product_type': 'product_type',
    'ctry_of_exchange': 'country_of_exchange',
    'ctry_incorporation': 'country_of_incorporation',
    'total_cost_fc': 'cost_fc',
    'mkt_value_fc': 'market_value_fc',
    'unrealised_pl_fc': 'unrealized_pnl_fc',
    'total_cost_sgd': 'cost_lc',
    'mkt_value_sgd': 'market_value_lc',
    'unrealised_pl_sgd': 'unrealized_pnl_lc',
    'mas_6digit_code': 'mas_6d_code_sg',
    'stake_holdings': 'pct_holding',
    'unit_cost': 'average_cost',
    'market_price': 'market_price',
    'trade_date': 'position_basis'
}


# =============================================================================
# TARGET SCHEMA - Position Master
# =============================================================================
POSITION_MASTER_COLUMNS = [
    'portfolio', 'security_full_name', 'security_short_name', 'isin', 'ticker',
    'quantity', 'shares_outstanding', 'shares_issued', 'pct_holding',
    'market_price', 'average_cost',
    'cost_fc', 'market_value_fc', 'net_book_value_fc', 'unrealized_pnl_fc',
    'cost_lc', 'market_value_lc', 'net_book_value_lc', 'unrealized_pnl_lc', 'provision_lc',
    'product_type', 'security_type', 'quoted_unquoted', 'industry', 'fin_nonfin_co',
    'issuer_type', 'reits_or_fund_y_n',
    'exchange', 'country_code', 'country_of_exchange', 'country_of_incorporation',
    'country_of_risk', 'country_of_operation', 'security_currency',
    'corp_code', 'branch_code', 'cost_centre', 'cels',
    'bwcif_sg', 'bwcif_ovs', 'mas_6d_code_sg', 'mas_6d_code_ovs',
    'position_basis', 'reporting_date', 'maturity_date',
    'src_system', 'sub_system', 'data_cat', 'data_frq', 'source_table',
    'etl_insert_ts', 'etl_batch_id',
    'src_id', 'processing_date'  # Partition columns
]


class PositionMasterETL:
    """ETL class for transforming source position data to position_master."""

    def __init__(self, spark: SparkSession, processing_date: str, batch_id: str = None):
        """
        Initialize ETL job.

        Args:
            spark: SparkSession instance
            processing_date: Processing date in DDMMYYYY format
            batch_id: Optional batch ID (generated if not provided)
        """
        self.spark = spark
        self.processing_date = processing_date
        self.batch_id = batch_id or str(uuid.uuid4())
        self.database = "gmp_cis"

    def transform_source(self, df, mapping: dict, source_table: str, src_system: str):
        """
        Transform a source DataFrame using the provided mapping.

        Args:
            df: Source DataFrame
            mapping: Dictionary mapping source columns to target columns
            source_table: Name of the source table
            src_system: Source system identifier

        Returns:
            Transformed DataFrame with position_master schema
        """
        # Start with selecting and renaming mapped columns
        select_exprs = []

        for target_col in POSITION_MASTER_COLUMNS:
            # Find source column that maps to this target
            source_col = None
            for src, tgt in mapping.items():
                if tgt == target_col:
                    source_col = src
                    break

            if source_col and source_col in df.columns:
                select_exprs.append(col(source_col).alias(target_col))
            elif target_col == 'src_system':
                select_exprs.append(lit(src_system).alias(target_col))
            elif target_col == 'source_table':
                select_exprs.append(lit(source_table).alias(target_col))
            elif target_col == 'etl_insert_ts':
                select_exprs.append(current_timestamp().alias(target_col))
            elif target_col == 'etl_batch_id':
                select_exprs.append(lit(self.batch_id).alias(target_col))
            elif target_col == 'processing_date':
                select_exprs.append(lit(self.processing_date).alias(target_col))
            elif target_col in ['sub_system', 'data_cat', 'data_frq', 'src_id']:
                # These come from partition columns if available
                if target_col in df.columns:
                    select_exprs.append(col(target_col).alias(target_col))
                else:
                    select_exprs.append(lit(None).cast(StringType()).alias(target_col))
            else:
                # Column not mapped - use NULL
                select_exprs.append(lit(None).cast(StringType()).alias(target_col))

        return df.select(*select_exprs)

    def read_source_table(self, table_name: str, src_system_filter: str = None):
        """
        Read source table with optional filtering.

        Args:
            table_name: Full table name (database.table)
            src_system_filter: Optional src_system filter value

        Returns:
            DataFrame of source data
        """
        df = self.spark.table(table_name)

        if src_system_filter and 'src_system' in df.columns:
            df = df.filter(col('src_system') == src_system_filter)

        # Filter by processing_date if specified
        if self.processing_date and 'processing_date' in df.columns:
            df = df.filter(col('processing_date') == self.processing_date)

        return df

    def process_user_upload_sources(self):
        """Process all USER_UPLOAD source tables."""
        print("Processing USER_UPLOAD sources...")

        dfs = []

        # USER_UPLOAD_1
        try:
            df1 = self.read_source_table(f"{self.database}.user_upload_1", "USER_UPLOAD")
            if df1.count() > 0:
                transformed = self.transform_source(df1, USER_UPLOAD_1_MAPPING, "user_upload_1", "USER_UPLOAD")
                dfs.append(transformed)
                print(f"  - user_upload_1: {df1.count()} records")
        except Exception as e:
            print(f"  - user_upload_1: SKIPPED ({e})")

        # USER_UPLOAD_2
        try:
            df2 = self.read_source_table(f"{self.database}.user_upload_2", "USER_UPLOAD")
            if df2.count() > 0:
                transformed = self.transform_source(df2, USER_UPLOAD_2_MAPPING, "user_upload_2", "USER_UPLOAD")
                dfs.append(transformed)
                print(f"  - user_upload_2: {df2.count()} records")
        except Exception as e:
            print(f"  - user_upload_2: SKIPPED ({e})")

        # USER_UPLOAD_3
        try:
            df3 = self.read_source_table(f"{self.database}.user_upload_3", "USER_UPLOAD")
            if df3.count() > 0:
                transformed = self.transform_source(df3, USER_UPLOAD_3_MAPPING, "user_upload_3", "USER_UPLOAD")
                dfs.append(transformed)
                print(f"  - user_upload_3: {df3.count()} records")
        except Exception as e:
            print(f"  - user_upload_3: SKIPPED ({e})")

        # USER_UPLOAD_4
        try:
            df4 = self.read_source_table(f"{self.database}.user_upload_4", "USER_UPLOAD")
            if df4.count() > 0:
                transformed = self.transform_source(df4, USER_UPLOAD_4_MAPPING, "user_upload_4", "USER_UPLOAD")
                dfs.append(transformed)
                print(f"  - user_upload_4: {df4.count()} records")
        except Exception as e:
            print(f"  - user_upload_4: SKIPPED ({e})")

        # USER_UPLOAD_5
        try:
            df5 = self.read_source_table(f"{self.database}.user_upload_5", "USER_UPLOAD")
            if df5.count() > 0:
                transformed = self.transform_source(df5, USER_UPLOAD_5_MAPPING, "user_upload_5", "USER_UPLOAD")
                dfs.append(transformed)
                print(f"  - user_upload_5: {df5.count()} records")
        except Exception as e:
            print(f"  - user_upload_5: SKIPPED ({e})")

        return dfs

    def process_ams_street_sources(self):
        """Process all AMS_STREET source tables."""
        print("Processing AMS_STREET sources...")

        dfs = []

        # AMS_STREET_1
        try:
            df1 = self.read_source_table(f"{self.database}.ams_street_1", "AMS_STREET")
            if df1.count() > 0:
                transformed = self.transform_source(df1, AMS_STREET_1_MAPPING, "ams_street_1", "AMS_STREET")
                dfs.append(transformed)
                print(f"  - ams_street_1: {df1.count()} records")
        except Exception as e:
            print(f"  - ams_street_1: SKIPPED ({e})")

        # AMS_STREET_2
        try:
            df2 = self.read_source_table(f"{self.database}.ams_street_2", "AMS_STREET")
            if df2.count() > 0:
                transformed = self.transform_source(df2, AMS_STREET_2_MAPPING, "ams_street_2", "AMS_STREET")
                dfs.append(transformed)
                print(f"  - ams_street_2: {df2.count()} records")
        except Exception as e:
            print(f"  - ams_street_2: SKIPPED ({e})")

        # AMS_STREET_3
        try:
            df3 = self.read_source_table(f"{self.database}.ams_street_3", "AMS_STREET")
            if df3.count() > 0:
                transformed = self.transform_source(df3, AMS_STREET_3_MAPPING, "ams_street_3", "AMS_STREET")
                dfs.append(transformed)
                print(f"  - ams_street_3: {df3.count()} records")
        except Exception as e:
            print(f"  - ams_street_3: SKIPPED ({e})")

        # AMS_STREET_4
        try:
            df4 = self.read_source_table(f"{self.database}.ams_street_4", "AMS_STREET")
            if df4.count() > 0:
                transformed = self.transform_source(df4, AMS_STREET_4_MAPPING, "ams_street_4", "AMS_STREET")
                dfs.append(transformed)
                print(f"  - ams_street_4: {df4.count()} records")
        except Exception as e:
            print(f"  - ams_street_4: SKIPPED ({e})")

        # AMS_STREET_5
        try:
            df5 = self.read_source_table(f"{self.database}.ams_street_5", "AMS_STREET")
            if df5.count() > 0:
                transformed = self.transform_source(df5, AMS_STREET_5_MAPPING, "ams_street_5", "AMS_STREET")
                dfs.append(transformed)
                print(f"  - ams_street_5: {df5.count()} records")
        except Exception as e:
            print(f"  - ams_street_5: SKIPPED ({e})")

        return dfs

    def run(self, mode: str = 'append'):
        """
        Execute the ETL job.

        Args:
            mode: Write mode ('append', 'overwrite')
        """
        print(f"\n{'='*60}")
        print(f"Position Master ETL Job")
        print(f"Processing Date: {self.processing_date}")
        print(f"Batch ID: {self.batch_id}")
        print(f"Mode: {mode}")
        print(f"{'='*60}\n")

        # Process all sources
        user_upload_dfs = self.process_user_upload_sources()
        ams_street_dfs = self.process_ams_street_sources()

        # Combine all DataFrames
        all_dfs = user_upload_dfs + ams_street_dfs

        if not all_dfs:
            print("\nNo data to process. Exiting.")
            return

        # Union all DataFrames
        print(f"\nUnioning {len(all_dfs)} source DataFrames...")
        combined_df = all_dfs[0]
        for df in all_dfs[1:]:
            combined_df = combined_df.unionByName(df, allowMissingColumns=True)

        total_records = combined_df.count()
        print(f"Total records to write: {total_records}")

        # Write to position_master table
        print(f"\nWriting to {self.database}.position_master...")

        combined_df.write \
            .mode(mode) \
            .partitionBy('src_id', 'processing_date') \
            .format('parquet') \
            .option('compression', 'snappy') \
            .saveAsTable(f"{self.database}.position_master")

        print(f"\nETL Job completed successfully!")
        print(f"Records written: {total_records}")
        print(f"{'='*60}\n")


def main():
    """Main entry point for the ETL job."""
    parser = argparse.ArgumentParser(description='Position Master ETL Job')
    parser.add_argument('--processing-date', required=True,
                        help='Processing date in DDMMYYYY format')
    parser.add_argument('--mode', default='append', choices=['append', 'overwrite'],
                        help='Write mode (default: append)')
    parser.add_argument('--batch-id', default=None,
                        help='Optional batch ID (auto-generated if not provided)')

    args = parser.parse_args()

    # Validate processing date format
    try:
        datetime.strptime(args.processing_date, '%d%m%Y')
    except ValueError:
        print(f"Error: Invalid processing date format. Expected DDMMYYYY, got: {args.processing_date}")
        return 1

    # Create Spark session
    spark = SparkSession.builder \
        .appName(f"PositionMasterETL_{args.processing_date}") \
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic") \
        .config("spark.sql.parquet.compression.codec", "snappy") \
        .enableHiveSupport() \
        .getOrCreate()

    try:
        # Run ETL
        etl = PositionMasterETL(spark, args.processing_date, args.batch_id)
        etl.run(mode=args.mode)
        return 0
    except Exception as e:
        print(f"ETL Job failed with error: {e}")
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    exit(main())
