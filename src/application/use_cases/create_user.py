"""
=============================================================================
CASO DE USO: CreateUser
=============================================================================

Los Casos de Uso (Application Services) orquestan las operaciones del dominio.
Coordinan repositorios, servicios de dominio y puertos externos.

NO contienen lógica de negocio — eso es del dominio.
Solo coordinan: "ejecuta A, luego B, luego publica evento C".

Principios aplicados:
- Single Responsibility: solo crea usuarios
- Dependency Injection: recibe sus dependencias en el constructor
- Dependency Inversion: depende de abstracciones (interfaces), no implementaciones
"""
import logging
import structlog

from src.domain.entities.user import User, UserRole
from src.domain.repositories.user_repository import UserRepository
from src.domain.value_objects.email_address import EmailAddress
from src.application.dtos.user_dtos import CreateUserCommand, UserResponse
from src.application.ports.event_bus import EventBus
from src.application.ports.notification_service import NotificationService

# Usamos structlog para logging estructurado — produce JSON en producción
logger = structlog.get_logger(__name__)


class UserAlreadyExistsError(Exception):
    """Error específico del dominio de aplicación."""
    pass


class CreateUserUseCase:
    """
    Caso de uso: Crear un nuevo usuario.

    Flujo:
    1. Validar que el email no existe
    2. Crear la entidad User (con hash de contraseña)
    3. Persistir en el repositorio
    4. Publicar eventos de dominio
    5. Enviar email de bienvenida (async via Celery)
    """

    def __init__(
        self,
        user_repository: UserRepository,
        event_bus: EventBus,
        notification_service: NotificationService,
        password_hasher,  # Puerto para hashear contraseñas
    ):
        # Inyección de dependencias — todas son interfaces, no implementaciones
        self.user_repository = user_repository
        self.event_bus = event_bus
        self.notification_service = notification_service
        self.password_hasher = password_hasher

    def execute(self, command: CreateUserCommand) -> UserResponse:
        """
        Ejecuta el caso de uso.

        Args:
            command: DTO con los datos de entrada validados

        Returns:
            UserResponse: DTO con los datos del usuario creado

        Raises:
            UserAlreadyExistsError: si el email ya está registrado
        """
        log = logger.bind(email=command.email, role=command.role)
        log.info("creating_user")

        # 1. Verificar que el email no existe
        email = EmailAddress(command.email)
        if self.user_repository.exists_by_email(email):
            log.warning("user_already_exists")
            raise UserAlreadyExistsError(f"Ya existe un usuario con email: {command.email}")

        # 2. Crear la entidad de dominio
        # El factory method del dominio garantiza las invariantes
        user = User.create(
            email=command.email,
            first_name=command.first_name,
            last_name=command.last_name,
            role=UserRole(command.role),
            phone=command.phone,
        )

        # 3. Hashear la contraseña (infraestructura, no dominio)
        user.password_hash = self.password_hasher.hash(command.password)

        # 4. Persistir — el repositorio maneja la traducción a ORM
        saved_user = self.user_repository.save(user)

        # 5. Publicar eventos de dominio
        # Los eventos ya fueron registrados en el aggregate durante user.create()
        # El repositorio los extrae y nosotros los publicamos
        # (En algunos patrones el repositorio los publica directamente)
        events = saved_user.pull_domain_events()
        self.event_bus.publish_many(events)

        # 6. Notificación (podría ser también via evento, pero mostramos el patrón directo)
        self.notification_service.send_welcome_email(
            to_email=str(saved_user.email),
            user_name=saved_user.first_name,
        )

        log.info("user_created", user_id=str(saved_user.id))

        # 7. Retornar DTO de respuesta (nunca la entidad directamente)
        return UserResponse(
            id=saved_user.id,
            email=str(saved_user.email),
            first_name=saved_user.first_name,
            last_name=saved_user.last_name,
            full_name=saved_user.full_name,
            role=saved_user.role.value,
            status=saved_user.status.value,
            created_at=saved_user.created_at,
        )
