"""
Party Repository

Data access layer for cis_party in Kudu tables. All queries execute via
Impala (no Django ORM). Mirrors reference_data/repositories/party_repository.py's
create() field lists exactly.
"""

import logging
from typing import Any, Dict

from .impala_connection import impala_manager
from .config import settings

logger = logging.getLogger(__name__)


class PartyRepository:
    """Repository for party operations with Kudu via Impala"""

    DATABASE = settings.IMPALA_CONFIG['DATABASE']
    TABLE_NAME = 'cis_party'

    @staticmethod
    def _escape_sql(value) -> str:
        """Escape single quotes in SQL values. Impala uses C-style \\' escaping, not doubled quotes."""
        if value is None:
            return ''
        return str(value).replace('\\', '\\\\').replace("'", "\\'")

    @staticmethod
    def upsert(party_data: Dict[str, Any]) -> bool:
        """
        Insert/update a party record using UPSERT.

        Args:
            party_data: Dictionary with party fields (must include party_short_name)

        Returns:
            True if successful, False otherwise
        """
        esc = PartyRepository._escape_sql
        columns = []
        values = []

        columns.append('party_short_name')
        values.append(f"'{esc(party_data.get('party_short_name', ''))}'")

        # Mirrors reference_data/repositories/party_repository.py's create()
        # string_fields list exactly.
        string_fields = [
            'm_label', 'party_full_name', 'record_type', 'status',
            'validated_by', 'validation_comments',
            'address_line_0', 'address_line_1', 'address_line_2', 'address_line_3',
            'city', 'country', 'postal_code',
            'fax_number', 'telex_number', 'primary_contact', 'primary_number',
            'other_contact', 'other_number',
            'industry', 'industry_group',
            'subsidiary_level', 'party_grandparent', 'party_parent',
            'resident_y_n', 'mas_industry_code', 'country_of_incorporation', 'cels_code',
            'src_system', 'sub_system', 'data_cat', 'data_frq', 'src_id',
            'processing_date', 'created_by', 'updated_by',
        ]

        for field in string_fields:
            if field in party_data:
                columns.append(field)
                value = party_data[field]
                if value is None or value == '':
                    values.append('NULL')
                else:
                    values.append(f"'{esc(str(value))}'")

        boolean_fields = [
            'is_broker', 'is_custodian', 'is_issuer', 'is_bank',
            'is_subsidiary', 'is_corporate', 'is_other', 'is_financial_institute',
            'is_active', 'is_deleted',
        ]

        for field in boolean_fields:
            if field in party_data:
                columns.append(field)
                value = party_data[field]
                if isinstance(value, bool):
                    values.append(str(value).upper())
                elif isinstance(value, str) and value.upper() in ('TRUE', 'FALSE'):
                    values.append(value.upper())
                else:
                    values.append('FALSE')

        if 'created_at' in party_data:
            columns.append('created_at')
            values.append('NOW()')
        if 'updated_at' in party_data:
            columns.append('updated_at')
            values.append('NOW()')

        columns_str = ', '.join(columns)
        values_str = ', '.join(values)

        query = f"""
        UPSERT INTO {PartyRepository.DATABASE}.{PartyRepository.TABLE_NAME} ({columns_str})
        VALUES ({values_str})
        """

        try:
            success = impala_manager.execute_write(query, database=PartyRepository.DATABASE)
            if success:
                logger.info(f"Successfully upserted party {party_data.get('party_short_name')}")
            return success
        except Exception as e:
            logger.error(f"Error upserting party: {e}")
            return False


party_repository = PartyRepository()
