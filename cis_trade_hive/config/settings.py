"""
Django settings for CisTrade project.

Enterprise-grade Trade Management System with:
- SOLID Architecture principles
- Impala/Kudu database connectivity
- Multi-environment support (LOCAL, SIT, UAT, PROD, DR)
- Direct data access without authentication
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from project root — works regardless of cwd
load_dotenv(BASE_DIR / '.env')

# ============================================================================
# Environment Configuration
# ============================================================================
# Set CIS_ENV environment variable to switch environments:
#   LOCAL - Local development with Docker
#   SIT   - System Integration Testing
#   UAT   - User Acceptance Testing
#   PROD  - Production
#   DR    - Disaster Recovery

from config.environments import (
    get_current_environment,
    get_environment_config,
    get_impala_config,
    get_hive_config,
    CURRENT_ENV,
    CURRENT_CONFIG,
    IMPALA_CONFIG as ENV_IMPALA_CONFIG,
    HIVE_CONFIG as ENV_HIVE_CONFIG,
)

# Current environment
CIS_ENVIRONMENT = CURRENT_ENV
CIS_ENVIRONMENT_DISPLAY = CURRENT_CONFIG.get('ENV_DISPLAY', CIS_ENVIRONMENT)

# Security Settings
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-CHANGE-ME-IN-PRODUCTION')

# Debug mode from environment config (can be overridden by env var)
DEBUG = os.environ.get('DJANGO_DEBUG', str(CURRENT_CONFIG.get('DEBUG', True))).lower() == 'true'

# Development mode settings
# Set SKIP_PERMISSION_CHECKS=false in .env to enforce permission checks
SKIP_PERMISSION_CHECKS = os.environ.get('SKIP_PERMISSION_CHECKS', str(DEBUG)).lower() == 'true'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0').split(',')

# Application definition
INSTALLED_APPS = [
    # Django Core Apps (minimal - with sessions for ACL)
    'django.contrib.auth',  # Required for User model in audit logs
    'django.contrib.contenttypes',
    'django.contrib.sessions',  # Required for session-based ACL auth
    'django.contrib.messages',  # Required for flash messages
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Third Party Apps
    'rest_framework',
    'django_filters',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_extensions',

    # Django Channels (WebSocket / real-time notifications)
    'channels',
    # daphne added conditionally below (requires Rust/cbor2 to build)

    # Custom Apps
    'core.apps.CoreConfig',
    'portfolio.apps.PortfolioConfig',
    'market_data.apps.MarketDataConfig',
    'udf.apps.UdfConfig',
    'reference_data.apps.ReferenceDataConfig',
    'security.apps.SecurityConfig',
    'trade.apps.TradeConfig',
    'lookup',
    'hive_poc.apps.HivePocConfig',  # Hive POC - Managed Tables with ORC
    'upload.apps.UploadConfig',  # File Upload & Hive External Table Ingestion
    'query_builder.apps.QueryBuilderConfig',  # Query Builder
]

# daphne (ASGI server with HTTP/2 + WebSocket) requires cbor2 which needs Rust.
# Add it only when it's actually installed so local dev without Rust still works.
try:
    import daphne  # noqa: F401
    INSTALLED_APPS.insert(0, 'daphne')
except ImportError:
    pass

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'core.middleware.performance_middleware.PerformanceMonitoringMiddleware',  # Performance monitoring
    'django.contrib.sessions.middleware.SessionMiddleware',  # Required for session-based auth
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',  # Required for flash messages
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # URL-level permission enforcement — must be after SessionMiddleware
    'core.middleware.permission_middleware.PermissionMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',  # Required for flash messages
                # Custom context processors
                'core.utils.context_processors.app_context',
                'core.utils.context_processors.sidebar_permissions',  # RBAC sidebar permissions
                'core.utils.context_processors.system_date_context',  # System date from GMP
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database Configuration
# Primary database (SQLite for development, MySQL for production)
DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.environ.get('DB_NAME', str(BASE_DIR / 'db.sqlite3')),
        'USER': os.environ.get('DB_USER', ''),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', ''),
        'PORT': os.environ.get('DB_PORT', ''),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        } if os.environ.get('DB_ENGINE') == 'django.db.backends.mysql' else {},
    },
}

# ============================================================================
# Impala Configuration (Environment-aware)
# ============================================================================
# Re-build IMPALA_CONFIG at settings load time using the live CIS_ENV so that
# cml_app.py setting os.environ["CIS_ENV"] before Django initialises is picked
# up correctly.  environments.py freezes CIS_ENV at import time (module level),
# so importing its pre-built IMPALA_CONFIG gives LOCAL defaults even when
# CIS_ENV=UAT is set by the CML launcher just before Django starts.
from config.environments import get_impala_config as _get_impala_cfg
import importlib as _importlib
import config.environments as _env_module

# Force environments module to re-evaluate with the current CIS_ENV value
_live_cis_env = os.environ.get('CIS_ENV', 'LOCAL').upper()
if _live_cis_env != _env_module.CIS_ENV:
    # CIS_ENV changed after environments.py was first imported — reload it so
    # IMPALA_CONFIG, HIVE_CONFIG reflect the correct environment.
    _importlib.reload(_env_module)

IMPALA_CONFIG = _env_module.IMPALA_CONFIG.copy()

# env var wins over config file for individual overrides
_use_ssl_env = os.environ.get('IMPALA_USE_SSL', '').lower()
if _use_ssl_env:
    IMPALA_CONFIG['USE_SSL'] = _use_ssl_env == 'true'
_impala_host_env = os.environ.get('IMPALA_HOST', '')
if _impala_host_env:
    IMPALA_CONFIG['HOST'] = _impala_host_env
_impala_port_env = os.environ.get('IMPALA_PORT', '')
if _impala_port_env:
    IMPALA_CONFIG['PORT'] = int(_impala_port_env)
_impala_auth_env = os.environ.get('IMPALA_AUTH', '')
if _impala_auth_env:
    IMPALA_CONFIG['AUTH'] = _impala_auth_env
    IMPALA_CONFIG['AUTH_MECHANISM'] = _impala_auth_env

# ============================================================================
# Hive Configuration (Environment-aware)
# ============================================================================
HIVE_CONFIG = _env_module.HIVE_CONFIG

# ============================================================================
# Kerberos Configuration (Environment-aware)
# ============================================================================
# Only used in non-LOCAL environments (SIT, UAT, PROD, DR)

KERBEROS_CONFIG = {
    'ENABLED': CURRENT_CONFIG.get('KERBEROS_ENABLED', False),
    'KRB5_KTNAME': os.environ.get('KRB5_KTNAME', CURRENT_CONFIG.get('KRB5_KTNAME')),
    'KRB5_PRINCIPAL': os.environ.get('KRB5_PRINCIPAL', CURRENT_CONFIG.get('KRB5_PRINCIPAL')),
    'KRB5CCNAME': os.environ.get('KRB5CCNAME', CURRENT_CONFIG.get('KRB5CCNAME')),
}

# ============================================================================
# REST Proxy Configuration (for Hive in CML environments)
# ============================================================================

USE_REST_PROXY = os.environ.get('USE_REST_PROXY', str(CURRENT_CONFIG.get('USE_REST_PROXY', False))).lower() == 'true'
HIVE_PROXY_URL = os.environ.get('HIVE_PROXY_URL', CURRENT_CONFIG.get('HIVE_PROXY_URL'))

# Impala Connection Pool Configuration
# IMPORTANT: Impala HS2 pool hard limit = 64 total across ALL Gunicorn workers.
# Formula: IMPALA_POOL_SIZE × gunicorn_workers must be < 64.
# With 4 Gunicorn workers: max 15 per worker (4×15=60, leaves 4 headroom).
# With 2 Gunicorn workers: max 25 per worker (2×25=50).
# Default 10 is safe for any worker count (4×10=40 < 64).
IMPALA_POOL_SIZE = int(os.environ.get('IMPALA_POOL_SIZE', '10'))

# Async Audit Queue Configuration
# Enables non-blocking audit logging for production performance
AUDIT_ASYNC_ENABLED = os.environ.get('AUDIT_ASYNC_ENABLED', 'True').lower() == 'true'
AUDIT_ASYNC_WORKERS = int(os.environ.get('AUDIT_ASYNC_WORKERS', '4'))
AUDIT_QUEUE_SIZE = int(os.environ.get('AUDIT_QUEUE_SIZE', '1000'))

# Audit Filtering Configuration
# When True, only audits write operations (POST/PUT/PATCH/DELETE) + authentication
# Reduces audit volume by 80-90% compared to auditing all requests including GET
AUDIT_ONLY_WRITES = os.environ.get('AUDIT_ONLY_WRITES', 'True').lower() == 'true'

# Audit Logger Type
# Options: 'impala' (production), 'console' (development)
AUDIT_LOGGER_TYPE = os.environ.get('AUDIT_LOGGER_TYPE', 'impala')

# Database Router
DATABASE_ROUTERS = ['core.repositories.db_router.DatabaseRouter']

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Singapore'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
# Use plain StaticFilesStorage — no manifest, no hashing.
# Works immediately after collectstatic copies static/ → staticfiles/.
# collectstatic runs automatically at startup via cml_app.py for non-SIT envs.
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# File Upload Settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024  # 100 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024  # 100 MB
FILE_UPLOAD_HANDLERS = [
    'django.core.files.uploadhandler.MemoryFileUploadHandler',
    'django.core.files.uploadhandler.TemporaryFileUploadHandler',
]

# Upload temporary directory
UPLOAD_TEMP_DIR = BASE_DIR / 'media' / 'uploads' / 'temp'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Crispy Forms Configuration
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}

# Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'cistrade-cache',
        'TIMEOUT': 300,
        'OPTIONS': {
            'MAX_ENTRIES': 1000
        }
    }
}

# ============================================================================
# Django Channels — Channel Layer Configuration
# ============================================================================
# LOCAL/DEV:  InMemoryChannelLayer  (no Redis required, not shared across workers)
# PROD/CML:   RedisChannelLayer     (set REDIS_URL env var, shared across all workers)
#
# Production note: With Gunicorn + multiple workers, InMemoryChannelLayer does NOT
# share state across processes — each worker has its own layer. Use Redis in prod.
#
# Redis URL format: redis://:password@hostname:6379/0
#                   rediss://:password@hostname:6380/0  (TLS)
# ============================================================================

_REDIS_URL = os.environ.get('REDIS_URL', '')

if _REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [_REDIS_URL],
                'capacity': 1500,           # max messages queued per group
                'expiry': 60,               # message TTL in seconds
                'group_expiry': 86400,      # group membership TTL (24 h)
                'symmetric_encryption_keys': [SECRET_KEY],  # encrypt channel messages
            },
        },
    }
else:
    # Development / Docker local — no Redis needed
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
            'CONFIG': {
                'capacity': 500,
                'expiry': 60,
            },
        },
    }

# WebSocket settings
WS_HEARTBEAT_INTERVAL   = int(os.environ.get('WS_HEARTBEAT_INTERVAL', '30'))   # seconds
WS_MAX_RECONNECT_DELAY  = int(os.environ.get('WS_MAX_RECONNECT_DELAY', '30'))  # seconds

# Add logger for channels
# (added to LOGGING dict after its definition)

# CSRF Configuration
CSRF_COOKIE_SECURE = not DEBUG

# Security Settings (Production)
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {asctime} {name}: {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'cistrade.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'core': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'portfolio': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'udf': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'reference_data': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'acl': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'audit': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'upload': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'trade': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'market_data': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'security': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'channels': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'daphne': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        # Suppress per-request access log noise from uvicorn under ASGI
        'uvicorn.access': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'uvicorn.error': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        # StreamingHttpResponse sync-iterator warning fires on every static
        # file request under ASGI — it is harmless and very noisy.
        'django.request': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
        # impyla logs "Using database X as default" on every connection reuse
        # and "Closing active operation" on every cursor close — the ETL
        # pipelines issue dozens of statements per run, so at INFO this
        # dwarfs every other log line and drowns out the app's own step
        # progress messages. Nothing here is actionable; keep only WARNING+.
        'impala': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
    # Safety net: any app logger not explicitly listed above (e.g. a new app,
    # or one added without updating this file) still reaches the log file
    # instead of being silently dropped — this is what caused prior debug
    # logging from trade/services/* to appear to "never fire".
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
}

# Create logs directory if it doesn't exist
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Suppress Django's "StreamingHttpResponse must consume synchronous iterator"
# warning that fires on every static file request when running under ASGI
# (uvicorn/daphne). WhiteNoise uses sync iterators — this is harmless.
import warnings
warnings.filterwarnings(
    'ignore',
    message='.*StreamingHttpResponse.*synchronous iterator.*',
    category=Warning,
)

# Email Configuration
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@cistrade.com')

# Application-specific Settings
APP_NAME = 'CisTrade'
APP_VERSION = '1.0.0'
APP_DESCRIPTION = 'Enterprise Trade Management System'

# Four-Eyes Principle (Maker-Checker)
MAKER_CHECKER_ENABLED = os.environ.get('MAKER_CHECKER_ENABLED', 'true').lower() == 'true'

# ============================================================================
# RBAC (Role-Based Access Control) Configuration
# ============================================================================
# Version: Determines which ACL tables to use
#   'v1' - Legacy tables: cis_user, cis_user_group, cis_group_permissions
#          - Single group per user (cis_user_group_id)
#          - Uses ACLRepository class
#
#   'v2' - New tables: cis_user_info, cis_user_group_info, cis_permission_info,
#                      cis_user_group_mapping_info, cis_group_permission_map
#          - Multi-group support (users can belong to multiple groups)
#          - Permission aggregation (READ_WRITE > READ)
#          - Uses ACLRepositoryV2 class
#
# Rollback: To rollback to v1, simply set RBAC_VERSION=v1 and restart.
#           No database changes required for rollback.
#
# Migration: When ready to switch:
#   1. Ensure new tables are populated with data
#   2. Test with RBAC_VERSION=v2 in development
#   3. Deploy with RBAC_VERSION=v2 in production
#   4. Monitor for issues, rollback to v1 if needed
#
RBAC_VERSION = os.environ.get('RBAC_VERSION', 'v2')

# RBAC Cache TTL (seconds) - How long to cache user permissions
RBAC_CACHE_TTL = int(os.environ.get('RBAC_CACHE_TTL', '300'))  # 5 minutes default
