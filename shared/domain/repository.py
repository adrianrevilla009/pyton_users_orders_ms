"""
============================================================
REPOSITORY INTERFACE - Puerto de salida (Hexagonal)
============================================================
En arquitectura hexagonal:
- El DOMINIO define las interfaces (puertos)
- La INFRAESTRUCTURA implementa las interfaces (adaptadores)

El dominio NUNCA importa de infraestructura.
La infraestructura SIEMPRE importa del dominio.

Esto permite:
- Cambiar PostgreSQL por MySQL sin tocar el dominio
- Tests con repositorios en memoria
============================================================
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List

T = TypeVar('T')  # Tipo de la entidad


class BaseRepository(ABC, Generic[T]):
    """
    Interfaz base para todos los repositorios.
    Define el contrato que deben cumplir las implementaciones.
    """

    @abstractmethod
    def save(self, entity: T) -> T:
        """Persiste una entidad (crea o actualiza)."""
        raise NotImplementedError

    @abstractmethod
    def find_by_id(self, entity_id: str) -> Optional[T]:
        """Busca una entidad por ID. Retorna None si no existe."""
        raise NotImplementedError

    @abstractmethod
    def find_all(self) -> List[T]:
        """Retorna todas las entidades."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, entity_id: str) -> None:
        """Elimina una entidad por ID."""
        raise NotImplementedError

    def exists(self, entity_id: str) -> bool:
        """Comprueba si una entidad existe. Puede sobreescribirse para optimizar."""
        return self.find_by_id(entity_id) is not None
