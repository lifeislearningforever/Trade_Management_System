#!/usr/bin/env python3
"""
SIT to UAT Database Migration Script - DDL Extraction

This script connects to SIT Impala/Kudu database and extracts:
1. Table DDL (CREATE TABLE statements)
2. Table data (INSERT statements) - optional
3. Generates migration files for UAT deployment

Supports two modes:
1. PyHive connection (Python library)
2. impala-shell (command line tool) - recommended for Kerberos

Usage:
    # Using impala-shell (recommended for Kerberos/CML)
    python extract_sit_ddl.py --use-impala-shell --host sit-impala-host

    # Using impala-shell with Kerberos
    python extract_sit_ddl.py --use-impala-shell --host sit-impala-host --kerberos

    # Using PyHive (local Docker)
    python extract_sit_ddl.py --host localhost --port 21050

    # Extract DDL and data
    python extract_sit_ddl.py --use-impala-shell --host sit-impala-host --include-data

    # Extract specific tables
    python extract_sit_ddl.py --use-impala-shell --host sit-impala-host --tables cis_trade,cis_portfolio

Environment Variables:
    SIT_IMPALA_HOST: SIT Impala host (default: localhost)
    SIT_IMPALA_PORT: SIT Impala port (default: 21050)
    SIT_IMPALA_AUTH: Authentication method (NOSASL, GSSAPI, LDAP)
    KRB5_CONFIG: Kerberos config file path (for Kerberos auth)
    KRB5CCNAME: Kerberos credential cache path
"""

import os
import re
import sys
import argparse
import logging
import subprocess
import tempfile
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default database name — used only as the CLI default for --source-database.
# The extractor classes take the database as a constructor argument now (not
# this module constant) so source and target can genuinely differ, which is
# the whole point of this script when the target environment (e.g. a new SIT
# database) is named differently from the source.
DATABASE = 'gmp_cis'

# Output directory
OUTPUT_DIR = Path(__file__).parent / 'output'


def requalify_ddl(ddl: str, source_db: str, target_db: str) -> str:
    """
    Rewrite `source_db.table` qualifiers embedded in extracted DDL text (Impala's
    SHOW CREATE TABLE always fully-qualifies the table name in its output) to
    `target_db.table`, so the generated DDL file can be deployed straight into a
    differently-named target database instead of requiring a manual find/replace
    on the output files first.
    """
    if not ddl or source_db == target_db:
        return ddl
    return re.sub(rf'\b{re.escape(source_db)}\.', f'{target_db}.', ddl)


def ensure_if_not_exists(ddl: str) -> str:
    """
    Insert IF NOT EXISTS after CREATE [EXTERNAL] TABLE if not already present,
    so re-running the generated DDL against a target that already has some of
    these tables doesn't error out. Used as the default (non-destructive)
    alternative to the old unconditional DROP TABLE IF EXISTS + CREATE TABLE.
    """
    if not ddl or re.search(r'(?i)create\s+(external\s+)?table\s+if\s+not\s+exists', ddl):
        return ddl
    return re.sub(
        r'(?i)^(CREATE\s+(?:EXTERNAL\s+)?TABLE)\s+',
        r'\1 IF NOT EXISTS ',
        ddl,
        count=1,
    )


