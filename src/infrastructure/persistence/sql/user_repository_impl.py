"""
=============================================================================
ADAPTADOR: SQLUserRepository
=============================================================================

Implementación concreta del puerto UserRepository usando Django ORM + PostgreSQL.

Este es el "adaptador" en la Arquitectura Hexagonal.
Traduce entre:
- Entidad de dominio (User) ↔ Modelo ORM (sql_models.User)

El dominio nunca sabe que existe Django ORM.
"""
from typing import Optional
import uuid

import structlog

from src.domain.entities.user import User, UserRole, UserStatus
from src.domain.repositories.user_repository import UserRepository
from src.domain.value_objects.email_address import EmailAddress
from src.infrastructure.persistence.sql.models import User as UserORM

logger = structlog.get_logger(__name__)


class SQLUserRepository(UserRepository):
    """
    Repositorio de usuarios implementado con Django ORM (PostgreSQL).

    Responsabilidades:
    1. Traducir User (dominio) → UserORM (infraestructura)
    2. Traducir UserORM (infraestructura) → User (dominio)
    3. Gestionar la persistencia
    """

    def save(self, user: User) -> User:
        """Crea o actualiza un usuario en PostgreSQL."""
        log = logger.bind(user_id=str(user.id))

        # Traducción dominio → ORM
        orm_data = {
            'email': str(user.email),
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': user.role.value,
            'status': user.status.value,
            'phone': user.phone or '',
            'password': user.password_hash,  # Ya hasheado por el caso de uso
        }

        try:
            # update_or_create: crea si no existe, actualiza si existe
            # Búsqueda por PK (id), actualización con orm_data
            orm_user, created = UserORM.objects.update_or_create(
                id=user.id,
                defaults=orm_data,
            )
            action = 'created' if created else 'updated'
            log.info("user_persisted", action=action)

        except Exception as e:
            log.error("user_persistence_failed", error=str(e))
            raise

        # Traducción ORM → dominio
        return self._to_domain(orm_user)

    def find_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        try:
            orm_user = UserORM.objects.get(id=user_id)
            return self._to_domain(orm_user)
        except UserORM.DoesNotExist:
            return None

    def find_by_email(self, email: EmailAddress) -> Optional[User]:
        try:
            orm_user = UserORM.objects.get(email=str(email))
            return self._to_domain(orm_user)
        except UserORM.DoesNotExist:
            return None

    def exists_by_email(self, email: EmailAddress) -> bool:
        return UserORM.objects.filter(email=str(email)).exists()

    def delete(self, user_id: uuid.UUID) -> None:
        """Soft delete — marca como eliminado sin borrar el registro."""
        from django.utils import timezone
        UserORM.objects.filter(id=user_id).update(
            status='deleted',
            deleted_at=timezone.now(),
            is_active=False,
        )

    def _to_domain(self, orm_user: UserORM) -> User:
        """
        Traduce un modelo ORM a una entidad de dominio.
        Este es el mapper — el punto de traducción entre capas.
        """
        return User(
            id=orm_user.id,
            email=EmailAddress(orm_user.email),
            first_name=orm_user.first_name,
            last_name=orm_user.last_name,
            role=UserRole(orm_user.role),
            status=UserStatus(orm_user.status),
            created_at=orm_user.created_at,
            updated_at=orm_user.updated_at,
            password_hash=orm_user.password,
            phone=orm_user.phone or None,
        )
