"""
============================================================
URLs PRINCIPALES
============================================================
Centraliza todas las rutas de la aplicación.
Patrón recomendado: cada app gestiona sus propias URLs
y aquí solo se incluyen.
============================================================
"""

from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    # Admin de Django
    path('admin/', admin.site.urls),

    # ---- API v1 ----
    path('api/v1/', include([
        # Autenticación (JWT)
        path('auth/', include('apps.users.infrastructure.urls.auth_urls')),

        # Recursos de negocio
        path('users/', include('apps.users.infrastructure.urls.user_urls')),
        path('orders/', include('apps.orders.infrastructure.urls')),
        path('notifications/', include('apps.notifications.infrastructure.urls')),
    ])),

    # ---- Infraestructura ----

    # Health checks: GET /health/ -> estado de BD, Redis, etc.
    path('health/', include('health_check.urls')),

    # Métricas Prometheus: GET /metrics -> scrapeado por Prometheus
    path('', include('django_prometheus.urls')),

    # Documentación API (Swagger / ReDoc)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
