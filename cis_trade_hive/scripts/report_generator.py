"""
Report Generator — PySpark
==========================
Reads a report definition from a Hive managed table by extraction_id,
executes the stored SQL/PySpark logic with caller-supplied parameters,
and writes the result to a properly quoted CSV with thousand-separated numbers.

Usage (Cloudera CML / spark-submit):
    spark-submit report_generator.py \
        --extraction_id RPT_TRADE_001 \
        --param portfolio=SG-PORT-01 \
        --param trade_date=2026-06-24 \
        --output /mnt/reports/output/

Or from Python:
    from report_generator import ReportGenerator
    gen = ReportGenerator(spark)
    gen.run(extraction_id='RPT_TRADE_001', params={'portfolio': 'SG-PORT-01'})
"""

import argparse
import csv
import io
import logging
import os
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s'
)
logger = logging.getLogger('report_generator')

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPORT_DB       = 'gmp_cis'
REPORT_DEF_TABLE = f'{REPORT_DB}.cis_report_definitions'  # managed Hive table

# Columns in cis_report_definitions:
#   extraction_id  STRING   -- unique report key  e.g. RPT_TRADE_001
#   report_name    STRING   -- human-readable name
#   sql_query      STRING   -- parameterised SQL; use {param_name} placeholders
#   numeric_cols   STRING   -- comma-separated column names that need thousand sep
#   decimal_places STRING   -- JSON/comma pairs: col:dp  e.g. "price:6,quantity:4"
#   output_format  STRING   -- CSV (only supported format for now)
#   description    STRING
#   is_active      BOOLEAN
#   created_by     STRING
#   created_at     TIMESTAMP


# ---------------------------------------------------------------------------
# Number formatting helpers
# ---------------------------------------------------------------------------

# Columns that should NEVER get thousand-separator treatment
# (e.g. IDs, codes, dates stored as strings)
_NON_NUMERIC_PATTERNS = re.compile(
    r'(id|code|isin|status|type|date|name|label|flag|source|remarks|currency)',
    re.IGNORECASE
)


def fmt_number(value: Any, decimal_places: int = 2) -> str:
    """
    Format a numeric value with thousand separators and fixed decimal places.
    Returns the original value as string if it cannot be parsed as a number.

    Examples:
        1234567.89  →  "1,234,567.89"
        None / ''   →  ""
        "APPLE"     →  "APPLE"   (non-numeric: passed through unchanged)
    """
    if value is None or value == '':
        return ''
    try:
        numeric = float(value)
        return f'{numeric:,.{decimal_places}f}'
    except (ValueError, TypeError):
        return str(value)


def fmt_string(value: Any) -> str:
    """
    Safely coerce any value to a clean string for CSV output.
    Strips leading/trailing whitespace; converts None to empty string.
    """
    if value is None:
        return ''
    return str(value).strip()


def should_format_as_number(col_name: str, explicit_numeric_cols: set) -> bool:
    """
    Return True if this column should receive thousand-separator formatting.
    Decision priority:
      1. Explicitly listed in numeric_cols from report definition → yes
      2. Name matches a known non-numeric pattern → no
      3. Default → no (safe: only format what we know about)
    """
    if col_name in explicit_numeric_cols:
        return True
    return False


# ---------------------------------------------------------------------------
# CSV writer — handles special characters correctly
# ---------------------------------------------------------------------------

def write_csv_safe(
    rows: List[Dict[str, Any]],
    columns: List[str],
    numeric_cols: set,
    decimal_map: Dict[str, int],
    output_path: str,
) -> int:
    """
    Write rows to a CSV file with:
    - QUOTE_ALL quoting strategy → every field is wrapped in double-quotes,
      so commas / semicolons / newlines inside security names never break columns
    - Double-quote escaping for any embedded double-quote characters (RFC 4180)
    - Thousand-separator formatting for declared numeric columns
    - UTF-8 encoding with BOM (Excel-friendly)

    Returns the number of rows written.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    row_count = 0
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(
            f,
            quoting=csv.QUOTE_ALL,       # wrap every field in double-quotes
            quotechar='"',
            doublequote=True,            # "" inside a quoted field = literal "
            lineterminator='\r\n',       # Windows line endings (Excel default)
        )

        # Header row
        writer.writerow(columns)

        for row in rows:
            csv_row = []
            for col in columns:
                raw = row.get(col)

                if should_format_as_number(col, numeric_cols):
                    dp = decimal_map.get(col, 2)
                    csv_row.append(fmt_number(raw, decimal_places=dp))
                else:
                    csv_row.append(fmt_string(raw))

            writer.writerow(csv_row)
            row_count += 1

    logger.info(f'Wrote {row_count} rows → {output_path}')
    return row_count


# ---------------------------------------------------------------------------
# Report definition loader
# ---------------------------------------------------------------------------

def load_report_definition(spark, extraction_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a single report definition row from the managed Hive table.
    Returns None if extraction_id is not found or is inactive.
    """
    query = f"""
        SELECT
            extraction_id,
            report_name,
            sql_query,
            numeric_cols,
            decimal_places,
            output_format,
            description
        FROM {REPORT_DEF_TABLE}
        WHERE extraction_id = '{extraction_id.replace('\\', '\\\\').replace("'", "\\'")}'
          AND is_active = TRUE
        LIMIT 1
    """
    logger.info(f'Loading report definition for extraction_id={extraction_id}')
    df = spark.sql(query)
    rows = df.collect()

    if not rows:
        logger.error(f'No active report definition found for extraction_id={extraction_id}')
        return None

    row = rows[0].asDict()
    logger.info(f'Loaded report: {row.get("report_name")}')
    return row


