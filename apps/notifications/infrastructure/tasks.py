"""
============================================================
CELERY TASKS - Tareas asíncronas de notificaciones
============================================================
Las tareas Celery se ejecutan en workers separados.
Son ideales para operaciones que no necesitan respuesta inmediata:
- Envío de emails
- Notificaciones push
- Procesamiento de imágenes
- Llamadas a APIs externas lentas

Configurar el worker:
  celery -A config worker --loglevel=info -Q notifications

Conceptos importantes:
- bind=True: permite acceder al objeto task (self) para reintentos
- max_retries: número máximo de reintentos
- countdown: segundos de espera antes de reintentar
============================================================
"""

import structlog
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

logger = structlog.get_logger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,     # 60 segundos entre reintentos
    queue='notifications',       # Cola específica para notificaciones
    name='send_welcome_email',
)
def send_welcome_email(self, user_id: str, email: str, name: str) -> dict:
    """
    Envía email de bienvenida a un nuevo usuario.
    
    Se ejecuta en background después del registro.
    Si falla, se reintenta automáticamente hasta 3 veces.
    """
    logger.info("Enviando email de bienvenida", user_id=user_id, email=email)

    try:
        # Simulación de envío de email
        # En producción: usar django.core.mail o SendGrid, Mailgun, etc.
        _send_email(
            to=email,
            subject=f"¡Bienvenido, {name}!",
            template='welcome',
            context={'name': name, 'user_id': user_id},
        )

        logger.info("Email de bienvenida enviado", user_id=user_id)
        return {'status': 'sent', 'user_id': user_id}

    except Exception as exc:
        logger.error("Error enviando email", user_id=user_id, error=str(exc))
        try:
            # Reintento con backoff exponencial
            raise self.retry(exc=exc, countdown=self.default_retry_delay * (2 ** self.request.retries))
        except MaxRetriesExceededError:
            logger.error("Máximo de reintentos alcanzado para email", user_id=user_id)
            return {'status': 'failed', 'user_id': user_id}


@shared_task(
    bind=True,
    max_retries=5,
    queue='notifications',
    name='send_order_confirmation',
)
def send_order_confirmation(self, order_id: str, user_email: str, total: str) -> dict:
    """Envía confirmación de pedido al usuario."""
    logger.info("Enviando confirmación de pedido", order_id=order_id)

    try:
        _send_email(
            to=user_email,
            subject=f"Pedido #{order_id[:8]} confirmado",
            template='order_confirmation',
            context={'order_id': order_id, 'total': total},
        )
        return {'status': 'sent', 'order_id': order_id}

    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(queue='maintenance', name='cleanup_expired_tokens')
def cleanup_expired_tokens() -> dict:
    """
    Tarea programada (cron) que limpia tokens JWT expirados.
    
    Se configura en Celery Beat:
    CELERY_BEAT_SCHEDULE = {
        'cleanup-tokens': {
            'task': 'cleanup_expired_tokens',
            'schedule': crontab(hour=2, minute=0),  # Cada día a las 2 AM
        }
    }
    """
    logger.info("Iniciando limpieza de tokens expirados")
    count = 0

    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        from django.utils import timezone
        expired = OutstandingToken.objects.filter(expires_at__lt=timezone.now())
        count = expired.count()
        expired.delete()
        logger.info("Tokens expirados eliminados", count=count)
    except Exception as e:
        logger.error("Error en limpieza de tokens", error=str(e))

    return {'deleted_count': count}


def _send_email(to: str, subject: str, template: str, context: dict) -> None:
    """
    Helper interno para enviar emails.
    En producción: integrar con Django's send_mail o un servicio externo.
    """
    from django.core.mail import send_mail
    from django.conf import settings

    # Por ahora solo loggeamos (en producción enviar de verdad)
    logger.info(
        "EMAIL (simulado)",
        to=to,
        subject=subject,
        template=template,
    )
