"""
============================================================
DOMINIO DE PEDIDOS (Orders Bounded Context)
============================================================

El Agregado Order es el ejemplo más rico del proyecto.
Muestra cómo modelar lógica de negocio compleja con DDD.

Invariantes del agregado:
1. Un pedido vacío no puede confirmarse
2. No se pueden añadir productos a un pedido confirmado
3. Solo se puede cancelar un pedido que no ha sido enviado
4. El total del pedido siempre refleja la suma de sus líneas
============================================================
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from domain.base import AggregateRoot, Entity, ValueObject, DomainEvent, DomainException, Repository
from domain.users.user import Money, Address


# ─── Enumeraciones ────────────────────────────────────────────

class OrderStatus(str, Enum):
    DRAFT = "draft"               # En construcción, no confirmado
    PENDING_PAYMENT = "pending_payment"   # Esperando pago
    PAID = "paid"                 # Pagado, pendiente preparación
    PROCESSING = "processing"     # En preparación
    SHIPPED = "shipped"           # Enviado
    DELIVERED = "delivered"       # Entregado
    CANCELLED = "cancelled"       # Cancelado
    REFUNDED = "refunded"         # Reembolsado


class PaymentMethod(str, Enum):
    CREDIT_CARD = "credit_card"
    STRIPE = "stripe"
    BANK_TRANSFER = "bank_transfer"
    PAYPAL = "paypal"


# ─── Value Objects específicos de Orders ─────────────────────

@dataclass(frozen=True)
class OrderNumber(ValueObject):
    """
    Número de pedido legible por humanos.
    
    Usamos un código más legible que el UUID para mostrar al cliente.
    Ejemplo: ORD-2024-001234
    """
    value: str

    @classmethod
    def generate(cls, sequence: int) -> "OrderNumber":
        """Genera un número de pedido secuencial."""
        year = datetime.utcnow().year
        return cls(value=f"ORD-{year}-{sequence:06d}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ProductId(ValueObject):
    """ID de producto (referencia al bounded context de Catálogo)."""
    value: uuid.UUID

    def __str__(self) -> str:
        return str(self.value)


# ─── Entidad: OrderLine ───────────────────────────────────────

class OrderLine(Entity):
    """
    Línea de pedido (entidad interna del agregado Order).
    
    IMPORTANTE: OrderLine NO tiene repositorio propio.
    Solo se accede y modifica a través de Order.
    
    Almacena una "snapshot" del precio: si el precio del producto
    cambia después, el pedido mantiene el precio original.
    """

    def __init__(
        self,
        product_id: ProductId,
        product_name: str,
        unit_price: Money,
        quantity: int,
    ):
        super().__init__()
        if quantity <= 0:
            raise DomainException("La cantidad debe ser mayor que 0", code="INVALID_QUANTITY")
        if quantity > 1000:
            raise DomainException("La cantidad máxima por línea es 1000", code="QUANTITY_EXCEEDED")

        self.product_id = product_id
        self.product_name = product_name
        self.unit_price = unit_price
        self.quantity = quantity

    @property
    def subtotal(self) -> Money:
        """Calcula el subtotal de esta línea."""
        return self.unit_price * self.quantity

    def update_quantity(self, new_quantity: int) -> None:
        if new_quantity <= 0:
            raise DomainException("La cantidad debe ser mayor que 0", code="INVALID_QUANTITY")
        self.quantity = new_quantity
        self._touch()


# ─── Domain Events de Orders ──────────────────────────────────

@dataclass
class OrderPlaced(DomainEvent):
    """Se emite cuando se confirma un pedido."""
    order_id: uuid.UUID = None
    user_id: uuid.UUID = None
    order_number: str = ""
    total_cents: int = 0
    currency: str = "EUR"


@dataclass
class OrderCancelled(DomainEvent):
    """Se emite cuando se cancela un pedido."""
    order_id: uuid.UUID = None
    user_id: uuid.UUID = None
    order_number: str = ""
    reason: str = ""


@dataclass
class OrderShipped(DomainEvent):
    """Se emite cuando se envía un pedido."""
    order_id: uuid.UUID = None
    user_id: uuid.UUID = None
    order_number: str = ""
    tracking_number: str = ""


@dataclass
class PaymentProcessed(DomainEvent):
    """Se emite cuando se procesa el pago."""
    order_id: uuid.UUID = None
    amount_cents: int = 0
    currency: str = "EUR"
    payment_method: str = ""
    transaction_id: str = ""


# ─── Aggregate Root: Order ────────────────────────────────────

class Order(AggregateRoot):
    """
    Agregado de Pedido.
    
    Raíz del agregado que incluye las OrderLines.
    Toda modificación del pedido pasa por esta clase.
    
    INVARIANTES (reglas que siempre deben cumplirse):
    1. Un pedido debe tener al menos una línea para confirmarse
    2. Las líneas solo se pueden modificar en estado DRAFT
    3. El total siempre es la suma de todos los subtotales
    4. Solo se puede cancelar un pedido no enviado/entregado
    """

    def __init__(
        self,
        user_id: uuid.UUID,
        shipping_address: Address,
        payment_method: PaymentMethod = PaymentMethod.STRIPE,
        order_number: Optional[OrderNumber] = None,
        id: Optional[uuid.UUID] = None,
    ):
        super().__init__(id)
        self.user_id = user_id
        self.order_number = order_number
        self.shipping_address = shipping_address
        self.payment_method = payment_method
        self.status = OrderStatus.DRAFT
        self._lines: List[OrderLine] = []
        self.notes: Optional[str] = None
        self.confirmed_at: Optional[datetime] = None
        self.shipped_at: Optional[datetime] = None
        self.delivered_at: Optional[datetime] = None
        self.cancelled_at: Optional[datetime] = None
        self.tracking_number: Optional[str] = None

    # ─── Propiedades calculadas ───────────────────────────────

    @property
    def lines(self) -> List[OrderLine]:
        """Devuelve una copia inmutable de las líneas."""
        return list(self._lines)

    @property
    def total(self) -> Money:
        """
        Total calculado siempre desde las líneas (source of truth).
        Nunca almacenamos el total como campo separado que pueda desincronizarse.
        """
        if not self._lines:
            return Money(0, "EUR")
        total = self._lines[0].subtotal
        for line in self._lines[1:]:
            total = total + line.subtotal
        return total

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self._lines)

    @property
    def can_be_cancelled(self) -> bool:
        """Un pedido puede cancelarse si no ha sido enviado ni entregado."""
        return self.status not in (
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
            OrderStatus.REFUNDED,
        )

    @property
    def is_editable(self) -> bool:
        """Las líneas solo se pueden editar en estado DRAFT."""
        return self.status == OrderStatus.DRAFT

    # ─── Comandos (operaciones que modifican el estado) ──────

    def add_line(
        self,
        product_id: ProductId,
        product_name: str,
        unit_price: Money,
        quantity: int,
    ) -> OrderLine:
        """
        Añade una línea al pedido.
        
        REGLA: Solo se puede modificar un pedido en estado DRAFT.
        Si el producto ya existe en una línea, incrementa la cantidad.
        """
        self._assert_is_editable()

        # Si el producto ya está en el pedido, incrementamos cantidad
        existing_line = self._find_line_by_product(product_id)
        if existing_line:
            existing_line.update_quantity(existing_line.quantity + quantity)
            return existing_line

        line = OrderLine(
            product_id=product_id,
            product_name=product_name,
            unit_price=unit_price,
            quantity=quantity,
        )
        self._lines.append(line)
        self._touch()
        return line

    def remove_line(self, product_id: ProductId) -> None:
        """Elimina una línea del pedido."""
        self._assert_is_editable()

        line = self._find_line_by_product(product_id)
        if not line:
            raise DomainException(
                f"Producto {product_id} no encontrado en el pedido",
                code="PRODUCT_NOT_IN_ORDER"
            )
        self._lines.remove(line)
        self._touch()

    def confirm(self) -> None:
        """
        Confirma el pedido y lo pone en espera de pago.
        
        INVARIANTE: El pedido debe tener al menos una línea.
        """
        if not self._lines:
            raise DomainException(
                "No se puede confirmar un pedido vacío",
                code="EMPTY_ORDER"
            )
        if self.status != OrderStatus.DRAFT:
            raise DomainException(
                f"Solo se puede confirmar un pedido en estado DRAFT. Estado actual: {self.status}",
                code="INVALID_ORDER_STATE"
            )

        self.status = OrderStatus.PENDING_PAYMENT
        self.confirmed_at = datetime.utcnow()
        self._touch()

        # Emitimos el evento de dominio para que otros bounded contexts
        # puedan reaccionar (notificaciones, inventario, analítica...)
        self.register_event(OrderPlaced(
            order_id=self.id,
            user_id=self.user_id,
            order_number=str(self.order_number),
            total_cents=self.total.amount_cents,
            currency=self.total.currency,
        ))

    def mark_as_paid(self, transaction_id: str) -> None:
        """Marca el pedido como pagado."""
        if self.status != OrderStatus.PENDING_PAYMENT:
            raise DomainException("El pedido no está pendiente de pago", code="INVALID_ORDER_STATE")

        self.status = OrderStatus.PAID
        self._touch()

        self.register_event(PaymentProcessed(
            order_id=self.id,
            amount_cents=self.total.amount_cents,
            currency=self.total.currency,
            payment_method=self.payment_method.value,
            transaction_id=transaction_id,
        ))

    def ship(self, tracking_number: str) -> None:
        """Marca el pedido como enviado."""
        if self.status not in (OrderStatus.PAID, OrderStatus.PROCESSING):
            raise DomainException("El pedido debe estar pagado para enviarse", code="INVALID_ORDER_STATE")

        self.status = OrderStatus.SHIPPED
        self.tracking_number = tracking_number
        self.shipped_at = datetime.utcnow()
        self._touch()

        self.register_event(OrderShipped(
            order_id=self.id,
            user_id=self.user_id,
            order_number=str(self.order_number),
            tracking_number=tracking_number,
        ))

    def deliver(self) -> None:
        """Marca el pedido como entregado."""
        if self.status != OrderStatus.SHIPPED:
            raise DomainException("El pedido debe estar enviado para marcarse como entregado", code="INVALID_ORDER_STATE")

        self.status = OrderStatus.DELIVERED
        self.delivered_at = datetime.utcnow()
        self._touch()

    def cancel(self, reason: str) -> None:
        """Cancela el pedido."""
        if not self.can_be_cancelled:
            raise DomainException(
                f"El pedido no puede cancelarse en estado {self.status}",
                code="ORDER_CANNOT_BE_CANCELLED"
            )

        self.status = OrderStatus.CANCELLED
        self.cancelled_at = datetime.utcnow()
        self._touch()

        self.register_event(OrderCancelled(
            order_id=self.id,
            user_id=self.user_id,
            order_number=str(self.order_number),
            reason=reason,
        ))

    # ─── Métodos privados ─────────────────────────────────────

    def _assert_is_editable(self) -> None:
        if not self.is_editable:
            raise DomainException(
                f"El pedido no puede modificarse en estado {self.status}",
                code="ORDER_NOT_EDITABLE"
            )

    def _find_line_by_product(self, product_id: ProductId) -> Optional[OrderLine]:
        for line in self._lines:
            if line.product_id == product_id:
                return line
        return None


# ─── Repository Interface de Order ───────────────────────────

class OrderRepository(Repository):
    """Puerto del repositorio de pedidos."""

    def get_by_id(self, id: uuid.UUID) -> Optional[Order]:
        ...

    def get_by_order_number(self, order_number: OrderNumber) -> Optional[Order]:
        ...

    def save(self, order: Order) -> None:
        ...

    def delete(self, id: uuid.UUID) -> None:
        ...

    def find_by_user_id(self, user_id: uuid.UUID, status: Optional[OrderStatus] = None) -> List[Order]:
        ...

    def get_next_sequence(self) -> int:
        """Obtiene el siguiente número de secuencia para OrderNumber."""
        ...


# ─── Domain Exceptions ───────────────────────────────────────

class OrderNotFoundError(DomainException):
    def __init__(self, identifier: str):
        super().__init__(f"Pedido no encontrado: {identifier}", code="ORDER_NOT_FOUND")


class InsufficientStockError(DomainException):
    def __init__(self, product_name: str, available: int, requested: int):
        super().__init__(
            f"Stock insuficiente para '{product_name}': disponible {available}, solicitado {requested}",
            code="INSUFFICIENT_STOCK"
        )
