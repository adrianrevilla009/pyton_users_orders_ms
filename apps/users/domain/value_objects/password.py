"""Value Object para contraseña hasheada."""
from dataclasses import dataclass


@dataclass(frozen=True)
class HashedPassword:
    """
    Value Object que encapsula una contraseña ya hasheada.
    El hashing se hace en la capa de infraestructura/aplicación,
    el dominio solo trabaja con el hash resultante.
    """
    value: str

    def __post_init__(self):
        if not self.value or len(self.value) < 10:
            raise ValueError("El hash de contraseña no parece válido")

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return "HashedPassword(***)"  # Nunca mostrar el hash en logs
