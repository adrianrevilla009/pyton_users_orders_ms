"""
============================================================
ORDER ENTITY - Aggregate Root del contexto de órdenes
============================================================
Demuestra un aggregate más complejo con:
- Entidades hijas (OrderItem)
- Invariantes complejas
- Máquina de estados
- Múltiples domain events
============================================================
"""

from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Optional
from enum import Enum
from dataclasses import dataclass
import uuid

from shared.domain.base_entity import BaseEntity, DomainEvent


class OrderStatus(Enum):
    """Máquina de estados del pedido."""
    DRAFT = "draft"               # Borrador, aún editando
    PENDING = "pending"           # Confirmado, pendiente de pago
    PAID = "paid"                 # Pagado, pendiente de envío
    PROCESSING = "processing"     # En preparación
    SHIPPED = "shipped"           # Enviado
    DELIVERED = "delivered"       # Entregado
    CANCELLED = "cancelled"       # Cancelado
    REFUNDED = "refunded"         # Reembolsado


# Transiciones válidas (State Machine)
VALID_TRANSITIONS = {
    OrderStatus.DRAFT: [OrderStatus.PENDING, OrderStatus.CANCELLED],
    OrderStatus.PENDING: [OrderStatus.PAID, OrderStatus.CANCELLED],
    OrderStatus.PAID: [OrderStatus.PROCESSING, OrderStatus.REFUNDED],
    OrderStatus.PROCESSING: [OrderStatus.SHIPPED, OrderStatus.CANCELLED],
    OrderStatus.SHIPPED: [OrderStatus.DELIVERED],
    OrderStatus.DELIVERED: [OrderStatus.REFUNDED],
    OrderStatus.CANCELLED: [],
    OrderStatus.REFUNDED: [],
}


@dataclass
class OrderItem:
    """
    Value Object que representa una línea del pedido.
    Es un VO porque su identidad viene del pedido que lo contiene.
    """
    product_id: str
    product_name: str
    unit_price: Decimal
    quantity: int
    item_id: str = ""

    def __post_init__(self):
        if not self.item_id:
            self.item_id = str(uuid.uuid4())
        if self.quantity <= 0:
            raise ValueError("La cantidad debe ser mayor que 0")
        if self.unit_price <= 0:
            raise ValueError("El precio unitario debe ser mayor que 0")

    @property
    def total_price(self) -> Decimal:
        return self.unit_price * self.quantity


# --- Domain Events ---

class OrderCreatedEvent(DomainEvent):
    def __init__(self, order_id: str, user_id: str, total: str):
        super().__init__(
            aggregate_id=order_id,
            event_type="order.created",
            payload={"user_id": user_id, "total": total}
        )

class OrderConfirmedEvent(DomainEvent):
    def __init__(self, order_id: str, total: str):
        super().__init__(
            aggregate_id=order_id,
            event_type="order.confirmed",
            payload={"total": total}
        )

class OrderCancelledEvent(DomainEvent):
    def __init__(self, order_id: str, reason: str):
        super().__init__(
            aggregate_id=order_id,
            event_type="order.cancelled",
            payload={"reason": reason}
        )

class OrderShippedEvent(DomainEvent):
    def __init__(self, order_id: str, tracking_code: str):
        super().__init__(
            aggregate_id=order_id,
            event_type="order.shipped",
            payload={"tracking_code": tracking_code}
        )


