#!/usr/bin/env python3
"""
SIT to UAT Database Migration Script - DDL Extraction

This script connects to SIT Impala/Kudu database and extracts:
1. Table DDL (CREATE TABLE statements)
2. Table data (INSERT statements) - optional
3. Generates migration files for UAT deployment

Usage:
    # Extract DDL only
    python extract_sit_ddl.py --host sit-impala-host --port 21050

    # Extract DDL and data
    python extract_sit_ddl.py --host sit-impala-host --port 21050 --include-data

    # Extract specific tables
    python extract_sit_ddl.py --host sit-impala-host --tables cis_trade,cis_portfolio

Environment Variables:
    SIT_IMPALA_HOST: SIT Impala host (default: localhost)
    SIT_IMPALA_PORT: SIT Impala port (default: 21050)
    SIT_IMPALA_AUTH: Authentication method (NOSASL, GSSAPI, LDAP)
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from pyhive import hive
    from thrift.transport import TSocket
except ImportError:
    print("Error: pyhive not installed. Run: pip install pyhive thrift thrift-sasl")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE = 'gmp_cis'

# Output directory
OUTPUT_DIR = Path(__file__).parent / 'output'


class SITDDLExtractor:
    """Extract DDL and data from SIT database."""

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 21050,
        auth: str = 'NOSASL',
        username: str = None,
        password: str = None
    ):
        self.host = host
        self.port = port
        self.auth = auth
        self.username = username
        self.password = password
        self.connection = None
        self.cursor = None

    def connect(self) -> bool:
        """Connect to SIT Impala."""
        try:
            logger.info(f"Connecting to SIT Impala at {self.host}:{self.port}")

            conn_params = {
                'host': self.host,
                'port': self.port,
                'auth': self.auth,
                'database': DATABASE
            }

            if self.username:
                conn_params['username'] = self.username
            if self.password:
                conn_params['password'] = self.password

            self.connection = hive.Connection(**conn_params)
            self.cursor = self.connection.cursor()

            # Test connection
            self.cursor.execute("SELECT 1")
            logger.info("Successfully connected to SIT Impala")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to SIT Impala: {str(e)}")
            return False

    def disconnect(self):
        """Close connection."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logger.info("Disconnected from SIT Impala")

    def get_all_tables(self) -> List[str]:
        """Get all tables in gmp_cis database."""
        try:
            self.cursor.execute(f"SHOW TABLES IN {DATABASE}")
            tables = [row[0] for row in self.cursor.fetchall()]
            logger.info(f"Found {len(tables)} tables in {DATABASE}")
            return sorted(tables)
        except Exception as e:
            logger.error(f"Error getting tables: {str(e)}")
            return []

    def get_table_ddl(self, table_name: str) -> Optional[str]:
        """Get CREATE TABLE statement for a table."""
        try:
            self.cursor.execute(f"SHOW CREATE TABLE {DATABASE}.{table_name}")
            result = self.cursor.fetchall()
            if result:
                # Join all rows (some DDLs span multiple rows)
                ddl = '\n'.join([row[0] for row in result])
                return ddl
            return None
        except Exception as e:
            logger.error(f"Error getting DDL for {table_name}: {str(e)}")
            return None

    def get_table_columns(self, table_name: str) -> List[Dict[str, str]]:
        """Get column information for a table."""
        try:
            self.cursor.execute(f"DESCRIBE {DATABASE}.{table_name}")
            columns = []
            for row in self.cursor.fetchall():
                columns.append({
                    'name': row[0],
                    'type': row[1],
                    'comment': row[2] if len(row) > 2 else ''
                })
            return columns
        except Exception as e:
            logger.error(f"Error getting columns for {table_name}: {str(e)}")
            return []

    def get_table_row_count(self, table_name: str) -> int:
        """Get row count for a table."""
        try:
            self.cursor.execute(f"SELECT COUNT(*) FROM {DATABASE}.{table_name}")
            result = self.cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting row count for {table_name}: {str(e)}")
            return 0

    def get_table_data(self, table_name: str, limit: int = None) -> List[Dict[str, Any]]:
        """Get data from a table."""
        try:
            query = f"SELECT * FROM {DATABASE}.{table_name}"
            if limit:
                query += f" LIMIT {limit}"

            self.cursor.execute(query)
            columns = [desc[0] for desc in self.cursor.description]
            rows = []
            for row in self.cursor.fetchall():
                rows.append(dict(zip(columns, row)))
            return rows
        except Exception as e:
            logger.error(f"Error getting data for {table_name}: {str(e)}")
            return []

    def format_value_for_insert(self, value: Any, col_type: str) -> str:
        """Format a value for INSERT statement."""
        if value is None:
            return 'NULL'

        col_type_lower = col_type.lower()

        # String types
        if 'string' in col_type_lower or 'varchar' in col_type_lower or 'char' in col_type_lower:
            # Escape single quotes
            escaped = str(value).replace("'", "''")
            return f"'{escaped}'"

        # Numeric types
        if any(t in col_type_lower for t in ['int', 'bigint', 'smallint', 'tinyint', 'decimal', 'double', 'float']):
            return str(value)

        # Boolean
        if 'boolean' in col_type_lower or 'bool' in col_type_lower:
            return 'true' if value else 'false'

        # Timestamp/Date
        if 'timestamp' in col_type_lower or 'date' in col_type_lower:
            return f"'{value}'"

        # Default: treat as string
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    def generate_insert_statements(
        self,
        table_name: str,
        columns: List[Dict[str, str]],
        data: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> List[str]:
        """Generate INSERT/UPSERT statements for table data."""
        if not data:
            return []

        statements = []
        col_names = [col['name'] for col in columns]
        col_types = {col['name']: col['type'] for col in columns}

        # Use UPSERT for Kudu tables
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]

            values_list = []
            for row in batch:
                values = []
                for col_name in col_names:
                    value = row.get(col_name)
                    col_type = col_types.get(col_name, 'string')
                    values.append(self.format_value_for_insert(value, col_type))

                values_list.append(f"({', '.join(values)})")

            # Generate UPSERT statement
            stmt = f"UPSERT INTO {DATABASE}.{table_name} ({', '.join(col_names)})\nVALUES\n"
            stmt += ',\n'.join(values_list) + ";"

            statements.append(stmt)

        return statements


