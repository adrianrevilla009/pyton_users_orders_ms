"""
=============================================================================
DTOs (Data Transfer Objects) — Capa de Aplicación
=============================================================================

Los DTOs son objetos simples para transportar datos entre capas.
Usando Pydantic v2 obtenemos:
- Validación automática en la entrada
- Serialización/deserialización a JSON
- Type hints con runtime validation
- Documentación automática en Swagger

DTOs de entrada (Commands/Queries) vs. DTOs de salida (Responses):
- CreateUserCommand: datos que entran para crear un usuario
- UserResponse: datos que se devuelven al cliente
"""
from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, EmailStr, field_validator, model_validator


# =============================================================================
# COMMANDS (entrada) — Datos para operaciones de escritura
# =============================================================================

class CreateUserCommand(BaseModel):
    """Datos necesarios para crear un nuevo usuario."""
    email: EmailStr
    first_name: str
    last_name: str
    password: str
    role: str = 'buyer'
    phone: Optional[str] = None

    @field_validator('first_name', 'last_name')
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v.strip()

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("La contraseña debe tener al menos 10 caracteres")
        if not any(c.isupper() for c in v):
            raise ValueError("La contraseña debe tener al menos una mayúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("La contraseña debe tener al menos un número")
        return v

    @field_validator('role')
    @classmethod
    def valid_role(cls, v: str) -> str:
        valid_roles = {'buyer', 'seller', 'admin', 'support'}
        if v not in valid_roles:
            raise ValueError(f"Rol inválido. Válidos: {valid_roles}")
        return v


class UpdateUserCommand(BaseModel):
    """Datos para actualizar un usuario existente."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


class ChangePasswordCommand(BaseModel):
    current_password: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("La contraseña debe tener al menos 10 caracteres")
        return v


# =============================================================================
# RESPONSES (salida) — Datos que devolvemos al cliente
# =============================================================================

class UserResponse(BaseModel):
    """Representación de usuario para la API."""
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    full_name: str
    role: str
    status: str
    created_at: datetime

    model_config = {'from_attributes': True}  # Para construir desde ORM models


class UserListResponse(BaseModel):
    """Lista paginada de usuarios."""
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
