"""
============================================================
SERIALIZERS - Capa de presentación HTTP
============================================================
Los serializers de DRF gestionan:
- Deserialización: JSON -> datos validados
- Serialización: objetos -> JSON para la respuesta

En nuestra arquitectura, los serializers son la "puerta de entrada"
de la capa de aplicación. Convierten HTTP payload a DTOs.
============================================================
"""

from rest_framework import serializers


class RegisterUserSerializer(serializers.Serializer):
    """Valida los datos de registro de usuario."""
    name = serializers.CharField(min_length=2, max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        """Validación cross-field: passwords deben coincidir."""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Las contraseñas no coinciden")
        return data


class LoginSerializer(serializers.Serializer):
    """Valida las credenciales de login."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserResponseSerializer(serializers.Serializer):
    """Serializa la respuesta de usuario (sin datos sensibles)."""
    id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    status = serializers.CharField()
    login_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    last_login = serializers.DateTimeField(allow_null=True)


class UpdateUserSerializer(serializers.Serializer):
    """Para actualizar datos básicos del usuario."""
    name = serializers.CharField(min_length=2, max_length=255, required=False)


class ChangeRoleSerializer(serializers.Serializer):
    """Para cambiar el rol. Solo admins."""
    role = serializers.ChoiceField(choices=['admin', 'manager', 'customer', 'readonly'])


class SuspendUserSerializer(serializers.Serializer):
    """Para suspender un usuario. Requiere razón."""
    reason = serializers.CharField(min_length=5, max_length=500)
