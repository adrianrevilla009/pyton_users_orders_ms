"""
=============================================================================
SETTINGS DE PRODUCCIÓN
=============================================================================
Configuración segura y optimizada para producción.
"""
from config.settings_base import *  # noqa
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from decouple import config

DEBUG = False

# Seguridad HTTP — IMPORTANTE en producción
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000          # 1 año
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True              # Forzar HTTPS
SESSION_COOKIE_SECURE = True            # Cookies solo por HTTPS
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'

# Sentry — monitorización de errores en producción
sentry_sdk.init(
    dsn=config('SENTRY_DSN', default=''),
    integrations=[DjangoIntegration()],
    traces_sample_rate=0.1,  # 10% de transacciones para performance
    send_default_pii=False,  # No enviar datos personales a Sentry
)

# Logging JSON en producción (para ELK, Datadog, etc.)
LOGGING['handlers']['console']['formatter'] = 'json'
LOGGING['root']['level'] = 'WARNING'
