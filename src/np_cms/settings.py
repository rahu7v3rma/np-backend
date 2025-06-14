"""
Django settings for np_cms project.

Generated by 'django-admin startproject' using Django 4.0.5.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.1/ref/settings/
"""

import os
from pathlib import Path

import environ


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    ALLOWED_CIDR_NETS=(list, []),
    SECURE_PROXY_SSL_HEADER_NAME=(str, ''),
    DJANGO_LOG_LEVEL=(str, 'INFO'),
    CORS_ALLOW_ALL_ORIGINS=(bool, False),
    CORS_ALLOWED_ORIGINS=(list, []),
    IMAGE_STORAGE_BUCKET_NAME=(str, ''),
    IMAGE_STORAGE_PREFIX=(str, ''),
    IMAGE_STORAGE_BASE_RETRIEVE_URL=(str, ''),
    DATA_STORAGE_BUCKET_NAME=(str, ''),
    DATA_STORAGE_ENDPOINT_URL=(str, None),
    AWS_S3_REGION_NAME=(str, None),
    DEFAULT_FROM_EMAIL=(str, ''),
    REPLY_TO_EMAIL=(str, ''),
    EMAIL_FROM=(str, ''),
    EMAIL_HOST_USER=(str, ''),
    AWS_SES_REGION_NAME=(str, None),
    AWS_SES_REGION_ENDPOINT=(str, None),
    INNER_AUTHORIZATION_KEYS=(list, []),
    STATIC_ROOT=(str, ''),
    SERVE_STATIC=(bool, False),
    MEDIA_ROOT=(str, os.path.join(BASE_DIR, 'media')),
    OTP_ADMIN_ENABLED=(bool, False),
    OTP_FERNET_KEY=(str, None),
    JWT_SECRET_KEY=(str, None),
    JWT_ALGORITHM=(str, None),
    JWT_EXPIRY_DAYS=(int, 7),
    DATA_UPLOAD_MAX_NUMBER_FIELDS=(int, 1000),
    GROW_BASE_URL=(str, None),
    GROW_PAGE_CODE=(str, None),
    GROW_USER_ID=(str, None),
    GROW_API_KEY=(str, None),
    GROW_WEBHOOK_SECRET=(str, None),
    EMPLOYEE_SITE_BASE_URL=(str, 'http://localhost:8000'),
    SMS_ACTIVETRAIL_BASE_URL=(str, None),
    SMS_ACTIVETRAIL_API_KEY=(str, None),
    CELERY_BROKER_URL=(str, ''),
    CELERY_RESULT_BACKEND=(str, 'django-db'),
    CELERY_TASK_ALWAYS_EAGER=(bool, True),
    ORIAN_BASE_URL=(str, None),
    ORIAN_API_TOKEN=(str, None),
    ORIAN_CONSIGNEE=(str, None),
    ORIAN_ID_PREFIX=(str, ''),
    ORIAN_MESSAGE_TIMEZONE_NAME=(str, None),
    ORIAN_DUMMY_CUSTOMER_PLATFORM_ID=(int, None),
    ORIAN_DUMMY_CUSTOMER_COMPANY_STREET=(str, None),
    ORIAN_DUMMY_CUSTOMER_COMPANY_STREET_NUMBER=(str, None),
    ORIAN_DUMMY_CUSTOMER_COMPANY_CITY=(str, None),
    ORIAN_DUMMY_CUSTOMER_COMPANY_PHONE_NUMBER=(str, None),
    ORIAN_RABBITMQ_HOST=(str, None),
    ORIAN_RABBITMQ_PORT=(int, None),
    ORIAN_RABBITMQ_VIRTUAL_HOST=(str, None),
    ORIAN_RABBITMQ_USER=(str, None),
    ORIAN_RABBITMQ_PASSWORD=(str, None),
    ORIAN_SFTP_HOST=(str, None),
    ORIAN_SFTP_PORT=(int, None),
    ORIAN_SFTP_USER=(str, None),
    ORIAN_SFTP_PASSWORD=(str, None),
    ORIAN_SFTP_SNAPSHOTS_DIR=(str, None),
    PAP_INBOUND_URL=(str, None),
    PAP_OUTBOUND_URL=(str, None),
    PAP_CONSIGNEE=(str, None),
    PAP_ID_PREFIX=(str, ''),
    PAP_MESSAGE_TIMEZONE_NAME=(str, None),
    PAP_VERBOSE=(bool, False),
    CC_RECIPIENT_EMAILS=(list, []),
    REPLY_TO_ADDRESSES_EMAILS=(list, []),
    STOCK_LIMIT_THRESHOLD=(int, None),
    TAX_PERCENT=(int, 0),
    LOGISTICS_PROVIDER_AUTHENTICATION_KEYS=(dict, {}),
)

