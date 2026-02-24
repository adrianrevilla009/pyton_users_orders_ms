"""Eventos de dominio relacionados con productos."""
from dataclasses import dataclass
from src.domain.events.base import DomainEvent


@dataclass(frozen=True)
class ProductCreatedEvent(DomainEvent):
    product_id: str = ''
    seller_id: str = ''
    name: str = ''
