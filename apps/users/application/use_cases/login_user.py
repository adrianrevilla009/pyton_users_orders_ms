"""
============================================================
LOGIN USE CASE
============================================================
Gestiona la autenticación del usuario.
Retorna tokens JWT para acceso a la API.
============================================================
"""

import structlog
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from apps.users.domain.repositories.user_repository import UserRepository
from apps.users.domain.services.password_service import PasswordHashService
from apps.users.domain.value_objects.email import UserEmail

logger = structlog.get_logger(__name__)


@dataclass
class LoginResponseDTO:
    """Respuesta del login con tokens JWT."""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    user_id: str = ""
    email: str = ""
    role: str = ""


class TokenService(ABC):
    """Puerto: servicio de generación de tokens JWT."""
    @abstractmethod
    def generate_access_token(self, user_id: str, email: str, role: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_refresh_token(self, user_id: str) -> str:
        raise NotImplementedError


class AuthenticationError(Exception):
    """Credenciales incorrectas o usuario no autorizado."""
    pass


class LoginUserUseCase:
    """
    Caso de uso: Autenticar usuario y generar tokens JWT.
    """

    def __init__(
        self,
        user_repository: UserRepository,
        password_service: PasswordHashService,
        token_service: TokenService,
    ):
        self._user_repo = user_repository
        self._password_service = password_service
        self._token_service = token_service

    def execute(self, email: str, password: str) -> LoginResponseDTO:
        """
        Autenticación en 3 pasos:
        1. Buscar usuario por email
        2. Verificar contraseña
        3. Generar tokens JWT
        """
        logger.info("Intento de login", email=email)

        # Buscar usuario (misma respuesta si no existe o si la pass es incorrecta
        # para evitar user enumeration attacks)
        user = self._user_repo.find_by_email(UserEmail(email))

        # Verificar contraseña (incluso si el usuario no existe, para evitar timing attacks)
        if user is None:
            self._password_service.verify(password, "fake_hash_to_prevent_timing_attack")
            logger.warning("Login fallido: usuario no encontrado", email=email)
            raise AuthenticationError("Credenciales incorrectas")

        if not self._password_service.verify(password, str(user.hashed_password)):
            logger.warning("Login fallido: contraseña incorrecta", user_id=user.id)
            raise AuthenticationError("Credenciales incorrectas")

        # Verificar que el usuario está activo
        if not user.is_active:
            logger.warning("Login bloqueado: usuario inactivo", user_id=user.id, status=user.status.value)
            raise AuthenticationError(f"Cuenta no disponible. Estado: {user.status.value}")

        # Registrar el login en el dominio
        user.record_login()
        self._user_repo.save(user)

        # Generar tokens
        access_token = self._token_service.generate_access_token(
            user_id=user.id,
            email=str(user.email),
            role=user.role.value,
        )
        refresh_token = self._token_service.generate_refresh_token(user_id=user.id)

        logger.info("Login exitoso", user_id=user.id, role=user.role.value)

        return LoginResponseDTO(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user.id,
            email=str(user.email),
            role=user.role.value,
        )
