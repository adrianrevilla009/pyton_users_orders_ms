"""
=============================================================================
EVENTOS DE DOMINIO — Base
=============================================================================

Los Domain Events representan algo que OCURRIÓ en el dominio.
Son inmutables y se nombran en pasado: UserCreated, OrderPaid, etc.

Flujo:
1. La entidad registra el evento en _domain_events
2. El repositorio persiste la entidad
3. El repositorio llama a pull_domain_events()
4. El Event Bus publica los eventos
5. Los handlers reaccionan (enviar email, actualizar cache, notificar a Kafka...)

Este patrón desacopla el dominio de sus efectos secundarios.
"""
from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass(frozen=True)
class DomainEvent:
    """
    Clase base para todos los eventos de dominio.
    Inmutable y con ID único para idempotencia.
    """
    occurred_at: datetime
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def event_type(self) -> str:
        """Nombre del evento — útil para el broker de mensajes."""
        return self.__class__.__name__
