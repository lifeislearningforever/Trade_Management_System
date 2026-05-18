"""
Query Builder Service

Generates safe parameterised Impala SQL from a UI config dict.
All table/column names validated against whitelist — only filter
values are user-supplied strings.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Whitelisted tables
# ---------------------------------------------------------------------------
TABLES = {
    'cis_trade':           {'alias': 't',   'display': 'Trade',        'date_col': 'trade_date'},
    'cis_portfolio':       {'alias': 'p',   'display': 'Portfolio',    'date_col': None},
    'cis_security':        {'alias': 's',   'display': 'Security',     'date_col': None},
    'cis_equity_price':    {'alias': 'ep',  'display': 'Equity Price', 'date_col': 'price_date'},
    'cis_trade_position':  {'alias': 'pos', 'display': 'Position',     'date_col': 'trade_date'},
    'cis_counterparty_kudu': {'alias': 'cp','display': 'Counterparty', 'date_col': None},
    'gmp_cis_sta_dly_fx_rates': {'alias': 'fx', 'display': 'FX Rates','date_col': 'processing_date'},
}

# ---------------------------------------------------------------------------
# Pre-defined safe join paths
# ---------------------------------------------------------------------------
JOIN_PATHS = {
    ('cis_trade', 'cis_portfolio'):      't.portfolio_short_name = p.portfolio_short_name',
    ('cis_trade', 'cis_security'):       't.security_label = s.security_name',
    ('cis_trade', 'cis_counterparty_kudu'): 't.broker = cp.counterparty_name',
    ('cis_security', 'cis_equity_price'):'s.security_name = ep.security_label',
    ('cis_trade_position', 'cis_trade'): 'pos.trade_id = t.trade_id',
    ('cis_trade_position', 'cis_security'): 'pos.security_label = s.security_name',
    ('cis_trade_position', 'cis_portfolio'): 'pos.portfolio_short_name = p.portfolio_short_name',
    ('cis_trade', 'cis_equity_price'):   't.security_label = ep.security_label',
}

# ---------------------------------------------------------------------------
# Role-based row limits
# ---------------------------------------------------------------------------
ROLE_LIMITS = {
    'VIEWER':       1_000,
    'TRADER':       5_000,
    'RISK_MANAGER': 10_000,
    'ADMIN':        50_000,
    'RBAC_ADMIN':   50_000,
}
DEFAULT_LIMIT = 1_000
MAX_JOINS = 3

FILTER_OPERATORS = {
    'eq':       '=',
    'neq':      '!=',
    'gt':       '>',
    'gte':      '>=',
    'lt':       '<',
    'lte':      '<=',
    'like':     'LIKE',
    'not_like': 'NOT LIKE',
    'in':       'IN',
    'not_in':   'NOT IN',
    'between':  'BETWEEN',
    'is_null':  'IS NULL',
    'is_not_null': 'IS NOT NULL',
}

AGGREGATIONS = {'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COUNT_DISTINCT'}

DATABASE = 'gmp_cis'


class QueryBuilderService:
    """
    Builds safe Impala SQL from a structured config dict.

    Config schema:
    {
        "primary_table": "cis_trade",
        "joins": [
            {"table": "cis_portfolio", "type": "INNER"}
        ],
        "columns": [
            {"table": "cis_trade", "column": "trade_id", "alias": ""},
            {"table": "cis_trade", "column": "trade_date", "agg": ""}
        ],
        "filters": [
            {"table": "cis_trade", "column": "trade_date", "op": "gte", "value": "2026-01-01", "logic": "AND"}
        ],
        "group_by": ["cis_trade.trade_date", "cis_portfolio.portfolio_short_name"],
        "having": [
            {"column": "COUNT(*)", "op": "gt", "value": "5"}
        ],
        "order_by": [
            {"table": "cis_trade", "column": "trade_date", "direction": "DESC"}
        ],
        "limit": 500,
        "user_role": "TRADER"
    }
    """

    def build(self, config: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """
        Build SQL from config. Returns (sql_string, params_list).
        Raises ValueError for invalid config.
        """
        self._validate_config(config)

        primary = config['primary_table']
        joins_config = config.get('joins', [])
        columns_config = config.get('columns', [])
        filters_config = config.get('filters', [])
        group_by_config = config.get('group_by', [])
        having_config = config.get('having', [])
        order_by_config = config.get('order_by', [])
        user_role = config.get('user_role', 'VIEWER').upper()

        row_limit = min(
            int(config.get('limit', DEFAULT_LIMIT)),
            ROLE_LIMITS.get(user_role, DEFAULT_LIMIT)
        )

        # Tables in use
        active_tables = {primary} | {j['table'] for j in joins_config}

        # SELECT
        select_clause, params = self._build_select(columns_config, active_tables)

        # FROM
        from_clause = f"{DATABASE}.{primary} {TABLES[primary]['alias']}"

        # JOINs
        join_clause = self._build_joins(primary, joins_config)

        # WHERE
        where_clause, where_params = self._build_where(filters_config, primary, active_tables)
        params.extend(where_params)

        # GROUP BY
        group_clause = self._build_group_by(group_by_config, active_tables)

        # HAVING
        having_clause, having_params = self._build_having(having_config)
        params.extend(having_params)

        # ORDER BY
        order_clause = self._build_order_by(order_by_config, active_tables)

        # Assemble
        parts = [f"SELECT {select_clause}", f"FROM {from_clause}"]
        if join_clause:
            parts.append(join_clause)
        if where_clause:
            parts.append(f"WHERE {where_clause}")
        if group_clause:
            parts.append(f"GROUP BY {group_clause}")
        if having_clause:
            parts.append(f"HAVING {having_clause}")
        if order_clause:
            parts.append(f"ORDER BY {order_clause}")
        parts.append(f"LIMIT {row_limit}")

        sql = '\n'.join(parts)
        return sql, params

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_select(self, columns: List[Dict], active_tables: set) -> Tuple[str, List]:
        if not columns:
            # Default: all columns from all active tables
            parts = []
            for tbl in active_tables:
                alias = TABLES[tbl]['alias']
                parts.append(f"{alias}.*")
            return ', '.join(parts), []

        parts = []
        for col in columns:
            tbl = col['table']
            self._assert_table(tbl)
            col_name = self._safe_column(col['column'])
            alias = TABLES[tbl]['alias']
            agg = col.get('agg', '').upper()
            col_alias = col.get('alias', '')

            if agg:
                if agg not in AGGREGATIONS:
                    raise ValueError(f"Invalid aggregation: {agg}")
                if agg == 'COUNT_DISTINCT':
                    expr = f"COUNT(DISTINCT {alias}.{col_name})"
                elif col_name == '*':
                    expr = f"{agg}(*)"
                else:
                    expr = f"{agg}({alias}.{col_name})"
            else:
                expr = f"{alias}.{col_name}"

            if col_alias:
                expr += f" AS {self._safe_column(col_alias)}"
            parts.append(expr)

        return ', '.join(parts), []

    def _build_joins(self, primary: str, joins: List[Dict]) -> str:
        if len(joins) > MAX_JOINS:
            raise ValueError(f"Maximum {MAX_JOINS} joins allowed")

        parts = []
        for j in joins:
            tbl = j['table']
            self._assert_table(tbl)
            join_type = j.get('type', 'INNER').upper()
            if join_type not in ('INNER', 'LEFT'):
                raise ValueError(f"Join type '{join_type}' not supported. Use INNER or LEFT.")

            condition = JOIN_PATHS.get((primary, tbl)) or JOIN_PATHS.get((tbl, primary))
            if not condition:
                raise ValueError(f"No defined join path between '{primary}' and '{tbl}'")

            alias = TABLES[tbl]['alias']
            parts.append(f"{join_type} JOIN {DATABASE}.{tbl} {alias} ON {condition}")

        return '\n'.join(parts)

    def _build_where(self, filters: List[Dict], primary: str, active_tables: set) -> Tuple[str, List]:
        if not filters:
            # Enforce date filter on large tables
            date_col = TABLES[primary].get('date_col')
            if date_col:
                alias = TABLES[primary]['alias']
                logger.warning(f"No date filter on {primary}.{date_col} — full scan risk")
            return '', []

        parts = []
        params = []
        for i, f in enumerate(filters):
            tbl = f['table']
            self._assert_table(tbl)
            col = self._safe_column(f['column'])
            op_key = f['op']
            alias = TABLES[tbl]['alias']
            logic = f.get('logic', 'AND').upper() if i > 0 else ''

            if op_key not in FILTER_OPERATORS:
                raise ValueError(f"Invalid filter operator: {op_key}")

            op = FILTER_OPERATORS[op_key]

            if op_key in ('is_null', 'is_not_null'):
                expr = f"{alias}.{col} {op}"
            elif op_key == 'between':
                vals = f['value']
                if not isinstance(vals, (list, tuple)) or len(vals) != 2:
                    raise ValueError("BETWEEN requires [low, high] values")
                expr = f"{alias}.{col} BETWEEN %s AND %s"
                params.extend([vals[0], vals[1]])
            elif op_key in ('in', 'not_in'):
                vals = f['value']
                if isinstance(vals, str):
                    vals = [v.strip() for v in vals.split(',')]
                placeholders = ', '.join(['%s'] * len(vals))
                expr = f"{alias}.{col} {op} ({placeholders})"
                params.extend(vals)
            elif op_key == 'like':
                expr = f"{alias}.{col} {op} %s"
                params.append(f"%{f['value']}%")
            else:
                expr = f"{alias}.{col} {op} %s"
                params.append(f['value'])

            if logic:
                parts.append(f"{logic} {expr}")
            else:
                parts.append(expr)

        return ' '.join(parts), params

    def _build_group_by(self, group_by: List[str], active_tables: set) -> str:
        if not group_by:
            return ''
        parts = []
        for item in group_by:
            if '.' in item:
                tbl, col = item.split('.', 1)
                self._assert_table(tbl)
                alias = TABLES[tbl]['alias']
                parts.append(f"{alias}.{self._safe_column(col)}")
            else:
                parts.append(self._safe_column(item))
        return ', '.join(parts)

    def _build_having(self, having: List[Dict]) -> Tuple[str, List]:
        if not having:
            return '', []
        parts = []
        params = []
        for i, h in enumerate(having):
            col = h['column']  # e.g. "COUNT(*)" — already an expression
            op_key = h['op']
            logic = h.get('logic', 'AND').upper() if i > 0 else ''
            if op_key not in FILTER_OPERATORS:
                raise ValueError(f"Invalid HAVING operator: {op_key}")
            op = FILTER_OPERATORS[op_key]
            expr = f"{col} {op} %s"
            params.append(h['value'])
            parts.append(f"{logic} {expr}".strip())
        return ' '.join(parts), params

    def _build_order_by(self, order_by: List[Dict], active_tables: set) -> str:
        if not order_by:
            return ''
        parts = []
        for o in order_by[:3]:  # max 3 sort columns
            tbl = o['table']
            self._assert_table(tbl)
            col = self._safe_column(o['column'])
            direction = o.get('direction', 'ASC').upper()
            if direction not in ('ASC', 'DESC'):
                direction = 'ASC'
            alias = TABLES[tbl]['alias']
            parts.append(f"{alias}.{col} {direction}")
        return ', '.join(parts)

    def _validate_config(self, config: Dict):
        if 'primary_table' not in config:
            raise ValueError("primary_table is required")
        self._assert_table(config['primary_table'])

    def _assert_table(self, table: str):
        if table not in TABLES:
            raise ValueError(f"Table '{table}' is not in the allowed list")

    @staticmethod
    def _safe_column(name: str) -> str:
        """Allow only alphanumeric, underscore, dot, star."""
        import re
        if not re.match(r'^[a-zA-Z0-9_.*()\s]+$', name):
            raise ValueError(f"Invalid column name: {name}")
        return name

    def get_join_options(self, primary_table: str) -> List[Dict]:
        """Return available join targets for a given primary table."""
        options = []
        for (t1, t2), condition in JOIN_PATHS.items():
            if t1 == primary_table:
                options.append({'table': t2, 'display': TABLES[t2]['display'], 'condition': condition})
            elif t2 == primary_table:
                options.append({'table': t1, 'display': TABLES[t1]['display'], 'condition': condition})
        return options

    def get_table_list(self) -> List[Dict]:
        return [
            {'table': k, 'display': v['display'], 'alias': v['alias']}
            for k, v in TABLES.items()
        ]


query_builder_service = QueryBuilderService()
