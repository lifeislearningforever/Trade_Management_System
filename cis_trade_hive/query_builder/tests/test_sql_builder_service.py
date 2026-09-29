"""
Tests for SqlBuilderService — covers happy path, corner cases, and
all negative (ValueError) paths.
"""

import pytest
from query_builder.services.sql_builder_service import SqlBuilderService


@pytest.fixture
def svc():
    return SqlBuilderService()


BASE = {'primary_table': 'cis_trade', 'limit': 100}


# ================================================================
# _validate — config-level guards
# ================================================================

class TestValidate:
    def test_missing_primary_table(self, svc):
        with pytest.raises(ValueError, match="primary_table is required"):
            svc.build({'limit': 10})

    def test_empty_primary_table(self, svc):
        with pytest.raises(ValueError, match="primary_table is required"):
            svc.build({'primary_table': '', 'limit': 10})

    def test_unknown_primary_table(self, svc):
        with pytest.raises(ValueError, match="not in the allowed list"):
            svc.build({'primary_table': 'cis_secret_table', 'limit': 10})

    def test_non_dict_config(self, svc):
        with pytest.raises(ValueError, match="must be a dict"):
            svc.build("SELECT 1")

    def test_zero_limit(self, svc):
        with pytest.raises(ValueError, match="Invalid limit value"):
            svc.build({'primary_table': 'cis_trade', 'limit': 0})

    def test_negative_limit(self, svc):
        with pytest.raises(ValueError, match="Invalid limit value"):
            svc.build({'primary_table': 'cis_trade', 'limit': -5})

    def test_non_numeric_limit(self, svc):
        with pytest.raises(ValueError, match="Invalid limit value"):
            svc.build({'primary_table': 'cis_trade', 'limit': 'all'})


# ================================================================
# _build_select — column selection
# ================================================================

class TestBuildSelect:
    def test_no_columns_returns_star(self, svc):
        sql, _ = svc.build(BASE)
        assert 'SELECT *' in sql

    def test_single_column(self, svc):
        cfg = {**BASE, 'columns': [{'table': 'cis_trade', 'column': 'trade_id'}]}
        sql, _ = svc.build(cfg)
        assert 't.trade_id' in sql

    def test_column_with_alias(self, svc):
        cfg = {**BASE, 'columns': [
            {'table': 'cis_trade', 'column': 'trade_id', 'alias': 'Deal_No'}
        ]}
        sql, _ = svc.build(cfg)
        assert 't.trade_id AS Deal_No' in sql

    def test_duplicate_alias_raises(self, svc):
        cfg = {**BASE, 'columns': [
            {'table': 'cis_trade', 'column': 'trade_id',    'alias': 'X'},
            {'table': 'cis_trade', 'column': 'trade_type',  'alias': 'X'},
        ]}
        with pytest.raises(ValueError, match="Duplicate column alias"):
            svc.build(cfg)

    def test_empty_column_name_raises(self, svc):
        cfg = {**BASE, 'columns': [{'table': 'cis_trade', 'column': ''}]}
        with pytest.raises(ValueError, match="Column name cannot be empty"):
            svc.build(cfg)

    def test_unknown_table_in_column_raises(self, svc):
        cfg = {**BASE, 'columns': [{'table': 'evil_table', 'column': 'id'}]}
        with pytest.raises(ValueError, match="not in the allowed list"):
            svc.build(cfg)

    def test_sql_injection_in_column_raises(self, svc):
        cfg = {**BASE, 'columns': [{'table': 'cis_trade', 'column': 'id; DROP TABLE cis_trade--'}]}
        with pytest.raises(ValueError, match="Invalid identifier"):
            svc.build(cfg)

    def test_sql_injection_in_alias_raises(self, svc):
        cfg = {**BASE, 'columns': [
            {'table': 'cis_trade', 'column': 'trade_id', 'alias': "x' OR '1'='1"}
        ]}
        with pytest.raises(ValueError, match="Invalid identifier"):
            svc.build(cfg)

    def test_invalid_aggregation_raises(self, svc):
        cfg = {**BASE, 'columns': [
            {'table': 'cis_trade', 'column': 'quantity', 'agg': 'HACK'}
        ]}
        with pytest.raises(ValueError, match="Invalid aggregation"):
            svc.build(cfg)

    def test_valid_aggregations(self, svc):
        for agg in ('COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COUNT_DISTINCT'):
            cfg = {**BASE, 'columns': [
                {'table': 'cis_trade', 'column': 'quantity', 'agg': agg}
            ]}
            sql, _ = svc.build(cfg)
            assert agg.replace('_DISTINCT', '') in sql.upper()

    def test_count_distinct_generates_correct_sql(self, svc):
        cfg = {**BASE, 'columns': [
            {'table': 'cis_trade', 'column': 'security_label', 'agg': 'COUNT_DISTINCT'}
        ]}
        sql, _ = svc.build(cfg)
        assert 'COUNT(DISTINCT t.security_label)' in sql