class Order(BaseEntity):
    """
    Aggregate Root del contexto de órdenes.
    
    Garantiza:
    - Solo se pueden añadir items en estado DRAFT
    - Las transiciones de estado son válidas (state machine)
    - El total se calcula siempre desde los items (nunca se guarda hardcoded)
    - Cada transición importante genera un Domain Event
    """

    # Mínimo de importe para crear un pedido (regla de negocio)
    MIN_ORDER_AMOUNT = Decimal("0.01")
    # Máximo de items por pedido
    MAX_ITEMS = 50

    def __init__(
        self,
        user_id: str,
        entity_id: str = None,
        notes: str = "",
    ):
        super().__init__(entity_id)
        self._user_id = user_id
        self._status = OrderStatus.DRAFT
        self._items: List[OrderItem] = []
        self._notes = notes
        self._shipping_address: Optional[str] = None
        self._tracking_code: Optional[str] = None
        self._cancelled_reason: Optional[str] = None

    @classmethod
    def create(cls, user_id: str, notes: str = "") -> 'Order':
        """Factory method para crear un nuevo pedido."""
        order = cls(user_id=user_id, notes=notes)
        order._record_event(OrderCreatedEvent(
            order_id=order.id,
            user_id=user_id,
            total="0.00"
        ))
        return order

    # --- Propiedades ---

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def items(self) -> List[OrderItem]:
        return list(self._items)  # Retorna copia para proteger la lista interna

    @property
    def total(self) -> Decimal:
        """El total SIEMPRE se calcula desde los items. Nunca se almacena."""
        return sum(item.total_price for item in self._items)

    @property
    def item_count(self) -> int:
        return len(self._items)

    @property
    def tracking_code(self) -> Optional[str]:
        return self._tracking_code

    @property
    def shipping_address(self) -> Optional[str]:
        return self._shipping_address

    # --- Comportamientos ---

    def add_item(self, product_id: str, product_name: str, unit_price: Decimal, quantity: int) -> None:
        """Añade un item al pedido. Solo en estado DRAFT."""
        self._assert_status(OrderStatus.DRAFT, "añadir items")

        if len(self._items) >= self.MAX_ITEMS:
            raise ValueError(f"No se pueden añadir más de {self.MAX_ITEMS} items")

        # Si el producto ya existe, actualizar cantidad
        for item in self._items:
            if item.product_id == product_id:
                new_quantity = item.quantity + quantity
                self._items.remove(item)
                self._items.append(OrderItem(
                    product_id=product_id,
                    product_name=product_name,
                    unit_price=unit_price,
                    quantity=new_quantity,
                    item_id=item.item_id,
                ))
                self._touch()
                return

        self._items.append(OrderItem(
            product_id=product_id,
            product_name=product_name,
            unit_price=unit_price,
            quantity=quantity,
        ))
        self._touch()

    def remove_item(self, item_id: str) -> None:
        """Elimina un item del pedido."""
        self._assert_status(OrderStatus.DRAFT, "eliminar items")
        self._items = [i for i in self._items if i.item_id != item_id]
        self._touch()

    def confirm(self, shipping_address: str) -> None:
        """
        Confirma el pedido (DRAFT -> PENDING).
        Valida que tenga items y dirección de envío.
        """
        self._assert_transition(OrderStatus.PENDING)

        if not self._items:
            raise ValueError("No se puede confirmar un pedido vacío")
        if self.total < self.MIN_ORDER_AMOUNT:
            raise ValueError(f"El pedido debe superar {self.MIN_ORDER_AMOUNT}")
        if not shipping_address:
            raise ValueError("La dirección de envío es obligatoria")

        self._status = OrderStatus.PENDING
        self._shipping_address = shipping_address
        self._touch()
        self._record_event(OrderConfirmedEvent(self.id, str(self.total)))

    def mark_as_paid(self) -> None:
        """Marca el pedido como pagado (PENDING -> PAID)."""
        self._assert_transition(OrderStatus.PAID)
        self._status = OrderStatus.PAID
        self._touch()

    def start_processing(self) -> None:
        """Inicia la preparación del pedido (PAID -> PROCESSING)."""
        self._assert_transition(OrderStatus.PROCESSING)
        self._status = OrderStatus.PROCESSING
        self._touch()

    def ship(self, tracking_code: str) -> None:
        """Marca el pedido como enviado con código de seguimiento."""
        self._assert_transition(OrderStatus.SHIPPED)
        if not tracking_code:
            raise ValueError("El código de seguimiento es obligatorio")
        self._status = OrderStatus.SHIPPED
        self._tracking_code = tracking_code
        self._touch()
        self._record_event(OrderShippedEvent(self.id, tracking_code))

    def deliver(self) -> None:
        """Marca el pedido como entregado."""
        self._assert_transition(OrderStatus.DELIVERED)
        self._status = OrderStatus.DELIVERED
        self._touch()

    def cancel(self, reason: str) -> None:
        """Cancela el pedido."""
        self._assert_transition(OrderStatus.CANCELLED)
        if not reason:
            raise ValueError("Debes indicar una razón para la cancelación")
        self._status = OrderStatus.CANCELLED
        self._cancelled_reason = reason
        self._touch()
        self._record_event(OrderCancelledEvent(self.id, reason))

    # --- Helpers privados ---

    def _assert_status(self, required: OrderStatus, action: str) -> None:
        """Verifica que el pedido está en el estado requerido."""
        if self._status != required:
            raise ValueError(
                f"No se puede {action} en estado '{self._status.value}'. "
                f"Requerido: '{required.value}'"
            )

    def _assert_transition(self, target: OrderStatus) -> None:
        """Verifica que la transición de estado es válida."""
        valid = VALID_TRANSITIONS.get(self._status, [])
        if target not in valid:
            raise ValueError(
                f"Transición inválida: {self._status.value} -> {target.value}. "
                f"Transiciones válidas: {[s.value for s in valid]}"
            )
