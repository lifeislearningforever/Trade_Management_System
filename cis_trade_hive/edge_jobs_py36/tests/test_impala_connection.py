"""Tests for edge_jobs_py36/lib/impala_connection.py.

The real `impala` package isn't installed in this environment (mirrors most
dev/test setups), so edge_jobs_py36.lib.impala_connection.IMPALA_AVAILABLE
is False at import time and `impala_connect` was never bound. Tests that
need the "available" code paths patch IMPALA_AVAILABLE to True and inject
`impala_connect` as a mock (create=True, since the name doesn't exist on
the module otherwise).
"""
import time
from unittest.mock import patch, MagicMock

import pytest

from edge_jobs_py36.lib.impala_connection import (
    ImpalaConnectionManager,
    QueryCache,
    _query_snippet,
    impala_manager,
    query_cache,
)


@pytest.fixture
def fresh_manager():
    """Reset the ImpalaConnectionManager singleton so each test gets an
    isolated instance with its own pool/counters, then restore afterward."""
    original = ImpalaConnectionManager._instance
    ImpalaConnectionManager._instance = None
    mgr = ImpalaConnectionManager()
    yield mgr
    ImpalaConnectionManager._instance = original


@pytest.fixture
def available():
    """Patch IMPALA_AVAILABLE True and inject a mock impala_connect."""
    mock_connect = MagicMock()
    with patch('edge_jobs_py36.lib.impala_connection.IMPALA_AVAILABLE', True), \
         patch('edge_jobs_py36.lib.impala_connection.impala_connect', mock_connect, create=True):
        yield mock_connect


class TestQuerySnippet:
    def test_short_query_unchanged(self):
        assert _query_snippet('SELECT 1') == 'SELECT 1'

    def test_collapses_whitespace(self):
        assert _query_snippet('SELECT   1\n  FROM  x') == 'SELECT 1 FROM x'

    def test_truncates_long_query(self):
        long_query = 'SELECT ' + 'a' * 200
        result = _query_snippet(long_query, max_len=20)
        assert len(result) == 23  # 20 + '...'
        assert result.endswith('...')


class TestSingleton:
    def test_returns_same_instance(self):
        a = ImpalaConnectionManager()
        b = ImpalaConnectionManager()
        assert a is b

    def test_module_exposes_singleton(self):
        assert isinstance(impala_manager, ImpalaConnectionManager)


class TestManagerInitialization:
    def test_pool_initialized_with_configured_size(self, fresh_manager):
        assert fresh_manager._max_connections == fresh_manager._pool.maxsize

    def test_connection_count_starts_at_zero(self, fresh_manager):
        assert fresh_manager._connection_count == 0


class TestCreateConnectionUnavailable:
    def test_returns_none_when_impala_unavailable(self, fresh_manager):
        with patch('edge_jobs_py36.lib.impala_connection.IMPALA_AVAILABLE', False):
            assert fresh_manager._create_connection() is None


class TestCreateConnectionAvailable:
    def test_creates_and_configures_connection(self, fresh_manager, available):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        available.return_value = mock_conn

        conn = fresh_manager._create_connection()

        assert conn is mock_conn
        assert hasattr(conn, '_created_at')

    def test_returns_none_on_exception(self, fresh_manager, available):
        available.side_effect = RuntimeError('connection refused')
        assert fresh_manager._create_connection() is None

    def test_ssl_enabled_when_env_true(self, fresh_manager, available, monkeypatch):
        monkeypatch.setenv('IMPALA_USE_SSL', 'true')
        mock_conn = MagicMock()
        available.return_value = mock_conn
        fresh_manager._create_connection()
        kwargs = available.call_args[1]
        assert kwargs.get('use_ssl') is True

    def test_kerberos_service_name_added_for_gssapi(self, fresh_manager, available):
        with patch('edge_jobs_py36.lib.impala_connection.settings') as mock_settings:
            mock_settings.IMPALA_CONFIG = {
                'HOST': 'h', 'PORT': 21050, 'DATABASE': 'gmp_cis',
                'AUTH_MECHANISM': 'GSSAPI', 'KERBEROS_SERVICE_NAME': 'impala',
            }
            fresh_manager._create_connection()
        kwargs = available.call_args[1]
        assert kwargs.get('kerberos_service_name') == 'impala'


