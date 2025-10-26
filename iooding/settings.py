from pathlib import Path
import os
import boto3

BASE_DIR = Path(__file__).resolve().parent.parent

ssm = boto3.client('ssm')

prefix = 'iooding'

# Fetch required secrets directly
SECRET_KEY = ssm.get_parameter(
    Name=f'{prefix}_django_secret_key',
    WithDecryption=True
)['Parameter']['Value']

DB_PASSWORD_PARAM = ssm.get_parameter(
    Name=f'{prefix}_db_password',
    WithDecryption=True
)['Parameter']['Value']

DEBUG = os.environ.get("DEBUG", "False") == "True"
ALLOWED_HOSTS = ['iooding.local', '192.168.0.100']
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
    'ckeditor5',
    'ckeditor_uploader',
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

# Database - PostgreSQL in k8s
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'iooding',
        'USER': 'iooding',
        'PASSWORD': DB_PASSWORD_PARAM,
        'HOST': 'postgres',
        'PORT': '5432',
    }
}

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

# CKEditor configuration
CKEDITOR5_CONFIGS = {
    'default': {
        'toolbar': [
            'heading', '|', 'bold', 'italic', 'link', 
            'bulletedList', 'numberedList', 'blockQuote'
        ],
        'height': 400,
    }
}

# Trust the ingress-nginx proxy
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Session - keep it simple
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

# CSRF - keep it simple  
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = ['https://iooding.local']

# Let ingress handle HTTPS redirects, not Django
SECURE_SSL_REDIRECT = False

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'