"""
=============================================================================
EventBus In-Memory — Para tests y desarrollo
=============================================================================

Implementación del puerto EventBus que guarda los eventos en memoria.
Fundamental para tests unitarios: no necesita Kafka real.

Patrón: Fake/Stub — implementación simplificada para tests.
"""
from src.domain.events.base import DomainEvent
from src.application.ports.event_bus import EventBus


class InMemoryEventBus(EventBus):
    """
    EventBus en memoria para tests.
    Permite verificar qué eventos se publicaron.
    """

    def __init__(self):
        self.published_events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.published_events.append(event)

    def publish_many(self, events: list[DomainEvent]) -> None:
        self.published_events.extend(events)

    def get_events_of_type(self, event_type: type) -> list[DomainEvent]:
        """Helper para tests: obtiene eventos de un tipo específico."""
        return [e for e in self.published_events if isinstance(e, event_type)]

    def clear(self) -> None:
        self.published_events.clear()