class TestValidateConnection:
    def test_expired_connection_is_invalid(self, fresh_manager):
        conn = MagicMock()
        conn._created_at = time.time() - fresh_manager._connection_timeout - 10
        assert fresh_manager._validate_connection(conn) is False

    def test_recently_used_connection_skips_ping(self, fresh_manager):
        conn = MagicMock()
        conn._created_at = time.time()
        conn._last_used = time.time()
        assert fresh_manager._validate_connection(conn) is True
        conn.cursor.assert_not_called()

    def test_idle_connection_is_pinged(self, fresh_manager):
        conn = MagicMock()
        conn._created_at = time.time()
        conn._last_used = time.time() - fresh_manager.VALIDATION_SKIP_THRESHOLD - 5
        mock_cursor = MagicMock()
        conn.cursor.return_value = mock_cursor
        assert fresh_manager._validate_connection(conn) is True
        mock_cursor.execute.assert_called_once_with("SELECT 1")

    def test_force_ping_always_pings(self, fresh_manager):
        conn = MagicMock()
        conn._created_at = time.time()
        conn._last_used = time.time()
        mock_cursor = MagicMock()
        conn.cursor.return_value = mock_cursor
        fresh_manager._validate_connection(conn, force_ping=True)
        mock_cursor.execute.assert_called_once_with("SELECT 1")

    def test_ping_exception_returns_false(self, fresh_manager):
        conn = MagicMock()
        conn._created_at = time.time()
        conn._last_used = time.time() - fresh_manager.VALIDATION_SKIP_THRESHOLD - 5
        conn.cursor.side_effect = RuntimeError('boom')
        assert fresh_manager._validate_connection(conn) is False


class TestEnsureDatabase:
    def test_returns_true_when_no_database_requested(self, fresh_manager):
        conn = MagicMock()
        assert fresh_manager._ensure_database(conn, None) is True

    def test_returns_true_when_already_correct_database(self, fresh_manager):
        conn = MagicMock()
        conn._database = 'gmp_cis'
        assert fresh_manager._ensure_database(conn, 'gmp_cis') is True
        conn.cursor.assert_not_called()

    def test_switches_database_when_different(self, fresh_manager):
        conn = MagicMock()
        conn._database = 'other_db'
        mock_cursor = MagicMock()
        conn.cursor.return_value = mock_cursor
        result = fresh_manager._ensure_database(conn, 'gmp_cis')
        assert result is True
        assert conn._database == 'gmp_cis'
        mock_cursor.execute.assert_called_once_with('USE gmp_cis')

    def test_returns_false_on_exception(self, fresh_manager):
        conn = MagicMock()
        conn._database = 'other_db'
        conn.cursor.side_effect = RuntimeError('boom')
        assert fresh_manager._ensure_database(conn, 'gmp_cis') is False


class TestGetConnectionUnavailable:
    def test_returns_none(self, fresh_manager):
        with patch('edge_jobs_py36.lib.impala_connection.IMPALA_AVAILABLE', False):
            assert fresh_manager.get_connection() is None


class TestGetConnectionFromPool:
    def test_reuses_valid_pooled_connection(self, fresh_manager, available):
        conn = MagicMock()
        conn._created_at = time.time()
        conn._last_used = time.time()
        conn._database = 'gmp_cis'
        fresh_manager._pool.put(conn)
        fresh_manager._connection_count = 1
        result = fresh_manager.get_connection('gmp_cis')
        assert result is conn

    def test_discards_stale_pooled_connection_and_creates_new(self, fresh_manager, available):
        stale = MagicMock()
        stale._created_at = time.time() - fresh_manager._connection_timeout - 10
        fresh_manager._pool.put(stale)
        fresh_manager._connection_count = 1
        new_conn = MagicMock()
        available.return_value = new_conn
        result = fresh_manager.get_connection()
        assert result is new_conn
        stale.close.assert_called_once()


