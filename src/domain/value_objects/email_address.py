"""
=============================================================================
VALUE OBJECT: EmailAddress
=============================================================================

Encapsula la lógica de validación de emails en el dominio.
En vez de tener strings de email dispersos por el código,
usamos este VO que garantiza que el email es siempre válido.
"""
import re
from dataclasses import dataclass


EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


@dataclass(frozen=True)
class EmailAddress:
    """Email validado y normalizado (lowercase)."""
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValueError("El email no puede estar vacío")

        normalized = self.value.strip().lower()
        object.__setattr__(self, 'value', normalized)

        if not EMAIL_REGEX.match(normalized):
            raise ValueError(f"Email inválido: {self.value}")

    @property
    def domain(self) -> str:
        """Extrae el dominio del email."""
        return self.value.split('@')[1]

    @property
    def local_part(self) -> str:
        """Extrae la parte local (antes del @)."""
        return self.value.split('@')[0]

    def __str__(self) -> str:
        return self.value
