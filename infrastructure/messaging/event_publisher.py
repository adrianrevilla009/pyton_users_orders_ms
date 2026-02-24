"""
============================================================
INFRAESTRUCTURA - MESSAGE BROKERS
============================================================

Implementaciones concretas para publicar domain events.
Soportamos tanto Kafka como RabbitMQ (configurable).

¿Cuándo usar Kafka vs RabbitMQ?

KAFKA:
- Event streaming / log distribuido
- Alto volumen (millones de mensajes/segundo)
- Retención de mensajes (puedes releer el pasado)
- Procesamiento en orden garantizado por partición
- Ideal para: event sourcing, analytics, auditoría, pipelines

RABBITMQ:
- Message broker tradicional (mensajería punto-a-punto)
- Más simple de operar
- Routing flexible (topics, fanout, direct, headers)
- Ideal para: tareas de trabajo, notificaciones, RPC
- Mensajes se eliminan tras consumirse (por defecto)

En este proyecto: Kafka para domain events, RabbitMQ para Celery tasks.
============================================================
"""

import json
import uuid
from dataclasses import asdict
from typing import Optional, Dict, Any
from datetime import datetime

import structlog
from django.conf import settings

from application.users.use_cases import EventPublisher
from domain.base import DomainEvent

logger = structlog.get_logger(__name__)


# ─── Serializador de Domain Events ───────────────────────────

def serialize_event(event: DomainEvent) -> Dict[str, Any]:
    """
    Serializa un domain event a un diccionario JSON-serializable.
    
    Convierte tipos especiales (UUID, datetime) a strings.
    """
    data = {}
    for key, value in event.__dict__.items():
        if isinstance(value, uuid.UUID):
            data[key] = str(value)
        elif isinstance(value, datetime):
            data[key] = value.isoformat()
        elif hasattr(value, '__dict__'):
            data[key] = str(value)
        else:
            data[key] = value

    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "event_version": event.event_version,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": data,
    }


# ─── Kafka Event Publisher ────────────────────────────────────

