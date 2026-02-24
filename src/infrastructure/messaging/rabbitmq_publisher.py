"""
=============================================================================
ADAPTADOR: RabbitMQ Publisher
=============================================================================

Alternativa a Kafka para mensajería con AMQP (Advanced Message Queuing Protocol).

Cuándo usar RabbitMQ vs Kafka:
- RabbitMQ: mensajes de trabajo, routing complejo, TTL, dead-letter queues
- Kafka: streams de eventos, alto volumen, replay, event sourcing

En este proyecto, RabbitMQ se usa para:
- Tareas de background (emails, notificaciones push)
- Integración con sistemas externos que usan AMQP
- Colas de trabajo con prioridad

Celery usa RabbitMQ como broker por defecto en este proyecto.
"""
import json
import pika
import structlog
from django.conf import settings

logger = structlog.get_logger(__name__)


class RabbitMQPublisher:
    """
    Publisher de mensajes para RabbitMQ.
    Sigue el patrón Producer-Consumer con exchanges y routing keys.
    """

    # Tipos de exchange en RabbitMQ:
    # - direct: routing exacto por clave
    # - topic: routing por patrón (order.*, *.created)
    # - fanout: broadcast a todas las colas
    # - headers: routing por cabeceras

    def __init__(self):
        self._connection = None
        self._channel = None
        self._connect()

    def _connect(self) -> None:
        """Establece conexión con RabbitMQ."""
        try:
            parameters = pika.URLParameters(settings.RABBITMQ_URL)
            parameters.heartbeat = 60          # Mantener conexión viva
            parameters.blocked_connection_timeout = 300

            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()

            # Declarar exchange topic para routing flexible
            self._channel.exchange_declare(
                exchange='domain_events',
                exchange_type='topic',
                durable=True,    # Sobrevive reinicios de RabbitMQ
            )

            # Cola de dead-letter para mensajes fallidos
            self._channel.queue_declare(
                queue='dead_letter_queue',
                durable=True,
                arguments={
                    'x-message-ttl': 86400000,  # 24h en milisegundos
                },
            )

            logger.info("rabbitmq_connected")

        except Exception as e:
            logger.error("rabbitmq_connection_failed", error=str(e))
            raise

    def publish(
        self,
        message: dict,
        routing_key: str,
        priority: int = 0,
    ) -> None:
        """
        Publica un mensaje en RabbitMQ.
        
        Args:
            message: Payload del mensaje
            routing_key: Clave de routing (ej: 'order.created', 'user.*.activated')
            priority: Prioridad del mensaje (0-9)
        """
        try:
            if not self._connection or self._connection.is_closed:
                self._connect()

            body = json.dumps(message, default=str)

            self._channel.basic_publish(
                exchange='domain_events',
                routing_key=routing_key,
                body=body.encode('utf-8'),
                properties=pika.BasicProperties(
                    delivery_mode=2,     # 2 = Persistente (sobrevive restart)
                    content_type='application/json',
                    priority=priority,
                ),
            )

            logger.info("rabbitmq_message_published", routing_key=routing_key)

        except pika.exceptions.AMQPConnectionError:
            logger.warning("rabbitmq_reconnecting")
            self._connect()
            self.publish(message, routing_key, priority)  # Reintentar una vez

        except Exception as e:
            logger.error("rabbitmq_publish_failed", routing_key=routing_key, error=str(e))
            raise

    def close(self) -> None:
        """Cierra la conexión correctamente."""
        if self._connection and not self._connection.is_closed:
            self._connection.close()


class RabbitMQConsumer:
    """
    Consumer de mensajes RabbitMQ.
    Cada cola recibe mensajes según su binding con el exchange.
    """

    def __init__(self, queue_name: str, routing_patterns: list[str]):
        self.queue_name = queue_name
        self.routing_patterns = routing_patterns

    def setup_queue(self, channel) -> None:
        """Declara la cola y sus bindings."""
        channel.queue_declare(
            queue=self.queue_name,
            durable=True,
            arguments={
                # Dead Letter Exchange para mensajes rechazados
                'x-dead-letter-exchange': 'dead_letter',
                'x-dead-letter-routing-key': f'dlq.{self.queue_name}',
            },
        )

        # Bindear la cola al exchange con los patrones de routing
        for pattern in self.routing_patterns:
            channel.queue_bind(
                queue=self.queue_name,
                exchange='domain_events',
                routing_key=pattern,
            )

    def consume(self, handler: callable) -> None:
        """
        Inicia el consumo de mensajes.
        
        Args:
            handler: Función que procesa cada mensaje (message_body: dict) -> bool
                     Retorna True si procesado OK, False para rechazar (NACK)
        """
        connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
        channel = connection.channel()
        self.setup_queue(channel)

        # Prefetch: procesar solo 1 mensaje a la vez (fair dispatch)
        channel.basic_qos(prefetch_count=1)

        def callback(ch, method, properties, body):
            try:
                message = json.loads(body.decode('utf-8'))
                success = handler(message)

                if success:
                    # ACK: mensaje procesado correctamente
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                else:
                    # NACK sin requeue: va al dead-letter
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            except Exception as e:
                logger.error("rabbitmq_message_processing_failed", error=str(e))
                # NACK sin requeue para evitar bucle infinito
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=callback,
        )

        logger.info("rabbitmq_consumer_started", queue=self.queue_name)
        channel.start_consuming()
