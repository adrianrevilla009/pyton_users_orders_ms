"""
============================================================
INFRAESTRUCTURA - OBSERVABILIDAD
============================================================

Tres pilares de la observabilidad:
1. LOGGING: Qué pasó (structlog en JSON)
2. MÉTRICAS: Cuántas veces y cuánto tardó (Prometheus)
3. TRAZAS: Por dónde pasó la petición (OpenTelemetry/Jaeger)

Esta capa no tiene lógica de negocio, solo instrumentación.
============================================================
"""

import time
import uuid
import logging
from typing import Optional

import structlog
from django.http import HttpRequest, HttpResponse
from django.conf import settings
from prometheus_client import Counter, Histogram, Gauge, Summary

logger = structlog.get_logger(__name__)

# ─── Configuración de Structlog ───────────────────────────────
# Structlog convierte los logs en JSON estructurado.
# Ventaja: puedes hacer queries en tu sistema de logs (ELK, Loki)
# Ejemplo query: logs where http_status=500 and user_id="abc"

structlog.configure(
    processors=[
        # Añade timestamp ISO 8601
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        # Añade el correlation ID si está en el contexto
        structlog.contextvars.merge_contextvars,
        # En desarrollo: formato bonito con colores
        # En producción: JSON puro para ELK/Loki
        structlog.processors.JSONRenderer() if not settings.DEBUG
        else structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)


# ─── Métricas Prometheus ──────────────────────────────────────
# Prometheus es un sistema de monitorización pull-based.
# Expone métricas en /metrics, Prometheus las recoge periódicamente.
# Grafana visualiza las métricas de Prometheus.

# Contador de peticiones HTTP
http_requests_total = Counter(
    "http_requests_total",
    "Total de peticiones HTTP recibidas",
    ["method", "endpoint", "status_code"],  # Labels para filtrar
)

# Histograma de latencia (distribución estadística)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Duración de las peticiones HTTP en segundos",
    ["method", "endpoint"],
    # Buckets: distribución de latencias esperadas
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Gauge: número de peticiones activas en este momento
http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Peticiones HTTP siendo procesadas ahora mismo",
    ["method"],
)

# Contador de errores de dominio
domain_errors_total = Counter(
    "domain_errors_total",
    "Total de errores de dominio",
    ["error_code", "entity"],
)

# Contadores de eventos de dominio
domain_events_published_total = Counter(
    "domain_events_published_total",
    "Total de domain events publicados",
    ["event_type"],
)

# Métricas de cache
cache_hits_total = Counter("cache_hits_total", "Cache hits", ["cache_key_prefix"])
cache_misses_total = Counter("cache_misses_total", "Cache misses", ["cache_key_prefix"])

# Métricas de tasks de Celery
celery_tasks_total = Counter(
    "celery_tasks_total",
    "Total de tasks de Celery",
    ["task_name", "state"],
)

celery_task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Duración de tasks de Celery",
    ["task_name"],
)


# ─── Middleware de Logging ────────────────────────────────────

