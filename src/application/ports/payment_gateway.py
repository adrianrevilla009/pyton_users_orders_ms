"""
=============================================================================
PUERTO: PaymentGateway
=============================================================================

Interface para procesamiento de pagos.
Implementación concreta: Stripe (en infraestructura).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class PaymentIntent:
    """Resultado de crear un intent de pago."""
    payment_intent_id: str
    client_secret: str  # Se envía al frontend para completar el pago
    amount: Decimal
    currency: str
    status: str


@dataclass
class PaymentResult:
    """Resultado de procesar un pago."""
    payment_id: str
    status: str
    amount: Decimal
    currency: str
    error_message: Optional[str] = None

    @property
    def is_successful(self) -> bool:
        return self.status == 'succeeded'


class PaymentGateway(ABC):
    """Puerto de salida para pagos."""

    @abstractmethod
    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        metadata: dict,
    ) -> PaymentIntent:
        """Crea un intent de pago (paso 1 del flujo Stripe)."""
        ...

    @abstractmethod
    def confirm_payment(self, payment_intent_id: str) -> PaymentResult:
        """Confirma que el pago se completó."""
        ...

    @abstractmethod
    def refund_payment(self, payment_id: str, amount: Optional[Decimal] = None) -> PaymentResult:
        """Reembolsa un pago (total o parcial)."""
        ...
