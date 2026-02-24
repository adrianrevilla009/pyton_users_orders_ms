"""
=============================================================================
SETTINGS BASE — Configuración compartida por todos los entornos
=============================================================================

Arquitectura de settings:
  config/
    settings_base.py     <- Este archivo (configuración común)
    settings/
      development.py     <- Entorno local (DEBUG=True, SQLite optional)
      staging.py         <- Pre-producción
      production.py      <- Producción (seguro, optimizado)

Patrón: cada entorno importa la base y sobreescribe lo necesario.
"""

import os
from pathlib import Path
from decouple import config, Csv

# =============================================================================
# PATHS
# =============================================================================
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# SEGURIDAD — valores que DEBEN cambiar en producción
# =============================================================================
SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# =============================================================================
# APLICACIONES INSTALADAS
# =============================================================================
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    # API REST
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'oauth2_provider',           # OAuth2
    'corsheaders',               # CORS
    'django_filters',            # Filtros en querysets

    # Documentación
    'drf_spectacular',

    # Métricas
    'django_prometheus',

    # Health Checks
    'health_check',
    'health_check.db',
    'health_check.cache',
    'health_check.storage',

    # Permisos granulares por objeto
    'guardian',
]

LOCAL_APPS = [
    # Nuestras apps Django (los modelos SQL viven aquí)
    'src.infrastructure.persistence.sql',  # Modelos ORM de Django
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# =============================================================================
# MIDDLEWARES
# =============================================================================
# Orden importante: cada middleware envuelve la request/response
MIDDLEWARE = [
    # Prometheus DEBE ir primero para capturar todas las métricas
    'django_prometheus.middleware.PrometheusBeforeMiddleware',

    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',         # CORS antes que Common
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # Middleware personalizado para logging de requests
    'src.infrastructure.security.middleware.RequestLoggingMiddleware',

    # Prometheus cierra el ciclo de métricas
    'django_prometheus.middleware.PrometheusAfterMiddleware',
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

# =============================================================================
# BASE DE DATOS SQL — PostgreSQL (principal)
# =============================================================================
DATABASES = {
    'default': {
        'ENGINE': 'django_prometheus.db.backends.postgresql',  # Wraps psycopg2 + métricas
        'NAME': config('DB_NAME', default='techlead_db'),
        'USER': config('DB_USER', default='techlead_user'),
        'PASSWORD': config('DB_PASSWORD', default='techlead_pass'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'OPTIONS': {
            'connect_timeout': 10,
        },
        # Pool de conexiones: crucial en producción para no agotar conexiones PG
        'CONN_MAX_AGE': 60,  # Reutiliza conexiones durante 60 segundos
    }
}

# =============================================================================
# CACHÉ — Redis
# =============================================================================
CACHES = {
    'default': {
        # django-redis como backend: compatible con la API de caché de Django
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_CACHE_URL', default='redis://localhost:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            # Serializar objetos Python complejos
            'SERIALIZER': 'django_redis.serializers.json.JSONSerializer',
            # Compresión para valores grandes
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            # Timeout de conexión
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
        },
        'TIMEOUT': 300,  # 5 minutos por defecto
        'KEY_PREFIX': 'techlead',  # Prefijo para evitar colisiones
    }
}

# Usar Redis también para las sesiones de Django
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# =============================================================================
# AUTENTICACIÓN Y SEGURIDAD
# =============================================================================

# Hasher de contraseñas: argon2 es el estándar actual (más seguro que bcrypt)
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',  # Fallback
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Modelo de usuario personalizado — siempre mejor definirlo al principio
AUTH_USER_MODEL = 'sql_models.User'  # Nuestro modelo extendido

# Backend de autenticación (django-guardian añade el suyo para permisos por objeto)
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'guardian.backends.ObjectPermissionBackend',  # Permisos por objeto
]

# =============================================================================
# DJANGO REST FRAMEWORK
# =============================================================================
REST_FRAMEWORK = {
    # Autenticación por defecto: JWT (stateless, escalable)
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'oauth2_provider.contrib.rest_framework.OAuth2Authentication',  # OAuth2
        'rest_framework.authentication.SessionAuthentication',  # Para el browsable API
    ],

    # Por defecto requerir autenticación (principio de mínimo acceso)
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],

    # Paginación por defecto
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,

    # Filtros
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],

    # Throttling (rate limiting) — protege contra abuso
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',    # Usuarios anónimos: 100 requests/hora
        'user': '1000/hour',   # Usuarios autenticados: 1000 requests/hora
    },

    # Schema para documentación automática
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',

    # Renderer: JSON por defecto, browsable API en DEBUG
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],

    # Manejo de excepciones personalizado
    'EXCEPTION_HANDLER': 'src.interfaces.api.views.exception_handler.custom_exception_handler',
}

