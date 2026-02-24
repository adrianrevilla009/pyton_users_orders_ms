"""
Configuración global de pytest.
Los fixtures definidos aquí están disponibles en todos los tests.
"""
import pytest
import django
from django.conf import settings


@pytest.fixture
def in_memory_event_bus():
    """Fixture: EventBus en memoria para tests."""
    from src.infrastructure.messaging.in_memory_event_bus import InMemoryEventBus
    return InMemoryEventBus()


@pytest.fixture
def fake_notification_service():
    """Fixture: Servicio de notificaciones fake."""
    from src.infrastructure.external_apis.sendgrid_service import ConsoleNotificationService
    return ConsoleNotificationService()
