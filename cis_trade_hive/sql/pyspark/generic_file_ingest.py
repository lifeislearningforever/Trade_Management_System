#!/usr/bin/env python3
"""
Generic File Ingestion Framework
================================
Metadata-driven PySpark job for ingesting CSV/TXT files into Hive External Tables (Parquet).

Usage:
    spark-submit generic_file_ingest.py \
        --source-id GMP_POSITIONS \
        --processing-date 2026-02-10 \
        --load-mode OVERWRITE_PARTITION \
        --batch-id BATCH_20260210_001

Parameters:
    --source-id         : Source identifier from cis_ingestion_config (required)
    --processing-date   : Processing date YYYY-MM-DD (default: today)
    --load-mode         : FULL, DELTA, OVERWRITE_PARTITION, MERGE (default: from config)
    --batch-id          : Unique batch identifier (default: auto-generated)
    --file-path         : Override file path (optional)
    --dry-run           : Preview without writing (default: False)
    --validate-only     : Only validate, don't load (default: False)
    --reprocess         : Force reprocess even if already loaded (default: False)

Created: 2026-02-10
Version: 1.0
"""

import argparse
import json
import logging
import re
import sys
import time
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, lit, current_timestamp, expr, when, trim, upper, lower,
    to_date, to_timestamp, regexp_replace, coalesce, count, sum as spark_sum,
    md5, concat_ws, row_number
)
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, LongType,
    DecimalType, DateType, TimestampType, BooleanType, DoubleType
)
from pyspark.sql.window import Window

# ============================================================================
# LOGGING SETUP
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("GenericFileIngest")


# ============================================================================
# CONSTANTS
# ============================================================================
CONFIG_TABLE = "gmp_cis.cis_ingestion_config"
RECON_TABLE = "gmp_cis.cis_ingestion_recon"
RECON_LOCATION = "/data/gmp_cis/ingestion/cis_ingestion_recon"

TYPE_MAPPING = {
    "STRING": StringType(),
    "INT": IntegerType(),
    "INTEGER": IntegerType(),
    "BIGINT": LongType(),
    "LONG": LongType(),
    "DECIMAL": DecimalType(20, 6),
    "DOUBLE": DoubleType(),
    "FLOAT": DoubleType(),
    "DATE": DateType(),
    "TIMESTAMP": TimestampType(),
    "BOOLEAN": BooleanType(),
    "BOOL": BooleanType()
}


# ============================================================================
# CONFIGURATION LOADER
# ============================================================================
class ConfigLoader:
    """Loads ingestion configuration from metadata table."""

    def __init__(self, spark: SparkSession):
        self.spark = spark

    def load_config(self, source_id: str) -> Dict:
        """Load configuration for a source."""
        query = f"""
            SELECT * FROM {CONFIG_TABLE}
            WHERE source_id = '{source_id}'
            AND is_active = TRUE
        """
        config_df = self.spark.sql(query)

        if config_df.count() == 0:
            raise ValueError(f"No active configuration found for source_id: {source_id}")

        config_row = config_df.first()
        return config_row.asDict()

    def parse_column_schema(self, schema_json: str) -> Tuple[StructType, List[Dict]]:
        """Parse column schema JSON into Spark StructType."""
        columns = json.loads(schema_json)

        fields = []
        for col_def in columns:
            col_name = col_def["name"]
            col_type_str = col_def["type"].upper()
            nullable = col_def.get("nullable", True)

            # Handle DECIMAL with precision
            if col_type_str.startswith("DECIMAL"):
                match = re.match(r"DECIMAL\((\d+),\s*(\d+)\)", col_type_str)
                if match:
                    precision, scale = int(match.group(1)), int(match.group(2))
                    spark_type = DecimalType(precision, scale)
                else:
                    spark_type = DecimalType(20, 6)
            else:
                spark_type = TYPE_MAPPING.get(col_type_str, StringType())

            fields.append(StructField(col_name, spark_type, nullable))

        return StructType(fields), columns

    def parse_validation_rules(self, rules_json: Optional[str]) -> List[Dict]:
        """Parse validation rules JSON."""
        if not rules_json:
            return []
        return json.loads(rules_json)

    def parse_transformations(self, transform_json: Optional[str]) -> List[Dict]:
        """Parse transformation rules JSON."""
        if not transform_json:
            return []
        return json.loads(transform_json)


