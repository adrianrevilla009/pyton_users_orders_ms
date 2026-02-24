"""
============================================================
CAPA DE APLICACIÓN - CASOS DE USO DE USUARIOS
============================================================

La capa de aplicación orquesta el dominio.
- Recibe comandos (DTOs) desde la capa de presentación (API)
- Usa repositorios para obtener/guardar entidades del dominio
- Publica domain events al message broker
- NO contiene lógica de negocio (eso es del dominio)
- NO sabe nada de HTTP, Django o la BD concreta

Patrón: Command/Query Segregation (CQRS simplificado)
- Commands: modifican estado (RegisterUser, ChangeRole...)
- Queries: leen datos (GetUser, ListUsers...)
============================================================
"""

from __future__ import annotations
import uuid
import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional, List

import structlog

from domain.users.user import (
    User, Email, Address, UserRole, UserStatus,
    UserRepository, UserNotFoundError, EmailAlreadyExistsError, Money
)
from domain.base import DomainException

logger = structlog.get_logger(__name__)


# ─── DTOs (Data Transfer Objects) ─────────────────────────────
# Los DTOs son estructuras simples para pasar datos entre capas.
# Evitan que el dominio se acople a la presentación.

@dataclass
class RegisterUserCommand:
    """Datos necesarios para registrar un usuario."""
    email: str
    password: str
    first_name: str = ""
    last_name: str = ""
    role: str = "customer"


@dataclass
class UpdateUserCommand:
    """Datos para actualizar un usuario."""
    user_id: uuid.UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


@dataclass
class ChangeRoleCommand:
    """Comando para cambiar el rol de un usuario."""
    target_user_id: uuid.UUID
    new_role: str
    requested_by_id: uuid.UUID


@dataclass
class SuspendUserCommand:
    """Comando para suspender un usuario."""
    target_user_id: uuid.UUID
    reason: str
    requested_by_id: uuid.UUID


@dataclass
class UserDTO:
    """DTO de respuesta para representar un usuario."""
    id: str
    email: str
    first_name: str
    last_name: str
    full_name: str
    role: str
    status: str
    is_active: bool
    last_login: Optional[str]
    created_at: str


# ─── Event Publisher Interface (Puerto) ──────────────────────
# La capa de aplicación necesita publicar eventos, pero no sabe
# cómo (Kafka, RabbitMQ, Redis...). Definimos un puerto (interfaz).

class EventPublisher:
    """
    Puerto para publicar domain events.
    
    Las implementaciones concretas (Kafka, RabbitMQ, Log) viven
    en la capa de infraestructura.
    """
    def publish(self, event) -> None:
        raise NotImplementedError


# ─── Password Hasher Interface (Puerto) ──────────────────────
class PasswordHasher:
    """Puerto para hashear contraseñas."""
    def hash(self, password: str) -> str:
        raise NotImplementedError

    def verify(self, password: str, hashed: str) -> bool:
        raise NotImplementedError


# ─── Email Verifier Interface (Puerto) ───────────────────────
class EmailVerificationService:
    """Puerto para enviar emails de verificación."""
    def send_verification_email(self, user_id: str, email: str, token: str) -> None:
        raise NotImplementedError


# ─── Caso de Uso: Registrar Usuario ──────────────────────────

class RegisterUserUseCase:
    """
    Caso de Uso: Registrar un nuevo usuario.
    
    FLUJO:
    1. Validar que el email no esté en uso (repositorio)
    2. Crear la entidad User en el dominio
    3. Hashear la contraseña
    4. Persistir el usuario (repositorio)
    5. Publicar el evento UserRegistered (broker)
    6. Enviar email de verificación
    7. Devolver el DTO del usuario creado
    
    INYECCIÓN DE DEPENDENCIAS:
    Las dependencias se inyectan en el constructor.
    Esto facilita el testing (puedes inyectar mocks).
    """

    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: PasswordHasher,
        event_publisher: EventPublisher,
        email_service: EmailVerificationService,
    ):
        self.user_repository = user_repository
        self.password_hasher = password_hasher
        self.event_publisher = event_publisher
        self.email_service = email_service

    def execute(self, command: RegisterUserCommand) -> UserDTO:
        log = logger.bind(email=command.email, role=command.role)
        log.info("register_user_started")

        # 1. Validar email (el Value Object lanza excepción si es inválido)
        try:
            email = Email(command.email)
        except DomainException as e:
            log.warning("register_user_invalid_email", error=str(e))
            raise

        # 2. Comprobar unicidad del email
        if self.user_repository.exists_by_email(email):
            log.warning("register_user_email_exists")
            raise EmailAlreadyExistsError(command.email)

        # 3. Validar y obtener el rol
        try:
            role = UserRole(command.role)
        except ValueError:
            raise DomainException(f"Rol inválido: {command.role}", code="INVALID_ROLE")

        # 4. Crear la entidad en el dominio
        user = User(
            email=email,
            role=role,
            first_name=command.first_name,
            last_name=command.last_name,
        )

        # 5. Hashear contraseña (fuera del dominio, es infra)
        hashed_password = self.password_hasher.hash(command.password)

        # 6. Persistir (el repositorio sabe cómo guardar User con su password hash)
        self.user_repository.save(user, hashed_password=hashed_password)

        # 7. Publicar domain events acumulados
        events = user.pull_events()
        for event in events:
            self.event_publisher.publish(event)
            log.info("domain_event_published", event_type=event.event_type)

        # 8. Enviar email de verificación
        verification_token = secrets.token_urlsafe(32)
        self.email_service.send_verification_email(
            user_id=str(user.id),
            email=str(user.email),
            token=verification_token,
        )

        log.info("register_user_completed", user_id=str(user.id))
        return self._to_dto(user)

    def _to_dto(self, user: User) -> UserDTO:
        return UserDTO(
            id=str(user.id),
            email=str(user.email),
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            role=user.role.value,
            status=user.status.value,
            is_active=user.is_active,
            last_login=user.last_login.isoformat() if user.last_login else None,
            created_at=user._created_at.isoformat(),
        )


