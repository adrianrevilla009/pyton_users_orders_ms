"""
=============================================================================
SETTINGS DE DESARROLLO
=============================================================================
Importa la configuración base y activa herramientas de desarrollo.
"""
from config.settings_base import *  # noqa

DEBUG = True

# En desarrollo aceptamos cualquier host
ALLOWED_HOSTS = ['*']

# Browsable API de DRF en desarrollo
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
    'rest_framework.renderers.BrowsableAPIRenderer',  # Solo en dev
]

# Relajamos el throttling en desarrollo
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': '10000/hour',
    'user': '100000/hour',
}

# CORS permisivo en desarrollo
CORS_ALLOW_ALL_ORIGINS = True

# Django Debug Toolbar (opcional, comentado para simplicidad)
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']

# Mostrar emails en consola en vez de enviarlos realmente
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Logging más verboso
LOGGING['root']['level'] = 'DEBUG'
