"""URLs de autenticación."""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from apps.users.infrastructure.views import RegisterUserView, LoginView

urlpatterns = [
    path('register/', RegisterUserView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
