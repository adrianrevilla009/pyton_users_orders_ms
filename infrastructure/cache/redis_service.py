"""
============================================================
INFRAESTRUCTURA - SERVICIO DE CACHÉ (Redis)
============================================================

Redis se usa para múltiples propósitos:
1. Caché de respuestas HTTP (reducir carga en BD)
2. Rate limiting (throttling personalizado)
3. Sesiones de usuario
4. Datos temporales (tokens de verificación, OTPs)
5. Locks distribuidos (evitar race conditions)
6. Cola de mensajes (con Celery)

Patrón usado: Cache-Aside (Lazy Loading)
- Primero buscamos en cache
- Si no existe, buscamos en BD y guardamos en cache
- La BD es siempre la fuente de verdad
============================================================
"""

import json
import uuid
import functools
import hashlib
from typing import Optional, Any, Callable, TypeVar
from datetime import timedelta

import structlog
from django.core.cache import cache
from django.conf import settings

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable)


class CacheService:
    """
    Servicio de caché con Redis.
    
    Proporciona una interfaz de alto nivel sobre django-redis,
    con logging, métricas y patrones útiles.
    """

    # TTLs predefinidos para distintos tipos de datos
    TTL_SHORT = 60              # 1 minuto (datos muy volátiles)
    TTL_MEDIUM = 300            # 5 minutos (datos normales)
    TTL_LONG = 3600             # 1 hora (datos poco cambiantes)
    TTL_VERY_LONG = 86400       # 1 día (datos casi estáticos)
    TTL_WEEK = 604800           # 1 semana

    def get(self, key: str) -> Optional[Any]:
        """Obtiene un valor del cache."""
        try:
            value = cache.get(key)
            if value is not None:
                logger.debug("cache_hit", key=key)
            else:
                logger.debug("cache_miss", key=key)
            return value
        except Exception as e:
            logger.error("cache_get_error", key=key, error=str(e))
            return None  # Fail gracefully: si el cache falla, seguimos sin él

    def set(self, key: str, value: Any, ttl: int = TTL_MEDIUM) -> bool:
        """Almacena un valor en cache con TTL."""
        try:
            cache.set(key, value, timeout=ttl)
            logger.debug("cache_set", key=key, ttl=ttl)
            return True
        except Exception as e:
            logger.error("cache_set_error", key=key, error=str(e))
            return False

    def delete(self, key: str) -> bool:
        """Elimina una entrada del cache."""
        try:
            cache.delete(key)
            logger.debug("cache_deleted", key=key)
            return True
        except Exception as e:
            logger.error("cache_delete_error", key=key, error=str(e))
            return False

    def delete_pattern(self, pattern: str) -> int:
        """
        Elimina todas las entradas que coinciden con un patrón.
        
        Ejemplo: delete_pattern("user:*") elimina todos los datos de usuarios.
        
        ADVERTENCIA: Esta operación puede ser costosa en Redis con muchas keys.
        Usar con moderación en producción.
        """
        try:
            from django_redis import get_redis_connection
            redis_conn = get_redis_connection("default")
            # El prefijo de django-redis se añade automáticamente
            full_pattern = f":1:{settings.CACHES['default'].get('KEY_PREFIX', '')}*{pattern}"
            keys = redis_conn.keys(full_pattern)
            if keys:
                redis_conn.delete(*keys)
            logger.info("cache_pattern_deleted", pattern=pattern, count=len(keys))
            return len(keys)
        except Exception as e:
            logger.error("cache_delete_pattern_error", pattern=pattern, error=str(e))
            return 0

    def get_or_set(self, key: str, factory: Callable, ttl: int = TTL_MEDIUM) -> Any:
        """
        Patrón Cache-Aside: obtiene del cache o llama a factory.
        
        Ejemplo:
            user = cache_service.get_or_set(
                f"user:{user_id}",
                lambda: user_repository.get_by_id(user_id),
                ttl=300
            )
        """
        value = self.get(key)
        if value is None:
            value = factory()
            if value is not None:
                self.set(key, value, ttl)
        return value

    def invalidate_user_cache(self, user_id: str) -> None:
        """Invalida todas las entradas de cache relacionadas con un usuario."""
        keys_to_delete = [
            f"user:{user_id}",
            f"user:{user_id}:profile",
            f"user:{user_id}:orders",
            f"user:{user_id}:permissions",
        ]
        for key in keys_to_delete:
            self.delete(key)


class RateLimiter:
    """
    Rate limiter usando Redis.
    
    Implementa el algoritmo Sliding Window Counter.
    
    Más preciso que el algoritmo Fixed Window (que puede permitir
    el doble de requests en el límite de ventana).
    
    Ejemplo de uso:
        limiter = RateLimiter()
        if not limiter.check_rate_limit(f"login:{ip}", limit=5, window=60):
            raise TooManyRequestsError()
    """

    def check_rate_limit(
        self,
        key: str,
        limit: int,
        window: int,  # segundos
    ) -> bool:
        """
        Verifica si se ha superado el rate limit.
        
        Devuelve True si la petición puede pasar, False si debe bloquearse.
        """
        try:
            from django_redis import get_redis_connection
            redis_conn = get_redis_connection("default")

            pipe = redis_conn.pipeline()
            now = self._get_timestamp()
            window_start = now - window

            # Sliding window: eliminamos entradas antiguas y añadimos la nueva
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(uuid.uuid4()): now})
            pipe.zcard(key)
            pipe.expire(key, window)

            results = pipe.execute()
            count = results[2]

            allowed = count <= limit
            if not allowed:
                logger.warning("rate_limit_exceeded", key=key, count=count, limit=limit)

            return allowed

        except Exception as e:
            logger.error("rate_limiter_error", key=key, error=str(e))
            return True  # Fail open: si el rate limiter falla, dejamos pasar

    def _get_timestamp(self) -> float:
        import time
        return time.time()

    def get_remaining(self, key: str, limit: int, window: int) -> int:
        """Cuántas peticiones quedan disponibles."""
        try:
            from django_redis import get_redis_connection
            redis_conn = get_redis_connection("default")

            now = self._get_timestamp()
            window_start = now - window
            count = redis_conn.zcount(key, window_start, now)
            return max(0, limit - count)
        except Exception:
            return limit


