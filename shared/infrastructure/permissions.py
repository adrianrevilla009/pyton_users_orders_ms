"""
============================================================
PERMISOS PERSONALIZADOS - RBAC
============================================================
DRF permite crear clases de permiso personalizadas.
Aquí implementamos RBAC (Role-Based Access Control)
basado en el rol del usuario en la entidad de dominio.

Para ABAC (Attribute-Based Access Control) a nivel de objeto,
usamos django-guardian (ver apps.users.admin).
============================================================
"""

from rest_framework.permissions import BasePermission
import structlog

logger = structlog.get_logger(__name__)


class IsAdminRole(BasePermission):
    """Solo usuarios con rol ADMIN pueden acceder."""
    message = "Requiere rol de Administrador"

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        has_perm = request.user.role == 'admin'
        if not has_perm:
            logger.warning(
                "Acceso denegado (requiere admin)",
                user_id=str(request.user.id),
                user_role=request.user.role,
                path=request.path,
            )
        return has_perm


class IsAdminOrManager(BasePermission):
    """Admins y Managers pueden acceder."""
    message = "Requiere rol de Administrador o Manager"

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in ['admin', 'manager']


class IsOwnerOrAdmin(BasePermission):
    """
    El usuario puede acceder a su propio recurso.
    Los admins pueden acceder a cualquier recurso.
    
    Requiere que el objeto tenga un campo 'user' o 'user_id'.
    """
    message = "Solo puedes acceder a tus propios recursos"

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True
        # Soporte para diferentes estructuras de objeto
        if hasattr(obj, 'user'):
            return obj.user == request.user
        if hasattr(obj, 'user_id'):
            return str(obj.user_id) == str(request.user.id)
        if hasattr(obj, 'id'):
            return str(obj.id) == str(request.user.id)
        return False


class ReadOnly(BasePermission):
    """Permite GET, HEAD, OPTIONS a cualquier usuario autenticado."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.method in ('GET', 'HEAD', 'OPTIONS')
