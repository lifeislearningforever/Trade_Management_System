"""
ACL Repository V2 - Role-Based Access Control for New Table Structure.

This module provides the data access layer for the new RBAC tables:
- cis_user_info: User master data
- cis_user_group_info: Group definitions
- cis_permission_info: Permission definitions
- cis_user_group_mapping_info: User to Group mappings (multi-group support)
- cis_group_permission_map: Group to Permission mappings

Features:
- Multi-group support: Users can belong to multiple groups
- Permission aggregation: Union of permissions from all user groups
- Entity-aware: All queries filter by entity (e.g., UOBS)
- Caching: Results are cached for performance
- Comprehensive logging: All operations are logged

Usage:
    from core.repositories.acl_repository_v2 import get_acl_repository_v2

    acl_repo = get_acl_repository_v2()
    auth_data = acl_repo.authenticate_user('TMP3RC')

    if auth_data:
        user = auth_data['user']
        groups = auth_data['groups']  # List of groups
        permissions = auth_data['permission_map']  # Aggregated permissions

Migration:
    Set RBAC_VERSION='v2' in settings to use this repository.
    Set RBAC_VERSION='v1' to rollback to legacy repository.

Author: CIS Trade Hive Team
Version: 2.0
Created: 2026-04-05
"""

import logging
from typing import Optional, List, Dict, Any, Set, Tuple
from functools import lru_cache
from datetime import datetime, timedelta

from .impala_connection import impala_manager

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300


