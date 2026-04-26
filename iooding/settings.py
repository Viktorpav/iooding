from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Environment (django-environ) ────────────────────────────────────────────
# Reads from .env file in local dev; from K8s env vars in production.
env = environ.Env(
    DEBUG=(bool, False),
    CONN_MAX_AGE=(int, 0),
    ALLOWED_HOSTS=(list, ['iooding.local']),
    LM_STUDIO_COMPLETION_MODEL=(str, 'local-model'),
    LM_STUDIO_EMBEDDING_MODEL=(str, 'nomic-embed-text'),
)
environ.Env.read_env(BASE_DIR / '.env', overrides=False)

# ─── Core secrets (injected by Sealed Secrets → K8s Secret → env) ────────────
SECRET_KEY = env('DJANGO_SECRET_KEY', default='django-insecure-local-dev-key')
DEBUG = env('DEBUG')

# Ingress-nginx handles external hostname validation; ALLOWED_HOSTS adds defense-in-depth.
ALLOWED_HOSTS = env('ALLOWED_HOSTS')
SITE_ID = 1

# ─── AI / LM Studio ──────────────────────────────────────────────────────────
LM_STUDIO_HOST = env('LM_STUDIO_HOST', default='http://192.168.0.16:1234/v1')
LM_STUDIO_API_KEY = env('LM_STUDIO_API_KEY', default='lm-studio')
LM_STUDIO_COMPLETION_MODEL = env('LM_STUDIO_COMPLETION_MODEL')
LM_STUDIO_EMBEDDING_MODEL = env('LM_STUDIO_EMBEDDING_MODEL')

# ─── Applications ─────────────────────────────────────────────────────────────
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

# ─── Middleware ────────────────────────────────────────────────────────────────
# WhiteNoise must come directly after SecurityMiddleware for best performance.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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

# ─── Database (single PostgreSQL) ─────────────────────────────────────────────
db_password = env('DB_PASSWORD', default='postgres')
default_db_url = f'postgres://iooding:{db_password}@postgres:5432/iooding'

DATABASES = {
    'default': {
        **env.db('DATABASE_URL', default=default_db_url),
        'OPTIONS': {
            'connect_timeout': 5,
        },
        # Persistent connections for ASGI workers — avoid per-request TCP overhead.
        # None = keep alive for the lifetime of the worker process.
        'CONN_MAX_AGE': None,
        'CONN_HEALTH_CHECKS': True,  # Django 5.1+ validates stale connections
    }
}

# ─── Cache (Redis) ────────────────────────────────────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://redis:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'IGNORE_EXCEPTIONS': True,   # degrade gracefully if Redis is down
        },
        'KEY_PREFIX': 'iooding',
        'TIMEOUT': 300,
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 1_209_600   # 2 weeks
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_NAME = 'iooding_sessionid'
SESSION_COOKIE_SAMESITE = 'Lax'

# ─── Password validation ───────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ─── Static & Media ───────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ─── CKEditor 5 ───────────────────────────────────────────────────────────────
CKEDITOR_5_CONFIGS = {
    'default': {
        'toolbar': {
            'items': ['heading', '|', 'bold', 'italic', 'link',
                      'bulletedList', 'numberedList', 'blockQuote', 'imageUpload'],
        }
    },
    'extends': {
        'blockToolbar': [
            'paragraph', 'heading1', 'heading2', 'heading3',
            '|', 'bulletedList', 'numberedList', 'blockQuote',
        ],
        'toolbar': {
            'items': [
                'heading', '|', 'bold', 'italic', 'link', 'underline', 'strikethrough',
                'code', 'codeBlock', '|', 'fontSize', 'fontColor', '|',
                'bulletedList', 'numberedList', 'todoList', '|',
                'outdent', 'indent', '|', 'alignment', '|',
                'imageUpload', 'blockQuote', 'insertTable', 'sourceEditing',
            ],
            'shouldNotGroupWhenFull': True,
        },
        'codeBlock': {
            'languages': [
                {'language': 'python',     'label': 'Python'},
                {'language': 'javascript', 'label': 'JavaScript'},
                {'language': 'html',       'label': 'HTML'},
                {'language': 'css',        'label': 'CSS'},
                {'language': 'yaml',       'label': 'YAML'},
                {'language': 'bash',       'label': 'Bash'},
            ]
        },
    },
}

# ─── Proxy & Security ─────────────────────────────────────────────────────────
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

_production = not DEBUG
SECURE_SSL_REDIRECT          = _production
SESSION_COOKIE_SECURE        = _production
CSRF_COOKIE_SECURE           = _production
SECURE_BROWSER_XSS_FILTER    = True
SECURE_CONTENT_TYPE_NOSNIFF  = True
SECURE_HSTS_SECONDS          = 31_536_000 if _production else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = _production
SECURE_HSTS_PRELOAD          = _production
X_FRAME_OPTIONS              = 'DENY'

CSRF_COOKIE_SAMESITE    = 'Lax'
CSRF_COOKIE_NAME        = 'iooding_csrftoken'
CSRF_TRUSTED_ORIGINS    = env('CSRF_TRUSTED_ORIGINS', default='https://iooding.local').split(',')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Logging (structured JSON → stdout → cluster log aggregation) ─────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.json.JsonFormatter',
            'format': '%(levelname)s %(asctime)s %(module)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',   # suppress SQL noise in production
            'propagate': False,
        },
    },
}