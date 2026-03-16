"""
Party Repository - Data Access Layer for Party Management

Uses new cis_party table (renamed from cis_counterparty_kudu).
"""

import logging
from typing import List, Dict, Any, Optional
from .reference_data_repository import ImpalaReferenceRepository

logger = logging.getLogger('reference_data')


class PartyRepository(ImpalaReferenceRepository):
    """Repository for Party data - Using cis_party Kudu table"""

    TABLE_NAME = 'cis_party'

    # Maker-Checker Status Constants
    STATUS_INITIAL = 'INITIAL'
    STATUS_MODIFIED = 'MODIFIED'
    STATUS_VALIDATED = 'VALIDATED'

    def list_all(
        self,
        search: Optional[str] = None,
        country: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[Dict]:
        """
        Fetch all parties from Kudu table

        Args:
            search: Optional search term for name or description
            country: Optional filter by country
            is_active: Optional filter by active status

        Returns:
            List of party dictionaries
        """
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE 1=1"

        if search:
            search_escaped = search.replace("'", "''")
            query += f" AND (LOWER(party_short_name) LIKE '%{search_escaped.lower()}%' OR LOWER(party_full_name) LIKE '%{search_escaped.lower()}%')"

        if country:
            country_escaped = country.replace("'", "''")
            query += f" AND country = '{country_escaped}'"

        if is_active is not None:
            query += f" AND is_active = {str(is_active).upper()}"

        # Order by src_system='CIS' first, then by party_short_name
        query += " ORDER BY CASE WHEN UPPER(src_system) = 'CIS' THEN 0 ELSE 1 END, party_short_name"

        results = self._execute_query(query)
        return results

    def get_by_short_name(self, short_name: str) -> Optional[Dict]:
        """Get specific party by short name (primary key)"""
        short_name_escaped = short_name.replace("'", "''")
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE party_short_name = '{short_name_escaped}' LIMIT 1"

        results = self._execute_query(query)
        return results[0] if results else None

    def get_distinct_countries(self) -> List[str]:
        """Get list of distinct countries for dropdown filter"""
        query = f"SELECT DISTINCT country FROM {self.TABLE_NAME} WHERE country IS NOT NULL AND country <> '' ORDER BY country"
        results = self._execute_query(query)
        return [r['country'] for r in results if r.get('country')]

    def create(self, party_data: Dict[str, Any]) -> bool:
        """
        Create new party using UPSERT

        Args:
            party_data: Dictionary with all party fields

        Returns:
            True if successful, False otherwise
        """
        # Build column list and values list
        columns = []
        values = []

        # Required fields
        columns.append('party_short_name')
        values.append(f"'{self._escape_sql(party_data.get('party_short_name', ''))}'")

        # Optional string fields
        string_fields = [
            'm_label', 'party_full_name', 'record_type', 'status',
            'validated_by', 'validation_comments',
            'address_line_0', 'address_line_1', 'address_line_2', 'address_line_3',
            'city', 'country', 'postal_code',
            'fax_number', 'telex_number', 'primary_contact', 'primary_number',
            'other_contact', 'other_number',
            'industry', 'industry_group',
            'subsidiary_level', 'party_grandparent', 'party_parent',
            'resident_y_n', 'mas_industry_code', 'country_of_incorporation', 'gics_code',
            'src_system', 'sub_system', 'data_cat', 'data_frq', 'src_id',
            'processing_date', 'created_by', 'updated_by'
        ]

        for field in string_fields:
            if field in party_data:
                columns.append(field)
                value = party_data[field]
                if value is None or value == '':
                    values.append('NULL')
                else:
                    values.append(f"'{self._escape_sql(str(value))}'")

        # Boolean fields
        boolean_fields = [
            'is_broker', 'is_custodian', 'is_issuer', 'is_bank',
            'is_subsidiary', 'is_corporate', 'is_active', 'is_deleted'
        ]

        for field in boolean_fields:
            if field in party_data:
                columns.append(field)
                value = party_data[field]
                if isinstance(value, bool):
                    values.append(str(value).upper())
                elif isinstance(value, str) and value.upper() in ['TRUE', 'FALSE']:
                    values.append(value.upper())
                else:
                    values.append('FALSE')

        # Timestamp fields
        if 'created_at' in party_data:
            columns.append('created_at')
            values.append('NOW()')
        if 'updated_at' in party_data:
            columns.append('updated_at')
            values.append('NOW()')

        # Build UPSERT query
        columns_str = ', '.join(columns)
        values_str = ', '.join(values)

        query = f"""
        UPSERT INTO {self.TABLE_NAME} ({columns_str})
        VALUES ({values_str})
        """

        try:
            self._execute_write(query)
            return True
        except Exception as e:
            logger.error(f"Error creating party: {e}")
            return False

    def update(self, short_name: str, party_data: Dict[str, Any]) -> bool:
        """
        Update existing party using UPSERT

        Args:
            short_name: Party short name (primary key)
            party_data: Dictionary with updated fields

        Returns:
            True if successful, False otherwise
        """
        # UPSERT works for both insert and update in Kudu
        party_data['party_short_name'] = short_name
        return self.create(party_data)

    def soft_delete(self, short_name: str, updated_by: str) -> bool:
        """
        Soft delete party (set is_active = false, is_deleted = true)

        Args:
            short_name: Party short name
            updated_by: User performing the delete

        Returns:
            True if successful, False otherwise
        """
        short_name_escaped = short_name.replace("'", "''")
        updated_by_escaped = updated_by.replace("'", "''")

        query = f"""
        UPSERT INTO {self.TABLE_NAME} (
            party_short_name, is_active, is_deleted, updated_by, updated_at
        )
        SELECT
            party_short_name,
            FALSE as is_active,
            TRUE as is_deleted,
            '{updated_by_escaped}' as updated_by,
            now() as updated_at
        FROM {self.TABLE_NAME}
        WHERE party_short_name = '{short_name_escaped}'
        """

        try:
            self._execute_write(query)
            return True
        except Exception as e:
            logger.error(f"Error soft deleting party: {e}")
            return False

    def restore(self, short_name: str, updated_by: str) -> bool:
        """
        Restore soft-deleted party (set is_active = true, is_deleted = false)

        Args:
            short_name: Party short name
            updated_by: User performing the restore

        Returns:
            True if successful, False otherwise
        """
        short_name_escaped = short_name.replace("'", "''")
        updated_by_escaped = updated_by.replace("'", "''")

        query = f"""
        UPSERT INTO {self.TABLE_NAME} (
            party_short_name, is_active, is_deleted, updated_by, updated_at
        )
        SELECT
            party_short_name,
            TRUE as is_active,
            FALSE as is_deleted,
            '{updated_by_escaped}' as updated_by,
            now() as updated_at
        FROM {self.TABLE_NAME}
        WHERE party_short_name = '{short_name_escaped}'
        """

        try:
            self._execute_write(query)
            return True
        except Exception as e:
            logger.error(f"Error restoring party: {e}")
            return False

    def get_parties_by_status(self, statuses: List[str]) -> List[Dict]:
        """
        Fetch parties by status(es) for pending approval queue.

        Args:
            statuses: List of status values (e.g., ['INITIAL', 'MODIFIED'])

        Returns:
            List of party dictionaries
        """
        if not statuses:
            return []

        status_list = ", ".join([f"'{s}'" for s in statuses])
        query = f"""
            SELECT * FROM {self.TABLE_NAME}
            WHERE status IN ({status_list})
            AND (is_deleted = FALSE OR is_deleted IS NULL)
            ORDER BY CASE WHEN UPPER(src_system) = 'CIS' THEN 0 ELSE 1 END,
                     updated_at DESC
        """
        return self._execute_query(query)

    def update_party_status(
        self,
        short_name: str,
        status: str,
        updated_by: str,
        validated_by: str = None,
        validation_comments: str = None
    ) -> bool:
        """
        Update party status and validation fields using UPSERT.

        Args:
            short_name: Party short name
            status: New status (INITIAL, MODIFIED, VALIDATED)
            updated_by: User performing the update
            validated_by: User validating (for VALIDATED status)
            validation_comments: Validation comments

        Returns:
            True if successful
        """
        short_name_escaped = short_name.replace("'", "''")
        updated_by_escaped = updated_by.replace("'", "''")
        status_escaped = status.replace("'", "''")

        # Build columns and values for UPSERT
        columns = ['party_short_name', 'status', 'updated_by', 'updated_at']
        values = [
            f"'{short_name_escaped}'",
            f"'{status_escaped}'",
            f"'{updated_by_escaped}'",
            'NOW()'
        ]

        if status == self.STATUS_VALIDATED and validated_by:
            validated_by_escaped = validated_by.replace("'", "''")
            columns.append('validated_by')
            values.append(f"'{validated_by_escaped}'")
            columns.append('validated_at')
            values.append('NOW()')
            if validation_comments:
                comments_escaped = validation_comments.replace("'", "''")
                columns.append('validation_comments')
                values.append(f"'{comments_escaped}'")

        columns_str = ', '.join(columns)
        values_str = ', '.join(values)

        # Use UPSERT to update only the specified columns
        query = f"""
        UPSERT INTO {self.TABLE_NAME} ({columns_str})
        SELECT {values_str}
        FROM {self.TABLE_NAME}
        WHERE party_short_name = '{short_name_escaped}'
        """

        try:
            self._execute_write(query)
            logger.info(f"Party {short_name} status updated to {status} by {updated_by}")
            return True
        except Exception as e:
            logger.error(f"Error updating party status: {e}")
            return False


# Singleton instance
party_repository = PartyRepository()
