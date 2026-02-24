"""
=============================================================================
MIDDLEWARE DE SEGURIDAD Y LOGGING
=============================================================================

Middlewares personalizados que se ejecutan en cada request/response.

1. RequestLoggingMiddleware: Loguea cada request con métricas de tiempo
2. SecurityHeadersMiddleware: Añade headers de seguridad HTTP
"""
import time
import uuid

import structlog
from django.http import HttpRequest, HttpResponse

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware:
    """
    Middleware para logging estructurado de requests HTTP.
    
    Loguea: método, path, status code, duración, user agent, IP.
    Añade un request_id único para correlacionar logs de una misma request.
    
    El request_id es fundamental en sistemas distribuidos para trazar
    una request a través de múltiples servicios.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Generar un ID único para esta request
        request_id = str(uuid.uuid4())
        request.request_id = request_id

        # Extraer IP real (considerando proxies y load balancers)
        ip_address = self._get_client_ip(request)

        # Contexto que se incluirá en todos los logs de esta request
        # structlog.contextvars permite pasar contexto sin pasarlo explícitamente
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            ip=ip_address,
            method=request.method,
            path=request.path,
        )

        # Log de inicio
        logger.info("request_started")

        # Medir tiempo de procesamiento
        start_time = time.monotonic()

        response = self.get_response(request)

        duration_ms = (time.monotonic() - start_time) * 1000

        # Log de fin con métricas
        log_fn = logger.warning if response.status_code >= 400 else logger.info
        log_fn(
            "request_finished",
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            user_id=str(request.user.id) if request.user.is_authenticated else None,
        )

        # Añadir request_id a la respuesta para debugging del frontend
        response['X-Request-ID'] = request_id

        # Limpiar contexto para el siguiente request (importante en servidores async)
        structlog.contextvars.clear_contextvars()

        return response

    @staticmethod
    def _get_client_ip(request: HttpRequest) -> str:
        """
        Obtiene la IP real del cliente, considerando proxies.
        
        X-Forwarded-For: IP real, IP proxy1, IP proxy2...
        En producción, confiar solo en proxies conocidos (TRUSTED_PROXIES).
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # Primera IP en la cadena es la del cliente real
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')


class RateLimitMiddleware:
    """
    Middleware de rate limiting por IP.
    Complementa el throttling de DRF para proteger endpoints pre-autenticación.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Solo aplicar rate limit a endpoints públicos de autenticación
        if request.path in ['/api/v1/auth/login/', '/api/v1/auth/register/']:
            from src.infrastructure.cache.cache_service import CacheService
            from django.http import JsonResponse

            ip = self._get_ip(request)
            cache = CacheService()
            key = f"rate_limit:auth:{ip}"

            is_allowed, remaining = cache.check_rate_limit(
                key=key,
                max_requests=10,
                window_seconds=60,
            )

            if not is_allowed:
                logger.warning("rate_limit_exceeded", ip=ip, path=request.path)
                return JsonResponse(
                    {'error': 'Demasiados intentos. Espera 1 minuto.'},
                    status=429,
                )

        return self.get_response(request)

    @staticmethod
    def _get_ip(request):
        return request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