def extract_ddl(
    extractor: SITDDLExtractor,
    tables: List[str],
    include_data: bool = False,
    data_limit: int = None
) -> Dict[str, Any]:
    """Extract DDL and optionally data for all tables."""

    result = {
        'timestamp': datetime.now().isoformat(),
        'database': DATABASE,
        'tables': {},
        'summary': {
            'total_tables': 0,
            'successful': 0,
            'failed': 0,
            'total_rows': 0
        }
    }

    for table_name in tables:
        logger.info(f"Processing table: {table_name}")

        table_info = {
            'ddl': None,
            'columns': [],
            'row_count': 0,
            'insert_statements': [],
            'status': 'pending'
        }

        try:
            # Get DDL
            ddl = extractor.get_table_ddl(table_name)
            if ddl:
                table_info['ddl'] = ddl
                table_info['status'] = 'success'
            else:
                table_info['status'] = 'failed'
                result['summary']['failed'] += 1
                continue

            # Get columns
            columns = extractor.get_table_columns(table_name)
            table_info['columns'] = columns

            # Get row count
            row_count = extractor.get_table_row_count(table_name)
            table_info['row_count'] = row_count
            result['summary']['total_rows'] += row_count

            # Get data if requested
            if include_data and row_count > 0:
                logger.info(f"  Extracting data ({row_count} rows)...")
                data = extractor.get_table_data(table_name, limit=data_limit)
                if data:
                    insert_stmts = extractor.generate_insert_statements(
                        table_name, columns, data
                    )
                    table_info['insert_statements'] = insert_stmts

            result['summary']['successful'] += 1

        except Exception as e:
            logger.error(f"Error processing {table_name}: {str(e)}")
            table_info['status'] = 'failed'
            table_info['error'] = str(e)
            result['summary']['failed'] += 1

        result['tables'][table_name] = table_info

    result['summary']['total_tables'] = len(tables)
    return result


