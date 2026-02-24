"""
============================================================
SETTINGS - Configuración principal de Django
============================================================
Usa django-environ para leer variables de entorno desde .env
Sigue el patrón 12-factor app para configuración.

En producción: separar en settings/base.py, settings/prod.py, settings/dev.py
============================================================
"""

import environ
import os
import structlog
from pathlib import Path

# Base directory del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# Inicializar environ - lee el archivo .env automáticamente
env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# ============================================================
# CORE DJANGO
# ============================================================
SECRET_KEY = env('SECRET_KEY', default='django-insecure-dev-key-change-me')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

# ============================================================
# APLICACIONES INSTALADAS
# Organizadas por categoría para facilitar la lectura
# ============================================================
INSTALLED_APPS = [
    # Django core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # DRF y documentación
    'rest_framework',
    'drf_spectacular',           # Swagger / OpenAPI
    'corsheaders',               # CORS

    # Seguridad
    'guardian',                  # Permisos a nivel objeto (ABAC/RBAC)

    # Métricas Prometheus - expone /metrics automáticamente
    'django_prometheus',

    # Health checks - expone /health/ con checks configurables
    'health_check',
    'health_check.db',           # Chequea PostgreSQL
    'health_check.cache',        # Chequea Redis
    'health_check.storage',

    # Nuestras apps de dominio
    'apps.users',
    'apps.orders',
    'apps.notifications',
]

# ============================================================
# MIDDLEWARE
# El orden importa: se ejecutan de arriba a abajo en request
# y de abajo a arriba en response
# ============================================================
MIDDLEWARE = [
    # Prometheus DEBE ser el primero y último para medir todo
    'django_prometheus.middleware.PrometheusBeforeMiddleware',

    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',    # CORS antes de CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # Middleware personalizado de logging estructurado
    'shared.infrastructure.monitoring.middleware.RequestLoggingMiddleware',

    # Prometheus al final para capturar el response
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

# ============================================================
# BASE DE DATOS SQL - PostgreSQL
# Usamos dj-database-url para parsear la URL de conexión
# ============================================================
DATABASES = {
    'default': env.db('DATABASE_URL', default='sqlite:///db.sqlite3'),
}
# Habilitar métricas de BD con Prometheus
DATABASES['default']['ENGINE'] = 'django_prometheus.db.backends.postgresql'

# ============================================================
# REDIS - Caché, sesiones, rate limiting
# ============================================================
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://localhost:6379/0'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            # Compresión para valores grandes
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            # Serialización
            'SERIALIZER': 'django_redis.serializers.json.JSONSerializer',
        },
        'KEY_PREFIX': 'techlead',
        'TIMEOUT': 300,  # 5 minutos por defecto
    }
}

# Sesiones en Redis (más rápido que BD)
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# ============================================================
# DJANGO REST FRAMEWORK
# ============================================================
REST_FRAMEWORK = {
    # Autenticación JWT por defecto
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    # Requiere autenticación por defecto (más seguro)
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    # Paginación global
    'DEFAULT_PAGINATION_CLASS': 'shared.infrastructure.pagination.StandardPagination',
    'PAGE_SIZE': 20,
    # Throttling (rate limiting) via Redis
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
    # Documentación automática
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Filtros y búsqueda
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    # Renderer: JSON en producción, browsable en dev
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ] if DEBUG else [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# ============================================================
# JWT CONFIGURATION
# ============================================================
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(
        minutes=env.int('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', default=60)
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        days=env.int('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7)
    ),
    'ROTATE_REFRESH_TOKENS': True,          # Rota el refresh token en cada uso
    'BLACKLIST_AFTER_ROTATION': True,       # Invalida el anterior
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# ============================================================
# SEGURIDAD - Headers HTTP
# ============================================================
# En producción, activar estos headers:
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000          # 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'

CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[
    'http://localhost:3000',
    'http://localhost:8080',
])

# ============================================================
# CUSTOM USER MODEL
# Siempre mejor definirlo desde el inicio del proyecto
# ============================================================
AUTH_USER_MODEL = 'users.User'

# Guardian para permisos a nivel de objeto
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'guardian.backends.ObjectPermissionBackend',   # ABAC
]

# ============================================================
# CELERY - Cola de tareas asíncronas
# ============================================================
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='amqp://guest:guest@localhost:5672/')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default='redis://localhost:6379/1')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
# Reintentos automáticos
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# ============================================================
# KAFKA CONFIGURATION
# ============================================================
KAFKA_CONFIG = {
    'bootstrap_servers': env('KAFKA_BOOTSTRAP_SERVERS', default='localhost:9092'),
    'topics': {
        'orders': env('KAFKA_TOPIC_ORDERS', default='orders.events'),
        'notifications': env('KAFKA_TOPIC_NOTIFICATIONS', default='notifications.events'),
    },
    'consumer_group': 'techlead-consumer-group',
}

# ============================================================
# MONGODB CONFIGURATION (NoSQL)
# Para datos no estructurados: logs de actividad, eventos, etc.
# ============================================================
MONGODB_CONFIG = {
    'host': env('MONGODB_HOST', default='localhost'),
    'port': env.int('MONGODB_PORT', default=27017),
    'db': env('MONGODB_DB', default='techlead_nosql'),
}

# ============================================================
# LOGGING ESTRUCTURADO con structlog
# Produce logs en formato JSON para ingestión en ELK/Datadog
# ============================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': structlog.stdlib.ProcessorFormatter,
            'processor': structlog.processors.JSONRenderer(),
        },
        'console': {
            '()': structlog.stdlib.ProcessorFormatter,
            'processor': structlog.dev.ConsoleRenderer(),
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console' if DEBUG else 'json',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs/app.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'json',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'apps': {'handlers': ['console', 'file'], 'level': 'DEBUG', 'propagate': False},
        'shared': {'handlers': ['console', 'file'], 'level': 'DEBUG', 'propagate': False},
    },
}

# Configuración de structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,        # Variables de contexto (request_id, user_id)
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt='iso'),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# ============================================================
# SPECTACULAR (Swagger / OpenAPI)
# ============================================================
SPECTACULAR_SETTINGS = {
    'TITLE': 'Tech Lead Demo API',
    'DESCRIPTION': 'API REST con DDD, Arquitectura Hexagonal, seguridad, métricas y más',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
    },
}

# ============================================================
# HEALTH CHECKS
# ============================================================
HEALTH_CHECK = {
    'DISK_USAGE_MAX': 90,    # Alerta si disco > 90%
    'MEMORY_MIN': 100,       # Alerta si RAM libre < 100MB
}

# ============================================================
# STATIC & MEDIA
# ============================================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ============================================================
# INTERNACIONALIZACIÓN
# ============================================================
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

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
