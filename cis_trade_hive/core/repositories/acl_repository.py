"""
ACL Repository for user and permission management.
Handles queries to Kudu/Impala ACL tables.
"""

import logging
from typing import Optional, List, Dict, Any
from .impala_connection import impala_manager

logger = logging.getLogger(__name__)


class ACLRepository:
    """
    Repository for ACL (Access Control List) operations.
    Follows Single Responsibility Principle.
    """

    def __init__(self):
        """Initialize ACL repository."""
        self.connection_manager = impala_manager

    def get_user_by_login(self, login: str) -> Optional[Dict[str, Any]]:
        """
        Get user by login ID.

        Args:
            login: User login ID (e.g., 'TMP4UG')

        Returns:
            Dictionary with user data or None if not found
        """
        try:
            query = f"""
                SELECT cis_user_id, login, name, entity, email, domain,
                       cis_user_group_id, is_deleted, enabled,
                       last_login, created_on, created_by, updated_on, updated_by
                FROM cis_user
                WHERE UPPER(login) = UPPER('{login}')
                  AND is_deleted = false
                  AND enabled = true
            """

            result = self.connection_manager.execute_query(query)

            if not result or len(result) == 0:
                return None

            return result[0]

        except Exception as e:
            logger.error(f"Error getting user by login: {str(e)}")
            logger.exception(e)
            return None

    def get_user_permissions(self, cis_user_group_id: int) -> List[Dict[str, Any]]:
        """
        Get all permissions for a user group.

        Args:
            cis_user_group_id: User group ID

        Returns:
            List of permission dictionaries
        """
        try:
            query = f"""
                SELECT cis_group_permissions_id, cis_user_group_id,
                       permission, read_write, is_deleted,
                       updated_on, updated_by
                FROM cis_group_permissions
                WHERE cis_user_group_id = {cis_user_group_id}
                  AND is_deleted = false
            """

            result = self.connection_manager.execute_query(query)
            return result if result else []

        except Exception as e:
            logger.error(f"Error getting user permissions: {str(e)}")
            logger.exception(e)
            return []

    def get_user_group(self, cis_user_group_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user group information.

        Args:
            cis_user_group_id: User group ID

        Returns:
            Dictionary with group data or None if not found
        """
        try:
            query = f"""
                SELECT cis_user_group_id, name, entity, description,
                       is_deleted, updated_on, updated_by
                FROM cis_user_group
                WHERE cis_user_group_id = {cis_user_group_id}
                  AND is_deleted = false
            """

            result = self.connection_manager.execute_query(query)

            if not result or len(result) == 0:
                return None

            return result[0]

        except Exception as e:
            logger.error(f"Error getting user group: {str(e)}")
            logger.exception(e)
            return None

    def has_permission(self, cis_user_group_id: int, permission: str, access_level: str = 'READ') -> bool:
        """
        Check if user group has specific permission with required access level.

        Args:
            cis_user_group_id: User group ID
            permission: Permission name (e.g., 'cis-portfolio')
            access_level: Required access level ('READ', 'WRITE')

        Returns:
            bool: True if user has permission, False otherwise
        """
        permissions = self.get_user_permissions(cis_user_group_id)

        for perm in permissions:
            if perm.get('permission') == permission:
                user_access = perm.get('read_write', '')

                # Check access level
                if access_level == 'READ':
                    return user_access in ['READ', 'WRITE']
                elif access_level == 'WRITE':
                    return user_access == 'WRITE'

        return False

    def authenticate_user(self, login: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user by login (simplified - no password for now).

        Args:
            login: User login ID

        Returns:
            Dictionary with user data and permissions, or None if authentication fails
        """
        user = self.get_user_by_login(login)

        if not user:
            logger.warning(f"Authentication failed: User {login} not found")
            return None

        # Get user group
        group = self.get_user_group(user['cis_user_group_id'])

        # Get permissions
        permissions = self.get_user_permissions(user['cis_user_group_id'])

        # Build permission map
        permission_map = {}
        for perm in permissions:
            perm_name = perm.get('permission')
            access_level = perm.get('read_write')
            permission_map[perm_name] = access_level

        return {
            'user': user,
            'group': group,
            'permissions': permissions,
            'permission_map': permission_map
        }

    def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Get all active users.

        Returns:
            List of user dictionaries
        """
        try:
            query = """
                SELECT cis_user_id, login, name, entity, email,
                       cis_user_group_id, enabled
                FROM cis_user
                WHERE is_deleted = false
            """

            result = self.connection_manager.execute_query(query)
            return result if result else []

        except Exception as e:
            logger.error(f"Error getting all users: {str(e)}")
            return []

    def update_last_login(self, login: str) -> bool:
        """
        Update user's last login timestamp.

        Note: This would require write access to Hive which might not be
        available in all environments. For now, we'll log it.

        Args:
            login: User login ID

        Returns:
            bool: True if successful
        """
        # Since we're using TEXT tables and Hive doesn't easily support
        # UPDATE operations, we'll just log this action
        logger.info(f"User {login} logged in")
        return True


# Singleton instance
_acl_repository = None


def get_acl_repository():
    """
    Factory function to get appropriate ACL repository based on RBAC_VERSION setting.

    This factory enables seamless switching between legacy (v1) and new (v2) RBAC systems
    via the RBAC_VERSION environment variable or Django setting.

    Configuration:
        Set RBAC_VERSION in environment or settings.py:
        - 'v1' (default): Uses legacy ACLRepository (cis_user, cis_user_group, cis_group_permissions)
        - 'v2': Uses new ACLRepositoryV2 (cis_user_info, cis_user_group_info, cis_permission_info,
                cis_user_group_mapping_info, cis_group_permission_map)

    Returns:
        ACLRepository or ACLRepositoryV2: Singleton instance based on RBAC_VERSION

    Rollback:
        To rollback from v2 to v1:
        1. Set RBAC_VERSION=v1 in environment
        2. Restart the application
        No database changes required.

    Example:
        >>> from core.repositories.acl_repository import get_acl_repository
        >>> acl_repo = get_acl_repository()
        >>> auth_data = acl_repo.authenticate_user('TMP3RC')

    Note:
        - Both v1 and v2 return compatible auth_data structures
        - v2 adds 'groups' (list) and 'group_names' keys
        - v2 supports multi-group membership
        - The factory caches the singleton based on version

    Migration Checklist:
        1. Populate new RBAC tables in production
        2. Test with RBAC_VERSION=v2 in development
        3. Deploy with RBAC_VERSION=v2
        4. Monitor for issues
        5. If issues, rollback by setting RBAC_VERSION=v1 and restart
    """
    global _acl_repository

    from django.conf import settings

    rbac_version = getattr(settings, 'RBAC_VERSION', 'v1')

    # Check if we need to create or switch repository
    if _acl_repository is not None:
        # Check if version changed (for hot-reload scenarios)
        current_version = getattr(_acl_repository, '_rbac_version', 'v1')
        if current_version != rbac_version:
            logger.info(f"RBAC version changed from {current_version} to {rbac_version}, recreating repository")
            _acl_repository = None

    if _acl_repository is None:
        if rbac_version == 'v2':
            from .acl_repository_v2 import ACLRepositoryV2
            _acl_repository = ACLRepositoryV2()
            _acl_repository._rbac_version = 'v2'
            logger.info("Initialized ACL Repository V2 (new RBAC tables with multi-group support)")
        else:
            _acl_repository = ACLRepository()
            _acl_repository._rbac_version = 'v1'
            logger.info("Initialized ACL Repository V1 (legacy tables)")

    return _acl_repository


def get_rbac_version() -> str:
    """
    Get the current RBAC version from settings.

    Returns:
        str: 'v1' or 'v2'
    """
    from django.conf import settings
    return getattr(settings, 'RBAC_VERSION', 'v1')


def reset_acl_repository() -> None:
    """
    Reset the singleton ACL repository.

    Useful for testing or when RBAC_VERSION changes.
    The next call to get_acl_repository() will create a new instance.

    Example:
        >>> from core.repositories.acl_repository import reset_acl_repository
        >>> reset_acl_repository()
        >>> repo = get_acl_repository()  # Creates new instance
    """
    global _acl_repository
    _acl_repository = None
    logger.info("ACL repository singleton reset")
