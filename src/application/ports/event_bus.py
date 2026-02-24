"""
=============================================================================
PUERTO: EventBus
=============================================================================

Interface para publicar eventos de dominio.
Las implementaciones concretas usan Kafka, RabbitMQ o un bus in-memory.
"""
from abc import ABC, abstractmethod
from src.domain.events.base import DomainEvent


class EventBus(ABC):
    """Puerto de salida para publicar eventos de dominio."""

    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        """Publica un evento. Puede ser síncrono o asíncrono."""
        ...

    @abstractmethod
    def publish_many(self, events: list[DomainEvent]) -> None:
        """Publica múltiples eventos de forma eficiente."""
        ...
