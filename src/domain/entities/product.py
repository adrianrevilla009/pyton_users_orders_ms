"""
=============================================================================
ENTIDAD DE DOMINIO: Product
=============================================================================

El producto es el núcleo del catálogo. Contiene:
- Lógica de inventario (stock)
- Lógica de precios
- Estados del ciclo de vida
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from src.domain.value_objects.money import Money
from src.domain.events.base import DomainEvent


class ProductStatus(Enum):
    DRAFT = 'draft'           # Borrador — no visible
    ACTIVE = 'active'         # Publicado y disponible
    OUT_OF_STOCK = 'out_of_stock'
    DISCONTINUED = 'discontinued'


@dataclass
class Product:
    """
    Entidad Product — núcleo del catálogo.

    Invariantes de negocio que esta entidad garantiza:
    1. El precio nunca puede ser negativo
    2. El stock nunca puede ser menor que 0
    3. No se puede comprar un producto no activo
    4. No se puede reducir stock más allá del disponible
    """
    id: uuid.UUID
    seller_id: uuid.UUID        # Referencia por ID, no por objeto (Aggregate Root)
    name: str
    description: str
    price: Money
    stock: int
    category: str
    status: ProductStatus
    created_at: datetime
    updated_at: datetime
    sku: Optional[str] = None   # Stock Keeping Unit
    image_url: Optional[str] = None

    _domain_events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    @classmethod
    def create(
        cls,
        seller_id: uuid.UUID,
        name: str,
        description: str,
        price: Decimal,
        currency: str,
        stock: int,
        category: str,
        sku: Optional[str] = None,
    ) -> 'Product':
        """Factory method para crear un nuevo producto."""
        from src.domain.events.product_events import ProductCreatedEvent

        if stock < 0:
            raise ValueError("El stock inicial no puede ser negativo")
        if price < 0:
            raise ValueError("El precio no puede ser negativo")

        now = datetime.utcnow()
        product = cls(
            id=uuid.uuid4(),
            seller_id=seller_id,
            name=name.strip(),
            description=description,
            price=Money(amount=Decimal(str(price)), currency=currency),
            stock=stock,
            category=category,
            status=ProductStatus.DRAFT,
            created_at=now,
            updated_at=now,
            sku=sku,
        )

        product._domain_events.append(ProductCreatedEvent(
            product_id=str(product.id),
            seller_id=str(seller_id),
            name=name,
            occurred_at=now,
        ))

        return product

    def publish(self) -> None:
        """Publica el producto (pasa de DRAFT a ACTIVE)."""
        if self.status != ProductStatus.DRAFT:
            raise ValueError(f"Solo se pueden publicar borradores, estado actual: {self.status.value}")
        if self.stock == 0:
            self.status = ProductStatus.OUT_OF_STOCK
        else:
            self.status = ProductStatus.ACTIVE
        self.updated_at = datetime.utcnow()

    def reduce_stock(self, quantity: int) -> None:
        """
        Reduce el stock. Llamado cuando se crea un pedido.
        Garantiza la invariante: stock >= 0.
        """
        if quantity <= 0:
            raise ValueError("La cantidad debe ser positiva")
        if quantity > self.stock:
            raise ValueError(
                f"Stock insuficiente: disponible={self.stock}, solicitado={quantity}"
            )
        self.stock -= quantity
        if self.stock == 0:
            self.status = ProductStatus.OUT_OF_STOCK
        self.updated_at = datetime.utcnow()

    def restock(self, quantity: int) -> None:
        """Añade stock (recepción de mercancía)."""
        if quantity <= 0:
            raise ValueError("La cantidad debe ser positiva")
        self.stock += quantity
        if self.status == ProductStatus.OUT_OF_STOCK:
            self.status = ProductStatus.ACTIVE
        self.updated_at = datetime.utcnow()

    def apply_discount(self, percentage: Decimal) -> Money:
        """Calcula el precio con descuento (sin modificar la entidad)."""
        if not (0 <= percentage <= 100):
            raise ValueError("El porcentaje debe estar entre 0 y 100")
        discount_factor = 1 - (percentage / 100)
        return self.price.multiply(discount_factor)

    def is_available(self) -> bool:
        return self.status == ProductStatus.ACTIVE and self.stock > 0

    def pull_domain_events(self) -> list[DomainEvent]:
        events = list(self._domain_events)
        self._domain_events.clear()
        return events
