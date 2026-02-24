"""
============================================================
PASSWORD SERVICE - Servicio de dominio
============================================================
Los Domain Services encapsulan lógica de dominio que no
pertenece naturalmente a ninguna entidad.

En este caso, el hashing de contraseñas necesita librerías
externas (bcrypt/argon2), así que usamos una interfaz en
el dominio y la implementación en infraestructura.
============================================================
"""

from abc import ABC, abstractmethod


class PasswordHashService(ABC):
    """
    Puerto de entrada para el servicio de hashing de contraseñas.
    El dominio define la interfaz; infraestructura implementa con bcrypt/argon2.
    """

    @abstractmethod
    def hash(self, plain_password: str) -> str:
        """Genera un hash seguro de la contraseña."""
        raise NotImplementedError

    @abstractmethod
    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verifica si una contraseña coincide con su hash."""
        raise NotImplementedError

    @staticmethod
    def validate_strength(password: str) -> None:
        """
        Valida que la contraseña cumpla la política de seguridad.
        Esta lógica SÍ vive en el dominio porque es una regla de negocio.
        """
        if len(password) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        if not any(c.isupper() for c in password):
            raise ValueError("La contraseña debe tener al menos una mayúscula")
        if not any(c.isdigit() for c in password):
            raise ValueError("La contraseña debe tener al menos un número")
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
            raise ValueError("La contraseña debe tener al menos un símbolo especial")
