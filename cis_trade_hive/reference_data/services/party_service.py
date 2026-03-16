"""
Party Service - Business Logic Layer for Party Management

Renamed from counterparty to party. Uses new cis_party and cis_party_cif tables.
"""

import logging
from typing import List, Dict, Optional, Any, Tuple
from reference_data.repositories.party_repository import party_repository
from reference_data.repositories.party_cif_repository import party_cif_repository

logger = logging.getLogger('reference_data')


class PartyService:
    """Service for Party reference data - Full CRUD operations with Maker-Checker workflow"""

    # Maker-Checker Status Constants
    STATUS_INITIAL = 'INITIAL'
    STATUS_MODIFIED = 'MODIFIED'
    STATUS_VALIDATED = 'VALIDATED'

    def __init__(self):
        self.repository = party_repository

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
            country: Filter by country
            is_active: Filter by active status

        Returns:
            List of party dictionaries
        """
        return self.repository.list_all(search=search, country=country, is_active=is_active)

    def get_by_short_name(self, short_name: str) -> Optional[Dict]:
        """Get specific party by short name (primary key)"""
        return self.repository.get_by_short_name(short_name)

    def get_distinct_countries(self) -> List[str]:
        """Get list of distinct countries for dropdown filter"""
        return self.repository.get_distinct_countries()

    def validate_party(
        self,
        party_data: Dict[str, Any],
        is_update: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate party data

        Args:
            party_data: Dictionary with party fields
            is_update: True if this is an update operation

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Required field validation
        short_name = party_data.get('party_short_name', '').strip()
        if not short_name:
            return False, "Party short name is required"

        # Check for duplicate on create
        if not is_update:
            existing = self.repository.get_by_short_name(short_name)
            if existing:
                return False, f"Party with short name '{short_name}' already exists"

        # Validate short name length
        if len(short_name) > 100:
            return False, "Party short name must be 100 characters or less"

        # Full name validation
        full_name = party_data.get('party_full_name', '').strip()
        if full_name and len(full_name) > 255:
            return False, "Party full name must be 255 characters or less"

        return True, None

    def create_party(
        self,
        party_data: Dict[str, Any],
        user_info: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Create new party with validation and audit logging

        Args:
            party_data: Dictionary with all party fields
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Validate
        is_valid, error_msg = self.validate_party(party_data, is_update=False)
        if not is_valid:
            return False, error_msg

        # Auto-generate m_label from party_short_name
        party_data['m_label'] = party_data.get('party_short_name', '')

        # Set src_system to 'cis' for all records created via UI
        party_data['src_system'] = 'cis'

        # Set initial status for maker-checker workflow
        party_data['status'] = self.STATUS_INITIAL

        # Set audit fields
        username = user_info.get('username', 'system')
        party_data['created_by'] = username
        party_data['updated_by'] = username
        party_data['is_active'] = True
        party_data['is_deleted'] = False
        party_data['created_at'] = True  # Flag to add NOW()
        party_data['updated_at'] = True  # Flag to add NOW()

        # Create in repository
        success = self.repository.create(party_data)

        if success:
            return True, None
        else:
            return False, "Failed to create party in database"

    def can_edit_party(self, party: Dict[str, Any]) -> bool:
        """
        Check if party can be edited based on src_system.
        Only parties created in CIS (src_system='cis') can be edited.
        Records from GMP are read-only.

        Args:
            party: Party dictionary

        Returns:
            True if editable, False if read-only
        """
        src_system = party.get('src_system', '').lower()
        return src_system == 'cis'

    def update_party(
        self,
        short_name: str,
        party_data: Dict[str, Any],
        user_info: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Update existing party with validation and audit logging

        Args:
            short_name: Party short name (primary key)
            party_data: Dictionary with updated fields
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Check if exists
        existing = self.repository.get_by_short_name(short_name)
        if not existing:
            return False, f"Party '{short_name}' not found"

        # Check if editable (only src_system='cis' can be edited)
        if not self.can_edit_party(existing):
            src_system = existing.get('src_system', 'unknown')
            return False, f"Cannot edit party from source system '{src_system}'. Only CIS records are editable."

        # Validate (skip duplicate check for updates)
        party_data['party_short_name'] = short_name
        is_valid, error_msg = self.validate_party(party_data, is_update=True)
        if not is_valid:
            return False, error_msg

        # Preserve m_label and src_system from existing record
        party_data['m_label'] = existing.get('m_label', short_name)
        party_data['src_system'] = existing.get('src_system', 'cis')

        # Set status to MODIFIED after edit (maker-checker workflow)
        party_data['status'] = self.STATUS_MODIFIED

        # Set audit fields
        username = user_info.get('username', 'system')
        party_data['updated_by'] = username
        party_data['updated_at'] = True  # Flag to add NOW()

        # Update in repository
        success = self.repository.update(short_name, party_data)

        if success:
            return True, None
        else:
            return False, "Failed to update party in database"

    def delete_party(
        self,
        short_name: str,
        user_info: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Soft delete party

        Args:
            short_name: Party short name
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Check if exists
        existing = self.repository.get_by_short_name(short_name)
        if not existing:
            return False, f"Party '{short_name}' not found"

        # Check if already deleted
        if existing.get('is_deleted'):
            return False, f"Party '{short_name}' is already deleted"

        # Soft delete
        username = user_info.get('username', 'system')
        success = self.repository.soft_delete(short_name, username)

        if success:
            return True, None
        else:
            return False, "Failed to delete party in database"

    def restore_party(
        self,
        short_name: str,
        user_info: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Restore soft-deleted party

        Args:
            short_name: Party short name
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Check if exists
        existing = self.repository.get_by_short_name(short_name)
        if not existing:
            return False, f"Party '{short_name}' not found"

        # Check if not deleted
        if not existing.get('is_deleted'):
            return False, f"Party '{short_name}' is not deleted"

        # Restore
        username = user_info.get('username', 'system')
        success = self.repository.restore(short_name, username)

        if success:
            return True, None
        else:
            return False, "Failed to restore party in database"

    def approve_party(
        self,
        short_name: str,
        user_info: Dict[str, str],
        comments: str = ''
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate/approve party (Checker action - Four-Eyes principle).
        INITIAL/MODIFIED -> VALIDATED

        Args:
            short_name: Party short name
            user_info: User information (validator)
            comments: Validation comments

        Returns:
            Tuple of (success, error_message)
        """
        # Get existing party
        existing = self.repository.get_by_short_name(short_name)
        if not existing:
            return False, f"Party '{short_name}' not found"

        # Validate current status
        current_status = existing.get('status', '')
        if current_status not in [self.STATUS_INITIAL, self.STATUS_MODIFIED]:
            return False, f"Cannot validate party with status '{current_status}'. Only INITIAL or MODIFIED parties can be validated."

        # Only CIS records can be validated
        if not self.can_edit_party(existing):
            return False, f"Cannot validate party from source system '{existing.get('src_system', 'unknown')}'."

        # Four-Eyes check: validator cannot be the creator
        created_by = existing.get('created_by', '')
        username = user_info.get('username', '')
        if created_by == username:
            return False, "You cannot validate your own party (Four-Eyes principle)"

        # Update status to VALIDATED
        success = self.repository.update_party_status(
            short_name=short_name,
            status=self.STATUS_VALIDATED,
            updated_by=username,
            validated_by=username,
            validation_comments=comments
        )

        if success:
            return True, None
        else:
            return False, "Failed to validate party in database"

    def get_pending_approval_parties(self) -> List[Dict]:
        """
        Get all parties pending approval (INITIAL or MODIFIED status).

        Returns:
            List of party dictionaries
        """
        return self.repository.get_parties_by_status([
            self.STATUS_INITIAL,
            self.STATUS_MODIFIED
        ])

    def can_user_validate(self, party: Dict[str, Any], username: str) -> bool:
        """
        Check if user can validate a party.

        Args:
            party: Party dictionary
            username: Username

        Returns:
            True if user can validate
        """
        if not party:
            return False

        # Can validate if:
        # 1. Status is INITIAL or MODIFIED
        # 2. User is not the creator (Four-Eyes)
        # 3. Party is from CIS source system
        status = party.get('status', '')
        created_by = party.get('created_by', '')
        src_system = (party.get('src_system', '') or '').lower()

        return (
            status in [self.STATUS_INITIAL, self.STATUS_MODIFIED] and
            created_by != username and
            src_system == 'cis'
        )

    @staticmethod
    def get_status_display_color(status: str) -> str:
        """
        Get Bootstrap color class for status badge.

        Args:
            status: Party status

        Returns:
            Bootstrap color class
        """
        colors = {
            'INITIAL': 'secondary',
            'MODIFIED': 'info',
            'VALIDATED': 'success',
        }
        return colors.get(status, 'secondary')


