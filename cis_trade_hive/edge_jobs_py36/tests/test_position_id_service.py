"""Tests for edge_jobs_py36/lib/position_id_service.py."""
import hashlib

import pytest

from edge_jobs_py36.lib import position_id_service as pid


class TestConstants:
    def test_traded_and_settled_values(self):
        assert pid.TRADED == 'TRADED'
        assert pid.SETTLED == 'SETTLED'

    def test_position_basis_choices(self):
        assert pid.POSITION_BASIS_CHOICES == ['TRADED', 'SETTLED']

    def test_position_basis_labels(self):
        assert pid.POSITION_BASIS_LABELS == {
            'TRADED': 'Traded',
            'SETTLED': 'Settled',
        }


class TestPositionId:
    def test_deterministic_same_inputs_same_id(self):
        a = pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS')
        b = pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS')
        assert a == b

    def test_different_portfolio_changes_id(self):
        a = pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS')
        b = pid.position_id('PORT2', 'SEC1', 'TRADED', '2026-09-17', 'CIS')
        assert a != b

    def test_different_security_changes_id(self):
        a = pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS')
        b = pid.position_id('PORT1', 'SEC2', 'TRADED', '2026-09-17', 'CIS')
        assert a != b

    def test_different_basis_changes_id(self):
        a = pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS')
        b = pid.position_id('PORT1', 'SEC1', 'SETTLED', '2026-09-17', 'CIS')
        assert a != b

    def test_different_date_changes_id(self):
        a = pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS')
        b = pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-18', 'CIS')
        assert a != b

    def test_different_src_system_changes_id(self):
        a = pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS')
        b = pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-17', 'AMS')
        assert a != b

    def test_returns_int(self):
        result = pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS')
        assert isinstance(result, int)

    def test_result_is_non_negative_and_bigint_safe(self):
        result = pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS')
        assert result >= 0
        assert result < 2 ** 63

    def test_matches_manual_md5_computation(self):
        key = '|'.join(['PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS'])
        digest = hashlib.md5(key.encode('utf-8')).hexdigest()
        expected = abs(int(digest, 16)) % (2 ** 63)
        assert pid.position_id('PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS') == expected

    @pytest.mark.parametrize('field_index', range(5))
    def test_none_component_treated_as_empty_string(self, field_index):
        """Any single None component hashes the same as passing ''."""
        args_with_none = ['PORT1', 'SEC1', 'TRADED', '2026-09-17', 'CIS']
        args_with_empty = list(args_with_none)
        args_with_none[field_index] = None
        args_with_empty[field_index] = ''
        assert pid.position_id(*args_with_none) == pid.position_id(*args_with_empty)

    def test_all_none_components(self):
        result = pid.position_id(None, None, None, None, None)
        expected = abs(int(hashlib.md5(b'||||').hexdigest(), 16)) % (2 ** 63)
        assert result == expected

    def test_all_empty_string_components(self):
        result = pid.position_id('', '', '', '', '')
        expected = abs(int(hashlib.md5(b'||||').hexdigest(), 16)) % (2 ** 63)
        assert result == expected

    def test_field_order_matters(self):
        """Swapping two field values (that would concatenate identically
        if order didn't matter) must not collide for distinguishable inputs."""
        a = pid.position_id('AB', 'CD', 'TRADED', '2026-09-17', 'CIS')
        b = pid.position_id('A', 'BCD', 'TRADED', '2026-09-17', 'CIS')
        assert a != b

    def test_unicode_inputs_do_not_raise(self):
        result = pid.position_id('Pörtfölio', 'Sécurité', 'TRADED', '2026-09-17', 'CIS')
        assert isinstance(result, int)


class TestPositionIdSqlConstant:
    def test_position_id_sql_contains_fnv_hash(self):
        assert 'fnv_hash' in pid.POSITION_ID_SQL

    def test_position_id_sql_contains_concat_ws(self):
        assert 'CONCAT_WS' in pid.POSITION_ID_SQL

    def test_position_id_sql_has_placeholders(self):
        for placeholder in ('{p}', '{s}', '{b}', '{d}', '{src}'):
            assert placeholder in pid.POSITION_ID_SQL

    def test_position_id_sql_casts_to_bigint(self):
        assert 'BIGINT' in pid.POSITION_ID_SQL

    def test_position_id_sql_wraps_in_abs(self):
        assert pid.POSITION_ID_SQL.strip().startswith('ABS(')


class TestPositionIdSqlExpr:
    def test_substitutes_all_expressions(self):
        result = pid.position_id_sql_expr(
            's.portfolio', 's.security_label', 's.position_basis',
            'CAST(s.reporting_date AS STRING)', 's.src_system',
        )
        assert 's.portfolio' in result
        assert 's.security_label' in result
        assert 's.position_basis' in result
        assert 'CAST(s.reporting_date AS STRING)' in result
        assert 's.src_system' in result

    def test_wraps_each_expression_in_coalesce(self):
        result = pid.position_id_sql_expr('a', 'b', 'c', 'd', 'e')
        assert "COALESCE(a, '')" in result
        assert "COALESCE(b, '')" in result
        assert "COALESCE(c, '')" in result
        assert "COALESCE(d, '')" in result
        assert "COALESCE(e, '')" in result

    def test_contains_fnv_hash_and_concat_ws(self):
        result = pid.position_id_sql_expr('a', 'b', 'c', 'd', 'e')
        assert 'fnv_hash' in result
        assert 'CONCAT_WS' in result

    def test_casts_to_bigint_and_wraps_abs(self):
        result = pid.position_id_sql_expr('a', 'b', 'c', 'd', 'e')
        assert result.startswith('ABS(CAST(fnv_hash(')
        assert result.endswith(')) AS BIGINT))')

    def test_different_expressions_produce_different_sql(self):
        result_a = pid.position_id_sql_expr('a', 'b', 'c', 'd', 'e')
        result_b = pid.position_id_sql_expr('x', 'y', 'z', 'w', 'v')
        assert result_a != result_b