def parse_numeric_cols(numeric_cols_str: str) -> set:
    """
    Parse comma-separated numeric column names from the report definition.
    Example: "quantity,price,total_amount,commission" → {'quantity','price',...}
    """
    if not numeric_cols_str:
        return set()
    return {c.strip() for c in numeric_cols_str.split(',') if c.strip()}


def parse_decimal_map(decimal_places_str: str) -> Dict[str, int]:
    """
    Parse decimal places per column.
    Format: "price:6,quantity:4,total_amount:2"
    Returns: {'price': 6, 'quantity': 4, 'total_amount': 2}
    Default dp=2 is applied in fmt_number when col not in this map.
    """
    result = {}
    if not decimal_places_str:
        return result
    for part in decimal_places_str.split(','):
        part = part.strip()
        if ':' in part:
            col, dp = part.split(':', 1)
            try:
                result[col.strip()] = int(dp.strip())
            except ValueError:
                pass
    return result


def substitute_params(sql_query: str, params: Dict[str, str]) -> str:
    """
    Replace {param_name} placeholders in the SQL query with caller-supplied values.
    Values are single-quoted and SQL-escaped (single quote doubled).

    Example:
        sql  = "SELECT * FROM cis_trade WHERE portfolio_short_name = {portfolio}"
        params = {'portfolio': "O'Brien Fund"}
        result = "SELECT * FROM cis_trade WHERE portfolio_short_name = 'O''Brien Fund'"
    """
    for key, value in params.items():
        escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
        sql_query = sql_query.replace(f'{{{key}}}', f"'{escaped}'")

    # Detect any unreplaced placeholders
    remaining = re.findall(r'\{(\w+)\}', sql_query)
    if remaining:
        raise ValueError(
            f'SQL query has unreplaced placeholders: {remaining}. '
            f'Provide them via --param {remaining[0]}=<value>'
        )
    return sql_query


# ---------------------------------------------------------------------------
# Main report runner
# ---------------------------------------------------------------------------

class ReportGenerator:
    """
    Executes a parameterised report from the Hive report definitions table
    and writes the result as a clean, properly-quoted CSV.
    """

    def __init__(self, spark, output_dir: str = '/tmp/cis_reports'):
        self.spark = spark
        self.output_dir = output_dir

    def run(
        self,
        extraction_id: str,
        params: Dict[str, str] = None,
        output_path: str = None,
    ) -> str:
        """
        Execute the report and write CSV.

        Args:
            extraction_id: Unique report key from cis_report_definitions
            params: Dict of SQL placeholder substitutions
            output_path: Override output file path (auto-generated if None)

        Returns:
            Path to the written CSV file
        """
        params = params or {}

        # 1. Load report definition
        defn = load_report_definition(self.spark, extraction_id)
        if not defn:
            raise ValueError(f'Report not found or inactive: {extraction_id}')

        # 2. Parse numeric column config
        numeric_cols = parse_numeric_cols(defn.get('numeric_cols', ''))
        decimal_map  = parse_decimal_map(defn.get('decimal_places', ''))

        # 3. Substitute parameters into SQL
        sql_query = substitute_params(defn['sql_query'], params)
        logger.info(f'Executing SQL:\n{sql_query}')

        # 4. Execute query via Spark SQL
        df = self.spark.sql(sql_query)
        columns = df.columns
        rows = [row.asDict() for row in df.collect()]

        logger.info(f'Query returned {len(rows)} rows, {len(columns)} columns')

        # 5. Build output path
        if not output_path:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_id = re.sub(r'[^A-Za-z0-9_\-]', '_', extraction_id)
            output_path = os.path.join(
                self.output_dir,
                f'{safe_id}_{ts}.csv'
            )

        # 6. Write CSV with safe quoting + number formatting
        row_count = write_csv_safe(
            rows=rows,
            columns=columns,
            numeric_cols=numeric_cols,
            decimal_map=decimal_map,
            output_path=output_path,
        )

        logger.info(
            f'Report complete: extraction_id={extraction_id}, '
            f'rows={row_count}, file={output_path}'
        )
        return output_path


