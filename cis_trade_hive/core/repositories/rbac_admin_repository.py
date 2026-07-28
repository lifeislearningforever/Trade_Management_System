"""
RBAC Admin Repository

CRUD operations for RBAC v2 tables:
  - cis_user_info
  - cis_user_group_info
  - cis_permission_info
  - cis_user_group_mapping_info
  - cis_group_permission_map

Design principles (low Kudu load):
  - All reads use ACLRepositoryV2 cache where possible
  - Writes are explicit (no background queries)
  - Batch operations for group assignment (one delete + one upsert per save)
  - Cache invalidation on write for affected user only
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from core.repositories.impala_connection import impala_manager
from core.repositories.acl_repository_v2 import ACLRepositoryV2
from core.audit.audit_kudu_repository import AuditLogKuduRepository

logger = logging.getLogger(__name__)

_audit = AuditLogKuduRepository

DB = 'gmp_cis'


class RBACAdminRepository:

    def __init__(self):
        self._acl = ACLRepositoryV2(database=DB)

    @staticmethod
    def _escape(v) -> str:
        # Impala uses C-style \' escaping, not doubled quotes.
        if v is None:
            return ''
        return str(v).replace('\\', '\\\\').replace("'", "\\'")

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def _id() -> str:
        """Fallback numeric ID (epoch ms). Use _next_id() for all new writes."""
        return str(int(datetime.now().timestamp() * 1000))

    @staticmethod
    def _next_id(sequence_name: str) -> str:
        """
        Allocate the next numeric ID from cis_sequence for the given RBAC sequence.

        Sequences registered by DDL 67:
          rbac_user_id, rbac_group_id, rbac_permission_id,
          rbac_user_group_map_id, rbac_group_perm_map_id

        Atomically increments current_value by 1 via UPSERT and returns the
        allocated value as a string.  Falls back to epoch-ms if the sequence
        row is missing (e.g. before DDL 67 has been run).
        """
        try:
            row = impala_manager.execute_query(
                f"SELECT current_value FROM {DB}.cis_sequence "
                f"WHERE sequence_name = '{sequence_name}'",
                database=DB
            )
            if not row:
                return str(int(datetime.now().timestamp() * 1000))
            next_val = int(row[0]['current_value']) + 1
            impala_manager.execute_write(
                f"UPSERT INTO {DB}.cis_sequence (sequence_name, current_value, increment_by) "
                f"VALUES ('{sequence_name}', {next_val}, 1)",
                database=DB
            )
            return str(next_val)
        except Exception:
            # Fallback — never break a write because of sequence failure
            return str(int(datetime.now().timestamp() * 1000))

    # =========================================================================
    # USERS
    # =========================================================================

    def get_all_users(self, include_inactive: bool = False) -> List[Dict]:
        try:
            where = "" if include_inactive else "WHERE is_deleted = false"
            query = f"""
                SELECT user_id, login, email, name, default_entity,
                       is_active, is_deleted, created_on, created_by,
                       updated_on, updated_by
                FROM {DB}.cis_user_info
                {where}
                ORDER BY name
            """
            return impala_manager.execute_query(query, database=DB) or []
        except Exception as e:
            logger.error(f"get_all_users error: {e}")
            return []

    def get_user(self, user_id: str) -> Optional[Dict]:
        try:
            query = f"""
                SELECT * FROM {DB}.cis_user_info
                WHERE user_id = '{self._escape(user_id)}'
                LIMIT 1
            """
            results = impala_manager.execute_query(query, database=DB)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"get_user error: {e}")
            return None

    def create_user(self, data: Dict, created_by: str) -> tuple[bool, str]:
        try:
            user_id = self._next_id('rbac_user_id')
            now = self._now()
            sql = f"""
                UPSERT INTO {DB}.cis_user_info
                (user_id, login, email, name, default_entity,
                 is_active, is_deleted, created_on, created_by, updated_on, updated_by)
                VALUES (
                    '{user_id}',
                    '{self._escape(data.get("login","")).upper()}',
                    '{self._escape(data.get("email",""))}',
                    '{self._escape(data.get("name",""))}',
                    '{self._escape(data.get("default_entity","UOBS"))}',
                    true, false,
                    '{now}', '{self._escape(created_by)}',
                    '{now}', '{self._escape(created_by)}'
                )
            """
            ok = impala_manager.execute_write(sql, database=DB)
            if ok:
                _audit.log_action(
                    user_id=created_by, username=created_by,
                    action_type='CREATE', entity_type='RBAC_USER',
                    entity_id=user_id,
                    entity_name=data.get('login', '').upper(),
                    action_description=f"Created user {data.get('login','').upper()}",
                    new_value=json.dumps({k: data.get(k) for k in ('login','email','name','default_entity')}),
                    action_category='ADMIN',
                )
            return (ok, user_id) if ok else (False, "DB write failed")
        except Exception as e:
            logger.error(f"create_user error: {e}")
            return False, str(e)

    def update_user(self, user_id: str, data: Dict, updated_by: str) -> bool:
        try:
            user = self.get_user(user_id)
            if not user:
                return False
            now = self._now()
            sql = f"""
                UPSERT INTO {DB}.cis_user_info
                (user_id, login, email, name, default_entity,
                 is_active, is_deleted, created_on, created_by, updated_on, updated_by)
                VALUES (
                    '{self._escape(user_id)}',
                    '{self._escape(data.get("login", user.get("login",""))).upper()}',
                    '{self._escape(data.get("email", user.get("email","")))}',
                    '{self._escape(data.get("name", user.get("name","")))}',
                    '{self._escape(data.get("default_entity", user.get("default_entity","UOBS")))}',
                    {str(data.get("is_active", user.get("is_active", True))).lower()},
                    false,
                    '{user.get("created_on", now)}',
                    '{self._escape(user.get("created_by", updated_by))}',
                    '{now}', '{self._escape(updated_by)}'
                )
            """
            ok = impala_manager.execute_write(sql, database=DB)
            if ok:
                login = data.get("login", user.get("login", ""))
                self._acl.clear_cache(login)
                _audit.log_action(
                    user_id=updated_by, username=updated_by,
                    action_type='UPDATE', entity_type='RBAC_USER',
                    entity_id=user_id,
                    entity_name=login.upper(),
                    action_description=f"Updated user {login.upper()}",
                    old_value=json.dumps({k: user.get(k) for k in ('login','email','name','is_active')}),
                    new_value=json.dumps({k: data.get(k, user.get(k)) for k in ('login','email','name','is_active')}),
                    action_category='ADMIN',
                )
            return ok
        except Exception as e:
            logger.error(f"update_user error: {e}")
            return False

    def deactivate_user(self, user_id: str, updated_by: str) -> bool:
        try:
            user = self.get_user(user_id)
            if not user:
                return False
            ok = self.update_user(user_id, {'is_active': False}, updated_by)
            if ok:
                _audit.log_action(
                    user_id=updated_by, username=updated_by,
                    action_type='DEACTIVATE', entity_type='RBAC_USER',
                    entity_id=user_id,
                    entity_name=user.get('login', '').upper(),
                    action_description=f"Deactivated user {user.get('login','').upper()}",
                    action_category='ADMIN',
                )
            return ok
        except Exception as e:
            logger.error(f"deactivate_user error: {e}")
            return False

    # =========================================================================
    # GROUPS
    # =========================================================================

    def get_all_groups(self, include_inactive: bool = False) -> List[Dict]:
        try:
            where = "WHERE is_deleted = false" if not include_inactive else ""
            query = f"""
                SELECT user_group_id, group_name, description, entity,
                       is_active, is_deleted, created_on, created_by, updated_on, updated_by
                FROM {DB}.cis_user_group_info
                {where}
                ORDER BY group_name
            """
            return impala_manager.execute_query(query, database=DB) or []
        except Exception as e:
            logger.error(f"get_all_groups error: {e}")
            return []

    def get_group(self, group_id: str) -> Optional[Dict]:
        try:
            query = f"""
                SELECT * FROM {DB}.cis_user_group_info
                WHERE user_group_id = '{self._escape(group_id)}'
                LIMIT 1
            """
            results = impala_manager.execute_query(query, database=DB)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"get_group error: {e}")
            return None

    def create_group(self, data: Dict, created_by: str) -> tuple[bool, str]:
        try:
            group_id = self._next_id('rbac_group_id')
            now = self._now()
            sql = f"""
                UPSERT INTO {DB}.cis_user_group_info
                (user_group_id, group_name, description, entity,
                 is_active, is_deleted, created_on, created_by, updated_on, updated_by)
                VALUES (
                    '{group_id}',
                    '{self._escape(data.get("group_name",""))}',
                    '{self._escape(data.get("description",""))}',
                    '{self._escape(data.get("entity","UOBS"))}',
                    true, false,
                    '{now}', '{self._escape(created_by)}',
                    '{now}', '{self._escape(created_by)}'
                )
            """
            ok = impala_manager.execute_write(sql, database=DB)
            if ok:
                _audit.log_action(
                    user_id=created_by, username=created_by,
                    action_type='CREATE', entity_type='RBAC_GROUP',
                    entity_id=group_id,
                    entity_name=data.get('group_name', ''),
                    action_description=f"Created group {data.get('group_name','')}",
                    new_value=json.dumps({k: data.get(k) for k in ('group_name','description','entity')}),
                    action_category='ADMIN',
                )
            return (ok, group_id) if ok else (False, "DB write failed")
        except Exception as e:
            logger.error(f"create_group error: {e}")
            return False, str(e)

    def update_group(self, group_id: str, data: Dict, updated_by: str) -> bool:
        try:
            group = self.get_group(group_id)
            if not group:
                return False
            now = self._now()
            sql = f"""
                UPSERT INTO {DB}.cis_user_group_info
                (user_group_id, group_name, description, entity,
                 is_active, is_deleted, created_on, created_by, updated_on, updated_by)
                VALUES (
                    '{self._escape(group_id)}',
                    '{self._escape(data.get("group_name", group.get("group_name","")))}',
                    '{self._escape(data.get("description", group.get("description","")))}',
                    '{self._escape(data.get("entity", group.get("entity","UOBS")))}',
                    {str(data.get("is_active", group.get("is_active", True))).lower()},
                    false,
                    '{group.get("created_on", now)}',
                    '{self._escape(group.get("created_by", updated_by))}',
                    '{now}', '{self._escape(updated_by)}'
                )
            """
            ok = impala_manager.execute_write(sql, database=DB)
            if ok:
                _audit.log_action(
                    user_id=updated_by, username=updated_by,
                    action_type='UPDATE', entity_type='RBAC_GROUP',
                    entity_id=group_id,
                    entity_name=data.get('group_name', group.get('group_name', '')),
                    action_description=f"Updated group {data.get('group_name', group.get('group_name',''))}",
                    old_value=json.dumps({k: group.get(k) for k in ('group_name','description','is_active')}),
                    new_value=json.dumps({k: data.get(k, group.get(k)) for k in ('group_name','description','is_active')}),
                    action_category='ADMIN',
                )
            return ok
        except Exception as e:
            logger.error(f"update_group error: {e}")
            return False

    # =========================================================================
    # PERMISSIONS
    # =========================================================================

    def get_all_permissions(self) -> List[Dict]:
        try:
            query = f"""
                SELECT permission_id, permission_name, entity, description,
                       is_active, created_on, created_by, updated_on, updated_by
                FROM {DB}.cis_permission_info
                WHERE is_deleted = false
                ORDER BY permission_name
            """
            return impala_manager.execute_query(query, database=DB) or []
        except Exception as e:
            logger.error(f"get_all_permissions error: {e}")
            return []

    def create_permission(self, data: Dict, created_by: str) -> tuple[bool, str]:
        try:
            perm_id = self._next_id('rbac_permission_id')
            now = self._now()
            sql = f"""
                UPSERT INTO {DB}.cis_permission_info
                (permission_id, permission_name, entity, description,
                 is_active, is_deleted, created_on, created_by, updated_on, updated_by)
                VALUES (
                    '{perm_id}',
                    '{self._escape(data.get("permission_name",""))}',
                    '{self._escape(data.get("entity","UOBS"))}',
                    '{self._escape(data.get("description",""))}',
                    true, false,
                    '{now}', '{self._escape(created_by)}',
                    '{now}', '{self._escape(created_by)}'
                )
            """
            ok = impala_manager.execute_write(sql, database=DB)
            if ok:
                _audit.log_action(
                    user_id=created_by, username=created_by,
                    action_type='CREATE', entity_type='RBAC_PERMISSION',
                    entity_id=perm_id,
                    entity_name=data.get('permission_name', ''),
                    action_description=f"Created permission {data.get('permission_name','')}",
                    new_value=json.dumps({k: data.get(k) for k in ('permission_name','entity','description')}),
                    action_category='ADMIN',
                )
            return (ok, perm_id) if ok else (False, "DB write failed")
        except Exception as e:
            logger.error(f"create_permission error: {e}")
            return False, str(e)

    # =========================================================================
    # USER → GROUP MAPPINGS  (batch save — replaces all groups for a user)
    # =========================================================================

    def get_user_group_mappings(self, user_id: str) -> List[Dict]:
        try:
            query = f"""
                SELECT user_group_mapping_id, user_id, group_name, entity,
                       is_active, created_on, created_by, updated_on, updated_by
                FROM {DB}.cis_user_group_mapping_info
                WHERE user_id = '{self._escape(user_id)}'
                  AND is_deleted = false
                ORDER BY group_name
            """
            return impala_manager.execute_query(query, database=DB) or []
        except Exception as e:
            logger.error(f"get_user_group_mappings error: {e}")
            return []

    def save_user_groups(
        self,
        user_id: str,
        user_login: str,
        group_names: List[str],
        entity: str,
        updated_by: str
    ) -> bool:
        """
        Replace all group mappings for a user in one operation.
        Step 1: soft-delete existing mappings for this user+entity.
        Step 2: upsert new mappings.
        Cache cleared for affected user.
        """
        try:
            now = self._now()

            # Step 1: soft-delete all current mappings via UPSERT (Kudu has no UPDATE)
            existing = self.get_user_group_mappings(user_id)
            for m in existing:
                if m.get('entity', '') != entity:
                    continue
                del_sql = f"""
                    UPSERT INTO {DB}.cis_user_group_mapping_info
                    (user_group_mapping_id, user_id, entity, group_name,
                     is_active, is_deleted, created_on, created_by, updated_on, updated_by)
                    VALUES (
                        '{self._escape(m["user_group_mapping_id"])}',
                        '{self._escape(user_id)}',
                        '{self._escape(m.get("entity", entity))}',
                        '{self._escape(m["group_name"])}',
                        false, true,
                        '{m.get("created_on", now)}', '{self._escape(m.get("created_by", updated_by))}',
                        '{now}', '{self._escape(updated_by)}'
                    )
                """
                impala_manager.execute_write(del_sql, database=DB)

            # Step 2: upsert new mappings
            for group_name in group_names:
                mapping_id = self._next_id('rbac_user_group_map_id')
                ins_sql = f"""
                    UPSERT INTO {DB}.cis_user_group_mapping_info
                    (user_group_mapping_id, user_id, entity, group_name,
                     is_active, is_deleted, created_on, created_by, updated_on, updated_by)
                    VALUES (
                        '{mapping_id}',
                        '{self._escape(user_id)}',
                        '{self._escape(entity)}',
                        '{self._escape(group_name)}',
                        true, false,
                        '{now}', '{self._escape(updated_by)}',
                        '{now}', '{self._escape(updated_by)}'
                    )
                """
                impala_manager.execute_write(ins_sql, database=DB)

            # Invalidate cache for this user
            self._acl.clear_cache(user_login)
            _audit.log_action(
                user_id=updated_by, username=updated_by,
                action_type='UPDATE', entity_type='RBAC_USER_GROUP',
                entity_id=user_id,
                entity_name=user_login,
                action_description=f"Updated group memberships for user {user_login}: {', '.join(group_names) or '(none)'}",
                new_value=json.dumps({'user_login': user_login, 'groups': group_names, 'entity': entity}),
                action_category='ADMIN',
            )
            return True

        except Exception as e:
            logger.error(f"save_user_groups error: {e}")
            return False

    # =========================================================================
    # GROUP → PERMISSION MAPPINGS
    # =========================================================================

    def get_group_permission_mappings(self, group_name: str, active_only: bool = False) -> List[Dict]:
        try:
            query = f"""
                SELECT gpm.group_permission_id, gpm.group_name,
                       gpm.permission_name, gpm.entity, gpm.mode, gpm.description,
                       gpm.is_active, gpm.created_on, gpm.created_by
                FROM {DB}.cis_group_permission_map gpm
                WHERE gpm.group_name = '{self._escape(group_name)}'
                  AND gpm.is_deleted = false
            """
            if active_only:
                query += "  AND gpm.is_active = true\n"
            query += "ORDER BY gpm.permission_name"
            return impala_manager.execute_query(query, database=DB) or []
        except Exception as e:
            logger.error(f"get_group_permission_mappings error: {e}")
            return []

    def save_group_permissions(
        self,
        group_name: str,
        permissions: List[Dict],   # [{'permission_name': ..., 'mode': ...}]
        entity: str,
        updated_by: str
    ) -> bool:
        """
        Replace all permission mappings for a group in one operation.
        Clears ACL cache for ALL users (group change affects everyone in it).

        Existing active rows are soft-deleted (is_active=false, is_deleted=true).
        If a permission is re-assigned, the same group_permission_id is reused so
        inactive rows are not resurrected and the table does not accumulate duplicates.
        """
        try:
            now = self._now()

            # Fetch only active rows to soft-delete — inactive rows are already excluded
            # from permission checks and must not be resurrected by a new UPSERT on the
            # same group_permission_id.
            existing_perms = self.get_group_permission_mappings(group_name, active_only=True)
            existing_by_perm = {
                ep['permission_name']: ep
                for ep in existing_perms
                if ep.get('entity', '') == entity
            }

            # Soft-delete all currently active mappings for this group+entity
            for ep in existing_by_perm.values():
                del_perm_sql = f"""
                    UPSERT INTO {DB}.cis_group_permission_map
                    (group_permission_id, group_name, permission_name, entity,
                     mode, description, is_active, is_deleted,
                     created_on, created_by, updated_on, updated_by)
                    VALUES (
                        '{self._escape(ep["group_permission_id"])}',
                        '{self._escape(group_name)}',
                        '{self._escape(ep.get("permission_name",""))}',
                        '{self._escape(ep.get("entity", entity))}',
                        '{self._escape(ep.get("mode","READ"))}',
                        '{self._escape(ep.get("description",""))}',
                        false, true,
                        '{ep.get("created_on", now)}', '{self._escape(ep.get("created_by", updated_by))}',
                        '{now}', '{self._escape(updated_by)}'
                    )
                """
                impala_manager.execute_write(del_perm_sql, database=DB)

            # Upsert new permissions — reuse existing group_permission_id when the same
            # permission_name is being re-assigned so Kudu updates the row in-place
            # instead of leaving an orphaned inactive row alongside a new active one.
            for perm in permissions:
                perm_name = perm.get("permission_name", "")
                existing = existing_by_perm.get(perm_name)
                perm_id = self._escape(existing["group_permission_id"]) if existing else self._next_id('rbac_group_perm_map_id')
                created_on = existing.get("created_on", now) if existing else now
                created_by = self._escape(existing.get("created_by", updated_by)) if existing else self._escape(updated_by)
                ins_sql = f"""
                    UPSERT INTO {DB}.cis_group_permission_map
                    (group_permission_id, group_name, permission_name, entity,
                     mode, description, is_active, is_deleted,
                     created_on, created_by, updated_on, updated_by)
                    VALUES (
                        '{perm_id}',
                        '{self._escape(group_name)}',
                        '{self._escape(perm_name)}',
                        '{self._escape(entity)}',
                        '{self._escape(perm.get("mode","READ"))}',
                        '{self._escape(perm.get("description",""))}',
                        true, false,
                        '{created_on}', '{created_by}',
                        '{now}', '{self._escape(updated_by)}'
                    )
                """
                impala_manager.execute_write(ins_sql, database=DB)

            # Clear all cached ACL data — group change affects everyone in it
            self._acl.clear_cache()
            perm_names = [p.get('permission_name', '') for p in permissions]
            _audit.log_action(
                user_id=updated_by, username=updated_by,
                action_type='UPDATE', entity_type='RBAC_GROUP_PERMISSION',
                entity_id=group_name,
                entity_name=group_name,
                action_description=f"Updated permissions for group {group_name}: {', '.join(perm_names) or '(none)'}",
                new_value=json.dumps({'group_name': group_name, 'permissions': permissions, 'entity': entity}),
                action_category='ADMIN',
            )
            return True

        except Exception as e:
            logger.error(f"save_group_permissions error: {e}")
            return False

    # =========================================================================
    # AUDIT LOG helpers
    # =========================================================================

    def get_rbac_audit(self, limit: int = 100) -> List[Dict]:
        """Fetch recent RBAC-related audit entries from cis_audit_log."""
        try:
            query = f"""
                SELECT action_type, entity_type, entity_id, entity_name,
                       action_description, old_value, new_value,
                       username, ip_address, audit_timestamp
                FROM {DB}.cis_audit_log
                WHERE entity_type IN (
                    'RBAC_USER','RBAC_GROUP','RBAC_PERMISSION',
                    'RBAC_USER_GROUP','RBAC_GROUP_PERMISSION'
                )
                ORDER BY audit_timestamp DESC
                LIMIT {limit}
            """
            return impala_manager.execute_query(query, database=DB) or []
        except Exception as e:
            logger.error(f"get_rbac_audit error: {e}")
            return []


rbac_admin_repository = RBACAdminRepository()
