"""
============================================================
REQUEST LOGGING MIDDLEWARE
============================================================
Middleware que añade logging estructurado a cada request.
Genera un request_id único por request para trazabilidad.
Ideal para correlacionar logs en sistemas distribuidos.
============================================================
"""

import uuid
import time
import structlog
from django.utils.deprecation import MiddlewareMixin

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Añade a cada request:
    - request_id: UUID único para correlación
    - Logging de inicio y fin con duración
    - Contexto de usuario si está autenticado
    """

    def process_request(self, request):
        """Se ejecuta al inicio del request."""
        # Generar o usar el request ID del header (para tracing distribuido)
        request_id = request.META.get('HTTP_X_REQUEST_ID') or str(uuid.uuid4())
        request.request_id = request_id
        request._start_time = time.time()

        # Añadir el request_id al contexto de structlog
        # Todos los logs posteriores en este request incluirán este ID
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.path,
        )

        logger.info(
            "Request iniciado",
            client_ip=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

    def process_response(self, request, response):
        """Se ejecuta al final del request."""
        duration_ms = None
        if hasattr(request, '_start_time'):
            duration_ms = round((time.time() - request._start_time) * 1000, 2)

        user_id = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_id = str(request.user.id)

        log_level = 'info' if response.status_code < 400 else 'warning' if response.status_code < 500 else 'error'
        log_fn = getattr(logger, log_level)

        log_fn(
            "Request completado",
            status_code=response.status_code,
            duration_ms=duration_ms,
            user_id=user_id,
        )

        # Añadir el request_id al header de respuesta para el cliente
        if hasattr(request, 'request_id'):
            response['X-Request-ID'] = request.request_id

        return response

    def _get_client_ip(self, request) -> str:
        """Obtiene la IP real del cliente (considera proxies)."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')
