"""
Report Template Service

Single responsibility: business logic around report template lifecycle.
Repository injected via constructor.
"""

import logging
from typing import Dict, Any, List, Optional

from query_builder.repositories.report_template_repository import (
    ReportTemplateRepository, report_template_repository
)

logger = logging.getLogger(__name__)


class ReportTemplateService:
    """Business logic for saved report templates."""

    def __init__(self, repository: ReportTemplateRepository = None):
        self._repo = repository or report_template_repository

    def get_accessible_templates(self, user_groups: List[str]) -> List[Dict]:
        return self._repo.get_all(user_groups)

    def get_by_id(self, template_id: int) -> Optional[Dict]:
        return self._repo.get_by_id(template_id)

    def save(self, data: Dict, created_by: str) -> bool:
        if not data.get('template_name', '').strip():
            raise ValueError("Template name is required")
        return self._repo.create(data, created_by)

    def update(self, template_id: int, data: Dict, updated_by: str) -> bool:
        if not self._repo.get_by_id(template_id):
            raise ValueError(f"Template {template_id} not found")
        return self._repo.update(template_id, data, updated_by)

    def delete(self, template_id: int, deleted_by: str) -> bool:
        if not self._repo.get_by_id(template_id):
            raise ValueError(f"Template {template_id} not found")
        return self._repo.delete(template_id, deleted_by)


report_template_service = ReportTemplateService()
