"""
============================================================
JWT TOKEN SERVICE - Implementación con SimpleJWT
============================================================
Implementa el puerto TokenService usando djangorestframework-simplejwt.
============================================================
"""

from rest_framework_simplejwt.tokens import RefreshToken
from apps.users.application.use_cases.login_user import TokenService


class JwtTokenService(TokenService):
    """Genera tokens JWT usando SimpleJWT."""

    def generate_access_token(self, user_id: str, email: str, role: str) -> str:
        """Genera un access token JWT con claims personalizados."""
        from apps.users.infrastructure.models.user_model import UserModel
        try:
            user = UserModel.objects.get(id=user_id)
            refresh = RefreshToken.for_user(user)
            # Añadir claims personalizados al token
            refresh['role'] = role
            refresh['email'] = email
            return str(refresh.access_token)
        except UserModel.DoesNotExist:
            raise ValueError(f"Usuario no encontrado: {user_id}")

    def generate_refresh_token(self, user_id: str) -> str:
        """Genera un refresh token JWT."""
        from apps.users.infrastructure.models.user_model import UserModel
        try:
            user = UserModel.objects.get(id=user_id)
            refresh = RefreshToken.for_user(user)
            return str(refresh)
        except UserModel.DoesNotExist:
            raise ValueError(f"Usuario no encontrado: {user_id}")
