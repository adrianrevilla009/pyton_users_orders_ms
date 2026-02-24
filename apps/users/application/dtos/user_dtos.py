"""
============================================================
DTOs (Data Transfer Objects) - Capa de Aplicación
============================================================
Los DTOs son objetos simples que transfieren datos entre
capas sin lógica de negocio.

En la arquitectura hexagonal:
- Los Use Cases reciben DTOs (no entidades de dominio)
- Los Use Cases retornan DTOs (no entidades de dominio)

Esto aísla la capa de aplicación de cambios en el dominio
y de cambios en la presentación (API, CLI, etc.)

Usamos Pydantic para validación automática.
============================================================
"""

from pydantic import BaseModel, field_validator
import re
from typing import Optional
from datetime import datetime


class RegisterUserDTO(BaseModel):
    """DTO para registrar un nuevo usuario."""
    name: str
    email: str
    password: str

    @field_validator('name')
    @classmethod
    def name_must_have_min_length(cls, v):
        if len(v.strip()) < 2:
            raise ValueError('El nombre debe tener al menos 2 caracteres')
        return v.strip()

    @field_validator('email')
    @classmethod
    def email_must_be_valid(cls, v):
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', v):
            raise ValueError('Email inválido')
        return v.lower()

    class Config:
        str_strip_whitespace = True


class UpdateUserDTO(BaseModel):
    """DTO para actualizar datos del usuario."""
    name: Optional[str] = None

    class Config:
        str_strip_whitespace = True


class ChangeRoleDTO(BaseModel):
    """DTO para cambiar rol de usuario (solo admins)."""
    role: str

    @field_validator('role')
    @classmethod
    def role_must_be_valid(cls, v):
        valid_roles = ['admin', 'manager', 'customer', 'readonly']
        if v not in valid_roles:
            raise ValueError(f'Rol inválido. Opciones: {valid_roles}')
        return v


class SuspendUserDTO(BaseModel):
    """DTO para suspender un usuario."""
    reason: str

    @field_validator('reason')
    @classmethod
    def reason_must_have_min_length(cls, v):
        if len(v.strip()) < 5:
            raise ValueError('La razón debe tener al menos 5 caracteres')
        return v.strip()


class UserResponseDTO(BaseModel):
    """DTO de respuesta con datos del usuario (sin contraseña)."""
    id: str
    name: str
    email: str
    role: str
    status: str
    login_count: int
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True  # Permite crear desde objetos ORM