class TestGetConnectionCreateNew:
    def test_creates_new_when_under_limit(self, fresh_manager, available):
        new_conn = MagicMock()
        available.return_value = new_conn
        result = fresh_manager.get_connection()
        assert result is new_conn
        assert fresh_manager._connection_count == 1

    def test_releases_slot_when_creation_fails(self, fresh_manager, available):
        available.side_effect = RuntimeError('boom')
        result = fresh_manager.get_connection()
        assert result is None
        assert fresh_manager._connection_count == 0


class TestGetConnectionPoolExhausted:
    def test_waits_and_returns_connection_from_pool(self, fresh_manager, available):
        fresh_manager._connection_count = fresh_manager._max_connections
        conn = MagicMock()
        conn._created_at = time.time()
        conn._last_used = time.time()

        def delayed_put():
            time.sleep(0.05)
            fresh_manager._pool.put(conn)

        import threading
        threading.Thread(target=delayed_put).start()
        result = fresh_manager.get_connection()
        assert result is conn

    def test_timeout_returns_none(self, fresh_manager, available):
        fresh_manager._connection_count = fresh_manager._max_connections
        with patch.object(fresh_manager._pool, 'get', side_effect=Exception()):
            from queue import Empty
            with patch.object(fresh_manager._pool, 'get', side_effect=Empty()):
                result = fresh_manager.get_connection()
        assert result is None


class TestReturnConnection:
    def test_none_connection_is_noop(self, fresh_manager):
        fresh_manager.return_connection(None)  # must not raise

    def test_puts_connection_back_in_pool(self, fresh_manager):
        conn = MagicMock()
        fresh_manager.return_connection(conn)
        assert fresh_manager._pool.qsize() == 1

    def test_closes_and_decrements_when_pool_full(self, fresh_manager):
        fresh_manager._connection_count = 1
        # fill pool to capacity
        for _ in range(fresh_manager._pool.maxsize):
            fresh_manager._pool.put(MagicMock())
        conn = MagicMock()
        fresh_manager.return_connection(conn)
        conn.close.assert_called_once()


