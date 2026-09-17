"""
Environment Configuration for CIS Trade Hive

Supported Environments:
- LOCAL: Local development with Docker Kudu/Impala (No Kerberos)
- SIT: System Integration Testing (Cloudera with Kerberos)
- UAT: User Acceptance Testing (Cloudera with Kerberos)
- PROD: Production (Cloudera with Kerberos)
- DR: Disaster Recovery (Cloudera with Kerberos)

Usage:
    from config.environments import get_environment_config, ENV_CONFIG

    # Get current environment config
    config = get_environment_config()
    print(config['IMPALA_HOST'])
"""

import os

# ============================================================================
# Environment Detection
# ============================================================================

# Set CIS_ENV='SIT' for CML/Cloudera, defaults to 'LOCAL' for development
# Convert to uppercase to handle case-insensitivity
CIS_ENV = os.environ.get('CIS_ENV', 'LOCAL').upper()

# Plain-text override for the Impala/Kudu database name -- lets ops retarget
# the app (e.g. gmp_cis -> gmp_cis_dev) by editing a file on the gateway host
# instead of having to set an environment variable. One name per line, blank
# lines/lines starting with # ignored. IMPALA_DB env var still wins if set.
_DATABASE_TXT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.txt')


def _resolve_database(env_var: str, default: str) -> str:
    env_val = os.environ.get(env_var)
    if env_val:
        return env_val
    try:
        with open(_DATABASE_TXT_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    return line
    except FileNotFoundError:
        pass
    return default


# ============================================================================
# IMPALA Configuration (for FAST READS)
# ============================================================================
# Connection: impala-shell -i <host>:21050

if CIS_ENV == 'SIT':
    # SIT - System Integration Testing (TST.UOBNET.COM)
    IMPALA_CONFIG = {
        'HOST': os.environ.get('IMPALA_HOST', 'lxmrwtsgyodt1.sg.uobnet.com'),
        'PORT': int(os.environ.get('IMPALA_PORT', '21050')),
        'DATABASE': _resolve_database('IMPALA_DB', 'gmp_cis'),
        'AUTH': os.environ.get('IMPALA_AUTH', 'GSSAPI'),  # Used by hybrid_connection.py
        'AUTH_MECHANISM': os.environ.get('IMPALA_AUTH', 'GSSAPI'),  # Used by impala_connection.py
        'USE_SSL': os.environ.get('IMPALA_USE_SSL', 'true').lower() == 'true',
        # Check both KRB_SERVICE_NAME and IMPALA_KRB_SERVICE_NAME for compatibility with .env
        'KERBEROS_SERVICE_NAME': os.environ.get('IMPALA_KRB_SERVICE_NAME', os.environ.get('KRB_SERVICE_NAME', 'impala')),
        'TIMEOUT': int(os.environ.get('IMPALA_TIMEOUT', '60')),
        'POOL_SIZE': int(os.environ.get('IMPALA_POOL_SIZE', '10')),
    }
elif CIS_ENV == 'UAT':
    # UAT - User Acceptance Testing (SG.UOBNET.COM)
    IMPALA_CONFIG = {
        'HOST': os.environ.get('IMPALA_HOST', 'lxmrwtsgvqk2.sg.uobnet.com'),
        'PORT': int(os.environ.get('IMPALA_PORT', '21050')),
        'DATABASE': _resolve_database('IMPALA_DB', 'gmp_cis'),
        'AUTH': os.environ.get('IMPALA_AUTH', 'GSSAPI'),
        'AUTH_MECHANISM': os.environ.get('IMPALA_AUTH', 'GSSAPI'),
        'USE_SSL': os.environ.get('IMPALA_USE_SSL', 'true').lower() == 'true',
        'KERBEROS_SERVICE_NAME': os.environ.get('IMPALA_KRB_SERVICE_NAME', os.environ.get('KRB_SERVICE_NAME', 'impala')),
        'TIMEOUT': int(os.environ.get('IMPALA_TIMEOUT', '60')),
        'POOL_SIZE': int(os.environ.get('IMPALA_POOL_SIZE', '10')),
    }
elif CIS_ENV == 'PROD':
    # PROD - Production (SG.UOBNET.COM)
    IMPALA_CONFIG = {
        'HOST': os.environ.get('IMPALA_HOST', 'lxmrwtsgvqk2.sg.uobnet.com'),
        'PORT': int(os.environ.get('IMPALA_PORT', '21050')),
        'DATABASE': _resolve_database('IMPALA_DB', 'gmp_cis'),
        'AUTH': os.environ.get('IMPALA_AUTH', 'GSSAPI'),
        'AUTH_MECHANISM': os.environ.get('IMPALA_AUTH', 'GSSAPI'),
        'USE_SSL': os.environ.get('IMPALA_USE_SSL', 'true').lower() == 'true',
        'KERBEROS_SERVICE_NAME': os.environ.get('IMPALA_KRB_SERVICE_NAME', os.environ.get('KRB_SERVICE_NAME', 'impala')),
        'TIMEOUT': int(os.environ.get('IMPALA_TIMEOUT', '60')),
        'POOL_SIZE': int(os.environ.get('IMPALA_POOL_SIZE', '10')),
    }
elif CIS_ENV == 'DR':
    # DR - Disaster Recovery (SG.UOBNET.COM)
    IMPALA_CONFIG = {
        'HOST': os.environ.get('IMPALA_HOST', 'lxmrwtsgvqk2.sg.uobnet.com'),
        'PORT': int(os.environ.get('IMPALA_PORT', '21050')),
        'DATABASE': _resolve_database('IMPALA_DB', 'gmp_cis'),
        'AUTH': os.environ.get('IMPALA_AUTH', 'GSSAPI'),
        'AUTH_MECHANISM': os.environ.get('IMPALA_AUTH', 'GSSAPI'),
        'USE_SSL': os.environ.get('IMPALA_USE_SSL', 'true').lower() == 'true',
        'KERBEROS_SERVICE_NAME': os.environ.get('IMPALA_KRB_SERVICE_NAME', os.environ.get('KRB_SERVICE_NAME', 'impala')),
        'TIMEOUT': int(os.environ.get('IMPALA_TIMEOUT', '60')),
        'POOL_SIZE': int(os.environ.get('IMPALA_POOL_SIZE', '10')),
    }
else:
    # LOCAL Development Configuration (No Kerberos)
    IMPALA_CONFIG = {
        'HOST': os.environ.get('IMPALA_HOST', 'localhost'),
        'PORT': int(os.environ.get('IMPALA_PORT', '21050')),
        'DATABASE': _resolve_database('IMPALA_DB', 'gmp_cis'),
        'AUTH': os.environ.get('IMPALA_AUTH', 'NOSASL'),
        'AUTH_MECHANISM': os.environ.get('IMPALA_AUTH', 'NOSASL'),
        'USE_SSL': False,
        'KERBEROS_SERVICE_NAME': None,
        'TIMEOUT': int(os.environ.get('IMPALA_TIMEOUT', '60')),
        'POOL_SIZE': int(os.environ.get('IMPALA_POOL_SIZE', '10')),
    }

# ============================================================================
# HIVE Configuration (for ACID WRITES - INSERT, UPDATE, DELETE)
# ============================================================================
# Connection: beeline -u 'jdbc:hive2://<host>:10000/;principal=hive/_HOST@REALM'

if CIS_ENV == 'SIT':
    # SIT - System Integration Testing
    HIVE_CONFIG = {
        'HOST': os.environ.get('HIVE_HOST', 'lxmrwtsgvqk2.sg.uobnet.com'),
        'PORT': int(os.environ.get('HIVE_PORT', '10000')),
        'DATABASE': os.environ.get('HIVE_DB', 'mrw_ima'),
        'AUTH': os.environ.get('HIVE_AUTH', 'GSSAPI'),
        'TIMEOUT': int(os.environ.get('HIVE_TIMEOUT', '300')),
        'POOL_SIZE': int(os.environ.get('HIVE_POOL_SIZE', '10')),
        'KERBEROS_SERVICE_NAME': os.environ.get('HIVE_KERBEROS_SERVICE_NAME', 'hive'),
        'USE_SSL': os.environ.get('HIVE_USE_SSL', 'true').lower() == 'true',
        'CA_CERT': os.environ.get('HIVE_POC_CA_CERT', '') or None,
    }
elif CIS_ENV == 'UAT':
    # UAT - User Acceptance Testing
    HIVE_CONFIG = {
        'HOST': os.environ.get('HIVE_HOST', 'lxmrwtsgvqk2.sg.uobnet.com'),
        'PORT': int(os.environ.get('HIVE_PORT', '10000')),
        'DATABASE': os.environ.get('HIVE_DB', 'mrw_ima'),
        'AUTH': os.environ.get('HIVE_AUTH', 'GSSAPI'),
        'TIMEOUT': int(os.environ.get('HIVE_TIMEOUT', '300')),
        'POOL_SIZE': int(os.environ.get('HIVE_POOL_SIZE', '10')),
        'KERBEROS_SERVICE_NAME': os.environ.get('HIVE_KERBEROS_SERVICE_NAME', 'hive'),
        'USE_SSL': os.environ.get('HIVE_USE_SSL', 'true').lower() == 'true',
        'CA_CERT': os.environ.get('HIVE_POC_CA_CERT', '') or None,
    }
elif CIS_ENV == 'PROD':
    # PROD - Production
    HIVE_CONFIG = {
        'HOST': os.environ.get('HIVE_HOST', 'lxmrwtsgvqk2.sg.uobnet.com'),
        'PORT': int(os.environ.get('HIVE_PORT', '10000')),
        'DATABASE': os.environ.get('HIVE_DB', 'mrw_ima'),
        'AUTH': os.environ.get('HIVE_AUTH', 'GSSAPI'),
        'TIMEOUT': int(os.environ.get('HIVE_TIMEOUT', '300')),
        'POOL_SIZE': int(os.environ.get('HIVE_POOL_SIZE', '10')),
        'KERBEROS_SERVICE_NAME': os.environ.get('HIVE_KERBEROS_SERVICE_NAME', 'hive'),
        'USE_SSL': os.environ.get('HIVE_USE_SSL', 'true').lower() == 'true',
        'CA_CERT': os.environ.get('HIVE_POC_CA_CERT', '') or None,
    }
elif CIS_ENV == 'DR':
    # DR - Disaster Recovery
    HIVE_CONFIG = {
        'HOST': os.environ.get('HIVE_HOST', 'lxmrwtsgvqk2.sg.uobnet.com'),
        'PORT': int(os.environ.get('HIVE_PORT', '10000')),
        'DATABASE': os.environ.get('HIVE_DB', 'mrw_ima'),
        'AUTH': os.environ.get('HIVE_AUTH', 'GSSAPI'),
        'TIMEOUT': int(os.environ.get('HIVE_TIMEOUT', '300')),
        'POOL_SIZE': int(os.environ.get('HIVE_POOL_SIZE', '10')),
        'KERBEROS_SERVICE_NAME': os.environ.get('HIVE_KERBEROS_SERVICE_NAME', 'hive'),
        'USE_SSL': os.environ.get('HIVE_USE_SSL', 'true').lower() == 'true',
        'CA_CERT': os.environ.get('HIVE_POC_CA_CERT', '') or None,
    }
else:
    # LOCAL Development Configuration (No Kerberos)
    HIVE_CONFIG = {
        'HOST': os.environ.get('HIVE_HOST', 'localhost'),
        'PORT': int(os.environ.get('HIVE_PORT', '10000')),
        'DATABASE': os.environ.get('HIVE_DB', 'gmp_cis'),
        'AUTH': os.environ.get('HIVE_AUTH', 'NOSASL'),
        'TIMEOUT': int(os.environ.get('HIVE_TIMEOUT', '300')),
        'POOL_SIZE': int(os.environ.get('HIVE_POOL_SIZE', '10')),
        'KERBEROS_SERVICE_NAME': None,
        'USE_SSL': False,
        'CA_CERT': None,
    }

# ============================================================================
# Optional: Initial Hive session properties to apply AFTER cursor creation
# ============================================================================

INIT_STATEMENTS = [
    # 'SET hive.execution.engine=tez',
    # 'SET hive.vectorized.execution.enabled=true',
]

# ============================================================================
# Defensive switch: if True, any attempt to set MR will be rewritten to Tez
# ============================================================================

ALWAYS_USE_TEZ = os.environ.get('HIVE_POC_ALWAYS_USE_TEZ', 'true').lower() == 'true'

# ============================================================================
# ENV_CONFIG Dictionary (for backward compatibility)
# ============================================================================

ENV_CONFIG = {
    'LOCAL': {
        'ENV_NAME': 'LOCAL',
        'ENV_DISPLAY': 'Local Development',
        'DEBUG': True,
        'IMPALA_HOST': 'localhost',
        'IMPALA_PORT': 21050,
        'IMPALA_AUTH': 'NOSASL',
        'IMPALA_DB': 'gmp_cis',
        'HIVE_HOST': 'localhost',
        'HIVE_PORT': 10000,
        'HIVE_AUTH': 'NOSASL',
        'HIVE_DB': 'gmp_cis',
        'KERBEROS_ENABLED': False,
        'USE_SSL': False,
    },
    'SIT': {
        'ENV_NAME': 'SIT',
        'ENV_DISPLAY': 'System Integration Testing',
        'DEBUG': False,
        'IMPALA_HOST': 'lxmrwtsgyodt1.sg.uobnet.com',
        'IMPALA_PORT': 21050,
        'IMPALA_AUTH': 'GSSAPI',
        'IMPALA_DB': 'gmp_cis',
        'HIVE_HOST': 'lxmrwtsgvqk2.sg.uobnet.com',
        'HIVE_PORT': 10000,
        'HIVE_AUTH': 'GSSAPI',
        'HIVE_DB': 'mrw_ima',
        'KERBEROS_ENABLED': True,
        'KERBEROS_SERVICE_NAME': 'impala',
        'USE_SSL': True,
    },
    'UAT': {
        'ENV_NAME': 'UAT',
        'ENV_DISPLAY': 'User Acceptance Testing',
        'DEBUG': False,
        'IMPALA_HOST': 'lxmrwtsgvqk2.sg.uobnet.com',
        'IMPALA_PORT': 21050,
        'IMPALA_AUTH': 'GSSAPI',
        'IMPALA_DB': 'gmp_cis',
        'HIVE_HOST': 'lxmrwtsgvqk2.sg.uobnet.com',
        'HIVE_PORT': 10000,
        'HIVE_AUTH': 'GSSAPI',
        'HIVE_DB': 'mrw_ima',
        'KERBEROS_ENABLED': True,
        'KERBEROS_SERVICE_NAME': 'impala',
        'USE_SSL': True,
    },
    'PROD': {
        'ENV_NAME': 'PROD',
        'ENV_DISPLAY': 'Production',
        'DEBUG': False,
        'IMPALA_HOST': 'lxmrwtsgvqk2.sg.uobnet.com',
        'IMPALA_PORT': 21050,
        'IMPALA_AUTH': 'GSSAPI',
        'IMPALA_DB': 'gmp_cis',
        'HIVE_HOST': 'lxmrwtsgvqk2.sg.uobnet.com',
        'HIVE_PORT': 10000,
        'HIVE_AUTH': 'GSSAPI',
        'HIVE_DB': 'mrw_ima',
        'KERBEROS_ENABLED': True,
        'KERBEROS_SERVICE_NAME': 'impala',
        'USE_SSL': True,
    },
    'DR': {
        'ENV_NAME': 'DR',
        'ENV_DISPLAY': 'Disaster Recovery',
        'DEBUG': False,
        'IMPALA_HOST': 'lxmrwtsgvqk2.sg.uobnet.com',
        'IMPALA_PORT': 21050,
        'IMPALA_AUTH': 'GSSAPI',
        'IMPALA_DB': 'gmp_cis',
        'HIVE_HOST': 'lxmrwtsgvqk2.sg.uobnet.com',
        'HIVE_PORT': 10000,
        'HIVE_AUTH': 'GSSAPI',
        'HIVE_DB': 'mrw_ima',
        'KERBEROS_ENABLED': True,
        'KERBEROS_SERVICE_NAME': 'impala',
        'USE_SSL': True,
    },
}

# Valid environment names
VALID_ENVIRONMENTS = list(ENV_CONFIG.keys())


def get_current_environment() -> str:
    """
    Detect current environment from CIS_ENV environment variable.

    Returns:
        Environment name (LOCAL, SIT, UAT, PROD, DR)
    """
    env = os.environ.get('CIS_ENV', 'LOCAL').upper()

    if env not in VALID_ENVIRONMENTS:
        print(f"WARNING: Unknown environment '{env}', defaulting to LOCAL")
        return 'LOCAL'

    return env


def get_environment_config(env_name: str = None) -> dict:
    """
    Get configuration for the specified or current environment.
    """
    if env_name is None:
        env_name = get_current_environment()

    if env_name not in ENV_CONFIG:
        raise ValueError(f"Unknown environment: {env_name}. Valid: {VALID_ENVIRONMENTS}")

    return ENV_CONFIG[env_name]


def get_impala_config(env_name: str = None) -> dict:
    """Get Impala configuration."""
    return IMPALA_CONFIG


def get_hive_config(env_name: str = None) -> dict:
    """Get Hive configuration."""
    return HIVE_CONFIG


def print_environment_info():
    """Print current environment configuration (for debugging)."""
    print("=" * 60)
    print(f"  CIS Trade Hive - Environment Configuration")
    print("=" * 60)
    print(f"  CIS_ENV:         {CIS_ENV}")
    print("")
    print("  Impala (FAST READS):")
    print(f"    Host:          {IMPALA_CONFIG['HOST']}")
    print(f"    Port:          {IMPALA_CONFIG['PORT']}")
    print(f"    Auth:          {IMPALA_CONFIG['AUTH_MECHANISM']}")
    print(f"    Database:      {IMPALA_CONFIG['DATABASE']}")
    print(f"    SSL:           {IMPALA_CONFIG['USE_SSL']}")
    print(f"    Kerberos:      {IMPALA_CONFIG['KERBEROS_SERVICE_NAME']}")
    print(f"    Pool Size:     {IMPALA_CONFIG['POOL_SIZE']}")
    print("")
    print("  Hive (ACID WRITES):")
    print(f"    Host:          {HIVE_CONFIG['HOST']}")
    print(f"    Port:          {HIVE_CONFIG['PORT']}")
    print(f"    Auth:          {HIVE_CONFIG['AUTH']}")
    print(f"    Database:      {HIVE_CONFIG['DATABASE']}")
    print(f"    SSL:           {HIVE_CONFIG['USE_SSL']}")
    print(f"    Kerberos:      {HIVE_CONFIG['KERBEROS_SERVICE_NAME']}")
    print(f"    Pool Size:     {HIVE_CONFIG['POOL_SIZE']}")
    print("=" * 60)


# ============================================================================
# Module-level convenience
# ============================================================================

CURRENT_ENV = get_current_environment()
CURRENT_CONFIG = get_environment_config()
