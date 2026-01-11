"""
UDF Repository - Kudu/Impala Backend
Fetches UDF definitions and dropdown options from Kudu/Impala tables.
"""

from typing import List, Dict, Any, Optional
from django.conf import settings
from core.repositories.impala_connection import impala_manager
import logging

logger = logging.getLogger(__name__)


class ImpalaConnection:
    """Manages Impala database connections for UDF module."""

    DATABASE = 'gmp_cis'

    @staticmethod
    def execute_query(query: str) -> List[Dict[str, Any]]:
        """
        Execute an Impala query and return results as list of dictionaries.

        Args:
            query: SQL query string

        Returns:
            List of dictionaries representing rows
        """
        try:
            results = impala_manager.execute_query(query, database=ImpalaConnection.DATABASE)
            logger.info(f"Query returned {len(results) if results else 0} rows")
            return results if results else []

        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            logger.error(f"Query: {query}")
            raise


class UDFDefinitionRepository:
    """Repository for UDF definition metadata from Kudu/Impala."""

    TABLE_NAME = 'cis_udf_definition'  # Impala table pointing to cis_udf_definition_kudu

    @staticmethod
    def get_all_definitions(entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch all UDF definitions from Kudu/Impala.

        Args:
            entity_type: Optional filter by entity type (PORTFOLIO, TRADE, etc.)

        Returns:
            List of UDF definition dictionaries
        """
        query = f"SELECT * FROM {UDFDefinitionRepository.TABLE_NAME}"

        if entity_type:
            query += f" WHERE entity_type = '{entity_type.upper()}'"

        query += " ORDER BY display_order, field_name"

        results = ImpalaConnection.execute_query(query)
        return results

    @staticmethod
    def get_definition_by_id(udf_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a specific UDF definition by ID."""
        query = f"SELECT * FROM {UDFDefinitionRepository.TABLE_NAME} WHERE udf_id = {udf_id} LIMIT 1"
        results = ImpalaConnection.execute_query(query)
        return results[0] if results else None

    @staticmethod
    def get_definition_by_name(field_name: str) -> Optional[Dict[str, Any]]:
        """Fetch a UDF definition by field name."""
        query = f"SELECT * FROM {UDFDefinitionRepository.TABLE_NAME} WHERE field_name = '{field_name}' LIMIT 1"
        results = ImpalaConnection.execute_query(query)
        return results[0] if results else None

    @staticmethod
    def get_portfolio_definitions() -> List[Dict[str, Any]]:
        """Fetch all UDF definitions for Portfolio entity type."""
        return UDFDefinitionRepository.get_all_definitions(entity_type='PORTFOLIO')

    @staticmethod
    def get_active_definitions(entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch only active UDF definitions."""
        query = f"SELECT * FROM {UDFDefinitionRepository.TABLE_NAME} WHERE is_active = true"

        if entity_type:
            query += f" AND entity_type = '{entity_type.upper()}'"

        query += " ORDER BY display_order, field_name"

        results = ImpalaConnection.execute_query(query)
        return results

    @staticmethod
    def insert_definition(udf_data: Dict[str, Any]) -> bool:
        """
        Insert UDF definition into Kudu table using UPSERT.

        Args:
            udf_data: Dictionary with UDF definition data
                Required keys: udf_id, field_name, label, field_type, entity_type

        Returns:
            True if successful, False otherwise
        """
        try:
            # Build column names and values
            columns = []
            values = []

            for key, value in udf_data.items():
                if value is not None:
                    columns.append(f"`{key}`")
                    if isinstance(value, str):
                        escaped_value = value.replace("'", "''")
                        values.append(f"'{escaped_value}'")
                    elif isinstance(value, bool):
                        values.append('true' if value else 'false')
                    elif isinstance(value, (int, float)):
                        values.append(str(value))
                    else:
                        values.append(f"'{str(value)}'")

            # Build UPSERT query
            upsert_query = f"""
            UPSERT INTO {ImpalaConnection.DATABASE}.{UDFDefinitionRepository.TABLE_NAME}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            # Execute via Impala
            success = impala_manager.execute_write(upsert_query, database=ImpalaConnection.DATABASE)

            if success:
                logger.info(f"Successfully inserted UDF definition: {udf_data.get('field_name')}")

            return success

        except Exception as e:
            logger.error(f"Error inserting UDF definition: {str(e)}")
            logger.error(f"UDF data: {udf_data}")
            return False

    @staticmethod
    def update_definition(udf_id: int, udf_data: Dict[str, Any]) -> bool:
        """
        Update UDF definition in Kudu table using UPSERT.

        Args:
            udf_id: UDF ID
            udf_data: Dictionary with updated UDF data

        Returns:
            True if successful, False otherwise
        """
        # Ensure udf_id is in the data
        udf_data['udf_id'] = udf_id
        return UDFDefinitionRepository.insert_definition(udf_data)

    @staticmethod
    def delete_definition(udf_id: int) -> bool:
        """
        Soft delete UDF definition by setting is_active = false.

        Args:
            udf_id: UDF ID to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            delete_query = f"""
            UPDATE {ImpalaConnection.DATABASE}.{UDFDefinitionRepository.TABLE_NAME}
            SET `is_active` = false
            WHERE `udf_id` = {udf_id}
            """

            success = impala_manager.execute_write(delete_query, database=ImpalaConnection.DATABASE)

            if success:
                logger.info(f"Successfully deleted UDF definition ID: {udf_id}")

            return success

        except Exception as e:
            logger.error(f"Error deleting UDF definition: {str(e)}")
            return False


class UDFOptionRepository:
    """Repository for UDF dropdown options from Kudu/Impala."""

    TABLE_NAME = 'cis_udf_option'

    @staticmethod
    def get_options_by_udf_id(udf_id: int) -> List[Dict[str, Any]]:
        """
        Fetch dropdown options for a specific UDF.

        Args:
            udf_id: The UDF definition ID

        Returns:
            List of option dictionaries with option_value, display_order, is_active
        """
        query = f"SELECT * FROM {UDFOptionRepository.TABLE_NAME} WHERE udf_id = {udf_id} ORDER BY display_order"
        results = ImpalaConnection.execute_query(query)
        return results

    @staticmethod
    def get_active_options_by_udf_id(udf_id: int) -> List[Dict[str, Any]]:
        """Fetch only active dropdown options for a UDF."""
        query = f"SELECT * FROM {UDFOptionRepository.TABLE_NAME} WHERE udf_id = {udf_id} AND is_active = true ORDER BY display_order"
        results = ImpalaConnection.execute_query(query)
        return results

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
    """Repository for UDF values in Kudu/Impala."""

    TABLE_NAME = 'cis_udf_value'

    @staticmethod
    def insert_value(value_data: Dict[str, Any]) -> bool:
        """
        Insert UDF value into Kudu/Impala.
        Note: Kudu write operations are not yet implemented.

        Args:
            value_data: Dictionary with UDF value data

        Returns:
            False - Kudu write operations not yet implemented
        """
        logger.warning("UDF value insert not yet implemented for Kudu/Impala")
        return False


class ReferenceDataRepository:
    """
    Repository for fetching reference data from Kudu/Impala tables.
    Used to populate UDF dropdown options from Currency, Country, Calendar, Counterparty tables.
    """

    @staticmethod
    def get_currencies() -> List[Dict[str, Any]]:
        """
        Fetch all currencies for dropdown options.

        Returns:
            List of currency dictionaries with iso_code, name, symbol
        """
        query = "SELECT * FROM gmp_cis_sta_dly_currency ORDER BY iso_code"
        results = ImpalaConnection.execute_query(query)
        return results

    @staticmethod
    def get_countries() -> List[Dict[str, Any]]:
        """
        Fetch all countries for dropdown options.

        Returns:
            List of country dictionaries with label, full_name
        """
        query = "SELECT * FROM gmp_cis_sta_dly_country ORDER BY label"
        results = ImpalaConnection.execute_query(query)
        return results

    @staticmethod
    def get_calendars() -> List[Dict[str, Any]]:
        """
        Fetch all calendars for dropdown options.

        Returns:
            List of calendar dictionaries with calendar_label, calendar_description
        """
        query = "SELECT DISTINCT calendar_label, calendar_description FROM gmp_cis_sta_dly_calendar ORDER BY calendar_label"
        results = ImpalaConnection.execute_query(query)
        return results

    @staticmethod
    def get_counterparties() -> List[Dict[str, Any]]:
        """
        Fetch all counterparties for dropdown options.

        Returns:
            List of counterparty dictionaries
        """
        query = "SELECT * FROM gmp_cis_sta_dly_counterparty ORDER BY counterparty_name"
        results = ImpalaConnection.execute_query(query)
        return results

    @staticmethod
    def get_brokers() -> List[Dict[str, Any]]:
        """
        Fetch counterparties that are brokers.

        Returns:
            List of broker counterparties
        """
        query = "SELECT * FROM gmp_cis_sta_dly_counterparty WHERE is_counterparty_broker = 'Y' ORDER BY counterparty_name"
        results = ImpalaConnection.execute_query(query)
        return results

    @staticmethod
    def get_custodians() -> List[Dict[str, Any]]:
        """
        Fetch counterparties that are custodians.

        Returns:
            List of custodian counterparties
        """
        query = "SELECT * FROM gmp_cis_sta_dly_counterparty WHERE is_counterparty_custodian = 'Y' ORDER BY counterparty_name"
        results = ImpalaConnection.execute_query(query)
        return results

    @staticmethod
    def get_issuers() -> List[Dict[str, Any]]:
        """
        Fetch counterparties that are issuers.

        Returns:
            List of issuer counterparties
        """
        query = "SELECT * FROM gmp_cis_sta_dly_counterparty WHERE is_counterparty_issuer = 'Y' ORDER BY counterparty_name"
        results = ImpalaConnection.execute_query(query)
        return results

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
