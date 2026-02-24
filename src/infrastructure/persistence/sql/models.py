"""
=============================================================================
MODELOS DJANGO ORM — Capa de Infraestructura
=============================================================================

Estos son los modelos de base de datos (PostgreSQL).
Son adaptadores que traducen entre la entidad de dominio y la BD.

IMPORTANTE: Los modelos ORM NO son las entidades de dominio.
Son representaciones de tablas SQL. El repositorio hace la traducción.

Patrón aplicado: Table Data Gateway / Active Record (Django ORM) pero
encapsulado detrás de la interfaz del repositorio para mantener
el dominio limpio de dependencias de infraestructura.
"""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


class UserManager(BaseUserManager):
    """Manager personalizado para el modelo de usuario."""

    def create_user(self, email: str, password: str = None, **extra_fields):
        if not email:
            raise ValueError("El email es obligatorio")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Modelo de usuario personalizado.
    Extiende AbstractBaseUser para control total sobre autenticación.
    Usamos UUID como PK para evitar IDs secuenciales predecibles (seguridad).
    """
    # UUID como PK — no predecible, distribuido, sin coordinación central
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True, db_index=True)  # Index para búsquedas rápidas
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)

    ROLE_CHOICES = [
        ('admin', 'Administrador'),
        ('seller', 'Vendedor'),
        ('buyer', 'Comprador'),
        ('support', 'Soporte'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='buyer', db_index=True)

    STATUS_CHOICES = [
        ('pending_verification', 'Pendiente de verificación'),
        ('active', 'Activo'),
        ('suspended', 'Suspendido'),
        ('deleted', 'Eliminado'),
    ]
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending_verification')

    # Django requiere estos campos para el sistema de permisos
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Auditoría — siempre útil en producción
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # Soft delete — en vez de borrar, marcamos como eliminado
    deleted_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'email'  # Login con email en vez de username
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    class Meta:
        app_label = 'sql_models'
        db_table = 'users'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'status']),  # Índice compuesto
            models.Index(fields=['role', 'status']),
        ]

    def __str__(self):
        return f"{self.email} ({self.role})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Product(models.Model):
    """Modelo SQL para productos."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ForeignKey a User — solo referenciamos el ID en el dominio,
    # pero en SQL necesitamos la FK real para integridad referencial
    seller = models.ForeignKey(
        User,
        on_delete=models.CASCADE,  # Si se elimina el seller, se eliminan sus productos
        related_name='products',
        db_index=True,
    )

    name = models.CharField(max_length=255)
    description = models.TextField()
    slug = models.SlugField(unique=True, max_length=255)

    # Precio — usamos Decimal para precisión monetaria
    price_amount = models.DecimalField(max_digits=10, decimal_places=2)
    price_currency = models.CharField(max_length=3, default='EUR')

    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, blank=True, unique=True, null=True)

    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('active', 'Activo'),
        ('out_of_stock', 'Sin stock'),
        ('discontinued', 'Descontinuado'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    category = models.CharField(max_length=100, db_index=True)
    image_url = models.URLField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'sql_models'
        db_table = 'products'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category', 'status']),
            models.Index(fields=['seller', 'status']),
        ]

    def __str__(self):
        return f"{self.name} ({self.status})"


class Order(models.Model):
    """Modelo SQL para pedidos."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='orders')

    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('confirmed', 'Confirmado'),
        ('paid', 'Pagado'),
        ('shipped', 'Enviado'),
        ('delivered', 'Entregado'),
        ('cancelled', 'Cancelado'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Dirección de envío desnormalizada — snapshot del momento de compra
    shipping_street = models.CharField(max_length=255)
    shipping_city = models.CharField(max_length=100)
    shipping_postal_code = models.CharField(max_length=20)
    shipping_country = models.CharField(max_length=2)
    shipping_state = models.CharField(max_length=100, blank=True)

    # Totales cacheados para rendimiento (evita recalcular)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total_currency = models.CharField(max_length=3, default='EUR')

    payment_id = models.CharField(max_length=255, blank=True)
    tracking_number = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'sql_models'
        db_table = 'orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['buyer', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]


class OrderItem(models.Model):
    """Items de un pedido — tabla de detalle."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)

    # Datos desnormalizados — snapshot del momento de compra
    # El nombre del producto puede cambiar, pero el historial debe preservarse
    product_name = models.CharField(max_length=255)
    unit_price_amount = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price_currency = models.CharField(max_length=3, default='EUR')
    quantity = models.PositiveIntegerField()

    class Meta:
        app_label = 'sql_models'
        db_table = 'order_items'


class AuditLog(models.Model):
    """
    Registro de auditoría para acciones sensibles.
    Inmutable — nunca se modifica ni elimina.
    Fundamental para compliance (GDPR, SOX, etc.)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)  # 'user.created', 'order.cancelled', etc.
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=50)
    data = models.JSONField(default=dict)       # Datos del cambio
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'sql_models'
        db_table = 'audit_logs'
        ordering = ['-created_at']
        # Nunca permitir modificación — solo inserción
        # Esto se puede reforzar a nivel de BD con permisos

    def __str__(self):
        return f"{self.action} on {self.entity_type}:{self.entity_id}"
