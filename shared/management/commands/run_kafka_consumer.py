"""
============================================================
MANAGEMENT COMMAND: run_kafka_consumer
============================================================
Comando Django para iniciar el consumer de Kafka como proceso.

Uso:
  python manage.py run_kafka_consumer
  python manage.py run_kafka_consumer --topics orders.events user.events

En producción, se gestiona como servicio systemd o proceso Docker.
============================================================
"""

from django.core.management.base import BaseCommand
from shared.infrastructure.messaging.kafka_consumer import KafkaConsumer
from django.conf import settings


def handle_user_registered(event_data: dict) -> None:
    """Handler para el evento user.registered."""
    from apps.notifications.infrastructure.tasks import send_welcome_email
    user_id = event_data['aggregate_id']
    payload = event_data['payload']
    # Encolar la tarea de email en Celery
    send_welcome_email.delay(
        user_id=user_id,
        email=payload.get('email', ''),
        name=payload.get('name', ''),
    )


def handle_order_confirmed(event_data: dict) -> None:
    """Handler para el evento order.confirmed."""
    from apps.notifications.infrastructure.tasks import send_order_confirmation
    order_id = event_data['aggregate_id']
    payload = event_data['payload']
    send_order_confirmation.delay(
        order_id=order_id,
        user_email=payload.get('user_email', ''),
        total=payload.get('total', '0'),
    )


class Command(BaseCommand):
    help = 'Inicia el consumer de eventos Kafka'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topics',
            nargs='+',
            default=['users.events', 'orders.events'],
            help='Topics de Kafka a consumir',
        )

    def handle(self, *args, **options):
        topics = options['topics']
        self.stdout.write(f"Iniciando Kafka consumer para topics: {topics}")

        consumer = KafkaConsumer(
            topics=topics,
            group_id=settings.KAFKA_CONFIG['consumer_group'],
        )

        # Registrar handlers
        consumer.register_handler('user.registered', handle_user_registered)
        consumer.register_handler('order.confirmed', handle_order_confirmed)

        # Iniciar (bloqueante)
        consumer.start()