class RequestLoggingMiddleware:
    """
    Middleware que logea todas las peticiones HTTP.
    
    Registra: método, path, status code, duración, user ID, IP.
    Usa structlog para formato JSON estructurado.
    
    IMPORTANTE: Este middleware añade latencia. En producción,
    considera loguear solo errores (4xx, 5xx) o muestrear.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start_time = time.perf_counter()

        # Obtener IP real (considerando proxies)
        client_ip = self._get_client_ip(request)

        # Incrementar gauge de peticiones activas
        http_requests_in_progress.labels(method=request.method).inc()

        response = self.get_response(request)

        # Calcular duración
        duration = time.perf_counter() - start_time
        status_code = response.status_code

        # Decrementar gauge
        http_requests_in_progress.labels(method=request.method).dec()

        # Normalizar el path para métricas (evitar cardinalidad explosiva)
        # /api/v1/users/123456 → /api/v1/users/{id}
        normalized_path = self._normalize_path(request.path)

        # Registrar métricas Prometheus
        http_requests_total.labels(
            method=request.method,
            endpoint=normalized_path,
            status_code=str(status_code),
        ).inc()

        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=normalized_path,
        ).observe(duration)

        # Log estructurado
        log_method = logger.warning if status_code >= 400 else logger.info
        log_method(
            "http_request",
            method=request.method,
            path=request.path,
            status_code=status_code,
            duration_ms=round(duration * 1000, 2),
            client_ip=client_ip,
            user_id=getattr(request.user, "id", None) if hasattr(request, "user") else None,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:200],
            correlation_id=getattr(request, "correlation_id", None),
        )

        return response

    def _get_client_ip(self, request: HttpRequest) -> str:
        """Obtiene la IP real del cliente, considerando proxies y load balancers."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

    def _normalize_path(self, path: str) -> str:
        """
        Normaliza paths de API para evitar cardinalidad explosiva en métricas.
        
        Sin normalización, cada user_id crearía una métrica diferente,
        lo que llenaría la memoria de Prometheus.
        
        /api/v1/users/550e8400-e29b-41d4-a716-446655440000 → /api/v1/users/{id}
        /api/v1/orders/42 → /api/v1/orders/{id}
        """
        import re
        # Reemplazar UUIDs
        path = re.sub(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '{id}',
            path
        )
        # Reemplazar IDs numéricos
        path = re.sub(r'/\d+', '/{id}', path)
        return path


class CorrelationIdMiddleware:
    """
    Añade un Correlation ID único a cada petición.
    
    El Correlation ID permite trazar una petición a través de
    múltiples servicios, logs y tareas asíncronas.
    
    Flujo: Frontend → API → Celery Task → Event → Consumer
    Todos comparten el mismo correlation_id para debug.
    
    Se puede pasar desde el cliente (X-Correlation-ID header)
    o se genera automáticamente si no viene.
    """

    HEADER_NAME = "X-Correlation-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Tomar el correlation ID del header o generar uno nuevo
        correlation_id = (
            request.META.get("HTTP_X_CORRELATION_ID")
            or str(uuid.uuid4())
        )

        # Almacenarlo en el request para uso en views
        request.correlation_id = correlation_id

        # Añadirlo al contexto de structlog (aparece en todos los logs de esta petición)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        response = self.get_response(request)

        # Devolver el correlation ID en la respuesta para que el cliente lo tenga
        response[self.HEADER_NAME] = correlation_id

        return response


# ─── OpenTelemetry Setup ──────────────────────────────────────

def setup_opentelemetry() -> None:
    """
    Configura OpenTelemetry para trazas distribuidas.
    
    OpenTelemetry es el estándar abierto para observabilidad.
    Exporta trazas a Jaeger (visualización) o a cualquier backend compatible.
    
    Las trazas muestran EXACTAMENTE qué llamadas se hacen y cuánto
    tardan: Django → PostgreSQL → Redis → Kafka, etc.
    
    Llamar esta función en apps.py → AppConfig.ready()
    """
    if not settings.OTEL_ENABLED:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter
        from opentelemetry.instrumentation.django import DjangoInstrumentor

        # Configurar el exportador de Jaeger
        jaeger_exporter = JaegerExporter(
            agent_host_name=settings.JAEGER_HOST,
            agent_port=settings.JAEGER_PORT,
        )

        # Crear el provider de trazas
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
        trace.set_tracer_provider(provider)

        # Auto-instrumentar Django
        DjangoInstrumentor().instrument(tracer_provider=provider)

        logger.info(
            "opentelemetry_configured",
            jaeger_host=settings.JAEGER_HOST,
            jaeger_port=settings.JAEGER_PORT,
        )

    except ImportError:
        logger.warning("opentelemetry_not_installed")
    except Exception as e:
        logger.error("opentelemetry_setup_failed", error=str(e))


# ─── Health Check custom para MongoDB ────────────────────────

class MongoDBHealthCheck:
    """
    Health check custom para MongoDB.
    
    Integra con django-health-check para exponer el estado
    en el endpoint /health/.
    """

    def check_status(self) -> dict:
        try:
            from infrastructure.database.mongo_repository import MongoDBClient
            healthy = MongoDBClient().health_check()
            return {
                "status": "ok" if healthy else "error",
                "backend": "MongoDB",
            }
        except Exception as e:
            return {"status": "error", "backend": "MongoDB", "error": str(e)}
