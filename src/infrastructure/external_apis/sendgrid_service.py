"""
=============================================================================
ADAPTADOR: SendGridNotificationService
=============================================================================

Implementación concreta del puerto NotificationService usando SendGrid.
SendGrid es el servicio de email transaccional más usado en producción.

Características que usamos:
- Templates dinámicos (HTML pre-diseñados)
- Tracking de apertura y clicks
- Métricas de entrega
- Bounce handling
"""
import structlog
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To, From
from django.conf import settings

from src.application.ports.notification_service import NotificationService

logger = structlog.get_logger(__name__)


class SendGridNotificationService(NotificationService):
    """Envío de emails transaccionales via SendGrid."""

    # IDs de templates en SendGrid (se crean en el dashboard)
    TEMPLATES = {
        'welcome': 'd-xxxxxxxxxxxxxxxxxxxx',          # Template de bienvenida
        'order_confirmation': 'd-yyyyyyyyyyyyyyyy',   # Confirmación de pedido
        'payment_confirmation': 'd-zzzzzzzzzzzzzzzz',
        'password_reset': 'd-aaaaaaaaaaaaaaaaaa',
    }

    def __init__(self):
        self._client = SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        self._from_email = settings.DEFAULT_FROM_EMAIL

    def send_welcome_email(self, to_email: str, user_name: str) -> None:
        """Envía email de bienvenida."""
        self._send_template(
            to_email=to_email,
            template_id=self.TEMPLATES['welcome'],
            dynamic_data={
                'user_name': user_name,
                'login_url': 'https://tuapp.com/login',
            },
        )

    def send_order_confirmation(self, to_email: str, order_id: str, total: str) -> None:
        """Envía confirmación de pedido."""
        self._send_template(
            to_email=to_email,
            template_id=self.TEMPLATES['order_confirmation'],
            dynamic_data={
                'order_id': order_id,
                'total': total,
                'order_url': f'https://tuapp.com/orders/{order_id}',
            },
        )

    def send_payment_confirmation(self, to_email: str, order_id: str, amount: str) -> None:
        """Envía confirmación de pago."""
        self._send_template(
            to_email=to_email,
            template_id=self.TEMPLATES['payment_confirmation'],
            dynamic_data={'order_id': order_id, 'amount': amount},
        )

    def send_password_reset(self, to_email: str, reset_token: str) -> None:
        """Envía enlace de reset de contraseña."""
        reset_url = f"https://tuapp.com/reset-password?token={reset_token}"
        self._send_template(
            to_email=to_email,
            template_id=self.TEMPLATES['password_reset'],
            dynamic_data={
                'reset_url': reset_url,
                'expiry_minutes': 30,
            },
        )

    def _send_template(self, to_email: str, template_id: str, dynamic_data: dict) -> None:
        """
        Envía un email usando un template dinámico de SendGrid.
        Maneja errores y logging de forma centralizada.
        """
        message = Mail(
            from_email=self._from_email,
            to_emails=to_email,
        )
        message.template_id = template_id
        message.dynamic_template_data = dynamic_data

        try:
            response = self._client.send(message)
            logger.info(
                "email_sent",
                to=to_email,
                template=template_id,
                status_code=response.status_code,
            )
        except Exception as e:
            logger.error(
                "email_send_failed",
                to=to_email,
                template=template_id,
                error=str(e),
            )
            # En producción: reintentar via Celery con backoff exponencial
            # No relanzar — los emails no deben bloquear la respuesta API


class ConsoleNotificationService(NotificationService):
    """
    Implementación de desarrollo que imprime en consola.
    Usada en tests y entorno local para no necesitar SendGrid.
    
    Este patrón (implementación fake/stub) es fundamental en DDD:
    permite desarrollar sin dependencias externas.
    """

    def send_welcome_email(self, to_email: str, user_name: str) -> None:
        logger.info("📧 [DEV] Welcome email", to=to_email, user=user_name)

    def send_order_confirmation(self, to_email: str, order_id: str, total: str) -> None:
        logger.info("📧 [DEV] Order confirmation", to=to_email, order_id=order_id, total=total)

    def send_payment_confirmation(self, to_email: str, order_id: str, amount: str) -> None:
        logger.info("📧 [DEV] Payment confirmation", to=to_email, order_id=order_id)

    def send_password_reset(self, to_email: str, reset_token: str) -> None:
        logger.info("📧 [DEV] Password reset", to=to_email, token=reset_token[:8] + "...")
