"""
Report Template Repository

Single responsibility: CRUD operations for cis_report_template (Kudu).
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class ReportTemplateRepository:
    """CRUD for the cis_report_template Kudu table."""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_report_template'

    def __init__(self, connection_manager=None):
        self._conn = connection_manager or impala_manager

    @staticmethod
    def _esc(val: str) -> str:
        return str(val or '').replace('\\', '\\\\').replace("'", "\\'")

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def get_all(self, user_groups: List[str] = None) -> List[Dict]:
        try:
            rows = self._conn.execute_query(
                f"SELECT * FROM {self.DATABASE}.{self.TABLE_NAME}"
                f" WHERE is_active = true ORDER BY template_name",
                database=self.DATABASE
            ) or []
            if not user_groups:
                return rows
            filtered = []
            for r in rows:
                allowed = json.loads(r.get('allowed_groups') or '[]')
                if r.get('is_public') or not allowed or any(g in allowed for g in user_groups):
                    filtered.append(r)
            return filtered
        except Exception as e:
            logger.error("Error fetching report templates: %s", e)
            return []

    def get_by_id(self, template_id: int) -> Optional[Dict]:
        try:
            rows = self._conn.execute_query(
                f"SELECT * FROM {self.DATABASE}.{self.TABLE_NAME}"
                f" WHERE template_id = {template_id} AND is_active = true LIMIT 1",
                database=self.DATABASE
            ) or []
            return rows[0] if rows else None
        except Exception as e:
            logger.error("Error fetching template %s: %s", template_id, e)
            return None

    def create(self, data: Dict, created_by: str) -> bool:
        try:
            template_id = int(time.time() * 1000)
            now = self._now()
            sql = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            (template_id, template_name, description, category,
             query_config, allowed_groups, is_public,
             created_by, created_at, updated_by, updated_at, is_active)
            VALUES (
                {template_id},
                '{self._esc(data.get('template_name', ''))}',
                '{self._esc(data.get('description', ''))}',
                '{self._esc(data.get('category', ''))}',
                '{self._esc(json.dumps(data.get('query_config', {})))}',
                '{self._esc(json.dumps(data.get('allowed_groups', [])))}',
                {str(bool(data.get('is_public', False))).lower()},
                '{self._esc(created_by)}', '{now}',
                '{self._esc(created_by)}', '{now}', true
            )
            """
            return self._conn.execute_write(sql, database=self.DATABASE)
        except Exception as e:
            logger.error("Error creating report template: %s", e)
            return False

    def update(self, template_id: int, data: Dict, updated_by: str) -> bool:
        existing = self.get_by_id(template_id)
        if not existing:
            return False
        try:
            now = self._now()
            query_config = json.dumps(
                data.get('query_config', json.loads(existing.get('query_config', '{}')))
            )
            allowed_groups = json.dumps(
                data.get('allowed_groups', json.loads(existing.get('allowed_groups', '[]')))
            )
            sql = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            (template_id, template_name, description, category,
             query_config, allowed_groups, is_public,
             created_by, created_at, updated_by, updated_at, is_active)
            VALUES (
                {template_id},
                '{self._esc(data.get('template_name', existing.get('template_name', '')))}',
                '{self._esc(data.get('description', existing.get('description', '')))}',
                '{self._esc(data.get('category', existing.get('category', '')))}',
                '{self._esc(query_config)}',
                '{self._esc(allowed_groups)}',
                {str(bool(data.get('is_public', existing.get('is_public', False)))).lower()},
                '{self._esc(existing.get('created_by', ''))}',
                '{existing.get('created_at', now)}',
                '{self._esc(updated_by)}', '{now}', true
            )
            """
            return self._conn.execute_write(sql, database=self.DATABASE)
        except Exception as e:
            logger.error("Error updating template %s: %s", template_id, e)
            return False

    def delete(self, template_id: int, deleted_by: str) -> bool:
        """Soft delete — sets is_active = false."""
        existing = self.get_by_id(template_id)
        if not existing:
            return False
        try:
            now = self._now()
            sql = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            (template_id, template_name, description, category,
             query_config, allowed_groups, is_public,
             created_by, created_at, updated_by, updated_at, is_active)
            VALUES (
                {template_id},
                '{self._esc(existing.get('template_name', ''))}',
                '{self._esc(existing.get('description', ''))}',
                '{self._esc(existing.get('category', ''))}',
                '{self._esc(existing.get('query_config', '{}'))}',
                '{self._esc(existing.get('allowed_groups', '[]'))}',
                {str(bool(existing.get('is_public', False))).lower()},
                '{self._esc(existing.get('created_by', ''))}',
                '{existing.get('created_at', now)}',
                '{self._esc(deleted_by)}', '{now}', false
            )
            """
            return self._conn.execute_write(sql, database=self.DATABASE)
        except Exception as e:
            logger.error("Error deleting template %s: %s", template_id, e)
            return False


report_template_repository = ReportTemplateRepository()
