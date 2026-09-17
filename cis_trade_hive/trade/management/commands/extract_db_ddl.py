"""
Django management command to extract DDL from database for migration.

Usage:
    # Extract all tables DDL
    python manage.py extract_db_ddl

    # Extract specific tables
    python manage.py extract_db_ddl --tables cis_trade,cis_portfolio

    # Extract DDL and data
    python manage.py extract_db_ddl --include-data

    # Specify output directory
    python manage.py extract_db_ddl --output-dir /path/to/output
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from core.repositories.impala_connection import impala_manager


class Command(BaseCommand):
    help = 'Extract DDL from gmp_cis database for SIT to UAT migration'

    DATABASE = settings.IMPALA_CONFIG['DATABASE']

    def add_arguments(self, parser):
        parser.add_argument(
            '--tables',
            type=str,
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
            type=str,
            default='scripts/db_migration/output',
            help='Output directory for generated files'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Database DDL Extraction'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        # Get tables to extract
        if options['tables']:
            tables = [t.strip() for t in options['tables'].split(',')]
        else:
            tables = self.get_all_tables()

        if not tables:
            raise CommandError('No tables found in database')

        self.stdout.write(f'Tables to extract: {len(tables)}')

        # Extract DDL and optionally data
        result = self.extract_tables(
            tables,
            include_data=options['include_data'],
            data_limit=options['data_limit']
        )

        # Write output files
        output_dir = Path(options['output_dir'])
        self.write_output_files(result, output_dir)

        # Print summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Extraction Complete!'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f"Total Tables: {result['summary']['total_tables']}")
        self.stdout.write(f"Successful: {result['summary']['successful']}")
        self.stdout.write(f"Failed: {result['summary']['failed']}")
        self.stdout.write(f"Total Rows: {result['summary']['total_rows']}")
        self.stdout.write(f"\nOutput Directory: {output_dir.absolute()}")

    def get_all_tables(self) -> List[str]:
        """Get all tables in gmp_cis database."""
        try:
            query = f"SHOW TABLES IN {self.DATABASE}"
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                return sorted([row.get('name', row.get('tab_name', list(row.values())[0])) for row in results])
            return []
        except Exception as e:
            self.stderr.write(f'Error getting tables: {str(e)}')
            return []

    def get_table_ddl(self, table_name: str) -> Optional[str]:
        """Get CREATE TABLE statement for a table."""
        try:
            query = f"SHOW CREATE TABLE {self.DATABASE}.{table_name}"
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                # Join all rows
                ddl_parts = []
                for row in results:
                    if isinstance(row, dict):
                        ddl_parts.append(list(row.values())[0])
                    else:
                        ddl_parts.append(str(row))
                return '\n'.join(ddl_parts)
            return None
        except Exception as e:
            self.stderr.write(f'Error getting DDL for {table_name}: {str(e)}')
            return None

    def get_table_columns(self, table_name: str) -> List[Dict[str, str]]:
        """Get column information for a table."""
        try:
            query = f"DESCRIBE {self.DATABASE}.{table_name}"
            results = impala_manager.execute_query(query, database=self.DATABASE)
            columns = []
            if results:
                for row in results:
                    if isinstance(row, dict):
                        columns.append({
                            'name': row.get('name', row.get('col_name', '')),
                            'type': row.get('type', row.get('data_type', '')),
                            'comment': row.get('comment', '')
                        })
            return columns
        except Exception as e:
            self.stderr.write(f'Error getting columns for {table_name}: {str(e)}')
            return []

    def get_table_row_count(self, table_name: str) -> int:
        """Get row count for a table."""
        try:
            query = f"SELECT COUNT(*) as cnt FROM {self.DATABASE}.{table_name}"
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and len(results) > 0:
                row = results[0]
                if isinstance(row, dict):
                    return row.get('cnt', 0)
            return 0
        except Exception as e:
            self.stderr.write(f'Error getting row count for {table_name}: {str(e)}')
            return 0

    def get_table_data(self, table_name: str, limit: int = None) -> List[Dict[str, Any]]:
        """Get data from a table."""
        try:
            query = f"SELECT * FROM {self.DATABASE}.{table_name}"
            if limit:
                query += f" LIMIT {limit}"
            return impala_manager.execute_query(query, database=self.DATABASE) or []
        except Exception as e:
            self.stderr.write(f'Error getting data for {table_name}: {str(e)}')
            return []

    def format_value_for_insert(self, value: Any, col_type: str) -> str:
        """Format a value for INSERT statement."""
        if value is None:
            return 'NULL'

        col_type_lower = col_type.lower()

        # String types
        if 'string' in col_type_lower or 'varchar' in col_type_lower or 'char' in col_type_lower:
            escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
            return f"'{escaped}'"

        # Numeric types
        if any(t in col_type_lower for t in ['int', 'bigint', 'smallint', 'tinyint', 'decimal', 'double', 'float']):
            if isinstance(value, Decimal):
                return str(float(value))
            return str(value)

        # Boolean
        if 'boolean' in col_type_lower or 'bool' in col_type_lower:
            return 'true' if value else 'false'

        # Timestamp/Date
        if 'timestamp' in col_type_lower or 'date' in col_type_lower:
            return f"'{value}'"

        # Default: treat as string
        escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
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

            stmt = f"UPSERT INTO {self.DATABASE}.{table_name} ({', '.join(col_names)})\nVALUES\n"
            stmt += ',\n'.join(values_list) + ";"

            statements.append(stmt)

        return statements

    def extract_tables(
        self,
        tables: List[str],
        include_data: bool = False,
        data_limit: int = None
    ) -> Dict[str, Any]:
        """Extract DDL and optionally data for all tables."""

        result = {
            'timestamp': datetime.now().isoformat(),
            'database': self.DATABASE,
            'tables': {},
            'summary': {
                'total_tables': 0,
                'successful': 0,
                'failed': 0,
                'total_rows': 0
            }
        }

        for table_name in tables:
            self.stdout.write(f'Processing: {table_name}')

            table_info = {
                'ddl': None,
                'columns': [],
                'row_count': 0,
                'insert_statements': [],
                'status': 'pending'
            }

            try:
                # Get DDL
                ddl = self.get_table_ddl(table_name)
                if ddl:
                    table_info['ddl'] = ddl
                    table_info['status'] = 'success'
                else:
                    table_info['status'] = 'failed'
                    result['summary']['failed'] += 1
                    continue

                # Get columns
                columns = self.get_table_columns(table_name)
                table_info['columns'] = columns

                # Get row count
                row_count = self.get_table_row_count(table_name)
                table_info['row_count'] = row_count
                result['summary']['total_rows'] += row_count

                # Get data if requested
                if include_data and row_count > 0:
                    self.stdout.write(f'  Extracting data ({row_count} rows)...')
                    data = self.get_table_data(table_name, limit=data_limit)
                    if data:
                        insert_stmts = self.generate_insert_statements(
                            table_name, columns, data
                        )
                        table_info['insert_statements'] = insert_stmts

                result['summary']['successful'] += 1
                self.stdout.write(self.style.SUCCESS(f'  OK ({row_count} rows)'))

            except Exception as e:
                self.stderr.write(f'  Error: {str(e)}')
                table_info['status'] = 'failed'
                table_info['error'] = str(e)
                result['summary']['failed'] += 1

            result['tables'][table_name] = table_info

        result['summary']['total_tables'] = len(tables)
        return result

    def write_output_files(self, result: Dict[str, Any], output_dir: Path):
        """Write DDL and data files."""

        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 1. Write combined DDL file
        ddl_file = output_dir / f'01_all_tables_ddl_{timestamp}.sql'
        with open(ddl_file, 'w') as f:
            f.write(f"-- ============================================\n")
            f.write(f"-- GMP_CIS Database DDL - Extracted\n")
            f.write(f"-- Generated: {result['timestamp']}\n")
            f.write(f"-- Tables: {result['summary']['total_tables']}\n")
            f.write(f"-- ============================================\n\n")

            f.write(f"-- Create database if not exists\n")
            f.write(f"CREATE DATABASE IF NOT EXISTS {self.DATABASE};\n")
            f.write(f"USE {self.DATABASE};\n\n")

            for table_name, table_info in result['tables'].items():
                if table_info['ddl']:
                    f.write(f"-- ----------------------------------------\n")
                    f.write(f"-- Table: {table_name}\n")
                    f.write(f"-- Rows: {table_info['row_count']}\n")
                    f.write(f"-- ----------------------------------------\n")
                    f.write(f"DROP TABLE IF EXISTS {self.DATABASE}.{table_name};\n\n")
                    f.write(table_info['ddl'])
                    if not table_info['ddl'].rstrip().endswith(';'):
                        f.write(";")
                    f.write("\n\n")

        self.stdout.write(f'Written: {ddl_file}')

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
                    f.write(f"DROP TABLE IF EXISTS {self.DATABASE}.{table_name};\n\n")
                    f.write(table_info['ddl'])
                    if not table_info['ddl'].rstrip().endswith(';'):
                        f.write(";")
                    f.write("\n")

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

                self.stdout.write(f'Written: {data_file}')

        # 4. Write combined data file
        if has_data:
            all_data_file = output_dir / f'02_all_tables_data_{timestamp}.sql'
            with open(all_data_file, 'w') as f:
                f.write(f"-- ============================================\n")
                f.write(f"-- GMP_CIS Database Data\n")
                f.write(f"-- Generated: {result['timestamp']}\n")
                f.write(f"-- ============================================\n\n")
                f.write(f"USE {self.DATABASE};\n\n")

                for table_name, table_info in result['tables'].items():
                    if table_info.get('insert_statements'):
                        f.write(f"-- ----------------------------------------\n")
                        f.write(f"-- Data for: {table_name} ({table_info['row_count']} rows)\n")
                        f.write(f"-- ----------------------------------------\n\n")

                        for stmt in table_info['insert_statements']:
                            f.write(stmt)
                            f.write("\n\n")

            self.stdout.write(f'Written: {all_data_file}')

        # 5. Write summary report
        summary_file = output_dir / f'00_migration_summary_{timestamp}.txt'
        with open(summary_file, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("Database Migration Summary\n")
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

        self.stdout.write(f'Written: {summary_file}')

        # 6. Write UAT deployment script
        deploy_script = output_dir / 'deploy_to_uat.sh'
        with open(deploy_script, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("#\n")
            f.write("# UAT Deployment Script\n")
            f.write(f"# Generated: {result['timestamp']}\n")
            f.write("#\n")
            f.write("# Usage:\n")
            f.write("#   ./deploy_to_uat.sh --host uat-impala-host --port 21050\n")
            f.write("#   ./deploy_to_uat.sh --host uat-impala-host --include-data\n")
            f.write("#\n\n")

            f.write('set -e\n\n')

            f.write('UAT_HOST="${UAT_IMPALA_HOST:-localhost}"\n')
            f.write('UAT_PORT="${UAT_IMPALA_PORT:-21050}"\n')
            f.write('INCLUDE_DATA=false\n')
            f.write('SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n\n')

            f.write('while [[ $# -gt 0 ]]; do\n')
            f.write('    case $1 in\n')
            f.write('        --host) UAT_HOST="$2"; shift 2 ;;\n')
            f.write('        --port) UAT_PORT="$2"; shift 2 ;;\n')
            f.write('        --include-data) INCLUDE_DATA=true; shift ;;\n')
            f.write('        *) echo "Unknown option: $1"; exit 1 ;;\n')
            f.write('    esac\n')
            f.write('done\n\n')

            f.write('echo "UAT Deployment"\n')
            f.write('echo "Host: $UAT_HOST:$UAT_PORT"\n\n')

            f.write('# Run DDL\n')
            f.write('echo "Creating tables..."\n')
            f.write(f'impala-shell -i "$UAT_HOST:$UAT_PORT" -f "$SCRIPT_DIR/01_all_tables_ddl_{timestamp}.sql"\n\n')

            f.write('# Run data if requested\n')
            f.write('if [ "$INCLUDE_DATA" = true ]; then\n')
            f.write('    echo "Loading data..."\n')
            f.write(f'    impala-shell -i "$UAT_HOST:$UAT_PORT" -f "$SCRIPT_DIR/02_all_tables_data_{timestamp}.sql"\n')
            f.write('fi\n\n')

            f.write('echo "Deployment complete!"\n')

        deploy_script.chmod(0o755)
        self.stdout.write(f'Written: {deploy_script}')
