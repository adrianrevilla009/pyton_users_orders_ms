"""URLs de autenticación."""
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenBlacklistView

from src.interfaces.api.views.user_views import UserRegistrationView

urlpatterns = [
    # Registro
    path('register/', UserRegistrationView.as_view(), name='auth-register'),

    # JWT Login → devuelve access + refresh token
    path('login/', TokenObtainPairView.as_view(), name='auth-login'),

    # Renovar access token con el refresh token
    path('refresh/', TokenRefreshView.as_view(), name='auth-refresh'),

    # Logout → invalida el refresh token (blacklist)
    path('logout/', TokenBlacklistView.as_view(), name='auth-logout'),
]
