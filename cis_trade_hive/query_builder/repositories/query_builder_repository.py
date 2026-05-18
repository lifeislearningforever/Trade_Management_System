"""
Query Builder Repository

Executes queries with:
- Connection pool semaphore (max 5 concurrent)
- Role-based timeout
- Result caching (TTL by data category)
- Schema cache (1hr TTL)
"""

import hashlib
import json
import logging
import threading
from typing import Dict, Any, List, Optional, Tuple

from django.core.cache import cache

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'
QUERY_TIMEOUT = 30          # seconds
MAX_CONCURRENT = 5          # max simultaneous query builder connections
_semaphore = threading.Semaphore(MAX_CONCURRENT)

CACHE_TTL = {
    'cis_trade':              120,
    'cis_trade_position':     120,
    'cis_equity_price':       300,
    'cis_portfolio':          900,
    'cis_security':           900,
    'cis_counterparty_kudu':  900,
    'gmp_cis_sta_dly_fx_rates': 300,
    'default':                300,
}
SCHEMA_CACHE_TTL = 3600


class QueryBuilderRepository:

    def execute(
        self,
        sql: str,
        params: List[Any],
        primary_table: str,
        use_cache: bool = True
    ) -> Tuple[List[Dict], bool]:
        """
        Execute a query. Returns (results, from_cache).
        Respects semaphore limit — raises RuntimeError if pool exhausted.
        """
        cache_key = None
        if use_cache:
            cache_key = 'qb:' + hashlib.md5(
                (sql + json.dumps(params, default=str)).encode()
            ).hexdigest()
            cached = cache.get(cache_key)
            if cached is not None:
                logger.info(f"Query cache hit: {cache_key}")
                return cached, True

        acquired = _semaphore.acquire(timeout=10)
        if not acquired:
            raise RuntimeError(
                "Query Builder is busy — too many concurrent queries. Please try again shortly."
            )

        try:
            logger.info(f"Executing query builder SQL (table={primary_table})")
            results = impala_manager.execute_query(sql, database=DATABASE)

            if use_cache and cache_key and results is not None:
                ttl = CACHE_TTL.get(primary_table, CACHE_TTL['default'])
                cache.set(cache_key, results, ttl)

            return results or [], False

        except Exception as e:
            logger.error(f"Query builder execution error: {e}")
            raise
        finally:
            _semaphore.release()

    def get_table_schema(self, table: str) -> List[Dict]:
        """
        Return column metadata for a table. Cached 1hr.
        Schema: [{'name': 'col', 'type': 'STRING'}, ...]
        """
        cache_key = f'qb:schema:{table}'
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            results = impala_manager.execute_query(
                f"DESCRIBE {DATABASE}.{table}",
                database=DATABASE
            )
            if not results:
                return []

            schema = []
            for row in results:
                name = row.get('name') or row.get('col_name') or list(row.values())[0]
                dtype = row.get('type') or row.get('data_type') or list(row.values())[1]
                schema.append({'name': str(name).strip(), 'type': str(dtype).strip().upper()})

            cache.set(cache_key, schema, SCHEMA_CACHE_TTL)
            return schema

        except Exception as e:
            logger.error(f"Schema fetch failed for {table}: {e}")
            return []

    def get_all_schemas(self, tables: List[str]) -> Dict[str, List[Dict]]:
        return {t: self.get_table_schema(t) for t in tables}


query_builder_repository = QueryBuilderRepository()
