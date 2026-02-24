"""
=============================================================================
SERVICIO DE CACHÉ — Redis
=============================================================================

Centraliza el uso de Redis para:
1. Caché de queries costosas (productos, catálogos)
2. Rate limiting por IP/usuario
3. Tokens de un solo uso (reset password, email verification)
4. Sesiones de usuario
5. Contadores en tiempo real (visitas, stock aproximado)

Principio: Cachear lo que es costoso de calcular y frecuentemente leído.
Invalidar de forma correcta es crucial (cache invalidation es uno de los
problemas más difíciles de la informática).
"""
import json
import hashlib
from datetime import timedelta
from typing import Any, Optional, Callable
from functools import wraps

import redis
import structlog
from django.conf import settings

logger = structlog.get_logger(__name__)


class CacheService:
    """
    Wrapper sobre Redis con utilidades comunes.
    Sigue el patrón Repository: abstrae el cliente Redis subyacente.
    """

    def __init__(self):
        self._client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    # =========================================================================
    # Operaciones básicas
    # =========================================================================

    def get(self, key: str) -> Optional[Any]:
        """Obtiene un valor de la caché. Retorna None si no existe."""
        try:
            value = self._client.get(key)
            if value is None:
                return None
            return json.loads(value)
        except Exception as e:
            # La caché nunca debe hacer fallar la aplicación
            logger.warning("cache_get_failed", key=key, error=str(e))
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        """Guarda un valor en caché con TTL (time-to-live)."""
        try:
            serialized = json.dumps(value, default=str)
            self._client.setex(key, ttl_seconds, serialized)
            return True
        except Exception as e:
            logger.warning("cache_set_failed", key=key, error=str(e))
            return False

    def delete(self, key: str) -> bool:
        """Elimina una clave de la caché."""
        try:
            self._client.delete(key)
            return True
        except Exception as e:
            logger.warning("cache_delete_failed", key=key, error=str(e))
            return False

    def delete_pattern(self, pattern: str) -> int:
        """
        Elimina todas las claves que coinciden con un patrón.
        Útil para invalidar grupos de claves (ej: 'products:*').

        CUIDADO: KEYS es O(N) en Redis. En producción usar SCAN.
        """
        try:
            # Usar SCAN en vez de KEYS para no bloquear Redis
            count = 0
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor, match=pattern, count=100)
                if keys:
                    self._client.delete(*keys)
                    count += len(keys)
                if cursor == 0:
                    break
            logger.info("cache_pattern_deleted", pattern=pattern, count=count)
            return count
        except Exception as e:
            logger.warning("cache_delete_pattern_failed", pattern=pattern, error=str(e))
            return 0

    # =========================================================================
    # Rate Limiting — Sliding Window Counter
    # =========================================================================

    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """
        Verifica el rate limit usando el patrón Fixed Window Counter.
        
        Returns:
            (is_allowed, remaining_requests)
        """
        try:
            pipe = self._client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            results = pipe.execute()
            
            current_count = results[0]
            remaining = max(0, max_requests - current_count)
            is_allowed = current_count <= max_requests
            
            return is_allowed, remaining
        except Exception as e:
            logger.warning("rate_limit_check_failed", key=key, error=str(e))
            # En caso de error de Redis, permitir la request (fail open)
            return True, max_requests

    # =========================================================================
    # Tokens de un solo uso
    # =========================================================================

    def store_one_time_token(
        self,
        token_type: str,
        user_id: str,
        ttl_minutes: int = 30,
    ) -> str:
        """
        Genera y almacena un token de un solo uso.
        Usado para: verificación de email, reset de contraseña.
        """
        import secrets
        token = secrets.token_urlsafe(32)
        key = f"one_time_token:{token_type}:{token}"
        self.set(key, {'user_id': user_id, 'type': token_type}, ttl_seconds=ttl_minutes * 60)
        return token

    def consume_one_time_token(self, token_type: str, token: str) -> Optional[str]:
        """
        Verifica y consume un token de un solo uso.
        Returns: user_id si el token es válido, None si no.
        """
        key = f"one_time_token:{token_type}:{token}"
        data = self.get(key)
        if data and data.get('type') == token_type:
            self.delete(key)  # Consumir — un solo uso
            return data.get('user_id')
        return None

    # =========================================================================
    # Contadores en tiempo real
    # =========================================================================

    def increment_counter(self, key: str, amount: int = 1) -> int:
        """Incrementa un contador atómicamente (útil para visitas, métricas)."""
        try:
            return self._client.incrby(key, amount)
        except Exception:
            return 0

    def get_counter(self, key: str) -> int:
        try:
            value = self._client.get(key)
            return int(value) if value else 0
        except Exception:
            return 0


# =============================================================================
# Decorador para cachear el resultado de funciones
# =============================================================================

def cached(ttl_seconds: int = 300, key_prefix: str = ''):
    """
    Decorador para cachear el resultado de una función.
    
    Uso:
        @cached(ttl_seconds=60, key_prefix='product')
        def get_product(product_id: str) -> dict:
            ...  # Operación costosa
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = CacheService()
            
            # Generar clave única basada en la función y sus argumentos
            args_str = json.dumps({'args': str(args), 'kwargs': str(kwargs)}, default=str)
            cache_key = f"{key_prefix}:{func.__name__}:{hashlib.md5(args_str.encode()).hexdigest()}"
            
            # Intentar obtener de caché
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug("cache_hit", key=cache_key)
                return cached_value
            
            # Calcular el valor y guardarlo
            logger.debug("cache_miss", key=cache_key)
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl_seconds=ttl_seconds)
            
            return result
        return wrapper
    return decorator