# ============================================================================
# FILE READER
# ============================================================================
class FileReader:
    """Reads source files based on configuration."""

    def __init__(self, spark: SparkSession, config: Dict):
        self.spark = spark
        self.config = config

    def read_file(self, file_path: str) -> DataFrame:
        """Read file based on file type configuration."""
        file_type = self.config.get("file_type", "CSV").upper()

        options = {
            "header": str(self.config.get("has_header", True)).lower(),
            "encoding": self.config.get("file_encoding", "UTF-8"),
            "quote": self.config.get("quote_char", '"'),
            "escape": self.config.get("escape_char", "\\"),
            "nullValue": self.config.get("null_string", ""),
            "mode": "PERMISSIVE",
            "columnNameOfCorruptRecord": "_corrupt_record"
        }

        if file_type in ("CSV", "TXT"):
            options["sep"] = self.config.get("column_delimiter", ",")
        elif file_type == "PIPE":
            options["sep"] = "|"
        elif file_type == "TAB":
            options["sep"] = "\t"
        elif file_type == "FIXED_WIDTH":
            return self._read_fixed_width(file_path)

        df = self.spark.read.options(**options).csv(file_path)

        # Skip rows if configured
        skip_rows = self.config.get("skip_rows", 0) or 0
        skip_footer = self.config.get("skip_footer_rows", 0) or 0

        if skip_rows > 0 or skip_footer > 0:
            df = self._skip_rows(df, skip_rows, skip_footer)

        return df

    def _read_fixed_width(self, file_path: str) -> DataFrame:
        """Read fixed-width format file."""
        raw_df = self.spark.read.text(file_path)

        columns = json.loads(self.config["column_schema"])

        exprs = []
        for col_def in columns:
            start = col_def.get("start_position", 0)
            length = col_def.get("length", 10)
            name = col_def["name"]
            exprs.append(
                trim(raw_df.value.substr(start + 1, length)).alias(name)
            )

        return raw_df.select(*exprs)

    def _skip_rows(self, df: DataFrame, skip_header: int, skip_footer: int) -> DataFrame:
        """Skip header and footer rows."""
        if skip_header == 0 and skip_footer == 0:
            return df

        w = Window.orderBy(lit(1))
        df_numbered = df.withColumn("_row_num", row_number().over(w))

        total_rows = df_numbered.count()

        return df_numbered.filter(
            (col("_row_num") > skip_header) &
            (col("_row_num") <= total_rows - skip_footer)
        ).drop("_row_num")


# ============================================================================
# DATA VALIDATOR
# ============================================================================
class DataValidator:
    """Validates data based on configuration rules."""

    def __init__(self, spark: SparkSession, rules: List[Dict]):
        self.spark = spark
        self.rules = rules

    def validate(self, df: DataFrame) -> Tuple[DataFrame, DataFrame, Dict]:
        """
        Validate DataFrame and separate valid/invalid records.
        Returns: (valid_df, rejected_df, validation_stats)
        """
        if not self.rules:
            return df, self.spark.createDataFrame([], df.schema), {"errors": []}

        error_conditions = []

        for rule in self.rules:
            column = rule["column"]
            rule_type = rule["rule"].upper()

            if rule_type == "NOT_NULL":
                cond = col(column).isNull()
                msg = f"{column}_IS_NULL"

            elif rule_type == "POSITIVE":
                cond = col(column) <= 0
                msg = f"{column}_NOT_POSITIVE"

            elif rule_type == "REGEX":
                pattern = rule["pattern"]
                cond = ~col(column).rlike(pattern)
                msg = f"{column}_REGEX_FAIL"

            elif rule_type == "IN_LIST":
                values = rule["values"]
                cond = ~col(column).isin(values)
                msg = f"{column}_NOT_IN_LIST"

            elif rule_type == "RANGE":
                min_val = rule.get("min")
                max_val = rule.get("max")
                cond = (col(column) < min_val) | (col(column) > max_val)
                msg = f"{column}_OUT_OF_RANGE"

            elif rule_type == "DATE_FORMAT":
                fmt = rule.get("format", "yyyy-MM-dd")
                cond = to_date(col(column), fmt).isNull()
                msg = f"{column}_INVALID_DATE"

            else:
                continue

            error_conditions.append((cond, msg))

        if error_conditions:
            validation_error = lit(None).cast(StringType())
            for cond, msg in error_conditions:
                validation_error = when(cond, msg).otherwise(validation_error)

            df = df.withColumn("_validation_error", validation_error)

            valid_df = df.filter(col("_validation_error").isNull()).drop("_validation_error")
            rejected_df = df.filter(col("_validation_error").isNotNull())

            error_stats = rejected_df.groupBy("_validation_error").count().collect()
            validation_stats = {
                "errors": [{"error": row["_validation_error"], "count": row["count"]} for row in error_stats]
            }
        else:
            valid_df = df
            rejected_df = self.spark.createDataFrame([], df.schema)
            validation_stats = {"errors": []}

        return valid_df, rejected_df, validation_stats


