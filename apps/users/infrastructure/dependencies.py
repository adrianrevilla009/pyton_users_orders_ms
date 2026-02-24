"""
============================================================
DEPENDENCY INJECTION - Composición de dependencias
============================================================
En Python no hay un contenedor DI estándar como Spring en Java.
Aquí implementamos una solución sencilla con funciones factory.

Para proyectos más grandes considerar:
- dependency-injector (librería)
- punq
- lagom

El patrón: cada función factory construye el grafo de
dependencias completo para un Use Case.
============================================================
"""

from functools import lru_cache

from apps.users.infrastructure.repositories.django_user_repository import DjangoUserRepository
from apps.users.infrastructure.repositories.cached_user_repository import CachedUserRepository
from apps.users.infrastructure.services.django_password_service import DjangoPasswordService
from apps.users.infrastructure.services.jwt_token_service import JwtTokenService
from apps.users.application.use_cases.register_user import RegisterUserUseCase
from apps.users.application.use_cases.login_user import LoginUserUseCase
from shared.infrastructure.messaging.event_publisher import KafkaEventPublisher


def get_user_repository():
    """
    Construye el repositorio con caché Redis.
    Patrón Decorator: CachedRepo envuelve DjangoRepo.
    """
    base_repo = DjangoUserRepository()
    return CachedUserRepository(base_repo)


def get_register_use_case() -> RegisterUserUseCase:
    """Factory del Use Case de registro."""
    return RegisterUserUseCase(
        user_repository=get_user_repository(),
        password_service=DjangoPasswordService(),
        event_publisher=KafkaEventPublisher(),
    )


def get_login_use_case() -> LoginUserUseCase:
    """Factory del Use Case de login."""
    return LoginUserUseCase(
        user_repository=get_user_repository(),
        password_service=DjangoPasswordService(),
        token_service=JwtTokenService(),
    )
