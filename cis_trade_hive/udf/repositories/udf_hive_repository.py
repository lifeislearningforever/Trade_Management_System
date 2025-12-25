"""
UDF Hive Repository
Fetches UDF definitions and dropdown options from Hive tables.
"""

from typing import List, Dict, Any, Optional
from pyhive import hive
from django.conf import settings
import subprocess
import tempfile
import os
import logging

logger = logging.getLogger(__name__)


class HiveConnection:
    """Manages Hive database connections."""

    @staticmethod
    def get_connection():
        """Create and return a Hive connection."""
        return hive.Connection(
            host='localhost',
            port=10000,
            database='cis',
            auth='NOSASL',
            configuration={'hive.server2.thrift.client.connect.timeout': '10000',
                          'hive.server2.thrift.client.socketTimeout': '60000'}
        )

    @staticmethod
    def execute_query(query: str) -> List[Dict[str, Any]]:
        """
        Execute a Hive query and return results as list of dictionaries.

        PyHive Limitations Handled:
        - Uses SELECT * to avoid column name issues
        - Avoids ORDER BY in SQL (sort in Python instead)
        - Handles qualified column names (table.column)
        """
        conn = HiveConnection.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            results = []

            for row in cursor.fetchall():
                # Handle qualified column names (table.column -> column)
                row_dict = {}
                for col, val in zip(columns, row):
                    # Remove table prefix if present
                    clean_col = col.split('.')[-1] if '.' in col else col
                    row_dict[clean_col] = val
                results.append(row_dict)

            return results
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def load_data_to_table(table_name: str, data_line: str) -> bool:
        """
        Load data into Hive table using beeline and LOAD DATA LOCAL INPATH.
        This works around PyHive connection issues with Hive 4.x.

        Args:
            table_name: Name of the table to load data into
            data_line: Pipe-delimited data line to load

        Returns:
            True if successful, False otherwise
        """
        temp_file = None

        try:
            # Create temporary file with data
            temp_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.txt',
                delete=False
            )
            temp_file.write(data_line)
            temp_file.close()

            # Use beeline to execute LOAD DATA command
            load_query = f"LOAD DATA LOCAL INPATH '{temp_file.name}' INTO TABLE {table_name};"

            # Execute via beeline subprocess (use full path to avoid Anaconda's beeline)
            result = subprocess.run(
                [
                    '/usr/local/bin/beeline',
                    '-u', 'jdbc:hive2://localhost:10000/cis',
                    '-e', load_query,
                    '--silent=true'
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                logger.info(f"Data loaded successfully into {table_name}")
                return True
            else:
                logger.error(f"Beeline error loading data: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Beeline timeout loading data into {table_name}")
            return False
        except Exception as e:
            logger.error(f"Error loading data into {table_name}: {str(e)}")
            return False

        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except:
                    pass


class UDFDefinitionRepository:
    """Repository for UDF definition metadata from Hive."""

    @staticmethod
    def get_all_definitions(entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch all UDF definitions from Hive.

        Args:
            entity_type: Optional filter by entity type (PORTFOLIO, TRADE, etc.)

        Returns:
            List of UDF definition dictionaries
        """
        query = "SELECT * FROM cis.cis_udf_definition"

        if entity_type:
            query += f" WHERE entity_type = '{entity_type.upper()}'"

        results = HiveConnection.execute_query(query)

        # Sort in Python (avoid ORDER BY in Hive due to PyHive issues)
        return sorted(results, key=lambda x: (x.get('display_order', 0), x.get('field_name', '')))

    @staticmethod
    def get_definition_by_id(udf_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a specific UDF definition by ID."""
        query = f"SELECT * FROM cis.cis_udf_definition WHERE udf_id = {udf_id}"
        results = HiveConnection.execute_query(query)
        return results[0] if results else None

    @staticmethod
    def get_definition_by_name(field_name: str) -> Optional[Dict[str, Any]]:
        """Fetch a UDF definition by field name."""
        query = f"SELECT * FROM cis.cis_udf_definition WHERE field_name = '{field_name}'"
        results = HiveConnection.execute_query(query)
        return results[0] if results else None

    @staticmethod
    def get_portfolio_definitions() -> List[Dict[str, Any]]:
        """Fetch all UDF definitions for Portfolio entity type."""
        return UDFDefinitionRepository.get_all_definitions(entity_type='PORTFOLIO')

    @staticmethod
    def get_active_definitions(entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch only active UDF definitions."""
        query = "SELECT * FROM cis.cis_udf_definition WHERE is_active = true"

        if entity_type:
            query += f" AND entity_type = '{entity_type.upper()}'"

        results = HiveConnection.execute_query(query)
        return sorted(results, key=lambda x: (x.get('display_order', 0), x.get('field_name', '')))

    @staticmethod
    def insert_definition(udf_data: Dict[str, Any]) -> bool:
        """
        Insert UDF definition into Hive using LOAD DATA.

        Args:
            udf_data: Dictionary with UDF definition data

        Returns:
            True if successful
        """
        try:
            # Helper to format values for pipe-delimited file
            def format_val(v):
                if v is None:
                    return ''
                # Replace pipes with escaped version to avoid delimiter conflict
                return str(v).replace('|', '\\|')

            # Build pipe-delimited data line (23 columns in correct order)
            data_line = '|'.join([
                str(udf_data.get('udf_id', '')),
                format_val(udf_data.get('field_name')),
                format_val(udf_data.get('label')),
                format_val(udf_data.get('description')),
                format_val(udf_data.get('field_type')),
                format_val(udf_data.get('entity_type')),
                str(udf_data.get('is_required', False)).lower(),
                str(udf_data.get('is_unique', False)).lower(),
                str(udf_data.get('max_length') or ''),
                str(udf_data.get('min_value_decimal') or ''),
                str(udf_data.get('max_value_decimal') or ''),
                str(udf_data.get('display_order', 0)),
                format_val(udf_data.get('group_name')),
                format_val(udf_data.get('default_string')),
                str(udf_data.get('default_int') or ''),
                str(udf_data.get('default_decimal') or ''),
                str(udf_data.get('default_bool', '')).lower() if udf_data.get('default_bool') is not None else '',
                format_val(udf_data.get('default_datetime')),
                str(udf_data.get('is_active', True)).lower(),
                format_val(udf_data.get('created_by')),
                format_val(udf_data.get('created_at')),
                format_val(udf_data.get('updated_by')),
                format_val(udf_data.get('updated_at'))
            ])

            return HiveConnection.load_data_to_table('cis_udf_definition', data_line)

        except Exception as e:
            logger.error(f"Error creating UDF definition data: {str(e)}")
            return False


class UDFOptionRepository:
    """Repository for UDF dropdown options from Hive."""

    @staticmethod
    def get_options_by_udf_id(udf_id: int) -> List[Dict[str, Any]]:
        """
        Fetch dropdown options for a specific UDF.

        Args:
            udf_id: The UDF definition ID

        Returns:
            List of option dictionaries with option_value, display_order, is_active
        """
        query = f"SELECT * FROM cis.cis_udf_option WHERE udf_id = {udf_id}"
        results = HiveConnection.execute_query(query)

        # Sort by display_order in Python
        return sorted(results, key=lambda x: x.get('display_order', 0))

    @staticmethod
    def get_active_options_by_udf_id(udf_id: int) -> List[Dict[str, Any]]:
        """Fetch only active dropdown options for a UDF."""
        query = f"SELECT * FROM cis.cis_udf_option WHERE udf_id = {udf_id} AND is_active = true"
        results = HiveConnection.execute_query(query)
        return sorted(results, key=lambda x: x.get('display_order', 0))

    @staticmethod
    def get_options_by_field_name(field_name: str) -> List[Dict[str, Any]]:
        """
        Fetch dropdown options for a UDF by field name.

        Args:
            field_name: The UDF field name (e.g., 'account_group')

        Returns:
            List of option dictionaries
        """
        # First get the UDF definition to find the udf_id
        definition = UDFDefinitionRepository.get_definition_by_name(field_name)

        if not definition:
            return []

        return UDFOptionRepository.get_options_by_udf_id(definition['udf_id'])


class UDFValueRepository:
    """Repository for UDF values in Hive."""

    @staticmethod
    def insert_value(value_data: Dict[str, Any]) -> bool:
        """
        Insert UDF value into Hive using LOAD DATA.

        Args:
            value_data: Dictionary with UDF value data

        Returns:
            True if successful
        """
        try:
            # Helper to format values for pipe-delimited file
            def format_val(v):
                if v is None:
                    return ''
                # Replace pipes with escaped version to avoid delimiter conflict
                return str(v).replace('|', '\\|')

            # Build pipe-delimited data line (14 columns in correct order)
            data_line = '|'.join([
                format_val(value_data.get('entity_type')),
                str(value_data.get('entity_id', '')),
                format_val(value_data.get('field_name')),
                str(value_data.get('udf_id', '')),
                format_val(value_data.get('value_string')),
                str(value_data.get('value_int') or ''),
                str(value_data.get('value_decimal') or ''),
                str(value_data.get('value_bool', '')).lower() if value_data.get('value_bool') is not None else '',
                format_val(value_data.get('value_datetime')),
                str(value_data.get('is_active', True)).lower(),
                format_val(value_data.get('created_by')),
                format_val(value_data.get('created_at')),
                format_val(value_data.get('updated_by')),
                format_val(value_data.get('updated_at'))
            ])

            return HiveConnection.load_data_to_table('cis_udf_value', data_line)

        except Exception as e:
            logger.error(f"Error creating UDF value data: {str(e)}")
            return False


class ReferenceDataRepository:
    """
    Repository for fetching reference data from Hive tables.
    Used to populate UDF dropdown options from Currency, Country, Calendar, Counterparty tables.
    """

    @staticmethod
    def get_currencies() -> List[Dict[str, Any]]:
        """
        Fetch all currencies for dropdown options.

        Returns:
            List of currency dictionaries with iso_code, name, symbol
        """
        query = "SELECT * FROM cis.gmp_cis_sta_dly_currency"
        results = HiveConnection.execute_query(query)

        # Sort by ISO code in Python
        return sorted(results, key=lambda x: x.get('iso_code', ''))

    @staticmethod
    def get_countries() -> List[Dict[str, Any]]:
        """
        Fetch all countries for dropdown options.

        Returns:
            List of country dictionaries with label, full_name
        """
        query = "SELECT * FROM cis.gmp_cis_sta_dly_country"
        results = HiveConnection.execute_query(query)

        # Sort by label in Python
        return sorted(results, key=lambda x: x.get('label', ''))

    @staticmethod
    def get_calendars() -> List[Dict[str, Any]]:
        """
        Fetch all calendars for dropdown options.

        Returns:
            List of calendar dictionaries with calendar_label, calendar_description
        """
        query = "SELECT DISTINCT calendar_label, calendar_description FROM cis.gmp_cis_sta_dly_calendar"
        results = HiveConnection.execute_query(query)

        # Sort by calendar_label in Python
        return sorted(results, key=lambda x: x.get('calendar_label', ''))

    @staticmethod
    def get_counterparties() -> List[Dict[str, Any]]:
        """
        Fetch all counterparties for dropdown options.

        Returns:
            List of counterparty dictionaries
        """
        query = "SELECT * FROM cis.gmp_cis_sta_dly_counterparty"
        results = HiveConnection.execute_query(query)

        # Sort by counterparty_name in Python
        return sorted(results, key=lambda x: x.get('counterparty_name', ''))

    @staticmethod
    def get_brokers() -> List[Dict[str, Any]]:
        """
        Fetch counterparties that are brokers.

        Returns:
            List of broker counterparties
        """
        query = "SELECT * FROM cis.gmp_cis_sta_dly_counterparty WHERE is_counterparty_broker = 'Y'"
        results = HiveConnection.execute_query(query)
        return sorted(results, key=lambda x: x.get('counterparty_name', ''))

    @staticmethod
    def get_custodians() -> List[Dict[str, Any]]:
        """
        Fetch counterparties that are custodians.

        Returns:
            List of custodian counterparties
        """
        query = "SELECT * FROM cis.gmp_cis_sta_dly_counterparty WHERE is_counterparty_custodian = 'Y'"
        results = HiveConnection.execute_query(query)
        return sorted(results, key=lambda x: x.get('counterparty_name', ''))

    @staticmethod
    def get_issuers() -> List[Dict[str, Any]]:
        """
        Fetch counterparties that are issuers.

        Returns:
            List of issuer counterparties
        """
        query = "SELECT * FROM cis.gmp_cis_sta_dly_counterparty WHERE is_counterparty_issuer = 'Y'"
        results = HiveConnection.execute_query(query)
        return sorted(results, key=lambda x: x.get('counterparty_name', ''))

    @staticmethod
    def get_account_groups() -> List[Dict[str, Any]]:
        """
        Fetch account groups for Portfolio UDF dropdown.

        This method fetches distinct account group values from UDF options
        or returns a predefined list if not in Hive.

        Returns:
            List of account group dictionaries with 'value' and 'label'
        """
        # Try to fetch from UDF options table first
        try:
            options = UDFOptionRepository.get_options_by_field_name('account_group')
            if options:
                return [
                    {'value': opt['option_value'], 'label': opt['option_value']}
                    for opt in options if opt.get('is_active', True)
                ]
        except Exception:
            pass

        # Fallback to common account groups
        return [
            {'value': 'TRADING', 'label': 'Trading'},
            {'value': 'INVESTMENT', 'label': 'Investment'},
            {'value': 'HEDGING', 'label': 'Hedging'},
            {'value': 'TREASURY', 'label': 'Treasury'},
            {'value': 'OPERATIONS', 'label': 'Operations'},
        ]

    @staticmethod
    def get_entity_groups() -> List[Dict[str, Any]]:
        """
        Fetch entity groups for Portfolio UDF dropdown.

        This method fetches distinct entity group values from UDF options
        or returns a predefined list if not in Hive.

        Returns:
            List of entity group dictionaries with 'value' and 'label'
        """
        # Try to fetch from UDF options table first
        try:
            options = UDFOptionRepository.get_options_by_field_name('entity_group')
            if options:
                return [
                    {'value': opt['option_value'], 'label': opt['option_value']}
                    for opt in options if opt.get('is_active', True)
                ]
        except Exception:
            pass

        # Fallback to common entity groups
        return [
            {'value': 'CORPORATE', 'label': 'Corporate'},
            {'value': 'INSTITUTIONAL', 'label': 'Institutional'},
            {'value': 'RETAIL', 'label': 'Retail'},
            {'value': 'GOVERNMENT', 'label': 'Government'},
            {'value': 'FUND', 'label': 'Fund'},
        ]


# Singleton instances for easy access
udf_definition_repository = UDFDefinitionRepository()
udf_option_repository = UDFOptionRepository()
udf_value_repository = UDFValueRepository()
reference_data_repository = ReferenceDataRepository()
