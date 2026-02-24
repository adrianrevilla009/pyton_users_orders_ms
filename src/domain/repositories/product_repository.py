"""Puerto: ProductRepository"""
from abc import ABC, abstractmethod
from typing import Optional
import uuid

from src.domain.entities.product import Product, ProductStatus


class ProductRepository(ABC):

    @abstractmethod
    def save(self, product: Product) -> Product:
        ...

    @abstractmethod
    def find_by_id(self, product_id: uuid.UUID) -> Optional[Product]:
        ...

    @abstractmethod
    def find_by_seller(self, seller_id: uuid.UUID) -> list[Product]:
        ...

    @abstractmethod
    def find_active_by_category(self, category: str) -> list[Product]:
        ...

    @abstractmethod
    def search(self, query: str, category: Optional[str] = None) -> list[Product]:
        """Búsqueda de texto libre — puede delegar en Elasticsearch o MongoDB."""
        ...

    @abstractmethod
    def delete(self, product_id: uuid.UUID) -> None:
        ...