# ============================================================================
# DATA TRANSFORMER
# ============================================================================
class DataTransformer:
    """Applies transformations based on configuration."""

    def __init__(self, spark: SparkSession, transformations: List[Dict]):
        self.spark = spark
        self.transformations = transformations

    def transform(self, df: DataFrame) -> DataFrame:
        """Apply all transformations."""
        for transform in self.transformations:
            column = transform["column"]
            transform_expr = transform["transform"]

            # Handle special cases
            if transform_expr.startswith("LITERAL("):
                value = transform_expr[8:-1].strip("'\"")
                df = df.withColumn(column, lit(value))
            elif transform_expr == "CURRENT_DATE()":
                df = df.withColumn(column, expr("current_date()"))
            elif transform_expr == "CURRENT_TIMESTAMP()":
                df = df.withColumn(column, current_timestamp())
            else:
                df = df.withColumn(column, expr(transform_expr))

        return df


# ============================================================================
# DATA WRITER
# ============================================================================
class DataWriter:
    """Writes data to target based on load mode."""

    def __init__(self, spark: SparkSession, config: Dict):
        self.spark = spark
        self.config = config

    def write(self, df: DataFrame, load_mode: str, processing_date: str) -> Dict:
        """
        Write DataFrame to target.
        Returns write statistics.
        """
        target_location = self.config["target_location"]
        partition_columns_str = self.config.get("partition_columns", "") or ""
        partition_columns = [c.strip() for c in partition_columns_str.split(",") if c.strip()]

        stats = {
            "rows_written": df.count(),
            "partitions_processed": [],
            "mode": load_mode
        }

        if load_mode == "FULL":
            writer = df.write.mode("overwrite")

        elif load_mode == "DELTA":
            writer = df.write.mode("append")

        elif load_mode == "OVERWRITE_PARTITION":
            self.spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
            writer = df.write.mode("overwrite")

            if partition_columns:
                partition_values = df.select(partition_columns).distinct().collect()
                stats["partitions_processed"] = [
                    {col_name: str(row[col_name]) for col_name in partition_columns}
                    for row in partition_values
                ]

        elif load_mode == "MERGE":
            stats = self._merge_write(df, target_location, partition_columns)
            return stats

        else:
            raise ValueError(f"Unknown load mode: {load_mode}")

        if partition_columns:
            writer = writer.partitionBy(*partition_columns)

        writer.format("parquet") \
            .option("compression", "snappy") \
            .save(target_location)

        return stats

    def _merge_write(self, source_df: DataFrame, target_location: str,
                     partition_columns: List[str]) -> Dict:
        """Simulate MERGE/UPSERT for Parquet tables."""
        pk_columns_str = self.config.get("primary_key_columns", "") or ""
        pk_columns = [c.strip() for c in pk_columns_str.split(",") if c.strip()]

        if not pk_columns:
            raise ValueError("MERGE mode requires primary_key_columns configuration")

        stats = {
            "rows_inserted": 0,
            "rows_updated": 0,
            "rows_unchanged": 0,
            "mode": "MERGE"
        }

        try:
            existing_df = self.spark.read.parquet(target_location)
        except Exception:
            writer = source_df.write.mode("overwrite")
            if partition_columns:
                writer = writer.partitionBy(*partition_columns)
            writer.format("parquet") \
                .option("compression", "snappy") \
                .save(target_location)
            stats["rows_inserted"] = source_df.count()
            return stats

        source_df = source_df.alias("source")
        existing_df = existing_df.alias("target")

        updates = source_df.join(existing_df, pk_columns, "inner").select("source.*")
        stats["rows_updated"] = updates.count()

        inserts = source_df.join(existing_df, pk_columns, "left_anti")
        stats["rows_inserted"] = inserts.count()

        unchanged = existing_df.join(source_df, pk_columns, "left_anti")
        stats["rows_unchanged"] = unchanged.count()

        final_df = updates.unionByName(inserts).unionByName(unchanged)

        writer = final_df.write.mode("overwrite")
        if partition_columns:
            writer = writer.partitionBy(*partition_columns)

        writer.format("parquet") \
            .option("compression", "snappy") \
            .save(target_location)

        return stats


