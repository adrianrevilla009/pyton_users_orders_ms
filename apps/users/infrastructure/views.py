"""
============================================================
VIEWS - Adaptadores HTTP de entrada (Hexagonal)
============================================================
Las vistas son adaptadores de entrada: convierten requests
HTTP en llamadas a los Use Cases.

Son lo más delgadas posible:
1. Extraer datos del request
2. Llamar al Use Case
3. Serializar respuesta

NO contienen lógica de negocio.
============================================================
"""

import structlog
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

from apps.users.application.use_cases.register_user import RegisterUserUseCase, UserAlreadyExistsError
from apps.users.application.use_cases.login_user import LoginUserUseCase, AuthenticationError
from apps.users.application.dtos.user_dtos import RegisterUserDTO, UpdateUserDTO, SuspendUserDTO, ChangeRoleDTO
from apps.users.infrastructure.serializers.user_serializers import (
    RegisterUserSerializer, LoginSerializer, UserResponseSerializer,
    UpdateUserSerializer, ChangeRoleSerializer, SuspendUserSerializer
)
from apps.users.infrastructure.dependencies import get_register_use_case, get_login_use_case
from shared.infrastructure.permissions import IsAdminOrManager

logger = structlog.get_logger(__name__)


class RegisterUserView(APIView):
    """POST /api/v1/auth/register - Registro de nuevo usuario."""
    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterUserSerializer,
        responses={201: UserResponseSerializer, 400: OpenApiResponse(description="Datos inválidos")},
        tags=['Autenticación'],
        summary='Registrar nuevo usuario',
    )
    def post(self, request):
        # 1. Validar input con serializer
        serializer = RegisterUserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # 2. Crear DTO
        dto = RegisterUserDTO(
            name=serializer.validated_data['name'],
            email=serializer.validated_data['email'],
            password=serializer.validated_data['password'],
        )

        # 3. Ejecutar Use Case
        try:
            use_case = get_register_use_case()
            result = use_case.execute(dto)
        except UserAlreadyExistsError as e:
            return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # 4. Serializar respuesta
        return Response(
            UserResponseSerializer(result.dict()).data,
            status=status.HTTP_201_CREATED
        )


class LoginView(APIView):
    """POST /api/v1/auth/login - Login y obtención de tokens JWT."""
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginSerializer,
        tags=['Autenticación'],
        summary='Login de usuario',
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            use_case = get_login_use_case()
            result = use_case.execute(
                email=serializer.validated_data['email'],
                password=serializer.validated_data['password'],
            )
        except AuthenticationError as e:
            # HTTP 401 para credenciales incorrectas
            return Response({'error': str(e)}, status=status.HTTP_401_UNAUTHORIZED)

        return Response({
            'access': result.access_token,
            'refresh': result.refresh_token,
            'token_type': result.token_type,
            'user': {
                'id': result.user_id,
                'email': result.email,
                'role': result.role,
            }
        })


class UserProfileView(APIView):
    """GET/PUT /api/v1/users/me - Perfil del usuario autenticado."""
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Usuarios'], summary='Obtener perfil del usuario autenticado')
    def get(self, request):
        """Retorna el perfil del usuario autenticado."""
        user = request.user
        return Response({
            'id': str(user.id),
            'name': user.name,
            'email': user.email,
            'role': user.role,
            'status': user.status,
            'login_count': user.login_count,
        })


class UserListView(APIView):
    """GET /api/v1/users/ - Lista de usuarios (solo admins/managers)."""
    permission_classes = [IsAdminOrManager]

    @extend_schema(tags=['Usuarios'], summary='Listar todos los usuarios')
    def get(self, request):
        from apps.users.infrastructure.models.user_model import UserModel
        users = UserModel.objects.all()[:20]
        return Response({
            'count': users.count(),
            'results': [
                {
                    'id': str(u.id),
                    'name': u.name,
                    'email': u.email,
                    'role': u.role,
                    'status': u.status,
                }
                for u in users
            ]
        })
