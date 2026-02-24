"""
=============================================================================
ENTIDAD DE DOMINIO: User
=============================================================================

Las Entidades tienen IDENTIDAD propia (un ID único) y pueden cambiar
a lo largo del tiempo, a diferencia de los Value Objects.

IMPORTANTE: Esta entidad de dominio NO es el modelo Django ORM.
Es la representación pura del dominio, sin dependencias de infraestructura.

La entidad de dominio se traduce hacia/desde el modelo ORM en el repositorio.
Esto es el núcleo de la Arquitectura Hexagonal: el dominio no sabe nada
de Django, PostgreSQL, Redis o cualquier otro detalle de infraestructura.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from src.domain.value_objects.email_address import EmailAddress
from src.domain.events.base import DomainEvent


class UserRole(Enum):
    """Roles del sistema — RBAC (Role-Based Access Control)."""
    ADMIN = 'admin'        # Acceso total
    SELLER = 'seller'      # Puede crear y gestionar productos
    BUYER = 'buyer'        # Solo puede comprar
    SUPPORT = 'support'    # Acceso de lectura para soporte

    @property
    def permissions(self) -> set[str]:
        """
        Permisos asociados a cada rol.
        En un sistema complejo, esto vendría de BD.
        """
        role_permissions = {
            UserRole.ADMIN: {
                'user:read', 'user:write', 'user:delete',
                'product:read', 'product:write', 'product:delete',
                'order:read', 'order:write', 'order:delete',
                'payment:read', 'payment:refund',
                'admin:access',
            },
            UserRole.SELLER: {
                'product:read', 'product:write',
                'order:read',
                'payment:read',
            },
            UserRole.BUYER: {
                'product:read',
                'order:read', 'order:write',
                'payment:write',
            },
            UserRole.SUPPORT: {
                'user:read',
                'product:read',
                'order:read',
                'payment:read',
            },
        }
        return role_permissions.get(self, set())


class UserStatus(Enum):
    """Estado del ciclo de vida del usuario."""
    PENDING_VERIFICATION = 'pending_verification'  # Email no verificado
    ACTIVE = 'active'
    SUSPENDED = 'suspended'
    DELETED = 'deleted'


@dataclass
class User:
    """
    Entidad User del dominio.

    Contiene la lógica de negocio relacionada con usuarios.
    Los datos se validan en el constructor y en los métodos.

    Nótese que los eventos de dominio se acumulan en _domain_events
    y se emiten cuando el repositorio persiste la entidad.
    Este patrón (Aggregate con eventos) es fundamental en CQRS/Event Sourcing.
    """
    id: uuid.UUID
    email: EmailAddress
    first_name: str
    last_name: str
    role: UserRole
    status: UserStatus
    created_at: datetime
    updated_at: datetime
    password_hash: str = ''
    phone: Optional[str] = None

    # Eventos de dominio acumulados — se emiten al persistir
    # No se serializan ni persisten directamente
    _domain_events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    @classmethod
    def create(
        cls,
        email: str,
        first_name: str,
        last_name: str,
        role: UserRole = UserRole.BUYER,
        phone: Optional[str] = None,
    ) -> 'User':
        """
        Factory method — la forma recomendada de crear nuevas entidades.
        Centraliza la lógica de creación y garantiza invariantes.
        """
        from src.domain.events.user_events import UserCreatedEvent
        now = datetime.utcnow()

        user = cls(
            id=uuid.uuid4(),
            email=EmailAddress(email),
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            role=role,
            status=UserStatus.PENDING_VERIFICATION,
            created_at=now,
            updated_at=now,
            phone=phone,
        )

        # Registrar evento de dominio — otros partes del sistema pueden reaccionar
        user._domain_events.append(UserCreatedEvent(
            user_id=str(user.id),
            email=str(user.email),
            occurred_at=now,
        ))

        return user

    def activate(self) -> None:
        """Activa el usuario tras verificar el email."""
        from src.domain.events.user_events import UserActivatedEvent
        if self.status != UserStatus.PENDING_VERIFICATION:
            raise ValueError(f"No se puede activar un usuario en estado: {self.status.value}")
        self.status = UserStatus.ACTIVE
        self.updated_at = datetime.utcnow()
        self._domain_events.append(UserActivatedEvent(
            user_id=str(self.id),
            occurred_at=self.updated_at,
        ))

    def suspend(self, reason: str) -> None:
        """Suspende al usuario. Solo un admin puede hacer esto."""
        from src.domain.events.user_events import UserSuspendedEvent
        if self.status == UserStatus.DELETED:
            raise ValueError("No se puede suspender un usuario eliminado")
        self.status = UserStatus.SUSPENDED
        self.updated_at = datetime.utcnow()
        self._domain_events.append(UserSuspendedEvent(
            user_id=str(self.id),
            reason=reason,
            occurred_at=self.updated_at,
        ))

    def change_role(self, new_role: UserRole) -> None:
        """Cambia el rol del usuario."""
        old_role = self.role
        self.role = new_role
        self.updated_at = datetime.utcnow()

    def has_permission(self, permission: str) -> bool:
        """Verifica si el usuario tiene un permiso específico."""
        return permission in self.role.permissions

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    def pull_domain_events(self) -> list[DomainEvent]:
        """
        Extrae y limpia los eventos de dominio pendientes.
        Se llama desde el repositorio tras persistir.
        """
        events = list(self._domain_events)
        self._domain_events.clear()
        return events
