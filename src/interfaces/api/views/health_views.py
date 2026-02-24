"""
=============================================================================
HEALTH CHECKS — Estado del sistema
=============================================================================

Los health checks son fundamentales en producción para:
- Kubernetes: liveness y readiness probes
- Load balancers: solo enviar tráfico a instancias sanas
- Monitorización: alertas cuando un servicio falla
- On-call: diagnóstico rápido de problemas

Distinción importante:
- /health/live: ¿Está el proceso vivo? (reiniciar si falla)
- /health/ready: ¿Puede servir tráfico? (sacar del LB si falla)
- /health/: Estado completo para diagnóstico
"""
import time
from typing import Any

import redis
from django.db import connection
from django.http import JsonResponse
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

import structlog

logger = structlog.get_logger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def liveness(request):
    """
    Liveness probe — ¿Está el proceso vivo?
    
    Solo falla si el proceso en sí está en un estado irrecuperable.
    Kubernetes reiniciará el pod si esto falla.
    Debe ser MUY rápido (< 50ms).
    """
    return JsonResponse({'status': 'alive'})


@api_view(['GET'])
@permission_classes([AllowAny])
def readiness(request):
    """
    Readiness probe — ¿Puede servir tráfico?
    
    Verifica las dependencias críticas (BD principal).
    El LB no envía tráfico si esto falla.
    """
    checks = {}

    # Verificar PostgreSQL (crítico)
    try:
        connection.ensure_connection()
        checks['postgresql'] = 'ok'
    except Exception as e:
        checks['postgresql'] = f'failed: {str(e)}'
        return JsonResponse({'status': 'not_ready', 'checks': checks}, status=503)

    return JsonResponse({'status': 'ready', 'checks': checks})


@api_view(['GET'])
@permission_classes([AllowAny])
def health_detail(request):
    """
    Health check detallado — Estado completo de todas las dependencias.
    Usado por sistemas de monitorización (Grafana, Datadog, etc.).
    """
    start_time = time.time()
    checks = {}
    overall_status = 'healthy'

    # ----- PostgreSQL -----
    checks['postgresql'] = _check_postgresql()

    # ----- Redis -----
    checks['redis'] = _check_redis()

    # ----- MongoDB -----
    checks['mongodb'] = _check_mongodb()

    # ----- Kafka -----
    checks['kafka'] = _check_kafka()

    # Determinar estado global
    failed = [name for name, result in checks.items() if result['status'] != 'ok']
    if failed:
        overall_status = 'degraded' if len(failed) < len(checks) else 'unhealthy'

    duration_ms = round((time.time() - start_time) * 1000, 2)

    response_data = {
        'status': overall_status,
        'checks': checks,
        'duration_ms': duration_ms,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }

    http_status = 200 if overall_status == 'healthy' else 503
    return JsonResponse(response_data, status=http_status)


def _check_postgresql() -> dict:
    """Verifica la conexión a PostgreSQL."""
    try:
        start = time.time()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        latency = round((time.time() - start) * 1000, 2)
        return {'status': 'ok', 'latency_ms': latency}
    except Exception as e:
        return {'status': 'failed', 'error': str(e)}


def _check_redis() -> dict:
    """Verifica la conexión a Redis."""
    try:
        start = time.time()
        client = redis.from_url(settings.REDIS_URL)
        client.ping()
        latency = round((time.time() - start) * 1000, 2)
        # Info adicional útil para diagnóstico
        info = client.info('server')
        return {
            'status': 'ok',
            'latency_ms': latency,
            'version': info.get('redis_version'),
            'connected_clients': info.get('connected_clients'),
        }
    except Exception as e:
        return {'status': 'failed', 'error': str(e)}


def _check_mongodb() -> dict:
    """Verifica la conexión a MongoDB."""
    try:
        from pymongo import MongoClient
        start = time.time()
        client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        latency = round((time.time() - start) * 1000, 2)
        return {'status': 'ok', 'latency_ms': latency}
    except Exception as e:
        return {'status': 'failed', 'error': str(e)}


def _check_kafka() -> dict:
    """Verifica la conectividad con Kafka."""
    try:
        from confluent_kafka.admin import AdminClient
        start = time.time()
        admin = AdminClient({'bootstrap.servers': settings.KAFKA_CONFIG['bootstrap.servers']})
        metadata = admin.list_topics(timeout=3)
        latency = round((time.time() - start) * 1000, 2)
        return {
            'status': 'ok',
            'latency_ms': latency,
            'brokers': len(metadata.brokers),
        }
    except Exception as e:
        return {'status': 'failed', 'error': str(e)}