# ============================================================================
# RECONCILIATION WRITER
# ============================================================================
class ReconWriter:
    """Writes reconciliation records."""

    def __init__(self, spark: SparkSession):
        self.spark = spark

    def write_recon(self, recon_data: Dict, processing_date: str):
        """Write reconciliation record."""
        recon_id = int(time.time() * 1000)
        recon_data["recon_id"] = recon_id
        recon_data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Convert all values to strings for JSON compatibility
        clean_data = {}
        for k, v in recon_data.items():
            if v is None:
                clean_data[k] = None
            elif isinstance(v, (dict, list)):
                clean_data[k] = json.dumps(v) if not isinstance(v, str) else v
            else:
                clean_data[k] = v

        recon_df = self.spark.createDataFrame([clean_data])

        recon_location = f"{RECON_LOCATION}/processing_date={processing_date}"

        recon_df.write.mode("append") \
            .format("parquet") \
            .option("compression", "snappy") \
            .save(recon_location)

        logger.info(f"Reconciliation record written: {recon_id}")


# ============================================================================
# MAIN INGESTION ENGINE
# ============================================================================
class IngestionEngine:
    """Main orchestration engine for file ingestion."""

    def __init__(self, spark: SparkSession, args: argparse.Namespace):
        self.spark = spark
        self.args = args
        self.config_loader = ConfigLoader(spark)
        self.recon_writer = ReconWriter(spark)

        self.config = self.config_loader.load_config(args.source_id)

        self.schema, self.column_defs = self.config_loader.parse_column_schema(
            self.config["column_schema"]
        )
        self.validation_rules = self.config_loader.parse_validation_rules(
            self.config.get("validation_rules")
        )
        self.transformations = self.config_loader.parse_transformations(
            self.config.get("transformations")
        )

    def run(self) -> Dict:
        """Execute the ingestion pipeline."""
        start_time = datetime.now()
        load_mode = self.args.load_mode or self.config.get("default_load_mode", "FULL")

        recon_data = {
            "config_id": self.config.get("config_id"),
            "source_id": self.args.source_id,
            "batch_id": self.args.batch_id,
            "run_mode": load_mode,
            "run_environment": self._get_environment(),
            "spark_app_id": self.spark.sparkContext.applicationId,
            "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "RUNNING",
            "rows_read": 0,
            "rows_validated": 0,
            "rows_rejected": 0,
            "rows_inserted": 0,
            "rows_updated": 0
        }

        try:
            # 1. Determine file path
            file_path = self.args.file_path or self._resolve_file_path()
            recon_data["file_path"] = file_path
            recon_data["file_name"] = file_path.split("/")[-1]

            logger.info(f"Processing file: {file_path}")

            # 2. Read file
            read_start = time.time()
            file_reader = FileReader(self.spark, self.config)
            raw_df = file_reader.read_file(file_path)
            read_time = int(time.time() - read_start)

            recon_data["source_total_rows"] = raw_df.count()
            recon_data["rows_read"] = recon_data["source_total_rows"]
            recon_data["read_time_seconds"] = read_time

            logger.info(f"Read {recon_data['rows_read']} rows in {read_time}s")

            # Check for empty file
            if recon_data["rows_read"] == 0:
                logger.warning("Source file is empty")
                recon_data["status"] = "SUCCESS"
                recon_data["warning_count"] = 1
                recon_data["warnings"] = json.dumps(["Source file is empty"])
                recon_data["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                recon_data["duration_seconds"] = 0
                recon_data["data_quality_score"] = 100.0
                return recon_data

            # 3. Validate
            validator = DataValidator(self.spark, self.validation_rules)
            valid_df, rejected_df, validation_stats = validator.validate(raw_df)

            recon_data["rows_validated"] = valid_df.count()
            recon_data["rows_rejected"] = rejected_df.count()
            recon_data["validation_errors"] = json.dumps(validation_stats["errors"])

            logger.info(f"Validated: {recon_data['rows_validated']} valid, {recon_data['rows_rejected']} rejected")

            # Check if all rows rejected
            if recon_data["rows_validated"] == 0 and recon_data["rows_rejected"] > 0:
                logger.error("All rows failed validation")
                recon_data["status"] = "FAILED"
                recon_data["error_message"] = "All rows failed validation"
                recon_data["data_quality_score"] = 0.0
                return recon_data

            # 4. Transform
            transform_start = time.time()
            transformer = DataTransformer(self.spark, self.transformations)
            transformed_df = transformer.transform(valid_df)
            transform_time = int(time.time() - transform_start)

            recon_data["rows_transformed"] = transformed_df.count()
            recon_data["transform_time_seconds"] = transform_time

            # 5. Add processing metadata
            processing_date = self.args.processing_date
            transformed_df = transformed_df \
                .withColumn("processing_date", lit(processing_date)) \
                .withColumn("batch_id", lit(self.args.batch_id)) \
                .withColumn("etl_load_timestamp", lit(int(time.time() * 1000)))

            # 6. Check for rerun
            is_rerun = self._check_rerun(processing_date)
            recon_data["is_rerun"] = is_rerun

            if self.args.dry_run:
                logger.info("DRY RUN - Preview of data:")
                transformed_df.show(20, truncate=False)
                recon_data["status"] = "DRY_RUN"
            elif self.args.validate_only:
                logger.info("VALIDATE ONLY - No data written")
                recon_data["status"] = "VALIDATED"
            else:
                # 7. Write to target
                write_start = time.time()
                writer = DataWriter(self.spark, self.config)
                write_stats = writer.write(transformed_df, load_mode, processing_date)
                write_time = int(time.time() - write_start)

                recon_data["rows_inserted"] = write_stats.get("rows_inserted", write_stats.get("rows_written", 0))
                recon_data["rows_updated"] = write_stats.get("rows_updated", 0)
                recon_data["write_time_seconds"] = write_time
                recon_data["partitions_processed"] = json.dumps(write_stats.get("partitions_processed", []))

                # Check for partial success (high rejection rate)
                rejection_rate = recon_data["rows_rejected"] / max(recon_data["source_total_rows"], 1)
                if rejection_rate > 0.1:
                    recon_data["status"] = "PARTIAL"
                    recon_data["warning_count"] = 1
                    recon_data["warnings"] = json.dumps([f"High rejection rate: {rejection_rate*100:.2f}%"])
                else:
                    recon_data["status"] = "SUCCESS"

                logger.info(f"Write completed in {write_time}s")

                # 8. Refresh table metadata
                self._refresh_table()

            # Calculate totals
            end_time = datetime.now()
            recon_data["end_time"] = end_time.strftime("%Y-%m-%d %H:%M:%S")
            recon_data["duration_seconds"] = int((end_time - start_time).total_seconds())

            # Calculate quality score
            total = recon_data.get("source_total_rows", 0)
            valid = recon_data.get("rows_validated", 0)
            recon_data["data_quality_score"] = round((valid / total * 100) if total > 0 else 0, 2)

        except FileNotFoundError as e:
            logger.error(f"File not found: {str(e)}")
            recon_data["status"] = "FAILED"
            recon_data["error_message"] = f"File not found: {str(e)}"
            recon_data["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        except Exception as e:
            logger.error(f"Ingestion failed: {str(e)}")
            recon_data["status"] = "FAILED"
            recon_data["error_message"] = str(e)
            recon_data["error_stack_trace"] = traceback.format_exc()
            recon_data["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            raise

        finally:
            # Write reconciliation record
            try:
                self.recon_writer.write_recon(recon_data, self.args.processing_date)
            except Exception as e:
                logger.error(f"Failed to write recon record: {e}")

        return recon_data

    def _resolve_file_path(self) -> str:
        """Resolve actual file path from pattern."""
        base_path = self.config["file_path"]
        pattern = self.config["file_name_pattern"]

        processing_date = self.args.processing_date
        date_obj = datetime.strptime(processing_date, "%Y-%m-%d")

        path = base_path.replace("{YYYY}", date_obj.strftime("%Y"))
        path = path.replace("{MM}", date_obj.strftime("%m"))
        path = path.replace("{DD}", date_obj.strftime("%d"))
        path = path.replace("{YYYYMMDD}", date_obj.strftime("%Y%m%d"))

        file_pattern = pattern.replace("{YYYY}", date_obj.strftime("%Y"))
        file_pattern = file_pattern.replace("{MM}", date_obj.strftime("%m"))
        file_pattern = file_pattern.replace("{DD}", date_obj.strftime("%d"))
        file_pattern = file_pattern.replace("{YYYYMMDD}", date_obj.strftime("%Y%m%d"))

        if "*" in file_pattern:
            import glob
            files = glob.glob(f"{path}/{file_pattern}")
            if not files:
                raise FileNotFoundError(f"No files found matching: {path}/{file_pattern}")
            return sorted(files)[-1]

        return f"{path}/{file_pattern}"

    def _check_rerun(self, processing_date: str) -> bool:
        """Check if this is a rerun for the same processing date."""
        query = f"""
            SELECT COUNT(*) as cnt FROM {RECON_TABLE}
            WHERE source_id = '{self.args.source_id}'
            AND processing_date = '{processing_date}'
            AND status = 'SUCCESS'
        """
        try:
            result = self.spark.sql(query).first()
            return result["cnt"] > 0
        except Exception:
            return False

    def _refresh_table(self):
        """Refresh Hive table metadata after write."""
        target_db = self.config.get("target_database", "gmp_cis")
        target_table = self.config.get("target_table", "")

        if not target_table:
            return

        try:
            self.spark.sql(f"REFRESH {target_db}.{target_table}")
            logger.info(f"Refreshed table: {target_db}.{target_table}")
        except Exception:
            try:
                self.spark.sql(f"MSCK REPAIR TABLE {target_db}.{target_table}")
                logger.info(f"Repaired partitions: {target_db}.{target_table}")
            except Exception as e:
                logger.warning(f"Could not refresh table metadata: {e}")

    def _get_environment(self) -> str:
        """Determine runtime environment."""
        try:
            conf = self.spark.sparkContext.getConf()
            master = conf.get("spark.master", "")
            if "local" in master:
                return "DEV"
            elif "yarn" in master:
                return "PROD"
            else:
                return "UNKNOWN"
        except Exception:
            return "UNKNOWN"


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Generic File Ingestion Framework")

    parser.add_argument("--source-id", required=True,
                        help="Source identifier from cis_ingestion_config")
    parser.add_argument("--processing-date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="Processing date (YYYY-MM-DD)")
    parser.add_argument("--load-mode", choices=["FULL", "DELTA", "OVERWRITE_PARTITION", "MERGE"],
                        help="Load mode (overrides config default)")
    parser.add_argument("--batch-id", default=None,
                        help="Batch identifier (auto-generated if not provided)")
    parser.add_argument("--file-path",
                        help="Override file path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing")
    parser.add_argument("--validate-only", action="store_true",
                        help="Only validate, don't load")
    parser.add_argument("--reprocess", action="store_true",
                        help="Force reprocess even if already loaded")

    args = parser.parse_args()

    # Generate batch ID if not provided
    if not args.batch_id:
        args.batch_id = f"BATCH_{args.processing_date.replace('-', '')}_{int(time.time()) % 1000:03d}"

    return args


def main():
    """Main entry point."""
    args = parse_args()

    logger.info("=" * 70)
    logger.info("GENERIC FILE INGESTION FRAMEWORK")
    logger.info("=" * 70)
    logger.info(f"Source ID      : {args.source_id}")
    logger.info(f"Processing Date: {args.processing_date}")
    logger.info(f"Load Mode      : {args.load_mode or 'FROM_CONFIG'}")
    logger.info(f"Batch ID       : {args.batch_id}")
    logger.info(f"Dry Run        : {args.dry_run}")
    logger.info("=" * 70)

    # Initialize Spark
    spark = SparkSession.builder \
        .appName(f"FileIngest_{args.source_id}_{args.processing_date}") \
        .enableHiveSupport() \
        .getOrCreate()

    try:
        engine = IngestionEngine(spark, args)
        result = engine.run()

        logger.info("=" * 70)
        logger.info("INGESTION COMPLETE")
        logger.info(f"Status         : {result['status']}")
        logger.info(f"Rows Read      : {result.get('rows_read', 0)}")
        logger.info(f"Rows Validated : {result.get('rows_validated', 0)}")
        logger.info(f"Rows Rejected  : {result.get('rows_rejected', 0)}")
        logger.info(f"Rows Written   : {result.get('rows_inserted', 0) + result.get('rows_updated', 0)}")
        logger.info(f"Duration       : {result.get('duration_seconds', 0)}s")
        logger.info(f"Quality Score  : {result.get('data_quality_score', 0)}%")
        logger.info("=" * 70)

        return 0 if result['status'] in ('SUCCESS', 'DRY_RUN', 'VALIDATED', 'PARTIAL') else 1

    except Exception as e:
        logger.error(f"INGESTION FAILED: {str(e)}")
        return 1

    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