# ---------------------------------------------------------------------------
# Hive DDL for the report definitions table (run once)
# ---------------------------------------------------------------------------

CREATE_REPORT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS gmp_cis.cis_report_definitions (
    extraction_id   STRING   COMMENT 'Unique report key, e.g. RPT_TRADE_001',
    report_name     STRING   COMMENT 'Human-readable report name',
    sql_query       STRING   COMMENT 'Parameterised SQL; use {param_name} placeholders',
    numeric_cols    STRING   COMMENT 'Comma-separated column names to format with thousand separators',
    decimal_places  STRING   COMMENT 'Col-specific decimal places: price:6,quantity:4,total_amount:2',
    output_format   STRING   COMMENT 'Output format: CSV',
    description     STRING   COMMENT 'Report description',
    is_active       BOOLEAN  COMMENT 'Soft disable flag',
    created_by      STRING,
    created_at      TIMESTAMP,
    updated_by      STRING,
    updated_at      TIMESTAMP
)
COMMENT 'Report definition registry — one row per report'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\\001'
STORED AS ORC;
"""

# ---------------------------------------------------------------------------
# Sample report definition INSERT (run once per report)
# ---------------------------------------------------------------------------

SAMPLE_INSERT = """
INSERT INTO gmp_cis.cis_report_definitions VALUES (
    'RPT_TRADE_001',
    'Trade List by Portfolio',
    'SELECT
         t.deal_number,
         t.trade_date,
         t.settlement_date,
         t.portfolio_short_name,
         t.security_label,
         t.security_full_name,
         t.trade_type,
         t.trade_status,
         t.quantity,
         t.price,
         t.total_amount,
         t.total_amount_lc,
         t.commission,
         t.currency_code
     FROM gmp_cis.cis_trade t
     WHERE t.portfolio_short_name = {portfolio}
       AND t.trade_date BETWEEN {date_from} AND {date_to}
       AND t.trade_status != ''CANCELLED''
     ORDER BY t.trade_date DESC, t.deal_number',
    'quantity,price,total_amount,total_amount_lc,commission',
    'quantity:4,price:6,total_amount:2,total_amount_lc:2,commission:2',
    'CSV',
    'All trades for a given portfolio within a date range',
    TRUE,
    'admin',
    current_timestamp(),
    'admin',
    current_timestamp()
);
"""


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description='CIS Report Generator')
    parser.add_argument(
        '--extraction_id', required=True,
        help='Report extraction_id from cis_report_definitions (e.g. RPT_TRADE_001)'
    )
    parser.add_argument(
        '--param', action='append', default=[],
        metavar='KEY=VALUE',
        help='SQL parameter substitution. Repeat for multiple params: --param portfolio=SG-01 --param date_from=2026-01-01'
    )
    parser.add_argument(
        '--output_dir', default='/tmp/cis_reports',
        help='Directory to write CSV output (default: /tmp/cis_reports)'
    )
    parser.add_argument(
        '--output_file', default=None,
        help='Override full output file path'
    )
    parser.add_argument(
        '--create_table', action='store_true',
        help='Print the DDL to create cis_report_definitions and exit'
    )
    parser.add_argument(
        '--sample_insert', action='store_true',
        help='Print a sample INSERT for cis_report_definitions and exit'
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.create_table:
        print(CREATE_REPORT_TABLE_DDL)
        sys.exit(0)

    if args.sample_insert:
        print(SAMPLE_INSERT)
        sys.exit(0)

    # Parse --param KEY=VALUE pairs
    params = {}
    for pair in args.param:
        if '=' not in pair:
            logger.error(f'Invalid --param format (expected KEY=VALUE): {pair}')
            sys.exit(1)
        key, _, value = pair.partition('=')
        params[key.strip()] = value.strip()

    # Initialise Spark session
    try:
        from pyspark.sql import SparkSession
        spark = (
            SparkSession.builder
            .appName(f'CIS_Report_{args.extraction_id}')
            .enableHiveSupport()
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel('WARN')
    except ImportError:
        logger.error('PySpark not available. Run via spark-submit or in a CML session.')
        sys.exit(1)

    try:
        gen = ReportGenerator(spark, output_dir=args.output_dir)
        output_path = gen.run(
            extraction_id=args.extraction_id,
            params=params,
            output_path=args.output_file,
        )
        print(f'SUCCESS: {output_path}')
    except Exception as e:
        logger.error(f'Report generation failed: {e}', exc_info=True)
        sys.exit(1)
    finally:
        spark.stop()


if __name__ == '__main__':
    main()
