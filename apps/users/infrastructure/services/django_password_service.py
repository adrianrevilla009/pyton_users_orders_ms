"""
============================================================
DJANGO PASSWORD SERVICE - Implementación con Django auth
============================================================
Implementa el puerto PasswordHashService del dominio
usando el sistema de hashing de Django (pbkdf2 + bcrypt).
============================================================
"""

from django.contrib.auth.hashers import make_password, check_password
from apps.users.domain.services.password_service import PasswordHashService


class DjangoPasswordService(PasswordHashService):
    """
    Adaptador: usa Django's password hashing (PBKDF2 por defecto,
    configurable con Argon2 o bcrypt via PASSWORD_HASHERS en settings).
    """

    def hash(self, plain_password: str) -> str:
        """Genera hash usando el algoritmo configurado en Django."""
        return make_password(plain_password)

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verifica la contraseña contra el hash."""
        return check_password(plain_password, hashed_password)
