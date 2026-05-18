"""
Report Template Repository — CRUD for cis_report_template (Kudu).
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)
DATABASE = 'gmp_cis'
TABLE = 'cis_report_template'


class ReportTemplateRepository:

    @staticmethod
    def _escape(val: str) -> str:
        return str(val).replace("'", "''")

    def get_all(self, user_groups: List[str] = None) -> List[Dict]:
        try:
            results = impala_manager.execute_query(
                f"SELECT * FROM {DATABASE}.{TABLE} WHERE is_active = true ORDER BY template_name",
                database=DATABASE
            )
            if not results:
                return []
            if user_groups:
                filtered = []
                for r in results:
                    allowed = json.loads(r.get('allowed_groups') or '[]')
                    if r.get('is_public') or not allowed or any(g in allowed for g in user_groups):
                        filtered.append(r)
                return filtered
            return results
        except Exception as e:
            logger.error(f"Error fetching report templates: {e}")
            return []

    def get_by_id(self, template_id: int) -> Optional[Dict]:
        try:
            results = impala_manager.execute_query(
                f"SELECT * FROM {DATABASE}.{TABLE} WHERE template_id = {template_id} AND is_active = true LIMIT 1",
                database=DATABASE
            )
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error fetching template {template_id}: {e}")
            return None

    def create(self, data: Dict, created_by: str) -> bool:
        try:
            template_id = int(time.time() * 1000)
            now = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            query_config = json.dumps(data.get('query_config', {}))
            allowed_groups = json.dumps(data.get('allowed_groups', []))

            sql = f"""
            UPSERT INTO {DATABASE}.{TABLE}
            (template_id, template_name, description, category,
             query_config, allowed_groups, is_public,
             created_by, created_at, updated_by, updated_at, is_active)
            VALUES (
                {template_id},
                '{self._escape(data.get('template_name', ''))}',
                '{self._escape(data.get('description', ''))}',
                '{self._escape(data.get('category', ''))}',
                '{self._escape(query_config)}',
                '{self._escape(allowed_groups)}',
                {str(bool(data.get('is_public', False))).lower()},
                '{self._escape(created_by)}',
                '{now}', '{self._escape(created_by)}', '{now}', true
            )
            """
            return impala_manager.execute_write(sql, database=DATABASE)
        except Exception as e:
            logger.error(f"Error creating report template: {e}")
            return False

    def update(self, template_id: int, data: Dict, updated_by: str) -> bool:
        try:
            existing = self.get_by_id(template_id)
            if not existing:
                return False
            now = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            query_config = json.dumps(data.get('query_config', json.loads(existing.get('query_config', '{}'))))
            allowed_groups = json.dumps(data.get('allowed_groups', json.loads(existing.get('allowed_groups', '[]'))))

            sql = f"""
            UPSERT INTO {DATABASE}.{TABLE}
            (template_id, template_name, description, category,
             query_config, allowed_groups, is_public,
             created_by, created_at, updated_by, updated_at, is_active)
            VALUES (
                {template_id},
                '{self._escape(data.get('template_name', existing.get('template_name', '')))}',
                '{self._escape(data.get('description', existing.get('description', '')))}',
                '{self._escape(data.get('category', existing.get('category', '')))}',
                '{self._escape(query_config)}',
                '{self._escape(allowed_groups)}',
                {str(bool(data.get('is_public', existing.get('is_public', False)))).lower()},
                '{self._escape(existing.get('created_by', ''))}',
                '{existing.get('created_at', now)}',
                '{self._escape(updated_by)}', '{now}', true
            )
            """
            return impala_manager.execute_write(sql, database=DATABASE)
        except Exception as e:
            logger.error(f"Error updating template {template_id}: {e}")
            return False

    def delete(self, template_id: int, deleted_by: str) -> bool:
        """Soft delete."""
        try:
            existing = self.get_by_id(template_id)
            if not existing:
                return False
            now = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sql = f"""
            UPSERT INTO {DATABASE}.{TABLE}
            (template_id, template_name, description, category,
             query_config, allowed_groups, is_public,
             created_by, created_at, updated_by, updated_at, is_active)
            VALUES (
                {template_id},
                '{self._escape(existing.get('template_name', ''))}',
                '{self._escape(existing.get('description', ''))}',
                '{self._escape(existing.get('category', ''))}',
                '{self._escape(existing.get('query_config', '{}'))}',
                '{self._escape(existing.get('allowed_groups', '[]'))}',
                {str(bool(existing.get('is_public', False))).lower()},
                '{self._escape(existing.get('created_by', ''))}',
                '{existing.get('created_at', now)}',
                '{self._escape(deleted_by)}', '{now}', false
            )
            """
            return impala_manager.execute_write(sql, database=DATABASE)
        except Exception as e:
            logger.error(f"Error deleting template {template_id}: {e}")
            return False


report_template_repository = ReportTemplateRepository()
