"""
Environment Configuration for CIS Trade Hive

Supported Environments:
- LOCAL: Local development with Docker Kudu/Impala
- SIT: System Integration Testing (TST.UOBNET.COM)
- UAT: User Acceptance Testing (SG.UOBNET.COM)
- PROD: Production (SG.UOBNET.COM)
- DR: Disaster Recovery (SG.UOBNET.COM)

Usage:
    from config.environments import get_environment_config, ENV_CONFIG

    # Get current environment config
    config = get_environment_config()
    print(config['IMPALA_HOST'])

    # Or access directly
    print(ENV_CONFIG['UAT']['KRB5_PRINCIPAL'])
"""

import os

# ============================================================================
# Environment Configuration Dictionary
# ============================================================================

ENV_CONFIG = {
    # -------------------------------------------------------------------------
    # LOCAL - Development Environment (Docker)
    # -------------------------------------------------------------------------
    'LOCAL': {
        'ENV_NAME': 'LOCAL',
        'ENV_DISPLAY': 'Local Development',
        'DEBUG': True,

        # Impala/Kudu Configuration
        'IMPALA_HOST': 'localhost',
        'IMPALA_PORT': 21050,
        'IMPALA_AUTH': 'NOSASL',
        'IMPALA_DB': 'gmp_cis',

        # Hive Configuration
        'HIVE_HOST': 'localhost',
        'HIVE_PORT': 10000,
        'HIVE_AUTH': 'NOSASL',
        'HIVE_DB': 'gmp_cis',

        # Kerberos - Not used in LOCAL
        'KERBEROS_ENABLED': False,
        'KRB5_KTNAME': None,
        'KRB5_PRINCIPAL': None,
        'KRB5CCNAME': None,

        # REST Proxy - Not used in LOCAL
        'USE_REST_PROXY': False,
        'HIVE_PROXY_URL': None,
    },

    # -------------------------------------------------------------------------
    # SIT - System Integration Testing
    # -------------------------------------------------------------------------
    'SIT': {
        'ENV_NAME': 'SIT',
        'ENV_DISPLAY': 'System Integration Testing',
        'DEBUG': False,

        # Impala Configuration
        'IMPALA_HOST': os.environ.get('SIT_IMPALA_HOST', 'sit-impala.example.com'),
        'IMPALA_PORT': 21050,
        'IMPALA_AUTH': 'GSSAPI',
        'IMPALA_DB': 'gmp_cis',

        # Hive Configuration
        'HIVE_HOST': os.environ.get('SIT_HIVE_HOST', 'sit-hive.example.com'),
        'HIVE_PORT': 10000,
        'HIVE_AUTH': 'GSSAPI',
        'HIVE_DB': 'mrw_ima',

        # Kerberos Configuration - SIT
        'KERBEROS_ENABLED': True,
        'KRB5_KTNAME': '/home/cdsw/CIS/secrets/owntmrwsg.keytab',
        'KRB5_PRINCIPAL': 'owntmrwsg@TST.UOBNET.COM',
        'KRB5CCNAME': 'FILE:/home/cdsw/CIS/krb5/krb5cc',

        # REST Proxy
        'USE_REST_PROXY': True,
        'HIVE_PROXY_URL': os.environ.get('SIT_HIVE_PROXY_URL', 'http://172.29.22.185:5000'),
    },

    # -------------------------------------------------------------------------
    # UAT - User Acceptance Testing
    # -------------------------------------------------------------------------
    'UAT': {
        'ENV_NAME': 'UAT',
        'ENV_DISPLAY': 'User Acceptance Testing',
        'DEBUG': False,

        # Impala Configuration
        'IMPALA_HOST': os.environ.get('UAT_IMPALA_HOST', 'uat-impala.example.com'),
        'IMPALA_PORT': 21050,
        'IMPALA_AUTH': 'GSSAPI',
        'IMPALA_DB': 'gmp_cis',

        # Hive Configuration
        'HIVE_HOST': os.environ.get('UAT_HIVE_HOST', 'uat-hive.example.com'),
        'HIVE_PORT': 10000,
        'HIVE_AUTH': 'GSSAPI',
        'HIVE_DB': 'mrw_ima',

        # Kerberos Configuration - UAT
        'KERBEROS_ENABLED': True,
        'KRB5_KTNAME': '/home/cdsw/CIS/secrets/ownumrwsg.keytab',
        'KRB5_PRINCIPAL': 'ownumrwsg@SG.UOBNET.COM',
        'KRB5CCNAME': 'FILE:/home/cdsw/CIS/krb5/krb5cc',

        # REST Proxy
        'USE_REST_PROXY': True,
        'HIVE_PROXY_URL': os.environ.get('UAT_HIVE_PROXY_URL', 'http://172.29.22.185:5000'),
    },

    # -------------------------------------------------------------------------
    # PROD - Production
    # -------------------------------------------------------------------------
    'PROD': {
        'ENV_NAME': 'PROD',
        'ENV_DISPLAY': 'Production',
        'DEBUG': False,

        # Impala Configuration
        'IMPALA_HOST': os.environ.get('PROD_IMPALA_HOST', 'prod-impala.example.com'),
        'IMPALA_PORT': 21050,
        'IMPALA_AUTH': 'GSSAPI',
        'IMPALA_DB': 'gmp_cis',

        # Hive Configuration
        'HIVE_HOST': os.environ.get('PROD_HIVE_HOST', 'prod-hive.example.com'),
        'HIVE_PORT': 10000,
        'HIVE_AUTH': 'GSSAPI',
        'HIVE_DB': 'mrw_ima',

        # Kerberos Configuration - PROD
        'KERBEROS_ENABLED': True,
        'KRB5_KTNAME': '/home/cdsw/CIS/secrets/ownumrwsg.keytab',
        'KRB5_PRINCIPAL': 'ownumrwsg@SG.UOBNET.COM',
        'KRB5CCNAME': 'FILE:/home/cdsw/CIS/krb5/krb5cc',

        # REST Proxy
        'USE_REST_PROXY': True,
        'HIVE_PROXY_URL': os.environ.get('PROD_HIVE_PROXY_URL', 'http://172.29.22.185:5000'),
    },

    # -------------------------------------------------------------------------
    # DR - Disaster Recovery
    # -------------------------------------------------------------------------
    'DR': {
        'ENV_NAME': 'DR',
        'ENV_DISPLAY': 'Disaster Recovery',
        'DEBUG': False,

        # Impala Configuration
        'IMPALA_HOST': os.environ.get('DR_IMPALA_HOST', 'dr-impala.example.com'),
        'IMPALA_PORT': 21050,
        'IMPALA_AUTH': 'GSSAPI',
        'IMPALA_DB': 'gmp_cis',

        # Hive Configuration
        'HIVE_HOST': os.environ.get('DR_HIVE_HOST', 'dr-hive.example.com'),
        'HIVE_PORT': 10000,
        'HIVE_AUTH': 'GSSAPI',
        'HIVE_DB': 'mrw_ima',

        # Kerberos Configuration - DR
        'KERBEROS_ENABLED': True,
        'KRB5_KTNAME': '/home/cdsw/CIS/secrets/ownrmrwsg.keytab',
        'KRB5_PRINCIPAL': 'ownrmrwsg@SG.UOBNET.COM',
        'KRB5CCNAME': 'FILE:/home/cdsw/CIS/krb5/krb5cc',

        # REST Proxy
        'USE_REST_PROXY': True,
        'HIVE_PROXY_URL': os.environ.get('DR_HIVE_PROXY_URL', 'http://172.29.22.185:5000'),
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

    # Handle legacy 'work' environment - map to SIT by default
    if env == 'WORK':
        env = 'SIT'

    if env not in VALID_ENVIRONMENTS:
        print(f"WARNING: Unknown environment '{env}', defaulting to LOCAL")
        return 'LOCAL'

    return env


def get_environment_config(env_name: str = None) -> dict:
    """
    Get configuration for the specified or current environment.

    Args:
        env_name: Environment name (optional, uses CIS_ENV if not provided)

    Returns:
        Environment configuration dictionary
    """
    if env_name is None:
        env_name = get_current_environment()

    env_name = env_name.upper()

    if env_name not in ENV_CONFIG:
        raise ValueError(f"Unknown environment: {env_name}. Valid: {VALID_ENVIRONMENTS}")

    return ENV_CONFIG[env_name]


def get_kerberos_config(env_name: str = None) -> dict:
    """
    Get Kerberos configuration for the specified or current environment.

    Args:
        env_name: Environment name (optional)

    Returns:
        Dictionary with KRB5_KTNAME, KRB5_PRINCIPAL, KRB5CCNAME, KERBEROS_ENABLED
    """
    config = get_environment_config(env_name)
    return {
        'KERBEROS_ENABLED': config.get('KERBEROS_ENABLED', False),
        'KRB5_KTNAME': config.get('KRB5_KTNAME'),
        'KRB5_PRINCIPAL': config.get('KRB5_PRINCIPAL'),
        'KRB5CCNAME': config.get('KRB5CCNAME'),
    }


def get_impala_config(env_name: str = None) -> dict:
    """
    Get Impala configuration for the specified or current environment.

    Args:
        env_name: Environment name (optional)

    Returns:
        Dictionary with IMPALA_HOST, IMPALA_PORT, IMPALA_AUTH, IMPALA_DB
    """
    config = get_environment_config(env_name)
    return {
        'HOST': config.get('IMPALA_HOST'),
        'PORT': config.get('IMPALA_PORT', 21050),
        'AUTH': config.get('IMPALA_AUTH', 'NOSASL'),
        'DATABASE': config.get('IMPALA_DB', 'gmp_cis'),
    }


def get_hive_config(env_name: str = None) -> dict:
    """
    Get Hive configuration for the specified or current environment.

    Args:
        env_name: Environment name (optional)

    Returns:
        Dictionary with HIVE_HOST, HIVE_PORT, HIVE_AUTH, HIVE_DB
    """
    config = get_environment_config(env_name)
    return {
        'HOST': config.get('HIVE_HOST'),
        'PORT': config.get('HIVE_PORT', 10000),
        'AUTH': config.get('HIVE_AUTH', 'NOSASL'),
        'DATABASE': config.get('HIVE_DB', 'gmp_cis'),
        'USE_REST_PROXY': config.get('USE_REST_PROXY', False),
        'HIVE_PROXY_URL': config.get('HIVE_PROXY_URL'),
    }


def print_environment_info():
    """Print current environment configuration (for debugging)."""
    env = get_current_environment()
    config = get_environment_config()

    print("=" * 60)
    print(f"  CIS Trade Hive - Environment Configuration")
    print("=" * 60)
    print(f"  Environment:     {config['ENV_DISPLAY']} ({env})")
    print(f"  Debug Mode:      {config['DEBUG']}")
    print("")
    print("  Impala:")
    print(f"    Host:          {config['IMPALA_HOST']}")
    print(f"    Port:          {config['IMPALA_PORT']}")
    print(f"    Auth:          {config['IMPALA_AUTH']}")
    print(f"    Database:      {config['IMPALA_DB']}")
    print("")
    print("  Hive:")
    print(f"    Host:          {config['HIVE_HOST']}")
    print(f"    Port:          {config['HIVE_PORT']}")
    print(f"    Auth:          {config['HIVE_AUTH']}")
    print(f"    Database:      {config['HIVE_DB']}")
    print(f"    REST Proxy:    {config['USE_REST_PROXY']}")
    if config['USE_REST_PROXY']:
        print(f"    Proxy URL:     {config['HIVE_PROXY_URL']}")
    print("")
    if config['KERBEROS_ENABLED']:
        print("  Kerberos:")
        print(f"    Keytab:        {config['KRB5_KTNAME']}")
        print(f"    Principal:     {config['KRB5_PRINCIPAL']}")
        print(f"    Cache:         {config['KRB5CCNAME']}")
    else:
        print("  Kerberos:        Disabled")
    print("=" * 60)


# ============================================================================
# Module-level convenience
# ============================================================================

# Current environment name
CURRENT_ENV = get_current_environment()

# Current environment config
CURRENT_CONFIG = get_environment_config()
