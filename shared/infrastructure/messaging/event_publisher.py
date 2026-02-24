"""
============================================================
EVENT PUBLISHER - Publicación de Domain Events
============================================================
Puerto de salida para publicar eventos de dominio a brokers.
Implementaciones: Kafka, RabbitMQ, in-memory (para tests).

Patrón: el dominio llama al publisher después de persistir.
Esto garantiza que la BD y el broker están sincronizados
(aunque para garantía absoluta necesitarías el patrón Outbox).
============================================================
"""

import json
import structlog
from abc import ABC, abstractmethod
from shared.domain.base_entity import DomainEvent

logger = structlog.get_logger(__name__)


class EventPublisher(ABC):
    """Interfaz del publicador de eventos."""

    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        """Publica un evento de dominio al broker."""
        raise NotImplementedError

    def publish_many(self, events: list) -> None:
        """Publica múltiples eventos."""
        for event in events:
            self.publish(event)


class KafkaEventPublisher(EventPublisher):
    """
    Adaptador: publica eventos en Apache Kafka.
    
    Kafka es ideal para:
    - Alto volumen de eventos
    - Log de eventos ordenado y persistente
    - Múltiples consumidores independientes
    - Replay de eventos históricos
    """

    def __init__(self):
        self._producer = None
        self._initialized = False

    def _get_producer(self):
        """Lazy initialization del producer de Kafka."""
        if not self._initialized:
            try:
                from confluent_kafka import Producer
                from django.conf import settings
                self._producer = Producer({
                    'bootstrap.servers': settings.KAFKA_CONFIG['bootstrap_servers'],
                    # Garantía de entrega: todos los réplicas deben confirmar
                    'acks': 'all',
                    # Reintentos automáticos
                    'retries': 3,
                    'retry.backoff.ms': 1000,
                    # Compresión para reducir red
                    'compression.type': 'snappy',
                })
                self._initialized = True
            except Exception as e:
                logger.warning("Kafka no disponible, usando fallback", error=str(e))
                return None
        return self._producer

    def publish(self, event: DomainEvent) -> None:
        """
        Publica un evento en el topic correspondiente.
        El topic se determina por el tipo de evento.
        """
        from django.conf import settings

        # Determinar el topic según el tipo de evento
        topic = self._get_topic(event.event_type)
        payload = json.dumps({
            'event_id': event.event_id,
            'event_type': event.event_type,
            'aggregate_id': event.aggregate_id,
            'occurred_on': event.occurred_on.isoformat(),
            'payload': event.payload,
        })

        producer = self._get_producer()
        if producer is None:
            # Fallback: log el evento si Kafka no está disponible
            logger.warning(
                "Evento no publicado en Kafka (no disponible)",
                event_type=event.event_type,
                aggregate_id=event.aggregate_id,
            )
            return

        producer.produce(
            topic=topic,
            key=event.aggregate_id.encode('utf-8'),  # La clave garantiza orden por aggregate
            value=payload.encode('utf-8'),
            callback=self._delivery_report,
        )
        producer.flush()  # Esperar confirmación

        logger.info(
            "Evento publicado en Kafka",
            topic=topic,
            event_type=event.event_type,
            aggregate_id=event.aggregate_id,
        )

    def _get_topic(self, event_type: str) -> str:
        """Mapea el tipo de evento al topic de Kafka."""
        from django.conf import settings
        topics = settings.KAFKA_CONFIG['topics']

        if event_type.startswith('user.'):
            return 'users.events'
        elif event_type.startswith('order.'):
            return topics.get('orders', 'orders.events')
        elif event_type.startswith('notification.'):
            return topics.get('notifications', 'notifications.events')
        return 'general.events'

    def _delivery_report(self, err, msg):
        """Callback de confirmación de entrega de Kafka."""
        if err is not None:
            logger.error("Error publicando en Kafka", error=str(err))
        else:
            logger.debug("Mensaje entregado en Kafka", topic=msg.topic(), partition=msg.partition())


class RabbitMQEventPublisher(EventPublisher):
    """
    Adaptador: publica eventos en RabbitMQ.
    
    RabbitMQ es ideal para:
    - Colas de tareas con routing complejo
    - Confirmaciones y dead-letter queues
    - Topología flexible (fanout, direct, topic exchanges)
    """

    def __init__(self):
        self._connection = None
        self._channel = None

    def _get_channel(self):
        """Obtiene o crea el canal RabbitMQ."""
        try:
            import pika
            from django.conf import settings

            if self._connection is None or self._connection.is_closed:
                params = pika.URLParameters(settings.RABBITMQ_URL)
                self._connection = pika.BlockingConnection(params)
                self._channel = self._connection.channel()

                # Declarar el exchange tipo 'topic' para routing flexible
                self._channel.exchange_declare(
                    exchange='domain_events',
                    exchange_type='topic',   # Routing por patrón: 'user.*', 'order.*'
                    durable=True,            # Sobrevive reinicios del broker
                )
            return self._channel
        except Exception as e:
            logger.warning("RabbitMQ no disponible", error=str(e))
            return None

    def publish(self, event: DomainEvent) -> None:
        """Publica en RabbitMQ con routing key basado en el tipo de evento."""
        import pika

        channel = self._get_channel()
        if channel is None:
            logger.warning("Evento no publicado en RabbitMQ", event_type=event.event_type)
            return

        payload = json.dumps({
            'event_id': event.event_id,
            'event_type': event.event_type,
            'aggregate_id': event.aggregate_id,
            'occurred_on': event.occurred_on.isoformat(),
            'payload': event.payload,
        })

        channel.basic_publish(
            exchange='domain_events',
            routing_key=event.event_type,       # 'user.registered', 'order.shipped', etc.
            body=payload.encode('utf-8'),
            properties=pika.BasicProperties(
                delivery_mode=2,                 # Persistente (sobrevive reinicios)
                content_type='application/json',
                message_id=event.event_id,
            ),
        )

        logger.info(
            "Evento publicado en RabbitMQ",
            routing_key=event.event_type,
            aggregate_id=event.aggregate_id,
        )


class InMemoryEventPublisher(EventPublisher):
    """
    Implementación en memoria para tests.
    Permite verificar qué eventos se publicaron sin necesitar un broker real.
    """

    def __init__(self):
        self.published_events = []

    def publish(self, event: DomainEvent) -> None:
        self.published_events.append(event)
        logger.debug("Evento publicado (in-memory)", event_type=event.event_type)

    def clear(self):
        """Limpia los eventos. Útil en setUp de tests."""
        self.published_events.clear()

    def get_events_by_type(self, event_type: str) -> list:
        """Helper para tests: filtra eventos por tipo."""
        return [e for e in self.published_events if e.event_type == event_type]
