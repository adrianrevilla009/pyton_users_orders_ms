"""
============================================================
REGISTER USER USE CASE - Caso de uso de aplicación
============================================================
Los Use Cases (también llamados Application Services) son:
- Orquestadores: coordinan entidades, repositorios y servicios
- Sin lógica de negocio propia: delegan al dominio
- Transaccionales: o todo funciona o nada

Flujo típico de un Use Case:
1. Validar entrada (DTO)
2. Cargar/crear entidades de dominio
3. Ejecutar lógica de dominio
4. Persistir cambios (repositorio)
5. Publicar Domain Events (broker)
6. Retornar DTO de respuesta

En arquitectura hexagonal, los use cases son "puertos de entrada".
============================================================
"""

import structlog
from apps.users.domain.entities.user import User
from apps.users.domain.repositories.user_repository import UserRepository
from apps.users.domain.services.password_service import PasswordHashService
from apps.users.domain.value_objects.email import UserEmail
from apps.users.application.dtos.user_dtos import RegisterUserDTO, UserResponseDTO
from shared.infrastructure.messaging.event_publisher import EventPublisher

# Logger estructurado - los logs incluirán contexto automáticamente
logger = structlog.get_logger(__name__)


class UserAlreadyExistsError(Exception):
    """Error de dominio: el email ya está registrado."""
    pass


class RegisterUserUseCase:
    """
    Caso de uso: Registrar un nuevo usuario.
    
    Inyección de dependencias en el constructor.
    Esto permite:
    - Tests con mocks/fakes fácilmente
    - Desacoplar de implementaciones concretas
    """

    def __init__(
        self,
        user_repository: UserRepository,           # Puerto: persistencia
        password_service: PasswordHashService,      # Puerto: hashing
        event_publisher: EventPublisher,            # Puerto: mensajería
    ):
        self._user_repo = user_repository
        self._password_service = password_service
        self._event_publisher = event_publisher

    def execute(self, dto: RegisterUserDTO) -> UserResponseDTO:
        """
        Ejecuta el registro del usuario.
        
        Args:
            dto: Datos validados del nuevo usuario
            
        Returns:
            UserResponseDTO con los datos del usuario creado
            
        Raises:
            UserAlreadyExistsError: Si el email ya está registrado
            ValueError: Si los datos no cumplen las reglas de dominio
        """
        logger.info("Iniciando registro de usuario", email=dto.email)

        # 1. Verificar que el email no existe
        email_vo = UserEmail(dto.email)
        if self._user_repo.exists_by_email(email_vo):
            logger.warning("Intento de registro con email duplicado", email=dto.email)
            raise UserAlreadyExistsError(f"Ya existe un usuario con el email: {dto.email}")

        # 2. Validar fortaleza de contraseña (regla de dominio)
        PasswordHashService.validate_strength(dto.password)

        # 3. Hashear la contraseña (servicio de dominio)
        hashed_password = self._password_service.hash(dto.password)

        # 4. Crear la entidad de dominio (genera el domain event internamente)
        user = User.create(
            name=dto.name,
            email=dto.email,
            hashed_password=hashed_password,
        )

        # 5. Persistir el usuario
        saved_user = self._user_repo.save(user)

        # 6. Publicar Domain Events al broker (Kafka/RabbitMQ)
        # Los eventos se publican DESPUÉS de persistir para garantizar consistencia
        domain_events = saved_user.pull_domain_events()
        for event in domain_events:
            self._event_publisher.publish(event)
            logger.info("Evento de dominio publicado", event_type=event.event_type)

        logger.info(
            "Usuario registrado exitosamente",
            user_id=saved_user.id,
            email=str(saved_user.email),
            role=saved_user.role.value,
        )

        # 7. Retornar DTO de respuesta (nunca la entidad de dominio)
        return UserResponseDTO(
            id=saved_user.id,
            name=saved_user.name,
            email=str(saved_user.email),
            role=saved_user.role.value,
            status=saved_user.status.value,
            login_count=saved_user.login_count,
            created_at=saved_user.created_at,
            updated_at=saved_user.updated_at,
        )
