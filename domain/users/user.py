"""
============================================================
DOMINIO DE USUARIOS
============================================================

Aquí vive la lógica de negocio relacionada con usuarios.
Sin Django, sin ORM, sin HTTP. Solo reglas de negocio.

Bounded Context: Identity & Access Management (IAM)
============================================================
"""

from __future__ import annotations
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Set

from domain.base import (
    AggregateRoot, ValueObject, DomainEvent, DomainException, Repository
)


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MANAGER = "manager"
    EMPLOYEE = "employee"
    CUSTOMER = "customer"
    READONLY = "readonly"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


@dataclass(frozen=True)
class Email(ValueObject):
    """
    Value Object para email.
    
    Si tienes un Email, SABES que es válido.
    Esto elimina validaciones dispersas por todo el código.
    """
    value: str

    def __post_init__(self):
        if not self._is_valid(self.value):
            raise DomainException(
                f"'{self.value}' no es un email válido",
                code="INVALID_EMAIL"
            )
        object.__setattr__(self, "value", self.value.lower().strip())

    @staticmethod
    def _is_valid(email: str) -> bool:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def __str__(self) -> str:
        return self.value

    @property
    def domain(self) -> str:
        return self.value.split("@")[1]


@dataclass(frozen=True)
class Money(ValueObject):
    """
    Value Object para dinero.
    
    NUNCA uses float para dinero. Almacenamos en céntimos (int)
    para evitar errores de coma flotante.
    """
    amount_cents: int
    currency: str = "EUR"

    def __post_init__(self):
        if self.amount_cents < 0:
            raise DomainException("El dinero no puede ser negativo", code="INVALID_MONEY")
        if len(self.currency) != 3:
            raise DomainException("Código ISO 4217 requerido (3 letras)", code="INVALID_CURRENCY")
        object.__setattr__(self, "currency", self.currency.upper())

    def __add__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount_cents + other.amount_cents, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount_cents - other.amount_cents, self.currency)

    def __mul__(self, factor: int) -> "Money":
        return Money(self.amount_cents * factor, self.currency)

    def _assert_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise DomainException(
                f"Monedas distintas: {self.currency} vs {other.currency}",
                code="CURRENCY_MISMATCH"
            )

    @property
    def amount(self) -> float:
        return self.amount_cents / 100

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"


@dataclass(frozen=True)
class Address(ValueObject):
    """Value Object para dirección postal."""
    street: str
    city: str
    postal_code: str
    country: str
    province: Optional[str] = None

    def __post_init__(self):
        if not self.street or not self.city or not self.postal_code:
            raise DomainException("Dirección incompleta", code="INVALID_ADDRESS")
        object.__setattr__(self, "country", self.country.upper())

    @property
    def full_address(self) -> str:
        parts = [self.street, self.city, self.postal_code]
        if self.province:
            parts.append(self.province)
        parts.append(self.country)
        return ", ".join(parts)


# ─── Domain Events ────────────────────────────────────────────

@dataclass
class UserRegistered(DomainEvent):
    user_id: uuid.UUID = None
    email: str = ""
    role: str = ""


@dataclass
class UserEmailVerified(DomainEvent):
    user_id: uuid.UUID = None


@dataclass
class UserRoleChanged(DomainEvent):
    user_id: uuid.UUID = None
    old_role: str = ""
    new_role: str = ""
    changed_by: uuid.UUID = None


@dataclass
class UserSuspended(DomainEvent):
    user_id: uuid.UUID = None
    reason: str = ""
    suspended_by: uuid.UUID = None


# ─── Aggregate Root: User ─────────────────────────────────────

class User(AggregateRoot):
    """
    Agregado de Usuario.
    
    REGLAS DE NEGOCIO:
    1. Solo SUPER_ADMIN puede asignar el rol SUPER_ADMIN
    2. Usuario suspendido no puede hacer login
    3. Email debe verificarse antes de hacer pedidos
    4. No puedes suspenderte a ti mismo
    """

    def __init__(
        self,
        email: Email,
        role: UserRole = UserRole.CUSTOMER,
        first_name: str = "",
        last_name: str = "",
        id: Optional[uuid.UUID] = None,
    ):
        super().__init__(id)
        self.email = email
        self.role = role
        self.first_name = first_name
        self.last_name = last_name
        self.status = UserStatus.PENDING_VERIFICATION
        self.address: Optional[Address] = None
        self.last_login: Optional[datetime] = None
        self._permissions: Set[str] = set()

        self.register_event(UserRegistered(
            user_id=self.id,
            email=str(email),
            role=role.value
        ))

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or str(self.email)

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    @property
    def is_admin(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    @property
    def can_create_orders(self) -> bool:
        return self.is_active

    def verify_email(self) -> None:
        if self.status != UserStatus.PENDING_VERIFICATION:
            raise DomainException("El email ya ha sido verificado", code="EMAIL_ALREADY_VERIFIED")
        self.status = UserStatus.ACTIVE
        self._touch()
        self.register_event(UserEmailVerified(user_id=self.id))

    def change_role(self, new_role: UserRole, changed_by: "User") -> None:
        if new_role == UserRole.SUPER_ADMIN and changed_by.role != UserRole.SUPER_ADMIN:
            raise DomainException(
                "Solo un super administrador puede asignar ese rol",
                code="INSUFFICIENT_PERMISSIONS"
            )
        old_role = self.role
        self.role = new_role
        self._touch()
        self.register_event(UserRoleChanged(
            user_id=self.id,
            old_role=old_role.value,
            new_role=new_role.value,
            changed_by=changed_by.id
        ))

    def suspend(self, reason: str, suspended_by: "User") -> None:
        if self.id == suspended_by.id:
            raise DomainException("No puedes suspenderte a ti mismo", code="SELF_SUSPENSION_NOT_ALLOWED")
        if self.role == UserRole.SUPER_ADMIN and suspended_by.role != UserRole.SUPER_ADMIN:
            raise DomainException("Permisos insuficientes", code="INSUFFICIENT_PERMISSIONS")
        if self.status == UserStatus.SUSPENDED:
            raise DomainException("El usuario ya está suspendido", code="ALREADY_SUSPENDED")
        self.status = UserStatus.SUSPENDED
        self._touch()
        self.register_event(UserSuspended(user_id=self.id, reason=reason, suspended_by=suspended_by.id))

    def update_address(self, address: Address) -> None:
        self.address = address
        self._touch()

    def record_login(self) -> None:
        if self.status == UserStatus.SUSPENDED:
            raise DomainException("Usuario suspendido. Contacta con el administrador.", code="USER_SUSPENDED")
        self.last_login = datetime.utcnow()
        self._touch()


class UserRepository(Repository):
    """Puerto del repositorio de usuarios."""
    def get_by_email(self, email: Email) -> Optional[User]: ...
    def get_by_id(self, id: uuid.UUID) -> Optional[User]: ...
    def save(self, user: User) -> None: ...
    def delete(self, id: uuid.UUID) -> None: ...
    def exists_by_email(self, email: Email) -> bool: ...
    def find_by_role(self, role: UserRole) -> list: ...


class UserNotFoundError(DomainException):
    def __init__(self, identifier: str):
        super().__init__(f"Usuario no encontrado: {identifier}", code="USER_NOT_FOUND")


class EmailAlreadyExistsError(DomainException):
    def __init__(self, email: str):
        super().__init__(f"El email '{email}' ya está registrado", code="EMAIL_ALREADY_EXISTS")
