"""Tests for edge_jobs_py36/lib/cache.py."""
import time
import threading

from edge_jobs_py36.lib.cache import _SimpleTTLCache, cache


class TestGetSet:
    def test_get_missing_key_returns_none_by_default(self):
        c = _SimpleTTLCache()
        assert c.get('missing') is None

    def test_get_missing_key_returns_custom_default(self):
        c = _SimpleTTLCache()
        assert c.get('missing', 'fallback') == 'fallback'

    def test_set_then_get_returns_value(self):
        c = _SimpleTTLCache()
        c.set('k', 'v')
        assert c.get('k') == 'v'

    def test_set_overwrites_existing_value(self):
        c = _SimpleTTLCache()
        c.set('k', 'v1')
        c.set('k', 'v2')
        assert c.get('k') == 'v2'

    def test_set_with_none_timeout_never_expires(self):
        c = _SimpleTTLCache()
        c.set('k', 'v', timeout=None)
        # far-future check without sleeping: patch time indirectly by
        # asserting the stored expiry is None
        assert c._store['k'] == ('v', None)
        assert c.get('k') == 'v'

    def test_set_default_timeout_is_300(self):
        c = _SimpleTTLCache()
        before = time.time()
        c.set('k', 'v')
        _, expires_at = c._store['k']
        assert 299 <= expires_at - before <= 301

    def test_expired_entry_returns_default_and_is_evicted(self):
        c = _SimpleTTLCache()
        c.set('k', 'v', timeout=-1)  # already expired
        assert c.get('k') is None
        assert 'k' not in c._store

    def test_expired_entry_with_custom_default(self):
        c = _SimpleTTLCache()
        c.set('k', 'v', timeout=-1)
        assert c.get('k', 'fallback') == 'fallback'

    def test_not_yet_expired_entry_is_returned(self):
        c = _SimpleTTLCache()
        c.set('k', 'v', timeout=1000)
        assert c.get('k') == 'v'

    def test_stores_falsy_values_correctly(self):
        c = _SimpleTTLCache()
        c.set('zero', 0)
        c.set('empty', '')
        c.set('false', False)
        assert c.get('zero') == 0
        assert c.get('empty') == ''
        assert c.get('false') is False

    def test_stores_none_value_returns_none_not_default(self):
        """Storing None as a value is distinct from a missing key: the
        entry tuple (None, expires_at) is not None itself, so get()
        returns the stored None rather than falling back to default."""
        c = _SimpleTTLCache()
        c.set('k', None)
        assert c.get('k', 'fallback') is None


class TestDelete:
    def test_delete_removes_key(self):
        c = _SimpleTTLCache()
        c.set('k', 'v')
        c.delete('k')
        assert c.get('k') is None

    def test_delete_missing_key_does_not_raise(self):
        c = _SimpleTTLCache()
        c.delete('never-set')  # should not raise

    def test_delete_then_reset_works(self):
        c = _SimpleTTLCache()
        c.set('k', 'v1')
        c.delete('k')
        c.set('k', 'v2')
        assert c.get('k') == 'v2'


class TestThreadSafety:
    def test_concurrent_sets_do_not_corrupt_store(self):
        c = _SimpleTTLCache()

        def writer(n):
            for i in range(50):
                c.set('k{}'.format(n), i)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for n in range(8):
            assert c.get('k{}'.format(n)) == 49


class TestModuleLevelSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(cache, _SimpleTTLCache)

    def test_singleton_get_set_delete_roundtrip(self):
        cache.set('singleton-test-key', 'value')
        assert cache.get('singleton-test-key') == 'value'
        cache.delete('singleton-test-key')
        assert cache.get('singleton-test-key') is None