class DistributedLock:
    """
    Lock distribuido usando Redis.
    
    Evita race conditions en entornos con múltiples workers/servidores.
    
    Ejemplo: evitar que dos workers procesen el mismo pedido simultáneamente.
    
    Implementa el algoritmo RedLock (simplificado para un solo nodo Redis).
    Para producción crítica, usar Redlock con múltiples nodos Redis.
    """

    def __init__(self, key: str, timeout: int = 30):
        self.key = f"lock:{key}"
        self.timeout = timeout
        self._lock_id = str(uuid.uuid4())  # ID único del lock (para liberarlo solo nosotros)

    def acquire(self) -> bool:
        """
        Adquiere el lock.
        
        Usa SET NX (set if not exists) que es atómico en Redis.
        Devuelve True si se adquirió, False si ya estaba ocupado.
        """
        try:
            from django_redis import get_redis_connection
            redis_conn = get_redis_connection("default")

            # SET key value NX EX timeout (atómico)
            acquired = redis_conn.set(
                self.key,
                self._lock_id,
                nx=True,        # Solo si NO existe
                ex=self.timeout # TTL automático (evita locks zombies)
            )
            if acquired:
                logger.debug("distributed_lock_acquired", key=self.key)
            else:
                logger.debug("distributed_lock_not_available", key=self.key)
            return bool(acquired)

        except Exception as e:
            logger.error("distributed_lock_acquire_error", key=self.key, error=str(e))
            return False

    def release(self) -> bool:
        """
        Libera el lock.
        
        Solo lo libera si somos nosotros quienes lo adquirimos.
        Usa un script Lua para que la comprobación y eliminación sean atómicas.
        """
        try:
            from django_redis import get_redis_connection
            redis_conn = get_redis_connection("default")

            # Script Lua: comprueba y elimina de forma atómica
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            result = redis_conn.eval(lua_script, 1, self.key, self._lock_id)
            if result:
                logger.debug("distributed_lock_released", key=self.key)
            return bool(result)

        except Exception as e:
            logger.error("distributed_lock_release_error", key=self.key, error=str(e))
            return False

    def __enter__(self):
        """Soporte para uso con 'with' statement."""
        if not self.acquire():
            raise RuntimeError(f"No se pudo adquirir el lock: {self.key}")
        return self

    def __exit__(self, *args):
        self.release()


class TokenStore:
    """
    Almacena tokens temporales en Redis.
    
    Para: verificación de email, reset de contraseña, OTPs, etc.
    Los tokens expiran automáticamente gracias al TTL de Redis.
    """

    PREFIX = "token:"

    def store(self, token: str, data: dict, ttl: int = 3600) -> None:
        """Almacena un token con sus datos asociados."""
        key = f"{self.PREFIX}{token}"
        cache.set(key, json.dumps(data), timeout=ttl)
        logger.debug("token_stored", ttl=ttl)

    def retrieve(self, token: str) -> Optional[dict]:
        """Recupera los datos de un token."""
        key = f"{self.PREFIX}{token}"
        raw = cache.get(key)
        if raw:
            return json.loads(raw)
        return None

    def consume(self, token: str) -> Optional[dict]:
        """
        Recupera y ELIMINA el token (uso único).
        
        Útil para tokens de un solo uso (email verification, reset password).
        """
        data = self.retrieve(token)
        if data:
            cache.delete(f"{self.PREFIX}{token}")
            logger.info("token_consumed")
        return data


# ─── Decorador de caché para funciones ───────────────────────

def cached(key_pattern: str, ttl: int = CacheService.TTL_MEDIUM):
    """
    Decorador para cachear el resultado de una función.
    
    Ejemplo:
        @cached("user:{user_id}", ttl=300)
        def get_user(user_id: str):
            return repository.get_by_id(user_id)
    
    La key se formatea con los argumentos de la función.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Construir la cache key con los argumentos
            all_args = {**{f"arg{i}": v for i, v in enumerate(args)}, **kwargs}
            try:
                cache_key = key_pattern.format(**all_args)
            except KeyError:
                # Si el patrón no coincide con los args, usar hash
                cache_key = f"{key_pattern}:{hashlib.md5(str(all_args).encode()).hexdigest()}"

            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug("cache_decorator_hit", key=cache_key)
                return cached_value

            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout=ttl)
            logger.debug("cache_decorator_set", key=cache_key, ttl=ttl)
            return result

        return wrapper
    return decorator
