"""
Datasource Management Repository

Data access layer for cis_datasource_mng table.
This table contains metadata about data sources including:
- Source file configuration (separator, columns, headers)
- Target table mapping
- Loading mode and options

Used for metadata-driven file ingestion to Hive external tables.
"""

import logging
from typing import Dict, List, Optional, Any

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger('upload')


class DatasourceRepository:
    """Repository for datasource management operations."""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_datasource_mng'

    # HDFS path for processing date file
    PROCESSING_DATE_FILE = '/mrw/cis/MRA_PC_DATE.txt'

    # Default values for additional columns
    DEFAULT_SRC_SYSTEM = 'cis'
    DEFAULT_SUB_SYSTEM = 'user'
    DEFAULT_DATA_CAT = 'sta'
    DEFAULT_DATA_FRQ = 'adhoc'

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

    def get_datasource_by_name(self, source_name: str) -> Optional[Dict[str, Any]]:
        """
        Get datasource configuration by source_name.

        Args:
            source_name: Name of the source file (e.g., 'CIS_External_upload_format_1.csv')

        Returns:
            Datasource configuration dict or None if not found
        """
        try:
            source_name_escaped = source_name.replace("'", "''")
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE source_name = '{source_name_escaped}'
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting datasource by name: {str(e)}")
            return None

    def get_datasource_by_id(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Get datasource configuration by source_id."""
        try:
            source_id_escaped = source_id.replace("'", "''")
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE source_id = '{source_id_escaped}'
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting datasource by ID: {str(e)}")
            return None

    def get_all_datasources(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all datasource configurations."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TABLE_NAME}
            ORDER BY source_name
            LIMIT {limit}
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []
        except Exception as e:
            logger.error(f"Error getting all datasources: {str(e)}")
            return []

    def get_processing_date_from_hdfs(self) -> Optional[str]:
        """
        Read processing date from HDFS file /mrw/cis/MRA_PC_DATE.txt.

        Returns:
            Date string in format YYYYMMDD (e.g., '20251125') or None if error
        """
        try:
            # Use hdfs command to read the file content
            import subprocess
            result = subprocess.run(
                ['hdfs', 'dfs', '-cat', self.PROCESSING_DATE_FILE],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                date_str = result.stdout.strip()
                # Validate format (should be YYYYMMDD)
                if len(date_str) == 8 and date_str.isdigit():
                    logger.info(f"Read processing date from HDFS: {date_str}")
                    return date_str
                else:
                    logger.warning(f"Invalid date format in {self.PROCESSING_DATE_FILE}: {date_str}")
                    return None
            else:
                logger.error(f"Error reading HDFS file: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout reading HDFS file: {self.PROCESSING_DATE_FILE}")
            return None
        except FileNotFoundError:
            logger.warning("hdfs command not found - using fallback date")
            return None
        except Exception as e:
            logger.error(f"Error reading processing date from HDFS: {str(e)}")
            return None

    def get_processing_date(self) -> str:
        """
        Get processing date for ingestion.
        First tries HDFS file, falls back to current date.

        Returns:
            Date string in YYYYMMDD format
        """
        from datetime import datetime

        # Try to read from HDFS
        hdfs_date = self.get_processing_date_from_hdfs()
        if hdfs_date:
            return hdfs_date

        # Fallback to current date
        current_date = datetime.now().strftime('%Y%m%d')
        logger.info(f"Using current date as processing date: {current_date}")
        return current_date

    def parse_intake_columns(self, datasource: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Parse intake_columns from datasource configuration.

        The intake_columns field can be:
        - A comma-separated string of column names: "col1,col2,col3"
        - A MAP<STRING, STRING> with column name -> type mapping
        - A JSON string

        Args:
            datasource: Datasource configuration dict

        Returns:
            List of column definitions: [{'name': 'col_name', 'type': 'STRING'}, ...]
        """
        columns = []
        intake_columns = datasource.get('intake_columns', '')

        if isinstance(intake_columns, dict):
            # MAP type from Hive - column name -> type mapping
            for col_name, col_type in intake_columns.items():
                columns.append({
                    'name': col_name.strip(),
                    'type': col_type.upper() if col_type else 'STRING'
                })
        elif isinstance(intake_columns, str) and intake_columns:
            # First try to parse as JSON
            try:
                import json
                col_map = json.loads(intake_columns)
                if isinstance(col_map, dict):
                    for col_name, col_type in col_map.items():
                        columns.append({
                            'name': col_name.strip(),
                            'type': col_type.upper() if col_type else 'STRING'
                        })
                    return columns
            except (json.JSONDecodeError, TypeError):
                pass

            # Parse as comma-separated column names (all STRING type)
            col_names = [c.strip() for c in intake_columns.split(',') if c.strip()]
            for col_name in col_names:
                columns.append({
                    'name': col_name,
                    'type': 'STRING'
                })

        return columns

    def get_target_table_columns(self, target_table: str, database: str = None) -> List[Dict[str, str]]:
        """
        Get column definitions from target Hive table.

        Args:
            target_table: Name of the target table
            database: Database name (default: gmp_cis)

        Returns:
            List of column definitions: [{'name': 'col_name', 'type': 'STRING'}, ...]
        """
        try:
            db = database or self.DATABASE
            query = f"DESCRIBE {db}.{target_table}"
            results = impala_manager.execute_query(query, database=db)

            columns = []
            if results:
                for row in results:
                    col_name = row.get('name', row.get('col_name', ''))
                    col_type = row.get('type', row.get('data_type', 'STRING'))
                    if col_name and not col_name.startswith('#'):
                        columns.append({
                            'name': col_name,
                            'type': col_type.upper()
                        })

            return columns

        except Exception as e:
            logger.error(f"Error getting target table columns: {str(e)}")
            return []

    def build_insert_query_with_defaults(
        self,
        datasource: Dict[str, Any],
        source_data_table: str,
        target_table: str,
        processing_date: str = None
    ) -> str:
        """
        Build INSERT query that adds default columns to data from source.

        Maps source CSV columns to target table columns and adds:
        - src_id: from datasource.source_id
        - src_system: 'cis'
        - data_cat: 'sta'
        - data_frq: 'adhoc'
        - processing_date: from MRA_PC_DATE.txt

        Args:
            datasource: Datasource configuration
            source_data_table: Name of staging table with CSV data
            target_table: Name of target Hive external table
            processing_date: Processing date in YYYYMMDD format

        Returns:
            INSERT INTO SELECT query string
        """
        if not processing_date:
            processing_date = self.get_processing_date()

        source_id = datasource.get('source_id', '')
        target_table_name = datasource.get('target_table', target_table)

        # Get intake columns from datasource
        intake_columns = self.parse_intake_columns(datasource)

        # Build source column list
        source_cols = [col['name'] for col in intake_columns]

        # Build target columns (source columns + additional columns)
        target_cols = source_cols + [
            'src_id', 'src_system', 'data_cat', 'data_frq', 'processing_date'
        ]

        # Build SELECT part with default values
        select_parts = []
        for col in source_cols:
            select_parts.append(f"`{col}`")

        # Add default columns
        select_parts.append(f"'{source_id}' as src_id")
        select_parts.append(f"'{self.DEFAULT_SRC_SYSTEM}' as src_system")
        select_parts.append(f"'{self.DEFAULT_DATA_CAT}' as data_cat")
        select_parts.append(f"'{self.DEFAULT_DATA_FRQ}' as data_frq")
        select_parts.append(f"'{processing_date}' as processing_date")

        query = f"""
        INSERT INTO {self.DATABASE}.{target_table_name}
        ({', '.join([f'`{c}`' for c in target_cols])})
        SELECT
            {', '.join(select_parts)}
        FROM {self.DATABASE}.{source_data_table}
        """

        return query

    def ingest_file_to_target_table(
        self,
        datasource: Dict[str, Any],
        staging_table: str,
        processing_date: str = None
    ) -> bool:
        """
        Ingest data from staging table to target table with additional columns.

        Args:
            datasource: Datasource configuration from cis_datasource_mng
            staging_table: Name of staging/external table with uploaded file data
            processing_date: Processing date (optional, reads from HDFS if not provided)

        Returns:
            True if successful, False otherwise
        """
        try:
            if not processing_date:
                processing_date = self.get_processing_date()

            target_table = datasource.get('target_table')
            if not target_table:
                logger.error("No target_table defined in datasource configuration")
                return False

            # Build and execute INSERT query
            insert_query = self.build_insert_query_with_defaults(
                datasource=datasource,
                source_data_table=staging_table,
                target_table=target_table,
                processing_date=processing_date
            )

            logger.info(f"Executing ingestion query to {target_table}")
            success = impala_manager.execute_write(insert_query, database=self.DATABASE)

            if success:
                logger.info(f"Successfully ingested data to {target_table}")
                # Refresh metadata
                impala_manager.execute_write(
                    f"INVALIDATE METADATA {self.DATABASE}.{target_table}",
                    database=self.DATABASE
                )

            return success

        except Exception as e:
            logger.error(f"Error ingesting file to target table: {str(e)}")
            return False


# Singleton instance
datasource_repository = DatasourceRepository()
