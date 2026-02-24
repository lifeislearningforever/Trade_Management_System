"""
Hive/Impala Configuration (Kerberos + SSL)
==========================================

All values can be overridden via environment variables.

Connection settings based on working Cloudera DataViz 7.2.9 config:
- Connection mode: Binary
- Socket type: SSL
- Authentication: Kerberos (GSSAPI)
- Kerberos service name: hive
- Execution engine: Tez (for fast writes)

Environment Variables:
    HIVE_POC_HOST          - HiveServer2 host
    HIVE_POC_PORT          - HiveServer2 port (default: 10000)
    HIVE_POC_DATABASE      - Database name
    HIVE_POC_AUTH_MECHANISM - Authentication (GSSAPI, NOSASL, PLAIN)
    HIVE_POC_KERBEROS_SERVICE_NAME - Kerberos service name
    HIVE_POC_USE_SSL       - Enable SSL (true/false)
    HIVE_POC_TIMEOUT       - Connection timeout in seconds
    HIVE_POC_EXECUTION_ENGINE - Hive execution engine (tez, mr)
"""

import os
from typing import Optional

# =============================================================================
# Helper Functions
# =============================================================================

def _to_bool(value: Optional[str], default: bool = True) -> bool:
    """Convert string to boolean."""
    if value is None:
        return default
    return str(value).lower() in ('1', 'true', 'yes', 'y')


# =============================================================================
# Core Connection Settings
# =============================================================================

HIVE_POC_CONFIG = {
    # Server & SSL
    'HOST': os.environ.get('HIVE_POC_HOST', 'lxmrwtsgv0m2.sg.uobnet.com'),
    'PORT': int(os.environ.get('HIVE_POC_PORT', '10000')),
    'DATABASE': os.environ.get('HIVE_POC_DATABASE', 'mrw_ima'),

    # Security/Authentication
    'AUTH_MECHANISM': os.environ.get('HIVE_POC_AUTH_MECHANISM', 'GSSAPI'),
    'KERBEROS_SERVICE_NAME': os.environ.get('HIVE_POC_KERBEROS_SERVICE_NAME', 'hive'),
    'USE_SSL': _to_bool(os.environ.get('HIVE_POC_USE_SSL'), default=True),

    # Timeouts
    'TIMEOUT': int(os.environ.get('HIVE_POC_TIMEOUT', '300')),

    # Optional: CA bundle path
    # Leave empty/None to skip SSL cert validation; raises on invalid config
    'CA_CERT': os.environ.get('HIVE_POC_CA_CERT', '') or None,

    # Optional: Initial Hive session properties to apply AFTER cursor creation
    # If your platform defines HIVE_POC_INIT_STMTS, it is here already, you can reset this to []
    'INIT_STATEMENTS': [
        # Set execution engine to Tez for faster operations
        "SET hive.execution.engine=tez",
        # Add other safe session flags if your cluster supports them, e.g.:
        # "SET hive.vectorized.execution.enabled=true",
        # "SET hive.vectorized.execution.reduce.enabled=true",
    ],

    # Defensive switch: if True, any attempt to set MR will be rewritten to Tez
    'ALWAYS_USE_TEZ': _to_bool(os.environ.get('HIVE_POC_ALWAYS_USE_TEZ'), default=True),
}


# =============================================================================
# Connection Pool Settings
# =============================================================================

HIVE_POC_POOL_CONFIG = {
    # Pool size
    'POOL_SIZE': int(os.environ.get('HIVE_POC_POOL_SIZE', '10')),
    'POOL_MIN_SIZE': int(os.environ.get('HIVE_POC_POOL_MIN_SIZE', '2')),

    # Connection age-out (seconds) - connections older than this are closed
    'CONNECTION_MAX_AGE': int(os.environ.get('HIVE_POC_CONNECTION_MAX_AGE', '3600')),  # 1 hour

    # Connection validation interval (seconds)
    'VALIDATION_INTERVAL': int(os.environ.get('HIVE_POC_VALIDATION_INTERVAL', '60')),

    # Connection acquire timeout (seconds)
    'ACQUIRE_TIMEOUT': int(os.environ.get('HIVE_POC_ACQUIRE_TIMEOUT', '30')),

    # Retry settings for failed connections
    'RETRY_COUNT': int(os.environ.get('HIVE_POC_RETRY_COUNT', '3')),
    'RETRY_DELAY': float(os.environ.get('HIVE_POC_RETRY_DELAY', '1.0')),

    # Pre-warm connections on startup
    'PRE_WARM': _to_bool(os.environ.get('HIVE_POC_PRE_WARM'), default=True),
}


# =============================================================================
# Performance Optimization Settings
# =============================================================================

