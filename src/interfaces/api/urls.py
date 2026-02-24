"""
=============================================================================
URLS DE LA API v1
=============================================================================

Router central de todos los endpoints de la API.
Organizado por dominios de negocio.
"""
from django.urls import path, include

urlpatterns = [
    # Autenticación y registro
    path('auth/', include('src.interfaces.api.urls_auth')),

    # Usuarios (CRUD)
    path('users/', include('src.interfaces.api.urls_users')),

    # Productos y catálogo
    path('products/', include('src.interfaces.api.urls_products')),

    # Pedidos
    path('orders/', include('src.interfaces.api.urls_orders')),

    # Pagos
    path('payments/', include('src.interfaces.api.urls_payments')),

    # Health checks propios (además de django-health-check)
    path('health/', include('src.interfaces.api.urls_health')),
]