# ================================================================
# _build_joins
# ================================================================

class TestBuildJoins:
    def test_valid_join(self, svc):
        cfg = {**BASE, 'joins': [{'table': 'cis_portfolio', 'type': 'INNER'}]}
        sql, _ = svc.build(cfg)
        assert 'INNER JOIN' in sql
        assert 'portfolio_short_name' in sql

    def test_left_join(self, svc):
        cfg = {**BASE, 'joins': [{'table': 'cis_portfolio', 'type': 'LEFT'}]}
        sql, _ = svc.build(cfg)
        assert 'LEFT JOIN' in sql

    def test_invalid_join_type_raises(self, svc):
        cfg = {**BASE, 'joins': [{'table': 'cis_portfolio', 'type': 'CROSS'}]}
        with pytest.raises(ValueError, match="Join type 'CROSS' not supported"):
            svc.build(cfg)

    def test_too_many_joins_raises(self, svc):
        cfg = {**BASE, 'joins': [
            {'table': 'cis_portfolio',     'type': 'INNER'},
            {'table': 'cis_security',      'type': 'INNER'},
            {'table': 'cis_counterparty_kudu', 'type': 'LEFT'},
            {'table': 'cis_equity_price',  'type': 'LEFT'},
        ]}
        with pytest.raises(ValueError, match="Maximum 3 joins"):
            svc.build(cfg)

    def test_unknown_join_table_raises(self, svc):
        cfg = {**BASE, 'joins': [{'table': 'users', 'type': 'INNER'}]}
        with pytest.raises(ValueError, match="not in the allowed list"):
            svc.build(cfg)

    def test_no_join_path_raises(self, svc):
        # cis_equity_price → cis_portfolio has no direct path
        cfg = {'primary_table': 'cis_equity_price', 'limit': 10,
               'joins': [{'table': 'cis_portfolio', 'type': 'INNER'}]}
        with pytest.raises(ValueError, match="No defined join path"):
            svc.build(cfg)

    def test_join_path_both_directions(self, svc):
        # cis_trade_position → cis_trade (forward)
        cfg1 = {'primary_table': 'cis_trade_position', 'limit': 10,
                'joins': [{'table': 'cis_trade', 'type': 'INNER'}]}
        sql1, _ = svc.build(cfg1)
        assert 'trade_id' in sql1

        # cis_trade → cis_portfolio (also has a defined path)
        cfg2 = {**BASE, 'joins': [{'table': 'cis_portfolio', 'type': 'INNER'}]}
        sql2, _ = svc.build(cfg2)
        assert 'portfolio_short_name' in sql2


# ================================================================
# _build_where — filter conditions
# ================================================================