# read environ variables from .env file
environ.Env.read_env(
    os.environ.get('DOTENV_FILE', os.path.join(BASE_DIR, '..', '.env'))
)

DEBUG = env('DEBUG')

ALLOWED_HOSTS = env('ALLOWED_HOSTS')
ALLOWED_CIDR_NETS = env('ALLOWED_CIDR_NETS')

# local ip is added if needed so health check requests can go through
allowed_local_ip = os.environ.get('ALLOWED_LOCAL_IP')
if allowed_local_ip:
    ALLOWED_HOSTS.append(allowed_local_ip)

# cookies should be https-only in production. will fail if setting is not
# set at all
CSRF_COOKIE_SECURE = env('HTTPS')
SESSION_COOKIE_SECURE = env('HTTPS')

# raises django's ImproperlyConfigured if SECRET_KEY is not available in
# env or file
SECRET_KEY = env('SECRET_KEY')

# Application definition
INSTALLED_APPS = [
    'modeltranslation',
    'custom_admin.apps.CustomAdminConfigSite',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.forms',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'formtools',
    'django_js_reverse',
    'webpack_loader',
    'django_celery_results',
    'dal',
    'dal_select2',
    'health',
    'common',
    'user_management',
    'user_profile',
    'storages',
    'django_ses',
    'colorfield',
    'inventory',
    'campaign',
    'payment',
    'export',
    'logistics',
    'nested_inline',
    'django_admin_inline_paginator',
]

MIDDLEWARE = [
    'allow_cidr.middleware.AllowCIDRMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'np_cms.urls'

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
                'django.template.context_processors.i18n',
            ],
        },
    },
]

WSGI_APPLICATION = 'np_cms.wsgi.application'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '{levelname} {asctime} {name} {message}',
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
            'level': env('DJANGO_LOG_LEVEL'),
            'propagate': False,
        },
    },
}

# Database
# https://docs.djangoproject.com/en/4.0/ref/settings/#databases
DATABASES = {}

if DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / '..' / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env('DATABASE_NAME'),
            'USER': env('DATABASE_USER'),
            'PASSWORD': env('DATABASE_PASS'),
            'HOST': env('DATABASE_HOST'),
            'PORT': env('DATABASE_PORT'),
        }
    }


# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': (
            'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'
        ),
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Jerusalem'

USE_I18N = True

USE_TZ = True

DATE_INPUT_FORMATS = ['%d-%m-%Y']

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = env('STATIC_ROOT')
SERVE_STATIC = env('SERVE_STATIC')

STATICFILES_DIRS = (
    (
        os.path.join('admin', 'campaign', 'webpack_bundles'),
        os.path.join(BASE_DIR, '..', 'js', 'webpack_bundles'),
    ),
)

# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# django-rest-framework settings
REST_FRAMEWORK = {
    'DEFAULT_PARSER_CLASSES': ['rest_framework.parsers.JSONParser'],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication'
    ],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
}

CORS_ALLOW_ALL_ORIGINS = env('CORS_ALLOW_ALL_ORIGINS')
CORS_ALLOWED_ORIGINS = env('CORS_ALLOWED_ORIGINS')
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-authorization',
]

MEDIA_URL = 'media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

