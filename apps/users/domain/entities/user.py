"""
============================================================
USER ENTITY - Entidad de dominio Usuario (Aggregate Root)
============================================================
En DDD, esta es la entidad central del bounded context "users".
Toda la lógica de negocio de usuario vive aquí.
NUNCA importa de Django, ORM, HTTP ni ninguna infraestructura.
============================================================
"""

from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from shared.domain.base_entity import BaseEntity, DomainEvent
from apps.users.domain.value_objects.email import UserEmail
from apps.users.domain.value_objects.password import HashedPassword


class UserRole(Enum):
    """
    Roles del sistema (RBAC - Role-Based Access Control).
    Jerarquía: ADMIN > MANAGER > CUSTOMER > READONLY
    """
    ADMIN = "admin"
    MANAGER = "manager"
    CUSTOMER = "customer"
    READONLY = "readonly"


class UserStatus(Enum):
    """Ciclo de vida del usuario."""
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


# --- Domain Events ---

class UserRegisteredEvent(DomainEvent):
    """Evento que se publica cuando un usuario se registra."""
    def __init__(self, user_id: str, email: str, name: str):
        super().__init__(
            aggregate_id=user_id,
            event_type="user.registered",
            payload={"email": email, "name": name}
        )

class UserSuspendedEvent(DomainEvent):
    def __init__(self, user_id: str, reason: str):
        super().__init__(
            aggregate_id=user_id,
            event_type="user.suspended",
            payload={"reason": reason}
        )

class UserEmailVerifiedEvent(DomainEvent):
    def __init__(self, user_id: str, email: str):
        super().__init__(
            aggregate_id=user_id,
            event_type="user.email_verified",
            payload={"email": email}
        )


class User(BaseEntity):
    """
    Aggregate Root del contexto de usuarios.
    
    REGLAS DE INVARIANTE (que el dominio garantiza):
    1. Un usuario no puede activarse sin verificar el email
    2. Solo usuarios activos pueden ser suspendidos
    3. El rol solo cambia en usuarios activos
    4. Cada acción relevante genera un Domain Event
    """

    def __init__(
        self,
        name: str,
        email: UserEmail,
        hashed_password: HashedPassword,
        role: UserRole = UserRole.CUSTOMER,
        entity_id: str = None,
    ):
        super().__init__(entity_id)
        self._name = name
        self._email = email
        self._hashed_password = hashed_password
        self._role = role
        self._status = UserStatus.PENDING_VERIFICATION
        self._login_count = 0
        self._last_login: Optional[datetime] = None

    @classmethod
    def create(cls, name: str, email: str, hashed_password: str) -> 'User':
        """
        Factory method - unica forma recomendada de crear usuarios nuevos.
        Garantiza que siempre se genera el evento de registro.
        """
        user = cls(
            name=name,
            email=UserEmail(email),
            hashed_password=HashedPassword(hashed_password),
        )
        user._record_event(UserRegisteredEvent(user.id, email, name))
        return user

    # --- Propiedades ---
    @property
    def name(self) -> str:
        return self._name

    @property
    def email(self) -> UserEmail:
        return self._email

    @property
    def hashed_password(self) -> HashedPassword:
        return self._hashed_password

    @property
    def role(self) -> UserRole:
        return self._role

    @property
    def status(self) -> UserStatus:
        return self._status

    @property
    def is_active(self) -> bool:
        return self._status == UserStatus.ACTIVE

    @property
    def login_count(self) -> int:
        return self._login_count

    @property
    def last_login(self) -> Optional[datetime]:
        return self._last_login

    # --- Comportamientos de dominio ---

    def verify_email(self) -> None:
        """Activa el usuario tras verificar el email."""
        if self._status != UserStatus.PENDING_VERIFICATION:
            raise ValueError(f"No se puede verificar desde estado: {self._status.value}")
        self._status = UserStatus.ACTIVE
        self._touch()
        self._record_event(UserEmailVerifiedEvent(self.id, str(self._email)))

    def suspend(self, reason: str) -> None:
        """
        Suspende el usuario. La autorización (quién puede suspender)
        se valida en el Use Case, no aquí. El dominio valida el ESTADO.
        """
        if self._status != UserStatus.ACTIVE:
            raise ValueError("Solo se pueden suspender usuarios activos")
        if not reason or len(reason) < 5:
            raise ValueError("Debes indicar una razón de al menos 5 caracteres")
        self._status = UserStatus.SUSPENDED
        self._touch()
        self._record_event(UserSuspendedEvent(self.id, reason))

    def reactivate(self) -> None:
        if self._status != UserStatus.SUSPENDED:
            raise ValueError("Solo se pueden reactivar usuarios suspendidos")
        self._status = UserStatus.ACTIVE
        self._touch()

    def change_role(self, new_role: UserRole) -> None:
        if not self.is_active:
            raise ValueError("No se puede cambiar el rol de un usuario inactivo")
        self._role = new_role
        self._touch()

    def update_name(self, new_name: str) -> None:
        if not new_name or len(new_name.strip()) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres")
        self._name = new_name.strip()
        self._touch()

    def record_login(self) -> None:
        """Llamado en cada login exitoso para auditoría."""
        self._login_count += 1
        self._last_login = datetime.now(timezone.utc)
        self._touch()

    def has_role(self, required_role: UserRole) -> bool:
        """Comprueba si el usuario tiene el rol requerido (con jerarquía)."""
        hierarchy = {
            UserRole.ADMIN: 4,
            UserRole.MANAGER: 3,
            UserRole.CUSTOMER: 2,
            UserRole.READONLY: 1,
        }
        return hierarchy.get(self._role, 0) >= hierarchy.get(required_role, 0)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self._email} role={self._role.value} status={self._status.value}>"
