"""
=============================================================================
VALUE OBJECT: Money
=============================================================================

Los Value Objects son objetos INMUTABLES que se identifican por su VALOR,
no por su identidad. No tienen ID propio.

Características:
- Inmutables (frozen=True en dataclass)
- Igualdad por valor, no por referencia
- Sin efectos secundarios
- Encapsulan lógica del dominio relacionada con su tipo

Money encapsula dinero con su divisa, evitando el anti-patrón de usar
floats para representar dinero (problemas de precisión).
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Self


@dataclass(frozen=True)  # frozen=True lo hace inmutable
class Money:
    """
    Representa una cantidad monetaria con su divisa.

    Usa Decimal en vez de float para evitar errores de redondeo:
    >>> 0.1 + 0.2 == 0.3  -> False (float)
    >>> Decimal('0.1') + Decimal('0.2') == Decimal('0.3')  -> True
    """
    amount: Decimal
    currency: str  # ISO 4217: EUR, USD, GBP...

    def __post_init__(self):
        """Validación al crear el objeto — el dominio se protege a sí mismo."""
        if not isinstance(self.amount, Decimal):
            # Usamos object.__setattr__ porque frozen no permite setattr normal
            object.__setattr__(self, 'amount', Decimal(str(self.amount)))

        if self.amount < Decimal('0'):
            raise ValueError(f"El importe no puede ser negativo: {self.amount}")

        if len(self.currency) != 3:
            raise ValueError(f"Divisa inválida (debe ser ISO 4217): {self.currency}")

        object.__setattr__(self, 'currency', self.currency.upper())

    def add(self, other: 'Money') -> 'Money':
        """Suma dos importes de la misma divisa. El dominio rechaza divisas distintas."""
        self._assert_same_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def subtract(self, other: 'Money') -> 'Money':
        self._assert_same_currency(other)
        result = self.amount - other.amount
        if result < 0:
            raise ValueError("El resultado no puede ser negativo")
        return Money(amount=result, currency=self.currency)

    def multiply(self, factor: Decimal | int | float) -> 'Money':
        """Multiplica por un factor (útil para impuestos, descuentos)."""
        factor = Decimal(str(factor))
        # Redondear a 2 decimales con ROUND_HALF_UP (estándar financiero)
        new_amount = (self.amount * factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Money(amount=new_amount, currency=self.currency)

    def is_zero(self) -> bool:
        return self.amount == Decimal('0')

    def _assert_same_currency(self, other: 'Money') -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"No se pueden operar divisas distintas: {self.currency} vs {other.currency}"
            )

    @classmethod
    def zero(cls, currency: str = 'EUR') -> 'Money':
        """Factory method para crear un importe cero."""
        return cls(amount=Decimal('0'), currency=currency)

    @classmethod
    def from_cents(cls, cents: int, currency: str = 'EUR') -> 'Money':
        """Crea Money desde centavos (como los devuelve Stripe)."""
        return cls(amount=Decimal(cents) / Decimal('100'), currency=currency)

    def to_cents(self) -> int:
        """Convierte a centavos para enviar a Stripe."""
        return int(self.amount * 100)

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"

    def __repr__(self) -> str:
        return f"Money(amount={self.amount!r}, currency={self.currency!r})"
