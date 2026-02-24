"""
=============================================================================
ADAPTADOR: StripePaymentGateway
=============================================================================

Implementación concreta del puerto PaymentGateway usando Stripe.

Flujo de pago con Stripe:
1. Backend crea un PaymentIntent → devuelve client_secret al frontend
2. Frontend usa Stripe.js con client_secret para recoger datos de tarjeta
3. Stripe procesa el pago y llama a nuestro webhook
4. Backend recibe webhook → marca el pedido como pagado

Este flujo (con webhooks) es más robusto que confiar solo en el callback
del frontend (que puede fallar por problemas de red, etc.).
"""
from decimal import Decimal
from typing import Optional

import stripe
import structlog
from django.conf import settings

from src.application.ports.payment_gateway import PaymentGateway, PaymentIntent, PaymentResult

logger = structlog.get_logger(__name__)


class StripePaymentGateway(PaymentGateway):
    """
    Adaptador para la API de Stripe.
    Implementa el puerto PaymentGateway del dominio de aplicación.
    """

    def __init__(self):
        # Configurar la API key de Stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        metadata: dict,
    ) -> PaymentIntent:
        """
        Crea un PaymentIntent en Stripe.
        
        El amount se envía en centavos (Stripe usa integers):
        10.99 EUR → 1099
        """
        amount_cents = int(amount * 100)

        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency.lower(),
                metadata=metadata,
                # Métodos de pago aceptados
                payment_method_types=['card'],
                # Captura automática (vs. autorizar primero y capturar después)
                capture_method='automatic',
            )

            logger.info(
                "stripe_payment_intent_created",
                intent_id=intent.id,
                amount=amount_cents,
                currency=currency,
            )

            return PaymentIntent(
                payment_intent_id=intent.id,
                client_secret=intent.client_secret,
                amount=amount,
                currency=currency,
                status=intent.status,
            )

        except stripe.error.CardError as e:
            logger.warning("stripe_card_error", error=str(e))
            raise ValueError(f"Error de tarjeta: {e.user_message}")
        except stripe.error.StripeError as e:
            logger.error("stripe_api_error", error=str(e))
            raise RuntimeError(f"Error procesando pago: {str(e)}")

    def confirm_payment(self, payment_intent_id: str) -> PaymentResult:
        """Verifica el estado de un PaymentIntent."""
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)

            return PaymentResult(
                payment_id=intent.id,
                status=intent.status,
                amount=Decimal(intent.amount) / 100,
                currency=intent.currency.upper(),
                error_message=intent.last_payment_error.get('message') if intent.last_payment_error else None,
            )

        except stripe.error.StripeError as e:
            logger.error("stripe_confirm_failed", payment_id=payment_intent_id, error=str(e))
            raise

    def refund_payment(self, payment_id: str, amount: Optional[Decimal] = None) -> PaymentResult:
        """Crea un reembolso en Stripe."""
        try:
            refund_params = {'payment_intent': payment_id}
            if amount:
                refund_params['amount'] = int(amount * 100)

            refund = stripe.Refund.create(**refund_params)

            logger.info("stripe_refund_created", payment_id=payment_id, refund_id=refund.id)

            return PaymentResult(
                payment_id=refund.id,
                status=refund.status,
                amount=Decimal(refund.amount) / 100,
                currency=refund.currency.upper(),
            )

        except stripe.error.StripeError as e:
            logger.error("stripe_refund_failed", payment_id=payment_id, error=str(e))
            raise

    def handle_webhook(self, payload: bytes, signature: str) -> dict:
        """
        Procesa un webhook de Stripe de forma segura.
        Verifica la firma para garantizar que viene de Stripe.
        """
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=signature,
                secret=settings.STRIPE_WEBHOOK_SECRET,
            )
            logger.info("stripe_webhook_received", event_type=event.type)
            return event

        except stripe.error.SignatureVerificationError:
            logger.warning("stripe_webhook_signature_invalid")
            raise ValueError("Firma de webhook inválida")
