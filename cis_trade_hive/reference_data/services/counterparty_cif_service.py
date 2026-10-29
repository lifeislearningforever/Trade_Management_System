"""
Counterparty CIF Service - Business Logic Layer for CIF Management
"""

from typing import List, Dict, Optional, Any, Tuple
from reference_data.repositories.counterparty_cif_repository import counterparty_cif_repository


class CounterpartyCIFService:
    """Service for managing Counterparty CIF business logic"""

    def __init__(self):
        self.repository = counterparty_cif_repository

    def list_cifs_for_counterparty(
        self,
        counterparty_short_name: str,
        is_active: Optional[bool] = None
    ) -> List[Dict]:
        """
        Get all CIFs for a specific counterparty

        Args:
            counterparty_short_name: Counterparty short name
            is_active: Optional filter by active status

        Returns:
            List of CIF dictionaries
        """
        return self.repository.get_by_counterparty(counterparty_short_name, is_active)

    def get_cif(self, counterparty_short_name: str, m_label: str) -> Optional[Dict]:
        """
        Get specific CIF by composite key

        Args:
            counterparty_short_name: Counterparty short name
            m_label: CIF number

        Returns:
            CIF dictionary or None
        """
        return self.repository.get_by_cif_key(counterparty_short_name, m_label)

    def _generate_cif_m_label(self, counterparty_short_name: str, country: str) -> str:
        """
        Generate unique m_label for CIF.
        Format: {counterparty_short_name}_{country}_{counter}

        Args:
            counterparty_short_name: Counterparty short name
            country: Country code

        Returns:
            Generated m_label
        """
        import time
        # Get existing CIFs for this counterparty
        existing_cifs = self.repository.get_by_counterparty(counterparty_short_name)

        # Count CIFs for this country
        country_count = sum(1 for cif in existing_cifs if cif.get('country') == country)

        # Generate unique m_label with timestamp to avoid collisions
        timestamp_suffix = str(int(time.time() * 1000))[-6:]  # Last 6 digits of timestamp
        m_label = f"{counterparty_short_name}_{country}_{country_count + 1}_{timestamp_suffix}"

        # Ensure length is within limit (50 chars)
        if len(m_label) > 50:
            m_label = m_label[:50]

        return m_label

    def validate_cif(
        self,
        cif_data: Dict[str, Any],
        is_update: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate CIF data

        Args:
            cif_data: Dictionary with CIF fields
            is_update: True if this is an update operation

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Required field validation
        counterparty_short_name = cif_data.get('counterparty_short_name', '').strip()
        if not counterparty_short_name:
            return False, "Counterparty short name is required"

        # Country is required
        country = cif_data.get('country', '').strip()
        if not country:
            return False, "Country is required"

        # m_label validation only for updates (for creates, it's auto-generated)
        if is_update:
            m_label = cif_data.get('m_label', '').strip()
            if not m_label:
                return False, "M-Label (CIF number) is required"

            # Validate m_label length
            if len(m_label) > 50:
                return False, "M-Label must be 50 characters or less"

        # Validate country length
        if country and len(country) > 100:
            return False, "Country must be 100 characters or less"

        # Validate description length
        description = cif_data.get('description', '').strip()
        if description and len(description) > 500:
            return False, "Description must be 500 characters or less"

        return True, None

    def create_cif(
        self,
        cif_data: Dict[str, Any],
        user_info: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Create new CIF with validation and audit logging.
        m_label is auto-generated from counterparty_short_name and country.

        Args:
            cif_data: Dictionary with all CIF fields
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Auto-generate m_label from counterparty and country
        counterparty_short_name = cif_data.get('counterparty_short_name', '')
        country = cif_data.get('country', '')

        if counterparty_short_name and country:
            cif_data['m_label'] = self._generate_cif_m_label(counterparty_short_name, country)

        # Validate
        is_valid, error_msg = self.validate_cif(cif_data, is_update=False)
        if not is_valid:
            return False, error_msg

        # Set audit fields
        username = user_info.get('username', 'system')
        cif_data['created_by'] = username
        cif_data['updated_by'] = username
        cif_data['is_active'] = True
        cif_data['is_deleted'] = False

        # Create in repository
        success = self.repository.create(cif_data)

        if success:
            return True, None
        else:
            return False, "Failed to create CIF in database"

    def update_cif(
        self,
        counterparty_short_name: str,
        m_label: str,
        cif_data: Dict[str, Any],
        user_info: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Update existing CIF with validation and audit logging

        Args:
            counterparty_short_name: Counterparty short name
            m_label: CIF number
            cif_data: Dictionary with updated fields
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Check if exists
        existing = self.repository.get_by_cif_key(counterparty_short_name, m_label)
        if not existing:
            return False, f"CIF '{m_label}' not found for counterparty '{counterparty_short_name}'"

        # Validate (skip duplicate check for updates)
        cif_data['counterparty_short_name'] = counterparty_short_name
        cif_data['m_label'] = m_label
        is_valid, error_msg = self.validate_cif(cif_data, is_update=True)
        if not is_valid:
            return False, error_msg

        # Set audit fields
        username = user_info.get('username', 'system')
        cif_data['updated_by'] = username

        # Update in repository
        success = self.repository.update(counterparty_short_name, m_label, cif_data)

        if success:
            return True, None
        else:
            return False, "Failed to update CIF in database"

    def delete_cif(
        self,
        counterparty_short_name: str,
        m_label: str,
        user_info: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Soft delete CIF

        Args:
            counterparty_short_name: Counterparty short name
            m_label: CIF number
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Check if exists
        existing = self.repository.get_by_cif_key(counterparty_short_name, m_label)
        if not existing:
            return False, f"CIF '{m_label}' not found for counterparty '{counterparty_short_name}'"

        # Check if already deleted
        if existing.get('is_deleted'):
            return False, f"CIF '{m_label}' is already deleted"

        # Soft delete
        username = user_info.get('username', 'system')
        success = self.repository.soft_delete(counterparty_short_name, m_label, username)

        if success:
            return True, None
        else:
            return False, "Failed to delete CIF in database"

    def restore_cif(
        self,
        counterparty_short_name: str,
        m_label: str,
        user_info: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Restore soft-deleted CIF

        Args:
            counterparty_short_name: Counterparty short name
            m_label: CIF number
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Check if exists
        existing = self.repository.get_by_cif_key(counterparty_short_name, m_label)
        if not existing:
            return False, f"CIF '{m_label}' not found for counterparty '{counterparty_short_name}'"

        # Check if not deleted
        if not existing.get('is_deleted'):
            return False, f"CIF '{m_label}' is not deleted"

        # Restore
        username = user_info.get('username', 'system')
        success = self.repository.restore(counterparty_short_name, m_label, username)

        if success:
            return True, None
        else:
            return False, "Failed to restore CIF in database"

    def delete_all_for_counterparty(
        self,
        counterparty_short_name: str,
        user_info: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Soft delete all CIFs for a counterparty

        Args:
            counterparty_short_name: Counterparty short name
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        username = user_info.get('username', 'system')
        success = self.repository.delete_all_for_counterparty(counterparty_short_name, username)

        if success:
            return True, None
        else:
            return False, "Failed to delete CIFs in database"

    def get_cif_counts(self, is_active: Optional[bool] = None) -> Dict[str, int]:
        """
        Get CIF counts for all counterparties in a single query (optimized)

        Args:
            is_active: Optional filter by active status

        Returns:
            Dictionary mapping counterparty_short_name to CIF count
        """
        return self.repository.get_cif_counts(is_active)

    def get_counterparties_with_multiple_cifs(self, is_active: Optional[bool] = None) -> List[str]:
        """
        Get list of counterparty names that have multiple CIFs

        Args:
            is_active: Optional filter by active status

        Returns:
            List of counterparty_short_name with count > 1
        """
        return self.repository.get_counterparties_with_multiple_cifs(is_active)


# Singleton instance
counterparty_cif_service = CounterpartyCIFService()
