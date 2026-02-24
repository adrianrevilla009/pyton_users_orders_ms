"""
=============================================================================
ENTIDAD DE DOMINIO: Order (Aggregate Root)
=============================================================================

Order es un AGGREGATE ROOT — la entrada a un aggregate que incluye
Order + OrderItems. Las OrderItems no tienen vida fuera de un Order.

El Aggregate garantiza la consistencia transaccional de todo el grupo.
Ningún código externo puede modificar OrderItems directamente;
todo debe pasar por Order.

Máquina de estados del pedido:
  PENDING → CONFIRMED → PAID → SHIPPED → DELIVERED
                ↓
            CANCELLED
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from src.domain.value_objects.money import Money
from src.domain.value_objects.address import Address
from src.domain.events.base import DomainEvent


class OrderStatus(Enum):
    PENDING = 'pending'         # Creado, pendiente de confirmación
    CONFIRMED = 'confirmed'     # Confirmado, esperando pago
    PAID = 'paid'               # Pagado
    SHIPPED = 'shipped'         # Enviado
    DELIVERED = 'delivered'     # Entregado — estado final exitoso
    CANCELLED = 'cancelled'     # Cancelado — estado final


# Transiciones válidas — la máquina de estados
VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),   # Estado final
    OrderStatus.CANCELLED: set(),   # Estado final
}


@dataclass
class OrderItem:
    """
    Entidad dentro del aggregate Order.
    Solo vive dentro de un Order — no tiene repositorio propio.
    """
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str       # Desnormalizado para historial (el nombre puede cambiar)
    unit_price: Money
    quantity: int

    @property
    def subtotal(self) -> Money:
        return self.unit_price.multiply(self.quantity)


@dataclass
class Order:
    """
    Aggregate Root del proceso de compra.
    Coordina la creación y gestión de un pedido completo.
    """
    id: uuid.UUID
    buyer_id: uuid.UUID
    items: list[OrderItem]
    shipping_address: Address
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    payment_id: Optional[str] = None  # ID de Stripe cuando se paga
    tracking_number: Optional[str] = None

    _domain_events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    @classmethod
    def create(
        cls,
        buyer_id: uuid.UUID,
        items_data: list[dict],  # [{'product_id', 'name', 'price', 'currency', 'quantity'}]
        shipping_address: Address,
    ) -> 'Order':
        """Factory method — crea un nuevo pedido con sus items."""
        from src.domain.events.order_events import OrderCreatedEvent

        if not items_data:
            raise ValueError("Un pedido debe tener al menos un item")

        now = datetime.utcnow()
        items = [
            OrderItem(
                id=uuid.uuid4(),
                product_id=uuid.UUID(item['product_id']),
                product_name=item['name'],
                unit_price=Money(amount=Decimal(str(item['price'])), currency=item['currency']),
                quantity=item['quantity'],
            )
            for item in items_data
        ]

        order = cls(
            id=uuid.uuid4(),
            buyer_id=buyer_id,
            items=items,
            shipping_address=shipping_address,
            status=OrderStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

        order._domain_events.append(OrderCreatedEvent(
            order_id=str(order.id),
            buyer_id=str(buyer_id),
            total_amount=str(order.total.amount),
            currency=order.total.currency,
            occurred_at=now,
        ))

        return order

    def _transition_to(self, new_status: OrderStatus) -> None:
        """Aplica una transición de estado validando que sea permitida."""
        if new_status not in VALID_TRANSITIONS[self.status]:
            raise ValueError(
                f"Transición inválida: {self.status.value} → {new_status.value}"
            )
        self.status = new_status
        self.updated_at = datetime.utcnow()

    def confirm(self) -> None:
        self._transition_to(OrderStatus.CONFIRMED)

    def mark_as_paid(self, payment_id: str) -> None:
        from src.domain.events.order_events import OrderPaidEvent
        self._transition_to(OrderStatus.PAID)
        self.payment_id = payment_id
        self._domain_events.append(OrderPaidEvent(
            order_id=str(self.id),
            payment_id=payment_id,
            occurred_at=self.updated_at,
        ))

    def ship(self, tracking_number: str) -> None:
        self._transition_to(OrderStatus.SHIPPED)
        self.tracking_number = tracking_number

    def deliver(self) -> None:
        self._transition_to(OrderStatus.DELIVERED)

    def cancel(self, reason: str = '') -> None:
        from src.domain.events.order_events import OrderCancelledEvent
        self._transition_to(OrderStatus.CANCELLED)
        self._domain_events.append(OrderCancelledEvent(
            order_id=str(self.id),
            reason=reason,
            occurred_at=self.updated_at,
        ))

    @property
    def total(self) -> Money:
        """Calcula el total sumando todos los items."""
        if not self.items:
            return Money.zero()
        result = self.items[0].subtotal
        for item in self.items[1:]:
            result = result.add(item.subtotal)
        return result

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items)

    def pull_domain_events(self) -> list[DomainEvent]:
        events = list(self._domain_events)
        self._domain_events.clear()
        return events
