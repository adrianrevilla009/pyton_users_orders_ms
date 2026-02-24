"""
============================================================
CACHED USER REPOSITORY - Decorador con caché Redis
============================================================
Patrón Decorator: envuelve el repositorio principal añadiendo
caché sin modificar la implementación original.

Ventajas:
- El repositorio base no sabe nada de caché
- Se puede activar/desactivar fácilmente
- Cache-aside pattern: busca en caché, si no está va a BD

Cache invalidation es uno de los problemas más difíciles
en informática. Aquí usamos TTL + invalidación explícita.
============================================================
"""

import json
import structlog
from typing import Optional, List
from datetime import datetime

from django.core.cache import cache

from apps.users.domain.entities.user import User, UserRole, UserStatus
from apps.users.domain.repositories.user_repository import UserRepository
from apps.users.domain.value_objects.email import UserEmail
from apps.users.domain.value_objects.password import HashedPassword

logger = structlog.get_logger(__name__)

# TTL del caché en segundos (15 minutos)
CACHE_TTL = 900


class CachedUserRepository(UserRepository):
    """
    Decorator que añade caché Redis al repositorio de usuarios.
    
    Implementa el patrón Cache-Aside:
    1. Buscar en caché (Redis)
    2. Si no está (cache miss), buscar en BD
    3. Guardar en caché el resultado
    4. Retornar el resultado
    """

    def __init__(self, inner_repository: UserRepository):
        """
        Recibe el repositorio real que envuelve.
        Se inyecta la dependencia, no se instancia aquí.
        """
        self._inner = inner_repository

    def save(self, user: User) -> User:
        """Al guardar, invalida el caché de ese usuario."""
        saved = self._inner.save(user)
        # Invalidar caché tras escribir (write-through)
        self._invalidate(saved.id, str(saved.email))
        logger.debug("Cache invalidado tras save", user_id=saved.id)
        return saved

    def find_by_id(self, user_id: str) -> Optional[User]:
        """Cache-aside por ID."""
        cache_key = self._key_by_id(user_id)
        cached = cache.get(cache_key)

        if cached:
            logger.debug("Cache HIT por ID", user_id=user_id)
            return self._deserialize(cached)

        logger.debug("Cache MISS por ID", user_id=user_id)
        user = self._inner.find_by_id(user_id)

        if user:
            cache.set(cache_key, self._serialize(user), CACHE_TTL)

        return user

    def find_by_email(self, email: UserEmail) -> Optional[User]:
        """Cache-aside por email."""
        cache_key = self._key_by_email(str(email))
        cached = cache.get(cache_key)

        if cached:
            logger.debug("Cache HIT por email", email=str(email))
            return self._deserialize(cached)

        logger.debug("Cache MISS por email", email=str(email))
        user = self._inner.find_by_email(email)

        if user:
            cache.set(cache_key, self._serialize(user), CACHE_TTL)

        return user

    def find_all(self, offset: int = 0, limit: int = 20) -> List[User]:
        """Lista no se cachea (datos muy variables)."""
        return self._inner.find_all(offset, limit)

    def delete(self, user_id: str) -> None:
        user = self._inner.find_by_id(user_id)
        self._inner.delete(user_id)
        if user:
            self._invalidate(user_id, str(user.email))

    def exists_by_email(self, email: UserEmail) -> bool:
        # Reutiliza find_by_email que ya tiene caché
        return self.find_by_email(email) is not None

    def count(self) -> int:
        return self._inner.count()

    # ---- Cache keys ----

    def _key_by_id(self, user_id: str) -> str:
        return f"user:id:{user_id}"

    def _key_by_email(self, email: str) -> str:
        return f"user:email:{email}"

    def _invalidate(self, user_id: str, email: str) -> None:
        """Elimina todas las entradas de caché de un usuario."""
        cache.delete_many([
            self._key_by_id(user_id),
            self._key_by_email(email),
        ])

    # ---- Serialización ----

    def _serialize(self, user: User) -> str:
        """Convierte la entidad a JSON para Redis."""
        return json.dumps({
            'id': user.id,
            'name': user.name,
            'email': str(user.email),
            'hashed_password': str(user.hashed_password),
            'role': user.role.value,
            'status': user.status.value,
            'login_count': user.login_count,
            'created_at': user.created_at.isoformat(),
            'updated_at': user.updated_at.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None,
        })

    def _deserialize(self, data: str) -> User:
        """Reconstruye la entidad desde JSON de Redis."""
        d = json.loads(data)
        user = User(
            name=d['name'],
            email=UserEmail(d['email']),
            hashed_password=HashedPassword(d['hashed_password']),
            role=UserRole(d['role']),
            entity_id=d['id'],
        )
        object.__setattr__(user, '_status', UserStatus(d['status']))
        object.__setattr__(user, '_login_count', d['login_count'])
        last_login = d.get('last_login')
        object.__setattr__(user, '_last_login', datetime.fromisoformat(last_login) if last_login else None)
        return user
