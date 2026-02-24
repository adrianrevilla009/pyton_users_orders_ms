"""
============================================================
MONGODB - Registro de actividad (NoSQL)
============================================================
Usamos MongoDB para datos no estructurados o semi-estructurados:
- Logs de actividad del usuario (esquema flexible)
- Eventos de auditoría
- Métricas históricas
- Documentos con estructura variable

MongoDB es ideal cuando:
- El esquema cambia frecuentemente
- Los datos no son relacionales
- Necesitas búsquedas de texto completo
- Alta velocidad de escritura

Usamos mongoengine como ODM (Object Document Mapper).
============================================================
"""

from mongoengine import Document, StringField, DateTimeField, DictField, connect
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger(__name__)


def connect_mongodb():
    """Conecta a MongoDB usando la configuración de Django."""
    from django.conf import settings
    config = settings.MONGODB_CONFIG
    connect(
        db=config['db'],
        host=config['host'],
        port=config['port'],
    )


class ActivityLog(Document):
    """
    Documento MongoDB para registrar actividad de usuarios.
    
    Ventaja sobre SQL: el campo 'metadata' puede tener
    estructura diferente en cada documento sin alterar el esquema.
    """
    user_id = StringField(required=True, max_length=100)
    action = StringField(required=True, max_length=100)
    resource_type = StringField(max_length=100)
    resource_id = StringField(max_length=100)
    ip_address = StringField(max_length=45)
    user_agent = StringField()
    # DictField acepta cualquier estructura JSON
    metadata = DictField(default=dict)
    occurred_at = DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        'collection': 'activity_logs',
        'indexes': [
            'user_id',
            'action',
            '-occurred_at',              # Índice descendente para queries recientes
            ('user_id', '-occurred_at'), # Índice compuesto
        ],
        'ordering': ['-occurred_at'],
    }

    @classmethod
    def log(cls, user_id: str, action: str, **kwargs) -> 'ActivityLog':
        """Factory method para crear un log fácilmente."""
        entry = cls(user_id=user_id, action=action, **kwargs)
        entry.save()
        logger.debug("Actividad registrada en MongoDB", user_id=user_id, action=action)
        return entry

    @classmethod
    def get_user_activity(cls, user_id: str, limit: int = 50) -> list:
        """Obtiene la actividad reciente de un usuario."""
        return list(cls.objects(user_id=user_id).limit(limit))


class SystemMetric(Document):
    """
    Documento MongoDB para métricas del sistema.
    Complementa a Prometheus con métricas de negocio personalizadas.
    """
    metric_name = StringField(required=True)
    value = DictField()
    tags = DictField(default=dict)
    recorded_at = DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        'collection': 'system_metrics',
        'indexes': [
            'metric_name',
            '-recorded_at',
            ('metric_name', '-recorded_at'),
        ],
    }