HIVE_POC_PERFORMANCE_CONFIG = {
    # Execution engine (tez is faster than mr for most operations)
    'EXECUTION_ENGINE': os.environ.get('HIVE_POC_EXECUTION_ENGINE', 'tez'),

    # Batch operations
    'BATCH_SIZE': int(os.environ.get('HIVE_POC_BATCH_SIZE', '100')),

    # Async write settings
    'ASYNC_WORKERS': int(os.environ.get('HIVE_POC_ASYNC_WORKERS', '5')),
    'ASYNC_QUEUE_SIZE': int(os.environ.get('HIVE_POC_ASYNC_QUEUE_SIZE', '100')),

    # Query optimization flags (applied via SET statements)
    'OPTIMIZATION_FLAGS': {
        'hive.execution.engine': 'tez',
        'hive.tez.auto.reducer.parallelism': 'true',
        'hive.vectorized.execution.enabled': 'true',
        'hive.cbo.enable': 'true',
        'hive.compute.query.using.stats': 'true',
        'hive.stats.fetch.column.stats': 'true',
        'hive.stats.fetch.partition.stats': 'true',
    },
}


# =============================================================================
# Impala Read Configuration (for fast reads)
# =============================================================================

IMPALA_READ_CONFIG = {
    'HOST': os.environ.get('IMPALA_HOST', os.environ.get('HIVE_POC_HOST', 'lxmrwtsgv0m2.sg.uobnet.com')),
    'PORT': int(os.environ.get('IMPALA_PORT', '21050')),
    'DATABASE': os.environ.get('IMPALA_DATABASE', os.environ.get('HIVE_POC_DATABASE', 'mrw_ima')),
    'AUTH_MECHANISM': os.environ.get('IMPALA_AUTH_MECHANISM', 'GSSAPI'),
    'KERBEROS_SERVICE_NAME': os.environ.get('IMPALA_KERBEROS_SERVICE_NAME', 'impala'),
    'USE_SSL': _to_bool(os.environ.get('IMPALA_USE_SSL'), default=True),
    'TIMEOUT': int(os.environ.get('IMPALA_TIMEOUT', '120')),
    'POOL_SIZE': int(os.environ.get('IMPALA_POOL_SIZE', '10')),
}


# =============================================================================
# Logging Configuration
# =============================================================================

HIVE_POC_LOGGING = {
    'LOG_QUERIES': _to_bool(os.environ.get('HIVE_POC_LOG_QUERIES'), default=False),
    'LOG_SLOW_QUERIES': _to_bool(os.environ.get('HIVE_POC_LOG_SLOW_QUERIES'), default=True),
    'SLOW_QUERY_THRESHOLD_MS': int(os.environ.get('HIVE_POC_SLOW_QUERY_THRESHOLD_MS', '5000')),
}


# =============================================================================
# Convenience function to get full config
# =============================================================================

def get_hive_config() -> dict:
    """Get complete Hive configuration."""
    return {
        'connection': HIVE_POC_CONFIG,
        'pool': HIVE_POC_POOL_CONFIG,
        'performance': HIVE_POC_PERFORMANCE_CONFIG,
        'impala': IMPALA_READ_CONFIG,
        'logging': HIVE_POC_LOGGING,
    }


def get_impala_connect_kwargs(database: str = None) -> dict:
    """Get kwargs for impyla connect() for Impala reads."""
    config = IMPALA_READ_CONFIG
    db_name = database or config['DATABASE']

    kwargs = {
        'host': config['HOST'],
        'port': config['PORT'],
        'database': db_name,
        'auth_mechanism': config['AUTH_MECHANISM'],
        'timeout': config['TIMEOUT'],
    }

    # Kerberos
    if config['AUTH_MECHANISM'] == 'GSSAPI':
        kwargs['kerberos_service_name'] = config['KERBEROS_SERVICE_NAME']

    # SSL
    if config['USE_SSL']:
        kwargs['use_ssl'] = True

    return kwargs


def get_hive_connect_kwargs(database: str = None) -> dict:
    """Get kwargs for impyla connect() for Hive writes."""
    config = HIVE_POC_CONFIG
    db_name = database or config['DATABASE']

    kwargs = {
        'host': config['HOST'],
        'port': config['PORT'],
        'database': db_name,
        'auth_mechanism': config['AUTH_MECHANISM'],
        'timeout': config['TIMEOUT'],
    }

    # Kerberos
    if config['AUTH_MECHANISM'] == 'GSSAPI':
        kwargs['kerberos_service_name'] = config['KERBEROS_SERVICE_NAME']

    # SSL
    if config['USE_SSL']:
        kwargs['use_ssl'] = True

    # Optional CA certificate
    if config.get('CA_CERT'):
        kwargs['ca_cert'] = config['CA_CERT']

    return kwargs