class TestBuildWhere:
    def _cfg(self, filters):
        return {**BASE, 'filters': filters}

    def test_eq_filter(self, svc):
        sql, params = svc.build(self._cfg([
            {'table': 'cis_trade', 'column': 'trade_type', 'op': 'eq', 'value': 'BUY'}
        ]))
        assert 'WHERE' in sql
        assert params == ['BUY']

    def test_is_null_no_value_needed(self, svc):
        sql, params = svc.build(self._cfg([
            {'table': 'cis_trade', 'column': 'broker', 'op': 'is_null'}
        ]))
        assert 'IS NULL' in sql
        assert params == []

    def test_is_not_null(self, svc):
        sql, params = svc.build(self._cfg([
            {'table': 'cis_trade', 'column': 'broker', 'op': 'is_not_null'}
        ]))
        assert 'IS NOT NULL' in sql

    def test_between_list(self, svc):
        sql, params = svc.build(self._cfg([
            {'table': 'cis_trade', 'column': 'quantity', 'op': 'between', 'value': [10, 100]}
        ]))
        assert 'BETWEEN' in sql
        assert params == [10, 100]

    def test_between_string_shorthand(self, svc):
        sql, params = svc.build(self._cfg([
            {'table': 'cis_trade', 'column': 'quantity', 'op': 'between', 'value': '10,100'}
        ]))
        assert 'BETWEEN' in sql
        assert params == ['10', '100']

    def test_between_wrong_arity_raises(self, svc):
        with pytest.raises(ValueError, match="BETWEEN requires exactly two values"):
            svc.build(self._cfg([
                {'table': 'cis_trade', 'column': 'quantity', 'op': 'between', 'value': [1]}
            ]))

    def test_in_operator(self, svc):
        sql, params = svc.build(self._cfg([
            {'table': 'cis_trade', 'column': 'trade_type', 'op': 'in', 'value': 'BUY,SELL'}
        ]))
        assert 'IN' in sql
        assert 'BUY' in params and 'SELL' in params

    def test_in_empty_value_raises(self, svc):
        with pytest.raises(ValueError, match="IN requires at least one value"):
            svc.build(self._cfg([
                {'table': 'cis_trade', 'column': 'trade_type', 'op': 'in', 'value': ''}
            ]))

    def test_like_wraps_percent(self, svc):
        sql, params = svc.build(self._cfg([
            {'table': 'cis_trade', 'column': 'security_label', 'op': 'like', 'value': 'APPL'}
        ]))
        assert params == ['%APPL%']

    def test_not_like(self, svc):
        sql, params = svc.build(self._cfg([
            {'table': 'cis_trade', 'column': 'security_label', 'op': 'not_like', 'value': 'TEST'}
        ]))
        assert 'NOT LIKE' in sql
        assert params == ['%TEST%']

    def test_missing_value_for_eq_raises(self, svc):
        with pytest.raises(ValueError, match="requires a value"):
            svc.build(self._cfg([
                {'table': 'cis_trade', 'column': 'trade_type', 'op': 'eq', 'value': ''}
            ]))

    def test_invalid_operator_raises(self, svc):
        with pytest.raises(ValueError, match="Invalid filter operator"):
            svc.build(self._cfg([
                {'table': 'cis_trade', 'column': 'trade_type', 'op': 'contains', 'value': 'X'}
            ]))

    def test_invalid_logic_defaults_to_and(self, svc):
        sql, _ = svc.build(self._cfg([
            {'table': 'cis_trade', 'column': 'trade_type', 'op': 'eq', 'value': 'BUY'},
            {'table': 'cis_trade', 'column': 'status',     'op': 'eq', 'value': 'ACTIVE',
             'logic': 'INJECT; DROP TABLE--'},
        ]))
        assert 'AND' in sql

    def test_sql_injection_in_filter_column_raises(self, svc):
        with pytest.raises(ValueError, match="Invalid identifier"):
            svc.build(self._cfg([
                {'table': 'cis_trade', 'column': "trade_id' OR '1'='1", 'op': 'eq', 'value': 'x'}
            ]))

    def test_unknown_table_in_filter_raises(self, svc):
        with pytest.raises(ValueError, match="not in the allowed list"):
            svc.build(self._cfg([
                {'table': 'admin_users', 'column': 'password', 'op': 'eq', 'value': 'x'}
            ]))

    def test_multiple_filters_with_or(self, svc):
        sql, params = svc.build(self._cfg([
            {'table': 'cis_trade', 'column': 'trade_type', 'op': 'eq', 'value': 'BUY'},
            {'table': 'cis_trade', 'column': 'trade_type', 'op': 'eq', 'value': 'SELL', 'logic': 'OR'},
        ]))
        assert 'OR' in sql
        assert 'BUY' in params and 'SELL' in params


# ================================================================
# _build_group_by
# ================================================================

class TestBuildGroupBy:
    def test_group_by_with_table_prefix(self, svc):
        cfg = {**BASE, 'group_by': ['cis_trade.trade_type']}
        sql, _ = svc.build(cfg)
        assert 'GROUP BY t.trade_type' in sql

    def test_group_by_unknown_table_raises(self, svc):
        cfg = {**BASE, 'group_by': ['hack_table.col']}
        with pytest.raises(ValueError, match="not in the allowed list"):
            svc.build(cfg)

    def test_group_by_injection_raises(self, svc):
        # The table part passes but the column injection is caught by _safe_identifier
        cfg = {**BASE, 'group_by': ["cis_trade.x'; DROP TABLE--"]}
        with pytest.raises(ValueError, match="Invalid identifier"):
            svc.build(cfg)


# ================================================================
# _build_order_by
# ================================================================

class TestBuildOrderBy:
    def test_order_asc(self, svc):
        cfg = {**BASE, 'order_by': [{'table': 'cis_trade', 'column': 'trade_date', 'direction': 'ASC'}]}
        sql, _ = svc.build(cfg)
        assert 'ORDER BY t.trade_date ASC' in sql

    def test_order_desc(self, svc):
        cfg = {**BASE, 'order_by': [{'table': 'cis_trade', 'column': 'trade_date', 'direction': 'DESC'}]}
        sql, _ = svc.build(cfg)
        assert 'ORDER BY t.trade_date DESC' in sql

    def test_invalid_direction_defaults_asc(self, svc):
        cfg = {**BASE, 'order_by': [{'table': 'cis_trade', 'column': 'trade_date', 'direction': 'SIDEWAYS'}]}
        sql, _ = svc.build(cfg)
        assert 'ASC' in sql

    def test_more_than_3_order_by_silently_truncated(self, svc):
        cfg = {**BASE, 'order_by': [
            {'table': 'cis_trade', 'column': 'trade_date',     'direction': 'ASC'},
            {'table': 'cis_trade', 'column': 'trade_type',     'direction': 'ASC'},
            {'table': 'cis_trade', 'column': 'quantity',       'direction': 'DESC'},
            {'table': 'cis_trade', 'column': 'security_label', 'direction': 'ASC'},
        ]}
        sql, _ = svc.build(cfg)
        assert sql.count(',') <= 2   # max 3 cols → 2 commas in ORDER BY