class PartyCIFService:
    """Service for managing Party CIF business logic"""

    def __init__(self):
        self.repository = party_cif_repository

    def list_cifs_for_party(
        self,
        party_short_name: str,
        is_active: Optional[bool] = None
    ) -> List[Dict]:
        """
        Get all CIFs for a specific party

        Args:
            party_short_name: Party short name
            is_active: Optional filter by active status

        Returns:
            List of CIF dictionaries
        """
        return self.repository.get_by_party(party_short_name, is_active)

    def get_cif(self, party_name: str, m_label: str, country: str = '') -> Optional[Dict]:
        """
        Get specific CIF by key

        Args:
            party_name: Party short name
            m_label: CIF number
            country: Country code

        Returns:
            CIF dictionary or None
        """
        return self.repository.get_by_cif_key(party_name, m_label, country)

    def _generate_cif_m_label(self, party_short_name: str, country: str) -> str:
        """
        Generate unique m_label for CIF.
        Format: {party_short_name}_{country}_{counter}

        Args:
            party_short_name: Party short name
            country: Country code

        Returns:
            Generated m_label
        """
        import time
        # Get existing CIFs for this party
        existing_cifs = self.repository.get_by_party(party_short_name)

        # Count CIFs for this country
        country_count = sum(1 for cif in existing_cifs if cif.get('country') == country)

        # Generate unique m_label with timestamp to avoid collisions
        timestamp_suffix = str(int(time.time() * 1000))[-6:]  # Last 6 digits of timestamp
        m_label = f"{party_short_name}_{country}_{country_count + 1}_{timestamp_suffix}"

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
        party_name = cif_data.get('party_name', '').strip()
        if not party_name:
            return False, "Party name is required"

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
        m_label is auto-generated from party_name and country.

        Args:
            cif_data: Dictionary with all CIF fields
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Auto-generate m_label from party and country
        party_name = cif_data.get('party_name', '')
        country = cif_data.get('country', '')

        if party_name and country:
            cif_data['m_label'] = self._generate_cif_m_label(party_name, country)

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
        party_name: str,
        m_label: str,
        country: str,
        cif_data: Dict[str, Any],
        user_info: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Update existing CIF with validation and audit logging

        Args:
            party_name: Party name
            m_label: CIF number
            country: Country code
            cif_data: Dictionary with updated fields
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Check if exists
        existing = self.repository.get_by_cif_key(party_name, m_label, country)
        if not existing:
            return False, f"CIF '{m_label}' not found for party '{party_name}'"

        # Validate (skip duplicate check for updates)
        cif_data['party_name'] = party_name
        cif_data['m_label'] = m_label
        cif_data['country'] = country
        is_valid, error_msg = self.validate_cif(cif_data, is_update=True)
        if not is_valid:
            return False, error_msg

        # Set audit fields
        username = user_info.get('username', 'system')
        cif_data['updated_by'] = username

        # Update in repository
        success = self.repository.update(party_name, m_label, country, cif_data)

        if success:
            return True, None
        else:
            return False, "Failed to update CIF in database"

    def delete_cif(
        self,
        party_name: str,
        m_label: str,
        country: str,
        user_info: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Soft delete CIF

        Args:
            party_name: Party name
            m_label: CIF number
            country: Country code
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Check if exists
        existing = self.repository.get_by_cif_key(party_name, m_label, country)
        if not existing:
            return False, f"CIF '{m_label}' not found for party '{party_name}'"

        # Check if already deleted
        if existing.get('is_deleted'):
            return False, f"CIF '{m_label}' is already deleted"

        # Soft delete
        username = user_info.get('username', 'system')
        success = self.repository.soft_delete(party_name, m_label, country, username)

        if success:
            return True, None
        else:
            return False, "Failed to delete CIF in database"

    def get_cif_counts(self, is_active: Optional[bool] = None) -> Dict[str, int]:
        """
        Get CIF counts for all parties in a single query (optimized)

        Args:
            is_active: Optional filter by active status

        Returns:
            Dictionary mapping party_name to CIF count
        """
        return self.repository.get_cif_counts(is_active)

    def get_parties_with_multiple_cifs(self, is_active: Optional[bool] = None) -> List[str]:
        """
        Get list of party names that have multiple CIFs

        Args:
            is_active: Optional filter by active status

        Returns:
            List of party_name with count > 1
        """
        return self.repository.get_parties_with_multiple_cifs(is_active)


# Singleton instances
party_service = PartyService()
party_cif_service = PartyCIFService()
