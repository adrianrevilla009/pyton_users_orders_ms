"""
=============================================================================
PERMISOS — RBAC con DRF
=============================================================================

Implementación de permisos basados en roles (RBAC).
Se integra con el sistema de permisos de Django REST Framework.

Uso:
    @permission_classes([IsAdminUser | IsSeller])
    def my_view(request):
        ...
"""
from rest_framework import permissions
from rest_framework.request import Request


class IsAdmin(permissions.BasePermission):
    """Solo administradores."""
    message = "Se requiere rol de administrador."

    def has_permission(self, request: Request, view) -> bool:
        return (
            request.user.is_authenticated and
            request.user.role == 'admin'
        )


class IsSeller(permissions.BasePermission):
    """Solo vendedores (y admins)."""
    message = "Se requiere rol de vendedor."

    def has_permission(self, request: Request, view) -> bool:
        return (
            request.user.is_authenticated and
            request.user.role in ('seller', 'admin')
        )


class IsBuyer(permissions.BasePermission):
    """Compradores autenticados."""
    message = "Debes estar autenticado como comprador."

    def has_permission(self, request: Request, view) -> bool:
        return (
            request.user.is_authenticated and
            request.user.role in ('buyer', 'seller', 'admin')
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Permiso a nivel de objeto.
    Permite acceso si el usuario es el dueño del objeto o es admin.
    
    El objeto debe tener un campo 'user_id', 'buyer_id', o 'seller_id'.
    """
    message = "No tienes permiso para acceder a este recurso."

    def has_object_permission(self, request: Request, view, obj) -> bool:
        if request.user.role == 'admin':
            return True

        # Comprobar distintos campos de ownership
        user_id = str(request.user.id)
        return (
            str(getattr(obj, 'user_id', None)) == user_id or
            str(getattr(obj, 'buyer_id', None)) == user_id or
            str(getattr(obj, 'seller_id', None)) == user_id
        )


class ReadOnly(permissions.BasePermission):
    """Permite solo operaciones de lectura (GET, HEAD, OPTIONS)."""

    def has_permission(self, request: Request, view) -> bool:
        return request.method in permissions.SAFE_METHODS
