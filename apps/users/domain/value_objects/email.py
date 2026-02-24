"""Value Object Email para el dominio de usuarios."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UserEmail:
    """
    Value Object para email de usuario.
    Valida el formato en el constructor - si llega aquí, es válido.
    El dominio nunca trabaja con strings raw para emails.
    """
    value: str

    def __post_init__(self):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, self.value):
            raise ValueError(f"Formato de email inválido: '{self.value}'")
        object.__setattr__(self, 'value', self.value.lower().strip())

    def __str__(self) -> str:
        return self.value

    def domain(self) -> str:
        """Retorna el dominio del email (parte después de @)."""
        return self.value.split('@')[1]
