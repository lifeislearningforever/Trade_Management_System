"""
ACL Repository for user and permission management.
Handles queries to Hive ACL tables (ORC + ACID).

Tables:
- cis_user: User accounts
- cis_user_group: User groups
- cis_group_permissions: Group permissions
- cis_user_group_membership: User-group associations
"""

import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from .hive_connection import hive_manager

logger = logging.getLogger(__name__)


class ACLRepository:
    """
    Repository for ACL (Access Control List) operations.
    Uses Hive managed tables with ORC format and ACID support.
    """

    def __init__(self):
        """Initialize ACL repository."""
        self.connection_manager = hive_manager
        self.database = 'gmp_cis'

    def _format_value(self, value: Any) -> str:
        """Format value for SQL query."""
        if value is None:
            return "NULL"
        elif isinstance(value, str):
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        elif isinstance(value, datetime):
            return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
        elif isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        else:
            return str(value)

    def _generate_id(self, prefix: str = '') -> str:
        """Generate a unique ID with optional prefix."""
        unique_part = str(uuid.uuid4())[:8].upper()
        return f"{prefix}{unique_part}" if prefix else unique_part

    # =========================================================================
    # USER OPERATIONS
    # =========================================================================

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get user by username.

        Args:
            username: User's username

        Returns:
            Dictionary with user data or None if not found
        """
        try:
            query = f"""
                SELECT user_id, username, email, full_name, department,
                       is_active, created_at, created_by, updated_at, updated_by
                FROM {self.database}.cis_user
                WHERE LOWER(username) = LOWER('{username}')
                  AND deleted_at IS NULL
                  AND is_active = TRUE
            """

            result = self.connection_manager.execute_query(query, database=self.database)

            if not result or len(result) == 0:
                return None

            return result[0]

        except Exception as e:
            logger.error(f"Error getting user by username: {str(e)}")
            logger.exception(e)
            return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        try:
            query = f"""
                SELECT user_id, username, email, full_name, department,
                       is_active, created_at, created_by, updated_at, updated_by
                FROM {self.database}.cis_user
                WHERE user_id = '{user_id}'
                  AND deleted_at IS NULL
            """

            result = self.connection_manager.execute_query(query, database=self.database)
            return result[0] if result else None

        except Exception as e:
            logger.error(f"Error getting user by ID: {str(e)}")
            return None

    def get_all_users(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        Get all users.

        Args:
            include_inactive: If True, include inactive users

        Returns:
            List of user dictionaries
        """
        try:
            where_clause = "WHERE deleted_at IS NULL"
            if not include_inactive:
                where_clause += " AND is_active = TRUE"

            query = f"""
                SELECT user_id, username, email, full_name, department, is_active
                FROM {self.database}.cis_user
                {where_clause}
            """

            result = self.connection_manager.execute_query(query, database=self.database)
            return result if result else []

        except Exception as e:
            logger.error(f"Error getting all users: {str(e)}")
            return []

    def create_user(self, user_data: Dict[str, Any], created_by: str = 'system') -> Optional[str]:
        """
        Create a new user.

        Args:
            user_data: Dictionary with user data (username, email, full_name, department)
            created_by: Username of creator

        Returns:
            User ID if successful, None otherwise
        """
        try:
            user_id = self._generate_id('U')
            now = datetime.now()

            query = f"""
                INSERT INTO {self.database}.cis_user
                (user_id, username, email, full_name, department, is_active,
                 created_at, created_by, updated_at, updated_by, deleted_at)
                VALUES (
                    '{user_id}',
                    {self._format_value(user_data.get('username'))},
                    {self._format_value(user_data.get('email'))},
                    {self._format_value(user_data.get('full_name'))},
                    {self._format_value(user_data.get('department'))},
                    TRUE,
                    '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    '{created_by}',
                    '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    '{created_by}',
                    NULL
                )
            """

            if self.connection_manager.execute_write(query, database=self.database):
                logger.info(f"Created user {user_data.get('username')} with ID {user_id}")
                return user_id
            return None

        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            return None

    # =========================================================================
    # GROUP OPERATIONS
    # =========================================================================

    def get_user_groups(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all groups a user belongs to.

        Args:
            user_id: User ID

        Returns:
            List of group dictionaries
        """
        try:
            # First get group IDs from membership table
            membership_query = f"""
                SELECT group_id
                FROM {self.database}.cis_user_group_membership
                WHERE user_id = '{user_id}'
                  AND deleted_at IS NULL
            """
            memberships = self.connection_manager.execute_query(
                membership_query, database=self.database
            )

            if not memberships:
                return []

            # Then get group details for each group_id
            group_ids = [m['group_id'] for m in memberships]
            groups = []

            for group_id in group_ids:
                group = self.get_group_by_id(group_id)
                if group and group.get('is_active'):
                    groups.append(group)

            return groups

        except Exception as e:
            logger.error(f"Error getting user groups: {str(e)}")
            return []

    def get_group_by_id(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get group by ID."""
        try:
            query = f"""
                SELECT group_id, group_name, description, is_active,
                       created_at, created_by, updated_at, updated_by
                FROM {self.database}.cis_user_group
                WHERE group_id = '{group_id}'
                  AND deleted_at IS NULL
            """

            result = self.connection_manager.execute_query(query, database=self.database)
            return result[0] if result else None

        except Exception as e:
            logger.error(f"Error getting group by ID: {str(e)}")
            return None

    def get_all_groups(self) -> List[Dict[str, Any]]:
        """Get all active groups."""
        try:
            query = f"""
                SELECT group_id, group_name, description, is_active
                FROM {self.database}.cis_user_group
                WHERE deleted_at IS NULL
                  AND is_active = TRUE
            """

            result = self.connection_manager.execute_query(query, database=self.database)
            return result if result else []

        except Exception as e:
            logger.error(f"Error getting all groups: {str(e)}")
            return []

    def create_group(self, group_data: Dict[str, Any], created_by: str = 'system') -> Optional[str]:
        """Create a new group."""
        try:
            group_id = self._generate_id('G')
            now = datetime.now()

            query = f"""
                INSERT INTO {self.database}.cis_user_group
                (group_id, group_name, description, is_active,
                 created_at, created_by, updated_at, updated_by, deleted_at)
                VALUES (
                    '{group_id}',
                    {self._format_value(group_data.get('group_name'))},
                    {self._format_value(group_data.get('description'))},
                    TRUE,
                    '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    '{created_by}',
                    '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    '{created_by}',
                    NULL
                )
            """

            if self.connection_manager.execute_write(query, database=self.database):
                logger.info(f"Created group {group_data.get('group_name')} with ID {group_id}")
                return group_id
            return None

        except Exception as e:
            logger.error(f"Error creating group: {str(e)}")
            return None

    def add_user_to_group(self, user_id: str, group_id: str, created_by: str = 'system') -> bool:
        """Add a user to a group."""
        try:
            membership_id = self._generate_id('M')
            now = datetime.now()

            query = f"""
                INSERT INTO {self.database}.cis_user_group_membership
                (membership_id, user_id, group_id, created_at, created_by, deleted_at)
                VALUES (
                    '{membership_id}',
                    '{user_id}',
                    '{group_id}',
                    '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    '{created_by}',
                    NULL
                )
            """

            success = self.connection_manager.execute_write(query, database=self.database)
            if success:
                logger.info(f"Added user {user_id} to group {group_id}")
            return success

        except Exception as e:
            logger.error(f"Error adding user to group: {str(e)}")
            return False

    # =========================================================================
    # PERMISSION OPERATIONS
    # =========================================================================

    def get_user_permissions(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all permissions for a user (through their groups).

        Args:
            user_id: User ID

        Returns:
            List of permission dictionaries
        """
        try:
            # Get user's groups first (avoiding JOIN issues with Hive ACID tables)
            groups = self.get_user_groups(user_id)
            if not groups:
                return []

            # Get permissions for each group
            all_permissions = []
            for group in groups:
                group_perms = self.get_group_permissions(group['group_id'])
                all_permissions.extend(group_perms)

            # Remove duplicates based on resource+action
            seen = set()
            unique_perms = []
            for perm in all_permissions:
                key = (perm.get('resource'), perm.get('action'))
                if key not in seen:
                    seen.add(key)
                    unique_perms.append(perm)

            return unique_perms

        except Exception as e:
            logger.error(f"Error getting user permissions: {str(e)}")
            return []

    def get_group_permissions(self, group_id: str) -> List[Dict[str, Any]]:
        """Get all permissions for a group."""
        try:
            query = f"""
                SELECT permission_id, group_id, resource, action, is_allowed
                FROM {self.database}.cis_group_permissions
                WHERE group_id = '{group_id}'
                  AND deleted_at IS NULL
            """

            result = self.connection_manager.execute_query(query, database=self.database)
            return result if result else []

        except Exception as e:
            logger.error(f"Error getting group permissions: {str(e)}")
            return []

    def has_permission(self, user_id: str, resource: str, action: str = 'READ') -> bool:
        """
        Check if user has specific permission.

        Args:
            user_id: User ID
            resource: Resource name (e.g., 'portfolio', 'trade')
            action: Required action ('READ', 'WRITE', 'DELETE', 'ADMIN')

        Returns:
            bool: True if user has permission
        """
        try:
            query = f"""
                SELECT 1
                FROM {self.database}.cis_group_permissions p
                JOIN {self.database}.cis_user_group_membership m ON p.group_id = m.group_id
                WHERE m.user_id = '{user_id}'
                  AND m.deleted_at IS NULL
                  AND p.deleted_at IS NULL
                  AND p.resource = '{resource}'
                  AND p.action = '{action}'
                  AND p.is_allowed = TRUE
                LIMIT 1
            """

            result = self.connection_manager.execute_query(query, database=self.database)
            return len(result) > 0

        except Exception as e:
            logger.error(f"Error checking permission: {str(e)}")
            return False

    def grant_permission(self, group_id: str, resource: str, action: str,
                        created_by: str = 'system') -> bool:
        """Grant permission to a group."""
        try:
            permission_id = self._generate_id('P')
            now = datetime.now()

            query = f"""
                INSERT INTO {self.database}.cis_group_permissions
                (permission_id, group_id, resource, action, is_allowed,
                 created_at, created_by, updated_at, updated_by, deleted_at)
                VALUES (
                    '{permission_id}',
                    '{group_id}',
                    '{resource}',
                    '{action}',
                    TRUE,
                    '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    '{created_by}',
                    '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    '{created_by}',
                    NULL
                )
            """

            success = self.connection_manager.execute_write(query, database=self.database)
            if success:
                logger.info(f"Granted {action} permission on {resource} to group {group_id}")
            return success

        except Exception as e:
            logger.error(f"Error granting permission: {str(e)}")
            return False

    # =========================================================================
    # AUTHENTICATION
    # =========================================================================

    def authenticate_user(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user by username (simplified - no password for now).

        Args:
            username: User username

        Returns:
            Dictionary with user data and permissions, or None if authentication fails
        """
        user = self.get_user_by_username(username)

        if not user:
            logger.warning(f"Authentication failed: User {username} not found")
            return None

        # Get user groups
        groups = self.get_user_groups(user['user_id'])

        # Get permissions
        permissions = self.get_user_permissions(user['user_id'])

        # Build permission map
        permission_map = {}
        for perm in permissions:
            resource = perm.get('resource')
            action = perm.get('action')
            if resource not in permission_map:
                permission_map[resource] = []
            if action not in permission_map[resource]:
                permission_map[resource].append(action)

        # Build user dict with expected keys for auth view
        user_data = {
            'login': user.get('username'),
            'cis_user_id': user.get('user_id'),
            'cis_user_group_id': groups[0].get('group_id') if groups else None,
            'name': user.get('full_name'),
            'email': user.get('email'),
        }

        # Primary group
        primary_group = groups[0] if groups else None
        group_data = {
            'name': primary_group.get('group_name') if primary_group else None
        } if primary_group else None

        return {
            'user': user_data,
            'group': group_data,
            'groups': groups,
            'permissions': permissions,
            'permission_map': permission_map
        }


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
