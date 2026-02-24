"""
============================================================
USER REPOSITORY INTERFACE - Puerto de salida
============================================================
Define el CONTRATO que debe cumplir cualquier implementación
de persistencia de usuarios.

Al estar en la capa de DOMINIO, no importa nada de
infraestructura. Solo trabaja con entidades de dominio.

Ventajas:
- Tests con implementación en memoria (sin BD)
- Cambiar PostgreSQL por otro motor sin tocar el dominio
- Múltiples implementaciones (SQL + caché)
============================================================
"""

from abc import ABC, abstractmethod
from typing import Optional, List

from apps.users.domain.entities.user import User
from apps.users.domain.value_objects.email import UserEmail


class UserRepository(ABC):
    """Interfaz del repositorio de usuarios."""

    @abstractmethod
    def save(self, user: User) -> User:
        """
        Persiste un usuario. Crea si no existe, actualiza si existe.
        Retorna el usuario con cualquier dato generado por la BD.
        """
        raise NotImplementedError

    @abstractmethod
    def find_by_id(self, user_id: str) -> Optional[User]:
        """Busca usuario por ID. Retorna None si no existe."""
        raise NotImplementedError

    @abstractmethod
    def find_by_email(self, email: UserEmail) -> Optional[User]:
        """Busca usuario por email. Retorna None si no existe."""
        raise NotImplementedError

    @abstractmethod
    def find_all(self, offset: int = 0, limit: int = 20) -> List[User]:
        """Lista usuarios con paginación."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, user_id: str) -> None:
        """Elimina un usuario por ID."""
        raise NotImplementedError

    @abstractmethod
    def exists_by_email(self, email: UserEmail) -> bool:
        """Comprueba si existe un usuario con ese email."""
        raise NotImplementedError

    @abstractmethod
    def count(self) -> int:
        """Cuenta el total de usuarios."""
        raise NotImplementedError
