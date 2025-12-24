"""
Django settings for CisTrade project.

Enterprise-grade Trade Management System with:
- SOLID Architecture principles
- Hive database connectivity
- Direct data access without authentication
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Security Settings
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-CHANGE-ME-IN-PRODUCTION')
DEBUG = os.environ.get('DJANGO_DEBUG', 'true').lower() == 'true'
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    # Django Core Apps (minimal - no admin, no auth)
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',

    # Third Party Apps
    'rest_framework',
    'django_filters',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_extensions',

    # Custom Apps
    'core.apps.CoreConfig',
    'portfolio.apps.PortfolioConfig',
    'udf.apps.UdfConfig',
    'reference_data.apps.ReferenceDataConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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
                # Custom context processors
                'core.utils.context_processors.app_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

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

# Hive Configuration (Local Environment)
HIVE_CONFIG = {
    'HOST': os.environ.get('HIVE_HOST', 'localhost'),
    'PORT': int(os.environ.get('HIVE_PORT', '10000')),
    'DATABASE': os.environ.get('HIVE_DB', 'cis'),
    'AUTH': os.environ.get('HIVE_AUTH', 'NOSASL'),
    'USERNAME': os.environ.get('HIVE_USERNAME', ''),
    'PASSWORD': os.environ.get('HIVE_PASSWORD', ''),
    'TIMEOUT': int(os.environ.get('HIVE_TIMEOUT', '60')),
}

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
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

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
    },
}

# Create logs directory if it doesn't exist
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

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