class KafkaEventPublisher(EventPublisher):
    """
    Publica domain events en Apache Kafka.
    
    Cada tipo de evento se publica en su propio topic.
    Convención de naming: {service}.{entity}.{event_type}
    Ejemplo: "techlead.users.UserRegistered"
    
    CONFIGURACIÓN DE KAFKA EN PRODUCCIÓN:
    - Usar múltiples réplicas (replication factor >= 3)
    - Habilitar acknowledgments (acks='all') para durabilidad
    - Configurar retries y linger_ms para batching
    - Monitorear consumer lag con herramientas como Kafka Lag Exporter
    """

    def __init__(self):
        self._producer = None
        self._enabled = bool(getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", None))

    def _get_producer(self):
        """Lazy initialization del producer (se conecta cuando se necesita)."""
        if self._producer is None and self._enabled:
            try:
                from kafka import KafkaProducer
                self._producer = KafkaProducer(
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                    # Serialización: JSON + encoding UTF-8
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                    # Durabilidad: espera confirmación de todos los réplicas
                    acks="all",
                    # Reintentos automáticos en caso de fallo transitorio
                    retries=3,
                    retry_backoff_ms=1000,
                    # Batching para mejor rendimiento
                    linger_ms=10,           # Espera 10ms para batching
                    batch_size=16384,        # Batch de 16KB
                    # Compresión para reducir ancho de banda
                    compression_type="gzip",
                    # Timeout de petición
                    request_timeout_ms=30000,
                )
                logger.info("kafka_producer_initialized")
            except Exception as e:
                logger.error("kafka_producer_init_failed", error=str(e))
                self._enabled = False

        return self._producer

    def publish(self, event: DomainEvent) -> None:
        """
        Publica un domain event en Kafka.
        
        El topic se deriva del tipo de evento.
        La key es el ID del agregado (garantiza orden por entidad).
        """
        if not self._enabled:
            # Si Kafka no está disponible, logueamos pero no fallamos
            logger.warning("kafka_not_available", event_type=event.event_type)
            return

        producer = self._get_producer()
        if not producer:
            return

        try:
            topic = f"techlead.{event.event_type.lower()}"
            payload = serialize_event(event)

            # La key garantiza que eventos del mismo agregado van a la misma partición
            # (preserva el orden de eventos por entidad)
            key = str(getattr(event, "user_id", None) or
                      getattr(event, "order_id", None) or
                      str(event.event_id))

            future = producer.send(topic, value=payload, key=key)
            # flush() asegura que el mensaje se envió antes de continuar
            # En producción con alto volumen, puedes omitir el flush y enviarlo async
            metadata = future.get(timeout=10)

            logger.info(
                "kafka_event_published",
                event_type=event.event_type,
                topic=metadata.topic,
                partition=metadata.partition,
                offset=metadata.offset,
            )

        except Exception as e:
            logger.error(
                "kafka_publish_failed",
                event_type=event.event_type,
                error=str(e),
            )
            # No propagamos la excepción: los domain events no deben romper el flujo principal
            # En producción, considera una Dead Letter Queue o reintentos con backoff

    def close(self) -> None:
        """Cierra el producer limpiamente."""
        if self._producer:
            self._producer.flush()
            self._producer.close()
            logger.info("kafka_producer_closed")


# ─── RabbitMQ Event Publisher ─────────────────────────────────

class RabbitMQEventPublisher(EventPublisher):
    """
    Publica domain events en RabbitMQ.
    
    Usamos un exchange de tipo 'topic' para routing flexible.
    El routing key sigue el patrón: {entity}.{event_type}
    
    Los consumidores pueden suscribirse a patrones:
    - "users.*" = todos los eventos de usuarios
    - "*.UserRegistered" = todos los registros (de cualquier entidad)
    - "#" = todos los eventos
    """

    EXCHANGE = "techlead.domain_events"  # Exchange principal

    def __init__(self):
        self._connection = None
        self._channel = None
        self._broker_url = getattr(settings, "CELERY_BROKER_URL", "")
        self._enabled = "amqp" in self._broker_url

    def _get_channel(self):
        """Establece conexión con RabbitMQ."""
        if self._channel is None and self._enabled:
            try:
                import pika
                parameters = pika.URLParameters(self._broker_url)
                self._connection = pika.BlockingConnection(parameters)
                self._channel = self._connection.channel()

                # Declarar el exchange (idempotente: no falla si ya existe)
                self._channel.exchange_declare(
                    exchange=self.EXCHANGE,
                    exchange_type="topic",   # Routing flexible por patrones
                    durable=True,            # Sobrevive reinicios de RabbitMQ
                )
                logger.info("rabbitmq_channel_initialized")
            except Exception as e:
                logger.error("rabbitmq_channel_init_failed", error=str(e))
                self._enabled = False

        return self._channel

    def publish(self, event: DomainEvent) -> None:
        """Publica un domain event en RabbitMQ."""
        if not self._enabled:
            logger.warning("rabbitmq_not_available", event_type=event.event_type)
            return

        channel = self._get_channel()
        if not channel:
            return

        try:
            import pika
            payload = serialize_event(event)

            # Routing key: "users.UserRegistered" o "orders.OrderPlaced"
            # Derivamos la entidad del tipo de evento (convención de naming)
            entity = self._infer_entity(event)
            routing_key = f"{entity}.{event.event_type}"

            channel.basic_publish(
                exchange=self.EXCHANGE,
                routing_key=routing_key,
                body=json.dumps(payload).encode("utf-8"),
                properties=pika.BasicProperties(
                    delivery_mode=2,         # Persistente: sobrevive reinicios
                    content_type="application/json",
                    message_id=str(event.event_id),
                    timestamp=int(event.occurred_at.timestamp()),
                    headers={
                        "event_type": event.event_type,
                        "event_version": str(event.event_version),
                    },
                ),
            )

            logger.info(
                "rabbitmq_event_published",
                event_type=event.event_type,
                routing_key=routing_key,
            )

        except Exception as e:
            logger.error("rabbitmq_publish_failed", event_type=event.event_type, error=str(e))
            # Intentar reconectar en el siguiente publish
            self._channel = None
            self._connection = None

    def _infer_entity(self, event: DomainEvent) -> str:
        """Infiere la entidad del tipo de evento."""
        event_name = event.event_type.lower()
        if "user" in event_name:
            return "users"
        elif "order" in event_name:
            return "orders"
        elif "payment" in event_name:
            return "payments"
        return "general"


# ─── Composite Publisher (publica en múltiples brokers) ──────

class CompositeEventPublisher(EventPublisher):
    """
    Publica en múltiples brokers simultáneamente.
    
    Útil en migraciones (de RabbitMQ a Kafka, por ejemplo)
    o cuando distintos consumidores usan distintos brokers.
    """

    def __init__(self, publishers: list):
        self.publishers = publishers

    def publish(self, event: DomainEvent) -> None:
        for publisher in self.publishers:
            try:
                publisher.publish(event)
            except Exception as e:
                logger.error(
                    "composite_publisher_error",
                    publisher=publisher.__class__.__name__,
                    error=str(e),
                )


# ─── Log Event Publisher (para tests y desarrollo) ────────────

class LogEventPublisher(EventPublisher):
    """
    Publisher que simplemente logea los eventos.
    
    Útil en desarrollo y tests cuando no hay broker disponible.
    """

    def publish(self, event: DomainEvent) -> None:
        logger.info(
            "domain_event_simulated",
            event_type=event.event_type,
            event_id=str(event.event_id),
            payload=serialize_event(event),
        )


# ─── Factory: crear el publisher apropiado ───────────────────

def create_event_publisher() -> EventPublisher:
    """
    Factory que decide qué publisher usar según la configuración.
    
    Centraliza la decisión en un solo lugar.
    """
    from django.conf import settings

    kafka_enabled = bool(getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", None))
    rabbitmq_enabled = "amqp" in getattr(settings, "CELERY_BROKER_URL", "")

    publishers = []

    if kafka_enabled:
        publishers.append(KafkaEventPublisher())
        logger.info("event_publisher_kafka_enabled")

    if rabbitmq_enabled:
        publishers.append(RabbitMQEventPublisher())
        logger.info("event_publisher_rabbitmq_enabled")

    if not publishers:
        logger.warning("event_publisher_fallback_to_log")
        return LogEventPublisher()

    if len(publishers) == 1:
        return publishers[0]

    return CompositeEventPublisher(publishers)
