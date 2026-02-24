"""
=============================================================================
SERIALIZERS — Validación y Serialización de la capa API
=============================================================================

Los serializers de DRF sirven para:
1. Deserializar (input): JSON → objeto Python validado
2. Serializar (output): objeto Python → JSON

Los serializers validan FORMATO y TIPOS.
Los DTOs (Pydantic) validan LÓGICA de negocio.
Ambas capas de validación se complementan.
"""
from rest_framework import serializers


class CreateUserSerializer(serializers.Serializer):
    """Serializer para el registro de usuarios."""
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, min_length=1)
    last_name = serializers.CharField(max_length=150, min_length=1)
    password = serializers.CharField(min_length=10, write_only=True)
    role = serializers.ChoiceField(
        choices=['buyer', 'seller'],
        default='buyer',
    )
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_password(self, value: str) -> str:
        """Validación adicional de contraseña."""
        if value.isdigit():
            raise serializers.ValidationError("La contraseña no puede ser solo números")
        return value


class UserSerializer(serializers.Serializer):
    """Serializer de respuesta para usuarios."""
    id = serializers.UUIDField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    full_name = serializers.CharField()
    role = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=10, write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict) -> dict:
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': 'Las contraseñas no coinciden'
            })
        return attrs
