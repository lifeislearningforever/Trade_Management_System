"""
Party CIF Repository - Data Access Layer for Party CIF Management

Uses new cis_party_cif table (renamed from cis_counterparty_cif_kudu).
"""

import logging
from typing import List, Dict, Optional, Any
from .reference_data_repository import ImpalaReferenceRepository

logger = logging.getLogger('reference_data')


class PartyCIFRepository(ImpalaReferenceRepository):
    """Repository for managing Party CIF data in Kudu"""

    TABLE_NAME = 'cis_party_cif'

    def get_by_party(self, party_short_name: str, is_active: Optional[bool] = None) -> List[Dict]:
        """
        Get all CIFs for a specific party

        Args:
            party_short_name: Party short name
            is_active: Optional filter by active status

        Returns:
            List of CIF dictionaries
        """
        party_escaped = self._escape_sql(party_short_name)
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE party_name = '{party_escaped}'"

        if is_active is not None:
            query += f" AND is_active = {str(is_active).upper()}"

        query += " ORDER BY country, m_label"

        return self._execute_query(query)

    def get_by_cif_key(self, party_name: str, m_label: str, country: str) -> Optional[Dict]:
        """
        Get specific CIF by composite key

        Args:
            party_name: Party short name
            m_label: CIF number
            country: Country code

        Returns:
            CIF dictionary or None
        """
        party_escaped = self._escape_sql(party_name)
        m_label_escaped = self._escape_sql(m_label)
        country_escaped = self._escape_sql(country)

        query = f"""
        SELECT * FROM {self.TABLE_NAME}
        WHERE party_name = '{party_escaped}'
        AND m_label = '{m_label_escaped}'
        AND country = '{country_escaped}'
        LIMIT 1
        """

        results = self._execute_query(query)
        return results[0] if results else None

    def create(self, cif_data: Dict[str, Any]) -> bool:
        """
        Create new CIF using UPSERT

        Args:
            cif_data: Dictionary with CIF fields (must include party_name, m_label, country)

        Returns:
            True if successful, False otherwise
        """
        # Build column list and values list
        columns = []
        values = []

        # Required fields (composite primary key)
        columns.append('party_name')
        values.append(f"'{self._escape_sql(cif_data.get('party_name', ''))}'")

        # m_label - auto-generate if not provided
        m_label = cif_data.get('m_label', '')
        if not m_label:
            # Generate m_label from party_name and country
            party_name = cif_data.get('party_name', '')
            country = cif_data.get('country', '')
            m_label = f"{party_name}_{country}" if country else party_name
        columns.append('m_label')
        values.append(f"'{self._escape_sql(m_label)}'")

        columns.append('country')
        values.append(f"'{self._escape_sql(cif_data.get('country', ''))}'")

        # Optional string fields
        string_fields = [
            'isin', 'description',
            'src_system', 'sub_system', 'data_cat', 'data_frq', 'src_id',
            'processing_date', 'record_type', 'created_by', 'updated_by'
        ]

        for field in string_fields:
            if field in cif_data:
                columns.append(field)
                value = cif_data[field]
                if value is None or value == '':
                    values.append('NULL')
                else:
                    values.append(f"'{self._escape_sql(str(value))}'")

        # Boolean fields
        boolean_fields = ['is_active', 'is_deleted']

        for field in boolean_fields:
            if field in cif_data:
                columns.append(field)
                value = cif_data[field]
                if isinstance(value, bool):
                    values.append(str(value).upper())
                elif isinstance(value, str) and value.upper() in ['TRUE', 'FALSE']:
                    values.append(value.upper())
                else:
                    values.append('FALSE')

        # Default is_active to TRUE if not provided
        if 'is_active' not in cif_data:
            columns.append('is_active')
            values.append('TRUE')

        # Default is_deleted to FALSE if not provided
        if 'is_deleted' not in cif_data:
            columns.append('is_deleted')
            values.append('FALSE')

        # Timestamp fields
        columns.append('created_at')
        values.append('NOW()')
        columns.append('updated_at')
        values.append('NOW()')

        # Build UPSERT query
        columns_str = ', '.join(columns)
        values_str = ', '.join(values)

        query = f"""
        UPSERT INTO {self.TABLE_NAME} ({columns_str})
        VALUES ({values_str})
        """

        return self._execute_write(query)

    def update(self, party_name: str, m_label: str, country: str, cif_data: Dict[str, Any]) -> bool:
        """
        Update existing CIF using UPSERT

        Args:
            party_name: Party name
            m_label: CIF number
            country: Country code
            cif_data: Dictionary with updated fields

        Returns:
            True if successful, False otherwise
        """
        # UPSERT works for both insert and update in Kudu
        cif_data['party_name'] = party_name
        cif_data['m_label'] = m_label
        cif_data['country'] = country
        return self.create(cif_data)

    def soft_delete(self, party_name: str, m_label: str, country: str, updated_by: str) -> bool:
        """
        Soft delete CIF (set is_active = false, is_deleted = true)

        Args:
            party_name: Party name
            m_label: CIF number
            country: Country code
            updated_by: User performing the delete

        Returns:
            True if successful, False otherwise
        """
        party_escaped = self._escape_sql(party_name)
        m_label_escaped = self._escape_sql(m_label)
        country_escaped = self._escape_sql(country)
        updated_by_escaped = self._escape_sql(updated_by)

        query = f"""
        UPSERT INTO {self.TABLE_NAME} (
            party_name, m_label, country, is_active, is_deleted, updated_by, updated_at
        )
        SELECT
            party_name,
            m_label,
            country,
            FALSE as is_active,
            TRUE as is_deleted,
            '{updated_by_escaped}' as updated_by,
            now() as updated_at
        FROM {self.TABLE_NAME}
        WHERE party_name = '{party_escaped}'
        AND m_label = '{m_label_escaped}'
        AND country = '{country_escaped}'
        """

        return self._execute_write(query)

    def restore(self, party_name: str, m_label: str, country: str, updated_by: str) -> bool:
        """
        Restore soft-deleted CIF (set is_active = true, is_deleted = false)

        Args:
            party_name: Party name
            m_label: CIF number
            country: Country code
            updated_by: User performing the restore

        Returns:
            True if successful, False otherwise
        """
        party_escaped = self._escape_sql(party_name)
        m_label_escaped = self._escape_sql(m_label)
        country_escaped = self._escape_sql(country)
        updated_by_escaped = self._escape_sql(updated_by)

        query = f"""
        UPSERT INTO {self.TABLE_NAME} (
            party_name, m_label, country, is_active, is_deleted, updated_by, updated_at
        )
        SELECT
            party_name,
            m_label,
            country,
            TRUE as is_active,
            FALSE as is_deleted,
            '{updated_by_escaped}' as updated_by,
            now() as updated_at
        FROM {self.TABLE_NAME}
        WHERE party_name = '{party_escaped}'
        AND m_label = '{m_label_escaped}'
        AND country = '{country_escaped}'
        """

        return self._execute_write(query)

    def delete_all_for_party(self, party_name: str, updated_by: str) -> bool:
        """
        Soft delete all CIFs for a party

        Args:
            party_name: Party name
            updated_by: User performing the delete

        Returns:
            True if successful, False otherwise
        """
        party_escaped = self._escape_sql(party_name)
        updated_by_escaped = self._escape_sql(updated_by)

        query = f"""
        UPSERT INTO {self.TABLE_NAME} (
            party_name, m_label, is_active, is_deleted, updated_by, updated_at
        )
        SELECT
            party_name,
            m_label,
            FALSE as is_active,
            TRUE as is_deleted,
            '{updated_by_escaped}' as updated_by,
            now() as updated_at
        FROM {self.TABLE_NAME}
        WHERE party_name = '{party_escaped}'
        """

        return self._execute_write(query)

    def get_cif_counts(self, is_active: Optional[bool] = None) -> Dict[str, int]:
        """
        Get CIF counts for all parties in a single aggregated query

        Args:
            is_active: Optional filter by active status

        Returns:
            Dictionary mapping party_name to CIF count
        """
        query = f"SELECT party_name, COUNT(*) as cif_count FROM {self.TABLE_NAME}"

        if is_active is not None:
            query += f" WHERE is_active = {str(is_active).upper()}"

        query += " GROUP BY party_name"

        results = self._execute_query(query)
        return {row['party_name']: row['cif_count'] for row in results}

    def get_parties_with_multiple_cifs(self, is_active: Optional[bool] = None) -> List[str]:
        """
        Get list of party names that have multiple CIFs (optimized with HAVING clause)

        Args:
            is_active: Optional filter by active status

        Returns:
            List of party_name with count > 1
        """
        query = f"""
        SELECT party_name, COUNT(*) as cif_count
        FROM {self.TABLE_NAME}
        """

        if is_active is not None:
            query += f" WHERE is_active = {str(is_active).upper()}"

        query += """
        GROUP BY party_name
        HAVING COUNT(*) > 1
        """

        results = self._execute_query(query)
        return [row['party_name'] for row in results]


# Singleton instance
party_cif_repository = PartyCIFRepository()
