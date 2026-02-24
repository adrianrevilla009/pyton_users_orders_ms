"""
=============================================================================
PUERTO (INTERFAZ): UserRepository
=============================================================================

En la Arquitectura Hexagonal, los repositorios son PUERTOS (interfaces).
El dominio define QUÉ operaciones necesita, sin saber CÓMO se implementan.

La implementación concreta (PostgreSQL, MongoDB, in-memory para tests)
vive en la capa de infraestructura y se inyecta en tiempo de ejecución.

Esto permite:
- Testear el dominio sin BD real (usar implementación in-memory)
- Cambiar de PostgreSQL a otro motor sin tocar el dominio
- Múltiples implementaciones (SQL para lecturas, NoSQL para búsquedas)
"""
from abc import ABC, abstractmethod
from typing import Optional
import uuid

from src.domain.entities.user import User
from src.domain.value_objects.email_address import EmailAddress


class UserRepository(ABC):
    """
    Interfaz abstracta para el repositorio de usuarios.
    El dominio habla con esta interfaz; la infraestructura la implementa.
    """

    @abstractmethod
    def save(self, user: User) -> User:
        """
        Persiste un usuario (crea o actualiza).
        También debe publicar los domain events pendientes.
        """
        ...

    @abstractmethod
    def find_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Busca usuario por ID. Retorna None si no existe."""
        ...

    @abstractmethod
    def find_by_email(self, email: EmailAddress) -> Optional[User]:
        """Busca usuario por email. Retorna None si no existe."""
        ...

    @abstractmethod
    def exists_by_email(self, email: EmailAddress) -> bool:
        """Verifica si existe un usuario con ese email."""
        ...

    @abstractmethod
    def delete(self, user_id: uuid.UUID) -> None:
        """Elimina un usuario (o lo marca como deleted — soft delete)."""
        ...
