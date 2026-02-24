"""Puerto: OrderRepository"""
from abc import ABC, abstractmethod
from typing import Optional
import uuid

from src.domain.entities.order import Order, OrderStatus


class OrderRepository(ABC):

    @abstractmethod
    def save(self, order: Order) -> Order:
        ...

    @abstractmethod
    def find_by_id(self, order_id: uuid.UUID) -> Optional[Order]:
        ...

    @abstractmethod
    def find_by_buyer(self, buyer_id: uuid.UUID) -> list[Order]:
        ...

    @abstractmethod
    def find_by_status(self, status: OrderStatus) -> list[Order]:
        ...