class ImpalaShellExtractor:
    """Extract DDL and data using impala-shell command line tool.

    This is the recommended approach for Kerberos/CML environments.
    """

    def __init__(
        self,
        host: str = 'localhost',
        port: Optional[int] = None,
        use_kerberos: bool = False,
        use_ssl: bool = False,
        principal: str = None,
        ca_cert: str = None,
        database: str = DATABASE,
    ):
        self.host = host
        # None (no --port given) means: don't pass a port to impala-shell at
        # all, let it use its own built-in default. Different Impala clusters
        # expose different default ports for the impala-shell CLI (21000 vs
        # 21050 depending on deployment) -- forcing a hardcoded default here
        # broke a real environment where only `-i host` (no port) connects.
        self.port = port
        self.use_kerberos = use_kerberos
        self.use_ssl = use_ssl
        self.principal = principal
        self.ca_cert = ca_cert
        self.database = database

    def _build_impala_shell_cmd(self, query: str = None, query_file: str = None) -> List[str]:
        """Build impala-shell command with appropriate flags."""
        cmd = ['impala-shell']

        # Connection -- only append :port when one was explicitly given.
        cmd.extend(['-i', f'{self.host}:{self.port}' if self.port else self.host])

        # Database
        cmd.extend(['-d', self.database])

        # Kerberos authentication
        if self.use_kerberos:
            cmd.append('-k')  # Use Kerberos authentication
            if self.principal:
                cmd.extend(['--principal', self.principal])

        # SSL
        if self.use_ssl:
            cmd.append('--ssl')
            if self.ca_cert:
                cmd.extend(['--ca_cert', self.ca_cert])

        # Output format
        cmd.extend(['-B'])  # Batch mode (no pretty printing)
        cmd.extend(['--output_delimiter', '\t'])  # Tab-delimited

        # Query
        if query:
            cmd.extend(['-q', query])
        elif query_file:
            cmd.extend(['-f', query_file])

        return cmd

    def _execute_query(self, query: str) -> Tuple[bool, List[str], str]:
        """Execute a query using impala-shell and return results."""
        try:
            cmd = self._build_impala_shell_cmd(query=query)

            # stdout/stderr=PIPE + universal_newlines instead of capture_output/text
            # (both Python 3.7+ only) -- this environment runs impala-shell under
            # Python 3.6.8.
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                return False, [], result.stderr

            # Parse output lines
            lines = [line for line in result.stdout.strip().split('\n') if line]
            return True, lines, ''

        except subprocess.TimeoutExpired:
            return False, [], 'Query timed out after 5 minutes'
        except FileNotFoundError:
            return False, [], 'impala-shell command not found. Please install Impala shell.'
        except Exception as e:
            return False, [], str(e)

    def connect(self) -> bool:
        """Test connection to Impala."""
        logger.info(
            f"Testing connection to {self.host}"
            f"{':' + str(self.port) if self.port else ''} using impala-shell"
        )
        if self.use_kerberos:
            logger.info("Using Kerberos authentication")

        success, _, error = self._execute_query("SELECT 1")
        if success:
            logger.info("Successfully connected to Impala")
            return True
        else:
            logger.error(f"Failed to connect: {error}")
            return False

    def disconnect(self):
        """No persistent connection to close."""
        pass

    def get_all_tables(self) -> List[str]:
        """Get all tables in the source database."""
        success, lines, error = self._execute_query(f"SHOW TABLES IN {self.database}")
        if success:
            tables = [line.strip() for line in lines if line.strip()]
            logger.info(f"Found {len(tables)} tables in {self.database}")
            return sorted(tables)
        else:
            logger.error(f"Error getting tables: {error}")
            return []

    def get_table_ddl(self, table_name: str) -> Optional[str]:
        """Get CREATE TABLE statement for a table."""
        success, lines, error = self._execute_query(
            f"SHOW CREATE TABLE {self.database}.{table_name}"
        )
        if success:
            ddl = '\n'.join(lines)
            # impala-shell's batch (-B) delimited output wraps STRING column
            # values in double quotes (doubling any embedded "), and SHOW CREATE
            # TABLE returns the whole multi-line DDL as one STRING field -- undo
            # that quoting here, or every generated CREATE statement in the
            # output .sql file fails with "Encountered: STRING LITERAL".
            if ddl.startswith('"') and ddl.endswith('"'):
                ddl = ddl[1:-1].replace('""', '"')
            return ddl
        else:
            logger.error(f"Error getting DDL for {table_name}: {error}")
            return None

    def get_table_columns(self, table_name: str) -> List[Dict[str, str]]:
        """Get column information for a table."""
        success, lines, error = self._execute_query(
            f"DESCRIBE {self.database}.{table_name}"
        )
        if success:
            columns = []
            for line in lines:
                parts = line.split('\t')
                if len(parts) >= 2:
                    columns.append({
                        'name': parts[0].strip(),
                        'type': parts[1].strip(),
                        'comment': parts[2].strip() if len(parts) > 2 else ''
                    })
            return columns
        else:
            logger.error(f"Error getting columns for {table_name}: {error}")
            return []

    def get_table_row_count(self, table_name: str) -> int:
        """Get row count for a table."""
        success, lines, error = self._execute_query(
            f"SELECT COUNT(*) FROM {self.database}.{table_name}"
        )
        if success and lines:
            try:
                return int(lines[0].strip())
            except ValueError:
                return 0
        return 0

    def get_table_data(self, table_name: str, limit: int = None) -> List[Dict[str, Any]]:
        """Get data from a table."""
        # First get columns
        columns = self.get_table_columns(table_name)
        if not columns:
            return []

        col_names = [col['name'] for col in columns]

        query = f"SELECT * FROM {self.database}.{table_name}"
        if limit:
            query += f" LIMIT {limit}"

        success, lines, error = self._execute_query(query)
        if success:
            rows = []
            for line in lines:
                values = line.split('\t')
                if len(values) == len(col_names):
                    row = {}
                    for i, col_name in enumerate(col_names):
                        val = values[i].strip()
                        row[col_name] = None if val == 'NULL' or val == '' else val
                    rows.append(row)
            return rows
        else:
            logger.error(f"Error getting data for {table_name}: {error}")
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
            return str(value)

        # Boolean
        if 'boolean' in col_type_lower or 'bool' in col_type_lower:
            return 'true' if str(value).lower() in ('true', '1', 'yes') else 'false'

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
        batch_size: int = 100,
        target_database: str = None,
    ) -> List[str]:
        """Generate INSERT/UPSERT statements for table data.

        target_database: database the UPSERT should write into. Defaults to
        self.database (source == target) for backward compatibility, but is
        normally the differently-named target database passed by extract_ddl().
        """
        if not data:
            return []

        target_db = target_database or self.database
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

            stmt = f"UPSERT INTO {target_db}.{table_name} ({', '.join(col_names)})\nVALUES\n"
            stmt += ',\n'.join(values_list) + ";"

            statements.append(stmt)

        return statements


