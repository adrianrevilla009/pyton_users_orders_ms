"""DTOs para pedidos."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
import uuid

from pydantic import BaseModel, field_validator


class OrderItemCommand(BaseModel):
    product_id: uuid.UUID
    quantity: int

    @field_validator('quantity')
    @classmethod
    def quantity_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("La cantidad debe ser mayor que 0")
        return v


class CreateOrderCommand(BaseModel):
    items: list[OrderItemCommand]
    shipping_street: str
    shipping_city: str
    shipping_postal_code: str
    shipping_country: str
    shipping_state: str = ''

    @field_validator('items')
    @classmethod
    def items_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("El pedido debe tener al menos un item")
        return v


class OrderItemResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    unit_price: Decimal
    currency: str
    quantity: int
    subtotal: Decimal


class OrderResponse(BaseModel):
    id: uuid.UUID
    buyer_id: uuid.UUID
    items: list[OrderItemResponse]
    total_amount: Decimal
    currency: str
    status: str
    shipping_address: str
    created_at: datetime
    payment_id: Optional[str] = None
    tracking_number: Optional[str] = None