if DEBUG:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'exports': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'logistics': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
else:
    STORAGES = {
        'default': {
            'BACKEND': 'lib.storage.AllaPrimaStorage',
            'OPTIONS': {
                'bucket_name': env('IMAGE_STORAGE_BUCKET_NAME'),
                'location': env('IMAGE_STORAGE_PREFIX'),
                'base_retrieve_url': env('IMAGE_STORAGE_BASE_RETRIEVE_URL'),
            },
        },
        'exports': {
            'BACKEND': 'storages.backends.s3.S3Storage',
            'OPTIONS': {
                'bucket_name': env('DATA_STORAGE_BUCKET_NAME'),
                'location': 'exports',
                'endpoint_url': env('DATA_STORAGE_ENDPOINT_URL'),
                'querystring_expire': 60,
            },
        },
        'logistics': {
            'BACKEND': 'storages.backends.s3.S3Storage',
            'OPTIONS': {
                'bucket_name': env('DATA_STORAGE_BUCKET_NAME'),
                'location': 'logistics',
                'endpoint_url': env('DATA_STORAGE_ENDPOINT_URL'),
                'querystring_expire': 60,
            },
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }

AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME')

EMAIL_BACKEND = 'django_ses.SESBackend'
EMAIL_HOST_USER = EMAIL_FROM = DEFAULT_FROM_EMAIL = env('EMAIL_FROM')
REPLY_TO_EMAIL = env('REPLY_TO_EMAIL')
AWS_SES_REGION_NAME = env('AWS_SES_REGION_NAME')
AWS_SES_REGION_ENDPOINT = env('AWS_SES_REGION_ENDPOINT')

SECURE_PROXY_SSL_HEADER = None
if env('SECURE_PROXY_SSL_HEADER_NAME'):
    SECURE_PROXY_SSL_HEADER = (env('SECURE_PROXY_SSL_HEADER_NAME'), 'https')

INNER_AUTHORIZATION_KEYS = env('INNER_AUTHORIZATION_KEYS')

# expiry interval for otp token
OTP_INTERVAL = 300
BASE_RESET_PASSWORD_URL = ''

# one time passwords
OTP_ADMIN_ENABLED = env('OTP_ADMIN_ENABLED')
OTP_FERNET_KEY = env('OTP_FERNET_KEY')

JWT_SECRET_KEY = env('JWT_SECRET_KEY')
JWT_ALGORITHM = env('JWT_ALGORITHM')
JWT_EXPIRY_DAYS = env('JWT_EXPIRY_DAYS')

GROW_BASE_URL = env('GROW_BASE_URL')
GROW_PAGE_CODE = env('GROW_PAGE_CODE')
GROW_USER_ID = env('GROW_USER_ID')
GROW_API_KEY = env('GROW_API_KEY')
# must be alpha-numeric otherwise grow trim it
GROW_WEBHOOK_SECRET = env('GROW_WEBHOOK_SECRET')

EMPLOYEE_SITE_BASE_URL = env('EMPLOYEE_SITE_BASE_URL')


# TRANSLATION SETTINGS
def gettext(s):
    return s


# this sets the languages the admin site is available in, and should only allow
# English
LANGUAGES = (('en', gettext('English')),)

MODELTRANSLATION_LANGUAGES = ('en', 'he')
MODELTRANSLATION_FALLBACK_LANGUAGES = {
    'default': ('en',),  # Fallback to English
}
MODELTRANSLATION_AUTO_POPULATE = True

FORM_RENDERER = 'django.forms.renderers.TemplatesSetting'

WEBPACK_LOADER = {
    'DEFAULT': {
        'BUNDLE_DIR_NAME': 'admin/campaign/webpack_bundles/',
        'CACHE': not DEBUG,
        'STATS_FILE': os.path.join(BASE_DIR, '..', 'js', 'webpack-stats.json'),
        'POLL_INTERVAL': 0.1,
        'IGNORE': [r'.+\.hot-update.js', r'.+\.map'],
    }
}

SMS_ACTIVETRAIL_BASE_URL = env('SMS_ACTIVETRAIL_BASE_URL')
SMS_ACTIVETRAIL_API_KEY = env('SMS_ACTIVETRAIL_API_KEY')

# celery settings
CELERY_BROKER_URL = env('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND')
CELERY_TASK_ALWAYS_EAGER = env('CELERY_TASK_ALWAYS_EAGER')
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ['json', 'pickle']

DATA_UPLOAD_MAX_NUMBER_FILES = 300
DATA_UPLOAD_MAX_NUMBER_FIELDS = env('DATA_UPLOAD_MAX_NUMBER_FIELDS')

# orian logistics center api settings
ORIAN_BASE_URL = env('ORIAN_BASE_URL')
ORIAN_API_TOKEN = env('ORIAN_API_TOKEN')
ORIAN_CONSIGNEE = env('ORIAN_CONSIGNEE')
ORIAN_ID_PREFIX = env('ORIAN_ID_PREFIX')
ORIAN_MESSAGE_TIMEZONE_NAME = env('ORIAN_MESSAGE_TIMEZONE_NAME')
ORIAN_DUMMY_CUSTOMER_PLATFORM_ID = env('ORIAN_DUMMY_CUSTOMER_PLATFORM_ID')
ORIAN_DUMMY_CUSTOMER_COMPANY_STREET = env('ORIAN_DUMMY_CUSTOMER_COMPANY_STREET')
ORIAN_DUMMY_CUSTOMER_COMPANY_STREET_NUMBER = env(
    'ORIAN_DUMMY_CUSTOMER_COMPANY_STREET_NUMBER'
)
ORIAN_DUMMY_CUSTOMER_COMPANY_CITY = env('ORIAN_DUMMY_CUSTOMER_COMPANY_CITY')
ORIAN_DUMMY_CUSTOMER_COMPANY_PHONE_NUMBER = env(
    'ORIAN_DUMMY_CUSTOMER_COMPANY_PHONE_NUMBER'
)
ORIAN_RABBITMQ_HOST = env('ORIAN_RABBITMQ_HOST')
ORIAN_RABBITMQ_PORT = env('ORIAN_RABBITMQ_PORT')
ORIAN_RABBITMQ_VIRTUAL_HOST = env('ORIAN_RABBITMQ_VIRTUAL_HOST')
ORIAN_RABBITMQ_USER = env('ORIAN_RABBITMQ_USER')
ORIAN_RABBITMQ_PASSWORD = env('ORIAN_RABBITMQ_PASSWORD')
ORIAN_SFTP_HOST = env('ORIAN_SFTP_HOST')
ORIAN_SFTP_PORT = env('ORIAN_SFTP_PORT')
ORIAN_SFTP_USER = env('ORIAN_SFTP_USER')
# remove prefix from sftp password setting to support strings starting with
# '$'. this can be done with `escape_proxy`, but may affect existing values
# containing dollar signs
PREFIXED_ORIAN_SFTP_PASSWORD = env('ORIAN_SFTP_PASSWORD')
if PREFIXED_ORIAN_SFTP_PASSWORD:
    ORIAN_SFTP_PASSWORD = PREFIXED_ORIAN_SFTP_PASSWORD.removeprefix('!')
else:
    ORIAN_SFTP_PASSWORD = PREFIXED_ORIAN_SFTP_PASSWORD
ORIAN_SFTP_SNAPSHOTS_DIR = env('ORIAN_SFTP_SNAPSHOTS_DIR')

PAP_INBOUND_URL = env('PAP_INBOUND_URL')
PAP_OUTBOUND_URL = env('PAP_OUTBOUND_URL')
PAP_CONSIGNEE = env('PAP_CONSIGNEE')
PAP_ID_PREFIX = env('PAP_ID_PREFIX')
PAP_MESSAGE_TIMEZONE_NAME = env('PAP_MESSAGE_TIMEZONE_NAME')
PAP_VERBOSE = env('PAP_VERBOSE')

# we currently have only one active logistics center and it is set here so that
# we know which one to use when sending out orders and purchase orders. in the
# future we may support multiple active centers, in which case suppliers or
# products will direct us which center should be used. the value here must
# match the value of one of the LogisticsCenterEnum options
ACTIVE_LOGISTICS_CENTER = 'Pick and Pack'

CC_RECIPIENT_EMAILS = env('CC_RECIPIENT_EMAILS')
REPLY_TO_ADDRESSES_EMAILS = env('REPLY_TO_ADDRESSES_EMAILS')

# The products stock level at which
# an alert should be triggered.
STOCK_LIMIT_THRESHOLD = env('STOCK_LIMIT_THRESHOLD') or 0

try:
    TAX_PERCENT = int(env('TAX_PERCENT')) or 0
    TAX_PERCENT = TAX_PERCENT if 100 >= TAX_PERCENT >= 0 else 0
except ValueError:
    TAX_PERCENT = 0

LOGISTICS_PROVIDER_AUTHENTICATION_KEYS = env('LOGISTICS_PROVIDER_AUTHENTICATION_KEYS')
