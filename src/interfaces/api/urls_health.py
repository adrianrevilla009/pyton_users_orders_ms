"""URLs de health checks."""
from django.urls import path
from src.interfaces.api.views.health_views import liveness, readiness, health_detail

urlpatterns = [
    path('live/', liveness, name='health-live'),
    path('ready/', readiness, name='health-ready'),
    path('detail/', health_detail, name='health-detail'),
]
