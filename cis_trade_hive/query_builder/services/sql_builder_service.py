"""
SQL Builder Service

Single responsibility: build a safe parameterised Impala SQL string
from a validated config dict. No I/O, no caching, no execution.

Table whitelist and join paths are class-level constants (OCP — extend
by adding to the dict, not by modifying logic).
"""

import re
import logging
from typing import Dict, Any, List, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class SqlBuilderService:
    """Builds Impala SQL from a structured query config dict."""

    DATABASE = settings.IMPALA_CONFIG['DATABASE']

    # Whitelisted tables — alias used in generated SQL
    TABLES: Dict[str, Dict] = {
        'cis_trade':                 {'alias': 't',   'display': 'Trade',        'date_col': 'trade_date'},
        'cis_portfolio':             {'alias': 'p',   'display': 'Portfolio',    'date_col': None},
        'cis_security':              {'alias': 's',   'display': 'Security',     'date_col': None},
        'cis_equity_price':          {'alias': 'ep',  'display': 'Equity Price', 'date_col': 'price_date'},
        'cis_trade_position':        {'alias': 'pos', 'display': 'Position',     'date_col': 'trade_date'},
        'cis_counterparty_kudu':     {'alias': 'cp',  'display': 'Counterparty', 'date_col': None},
        'gmp_cis_sta_dly_fx_rates':  {'alias': 'fx',  'display': 'FX Rates',     'date_col': 'processing_date'},
    }

    # Pre-defined join paths — both directions registered for lookup
    JOIN_PATHS: Dict[Tuple, str] = {
        ('cis_trade', 'cis_portfolio'):          't.portfolio_short_name = p.portfolio_short_name',
        ('cis_trade', 'cis_security'):           't.security_label = s.security_name',
        ('cis_trade', 'cis_counterparty_kudu'):  't.broker = cp.counterparty_name',
        ('cis_trade', 'cis_equity_price'):       't.security_label = ep.security_label',
        ('cis_security', 'cis_equity_price'):    's.security_name = ep.security_label',
        ('cis_trade_position', 'cis_trade'):     'pos.trade_id = t.trade_id',
        ('cis_trade_position', 'cis_security'):  'pos.security_label = s.security_name',
        ('cis_trade_position', 'cis_portfolio'): 'pos.portfolio_short_name = p.portfolio_short_name',
    }

    # Role-based maximum row counts
    ROLE_LIMITS: Dict[str, int] = {
        'VIEWER':       1_000,
        'TRADER':       5_000,
        'RISK_MANAGER': 10_000,
        'ADMIN':        50_000,
        'RBAC_ADMIN':   50_000,
    }
    DEFAULT_LIMIT = 1_000
    MAX_JOINS = 3

    FILTER_OPERATORS: Dict[str, str] = {
        'eq':           '=',
        'neq':          '!=',
        'gt':           '>',
        'gte':          '>=',
        'lt':           '<',
        'lte':          '<=',
        'like':         'LIKE',
        'not_like':     'NOT LIKE',
        'in':           'IN',
        'not_in':       'NOT IN',
        'between':      'BETWEEN',
        'is_null':      'IS NULL',
        'is_not_null':  'IS NOT NULL',
    }

    VALID_AGGREGATIONS = frozenset({'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COUNT_DISTINCT'})
    VALID_JOIN_TYPES = frozenset({'INNER', 'LEFT'})
    VALID_DIRECTIONS = frozenset({'ASC', 'DESC'})

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def build(self, config: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """
        Build SQL from config dict. Returns (sql, params).
        Raises ValueError for invalid config.
        """
        self._validate(config)

        primary        = config['primary_table']
        joins_cfg      = config.get('joins', [])
        columns_cfg    = config.get('columns', [])
        filters_cfg    = config.get('filters', [])
        group_by_cfg   = config.get('group_by', [])
        having_cfg     = config.get('having', [])
        order_by_cfg   = config.get('order_by', [])
        user_role      = config.get('user_role', 'VIEWER').upper()

        requested_limit = int(config.get('limit', self.DEFAULT_LIMIT))
        if requested_limit <= 0:
            raise ValueError("limit must be a positive integer")
        row_limit = min(requested_limit, self.ROLE_LIMITS.get(user_role, self.DEFAULT_LIMIT))

        select_sql, params = self._build_select(columns_cfg)
        from_sql          = f"{self.DATABASE}.{primary} {self.TABLES[primary]['alias']}"
        join_sql          = self._build_joins(primary, joins_cfg)
        where_sql, wparams = self._build_where(filters_cfg)
        params.extend(wparams)
        group_sql         = self._build_group_by(group_by_cfg)
        having_sql, hparams = self._build_having(having_cfg)
        params.extend(hparams)
        order_sql         = self._build_order_by(order_by_cfg)

        parts = [f"SELECT {select_sql}", f"FROM {from_sql}"]
        if join_sql:   parts.append(join_sql)
        if where_sql:  parts.append(f"WHERE {where_sql}")
        if group_sql:  parts.append(f"GROUP BY {group_sql}")
        if having_sql: parts.append(f"HAVING {having_sql}")
        if order_sql:  parts.append(f"ORDER BY {order_sql}")
        parts.append(f"LIMIT {row_limit}")

        return '\n'.join(parts), params

    def get_table_list(self) -> List[Dict]:
        return [
            {'table': k, 'display': v['display'], 'alias': v['alias']}
            for k, v in self.TABLES.items()
        ]

    def get_join_options(self, primary_table: str) -> List[Dict]:
        options = []
        for (t1, t2), condition in self.JOIN_PATHS.items():
            if t1 == primary_table:
                info = self.TABLES.get(t2, {})
                options.append({'table': t2, 'display': info.get('display', t2), 'condition': condition})
            elif t2 == primary_table:
                info = self.TABLES.get(t1, {})
                options.append({'table': t1, 'display': info.get('display', t1), 'condition': condition})
        return options

    # ----------------------------------------------------------------
    # Private builders — each builds exactly one SQL clause (SRP)
    # ----------------------------------------------------------------

    def _build_select(self, columns: List[Dict]) -> Tuple[str, List]:
        if not columns:
            # No columns specified — only select from the primary table alias to avoid
            # cartesian column explosion when joins are present (corner case: * on all
            # tables in TABLES includes non-joined tables, producing invalid SQL).
            return '*', []

        seen_aliases: set = set()
        parts = []
        for col in columns:
            tbl  = self._assert_table(col.get('table', ''))
            raw_col = col.get('column', '').strip()
            if not raw_col:
                raise ValueError("Column name cannot be empty")
            name = self._safe_identifier(raw_col)
            alias_str = self.TABLES[tbl]['alias']
            agg  = col.get('agg', '').strip().upper()
            col_alias = col.get('alias', '').strip()

            if agg:
                if agg not in self.VALID_AGGREGATIONS:
                    raise ValueError(f"Invalid aggregation: {agg!r}. "
                                     f"Valid: {sorted(self.VALID_AGGREGATIONS)}")
                expr = (f"COUNT(DISTINCT {alias_str}.{name})"
                        if agg == 'COUNT_DISTINCT'
                        else f"{agg}({'*' if name == '*' else f'{alias_str}.{name}'})")
            else:
                expr = f"{alias_str}.{name}"

            if col_alias:
                safe_alias = self._safe_identifier(col_alias)
                if safe_alias in seen_aliases:
                    raise ValueError(f"Duplicate column alias: {safe_alias!r}")
                seen_aliases.add(safe_alias)
                expr += f" AS {safe_alias}"

            parts.append(expr)

        return ', '.join(parts), []

    def _build_joins(self, primary: str, joins: List[Dict]) -> str:
        if len(joins) > self.MAX_JOINS:
            raise ValueError(f"Maximum {self.MAX_JOINS} joins allowed")

        lines = []
        for j in joins:
            tbl       = self._assert_table(j['table'])
            join_type = j.get('type', 'INNER').upper()
            if join_type not in self.VALID_JOIN_TYPES:
                raise ValueError(f"Join type '{join_type}' not supported. Use INNER or LEFT.")

            condition = (self.JOIN_PATHS.get((primary, tbl))
                         or self.JOIN_PATHS.get((tbl, primary)))
            if not condition:
                raise ValueError(f"No defined join path between '{primary}' and '{tbl}'")

            lines.append(
                f"{join_type} JOIN {self.DATABASE}.{tbl} {self.TABLES[tbl]['alias']} ON {condition}"
            )
        return '\n'.join(lines)

    def _build_where(self, filters: List[Dict]) -> Tuple[str, List]:
        if not filters:
            return '', []

        parts, params = [], []
        for i, f in enumerate(filters):
            tbl     = self._assert_table(f.get('table', ''))
            col     = self._safe_identifier(f.get('column', ''))
            op_key  = f.get('op', '')
            alias   = self.TABLES[tbl]['alias']
            logic   = f.get('logic', 'AND').upper() if i > 0 else ''
            if logic not in ('AND', 'OR'):
                logic = 'AND'

            if op_key not in self.FILTER_OPERATORS:
                raise ValueError(f"Invalid filter operator: {op_key!r}")

            op = self.FILTER_OPERATORS[op_key]

            if op_key in ('is_null', 'is_not_null'):
                expr = f"{alias}.{col} {op}"
            elif op_key == 'between':
                vals = f.get('value')
                if isinstance(vals, str):
                    parts_v = [v.strip() for v in vals.split(',')]
                    if len(parts_v) == 2:
                        vals = parts_v
                if not isinstance(vals, (list, tuple)) or len(vals) != 2:
                    raise ValueError("BETWEEN requires exactly two values: [low, high] or 'low,high'")
                expr = f"{alias}.{col} BETWEEN %s AND %s"
                params.extend(vals)
            elif op_key in ('in', 'not_in'):
                vals = f.get('value', '')
                if isinstance(vals, str):
                    vals = [v.strip() for v in vals.split(',') if v.strip()]
                if not vals:
                    raise ValueError(f"{op_key.upper()} requires at least one value")
                placeholders = ', '.join(['%s'] * len(vals))
                expr = f"{alias}.{col} {op} ({placeholders})"
                params.extend(vals)
            elif op_key in ('like', 'not_like'):
                val = f.get('value', '')
                expr = f"{alias}.{col} {op} %s"
                params.append(f"%{val}%")
            else:
                val = f.get('value')
                if val is None or val == '':
                    raise ValueError(f"Filter on '{col}' requires a value for operator '{op_key}'")
                expr = f"{alias}.{col} {op} %s"
                params.append(val)

            parts.append(f"{logic} {expr}".strip())

        return ' '.join(parts), params

    def _build_group_by(self, group_by: List[str]) -> str:
        if not group_by:
            return ''
        parts = []
        for item in group_by:
            if '.' in item:
                tbl, col = item.split('.', 1)
                self._assert_table(tbl)
                parts.append(f"{self.TABLES[tbl]['alias']}.{self._safe_identifier(col)}")
            else:
                parts.append(self._safe_identifier(item))
        return ', '.join(parts)

    def _build_having(self, having: List[Dict]) -> Tuple[str, List]:
        if not having:
            return '', []
        parts, params = [], []
        for i, h in enumerate(having):
            op_key = h['op']
            if op_key not in self.FILTER_OPERATORS:
                raise ValueError(f"Invalid HAVING operator: {op_key}")
            logic = h.get('logic', 'AND').upper() if i > 0 else ''
            expr = f"{h['column']} {self.FILTER_OPERATORS[op_key]} %s"
            params.append(h['value'])
            parts.append(f"{logic} {expr}".strip())
        return ' '.join(parts), params

    def _build_order_by(self, order_by: List[Dict]) -> str:
        if not order_by:
            return ''
        parts = []
        for o in order_by[:3]:
            tbl = self._assert_table(o['table'])
            col = self._safe_identifier(o['column'])
            direction = o.get('direction', 'ASC').upper()
            if direction not in self.VALID_DIRECTIONS:
                direction = 'ASC'
            parts.append(f"{self.TABLES[tbl]['alias']}.{col} {direction}")
        return ', '.join(parts)

    # ----------------------------------------------------------------
    # Guards
    # ----------------------------------------------------------------

    def _validate(self, config: Dict) -> None:
        if not isinstance(config, dict):
            raise ValueError("Query config must be a dict")
        if not config.get('primary_table'):
            raise ValueError("primary_table is required")
        self._assert_table(config['primary_table'])
        limit = config.get('limit', self.DEFAULT_LIMIT)
        try:
            int_limit = int(limit)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid limit value: {limit!r}")
        if int_limit <= 0:
            raise ValueError(f"Invalid limit value: {limit!r} — must be a positive integer")

    def _assert_table(self, table: str) -> str:
        if table not in self.TABLES:
            raise ValueError(f"Table '{table}' is not in the allowed list")
        return table

    @staticmethod
    def _safe_identifier(name: str) -> str:
        # Allow letters, digits, underscore, dot, *, ( ) and single spaces — nothing else.
        # Explicit newline/tab rejection before the regex (re.DOTALL would miss \n in \s).
        if '\n' in name or '\r' in name or '\t' in name or '\x00' in name:
            raise ValueError(f"Invalid identifier: {name!r}")
        if not re.match(r'^[a-zA-Z0-9_.*() ]+$', name):
            raise ValueError(f"Invalid identifier: {name!r}")
        return name


sql_builder_service = SqlBuilderService()
