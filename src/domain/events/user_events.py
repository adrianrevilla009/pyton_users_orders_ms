"""Eventos de dominio relacionados con usuarios."""
from dataclasses import dataclass
from src.domain.events.base import DomainEvent


@dataclass(frozen=True)
class UserCreatedEvent(DomainEvent):
    user_id: str = ''
    email: str = ''


@dataclass(frozen=True)
class UserActivatedEvent(DomainEvent):
    user_id: str = ''


@dataclass(frozen=True)
class UserSuspendedEvent(DomainEvent):
    user_id: str = ''
    reason: str = ''