class TestGetCursor:
    def test_yields_cursor_when_connection_available(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        available.return_value = conn
        with fresh_manager.get_cursor() as c:
            assert c is cursor

    def test_yields_none_when_no_connection(self, fresh_manager):
        with patch.object(fresh_manager, 'get_connection', return_value=None):
            with fresh_manager.get_cursor() as c:
                assert c is None

    def test_closes_cursor_and_returns_connection(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        available.return_value = conn
        with fresh_manager.get_cursor():
            pass
        cursor.close.assert_called()


class TestExecuteQuery:
    def test_returns_empty_list_when_unavailable(self, fresh_manager):
        with patch('edge_jobs_py36.lib.impala_connection.IMPALA_AVAILABLE', False):
            assert fresh_manager.execute_query('SELECT 1') == []

    def test_returns_dict_rows(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.description = [('id',), ('name',)]
        cursor.fetchall.return_value = [(1, 'A'), (2, 'B')]
        conn.cursor.return_value = cursor
        available.return_value = conn
        result = fresh_manager.execute_query('SELECT id, name FROM x')
        assert result == [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}]

    def test_returns_empty_list_when_no_cursor(self, fresh_manager):
        with patch.object(fresh_manager, 'get_connection', return_value=None):
            assert fresh_manager.execute_query('SELECT 1') == []

    def test_uses_params_when_given(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.description = [('id',)]
        cursor.fetchall.return_value = []
        conn.cursor.return_value = cursor
        available.return_value = conn
        fresh_manager.execute_query('SELECT * FROM x WHERE id=?', params=[1])
        cursor.execute.assert_called_with('SELECT * FROM x WHERE id=?', [1])

    def test_returns_empty_list_on_exception(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.execute.side_effect = RuntimeError('boom')
        conn.cursor.return_value = cursor
        available.return_value = conn
        assert fresh_manager.execute_query('SELECT 1') == []


class TestExecuteWrite:
    def test_returns_false_when_unavailable(self, fresh_manager):
        with patch('edge_jobs_py36.lib.impala_connection.IMPALA_AVAILABLE', False):
            assert fresh_manager.execute_write('DELETE FROM x') is False

    def test_returns_true_on_success_and_commits(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        available.return_value = conn
        result = fresh_manager.execute_write('DELETE FROM x')
        assert result is True
        conn.commit.assert_called_once()

    def test_returns_false_when_no_connection(self, fresh_manager):
        with patch.object(fresh_manager, 'get_connection', return_value=None):
            assert fresh_manager.execute_write('DELETE FROM x') is False

    def test_rolls_back_and_returns_false_on_exception(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.execute.side_effect = RuntimeError('boom')
        conn.cursor.return_value = cursor
        available.return_value = conn
        result = fresh_manager.execute_write('DELETE FROM x')
        assert result is False
        conn.rollback.assert_called_once()

    def test_uses_params_when_given(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        available.return_value = conn
        fresh_manager.execute_write('DELETE FROM x WHERE id=?', params=[1])
        cursor.execute.assert_called_with('DELETE FROM x WHERE id=?', [1])


class TestTestConnection:
    def test_returns_false_when_unavailable(self, fresh_manager):
        with patch('edge_jobs_py36.lib.impala_connection.IMPALA_AVAILABLE', False):
            assert fresh_manager.test_connection() is False

    def test_returns_true_on_success(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        conn.cursor.return_value = cursor
        available.return_value = conn
        assert fresh_manager.test_connection() is True

    def test_returns_false_on_exception(self, fresh_manager, available):
        with patch.object(fresh_manager, 'get_cursor', side_effect=RuntimeError('boom')):
            assert fresh_manager.test_connection() is False


class TestGetTables:
    def test_returns_table_names(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = [('cis_trade',), ('cis_portfolio',)]
        conn.cursor.return_value = cursor
        available.return_value = conn
        assert fresh_manager.get_tables() == ['cis_trade', 'cis_portfolio']

    def test_returns_empty_list_when_no_cursor(self, fresh_manager):
        with patch.object(fresh_manager, 'get_connection', return_value=None):
            assert fresh_manager.get_tables() == []

    def test_returns_empty_list_on_exception(self, fresh_manager, available):
        with patch.object(fresh_manager, 'get_cursor', side_effect=RuntimeError('boom')):
            assert fresh_manager.get_tables() == []


class TestDescribeTable:
    def test_returns_column_dicts(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.description = [('name',), ('type',)]
        cursor.fetchall.return_value = [('id', 'bigint')]
        conn.cursor.return_value = cursor
        available.return_value = conn
        result = fresh_manager.describe_table('cis_trade')
        assert result == [{'name': 'id', 'type': 'bigint'}]

    def test_returns_empty_list_on_exception(self, fresh_manager, available):
        with patch.object(fresh_manager, 'get_cursor', side_effect=RuntimeError('boom')):
            assert fresh_manager.describe_table('cis_trade') == []


class TestAsyncWrites:
    def test_execute_write_async_queues_and_runs(self, fresh_manager, available):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        available.return_value = conn
        callback_result = []
        fresh_manager.execute_write_async('DELETE FROM x', callback=lambda s: callback_result.append(s))
        fresh_manager.wait_for_async_writes(timeout=5)
        assert callback_result == [True]

    def test_get_async_queue_size_reflects_pending(self, fresh_manager, available):
        conn = MagicMock()
        available.return_value = conn
        fresh_manager.execute_write_async('DELETE FROM x')
        fresh_manager.wait_for_async_writes(timeout=5)
        assert fresh_manager.get_async_queue_size() == 0

    def test_wait_for_async_writes_returns_completed_count(self, fresh_manager, available):
        conn = MagicMock()
        available.return_value = conn
        fresh_manager.execute_write_async('DELETE FROM x')
        completed = fresh_manager.wait_for_async_writes(timeout=5)
        assert completed == 1

    def test_submit_failure_falls_back_to_sync(self, fresh_manager, available):
        conn = MagicMock()
        available.return_value = conn
        with patch.object(fresh_manager._async_executor, 'submit', side_effect=RuntimeError('boom')), \
             patch.object(fresh_manager, 'execute_write') as mock_sync:
            fresh_manager.execute_write_async('DELETE FROM x')
        mock_sync.assert_called_once()


class TestPoolStatsAndRecycling:
    def test_get_pool_stats_returns_expected_keys(self, fresh_manager):
        stats = fresh_manager.get_pool_stats()
        assert 'pool_size' in stats
        assert 'active_connections' in stats
        assert 'pool_utilization_pct' in stats

    def test_log_pool_stats_does_not_raise(self, fresh_manager):
        fresh_manager.log_pool_stats()

    def test_reset_stats_zeroes_counters(self, fresh_manager):
        ImpalaConnectionManager._connection_reuse_count = 5
        fresh_manager.reset_stats()
        assert ImpalaConnectionManager._connection_reuse_count == 0

    def test_recycle_idle_connections_closes_old_ones(self, fresh_manager):
        old_conn = MagicMock()
        old_conn._last_used = time.time() - 1000
        fresh_manager._pool.put(old_conn)
        fresh_manager._connection_count = 1
        recycled = fresh_manager.recycle_idle_connections(max_idle_seconds=300)
        assert recycled == 1
        old_conn.close.assert_called_once()

    def test_recycle_idle_connections_keeps_fresh_ones(self, fresh_manager):
        fresh_conn = MagicMock()
        fresh_conn._last_used = time.time()
        fresh_manager._pool.put(fresh_conn)
        recycled = fresh_manager.recycle_idle_connections(max_idle_seconds=300)
        assert recycled == 0
        assert fresh_manager._pool.qsize() == 1


class TestQueryCacheSingleton:
    def test_returns_same_instance(self):
        a = QueryCache()
        b = QueryCache()
        assert a is b

    def test_module_exposes_singleton(self):
        assert isinstance(query_cache, QueryCache)


class TestQueryCacheOperations:
    def test_set_and_get(self):
        cache = QueryCache()
        cache.set('k1', 'value1', ttl=100)
        assert cache.get('k1') == 'value1'
        cache.invalidate('k1')

    def test_get_missing_key_returns_none(self):
        cache = QueryCache()
        assert cache.get('nonexistent-key-xyz') is None

    def test_expired_entry_returns_none_and_is_removed(self):
        cache = QueryCache()
        cache.set('k2', 'value2', ttl=-1)
        assert cache.get('k2') is None
        assert 'k2' not in cache._cache

    def test_invalidate_removes_key(self):
        cache = QueryCache()
        cache.set('k3', 'value3', ttl=100)
        cache.invalidate('k3')
        assert cache.get('k3') is None

    def test_invalidate_missing_key_is_noop(self):
        cache = QueryCache()
        cache.invalidate('never-set-key')  # must not raise

    def test_invalidate_pattern_removes_matching_keys(self):
        cache = QueryCache()
        cache.set('portfolios:all', 'v1', ttl=100)
        cache.set('portfolios:search:x', 'v2', ttl=100)
        cache.set('securities:all', 'v3', ttl=100)
        removed = cache.invalidate_pattern('portfolios:')
        assert removed == 2
        assert cache.get('securities:all') == 'v3'
        cache.invalidate('securities:all')

    def test_clear_empties_cache(self):
        cache = QueryCache()
        cache.set('k4', 'v', ttl=100)
        cache.clear()
        assert cache.get('k4') is None

    def test_get_stats_reports_valid_and_expired(self):
        cache = QueryCache()
        cache.clear()
        cache.set('valid-key', 'v', ttl=100)
        cache._cache['expired-key'] = ('v', time.time() - 1)
        stats = cache.get_stats()
        assert stats['total_keys'] == 2
        assert stats['valid_keys'] == 1
        assert stats['expired_keys'] == 1
        cache.clear()

    def test_default_ttl_used_when_none_given(self):
        cache = QueryCache()
        cache.set('k5', 'v')
        _, expiry = cache._cache['k5']
        assert expiry - time.time() > 200  # close to default 300s
        cache.invalidate('k5')
