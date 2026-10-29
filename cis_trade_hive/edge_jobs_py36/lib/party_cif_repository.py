"""
Party CIF Repository

Data access layer for cis_party_cif in Kudu tables. All queries execute via
Impala (no Django ORM). Mirrors reference_data/repositories/party_cif_repository.py's
create() field lists exactly.

Note: the real column is `isin`, not `cif` -- verified against the live
schema (sql/ddl/77_cis_party_cif_fix_primary_key.sql and the Django
repository's field list), which is authoritative over any older prototype
SQL that referenced a `cif` column.
"""

import logging
from typing import Any, Dict

from .impala_connection import impala_manager
from .config import settings

logger = logging.getLogger(__name__)


class PartyCifRepository:
    """Repository for party CIF operations with Kudu via Impala"""

    DATABASE = settings.IMPALA_CONFIG['DATABASE']
    TABLE_NAME = 'cis_party_cif'

    @staticmethod
    def _escape_sql(value) -> str:
        """Escape single quotes in SQL values. Impala uses C-style \\' escaping, not doubled quotes."""
        if value is None:
            return ''
        return str(value).replace('\\', '\\\\').replace("'", "\\'")

    @staticmethod
    def upsert(cif_data: Dict[str, Any]) -> bool:
        """
        Insert/update a party CIF record using UPSERT.

        Args:
            cif_data: Dictionary with CIF fields (must include party_name, country;
                      m_label auto-generated from party_name+country if absent)

        Returns:
            True if successful, False otherwise
        """
        esc = PartyCifRepository._escape_sql
        columns = []
        values = []

        # Composite primary key: party_name, m_label, country
        columns.append('party_name')
        values.append(f"'{esc(cif_data.get('party_name', ''))}'")

        m_label = cif_data.get('m_label', '')
        if not m_label:
            party_name = cif_data.get('party_name', '')
            country = cif_data.get('country', '')
            m_label = f"{party_name}_{country}" if country else party_name
        columns.append('m_label')
        values.append(f"'{esc(m_label)}'")

        columns.append('country')
        values.append(f"'{esc(cif_data.get('country', ''))}'")

        # Mirrors reference_data/repositories/party_cif_repository.py's
        # create() string_fields list exactly -- note 'isin', not 'cif'.
        string_fields = [
            'isin', 'description',
            'src_system', 'sub_system', 'data_cat', 'data_frq', 'src_id',
            'processing_date', 'record_type', 'created_by', 'updated_by',
        ]

        for field in string_fields:
            if field in cif_data:
                columns.append(field)
                value = cif_data[field]
                if value is None or value == '':
                    values.append('NULL')
                else:
                    values.append(f"'{esc(str(value))}'")

        boolean_fields = ['is_active', 'is_deleted']
        for field in boolean_fields:
            if field in cif_data:
                columns.append(field)
                value = cif_data[field]
                if isinstance(value, bool):
                    values.append(str(value).upper())
                elif isinstance(value, str) and value.upper() in ('TRUE', 'FALSE'):
                    values.append(value.upper())
                else:
                    values.append('FALSE')

        if 'is_active' not in cif_data:
            columns.append('is_active')
            values.append('TRUE')
        if 'is_deleted' not in cif_data:
            columns.append('is_deleted')
            values.append('FALSE')

        columns.append('created_at')
        values.append('NOW()')
        columns.append('updated_at')
        values.append('NOW()')

        columns_str = ', '.join(columns)
        values_str = ', '.join(values)

        query = f"""
        UPSERT INTO {PartyCifRepository.DATABASE}.{PartyCifRepository.TABLE_NAME} ({columns_str})
        VALUES ({values_str})
        """

        try:
            success = impala_manager.execute_write(query, database=PartyCifRepository.DATABASE)
            if success:
                logger.info(
                    f"Successfully upserted party CIF "
                    f"{cif_data.get('party_name')}/{m_label}/{cif_data.get('country')}"
                )
            return success
        except Exception as e:
            logger.error(f"Error upserting party CIF: {e}")
            return False


party_cif_repository = PartyCifRepository()
