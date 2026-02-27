"""
Upload Kudu Repository

Data access layer for file upload operations using Kudu via Impala.
Handles:
- Upload metadata storage (cis_file_upload table)
- Hive external table creation for ingested files
- File ingestion tracking and status management

Supports file formats: CSV, Excel, JSON, Parquet, Text
Storage location: HDFS on Cloudera CML
"""

import logging
import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger('upload')


class UploadKuduRepository:
    """Repository for file upload operations with Kudu via Impala."""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_file_upload'
    EXTERNAL_TABLE_PREFIX = 'ext_'

    # HDFS base path for uploaded files (Cloudera CML)
    HDFS_BASE_PATH = '/user/cis/uploads'

    # Upload Status Constants
    STATUS_PENDING = 'PENDING'           # File uploaded, not yet validated
    STATUS_VALIDATING = 'VALIDATING'     # Validation in progress
    STATUS_VALIDATED = 'VALIDATED'       # Validation passed
    STATUS_VALIDATION_FAILED = 'VALIDATION_FAILED'  # Validation failed
    STATUS_INGESTING = 'INGESTING'       # Ingestion in progress
    STATUS_COMPLETED = 'COMPLETED'       # Successfully ingested to Hive
    STATUS_FAILED = 'FAILED'             # Ingestion failed
    STATUS_CANCELLED = 'CANCELLED'       # Cancelled by user

    ALL_STATUSES = [
        STATUS_PENDING, STATUS_VALIDATING, STATUS_VALIDATED,
        STATUS_VALIDATION_FAILED, STATUS_INGESTING, STATUS_COMPLETED,
        STATUS_FAILED, STATUS_CANCELLED
    ]

    # Supported file formats
    SUPPORTED_FORMATS = {
        'csv': {'mime': 'text/csv', 'hive_format': 'TEXTFILE', 'serde': 'org.apache.hadoop.hive.serde2.OpenCSVSerde'},
        'tsv': {'mime': 'text/tab-separated-values', 'hive_format': 'TEXTFILE', 'serde': 'org.apache.hadoop.hive.serde2.OpenCSVSerde'},
        'txt': {'mime': 'text/plain', 'hive_format': 'TEXTFILE', 'serde': None},
        'json': {'mime': 'application/json', 'hive_format': 'JSONFILE', 'serde': 'org.apache.hive.hcatalog.data.JsonSerDe'},
        'parquet': {'mime': 'application/octet-stream', 'hive_format': 'PARQUET', 'serde': None},
        'xlsx': {'mime': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'hive_format': 'TEXTFILE', 'serde': None},
        'xls': {'mime': 'application/vnd.ms-excel', 'hive_format': 'TEXTFILE', 'serde': None},
    }

    # Maximum file size (100 MB)
    MAX_FILE_SIZE = 100 * 1024 * 1024

    @staticmethod
    def escape_value(val: Any) -> str:
        """Escape value for SQL query."""
        if val is None:
            return 'NULL'
        if isinstance(val, str):
            return f"'{val.replace(chr(39), chr(39)+chr(39))}'"
        if isinstance(val, bool):
            return str(val).lower()
        return str(val)

    @staticmethod
    def to_decimal(val: Any, default: float = 0) -> str:
        """Convert value to decimal string for SQL (no quotes)."""
        if val is None or val == '':
            return str(default)
        try:
            if isinstance(val, str):
                val = val.strip()
                if val == '':
                    return str(default)
                return str(float(val))
            return str(float(val))
        except (ValueError, TypeError):
            return str(default)

    # =========================================================================
    # ID GENERATION
    # =========================================================================

    def get_next_id(self) -> str:
        """Generate unique upload ID."""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        unique_suffix = uuid.uuid4().hex[:8].upper()
        return f"UPL-{timestamp}-{unique_suffix}"

    def generate_table_name(self, file_name: str) -> str:
        """Generate Hive external table name from file name."""
        # Remove extension and clean up name
        base_name = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name
        # Replace special chars with underscore
        clean_name = ''.join(c if c.isalnum() else '_' for c in base_name.lower())
        # Remove consecutive underscores
        while '__' in clean_name:
            clean_name = clean_name.replace('__', '_')
        # Add timestamp for uniqueness
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{self.EXTERNAL_TABLE_PREFIX}{clean_name}_{timestamp}"

    # =========================================================================
    # UPLOAD CRUD OPERATIONS
    # =========================================================================

    def table_exists(self) -> bool:
        """Check if the upload table exists."""
        try:
            query = f"SHOW TABLES IN {self.DATABASE} LIKE '{self.TABLE_NAME}'"
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return bool(results)
        except Exception:
            return False

    def get_all_uploads(
        self,
        limit: int = 100,
        status: Optional[str] = None,
        file_type: Optional[str] = None,
        search: Optional[str] = None,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all uploads with optional filters.
        """
        try:
            # Check if table exists first
            if not self.table_exists():
                logger.warning(f"Table {self.DATABASE}.{self.TABLE_NAME} does not exist. Please create it using sql/ddl/21_file_upload_table.sql")
                return []

            where_clauses = []

            if not include_deleted:
                where_clauses.append("(is_deleted = false OR is_deleted IS NULL)")

            if status:
                status_escaped = status.replace("'", "''")
                where_clauses.append(f"`status` = '{status_escaped}'")

            if file_type:
                file_type_escaped = file_type.replace("'", "''")
                where_clauses.append(f"`file_type` = '{file_type_escaped}'")

            if search:
                search_escaped = search.replace("'", "''").replace('%', '\\%')
                where_clauses.append(f"(LOWER(`file_name`) LIKE LOWER('%{search_escaped}%') OR LOWER(`description`) LIKE LOWER('%{search_escaped}%'))")

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT {limit}
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching uploads: {str(e)}")
            return []

    def get_upload_by_id(self, upload_id: str) -> Optional[Dict[str, Any]]:
        """Get upload by ID."""
        try:
            upload_id_escaped = upload_id.replace("'", "''")
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE upload_id = '{upload_id_escaped}'
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting upload by ID: {str(e)}")
            return None

    def create_upload(self, upload_data: Dict[str, Any], created_by: str) -> Optional[str]:
        """
        Create a new upload record.
        Returns upload_id if successful, None otherwise.
        """
        try:
            upload_id = upload_data.get('upload_id') or self.get_next_id()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Generate target table name
            target_table = self.generate_table_name(upload_data.get('file_name', 'upload'))

            # Build column and value lists
            # Note: 'encoding' is a reserved keyword in Impala, use backticks
            columns = [
                'upload_id', 'file_name', 'original_file_name', 'file_path',
                'file_size', 'file_type', 'mime_type', 'row_count', 'column_count',
                'delimiter', 'has_header', '`encoding`', 'description',
                'target_table_name', 'target_database', 'hdfs_path',
                'schema_json', 'sample_data_json', 'validation_errors_json',
                'status', 'is_deleted',
                'created_by', 'created_at', 'updated_by', 'updated_at'
            ]

            values = [
                self.escape_value(upload_id),
                self.escape_value(upload_data.get('file_name')),
                self.escape_value(upload_data.get('original_file_name', upload_data.get('file_name'))),
                self.escape_value(upload_data.get('file_path', '')),
                self.to_decimal(upload_data.get('file_size', 0)),
                self.escape_value(upload_data.get('file_type', '')),
                self.escape_value(upload_data.get('mime_type', '')),
                self.to_decimal(upload_data.get('row_count', 0)),
                self.to_decimal(upload_data.get('column_count', 0)),
                self.escape_value(upload_data.get('delimiter', ',')),
                str(upload_data.get('has_header', True)).lower(),
                self.escape_value(upload_data.get('encoding', 'UTF-8')),
                self.escape_value(upload_data.get('description', '')),
                self.escape_value(target_table),
                self.escape_value(upload_data.get('target_database', self.DATABASE)),
                self.escape_value(f"{self.HDFS_BASE_PATH}/{upload_id}"),
                self.escape_value(json.dumps(upload_data.get('schema', [])) if upload_data.get('schema') else '[]'),
                self.escape_value(json.dumps(upload_data.get('sample_data', [])) if upload_data.get('sample_data') else '[]'),
                self.escape_value(json.dumps(upload_data.get('validation_errors', [])) if upload_data.get('validation_errors') else '[]'),
                self.escape_value(self.STATUS_PENDING),
                'false',
                self.escape_value(created_by),
                f"'{timestamp}'",
                self.escape_value(created_by),
                f"'{timestamp}'"
            ]

            query = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                logger.info(f"Created upload record: {upload_id}")
                return upload_id

            return None

        except Exception as e:
            logger.error(f"Error creating upload: {str(e)}")
            return None

    def update_upload(self, upload_id: str, update_data: Dict[str, Any], updated_by: str) -> bool:
        """Update upload record."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            set_clauses = []

            # String fields (encoding needs backticks as it's a reserved keyword)
            string_fields = [
                'file_name', 'file_path', 'file_type', 'mime_type',
                'delimiter', 'description', 'status',
                'target_table_name', 'target_database', 'hdfs_path'
            ]

            # Reserved keyword fields that need backticks
            reserved_keyword_fields = ['encoding']

            # Numeric fields
            numeric_fields = ['file_size', 'row_count', 'column_count']

            # Boolean fields
            boolean_fields = ['has_header', 'is_deleted']

            # JSON fields
            json_fields = ['schema_json', 'sample_data_json', 'validation_errors_json']

            for field in string_fields:
                if field in update_data:
                    set_clauses.append(f"`{field}` = {self.escape_value(update_data[field])}")

            for field in reserved_keyword_fields:
                if field in update_data:
                    set_clauses.append(f"`{field}` = {self.escape_value(update_data[field])}")

            for field in numeric_fields:
                if field in update_data:
                    set_clauses.append(f"`{field}` = {self.to_decimal(update_data[field])}")

            for field in boolean_fields:
                if field in update_data:
                    set_clauses.append(f"`{field}` = {str(update_data[field]).lower()}")

            for field in json_fields:
                if field in update_data:
                    json_val = json.dumps(update_data[field]) if isinstance(update_data[field], (dict, list)) else update_data[field]
                    set_clauses.append(f"`{field}` = {self.escape_value(json_val)}")

            # Always update audit fields
            set_clauses.append(f"updated_by = {self.escape_value(updated_by)}")
            set_clauses.append(f"updated_at = '{timestamp}'")

            if not set_clauses:
                return True

            upload_id_escaped = upload_id.replace("'", "''")
            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET {', '.join(set_clauses)}
            WHERE upload_id = '{upload_id_escaped}'
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                logger.info(f"Updated upload: {upload_id}")

            return success

        except Exception as e:
            logger.error(f"Error updating upload: {str(e)}")
            return False

    def update_status(self, upload_id: str, new_status: str, updated_by: str, error_message: str = None) -> bool:
        """Update upload status."""
        update_data = {'status': new_status}
        if error_message:
            update_data['validation_errors_json'] = [{'error': error_message, 'timestamp': datetime.now().isoformat()}]
        return self.update_upload(upload_id, update_data, updated_by)

    def soft_delete(self, upload_id: str, deleted_by: str) -> bool:
        """Soft delete an upload."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            upload_id_escaped = upload_id.replace("'", "''")

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET is_deleted = true,
                status = '{self.STATUS_CANCELLED}',
                updated_by = {self.escape_value(deleted_by)},
                updated_at = '{timestamp}'
            WHERE upload_id = '{upload_id_escaped}'
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                logger.info(f"Soft deleted upload: {upload_id}")

            return success

        except Exception as e:
            logger.error(f"Error soft deleting upload: {str(e)}")
            return False

    # =========================================================================
    # HIVE EXTERNAL TABLE OPERATIONS
    # =========================================================================

    def create_external_table(
        self,
        table_name: str,
        columns: List[Dict[str, str]],
        hdfs_path: str,
        file_format: str = 'csv',
        delimiter: str = ',',
        has_header: bool = True,
        database: str = None
    ) -> bool:
        """
        Create Hive external table for ingested file.

        Args:
            table_name: Name for the external table
            columns: List of {'name': 'col_name', 'type': 'STRING'} dicts
            hdfs_path: HDFS path where data files are stored
            file_format: csv, json, parquet, etc.
            delimiter: Field delimiter for CSV/TSV
            has_header: Whether file has header row
            database: Target database (default: gmp_cis)
        """
        try:
            db = database or self.DATABASE
            format_config = self.SUPPORTED_FORMATS.get(file_format.lower(), self.SUPPORTED_FORMATS['csv'])

            # Build column definitions
            column_defs = []
            for col in columns:
                col_name = col.get('name', '').replace(' ', '_').replace('-', '_')
                col_type = col.get('type', 'STRING').upper()
                if col_name:
                    # Escape column names with backticks
                    column_defs.append(f"`{col_name}` {col_type}")

            if not column_defs:
                logger.error("No columns defined for external table")
                return False

            # Build CREATE TABLE statement
            create_sql = f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {db}.{table_name} (
                {', '.join(column_defs)}
            )
            """

            # Add ROW FORMAT for CSV/TSV
            if file_format.lower() in ['csv', 'tsv']:
                delim_char = '\\t' if file_format.lower() == 'tsv' else delimiter
                create_sql += f"""
                ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
                WITH SERDEPROPERTIES (
                    'separatorChar' = '{delim_char}',
                    'quoteChar' = '"',
                    'escapeChar' = '\\\\'
                )
                """
            elif file_format.lower() == 'json':
                create_sql += """
                ROW FORMAT SERDE 'org.apache.hive.hcatalog.data.JsonSerDe'
                """

            # Add storage format and location
            create_sql += f"""
            STORED AS {format_config['hive_format']}
            LOCATION '{hdfs_path}'
            """

            # Add table properties
            create_sql += f"""
            TBLPROPERTIES (
                'skip.header.line.count' = '{1 if has_header else 0}',
                'serialization.null.format' = '',
                'created_by' = 'cis_upload_module',
                'created_at' = '{datetime.now().isoformat()}'
            )
            """

            success = impala_manager.execute_write(create_sql, database=db)

            if success:
                logger.info(f"Created external table: {db}.{table_name}")
                # Refresh table metadata
                impala_manager.execute_write(f"INVALIDATE METADATA {db}.{table_name}", database=db)

            return success

        except Exception as e:
            logger.error(f"Error creating external table: {str(e)}")
            return False

    def drop_external_table(self, table_name: str, database: str = None) -> bool:
        """Drop Hive external table (does not delete data files)."""
        try:
            db = database or self.DATABASE
            query = f"DROP TABLE IF EXISTS {db}.{table_name}"
            success = impala_manager.execute_write(query, database=db)

            if success:
                logger.info(f"Dropped external table: {db}.{table_name}")

            return success

        except Exception as e:
            logger.error(f"Error dropping external table: {str(e)}")
            return False

    def get_table_preview(self, table_name: str, database: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get preview data from external table."""
        try:
            db = database or self.DATABASE
            query = f"SELECT * FROM {db}.{table_name} LIMIT {limit}"
            results = impala_manager.execute_query(query, database=db)
            return results if results else []
        except Exception as e:
            logger.error(f"Error getting table preview: {str(e)}")
            return []

    def get_table_row_count(self, table_name: str, database: str = None) -> int:
        """Get row count from external table."""
        try:
            db = database or self.DATABASE
            query = f"SELECT COUNT(*) as cnt FROM {db}.{table_name}"
            results = impala_manager.execute_query(query, database=db)
            if results:
                return int(results[0].get('cnt', 0))
            return 0
        except Exception as e:
            logger.error(f"Error getting row count: {str(e)}")
            return 0

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_upload_statistics(self) -> Dict[str, Any]:
        """Get upload statistics for dashboard."""
        try:
            # Check if table exists first
            if not self.table_exists():
                logger.warning(f"Table {self.DATABASE}.{self.TABLE_NAME} does not exist")
                return {
                    'total_uploads': 0,
                    'pending': 0,
                    'completed': 0,
                    'failed': 0,
                    'total_size_bytes': 0,
                    'total_rows': 0,
                    'status_breakdown': {},
                    'file_type_breakdown': {}
                }

            query = f"""
            SELECT
                status,
                file_type,
                COUNT(*) as count,
                SUM(file_size) as total_size,
                SUM(row_count) as total_rows
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE is_deleted = false OR is_deleted IS NULL
            GROUP BY status, file_type
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            stats = {
                'total_uploads': 0,
                'pending': 0,
                'completed': 0,
                'failed': 0,
                'total_size_bytes': 0,
                'total_rows': 0,
                'status_breakdown': {},
                'file_type_breakdown': {}
            }

            if results:
                for row in results:
                    status = row.get('status', 'Unknown')
                    file_type = row.get('file_type', 'Unknown')
                    count = int(row.get('count', 0))
                    size = int(row.get('total_size', 0) or 0)
                    rows = int(row.get('total_rows', 0) or 0)

                    stats['total_uploads'] += count
                    stats['total_size_bytes'] += size
                    stats['total_rows'] += rows

                    stats['status_breakdown'][status] = stats['status_breakdown'].get(status, 0) + count
                    stats['file_type_breakdown'][file_type] = stats['file_type_breakdown'].get(file_type, 0) + count

                    if status == self.STATUS_PENDING:
                        stats['pending'] += count
                    elif status == self.STATUS_COMPLETED:
                        stats['completed'] += count
                    elif status in [self.STATUS_FAILED, self.STATUS_VALIDATION_FAILED]:
                        stats['failed'] += count

            return stats

        except Exception as e:
            logger.error(f"Error getting upload statistics: {str(e)}")
            return {
                'total_uploads': 0,
                'pending': 0,
                'completed': 0,
                'failed': 0,
                'total_size_bytes': 0,
                'total_rows': 0,
                'status_breakdown': {},
                'file_type_breakdown': {}
            }


# Singleton instance
upload_kudu_repository = UploadKuduRepository()
