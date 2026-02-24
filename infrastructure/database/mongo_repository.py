"""
============================================================
INFRAESTRUCTURA - REPOSITORIO MONGODB (NoSQL)
============================================================

MongoDB se usa para datos no estructurados o semi-estructurados:
- Logs de auditoría (registros inmutables de acciones)
- Configuraciones dinámicas (JSON flexible)
- Historial de eventos de dominio (Event Store)
- Datos de analítica (documentos variables)

Usamos pymongo directamente (sin ODM) para máximo control.
En proyectos donde el schema es más fijo, se puede usar MongoEngine.

¿Por qué MongoDB para audit logs y no PostgreSQL?
- Los logs de auditoría son append-only (nunca se modifican)
- El payload puede variar entre eventos (schema flexible)
- Necesitamos escrituras rápidas sin impactar la BD principal
- Fácil de escalar horizontalmente (sharding)
============================================================
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import structlog
from pymongo import MongoClient, DESCENDING
from pymongo.collection import Collection

from django.conf import settings

logger = structlog.get_logger(__name__)


class MongoDBClient:
    """
    Cliente singleton para MongoDB.
    
    Usamos el patrón singleton para reutilizar la conexión
    en toda la aplicación. pymongo gestiona el connection pool internamente.
    """
    _instance: Optional["MongoDBClient"] = None
    _client: Optional[MongoClient] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_client(self) -> MongoClient:
        if self._client is None:
            self._client = MongoClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=5000,  # Timeout de conexión: 5 segundos
                connectTimeoutMS=5000,
                maxPoolSize=50,           # Pool máximo de conexiones
                minPoolSize=5,            # Pool mínimo (conexiones precreadas)
                retryWrites=True,         # Reintentos automáticos en escritura
            )
            logger.info("mongodb_connected", uri=settings.MONGODB_URI.split("@")[-1])
        return self._client

    def get_database(self):
        return self.get_client()[settings.MONGODB_DB_NAME]

    def health_check(self) -> bool:
        """Verifica que MongoDB está disponible."""
        try:
            self.get_client().admin.command("ping")
            return True
        except Exception as e:
            logger.error("mongodb_health_check_failed", error=str(e))
            return False


# ─── Audit Log Repository ─────────────────────────────────────

class AuditLogDocument:
    """
    Estructura de un documento de log de auditoría.
    
    En MongoDB no hay schema fijo, pero definimos la estructura
    esperada aquí como documentación viva.
    """
    COLLECTION = "audit_logs"

    @staticmethod
    def create(
        event_type: str,
        user_id: Optional[str],
        entity_type: str,
        entity_id: str,
        action: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """Crea un documento de audit log."""
        return {
            "_id": str(uuid.uuid4()),
            "event_type": event_type,
            "user_id": user_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "payload": payload,
            "metadata": metadata or {},
            "created_at": datetime.utcnow(),
            # TTL: los logs se eliminan automáticamente después de 90 días
            # (requiere TTL index en MongoDB: db.audit_logs.createIndex({created_at:1},{expireAfterSeconds:7776000}))
        }


class AuditLogRepository:
    """
    Repositorio para logs de auditoría en MongoDB.
    
    Los audit logs son inmutables: solo se escriben, nunca se modifican.
    Registran quién hizo qué, cuándo y con qué datos.
    """

    def __init__(self):
        self._db = MongoDBClient().get_database()

    @property
    def collection(self) -> Collection:
        return self._db[AuditLogDocument.COLLECTION]

    def log(
        self,
        event_type: str,
        user_id: Optional[str],
        entity_type: str,
        entity_id: str,
        action: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Registra una acción de auditoría.
        
        Devuelve el ID del documento creado.
        """
        doc = AuditLogDocument.create(
            event_type=event_type,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            payload=payload,
            metadata=metadata,
        )
        result = self.collection.insert_one(doc)
        logger.debug(
            "audit_log_created",
            audit_id=str(result.inserted_id),
            event_type=event_type,
            entity_id=entity_id,
        )
        return str(result.inserted_id)

    def find_by_entity(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 50,
    ) -> List[Dict]:
        """Obtiene el historial de auditoría de una entidad."""
        cursor = (
            self.collection
            .find(
                {"entity_type": entity_type, "entity_id": entity_id},
                {"_id": 0}  # Excluir el _id de MongoDB de la respuesta
            )
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        return list(cursor)

    def find_by_user(self, user_id: str, limit: int = 100) -> List[Dict]:
        """Obtiene todas las acciones de un usuario."""
        cursor = (
            self.collection
            .find({"user_id": user_id}, {"_id": 0})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        return list(cursor)

    def setup_indexes(self) -> None:
        """
        Crea los índices necesarios en MongoDB.
        
        Llamar este método al iniciar la aplicación (en AppConfig.ready()).
        Los índices son cruciales para el rendimiento de queries.
        """
        # Índice compuesto para búsquedas por entidad
        self.collection.create_index([
            ("entity_type", 1),
            ("entity_id", 1),
            ("created_at", DESCENDING),
        ], name="entity_history_idx")

        # Índice para búsquedas por usuario
        self.collection.create_index([
            ("user_id", 1),
            ("created_at", DESCENDING),
        ], name="user_actions_idx")

        # TTL Index: elimina documentos automáticamente después de 90 días
        self.collection.create_index(
            [("created_at", 1)],
            expireAfterSeconds=90 * 24 * 3600,  # 90 días
            name="ttl_idx",
        )

        logger.info("mongodb_indexes_created", collection=AuditLogDocument.COLLECTION)


# ─── Event Store (para Event Sourcing opcional) ───────────────

class EventStoreRepository:
    """
    Event Store en MongoDB.
    
    Almacena todos los domain events en orden cronológico.
    Permite reconstruir el estado de cualquier entidad
    reproduciéndolos (Event Sourcing).
    
    Esto es avanzado y opcional, pero muy potente para auditoría,
    debugging y análisis de comportamiento del sistema.
    """
    COLLECTION = "domain_events"

    def __init__(self):
        self._db = MongoDBClient().get_database()

    @property
    def collection(self) -> Collection:
        return self._db[self.COLLECTION]

    def append(self, event) -> None:
        """Añade un domain event al event store."""
        doc = {
            "_id": str(event.event_id),
            "event_type": event.event_type,
            "event_version": event.event_version,
            "occurred_at": event.occurred_at,
            "payload": {
                k: str(v) for k, v in event.__dict__.items()
                if k not in ("event_id", "occurred_at", "event_version")
            },
        }
        try:
            self.collection.insert_one(doc)
        except Exception as e:
            # El event store no debe romper el flujo principal
            logger.error("event_store_append_failed", error=str(e), event_type=event.event_type)

    def get_events_by_aggregate(self, aggregate_id: str) -> List[Dict]:
        """Obtiene todos los eventos de un agregado en orden cronológico."""
        return list(
            self.collection
            .find({"payload.aggregate_id": aggregate_id})
            .sort("occurred_at", 1)
        )