class ACLRepositoryV2:
    """
    Repository for Role-Based Access Control (RBAC) operations.

    This repository queries the new RBAC tables and provides:
    - User authentication
    - Group membership lookup (multi-group support)
    - Permission aggregation across all user groups
    - Permission checking with mode (READ, WRITE)

    Attributes:
        connection_manager: Impala connection manager for database queries
        _cache: In-memory cache for user data
        _cache_timestamps: Cache entry timestamps for TTL management

    Example:
        >>> repo = ACLRepositoryV2()
        >>> auth_data = repo.authenticate_user('TMP3RC')
        >>> if auth_data:
        ...     print(f"User: {auth_data['user']['name']}")
        ...     print(f"Groups: {[g['group_name'] for g in auth_data['groups']]}")
        ...     print(f"Can create trades: {auth_data['permission_map'].get('trade-create')}")
    """

    # Table names (configurable for different environments)
    TABLE_USER = 'cis_user_info'
    TABLE_GROUP = 'cis_user_group_info'
    TABLE_PERMISSION = 'cis_permission_info'
    TABLE_USER_GROUP_MAPPING = 'cis_user_group_mapping_info'
    TABLE_GROUP_PERMISSION_MAP = 'cis_group_permission_map'

    def __init__(self, database: str = 'gmp_cis'):
        """
        Initialize ACL Repository V2.

        Args:
            database: Database name (default: 'gmp_cis')
        """
        self.connection_manager = impala_manager
        self.database = database
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}

    def _is_cache_valid(self, cache_key: str) -> bool:
        """
        Check if cache entry is still valid based on TTL.

        Args:
            cache_key: The cache key to check

        Returns:
            bool: True if cache is valid, False if expired or missing
        """
        if cache_key not in self._cache_timestamps:
            return False

        elapsed = (datetime.now() - self._cache_timestamps[cache_key]).total_seconds()
        return elapsed < CACHE_TTL

    def _set_cache(self, cache_key: str, value: Any) -> None:
        """
        Set cache entry with timestamp.

        Args:
            cache_key: The cache key
            value: The value to cache
        """
        self._cache[cache_key] = value
        self._cache_timestamps[cache_key] = datetime.now()

    def _get_cache(self, cache_key: str) -> Optional[Any]:
        """
        Get cache entry if valid.

        Args:
            cache_key: The cache key

        Returns:
            Cached value if valid, None otherwise
        """
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key)
        return None

    def clear_cache(self, user_login: Optional[str] = None) -> None:
        """
        Clear cache for a specific user or all users.

        Args:
            user_login: Optional user login to clear. If None, clears all cache.

        Example:
            >>> repo.clear_cache('TMP3RC')  # Clear specific user
            >>> repo.clear_cache()  # Clear all
        """
        if user_login:
            cache_key = f"user:{user_login.upper()}"
            self._cache.pop(cache_key, None)
            self._cache_timestamps.pop(cache_key, None)
            logger.debug(f"Cleared cache for user: {user_login}")
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
            logger.debug("Cleared all ACL cache")

    def get_user_by_login(self, login: str, entity: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get user by login ID.

        Queries cis_user_info table for active, non-deleted user matching the login.

        Args:
            login: User login ID (e.g., 'TMP3RC', 'UNCSHR')
            entity: Optional entity filter (e.g., 'UOBS')

        Returns:
            Dictionary with user data or None if not found.
            Keys: user_id, login, email, name, default_entity, last_login,
                  is_active, created_on, created_by, updated_on, updated_by

        Raises:
            Exception: If database query fails (logged and returns None)

        Example:
            >>> user = repo.get_user_by_login('TMP3RC')
            >>> if user:
            ...     print(f"Found user: {user['name']}")
        """
        try:
            login_escaped = login.replace("'", "''").upper()

            query = f"""
                SELECT user_id, login, email, name, default_entity, last_login,
                       is_active, is_deleted, created_on, created_by, updated_on, updated_by
                FROM {self.TABLE_USER}
                WHERE UPPER(login) = '{login_escaped}'
                  AND is_active = true
                  AND is_deleted = false
            """

            if entity:
                entity_escaped = entity.replace("'", "''").upper()
                query += f" AND UPPER(default_entity) = '{entity_escaped}'"

            query += " LIMIT 1"

            result = self.connection_manager.execute_query(query, database=self.database)

            if not result or len(result) == 0:
                logger.debug(f"User not found: {login}")
                return None

            logger.debug(f"Found user: {login}")
            return result[0]

        except Exception as e:
            logger.error(f"Error getting user by login '{login}': {str(e)}")
            logger.exception(e)
            return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user by user_id.

        Args:
            user_id: User ID (primary key)

        Returns:
            Dictionary with user data or None if not found.

        Example:
            >>> user = repo.get_user_by_id('1773384561790')
        """
        try:
            user_id_escaped = str(user_id).replace("'", "''")

            query = f"""
                SELECT user_id, login, email, name, default_entity, last_login,
                       is_active, is_deleted, created_on, created_by, updated_on, updated_by
                FROM {self.TABLE_USER}
                WHERE user_id = '{user_id_escaped}'
                  AND is_active = true
                  AND is_deleted = false
                LIMIT 1
            """

            result = self.connection_manager.execute_query(query, database=self.database)

            if not result or len(result) == 0:
                return None

            return result[0]

        except Exception as e:
            logger.error(f"Error getting user by ID '{user_id}': {str(e)}")
            return None

    def get_user_groups(self, user_id: str, entity: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all groups for a user.

        Queries cis_user_group_mapping_info to find all groups the user belongs to.
        Supports multi-group membership.

        Args:
            user_id: User ID from cis_user_info
            entity: Optional entity filter

        Returns:
            List of group dictionaries with keys:
            - group_name: Name of the group (e.g., 'SG-TRADER')
            - entity: Entity (e.g., 'UOBS')
            - mapping_id: Mapping record ID

        Example:
            >>> groups = repo.get_user_groups('1773384561790')
            >>> for g in groups:
            ...     print(f"Group: {g['group_name']}")
        """
        try:
            user_id_escaped = str(user_id).replace("'", "''")

            query = f"""
                SELECT ugm.user_group_mapping_id as mapping_id,
                       ugm.group_name,
                       ugm.entity,
                       ugi.description as group_description
                FROM {self.TABLE_USER_GROUP_MAPPING} ugm
                LEFT JOIN {self.TABLE_GROUP} ugi
                    ON ugm.group_name = ugi.group_name
                    AND ugm.entity = ugi.entity
                WHERE ugm.user_id = '{user_id_escaped}'
                  AND ugm.is_active = true
                  AND ugm.is_deleted = false
            """

            if entity:
                entity_escaped = entity.replace("'", "''").upper()
                query += f" AND UPPER(ugm.entity) = '{entity_escaped}'"

            query += " ORDER BY ugm.group_name"

            result = self.connection_manager.execute_query(query, database=self.database)
            return result if result else []

        except Exception as e:
            logger.error(f"Error getting groups for user '{user_id}': {str(e)}")
            logger.exception(e)
            return []

    def get_group_permissions(
        self,
        group_name: str,
        entity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all permissions for a group.

        Queries cis_group_permission_map for all permissions assigned to the group.

        Args:
            group_name: Group name (e.g., 'SG-TRADER')
            entity: Optional entity filter

        Returns:
            List of permission dictionaries with keys:
            - permission_name: Name of permission (e.g., 'trade-create')
            - mode: Access mode ('READ' or 'WRITE')
            - description: Permission description

        Example:
            >>> perms = repo.get_group_permissions('SG-TRADER')
            >>> for p in perms:
            ...     print(f"{p['permission_name']}: {p['mode']}")
        """
        try:
            group_escaped = group_name.replace("'", "''")

            query = f"""
                SELECT permission_name, mode, description
                FROM {self.TABLE_GROUP_PERMISSION_MAP}
                WHERE group_name = '{group_escaped}'
                  AND is_active = true
                  AND is_deleted = false
            """

            if entity:
                entity_escaped = entity.replace("'", "''").upper()
                query += f" AND UPPER(entity) = '{entity_escaped}'"

            query += " ORDER BY permission_name"

            result = self.connection_manager.execute_query(query, database=self.database)
            return result if result else []

        except Exception as e:
            logger.error(f"Error getting permissions for group '{group_name}': {str(e)}")
            logger.exception(e)
            return []

    def get_aggregated_permissions(
        self,
        user_id: str,
        entity: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Get aggregated permissions across all user groups.

        For users belonging to multiple groups, this method:
        1. Fetches all groups the user belongs to
        2. Fetches permissions for each group
        3. Aggregates permissions (WRITE takes precedence over READ)

        Args:
            user_id: User ID
            entity: Optional entity filter

        Returns:
            Dictionary mapping permission_name to highest access mode.
            Example: {'trade-create': 'WRITE', 'trade-list': 'READ'}

        Note:
            If a user has READ from one group and WRITE from another,
            WRITE is used (highest privilege wins).

        Example:
            >>> perms = repo.get_aggregated_permissions('1773384561790')
            >>> if perms.get('trade-create') == 'WRITE':
            ...     print("User can create trades")
        """
        try:
            # Get all groups for user
            groups = self.get_user_groups(user_id, entity)

            if not groups:
                logger.debug(f"User {user_id} has no group memberships")
                return {}

            # Aggregate permissions from all groups
            permission_map: Dict[str, str] = {}

            for group in groups:
                group_name = group.get('group_name')
                if not group_name:
                    continue

                group_perms = self.get_group_permissions(group_name, entity)

                for perm in group_perms:
                    perm_name = perm.get('permission_name')
                    raw_mode = perm.get('mode', 'READ')

                    if not perm_name:
                        continue

                    # Normalise READ_WRITE (stored in DB) → WRITE (used by has_perm checks)
                    mode = 'WRITE' if raw_mode == 'READ_WRITE' else raw_mode

                    # Use highest privilege (WRITE > READ)
                    existing_mode = permission_map.get(perm_name)
                    if existing_mode is None or mode == 'WRITE':
                        permission_map[perm_name] = mode

            logger.debug(f"Aggregated {len(permission_map)} permissions for user {user_id}")
            return permission_map

        except Exception as e:
            logger.error(f"Error aggregating permissions for user '{user_id}': {str(e)}")
            logger.exception(e)
            return {}

    def has_permission(
        self,
        user_id: str,
        permission: str,
        required_mode: str = 'READ',
        entity: Optional[str] = None
    ) -> bool:
        """
        Check if user has specific permission with required access level.

        Args:
            user_id: User ID
            permission: Permission name (e.g., 'trade-create')
            required_mode: Required access level ('READ' or 'WRITE')
            entity: Optional entity filter

        Returns:
            bool: True if user has permission with required or higher access

        Access Level Hierarchy:
            - WRITE includes READ access
            - READ does not include WRITE access

        Example:
            >>> if repo.has_permission('123', 'trade-create', 'WRITE'):
            ...     print("User can create trades")
        """
        try:
            permissions = self.get_aggregated_permissions(user_id, entity)
            user_mode = permissions.get(permission)

            if user_mode is None:
                return False

            if required_mode == 'READ':
                return user_mode in ('READ', 'WRITE')
            elif required_mode == 'WRITE':
                return user_mode == 'WRITE'

            return False

        except Exception as e:
            logger.error(f"Error checking permission '{permission}' for user '{user_id}': {str(e)}")
            return False

    def authenticate_user(self, login: str, entity: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Authenticate user and retrieve full authorization data.

        This is the main authentication method that:
        1. Looks up user by login
        2. Retrieves all group memberships
        3. Aggregates permissions from all groups
        4. Returns complete auth data for session storage

        Args:
            login: User login ID (e.g., 'TMP3RC')
            entity: Optional entity filter

        Returns:
            Dictionary with authentication data or None if auth fails.

            On success, returns:
            {
                'user': {
                    'user_id': '123',
                    'login': 'TMP3RC',
                    'name': 'PRAKASH HOSALLI',
                    'email': 'prakash@example.com',
                    'default_entity': 'UOBS',
                    ...
                },
                'groups': [
                    {'group_name': 'SG-TRADER', 'entity': 'UOBS', ...},
                    {'group_name': 'CIS-OPS', 'entity': 'UOBS', ...}
                ],
                'permissions': [
                    {'permission_name': 'trade-create', 'mode': 'WRITE', ...},
                    ...
                ],
                'permission_map': {
                    'trade-create': 'WRITE',
                    'trade-list': 'READ',
                    ...
                },
                'group_names': ['SG-TRADER', 'CIS-OPS']
            }

        Caching:
            Results are cached for CACHE_TTL seconds (default: 5 minutes).
            Use clear_cache() to force refresh.

        Example:
            >>> auth = repo.authenticate_user('TMP3RC')
            >>> if auth:
            ...     print(f"Welcome {auth['user']['name']}")
            ...     print(f"Groups: {auth['group_names']}")
            ...     if auth['permission_map'].get('trade-create') == 'WRITE':
            ...         print("You can create trades")
        """
        login_upper = login.upper()
        cache_key = f"user:{login_upper}"

        # Check cache first
        cached = self._get_cache(cache_key)
        if cached:
            logger.debug(f"Returning cached auth data for: {login}")
            return cached

        try:
            # Get user
            user = self.get_user_by_login(login, entity)

            if not user:
                logger.warning(f"Authentication failed: User '{login}' not found")
                return None

            user_id = user.get('user_id')
            user_entity = entity or user.get('default_entity')

            # Get all groups
            groups = self.get_user_groups(user_id, user_entity)

            if not groups:
                logger.warning(f"Authentication warning: User '{login}' has no group memberships")
                # Still allow login but with no permissions
                groups = []

            # Get aggregated permissions
            permission_map = self.get_aggregated_permissions(user_id, user_entity)

            # Build full permissions list for audit/display
            all_permissions = []
            for group in groups:
                group_perms = self.get_group_permissions(group.get('group_name'), user_entity)
                all_permissions.extend(group_perms)

            # Build result
            auth_data = {
                'user': user,
                'groups': groups,
                'permissions': all_permissions,
                'permission_map': permission_map,
                'group_names': [g.get('group_name') for g in groups if g.get('group_name')]
            }

            # Cache result
            self._set_cache(cache_key, auth_data)

            logger.info(f"Authentication successful for: {login} (groups: {auth_data['group_names']})")
            return auth_data

        except Exception as e:
            logger.error(f"Authentication error for '{login}': {str(e)}")
            logger.exception(e)
            return None

    def get_all_users(self, entity: Optional[str] = None, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        Get all users.

        Args:
            entity: Optional entity filter
            include_inactive: If True, include inactive users

        Returns:
            List of user dictionaries

        Example:
            >>> users = repo.get_all_users(entity='UOBS')
            >>> print(f"Found {len(users)} users")
        """
        try:
            query = f"""
                SELECT user_id, login, email, name, default_entity, is_active
                FROM {self.TABLE_USER}
                WHERE is_deleted = false
            """

            if not include_inactive:
                query += " AND is_active = true"

            if entity:
                entity_escaped = entity.replace("'", "''").upper()
                query += f" AND UPPER(default_entity) = '{entity_escaped}'"

            query += " ORDER BY name"

            result = self.connection_manager.execute_query(query, database=self.database)
            return result if result else []

        except Exception as e:
            logger.error(f"Error getting all users: {str(e)}")
            return []

    def get_all_groups(self, entity: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all groups.

        Args:
            entity: Optional entity filter

        Returns:
            List of group dictionaries

        Example:
            >>> groups = repo.get_all_groups()
            >>> for g in groups:
            ...     print(f"{g['group_name']}: {g['description']}")
        """
        try:
            query = f"""
                SELECT user_group_id, group_name, description, entity, is_active
                FROM {self.TABLE_GROUP}
                WHERE is_deleted = false
                  AND is_active = true
            """

            if entity:
                entity_escaped = entity.replace("'", "''").upper()
                query += f" AND UPPER(entity) = '{entity_escaped}'"

            query += " ORDER BY group_name"

            result = self.connection_manager.execute_query(query, database=self.database)
            return result if result else []

        except Exception as e:
            logger.error(f"Error getting all groups: {str(e)}")
            return []

    def get_all_permissions(self, entity: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all defined permissions.

        Args:
            entity: Optional entity filter

        Returns:
            List of permission dictionaries

        Example:
            >>> perms = repo.get_all_permissions()
            >>> print(f"System has {len(perms)} defined permissions")
        """
        try:
            query = f"""
                SELECT permission_id, permission_name, description, entity, is_active
                FROM {self.TABLE_PERMISSION}
                WHERE is_deleted = false
                  AND is_active = true
            """

            if entity:
                entity_escaped = entity.replace("'", "''").upper()
                query += f" AND UPPER(entity) = '{entity_escaped}'"

            query += " ORDER BY permission_name"

            result = self.connection_manager.execute_query(query, database=self.database)
            return result if result else []

        except Exception as e:
            logger.error(f"Error getting all permissions: {str(e)}")
            return []

    def update_last_login(self, login: str) -> bool:
        """
        Persist last_login timestamp on cis_user_info at successful login.

        Fetches the current user row by login, then UPSERTs it back with
        last_login = NOW() and updated_on = NOW().  All other columns are
        preserved unchanged so no data is lost.

        Args:
            login: User login ID (e.g. 'TMP3RC')

        Returns:
            bool: True if written, False if user not found or write failed
        """
        try:
            user = self.get_user_by_login(login)
            if not user:
                logger.warning(f"update_last_login: user '{login}' not found")
                return False

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            esc = lambda v: str(v).replace("'", "''") if v is not None else ''

            upsert_sql = f"""
                UPSERT INTO {self.database}.{self.TABLE_USER}
                (user_id, login, email, name, default_entity,
                 last_login, is_active, is_deleted,
                 created_on, created_by, updated_on, updated_by)
                VALUES (
                    '{esc(user["user_id"])}',
                    '{esc(user["login"])}',
                    '{esc(user.get("email", ""))}',
                    '{esc(user.get("name", ""))}',
                    '{esc(user.get("default_entity", ""))}',
                    '{now}',
                    {str(user.get("is_active", True)).lower()},
                    {str(user.get("is_deleted", False)).lower()},
                    '{esc(user.get("created_on", now))}',
                    '{esc(user.get("created_by", login))}',
                    '{now}',
                    '{esc(login)}'
                )
            """

            ok = self.connection_manager.execute_write(upsert_sql, database=self.database)
            if ok:
                self.clear_cache(login)
                logger.info(f"last_login updated for user '{login}'")
            return bool(ok)

        except Exception as e:
            logger.error(f"Error updating last_login for '{login}': {str(e)}")
            return False


# ============================================================================
# Singleton Instance and Factory
# ============================================================================

_acl_repository_v2: Optional[ACLRepositoryV2] = None


def get_acl_repository_v2() -> ACLRepositoryV2:
    """
    Get singleton ACL Repository V2 instance.

    This factory function ensures only one instance exists,
    which is important for cache efficiency.

    Returns:
        ACLRepositoryV2: Singleton instance

    Example:
        >>> repo = get_acl_repository_v2()
        >>> auth = repo.authenticate_user('TMP3RC')
    """
    global _acl_repository_v2
    if _acl_repository_v2 is None:
        _acl_repository_v2 = ACLRepositoryV2()
        logger.info("ACL Repository V2 initialized")
    return _acl_repository_v2


def reset_acl_repository_v2() -> None:
    """
    Reset singleton instance (useful for testing).

    Example:
        >>> reset_acl_repository_v2()
        >>> repo = get_acl_repository_v2()  # Creates new instance
    """
    global _acl_repository_v2
    _acl_repository_v2 = None
    logger.info("ACL Repository V2 reset")
