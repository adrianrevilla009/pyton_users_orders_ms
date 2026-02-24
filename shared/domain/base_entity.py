"""
============================================================
BASE ENTITY - Clase base para todas las entidades de dominio
============================================================
En DDD:
- Entidad: tiene identidad única y ciclo de vida propio
- Value Object: sin identidad, definido por sus atributos
- Aggregate Root: entidad principal de un grupo de entidades
- Domain Event: algo que ocurrió en el dominio (pasado inmutable)
============================================================
"""

import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Any


@dataclass
class DomainEvent:
    """
    Evento de dominio: algo significativo que ocurrió.
    Son inmutables y se publican al broker (Kafka/RabbitMQ).
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_on: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    aggregate_id: str = ""
    event_type: str = ""
    payload: dict = field(default_factory=dict)


class BaseEntity:
    """Clase base para entidades de dominio con gestión de Domain Events."""

    def __init__(self, entity_id: str = None):
        self._id = entity_id or str(uuid.uuid4())
        self._created_at = datetime.now(timezone.utc)
        self._updated_at = datetime.now(timezone.utc)
        self._domain_events: List[DomainEvent] = []

    @property
    def id(self) -> str:
        return self._id

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def _record_event(self, event: DomainEvent) -> None:
        """Registra un evento pendiente de publicar."""
        self._domain_events.append(event)

    def pull_domain_events(self) -> List[DomainEvent]:
        """Extrae y limpia los eventos. Llamar tras persistir."""
        events = self._domain_events.copy()
        self._domain_events.clear()
        return events

    def _touch(self):
        self._updated_at = datetime.now(timezone.utc)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self._id}>"
