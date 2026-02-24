"""
============================================================
DJANGO USER REPOSITORY - Adaptador de infraestructura
============================================================
Implementa el puerto UserRepository usando Django ORM.

Este es el ADAPTADOR en la arquitectura hexagonal.
Traduce entre:
- Entidades de dominio <-> Modelos ORM de Django

El MAPPER es crítico: separa limpiamente ambas representaciones.
Si mañana cambiamos de PostgreSQL a MySQL, solo cambia este archivo.
============================================================
"""

import structlog
from typing import Optional, List

from apps.users.domain.entities.user import User, UserRole, UserStatus
from apps.users.domain.repositories.user_repository import UserRepository
from apps.users.domain.value_objects.email import UserEmail
from apps.users.domain.value_objects.password import HashedPassword
from apps.users.infrastructure.models.user_model import UserModel

logger = structlog.get_logger(__name__)


class DjangoUserRepository(UserRepository):
    """
    Implementación PostgreSQL del repositorio de usuarios.
    Usa el ORM de Django internamente pero el dominio no lo sabe.
    """

    def save(self, user: User) -> User:
        """
        Convierte la entidad de dominio a modelo ORM y persiste.
        Patrón: upsert (update or create).
        """
        model_data = self._to_model_data(user)

        # update_or_create: crea si no existe, actualiza si existe
        model, created = UserModel.objects.update_or_create(
            id=user.id,
            defaults=model_data,
        )

        logger.debug(
            "Usuario persistido",
            user_id=str(model.id),
            created=created,
        )

        return self._to_domain(model)

    def find_by_id(self, user_id: str) -> Optional[User]:
        try:
            model = UserModel.objects.get(id=user_id)
            return self._to_domain(model)
        except UserModel.DoesNotExist:
            return None

    def find_by_email(self, email: UserEmail) -> Optional[User]:
        try:
            model = UserModel.objects.get(email=str(email))
            return self._to_domain(model)
        except UserModel.DoesNotExist:
            return None

    def find_all(self, offset: int = 0, limit: int = 20) -> List[User]:
        models = UserModel.objects.all()[offset:offset + limit]
        return [self._to_domain(m) for m in models]

    def delete(self, user_id: str) -> None:
        UserModel.objects.filter(id=user_id).delete()
        logger.info("Usuario eliminado", user_id=user_id)

    def exists_by_email(self, email: UserEmail) -> bool:
        return UserModel.objects.filter(email=str(email)).exists()

    def count(self) -> int:
        return UserModel.objects.count()

    # ---- MAPPER: Dominio <-> ORM ----

    def _to_model_data(self, user: User) -> dict:
        """
        Convierte entidad de dominio a diccionario para ORM.
        Esta es la traducción DOMINIO -> INFRAESTRUCTURA.
        """
        return {
            'name': user.name,
            'email': str(user.email),
            'password': str(user.hashed_password),  # Ya hasheada
            'role': user.role.value,
            'status': user.status.value,
            'login_count': user.login_count,
            'last_login_custom': user.last_login,
            'updated_at': user.updated_at,
        }

    def _to_domain(self, model: UserModel) -> User:
        """
        Convierte modelo ORM a entidad de dominio.
        Esta es la traducción INFRAESTRUCTURA -> DOMINIO.
        """
        user = User(
            name=model.name,
            email=UserEmail(model.email),
            hashed_password=HashedPassword(model.password),
            role=UserRole(model.role),
            entity_id=str(model.id),
        )
        # Restaurar estado interno (privado, usamos object.__setattr__)
        object.__setattr__(user, '_status', UserStatus(model.status))
        object.__setattr__(user, '_login_count', model.login_count)
        object.__setattr__(user, '_last_login', model.last_login_custom)
        object.__setattr__(user, '_created_at', model.created_at)
        object.__setattr__(user, '_updated_at', model.updated_at)

        return user
