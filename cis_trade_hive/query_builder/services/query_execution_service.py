"""
Query Execution Service

Single responsibility: orchestrate building + executing a query.
Receives SqlBuilderService and QueryBuilderRepository via constructor
(dependency inversion — depends on abstractions, not concrete imports).
"""

import logging
from typing import Dict, Any, List, Tuple

from query_builder.repositories.query_builder_repository import QueryBuilderRepository, query_builder_repository
from query_builder.services.sql_builder_service import SqlBuilderService, sql_builder_service

logger = logging.getLogger(__name__)


class QueryExecutionService:
    """
    Orchestrates: config → SQL → execute → results.
    Does not know about HTTP, audit logging, or exports.
    """

    def __init__(
        self,
        builder: SqlBuilderService = None,
        repository: QueryBuilderRepository = None,
    ):
        self._builder = builder or sql_builder_service
        self._repo = repository or query_builder_repository

    def run(
        self,
        config: Dict[str, Any],
        use_cache: bool = True,
    ) -> Tuple[List[Dict], bool, str]:
        """
        Build and execute a query.

        Returns:
            (results, from_cache, sql_string)
        Raises:
            ValueError  — invalid config
            RuntimeError — pool saturated
        """
        sql, params = self._builder.build(config)
        results, from_cache = self._repo.execute(
            sql, params,
            primary_table=config['primary_table'],
            use_cache=use_cache,
        )
        return results, from_cache, sql

    def get_table_list(self) -> List[Dict]:
        return self._builder.get_table_list()

    def get_join_options(self, primary_table: str) -> List[Dict]:
        return self._builder.get_join_options(primary_table)

    def get_all_schemas(self, tables: List[str] = None) -> Dict[str, List[Dict]]:
        target = tables or list(self._builder.TABLES.keys())
        return self._repo.get_all_schemas(target)

    def get_table_schema(self, table: str) -> List[Dict]:
        return self._repo.get_table_schema(table)


query_execution_service = QueryExecutionService()
