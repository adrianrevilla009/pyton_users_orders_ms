"""
=============================================================================
VALUE OBJECT: Address
=============================================================================

Dirección postal. Inmutable por ser VO.
Si una dirección cambia, se crea una nueva (no se modifica la existente).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Address:
    """Dirección física completa."""
    street: str
    city: str
    postal_code: str
    country: str  # ISO 3166-1 alpha-2: ES, FR, DE...
    state: str = ''

    def __post_init__(self):
        if not self.street or not self.city or not self.postal_code:
            raise ValueError("Calle, ciudad y código postal son obligatorios")
        if len(self.country) != 2:
            raise ValueError(f"País inválido (debe ser ISO 3166-1 alpha-2): {self.country}")
        object.__setattr__(self, 'country', self.country.upper())

    def __str__(self) -> str:
        parts = [self.street, self.city]
        if self.state:
            parts.append(self.state)
        parts.extend([self.postal_code, self.country])
        return ', '.join(parts)
