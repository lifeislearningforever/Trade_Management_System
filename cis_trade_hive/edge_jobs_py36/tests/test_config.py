"""Tests for edge_jobs_py36/lib/config.py."""
from unittest.mock import patch

from edge_jobs_py36.lib.config import _Settings, settings, _PROJECT_ROOT


BASE_IMPALA_CONFIG = {
    'HOST': 'lxmrwtsgyodt1.sg.uobnet.com',
    'PORT': 21050,
    'DATABASE': 'gmp_cis',
    'AUTH': 'GSSAPI',
    'AUTH_MECHANISM': 'GSSAPI',
    'USE_SSL': True,
    'KERBEROS_SERVICE_NAME': 'impala',
    'TIMEOUT': 60,
    'POOL_SIZE': 10,
}


def _patched_env_module():
    """Build a stand-in for config.environments with a copyable IMPALA_CONFIG."""
    class _Env:
        IMPALA_CONFIG = dict(BASE_IMPALA_CONFIG)
    return _Env()


class TestSettingsBaseDir:
    def test_base_dir_is_project_root(self):
        with patch.dict('os.environ', {}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.BASE_DIR == _PROJECT_ROOT


class TestSettingsNoOverrides:
    def test_no_env_overrides_uses_defaults_from_environments_module(self):
        with patch.dict('os.environ', {}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['HOST'] == 'lxmrwtsgyodt1.sg.uobnet.com'
        assert s.IMPALA_CONFIG['PORT'] == 21050
        assert s.IMPALA_CONFIG['USE_SSL'] is True
        assert s.IMPALA_CONFIG['AUTH'] == 'GSSAPI'

    def test_pool_size_defaults_from_impala_config(self):
        with patch.dict('os.environ', {}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_POOL_SIZE == 10

    def test_pool_size_falls_back_to_10_when_absent_from_config(self):
        env = _patched_env_module()
        del env.IMPALA_CONFIG['POOL_SIZE']
        with patch.dict('os.environ', {}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', env):
            s = _Settings()
        assert s.IMPALA_POOL_SIZE == 10

    def test_does_not_mutate_the_environments_module_config(self):
        """_Settings.__init__ copies IMPALA_CONFIG before mutating it."""
        env = _patched_env_module()
        original = dict(env.IMPALA_CONFIG)
        with patch.dict('os.environ', {'IMPALA_HOST': 'overridden-host'}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', env):
            _Settings()
        assert env.IMPALA_CONFIG == original


class TestUseSslOverride:
    def test_use_ssl_env_true_overrides_to_true(self):
        with patch.dict('os.environ', {'IMPALA_USE_SSL': 'true'}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['USE_SSL'] is True

    def test_use_ssl_env_false_overrides_to_false(self):
        with patch.dict('os.environ', {'IMPALA_USE_SSL': 'false'}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['USE_SSL'] is False

    def test_use_ssl_env_is_case_insensitive(self):
        with patch.dict('os.environ', {'IMPALA_USE_SSL': 'TRUE'}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['USE_SSL'] is True

    def test_use_ssl_env_unset_keeps_default(self):
        with patch.dict('os.environ', {}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['USE_SSL'] is True

    def test_use_ssl_env_empty_string_keeps_default(self):
        with patch.dict('os.environ', {'IMPALA_USE_SSL': ''}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['USE_SSL'] is True


class TestHostOverride:
    def test_host_env_overrides_default(self):
        with patch.dict('os.environ', {'IMPALA_HOST': 'custom-host.example.com'}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['HOST'] == 'custom-host.example.com'

    def test_host_env_unset_keeps_default(self):
        with patch.dict('os.environ', {}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['HOST'] == 'lxmrwtsgyodt1.sg.uobnet.com'

    def test_host_env_empty_string_keeps_default(self):
        with patch.dict('os.environ', {'IMPALA_HOST': ''}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['HOST'] == 'lxmrwtsgyodt1.sg.uobnet.com'


class TestPortOverride:
    def test_port_env_overrides_default_as_int(self):
        with patch.dict('os.environ', {'IMPALA_PORT': '9999'}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['PORT'] == 9999
        assert isinstance(s.IMPALA_CONFIG['PORT'], int)

    def test_port_env_unset_keeps_default(self):
        with patch.dict('os.environ', {}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['PORT'] == 21050

    def test_port_env_empty_string_keeps_default(self):
        with patch.dict('os.environ', {'IMPALA_PORT': ''}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['PORT'] == 21050


class TestAuthOverride:
    def test_auth_env_overrides_both_auth_keys(self):
        with patch.dict('os.environ', {'IMPALA_AUTH': 'NOSASL'}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['AUTH'] == 'NOSASL'
        assert s.IMPALA_CONFIG['AUTH_MECHANISM'] == 'NOSASL'

    def test_auth_env_unset_keeps_default(self):
        with patch.dict('os.environ', {}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['AUTH'] == 'GSSAPI'
        assert s.IMPALA_CONFIG['AUTH_MECHANISM'] == 'GSSAPI'

    def test_auth_env_empty_string_keeps_default(self):
        with patch.dict('os.environ', {'IMPALA_AUTH': ''}, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['AUTH'] == 'GSSAPI'


class TestAllOverridesCombined:
    def test_all_overrides_applied_together(self):
        env_vars = {
            'IMPALA_USE_SSL': 'false',
            'IMPALA_HOST': 'combo-host',
            'IMPALA_PORT': '12345',
            'IMPALA_AUTH': 'LDAP',
        }
        with patch.dict('os.environ', env_vars, clear=True), \
             patch('edge_jobs_py36.lib.config._env_module', _patched_env_module()):
            s = _Settings()
        assert s.IMPALA_CONFIG['USE_SSL'] is False
        assert s.IMPALA_CONFIG['HOST'] == 'combo-host'
        assert s.IMPALA_CONFIG['PORT'] == 12345
        assert s.IMPALA_CONFIG['AUTH'] == 'LDAP'
        assert s.IMPALA_CONFIG['AUTH_MECHANISM'] == 'LDAP'
        assert s.IMPALA_POOL_SIZE == 10  # unaffected, no POOL_SIZE override path


class TestModuleLevelSingleton:
    def test_settings_singleton_is_settings_instance(self):
        assert isinstance(settings, _Settings)

    def test_settings_singleton_has_impala_config(self):
        assert 'HOST' in settings.IMPALA_CONFIG
        assert 'PORT' in settings.IMPALA_CONFIG

    def test_settings_singleton_has_base_dir(self):
        assert settings.BASE_DIR == _PROJECT_ROOT

    def test_settings_singleton_has_pool_size(self):
        assert isinstance(settings.IMPALA_POOL_SIZE, int)
