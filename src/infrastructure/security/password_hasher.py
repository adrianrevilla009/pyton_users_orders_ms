"""Puerto e implementación para hash de contraseñas."""
from abc import ABC, abstractmethod
from django.contrib.auth.hashers import make_password, check_password


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str: ...

    @abstractmethod
    def verify(self, password: str, hashed: str) -> bool: ...


class DjangoPasswordHasher(PasswordHasher):
    """Usa el sistema de hashing de Django (argon2 configurado en settings)."""

    def hash(self, password: str) -> str:
        return make_password(password)

    def verify(self, password: str, hashed: str) -> bool:
        return check_password(password, hashed)
