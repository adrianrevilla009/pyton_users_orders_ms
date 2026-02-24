"""
=============================================================================
ADAPTADOR: KafkaEventBus
=============================================================================

Implementación del puerto EventBus usando Apache Kafka.

Por qué Kafka para eventos de dominio:
- Durabilidad: los mensajes se persisten en disco (replay posible)
- Escalabilidad: particionamiento horizontal masivo
- Ordenación garantizada dentro de una partición
- Consumers independientes (múltiples sistemas pueden suscribirse)
- Replayability: reprocesar eventos históricos

Casos de uso en nuestro dominio:
- order.created → notificación email + actualizar inventario
- order.paid → iniciar envío
- user.created → enviar email bienvenida
- product.created → indexar en buscador
"""
import json
from datetime import datetime
from typing import Optional
import structlog
from django.conf import settings

from src.domain.events.base import DomainEvent
from src.application.ports.event_bus import EventBus

logger = structlog.get_logger(__name__)


class KafkaEventBus(EventBus):
    """
    Publicador de eventos de dominio via Kafka.
    
    El topic se determina automáticamente por el tipo de evento:
    - UserCreatedEvent → 'notifications.events'
    - OrderCreatedEvent → 'orders.events'
    - etc.
    """

    # Mapeo evento → topic de Kafka
    EVENT_TOPIC_MAP = {
        'UserCreatedEvent': 'notifications.events',
        'UserActivatedEvent': 'notifications.events',
        'UserSuspendedEvent': 'notifications.events',
        'OrderCreatedEvent': 'orders.events',
        'OrderPaidEvent': 'orders.events',
        'OrderCancelledEvent': 'orders.events',
        'ProductCreatedEvent': 'notifications.events',
    }
    DEFAULT_TOPIC = 'general.events'

    def __init__(self):
        self._producer = None
        self._config = settings.KAFKA_CONFIG

    @property
    def producer(self):
        """Lazy initialization del producer (conexión bajo demanda)."""
        if self._producer is None:
            try:
                from confluent_kafka import Producer
                self._producer = Producer(self._config)
                logger.info("kafka_producer_connected")
            except Exception as e:
                logger.error("kafka_producer_connection_failed", error=str(e))
                raise
        return self._producer

    def publish(self, event: DomainEvent) -> None:
        """Publica un único evento de dominio en Kafka."""
        topic = self._get_topic(event)
        payload = self._serialize_event(event)

        try:
            self.producer.produce(
                topic=topic,
                key=event.event_id,          # Clave para particionamiento
                value=json.dumps(payload),
                callback=self._delivery_callback,
            )
            # Poll para procesar callbacks de entrega
            self.producer.poll(0)
            logger.info("event_published_to_kafka", event_type=event.event_type, topic=topic)

        except Exception as e:
            logger.error(
                "kafka_publish_failed",
                event_type=event.event_type,
                topic=topic,
                error=str(e),
            )
            # En producción: usar un outbox pattern para garantizar entrega
            raise

    def publish_many(self, events: list[DomainEvent]) -> None:
        """Publica múltiples eventos de forma eficiente (batch)."""
        if not events:
            return

        for event in events:
            self.publish(event)

        # Esperar a que todos los mensajes se entreguen
        self.producer.flush(timeout=10)

    def _get_topic(self, event: DomainEvent) -> str:
        """Determina el topic de Kafka para un tipo de evento."""
        return self.EVENT_TOPIC_MAP.get(event.event_type, self.DEFAULT_TOPIC)

    def _serialize_event(self, event: DomainEvent) -> dict:
        """Serializa el evento a un dict JSON-serializable."""
        # Convertimos el dataclass a dict usando __dict__
        event_data = {k: v for k, v in event.__dict__.items() if not k.startswith('_')}

        return {
            'event_id': event.event_id,
            'event_type': event.event_type,
            'occurred_at': event.occurred_at.isoformat(),
            'data': event_data,
            # Metadata del envelope — útil para el consumer
            'schema_version': '1.0',
            'source': 'techlead-api',
        }

    @staticmethod
    def _delivery_callback(err, msg):
        """Callback para confirmar entrega del mensaje."""
        if err:
            logger.error("kafka_delivery_failed", error=str(err))
        else:
            logger.debug(
                "kafka_message_delivered",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
            )


# =============================================================================
# CONSUMER de Kafka — para procesar eventos recibidos
# =============================================================================

class KafkaEventConsumer:
    """
    Consumer de eventos de Kafka.
    
    Se ejecuta como proceso separado (worker).
    Cada evento recibido se despacha al handler correspondiente.
    """

    def __init__(self, topics: list[str]):
        self.topics = topics
        self._consumer = None
        self._handlers: dict[str, callable] = {}

    def register_handler(self, event_type: str, handler: callable) -> None:
        """Registra un handler para un tipo de evento."""
        self._handlers[event_type] = handler
        logger.info("event_handler_registered", event_type=event_type)

    def start_consuming(self) -> None:
        """
        Inicia el bucle de consumo. Blocking — ejecutar en thread/proceso separado.
        """
        from confluent_kafka import Consumer, KafkaError

        config = {**settings.KAFKA_CONFIG, 'enable.auto.commit': False}
        consumer = Consumer(config)
        consumer.subscribe(self.topics)

        logger.info("kafka_consumer_started", topics=self.topics)

        try:
            while True:
                msg = consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error("kafka_consumer_error", error=str(msg.error()))
                    continue

                try:
                    payload = json.loads(msg.value().decode('utf-8'))
                    event_type = payload.get('event_type')

                    if event_type in self._handlers:
                        self._handlers[event_type](payload)
                        # Commit manual — solo tras procesar correctamente
                        consumer.commit(msg)
                    else:
                        logger.warning("no_handler_for_event", event_type=event_type)
                        consumer.commit(msg)

                except Exception as e:
                    logger.error("event_processing_failed", error=str(e), msg=str(msg.value()))
                    # En producción: enviar a Dead Letter Queue

        finally:
            consumer.close()
            logger.info("kafka_consumer_stopped")
