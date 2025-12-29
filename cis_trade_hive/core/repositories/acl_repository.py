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

            result = self.connection_manager.execute_query(query, database='gmp_cis')

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

            result = self.connection_manager.execute_query(query, database='gmp_cis')
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

            result = self.connection_manager.execute_query(query, database='gmp_cis')

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
            access_level: Required access level ('READ', 'WRITE', 'READ_WRITE')

        Returns:
            bool: True if user has permission, False otherwise
        """
        permissions = self.get_user_permissions(cis_user_group_id)

        for perm in permissions:
            if perm.get('permission') == permission:
                user_access = perm.get('read_write', '')

                # Check access level
                if access_level == 'READ':
                    return user_access in ['READ', 'WRITE', 'READ_WRITE']
                elif access_level == 'WRITE':
                    return user_access in ['WRITE', 'READ_WRITE']
                elif access_level == 'READ_WRITE':
                    return user_access == 'READ_WRITE'

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

            result = self.connection_manager.execute_query(query, database='gmp_cis')
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


def get_acl_repository() -> ACLRepository:
    """
    Get singleton ACL repository instance.

    Returns:
        ACLRepository instance
    """
    global _acl_repository
    if _acl_repository is None:
        _acl_repository = ACLRepository()
    return _acl_repository
