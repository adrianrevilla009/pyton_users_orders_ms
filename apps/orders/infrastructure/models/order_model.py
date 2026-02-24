"""
============================================================
ORDER MODELS - ORM Django para el contexto de órdenes
============================================================
Dos modelos relacionados: Order y OrderItem.
Se usan índices específicos para queries de negocio frecuentes.
============================================================
"""

from django.db import models
from django.conf import settings
import uuid


class OrderModel(models.Model):
    """Modelo de BD para Order."""

    class StatusChoices(models.TextChoices):
        DRAFT = 'draft', 'Borrador'
        PENDING = 'pending', 'Pendiente'
        PAID = 'paid', 'Pagado'
        PROCESSING = 'processing', 'En proceso'
        SHIPPED = 'shipped', 'Enviado'
        DELIVERED = 'delivered', 'Entregado'
        CANCELLED = 'cancelled', 'Cancelado'
        REFUNDED = 'refunded', 'Reembolsado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # FK al usuario (no a la entidad de dominio, sino al modelo ORM)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,  # PROTECT: no borrar usuario si tiene pedidos
        related_name='orders',
        db_index=True,
    )
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.DRAFT, db_index=True)
    notes = models.TextField(blank=True, default='')
    shipping_address = models.TextField(blank=True, null=True)
    tracking_code = models.CharField(max_length=100, blank=True, null=True)
    cancelled_reason = models.TextField(blank=True, null=True)

    # Total desnormalizado para queries rápidas (aunque se calcula desde items)
    # Se recalcula en cada save del repositorio
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status'], name='idx_orders_user_status'),
            models.Index(fields=['status', 'created_at'], name='idx_orders_status_date'),
        ]

    def __str__(self):
        return f"Order {self.id} [{self.status}] - {self.total_amount}"


class OrderItemModel(models.Model):
    """Modelo de BD para OrderItem."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(OrderModel, on_delete=models.CASCADE, related_name='items')
    product_id = models.CharField(max_length=100, db_index=True)
    product_name = models.CharField(max_length=255)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    class Meta:
        db_table = 'order_items'

    @property
    def total_price(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"