# =============================================================================
# JWT (JSON Web Tokens)
# =============================================================================
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', default=60, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,        # Nuevo refresh token en cada uso
    'BLACKLIST_AFTER_ROTATION': True,      # Invalida el anterior
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': config('JWT_SECRET_KEY', default=SECRET_KEY),
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# =============================================================================
# OAUTH2
# =============================================================================
OAUTH2_PROVIDER = {
    'SCOPES': {
        'read': 'Leer datos',
        'write': 'Escribir datos',
        'admin': 'Acceso administrativo',
    },
    'ACCESS_TOKEN_EXPIRE_SECONDS': 3600,
    'REFRESH_TOKEN_EXPIRE_SECONDS': 86400 * 7,
}

# =============================================================================
# CELERY — Cola de tareas asíncronas
# =============================================================================
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='amqp://guest:guest@localhost:5672/')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/2')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Europe/Madrid'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutos máximo por tarea
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Mejor distribución de tareas
CELERY_ACKS_LATE = True  # Ack solo cuando la tarea termina (más seguro)

# =============================================================================
# KAFKA
# =============================================================================
KAFKA_CONFIG = {
    'bootstrap.servers': config('KAFKA_BOOTSTRAP_SERVERS', default='localhost:9092'),
    'group.id': config('KAFKA_GROUP_ID', default='techlead-consumers'),
    'auto.offset.reset': 'earliest',
    'enable.auto.commit': False,  # Commit manual para mayor control
}

KAFKA_TOPICS = {
    'orders': config('KAFKA_TOPIC_ORDERS', default='orders.events'),
    'payments': config('KAFKA_TOPIC_PAYMENTS', default='payments.events'),
    'notifications': config('KAFKA_TOPIC_NOTIFICATIONS', default='notifications.events'),
}

# =============================================================================
# MONGODB
# =============================================================================
MONGO_URI = config('MONGO_URI', default='mongodb://localhost:27017/')
MONGO_DB_NAME = config('MONGO_DB_NAME', default='techlead_mongo')

# =============================================================================
# REDIS (configuración directa, más allá del caché)
# =============================================================================
REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

# =============================================================================
# STRIPE
# =============================================================================
STRIPE_PUBLIC_KEY = config('STRIPE_PUBLIC_KEY', default='')
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default='')

# =============================================================================
# SENDGRID
# =============================================================================
SENDGRID_API_KEY = config('SENDGRID_API_KEY', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@example.com')

# =============================================================================
# LOGGING ESTRUCTURADO — structlog + python-json-logger
# =============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        # Formato JSON para producción (ingestado por ELK, Datadog, etc.)
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
        },
        # Formato legible para desarrollo
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },

    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'json_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'app.json.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 5,
            'formatter': 'json',
        },
    },

    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },

    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'techlead': {  # Nuestro logger principal
            'handlers': ['console', 'json_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# =============================================================================
# DOCUMENTACIÓN API (drf-spectacular)
# =============================================================================
SPECTACULAR_SETTINGS = {
    'TITLE': 'TechLead Demo API',
    'DESCRIPTION': '''
    API de demostración que implementa DDD, Arquitectura Hexagonal,
    múltiples bases de datos, mensajería, seguridad y más.
    ''',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
    },
}

# =============================================================================
# CORS
# =============================================================================
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',  # React dev server
    'http://localhost:8080',  # Vue dev server
]
CORS_ALLOW_CREDENTIALS = True

# =============================================================================
# ARCHIVOS ESTÁTICOS Y MEDIA
# =============================================================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# =============================================================================
# INTERNACIONALIZACIÓN
# =============================================================================
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'Europe/Madrid'
USE_I18N = True
USE_TZ = True

# =============================================================================
# CAMPO PK POR DEFECTO
# =============================================================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
