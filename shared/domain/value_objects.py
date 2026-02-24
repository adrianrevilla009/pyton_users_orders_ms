"""
============================================================
VALUE OBJECTS - Objetos de valor base
============================================================
Un Value Object en DDD:
- NO tiene identidad propia (se identifica por su valor)
- Es inmutable
- Es intercambiable: dos VO con los mismos valores son idénticos

Ejemplos: Email, Money, Address, PhoneNumber...
============================================================
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)  # frozen=True lo hace inmutable
class Email:
    """Value Object para email. Valida formato en construcción."""
    value: str

    def __post_init__(self):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, self.value):
            raise ValueError(f"Email inválido: {self.value}")
        # __post_init__ no puede usar self.value = porque es frozen
        # Usamos object.__setattr__ para normalizar
        object.__setattr__(self, 'value', self.value.lower())

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Money:
    """
    Value Object para dinero.
    NUNCA usar float para dinero - siempre Decimal.
    """
    amount: Decimal
    currency: str = "EUR"

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("El importe no puede ser negativo")
        if len(self.currency) != 3:
            raise ValueError(f"Moneda inválida: {self.currency}. Usa ISO 4217 (EUR, USD...)")
        object.__setattr__(self, 'amount', Decimal(str(self.amount)))
        object.__setattr__(self, 'currency', self.currency.upper())

    def add(self, other: 'Money') -> 'Money':
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def subtract(self, other: 'Money') -> 'Money':
        self._assert_same_currency(other)
        result = self.amount - other.amount
        if result < 0:
            raise ValueError("El resultado no puede ser negativo")
        return Money(result, self.currency)

    def multiply(self, factor: Decimal) -> 'Money':
        return Money(self.amount * factor, self.currency)

    def _assert_same_currency(self, other: 'Money'):
        if self.currency != other.currency:
            raise ValueError(f"No se pueden operar monedas distintas: {self.currency} vs {other.currency}")

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"


@dataclass(frozen=True)
class Address:
    """Value Object para dirección postal."""
    street: str
    city: str
    country: str
    postal_code: str
    state: Optional[str] = None

    def __post_init__(self):
        if not self.street or not self.city or not self.country:
            raise ValueError("Calle, ciudad y país son obligatorios")

    def __str__(self) -> str:
        parts = [self.street, self.postal_code, self.city]
        if self.state:
            parts.append(self.state)
        parts.append(self.country)
        return ", ".join(parts)