class PyHiveExtractor:
    """Extract DDL and data using PyHive library.

    Use this for local Docker development or non-Kerberos environments.
    """

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 21050,
        auth: str = 'NOSASL',
        username: str = None,
        password: str = None,
        database: str = DATABASE,
    ):
        self.host = host
        self.port = port
        self.auth = auth
        self.username = username
        self.password = password
        self.database = database
        self.connection = None
        self.cursor = None

    def connect(self) -> bool:
        """Connect to SIT Impala using PyHive."""
        try:
            from pyhive import hive

            logger.info(f"Connecting to Impala at {self.host}:{self.port} using PyHive")

            conn_params = {
                'host': self.host,
                'port': self.port,
                'auth': self.auth,
                'database': self.database
            }

            if self.username:
                conn_params['username'] = self.username
            if self.password:
                conn_params['password'] = self.password

            self.connection = hive.Connection(**conn_params)
            self.cursor = self.connection.cursor()

            # Test connection
            self.cursor.execute("SELECT 1")
            logger.info("Successfully connected to Impala")
            return True

        except ImportError:
            logger.error("PyHive not installed. Run: pip install pyhive thrift thrift-sasl")
            return False
        except Exception as e:
            logger.error(f"Failed to connect: {str(e)}")
            return False

    def disconnect(self):
        """Close connection."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logger.info("Disconnected from Impala")

    def get_all_tables(self) -> List[str]:
        """Get all tables in the source database."""
        try:
            self.cursor.execute(f"SHOW TABLES IN {self.database}")
            tables = [row[0] for row in self.cursor.fetchall()]
            logger.info(f"Found {len(tables)} tables in {self.database}")
            return sorted(tables)
        except Exception as e:
            logger.error(f"Error getting tables: {str(e)}")
            return []

    def get_table_ddl(self, table_name: str) -> Optional[str]:
        """Get CREATE TABLE statement for a table."""
        try:
            self.cursor.execute(f"SHOW CREATE TABLE {self.database}.{table_name}")
            result = self.cursor.fetchall()
            if result:
                ddl = '\n'.join([row[0] for row in result])
                return ddl
            return None
        except Exception as e:
            logger.error(f"Error getting DDL for {table_name}: {str(e)}")
            return None

    def get_table_columns(self, table_name: str) -> List[Dict[str, str]]:
        """Get column information for a table."""
        try:
            self.cursor.execute(f"DESCRIBE {self.database}.{table_name}")
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
            self.cursor.execute(f"SELECT COUNT(*) FROM {self.database}.{table_name}")
            result = self.cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting row count for {table_name}: {str(e)}")
            return 0

    def get_table_data(self, table_name: str, limit: int = None) -> List[Dict[str, Any]]:
        """Get data from a table."""
        try:
            query = f"SELECT * FROM {self.database}.{table_name}"
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

        if 'string' in col_type_lower or 'varchar' in col_type_lower or 'char' in col_type_lower:
            escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
            return f"'{escaped}'"

        if any(t in col_type_lower for t in ['int', 'bigint', 'smallint', 'tinyint', 'decimal', 'double', 'float']):
            return str(value)

        if 'boolean' in col_type_lower or 'bool' in col_type_lower:
            return 'true' if value else 'false'

        if 'timestamp' in col_type_lower or 'date' in col_type_lower:
            return f"'{value}'"

        escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
        return f"'{escaped}'"

    def generate_insert_statements(
        self,
        table_name: str,
        columns: List[Dict[str, str]],
        data: List[Dict[str, Any]],
        batch_size: int = 100,
        target_database: str = None,
    ) -> List[str]:
        """Generate INSERT/UPSERT statements for table data.

        target_database: database the UPSERT should write into. Defaults to
        self.database (source == target) for backward compatibility, but is
        normally the differently-named target database passed by extract_ddl().
        """
        if not data:
            return []

        target_db = target_database or self.database
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

            stmt = f"UPSERT INTO {target_db}.{table_name} ({', '.join(col_names)})\nVALUES\n"
            stmt += ',\n'.join(values_list) + ";"

            statements.append(stmt)

        return statements


def extract_ddl(
    extractor,
    tables: List[str],
    include_data: bool = False,
    data_limit: int = None,
    target_database: str = None,
    drop_existing: bool = False,
) -> Dict[str, Any]:
    """
    Extract DDL and optionally data for all tables.

    target_database: if different from extractor.database (the source), every
    extracted DDL statement is requalified from source_db.table to
    target_db.table (Impala's SHOW CREATE TABLE always fully-qualifies the
    name), and UPSERT data statements are generated against target_database
    too. Defaults to the source database (no requalification) if not given.

    drop_existing: if False (default), CREATE TABLE statements get IF NOT
    EXISTS injected instead of being preceded by an unconditional
    DROP TABLE IF EXISTS -- safe to re-run against a target that already has
    some of these tables. Set True to restore the old drop-and-recreate
    behaviour.
    """
    source_db = extractor.database
    target_db = target_database or source_db

    result = {
        'timestamp': datetime.now().isoformat(),
        'source_database': source_db,
        'target_database': target_db,
        'drop_existing': drop_existing,
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
            # Get DDL, requalified to the target database name and (unless
            # drop_existing) made idempotent with IF NOT EXISTS.
            ddl = extractor.get_table_ddl(table_name)
            if ddl:
                ddl = requalify_ddl(ddl, source_db, target_db)
                if not drop_existing:
                    ddl = ensure_if_not_exists(ddl)
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
                        table_name, columns, data, target_database=target_db
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


def write_output_files(result: Dict[str, Any], output_dir: Path, use_kerberos: bool = False):
    """Write DDL and data files."""

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    target_db = result.get('target_database') or result.get('database') or DATABASE
    source_db = result.get('source_database', target_db)
    drop_existing = result.get('drop_existing', False)
    drop_line = (
        (lambda t: f"DROP TABLE IF EXISTS {target_db}.{t};\n\n")
        if drop_existing else (lambda t: "")
    )

    # 1. Write combined DDL file
    ddl_file = output_dir / f'01_all_tables_ddl_{timestamp}.sql'
    with open(ddl_file, 'w') as f:
        f.write(f"-- ============================================\n")
        f.write(f"-- {target_db} Database DDL\n")
        f.write(f"-- Source database : {source_db}\n")
        f.write(f"-- Target database  : {target_db}\n")
        f.write(f"-- Generated: {result['timestamp']}\n")
        f.write(f"-- Tables: {result['summary']['total_tables']}\n")
        f.write(f"-- drop_existing={drop_existing} (tables use IF NOT EXISTS when False)\n")
        f.write(f"-- ============================================\n\n")

        f.write(f"-- Create database if not exists\n")
        f.write(f"CREATE DATABASE IF NOT EXISTS {target_db};\n")
        f.write(f"USE {target_db};\n\n")

        for table_name, table_info in result['tables'].items():
            if table_info['ddl']:
                f.write(f"-- ----------------------------------------\n")
                f.write(f"-- Table: {table_name}\n")
                f.write(f"-- Rows: {table_info['row_count']}\n")
                f.write(f"-- ----------------------------------------\n")
                f.write(drop_line(table_name))
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
                f.write(drop_line(table_name))
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
            f.write(f"-- {target_db} Database Data - Extracted from {source_db}\n")
            f.write(f"-- Generated: {result['timestamp']}\n")
            f.write(f"-- ============================================\n\n")
            f.write(f"USE {target_db};\n\n")

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
        f.write(f"Source Database: {source_db}\n")
        f.write(f"Target Database: {target_db}\n\n")

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

    # 6. Write UAT deployment script with Kerberos support
    deploy_script = output_dir / f'deploy_to_uat.sh'
    with open(deploy_script, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write("#\n")
        f.write("# UAT Deployment Script\n")
        f.write(f"# Generated: {result['timestamp']}\n")
        f.write("#\n")
        f.write("# Usage:\n")
        f.write("#   # Without Kerberos (local/Docker)\n")
        f.write("#   ./deploy_to_uat.sh --host uat-impala-host --port 21050\n")
        f.write("#\n")
        f.write("#   # With Kerberos (CML/Production)\n")
        f.write("#   ./deploy_to_uat.sh --host uat-impala-host --kerberos\n")
        f.write("#\n")
        f.write("#   # With Kerberos and custom principal\n")
        f.write("#   ./deploy_to_uat.sh --host uat-impala-host --kerberos --principal impala/host@REALM\n")
        f.write("#\n")
        f.write("#   # Include data\n")
        f.write("#   ./deploy_to_uat.sh --host uat-impala-host --kerberos --include-data\n")
        f.write("#\n\n")

        f.write('set -e\n\n')

        f.write('# Default values\n')
        f.write('UAT_HOST="${UAT_IMPALA_HOST:-localhost}"\n')
        # Left empty unless --port/UAT_IMPALA_PORT is set -- omitting the port
        # lets impala-shell fall back to its own built-in default, which is
        # what some clusters actually require (forcing 21050 breaks others).
        f.write('UAT_PORT="${UAT_IMPALA_PORT:-}"\n')
        f.write('USE_KERBEROS=false\n')
        f.write('USE_SSL=false\n')
        f.write('PRINCIPAL=""\n')
        f.write('CA_CERT=""\n')
        f.write('INCLUDE_DATA=false\n')
        f.write('SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n\n')

        f.write('# Parse arguments\n')
        f.write('while [[ $# -gt 0 ]]; do\n')
        f.write('    case $1 in\n')
        f.write('        --host) UAT_HOST="$2"; shift 2 ;;\n')
        f.write('        --port) UAT_PORT="$2"; shift 2 ;;\n')
        f.write('        --kerberos|-k) USE_KERBEROS=true; shift ;;\n')
        f.write('        --ssl) USE_SSL=true; shift ;;\n')
        f.write('        --principal) PRINCIPAL="$2"; shift 2 ;;\n')
        f.write('        --ca-cert) CA_CERT="$2"; shift 2 ;;\n')
        f.write('        --include-data) INCLUDE_DATA=true; shift ;;\n')
        f.write('        --help|-h)\n')
        f.write('            echo "Usage: $0 [options]"\n')
        f.write('            echo ""\n')
        f.write('            echo "Options:"\n')
        f.write('            echo "  --host HOST       UAT Impala host"\n')
        f.write('            echo "  --port PORT       UAT Impala port (default: unset -- impala-shell"\n')
        f.write('            echo "                    uses its own built-in default)"\n')
        f.write('            echo "  --kerberos, -k    Use Kerberos authentication"\n')
        f.write('            echo "  --ssl             Use SSL connection"\n')
        f.write('            echo "  --principal PRINC Kerberos principal"\n')
        f.write('            echo "  --ca-cert FILE    CA certificate for SSL"\n')
        f.write('            echo "  --include-data    Load data as well as DDL"\n')
        f.write('            exit 0\n')
        f.write('            ;;\n')
        f.write('        *) echo "Unknown option: $1"; exit 1 ;;\n')
        f.write('    esac\n')
        f.write('done\n\n')

        f.write('# Build impala-shell command\n')
        f.write('if [ -n "$UAT_PORT" ]; then\n')
        f.write('    IMPALA_CMD="impala-shell -i $UAT_HOST:$UAT_PORT"\n')
        f.write('else\n')
        f.write('    IMPALA_CMD="impala-shell -i $UAT_HOST"\n')
        f.write('fi\n\n')

        f.write('if [ "$USE_KERBEROS" = true ]; then\n')
        f.write('    IMPALA_CMD="$IMPALA_CMD -k"\n')
        f.write('    if [ -n "$PRINCIPAL" ]; then\n')
        f.write('        IMPALA_CMD="$IMPALA_CMD --principal $PRINCIPAL"\n')
        f.write('    fi\n')
        f.write('    \n')
        f.write('    # Check for valid Kerberos ticket\n')
        f.write('    echo "Checking Kerberos ticket..."\n')
        f.write('    if ! klist -s 2>/dev/null; then\n')
        f.write('        echo "ERROR: No valid Kerberos ticket found."\n')
        f.write('        echo "Please run: kinit <username>@<REALM>"\n')
        f.write('        exit 1\n')
        f.write('    fi\n')
        f.write('    klist\n')
        f.write('    echo ""\n')
        f.write('fi\n\n')

        f.write('if [ "$USE_SSL" = true ]; then\n')
        f.write('    IMPALA_CMD="$IMPALA_CMD --ssl"\n')
        f.write('    if [ -n "$CA_CERT" ]; then\n')
        f.write('        IMPALA_CMD="$IMPALA_CMD --ca_cert $CA_CERT"\n')
        f.write('    fi\n')
        f.write('fi\n\n')

        f.write('echo "========================================"\n')
        f.write('echo "UAT Database Deployment"\n')
        f.write('echo "========================================"\n')
        f.write('echo "Host: $UAT_HOST${UAT_PORT:+:$UAT_PORT}"\n')
        f.write('echo "Kerberos: $USE_KERBEROS"\n')
        f.write('echo "SSL: $USE_SSL"\n')
        f.write('echo "Include Data: $INCLUDE_DATA"\n')
        f.write('echo ""\n\n')

        f.write('# Function to run SQL file\n')
        f.write('run_sql() {\n')
        f.write('    local sql_file="$1"\n')
        f.write('    echo "Running: $sql_file"\n')
        f.write('    $IMPALA_CMD -f "$sql_file"\n')
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

    # 7. Write load_data_with_stats.sh -- runs every tables/data/*.sql file
    # individually (rather than one combined data file), logging each run and
    # reporting a per-table + total UPSERT row-count summary at the end.
    load_data_script = output_dir / 'load_data_with_stats.sh'
    with open(load_data_script, 'w') as f:
        f.write(f'''#!/bin/bash
#
# Load Data From data/ Folder -- per-table UPSERT with logging and stats
#
# Runs every .sql file under data/ individually via impala-shell -f (instead
# of the one combined 02_all_tables_data_*.sql file deploy_to_uat.sh uses),
# so a failure on one table doesn't hide progress on the rest, and so you
# get a per-table + total row-count summary at the end.
#
# Tables must already exist (run the DDL / deploy_to_uat.sh Step 1 first).
#
# Usage:
#   ./load_data_with_stats.sh --host <host> [--port <port>] [--kerberos] [--ssl] \\
#       [--database {target_db}] [--principal <princ>] [--ca-cert <file>]
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/data"
LOG_FILE="$SCRIPT_DIR/load_data_$(date +%Y%m%d_%H%M%S).log"

HOST=""
PORT=""
DATABASE="{target_db}"
USE_KERBEROS=false
USE_SSL=false
PRINCIPAL=""
CA_CERT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --host) HOST="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --database) DATABASE="$2"; shift 2 ;;
        --kerberos|-k) USE_KERBEROS=true; shift ;;
        --ssl) USE_SSL=true; shift ;;
        --principal) PRINCIPAL="$2"; shift 2 ;;
        --ca-cert) CA_CERT="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 --host HOST [--port PORT] [--kerberos] [--ssl] [--database DB]"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$HOST" ]; then
    echo "ERROR: --host is required"
    exit 1
fi

if [ ! -d "$DATA_DIR" ]; then
    echo "ERROR: data directory not found: $DATA_DIR (did you run with --include-data?)"
    exit 1
fi

# Build impala-shell command. Port is only appended if given -- omitting it
# lets impala-shell fall back to its own built-in default, which some
# clusters require.
IMPALA_CMD="impala-shell -i $HOST${{PORT:+:$PORT}}"
if [ "$USE_KERBEROS" = true ]; then
    IMPALA_CMD="$IMPALA_CMD -k"
    [ -n "$PRINCIPAL" ] && IMPALA_CMD="$IMPALA_CMD --principal $PRINCIPAL"
    echo "Checking Kerberos ticket..."
    if ! klist -s 2>/dev/null; then
        echo "ERROR: No valid Kerberos ticket found. Run: kinit <username>@<REALM>"
        exit 1
    fi
fi
if [ "$USE_SSL" = true ]; then
    IMPALA_CMD="$IMPALA_CMD --ssl"
    [ -n "$CA_CERT" ] && IMPALA_CMD="$IMPALA_CMD --ca_cert $CA_CERT"
fi
IMPALA_CMD="$IMPALA_CMD -d $DATABASE"

{{
    echo "========================================"
    echo "Data Load -- $(date)"
    echo "Host: $HOST${{PORT:+:$PORT}}  Database: $DATABASE"
    echo "========================================"
}} | tee "$LOG_FILE"

declare -a TABLE_NAMES
declare -a TABLE_ROWS
declare -a TABLE_STATUS

TOTAL_ROWS=0
TOTAL_OK=0
TOTAL_FAIL=0

shopt -s nullglob
FILES=("$DATA_DIR"/*.sql)
if [ ${{#FILES[@]}} -eq 0 ]; then
    echo "No .sql files found in $DATA_DIR" | tee -a "$LOG_FILE"
    exit 1
fi

for f in "${{FILES[@]}}"; do
    table_name="$(basename "$f" .sql)"
    table_name="${{table_name%_data}}"

    {{
        echo ""
        echo "--- $table_name ($f) ---"
    }} | tee -a "$LOG_FILE"

    OUTPUT="$($IMPALA_CMD -f "$f" 2>&1)"
    STATUS=$?
    echo "$OUTPUT" | tee -a "$LOG_FILE"

    # Impala prints a line like "Modified N row(s), M row error(s) in Xs"
    # after a DML statement -- pull the first number out of it. If the
    # installed Impala version phrases this differently, ROWS falls back
    # to "n/a" rather than a misleading 0.
    ROWS=$(echo "$OUTPUT" | grep -oEi 'modified [0-9]+ row' | grep -oE '[0-9]+' | tail -1)
    ROWS=${{ROWS:-n/a}}

    if [ $STATUS -eq 0 ]; then
        TABLE_STATUS+=("OK")
        TOTAL_OK=$((TOTAL_OK + 1))
    else
        TABLE_STATUS+=("FAILED")
        TOTAL_FAIL=$((TOTAL_FAIL + 1))
    fi
    TABLE_NAMES+=("$table_name")
    TABLE_ROWS+=("$ROWS")
    if [[ "$ROWS" =~ ^[0-9]+$ ]]; then
        TOTAL_ROWS=$((TOTAL_ROWS + ROWS))
    fi
done

{{
    echo ""
    echo "========================================"
    echo "Summary"
    echo "========================================"
    printf "%-40s %-15s %-10s\\n" "Table" "Rows Upserted" "Status"
    printf -- '-%.0s' {{1..70}}; echo ""
    for i in "${{!TABLE_NAMES[@]}}"; do
        printf "%-40s %-15s %-10s\\n" "${{TABLE_NAMES[$i]}}" "${{TABLE_ROWS[$i]}}" "${{TABLE_STATUS[$i]}}"
    done
    printf -- '-%.0s' {{1..70}}; echo ""
    echo "Total tables : ${{#TABLE_NAMES[@]}}  (OK: $TOTAL_OK, FAILED: $TOTAL_FAIL)"
    echo "Total rows upserted (parsed): $TOTAL_ROWS"
}} | tee -a "$LOG_FILE"

echo ""
echo "Log saved to: $LOG_FILE"

if [ $TOTAL_FAIL -gt 0 ]; then
    exit 1
fi
''')

    load_data_script.chmod(0o755)
    logger.info(f"Written: {load_data_script}")

    return output_dir


def main():
    parser = argparse.ArgumentParser(
        description='Extract DDL from SIT database for UAT migration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using impala-shell with Kerberos (recommended for CML)
  python extract_sit_ddl.py --use-impala-shell --host sit-impala-host --kerberos

  # Using impala-shell with Kerberos and custom principal
  python extract_sit_ddl.py --use-impala-shell --host sit-impala-host --kerberos --principal impala/host@REALM

  # Using PyHive (local Docker, no Kerberos)
  python extract_sit_ddl.py --host localhost --port 21050

  # Extract with data
  python extract_sit_ddl.py --use-impala-shell --host sit-impala-host --kerberos --include-data

  # Extract specific tables
  python extract_sit_ddl.py --use-impala-shell --host sit-impala-host --tables cis_trade,cis_portfolio

  # Copy all tables into a differently-named SIT database
  python extract_sit_ddl.py --use-impala-shell --host sit-impala-host --kerberos \\
      --source-database gmp_cis --target-database gmp_cis_dev --include-data
        """
    )

    # Connection mode
    parser.add_argument(
        '--use-impala-shell',
        action='store_true',
        help='Use impala-shell command instead of PyHive (recommended for Kerberos)'
    )

    # Connection parameters
    parser.add_argument(
        '--host',
        default=os.environ.get('SIT_IMPALA_HOST', 'localhost'),
        help='SIT Impala host'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=int(os.environ['SIT_IMPALA_PORT']) if os.environ.get('SIT_IMPALA_PORT') else None,
        help='SIT Impala port. In --use-impala-shell mode, omitting this lets '
             'impala-shell fall back to its own built-in default port instead '
             'of forcing one -- some clusters only accept connections on that '
             'default. Required (defaults to 21050) in PyHive mode.'
    )

    # Authentication
    parser.add_argument(
        '--kerberos', '-k',
        action='store_true',
        help='Use Kerberos authentication (for impala-shell mode)'
    )
    parser.add_argument(
        '--principal',
        help='Kerberos principal (e.g., impala/host@REALM)'
    )
    parser.add_argument(
        '--ssl',
        action='store_true',
        help='Use SSL connection'
    )
    parser.add_argument(
        '--ca-cert',
        help='CA certificate file for SSL'
    )

    # PyHive-specific auth (for non-Kerberos)
    parser.add_argument(
        '--auth',
        default=os.environ.get('SIT_IMPALA_AUTH', 'NOSASL'),
        choices=['NOSASL', 'GSSAPI', 'LDAP'],
        help='Authentication method (for PyHive mode)'
    )
    parser.add_argument(
        '--username',
        default=os.environ.get('SIT_IMPALA_USER'),
        help='Username (for LDAP auth with PyHive)'
    )
    parser.add_argument(
        '--password',
        default=os.environ.get('SIT_IMPALA_PASSWORD'),
        help='Password (for LDAP auth with PyHive)'
    )

    # Table selection
    parser.add_argument(
        '--tables',
        help='Comma-separated list of tables to extract (default: all)'
    )

    # Database naming (source vs target)
    parser.add_argument(
        '--source-database',
        default=os.environ.get('SIT_IMPALA_DB', DATABASE),
        help=f'Database to read DDL/data from (default: {DATABASE})'
    )
    parser.add_argument(
        '--target-database',
        default=None,
        help='Database name to generate DDL/data for (default: same as --source-database). '
             'Use this to restore into a differently-named SIT database.'
    )
    parser.add_argument(
        '--drop-existing',
        action='store_true',
        help='Emit unconditional DROP TABLE IF EXISTS before each CREATE TABLE '
             '(destructive; default is safe CREATE TABLE IF NOT EXISTS)'
    )

    # Data extraction
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

    # Output
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=OUTPUT_DIR,
        help='Output directory for generated files'
    )

    args = parser.parse_args()

    # Create appropriate extractor
    if args.use_impala_shell:
        extractor = ImpalaShellExtractor(
            host=args.host,
            port=args.port,
            use_kerberos=args.kerberos,
            use_ssl=args.ssl,
            principal=args.principal,
            ca_cert=args.ca_cert,
            database=args.source_database
        )
    else:
        # PyHive needs a concrete port (unlike impala-shell, it can't fall
        # back to a CLI default) -- 21050 matches the documented local Docker
        # setup (see CLAUDE.md).
        extractor = PyHiveExtractor(
            host=args.host,
            port=args.port or 21050,
            auth=args.auth,
            username=args.username,
            password=args.password,
            database=args.source_database
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

        target_database = args.target_database or args.source_database
        logger.info(
            f"Extracting {len(tables)} tables from '{args.source_database}' "
            f"-> '{target_database}'..."
        )

        # Extract DDL and data
        result = extract_ddl(
            extractor,
            tables,
            include_data=args.include_data,
            data_limit=args.data_limit,
            target_database=target_database,
            drop_existing=args.drop_existing
        )

        # Write output files
        output_dir = write_output_files(result, args.output_dir, use_kerberos=args.kerberos)

        # Print summary
        print("\n" + "=" * 60)
        print("Extraction Complete!")
        print("=" * 60)
        print(f"Source Database: {result['source_database']}")
        print(f"Target Database: {result['target_database']}")
        print(f"Total Tables: {result['summary']['total_tables']}")
        print(f"Successful: {result['summary']['successful']}")
        print(f"Failed: {result['summary']['failed']}")
        print(f"Total Rows: {result['summary']['total_rows']}")
        print(f"\nOutput Directory: {output_dir}")
        print("\nNext Steps:")
        print("  1. Review generated DDL files")
        print("  2. Copy to UAT environment")
        if args.kerberos:
            print("  3. Run: ./deploy_to_uat.sh --host <uat-host> --kerberos")
        else:
            print("  3. Run: ./deploy_to_uat.sh --host <uat-host> --port 21050")
        print("=" * 60)

    finally:
        extractor.disconnect()


if __name__ == '__main__':
    main()
