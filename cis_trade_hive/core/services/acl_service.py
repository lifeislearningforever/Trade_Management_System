"""
ACL (Access Control List) Service

Implements Role-Based Access Control using Kudu tables.
Follows Single Responsibility and Dependency Inversion principles.
"""

import logging
from typing import Optional, Dict, List
from django.contrib.auth.models import User
from django.core.cache import cache
from django.conf import settings
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger('acl')


class ACLService:
    """
    Service for managing Access Control List permissions.

    Responsibilities:
    - Fetch user permissions from Kudu tables
    - Cache permissions for performance
    - Check user access rights
    """

    def __init__(self):
        self.cache_timeout = getattr(settings, 'ACL_CACHE_TIMEOUT', 300)
        self.database = settings.HIVE_CONFIG['DATABASE']

    def get_user_permissions(self, user: User) -> Dict[str, bool]:
        """
        Get all permissions for a user from Kudu ACL tables.

        Returns dictionary like:
        {
            'portfolio_view': True,
            'portfolio_create': True,
            'portfolio_edit': False,
            ...
        }
        """
        if not user or not user.is_authenticated:
            return settings.ACL_DEFAULT_PERMISSIONS.copy()

        # Try cache first
        cache_key = f'acl_permissions_{user.id}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # Fetch from Kudu
        permissions = self._fetch_permissions_from_kudu(user)

        # Cache the result
        cache.set(cache_key, permissions, self.cache_timeout)

        return permissions

    def _fetch_permissions_from_kudu(self, user: User) -> Dict[str, bool]:
        """
        Fetch user permissions from Kudu tables.

        Schema expected:
        - cis_user: user information
        - cis_user_group: user group assignments
        - cis_group_permissions: group permissions

        """
        try:
            # Query to get user's group and permissions
            query = f"""
                SELECT
                    gp.permission_name,
                    gp.can_view,
                    gp.can_create,
                    gp.can_edit,
                    gp.can_delete,
                    gp.can_approve
                FROM {self.database}.cis_user u
                JOIN {self.database}.cis_user_group ug ON u.user_id = ug.user_id
                JOIN {self.database}.cis_group_permissions gp ON ug.group_id = gp.group_id
                WHERE u.username = %s
                  AND u.is_active = TRUE
                  AND ug.is_active = TRUE
                  AND gp.is_active = TRUE
            """

            results = impala_manager.execute_query(query, [user.username])

            if not results:
                logger.warning(f"No ACL permissions found for user: {user.username}")
                return settings.ACL_DEFAULT_PERMISSIONS.copy()

            # Build permissions dictionary
            permissions = {}
            for row in results:
                perm_name = row.get('permission_name', '')
                permissions[f"{perm_name}_view"] = row.get('can_view', False)
                permissions[f"{perm_name}_create"] = row.get('can_create', False)
                permissions[f"{perm_name}_edit"] = row.get('can_edit', False)
                permissions[f"{perm_name}_delete"] = row.get('can_delete', False)
                permissions[f"{perm_name}_approve"] = row.get('can_approve', False)

            logger.info(f"Loaded {len(results)} permission rules for user: {user.username}")
            return permissions

        except Exception as e:
            logger.error(f"Failed to fetch ACL permissions: {str(e)}")
            return settings.ACL_DEFAULT_PERMISSIONS.copy()

    def has_permission(self, user: User, permission: str) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user: Django User object
            permission: Permission string like 'portfolio_create'

        Returns:
            True if user has permission, False otherwise
        """
        if not settings.ACL_ENABLED:
            return True  # ACL disabled, allow all

        if user and user.is_superuser:
            return True  # Superusers have all permissions

        permissions = self.get_user_permissions(user)
        return permissions.get(permission, False)

    def check_permission(self, user: User, permission: str):
        """
        Check permission and raise exception if not allowed.

        Raises:
            PermissionDenied if user doesn't have permission
        """
        from django.core.exceptions import PermissionDenied

        if not self.has_permission(user, permission):
            logger.warning(
                f"Permission denied: user={user.username if user else 'anonymous'}, "
                f"permission={permission}"
            )
            raise PermissionDenied(f"You do not have permission: {permission}")

    def clear_user_cache(self, user: User):
        """Clear cached permissions for a user"""
        cache_key = f'acl_permissions_{user.id}'
        cache.delete(cache_key)
        logger.info(f"Cleared ACL cache for user: {user.username}")

    def get_user_groups(self, user: User) -> List[Dict]:
        """Get all groups for a user"""
        try:
            query = f"""
                SELECT
                    g.group_id,
                    g.group_name,
                    g.description
                FROM {self.database}.cis_user u
                JOIN {self.database}.cis_user_group ug ON u.user_id = ug.user_id
                JOIN {self.database}.cis_group g ON ug.group_id = g.group_id
                WHERE u.username = %s
                  AND u.is_active = TRUE
                  AND ug.is_active = TRUE
                  AND g.is_active = TRUE
            """

            return impala_manager.execute_query(query, [user.username])

        except Exception as e:
            logger.error(f"Failed to fetch user groups: {str(e)}")
            return []


# Global ACL service instance
acl_service = ACLService()
