from pathlib import Path
import os
import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

BASE_DIR = Path(__file__).resolve().parent.parent

# Try to get parameters from SSM if configured, otherwise rely on env vars
def get_ssm_param(name, default=None):
    try:
        ssm = boto3.client('ssm', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
        return ssm.get_parameter(Name=name, WithDecryption=True)['Parameter']['Value']
    except (BotoCoreError, ClientError, NoCredentialsError):
        return default

prefix = 'iooding'

# Fetch required secrets - prioritize env vars, then SSM
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or get_ssm_param(f'{prefix}_django_secret_key') or 'django-insecure-local-dev-key'
DB_PASSWORD = os.environ.get('DB_PASSWORD') or get_ssm_param(f'{prefix}_db_password') or 'postgres'

DEBUG = os.environ.get("DEBUG", "False") == "True"
# In a container/K8s environment, the Ingress (Nginx) handles domain security.
# Using '*' allows K8s health checks and various internal IPs to work without complex scripts.
ALLOWED_HOSTS = ['*']
SITE_ID = 1

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    'blog',
    'django_ckeditor_5',
    'taggit',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

ROOT_URLCONF = 'iooding.urls'

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

WSGI_APPLICATION = 'iooding.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.postgresql'),
        'NAME': os.environ.get('DB_NAME', 'iooding'),
        'USER': os.environ.get('DB_USER', 'iooding'),
        'PASSWORD': DB_PASSWORD,
        'HOST': os.environ.get('DB_HOST', 'postgres'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'OPTIONS': {
            'connect_timeout': 5,
        }
    },
    'ai': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('AI_DB_NAME', 'iooding_ai'),
        'USER': os.environ.get('AI_DB_USER', 'iooding'),
        'PASSWORD': os.environ.get('AI_DB_PASSWORD', DB_PASSWORD),
        'HOST': os.environ.get('AI_DB_HOST', 'postgres-ai'),
        'PORT': os.environ.get('AI_DB_PORT', '5432'),
        'OPTIONS': {
            'connect_timeout': 5,
        }
    }
}

DATABASE_ROUTERS = ['blog.db_routers.AIRouter']


# Redis Configuration
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get('REDIS_URL', "redis://redis:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "iooding",
    }
}

# Use Redis for sessions with DB fallback
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

SESSION_COOKIE_AGE = 1209600  # 2 weeks
SESSION_COOKIE_HTTPONLY = True

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# CKEditor 5 Configuration
CKEDITOR_5_CONFIGS = {
    'default': {
        'toolbar': {
            'items': ['heading', '|', 'bold', 'italic', 'link',
                      'bulletedList', 'numberedList', 'blockQuote', 'imageUpload', ],
        }
    },
    'extends': {
        'toolbar': {
            'items': ['heading', '|', 'bold', 'italic', 'link',
                      'bulletedList', 'numberedList', 'blockQuote', 'imageUpload', ],
        }
    }
}

# Trust the ingress-nginx proxy
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Security settings
# In production (DEBUG=False), we want these True.
# In local (DEBUG=True), we might want them False if not using https locally.
HTTPS_ENABLED = os.environ.get('HTTPS_ENABLED', 'False') == 'True'

SECURE_SSL_REDIRECT = not DEBUG or HTTPS_ENABLED
SESSION_COOKIE_SECURE = not DEBUG or HTTPS_ENABLED
CSRF_COOKIE_SECURE = not DEBUG or HTTPS_ENABLED

SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# Security Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Trusted origins for CSRF
CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS', "https://iooding.local").split(',')

# Cookie settings
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_NAME = 'iooding_sessionid'
CSRF_COOKIE_NAME = 'iooding_csrftoken'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Logging configuration for Kubernetes (stdout)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}