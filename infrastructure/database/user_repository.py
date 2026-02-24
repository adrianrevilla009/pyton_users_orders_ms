"""
============================================================
INFRAESTRUCTURA - REPOSITORIO DE USUARIOS (PostgreSQL)
============================================================

Esta es la implementación concreta del puerto UserRepository.
Usa Django ORM para interactuar con PostgreSQL.

El dominio NO conoce esta clase. Solo conoce la interfaz
UserRepository. Aquí traducimos entre:
  - Entidades del dominio (User) ↔ Modelos Django (UserModel)

Patrón: Repository Pattern + Data Mapper
============================================================
"""

import uuid
from typing import Optional, List

import structlog

from domain.users.user import (
    User, Email, Address, UserRole, UserStatus, UserRepository
)
from domain.base import DomainException

logger = structlog.get_logger(__name__)


class DjangoUserRepository(UserRepository):
    """
    Implementación del repositorio de usuarios usando Django ORM.
    
    RESPONSABILIDAD:
    - Traducir entre entidades de dominio y modelos Django
    - Manejar la persistencia en PostgreSQL
    - Ser la única clase que conoce el modelo Django de usuario
    
    Esta clase vive en la INFRAESTRUCTURA, no en el dominio.
    """

    def get_by_id(self, id: uuid.UUID) -> Optional[User]:
        """Obtiene un usuario por su UUID."""
        from apps.users.models import User as UserModel
        try:
            model = UserModel.objects.get(id=id)
            return self._to_domain(model)
        except UserModel.DoesNotExist:
            return None
        except Exception as e:
            logger.error("user_repository_get_by_id_error", error=str(e), user_id=str(id))
            raise

    def get_by_email(self, email: Email) -> Optional[User]:
        """Obtiene un usuario por su email."""
        from apps.users.models import User as UserModel
        try:
            model = UserModel.objects.get(email=str(email))
            return self._to_domain(model)
        except UserModel.DoesNotExist:
            return None

    def exists_by_email(self, email: Email) -> bool:
        """Comprueba si existe un usuario con ese email."""
        from apps.users.models import User as UserModel
        return UserModel.objects.filter(email=str(email)).exists()

    def save(self, user: User, hashed_password: Optional[str] = None) -> None:
        """
        Persiste o actualiza un usuario.
        
        Upsert: si existe, actualiza; si no, crea.
        Usamos update_or_create para operaciones atómicas.
        """
        from apps.users.models import User as UserModel

        defaults = {
            "email": str(user.email),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role.value,
            "status": user.status.value,
            "last_login": user.last_login,
        }

        # Dirección (campos desnormalizados en el modelo para simplicidad)
        if user.address:
            defaults.update({
                "address_street": user.address.street,
                "address_city": user.address.city,
                "address_postal_code": user.address.postal_code,
                "address_country": user.address.country,
                "address_province": user.address.province,
            })

        if hashed_password:
            defaults["password"] = hashed_password

        UserModel.objects.update_or_create(
            id=user.id,
            defaults=defaults,
        )
        logger.debug("user_saved", user_id=str(user.id))

    def delete(self, id: uuid.UUID) -> None:
        """Elimina un usuario."""
        from apps.users.models import User as UserModel
        count, _ = UserModel.objects.filter(id=id).delete()
        if count == 0:
            raise DomainException(f"Usuario {id} no encontrado para eliminar", code="USER_NOT_FOUND")

    def find_by_role(self, role: UserRole) -> List[User]:
        """Obtiene todos los usuarios con un rol específico."""
        from apps.users.models import User as UserModel
        models = UserModel.objects.filter(role=role.value)
        return [self._to_domain(m) for m in models]

    def _to_domain(self, model) -> User:
        """
        Mapper: convierte un modelo Django en una entidad de dominio.
        
        Esta es la traducción crítica. Asegúrate de que TODOS
        los atributos del dominio se mapeen correctamente.
        """
        # Reconstruimos el Value Object Email
        email = Email(model.email)

        # Reconstruimos el rol
        try:
            role = UserRole(model.role)
        except ValueError:
            role = UserRole.CUSTOMER

        # Reconstruimos el status
        try:
            status = UserStatus(model.status)
        except ValueError:
            status = UserStatus.INACTIVE

        # Creamos la entidad sin llamar a __init__ completo
        # para evitar lanzar el evento UserRegistered de nuevo
        user = User.__new__(User)
        user.id = model.id
        user.email = email
        user.role = role
        user.status = status
        user.first_name = model.first_name
        user.last_name = model.last_name
        user.last_login = model.last_login
        user._created_at = model.date_joined
        user._updated_at = model.date_joined
        user._domain_events = []
        user._permissions = set()

        # Reconstruir dirección si existe
        if model.address_street:
            try:
                user.address = Address(
                    street=model.address_street,
                    city=model.address_city,
                    postal_code=model.address_postal_code,
                    country=model.address_country,
                    province=model.address_province,
                )
            except Exception:
                user.address = None
        else:
            user.address = None

        return user
