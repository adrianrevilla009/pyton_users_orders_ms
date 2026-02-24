"""
============================================================
USER MODEL - Modelo Django ORM (Infraestructura)
============================================================
Esta es la representación de la BD. Es completamente
diferente a la entidad de dominio User.

Puntos clave:
- Hereda de AbstractBaseUser para control total del modelo de auth
- El ORM es un DETALLE DE IMPLEMENTACIÓN del dominio
- El mapper (abajo) traduce entre modelo ORM y entidad de dominio
- Prometheus instrumenta las queries automáticamente
============================================================
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
import uuid


class UserManager(BaseUserManager):
    """Manager personalizado para el modelo User."""

    def create_user(self, email, name, password=None, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio')
        email = self.normalize_email(email)
        user = self.model(email=email, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('status', 'active')
        return self.create_user(email, name, password, **extra_fields)


class UserModel(AbstractBaseUser, PermissionsMixin):
    """
    Modelo de base de datos para usuarios.
    
    Importante: este modelo NO es la entidad de dominio.
    Es solo la representación ORM de la persistencia.
    """

    class RoleChoices(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        MANAGER = 'manager', 'Manager'
        CUSTOMER = 'customer', 'Customer'
        READONLY = 'readonly', 'Solo lectura'

    class StatusChoices(models.TextChoices):
        PENDING = 'pending_verification', 'Pendiente verificación'
        ACTIVE = 'active', 'Activo'
        SUSPENDED = 'suspended', 'Suspendido'
        DELETED = 'deleted', 'Eliminado'

    # UUID como primary key (mejor que integer para sistemas distribuidos)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, verbose_name='Nombre')
    email = models.EmailField(unique=True, db_index=True, verbose_name='Email')

    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.CUSTOMER,
        db_index=True,    # Índice para filtros por rol frecuentes
    )
    status = models.CharField(
        max_length=30,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
        db_index=True,
    )
    login_count = models.PositiveIntegerField(default=0)
    last_login_custom = models.DateTimeField(null=True, blank=True)

    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Django auth requirements
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    objects = UserManager()

    class Meta:
        db_table = 'users'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['-created_at']
        # Índices compuestos para queries frecuentes
        indexes = [
            models.Index(fields=['email', 'status'], name='idx_users_email_status'),
            models.Index(fields=['role', 'status'], name='idx_users_role_status'),
        ]

    def __str__(self):
        return f"{self.name} <{self.email}>"
