"""Eventos de dominio relacionados con pedidos."""
from dataclasses import dataclass
from src.domain.events.base import DomainEvent


@dataclass(frozen=True)
class OrderCreatedEvent(DomainEvent):
    order_id: str = ''
    buyer_id: str = ''
    total_amount: str = ''
    currency: str = ''


@dataclass(frozen=True)
class OrderPaidEvent(DomainEvent):
    order_id: str = ''
    payment_id: str = ''


@dataclass(frozen=True)
class OrderCancelledEvent(DomainEvent):
    order_id: str = ''
    reason: str = ''