def write_output_files(result: Dict[str, Any], output_dir: Path):
    """Write DDL and data files."""

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 1. Write combined DDL file
    ddl_file = output_dir / f'01_all_tables_ddl_{timestamp}.sql'
    with open(ddl_file, 'w') as f:
        f.write(f"-- ============================================\n")
        f.write(f"-- GMP_CIS Database DDL - Extracted from SIT\n")
        f.write(f"-- Generated: {result['timestamp']}\n")
        f.write(f"-- Tables: {result['summary']['total_tables']}\n")
        f.write(f"-- ============================================\n\n")

        f.write(f"-- Create database if not exists\n")
        f.write(f"CREATE DATABASE IF NOT EXISTS {DATABASE};\n")
        f.write(f"USE {DATABASE};\n\n")

        for table_name, table_info in result['tables'].items():
            if table_info['ddl']:
                f.write(f"-- ----------------------------------------\n")
                f.write(f"-- Table: {table_name}\n")
                f.write(f"-- Rows: {table_info['row_count']}\n")
                f.write(f"-- ----------------------------------------\n")
                f.write(f"DROP TABLE IF EXISTS {DATABASE}.{table_name};\n\n")
                f.write(table_info['ddl'])
                f.write(";\n\n")

    logger.info(f"Written: {ddl_file}")

    # 2. Write individual table DDL files
    tables_dir = output_dir / 'tables'
    tables_dir.mkdir(exist_ok=True)

    for table_name, table_info in result['tables'].items():
        if table_info['ddl']:
            table_file = tables_dir / f'{table_name}.sql'
            with open(table_file, 'w') as f:
                f.write(f"-- Table: {table_name}\n")
                f.write(f"-- Extracted: {result['timestamp']}\n")
                f.write(f"-- Rows: {table_info['row_count']}\n\n")
                f.write(f"DROP TABLE IF EXISTS {DATABASE}.{table_name};\n\n")
                f.write(table_info['ddl'])
                f.write(";\n")

    # 3. Write data files if present
    data_dir = output_dir / 'data'
    has_data = False

    for table_name, table_info in result['tables'].items():
        if table_info.get('insert_statements'):
            has_data = True
            data_dir.mkdir(exist_ok=True)

            data_file = data_dir / f'{table_name}_data.sql'
            with open(data_file, 'w') as f:
                f.write(f"-- Data for: {table_name}\n")
                f.write(f"-- Rows: {table_info['row_count']}\n")
                f.write(f"-- Extracted: {result['timestamp']}\n\n")

                for stmt in table_info['insert_statements']:
                    f.write(stmt)
                    f.write("\n\n")

            logger.info(f"Written: {data_file}")

    # 4. Write combined data file
    if has_data:
        all_data_file = output_dir / f'02_all_tables_data_{timestamp}.sql'
        with open(all_data_file, 'w') as f:
            f.write(f"-- ============================================\n")
            f.write(f"-- GMP_CIS Database Data - Extracted from SIT\n")
            f.write(f"-- Generated: {result['timestamp']}\n")
            f.write(f"-- ============================================\n\n")
            f.write(f"USE {DATABASE};\n\n")

            for table_name, table_info in result['tables'].items():
                if table_info.get('insert_statements'):
                    f.write(f"-- ----------------------------------------\n")
                    f.write(f"-- Data for: {table_name} ({table_info['row_count']} rows)\n")
                    f.write(f"-- ----------------------------------------\n\n")

                    for stmt in table_info['insert_statements']:
                        f.write(stmt)
                        f.write("\n\n")

        logger.info(f"Written: {all_data_file}")

    # 5. Write summary report
    summary_file = output_dir / f'00_migration_summary_{timestamp}.txt'
    with open(summary_file, 'w') as f:
        f.write("=" * 60 + "\n")
        f.write("SIT to UAT Migration Summary\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Extraction Time: {result['timestamp']}\n")
        f.write(f"Database: {result['database']}\n\n")

        f.write("Summary:\n")
        f.write(f"  Total Tables: {result['summary']['total_tables']}\n")
        f.write(f"  Successful: {result['summary']['successful']}\n")
        f.write(f"  Failed: {result['summary']['failed']}\n")
        f.write(f"  Total Rows: {result['summary']['total_rows']}\n\n")

        f.write("Tables:\n")
        f.write("-" * 60 + "\n")
        f.write(f"{'Table Name':<40} {'Rows':>10} {'Status':>10}\n")
        f.write("-" * 60 + "\n")

        for table_name, table_info in sorted(result['tables'].items()):
            f.write(f"{table_name:<40} {table_info['row_count']:>10} {table_info['status']:>10}\n")

        f.write("-" * 60 + "\n")

    logger.info(f"Written: {summary_file}")

    # 6. Write UAT deployment script
    deploy_script = output_dir / f'deploy_to_uat.sh'
    with open(deploy_script, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write("#\n")
        f.write("# UAT Deployment Script\n")
        f.write(f"# Generated: {result['timestamp']}\n")
        f.write("#\n")
        f.write("# Usage:\n")
        f.write("#   ./deploy_to_uat.sh --host uat-impala-host --port 21050\n")
        f.write("#   ./deploy_to_uat.sh --host uat-impala-host --port 21050 --include-data\n")
        f.write("#\n\n")

        f.write('set -e\n\n')

        f.write('# Default values\n')
        f.write('UAT_HOST="${UAT_IMPALA_HOST:-localhost}"\n')
        f.write('UAT_PORT="${UAT_IMPALA_PORT:-21050}"\n')
        f.write('INCLUDE_DATA=false\n')
        f.write('SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n\n')

        f.write('# Parse arguments\n')
        f.write('while [[ $# -gt 0 ]]; do\n')
        f.write('    case $1 in\n')
        f.write('        --host) UAT_HOST="$2"; shift 2 ;;\n')
        f.write('        --port) UAT_PORT="$2"; shift 2 ;;\n')
        f.write('        --include-data) INCLUDE_DATA=true; shift ;;\n')
        f.write('        *) echo "Unknown option: $1"; exit 1 ;;\n')
        f.write('    esac\n')
        f.write('done\n\n')

        f.write('echo "========================================"\n')
        f.write('echo "UAT Database Deployment"\n')
        f.write('echo "========================================"\n')
        f.write('echo "Host: $UAT_HOST"\n')
        f.write('echo "Port: $UAT_PORT"\n')
        f.write('echo "Include Data: $INCLUDE_DATA"\n')
        f.write('echo ""\n\n')

        f.write('# Function to run SQL file\n')
        f.write('run_sql() {\n')
        f.write('    local sql_file="$1"\n')
        f.write('    echo "Running: $sql_file"\n')
        f.write('    impala-shell -i "$UAT_HOST:$UAT_PORT" -f "$sql_file"\n')
        f.write('}\n\n')

        f.write('# Step 1: Create tables (DDL)\n')
        f.write('echo "Step 1: Creating tables..."\n')
        f.write(f'DDL_FILE="$SCRIPT_DIR/01_all_tables_ddl_{timestamp}.sql"\n')
        f.write('if [ -f "$DDL_FILE" ]; then\n')
        f.write('    run_sql "$DDL_FILE"\n')
        f.write('    echo "Tables created successfully."\n')
        f.write('else\n')
        f.write('    echo "ERROR: DDL file not found: $DDL_FILE"\n')
        f.write('    exit 1\n')
        f.write('fi\n\n')

        f.write('# Step 2: Load data (if requested)\n')
        f.write('if [ "$INCLUDE_DATA" = true ]; then\n')
        f.write('    echo "Step 2: Loading data..."\n')
        f.write(f'    DATA_FILE="$SCRIPT_DIR/02_all_tables_data_{timestamp}.sql"\n')
        f.write('    if [ -f "$DATA_FILE" ]; then\n')
        f.write('        run_sql "$DATA_FILE"\n')
        f.write('        echo "Data loaded successfully."\n')
        f.write('    else\n')
        f.write('        echo "WARNING: Data file not found: $DATA_FILE"\n')
        f.write('    fi\n')
        f.write('else\n')
        f.write('    echo "Step 2: Skipping data load (use --include-data to load data)"\n')
        f.write('fi\n\n')

        f.write('echo ""\n')
        f.write('echo "========================================"\n')
        f.write('echo "Deployment Complete!"\n')
        f.write('echo "========================================"\n')

    # Make script executable
    deploy_script.chmod(0o755)
    logger.info(f"Written: {deploy_script}")

    return output_dir


def main():
    parser = argparse.ArgumentParser(
        description='Extract DDL from SIT database for UAT migration'
    )
    parser.add_argument(
        '--host',
        default=os.environ.get('SIT_IMPALA_HOST', 'localhost'),
        help='SIT Impala host'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=int(os.environ.get('SIT_IMPALA_PORT', '21050')),
        help='SIT Impala port'
    )
    parser.add_argument(
        '--auth',
        default=os.environ.get('SIT_IMPALA_AUTH', 'NOSASL'),
        choices=['NOSASL', 'GSSAPI', 'LDAP'],
        help='Authentication method'
    )
    parser.add_argument(
        '--username',
        default=os.environ.get('SIT_IMPALA_USER'),
        help='Username (for LDAP auth)'
    )
    parser.add_argument(
        '--password',
        default=os.environ.get('SIT_IMPALA_PASSWORD'),
        help='Password (for LDAP auth)'
    )
    parser.add_argument(
        '--tables',
        help='Comma-separated list of tables to extract (default: all)'
    )
    parser.add_argument(
        '--include-data',
        action='store_true',
        help='Include table data in extraction'
    )
    parser.add_argument(
        '--data-limit',
        type=int,
        help='Limit rows per table when extracting data'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=OUTPUT_DIR,
        help='Output directory for generated files'
    )

    args = parser.parse_args()

    # Create extractor
    extractor = SITDDLExtractor(
        host=args.host,
        port=args.port,
        auth=args.auth,
        username=args.username,
        password=args.password
    )

    # Connect
    if not extractor.connect():
        logger.error("Failed to connect to SIT database")
        sys.exit(1)

    try:
        # Get tables
        if args.tables:
            tables = [t.strip() for t in args.tables.split(',')]
        else:
            tables = extractor.get_all_tables()

        if not tables:
            logger.error("No tables found")
            sys.exit(1)

        logger.info(f"Extracting {len(tables)} tables...")

        # Extract DDL and data
        result = extract_ddl(
            extractor,
            tables,
            include_data=args.include_data,
            data_limit=args.data_limit
        )

        # Write output files
        output_dir = write_output_files(result, args.output_dir)

        # Print summary
        print("\n" + "=" * 60)
        print("Extraction Complete!")
        print("=" * 60)
        print(f"Total Tables: {result['summary']['total_tables']}")
        print(f"Successful: {result['summary']['successful']}")
        print(f"Failed: {result['summary']['failed']}")
        print(f"Total Rows: {result['summary']['total_rows']}")
        print(f"\nOutput Directory: {output_dir}")
        print("\nNext Steps:")
        print("  1. Review generated DDL files")
        print("  2. Copy to UAT environment")
        print(f"  3. Run: ./deploy_to_uat.sh --host <uat-host> --port 21050")
        print("=" * 60)

    finally:
        extractor.disconnect()


if __name__ == '__main__':
    main()
