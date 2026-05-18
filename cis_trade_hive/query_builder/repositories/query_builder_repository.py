"""
Query Builder Repository

Single responsibility: execute Impala queries and fetch table schema.
All constants (table list, cache TTL, limits) are class attributes.
"""

import hashlib
import json
import logging
import threading
from typing import Dict, Any, List, Tuple, Optional

from django.core.cache import cache

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class QueryBuilderRepository:
    """
    Data access for query builder.

    Responsibilities:
    - Execute a pre-built SQL string with params
    - Fetch and cache column schema for whitelisted tables
    """

    DATABASE = 'gmp_cis'
    MAX_CONCURRENT = 5          # max simultaneous query builder connections
    QUERY_TIMEOUT = 30          # seconds
    SCHEMA_CACHE_TTL = 3600     # 1 hour

    # Cache TTL per table — higher churn tables get shorter TTL
    RESULT_CACHE_TTL: Dict[str, int] = {
        'cis_trade':                 120,
        'cis_trade_position':        120,
        'cis_equity_price':          300,
        'gmp_cis_sta_dly_fx_rates':  300,
        'cis_portfolio':             900,
        'cis_security':              900,
        'cis_counterparty_kudu':     900,
        'default':                   300,
    }

    _semaphore = threading.Semaphore(MAX_CONCURRENT)

    def __init__(self, connection_manager=None):
        self._conn = connection_manager or impala_manager

    def execute(
        self,
        sql: str,
        params: List[Any],
        primary_table: str,
        use_cache: bool = True,
    ) -> Tuple[List[Dict], bool]:
        """
        Execute query. Returns (results, from_cache).
        Raises RuntimeError if connection pool is saturated.
        """
        cache_key = None
        if use_cache:
            cache_key = 'qb:result:' + hashlib.md5(
                (sql + json.dumps(params, default=str)).encode()
            ).hexdigest()
            cached = cache.get(cache_key)
            if cached is not None:
                logger.info("Query builder cache hit: %s", cache_key)
                return cached, True

        acquired = self._semaphore.acquire(timeout=10)
        if not acquired:
            raise RuntimeError(
                "Query Builder is busy — too many concurrent queries. Please try again shortly."
            )
        try:
            logger.info("Executing query builder SQL (table=%s)", primary_table)
            results = self._conn.execute_query(sql, database=self.DATABASE) or []

            if use_cache and cache_key:
                ttl = self.RESULT_CACHE_TTL.get(primary_table, self.RESULT_CACHE_TTL['default'])
                cache.set(cache_key, results, ttl)

            return results, False
        except Exception:
            raise
        finally:
            self._semaphore.release()

    def get_table_schema(self, table: str) -> List[Dict]:
        """
        Return [{name, type}] for each column in the table.
        Cached for SCHEMA_CACHE_TTL seconds.
        """
        cache_key = f'qb:schema:{table}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            rows = self._conn.execute_query(
                f"DESCRIBE {self.DATABASE}.{table}",
                database=self.DATABASE
            ) or []
            schema = []
            for row in rows:
                name = row.get('name') or row.get('col_name') or list(row.values())[0]
                dtype = row.get('type') or row.get('data_type') or list(row.values())[1]
                schema.append({'name': str(name).strip(), 'type': str(dtype).strip().upper()})
            cache.set(cache_key, schema, self.SCHEMA_CACHE_TTL)
            return schema
        except Exception as e:
            logger.error("Schema fetch failed for %s: %s", table, e)
            return []

    def get_all_schemas(self, tables: List[str]) -> Dict[str, List[Dict]]:
        return {t: self.get_table_schema(t) for t in tables}


query_builder_repository = QueryBuilderRepository()