# ─── Caso de Uso: Obtener Usuario ────────────────────────────

class GetUserUseCase:
    """
    Caso de Uso: Obtener datos de un usuario.
    
    Es un Query (no modifica estado).
    Incluye control de acceso: un usuario solo puede ver
    su propio perfil a menos que sea admin.
    """

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    def execute(self, user_id: uuid.UUID, requested_by_id: uuid.UUID) -> UserDTO:
        # El usuario que hace la petición
        requester = self.user_repository.get_by_id(requested_by_id)
        if not requester:
            raise UserNotFoundError(str(requested_by_id))

        # Solo admins pueden ver a otros usuarios
        if user_id != requested_by_id and not requester.is_admin:
            raise DomainException(
                "No tienes permisos para ver este perfil",
                code="FORBIDDEN"
            )

        target_user = self.user_repository.get_by_id(user_id)
        if not target_user:
            raise UserNotFoundError(str(user_id))

        return self._to_dto(target_user)

    def _to_dto(self, user: User) -> UserDTO:
        return UserDTO(
            id=str(user.id),
            email=str(user.email),
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            role=user.role.value,
            status=user.status.value,
            is_active=user.is_active,
            last_login=user.last_login.isoformat() if user.last_login else None,
            created_at=user._created_at.isoformat(),
        )


# ─── Caso de Uso: Cambiar Rol ─────────────────────────────────

class ChangeUserRoleUseCase:
    """
    Caso de Uso: Cambiar el rol de un usuario.
    
    La lógica de negocio (quién puede cambiar qué rol)
    vive en la entidad User del dominio, no aquí.
    La capa de aplicación solo orquesta.
    """

    def __init__(
        self,
        user_repository: UserRepository,
        event_publisher: EventPublisher,
    ):
        self.user_repository = user_repository
        self.event_publisher = event_publisher

    def execute(self, command: ChangeRoleCommand) -> UserDTO:
        log = logger.bind(
            target_user_id=str(command.target_user_id),
            new_role=command.new_role,
            requested_by=str(command.requested_by_id)
        )

        # Cargar quien hace la petición
        requester = self.user_repository.get_by_id(command.requested_by_id)
        if not requester:
            raise UserNotFoundError(str(command.requested_by_id))

        # Cargar el usuario objetivo
        target_user = self.user_repository.get_by_id(command.target_user_id)
        if not target_user:
            raise UserNotFoundError(str(command.target_user_id))

        # Validar y parsear el nuevo rol
        try:
            new_role = UserRole(command.new_role)
        except ValueError:
            raise DomainException(f"Rol inválido: {command.new_role}", code="INVALID_ROLE")

        # Delegar la lógica de negocio al dominio
        # (la entidad User verifica las reglas)
        target_user.change_role(new_role, changed_by=requester)

        # Persistir
        self.user_repository.save(target_user)

        # Publicar eventos
        for event in target_user.pull_events():
            self.event_publisher.publish(event)

        log.info("user_role_changed")
        return self._to_dto(target_user)

    def _to_dto(self, user: User) -> UserDTO:
        return UserDTO(
            id=str(user.id),
            email=str(user.email),
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            role=user.role.value,
            status=user.status.value,
            is_active=user.is_active,
            last_login=user.last_login.isoformat() if user.last_login else None,
            created_at=user._created_at.isoformat(),
        )