# ================================================================
# Role-based LIMIT enforcement
# ================================================================

class TestRoleLimits:
    @pytest.mark.parametrize('role,max_rows', [
        ('VIEWER',       1_000),
        ('TRADER',       5_000),
        ('RISK_MANAGER', 10_000),
        ('ADMIN',        50_000),
        ('RBAC_ADMIN',   50_000),
    ])
    def test_role_cap_enforced(self, svc, role, max_rows):
        cfg = {'primary_table': 'cis_trade', 'limit': 999_999, 'user_role': role}
        sql, _ = svc.build(cfg)
        assert f'LIMIT {max_rows}' in sql

    def test_unknown_role_defaults_to_viewer_cap(self, svc):
        cfg = {'primary_table': 'cis_trade', 'limit': 999_999, 'user_role': 'SUPERUSER'}
        sql, _ = svc.build(cfg)
        assert f'LIMIT {SqlBuilderService.DEFAULT_LIMIT}' in sql

    def test_requested_limit_below_role_cap_honoured(self, svc):
        cfg = {'primary_table': 'cis_trade', 'limit': 50, 'user_role': 'ADMIN'}
        sql, _ = svc.build(cfg)
        assert 'LIMIT 50' in sql


# ================================================================
# Safe identifier
# ================================================================

class TestSafeIdentifier:
    @pytest.mark.parametrize('name', [
        "trade_id", "trade_date", "quantity", "col_123", "SUM(*)", "COUNT(*)",
    ])
    def test_valid_identifiers(self, svc, name):
        assert svc._safe_identifier(name) == name

    @pytest.mark.parametrize('name', [
        "'; DROP TABLE--", "1=1", "col`hack`", "col\x00null", "col\nbreak",
        "--comment", "col;inject",
    ])
    def test_invalid_identifiers_raise(self, svc, name):
        with pytest.raises(ValueError, match="Invalid identifier"):
            svc._safe_identifier(name)


# ================================================================
# Full SQL structure
# ================================================================

class TestFullSQL:
    def test_minimal_build_contains_required_clauses(self, svc):
        sql, params = svc.build(BASE)
        assert sql.startswith('SELECT')
        assert 'FROM gmp_cis.cis_trade' in sql
        assert 'LIMIT' in sql
        assert params == []

    def test_full_featured_query(self, svc):
        cfg = {
            'primary_table': 'cis_trade',
            'limit': 200,
            'user_role': 'ADMIN',
            'joins': [{'table': 'cis_portfolio', 'type': 'LEFT'}],
            'columns': [
                {'table': 'cis_trade',     'column': 'trade_id',    'alias': 'Deal'},
                {'table': 'cis_portfolio', 'column': 'portfolio_short_name'},
                {'table': 'cis_trade',     'column': 'quantity',    'agg': 'SUM', 'alias': 'Total_Qty'},
            ],
            'filters': [
                {'table': 'cis_trade', 'column': 'trade_type', 'op': 'eq', 'value': 'BUY'},
            ],
            'group_by': ['cis_trade.trade_id', 'cis_portfolio.portfolio_short_name'],
            'order_by': [{'table': 'cis_trade', 'column': 'trade_id', 'direction': 'DESC'}],
        }
        sql, params = svc.build(cfg)
        assert 'LEFT JOIN' in sql
        assert 'SUM(t.quantity) AS Total_Qty' in sql
        assert 'GROUP BY' in sql
        assert 'ORDER BY t.trade_id DESC' in sql
        assert params == ['BUY']

    def test_database_prefix_always_present(self, svc):
        sql, _ = svc.build(BASE)
        assert 'gmp_cis.cis_trade' in sql

    def test_get_table_list(self, svc):
        tables = svc.get_table_list()
        names = [t['table'] for t in tables]
        assert 'cis_trade' in names
        assert 'cis_portfolio' in names

    def test_get_join_options_for_trade(self, svc):
        options = svc.get_join_options('cis_trade')
        tables = [o['table'] for o in options]
        assert 'cis_portfolio' in tables
        assert 'cis_security' in tables
