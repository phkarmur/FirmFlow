import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Add apps directory to sys.path
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / 'apps'))

load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'firmflow-insecure-dev-secret-key-replace-in-production')
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,web,api').split(',') if h.strip()]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'django_celery_beat',

    # FirmFlow Apps
    'apps.common.apps.CommonConfig',
    'apps.accounts.apps.AccountsConfig',
    'apps.clients.apps.ClientsConfig',
    'apps.services.apps.ServicesConfig',
    'apps.periods.apps.PeriodsConfig',
    'apps.tasks.apps.TasksConfig',
    'apps.bulk.apps.BulkConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.reports.apps.ReportsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.common.middleware.RequestLoggingMiddleware',
    # After the request logger, so blocked calls are still in the request log
    'apps.accounts.middleware.PasswordChangeRequiredMiddleware',
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
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DB_ENGINE = os.getenv('DB_ENGINE')
if DB_ENGINE == 'django.db.backends.sqlite3' or not os.getenv('DB_HOST'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / os.getenv('DB_NAME', 'db.sqlite3'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'firmflow_db'),
            'USER': os.getenv('DB_USER', 'firmflow_user'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'firmflow_password_secret'),
            'HOST': os.getenv('DB_HOST', 'postgres'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }

# Password validation & Argon2
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
]

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 10},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

AUTH_USER_MODEL = 'accounts.User'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static & Media
STATIC_URL = os.getenv('STATIC_URL', '/static/')
STATIC_ROOT = BASE_DIR / os.getenv('STATIC_ROOT', 'static')

MEDIA_URL = os.getenv('MEDIA_URL', '/media/')
MEDIA_ROOT = BASE_DIR / os.getenv('MEDIA_ROOT', 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'apps.common.pagination.StandardResultsSetPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# CORS & CSRF
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000').split(',') if o.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://localhost:8000').split(',') if o.strip()]

# OpenAPI Docs
SPECTACULAR_SETTINGS = {
    'TITLE': 'FirmFlow Practice Management API',
    'DESCRIPTION': 'REST API for FirmFlow CA/CS Practice Management System',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Celery
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')
CELERY_TIMEZONE = TIME_ZONE

# Email
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 1025))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'False').lower() in ('true', '1')
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() in ('true', '1')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'notifications@firmflow.local')
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', 10))
# Notification e-mails: True = send with the Celery worker (Docker), False = send after commit in the web process
NOTIFY_EMAIL_ASYNC = os.getenv('NOTIFY_EMAIL_ASYNC', 'False').lower() in ('true', '1', 'yes')
# /healthz reports 'unhealthy' when Redis is down only if this is on (default: on when e-mails go through Celery)
HEALTH_REQUIRE_REDIS = os.getenv('HEALTH_REQUIRE_REDIS', str(NOTIFY_EMAIL_ASYNC)).lower() in ('true', '1', 'yes')
# Used for links in e-mails
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')

# Task attachments are stored OUTSIDE the public media folder and only served through
# the authenticated download endpoint (spec §5.8 F2)
PRIVATE_MEDIA_ROOT = BASE_DIR / os.getenv('PRIVATE_MEDIA_ROOT', 'private_media')

# Structured logging (spec §10): one JSON line per event on stdout
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'raw': {'format': '%(message)s'},
        'plain': {'format': '%(asctime)s %(levelname)s %(name)s %(message)s'},
    },
    'handlers': {
        'structured': {'class': 'logging.StreamHandler', 'formatter': 'raw'},
        'console': {'class': 'logging.StreamHandler', 'formatter': 'plain'},
    },
    'loggers': {
        'firmflow.structured': {'handlers': ['structured'], 'level': LOG_LEVEL, 'propagate': False},
        'django': {'handlers': ['console'], 'level': 'WARNING'},
    },
}

# PAN Encryption Key (AES-256)
PAN_ENCRYPTION_KEY = os.getenv('PAN_ENCRYPTION_KEY', 'firmflow_32_byte_secret_key_pan_aes_gcm!')


# ---------------------------------------------------------------------------
# Phase C: sign-in protection, sessions, production safety
# ---------------------------------------------------------------------------
def _env_bool(name, default):
    return os.getenv(name, str(default)).lower() in ('true', '1', 'yes')

LOGIN_MAX_FAILURES = int(os.getenv('LOGIN_MAX_FAILURES', 10))
LOGIN_MAX_FAILURES_PER_IP = int(os.getenv('LOGIN_MAX_FAILURES_PER_IP', 50))
LOGIN_LOCKOUT_MINUTES = int(os.getenv('LOGIN_LOCKOUT_MINUTES', 15))
PASSWORD_RESET_MAX_PER_HOUR = int(os.getenv('PASSWORD_RESET_MAX_PER_HOUR', 5))
PASSWORD_RESET_TIMEOUT = int(os.getenv('PASSWORD_RESET_TIMEOUT_MINUTES', 60)) * 60
# Only turn on behind a proxy (nginx) that sets X-Forwarded-For itself
TRUST_X_FORWARDED_FOR = _env_bool('TRUST_X_FORWARDED_FOR', False)

# A sign-in lasts SESSION_HOURS (default 12) from the sign-in time
SESSION_COOKIE_AGE = int(os.getenv('SESSION_HOURS', 12)) * 3600
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# HTTPS settings. Defaults: on when DEBUG is off. Set SECURE_COOKIES=False only for a test server
# without HTTPS. HSTS stays off (0) until you set HSTS_SECONDS after HTTPS works for every host name.
SESSION_COOKIE_SECURE = _env_bool('SECURE_COOKIES', not DEBUG)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_HSTS_SECONDS = int(os.getenv('HSTS_SECONDS', 0))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('HSTS_INCLUDE_SUBDOMAINS', False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
if _env_bool('USE_X_FORWARDED_PROTO', False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# With DEBUG off, refuse to start with a missing or known (public) key.
_KNOWN_KEYS = {
    'firmflow-insecure-dev-secret-key-replace-in-production',
    'change-this-in-production-firmflow-super-secret-key-at-least-50-chars',
    'firmflow_32_byte_secret_key_pan_aes_gcm!',
    'v8ZlXj6uF2y9qA4p7rT1w0m3k5L8oN2iP4eR6tY8uI0=',
}
if not DEBUG:
    from django.core.exceptions import ImproperlyConfigured
    _problems = []
    if not os.getenv('SECRET_KEY') or SECRET_KEY in _KNOWN_KEYS or len(SECRET_KEY) < 40:
        _problems.append('SECRET_KEY (set a random value of 50+ characters)')
    if not os.getenv('PAN_ENCRYPTION_KEY') or PAN_ENCRYPTION_KEY in _KNOWN_KEYS:
        _problems.append('PAN_ENCRYPTION_KEY (set a random value; keep it safe - PAN data cannot be read without it)')
    if _problems:
        raise ImproperlyConfigured('DEBUG is off, but these settings use a default or example value: ' + '; '.join(_problems))

# Backups (apps/common/backup.py): python manage.py backup_firmflow
BACKUP_DIR = Path(os.getenv('BACKUP_DIR', str(BASE_DIR / 'backups')))
BACKUP_KEEP = int(os.getenv('BACKUP_KEEP', 14))
# Daily backup at 01:30 by Celery beat when on (needs a running beat + worker)
BACKUP_DAILY = _env_bool('BACKUP_DAILY', False)
