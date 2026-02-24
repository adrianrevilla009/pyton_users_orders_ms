"""
============================================================
KAFKA CONSUMER - Consumidor de eventos
============================================================
Consume eventos de Kafka y los despacha a handlers.
Se ejecuta como proceso independiente (worker).

Para iniciar el consumer:
  python manage.py run_kafka_consumer

Patrón: Event Handler Registry - cada tipo de evento
tiene un handler registrado que lo procesa.
============================================================
"""

import json
import structlog
from typing import Callable, Dict
from shared.domain.base_entity import DomainEvent

logger = structlog.get_logger(__name__)

# Registro de handlers: event_type -> función handler
EventHandlerType = Callable[[dict], None]


class KafkaConsumer:
    """
    Consumer de eventos Kafka.
    
    Características:
    - Auto-commit deshabilitado (commit manual tras procesar)
    - At-least-once delivery (puede recibir duplicados)
    - Idempotency se garantiza en los handlers
    """

    def __init__(self, topics: list, group_id: str):
        self._topics = topics
        self._group_id = group_id
        self._handlers: Dict[str, EventHandlerType] = {}
        self._consumer = None

    def register_handler(self, event_type: str, handler: EventHandlerType) -> None:
        """Registra un handler para un tipo de evento."""
        self._handlers[event_type] = handler
        logger.info("Handler registrado", event_type=event_type)

    def start(self) -> None:
        """Inicia el loop de consumo. Bloqueante."""
        try:
            from confluent_kafka import Consumer, KafkaException
            from django.conf import settings

            self._consumer = Consumer({
                'bootstrap.servers': settings.KAFKA_CONFIG['bootstrap_servers'],
                'group.id': self._group_id,
                'auto.offset.reset': 'earliest',
                'enable.auto.commit': False,        # Commit manual
                'max.poll.interval.ms': 300000,     # 5 minutos máximo por mensaje
            })

            self._consumer.subscribe(self._topics)
            logger.info("Kafka consumer iniciado", topics=self._topics, group_id=self._group_id)

            while True:
                msg = self._consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    logger.error("Error en Kafka consumer", error=str(msg.error()))
                    continue

                self._process_message(msg)

                # Commit DESPUÉS de procesar (at-least-once)
                self._consumer.commit(asynchronous=False)

        except KeyboardInterrupt:
            logger.info("Kafka consumer detenido por el usuario")
        except Exception as e:
            logger.error("Error fatal en Kafka consumer", error=str(e))
            raise
        finally:
            if self._consumer:
                self._consumer.close()

    def _process_message(self, msg) -> None:
        """Procesa un mensaje individual."""
        try:
            data = json.loads(msg.value().decode('utf-8'))
            event_type = data.get('event_type', 'unknown')

            logger.info(
                "Procesando evento",
                event_type=event_type,
                aggregate_id=data.get('aggregate_id'),
                partition=msg.partition(),
                offset=msg.offset(),
            )

            handler = self._handlers.get(event_type)
            if handler:
                handler(data)
            else:
                logger.warning("Sin handler para evento", event_type=event_type)

        except json.JSONDecodeError as e:
            logger.error("Mensaje Kafka inválido (no es JSON)", error=str(e))
        except Exception as e:
            logger.error("Error procesando mensaje Kafka", error=str(e), exc_info=True)
            # En producción: mover a Dead Letter Queue
