"""
=============================================================================
VISTAS API: Users
=============================================================================

Las vistas son la capa más externa — el punto de entrada HTTP.
Responsabilidades:
1. Parsear y validar la request HTTP
2. Delegar al caso de uso
3. Formatear la respuesta HTTP

Las vistas NO contienen lógica de negocio — solo coordinación.
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter

import structlog

from src.application.dtos.user_dtos import CreateUserCommand, UserResponse
from src.application.use_cases.create_user import CreateUserUseCase, UserAlreadyExistsError
from src.infrastructure.persistence.sql.user_repository_impl import SQLUserRepository
from src.infrastructure.messaging.kafka_event_bus import KafkaEventBus
from src.infrastructure.external_apis.sendgrid_service import SendGridNotificationService
from src.infrastructure.security.permissions import IsAdmin, IsOwnerOrAdmin
from src.interfaces.api.serializers.user_serializers import UserSerializer, CreateUserSerializer

logger = structlog.get_logger(__name__)


class UserRegistrationView(APIView):
    """
    POST /api/v1/auth/register/
    Registro público de nuevos usuarios.
    """
    permission_classes = [AllowAny]  # Endpoint público

    @extend_schema(
        request=CreateUserSerializer,
        responses={201: UserSerializer, 400: dict, 409: dict},
        description="Registra un nuevo usuario en el sistema",
        tags=["Autenticación"],
    )
    def post(self, request: Request) -> Response:
        # 1. Validar datos de entrada con el serializer DRF
        serializer = CreateUserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Construir el command (DTO de entrada)
        command = CreateUserCommand(**serializer.validated_data)

        # 3. Construir el caso de uso con sus dependencias (DI manual)
        # En producción: usar un contenedor de DI (punq, dependency-injector)
        use_case = self._build_use_case()

        try:
            # 4. Ejecutar el caso de uso
            user_response = use_case.execute(command)

            # 5. Devolver respuesta
            return Response(
                user_response.model_dump(),
                status=status.HTTP_201_CREATED,
            )

        except UserAlreadyExistsError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_409_CONFLICT,
            )

        except Exception as e:
            logger.error("user_registration_failed", error=str(e))
            return Response(
                {'error': 'Error interno del servidor'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _build_use_case(self) -> CreateUserUseCase:
        """
        Construye el caso de uso con sus dependencias.
        
        En producción real, esto lo haría un contenedor de inyección de dependencias.
        Aquí lo hacemos manual para que sea explícito y fácil de entender.
        """
        from src.infrastructure.security.password_hasher import DjangoPasswordHasher

        return CreateUserUseCase(
            user_repository=SQLUserRepository(),
            event_bus=KafkaEventBus(),
            notification_service=SendGridNotificationService(),
            password_hasher=DjangoPasswordHasher(),
        )


class UserDetailView(APIView):
    """
    GET/PUT/DELETE /api/v1/users/{user_id}/
    Gestión de un usuario específico.
    """
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    @extend_schema(
        responses={200: UserSerializer, 404: dict},
        description="Obtiene los detalles de un usuario",
        tags=["Usuarios"],
    )
    def get(self, request: Request, user_id: str) -> Response:
        import uuid
        repository = SQLUserRepository()
        user = repository.find_by_id(uuid.UUID(user_id))

        if not user:
            return Response(
                {'error': 'Usuario no encontrado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Verificar permiso de objeto (solo el propio usuario o admin)
        self.check_object_permissions(request, user)

        return Response(UserResponse(
            id=user.id,
            email=str(user.email),
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            role=user.role.value,
            status=user.status.value,
            created_at=user.created_at,
        ).model_dump())


class UserListView(APIView):
    """
    GET /api/v1/users/ — Solo para administradores.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='role', description='Filtrar por rol', required=False, type=str),
            OpenApiParameter(name='page', description='Número de página', required=False, type=int),
        ],
        description="Lista todos los usuarios (solo admins)",
        tags=["Usuarios (Admin)"],
    )
    def get(self, request: Request) -> Response:
        from src.infrastructure.persistence.sql.models import User as UserORM
        from django.core.paginator import Paginator

        queryset = UserORM.objects.all()

        # Filtros opcionales
        role = request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)

        # Paginación
        paginator = Paginator(queryset, 20)
        page = request.query_params.get('page', 1)
        page_obj = paginator.get_page(page)

        users_data = [
            {
                'id': str(u.id),
                'email': u.email,
                'full_name': u.full_name,
                'role': u.role,
                'status': u.status,
                'created_at': u.created_at.isoformat(),
            }
            for u in page_obj
        ]

        return Response({
            'items': users_data,
            'total': paginator.count,
            'page': page_obj.number,
            'total_pages': paginator.num_pages,
        })
