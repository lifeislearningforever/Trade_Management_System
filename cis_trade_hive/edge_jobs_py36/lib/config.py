"""
Django-free stand-in for django.conf.settings, used by every forked
repository/service in this package.

Wraps config.environments (already Django-free -- see lib/__init__.py,
which puts the project root on sys.path before this module's own imports
run) and replicates the small amount of override logic that
config/settings.py itself layers on top of it (env var overrides win over
the per-CIS_ENV defaults baked into config/environments.py).

This is a deliberate duplication of settings.py's override block, not a
shared import, because settings.py itself requires django.conf and the
rest of INSTALLED_APPS to import. Keep it in sync by hand if that block
in config/settings.py changes.
"""
import os

from . import _PROJECT_ROOT  # noqa: F401  (import order: ensures sys.path bootstrap ran)
import config.environments as _env_module


class _Settings:
    """Minimal attribute-style settings object, mirroring the subset of
    django.conf.settings actually used by the forked repositories/services
    in this package: IMPALA_CONFIG, IMPALA_POOL_SIZE, BASE_DIR."""

    def __init__(self):
        self.BASE_DIR = _PROJECT_ROOT

        impala_config = _env_module.IMPALA_CONFIG.copy()

        # Mirror config/settings.py: env var wins over the per-CIS_ENV default.
        _use_ssl_env = os.environ.get('IMPALA_USE_SSL', '').lower()
        if _use_ssl_env:
            impala_config['USE_SSL'] = _use_ssl_env == 'true'
        _impala_host_env = os.environ.get('IMPALA_HOST', '')
        if _impala_host_env:
            impala_config['HOST'] = _impala_host_env
        _impala_port_env = os.environ.get('IMPALA_PORT', '')
        if _impala_port_env:
            impala_config['PORT'] = int(_impala_port_env)
        _impala_auth_env = os.environ.get('IMPALA_AUTH', '')
        if _impala_auth_env:
            impala_config['AUTH'] = _impala_auth_env
            impala_config['AUTH_MECHANISM'] = _impala_auth_env

        self.IMPALA_CONFIG = impala_config
        self.IMPALA_POOL_SIZE = impala_config.get('POOL_SIZE', 10)


settings = _Settings()
