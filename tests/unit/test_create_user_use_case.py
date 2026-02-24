"""
=============================================================================
TESTS UNITARIOS: CreateUser Use Case
=============================================================================

Tests del caso de uso usando dobles de prueba (mocks/stubs).
No se usa BD real — todo está en memoria.
"""
import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

from src.application.use_cases.create_user import CreateUserUseCase, UserAlreadyExistsError
from src.application.dtos.user_dtos import CreateUserCommand
from src.domain.entities.user import UserStatus
from src.infrastructure.messaging.in_memory_event_bus import InMemoryEventBus
from src.domain.events.user_events import UserCreatedEvent


class FakeUserRepository:
    """Implementación falsa del repositorio para tests."""

    def __init__(self, existing_emails=None):
        self._users = {}
        self._existing_emails = set(existing_emails or [])

    def save(self, user):
        self._users[str(user.id)] = user
        return user

    def find_by_id(self, user_id):
        return self._users.get(str(user_id))

    def find_by_email(self, email):
        for user in self._users.values():
            if str(user.email) == str(email):
                return user
        return None

    def exists_by_email(self, email):
        return str(email) in self._existing_emails

    def delete(self, user_id):
        self._users.pop(str(user_id), None)


class FakePasswordHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == f"hashed:{password}"


class FakeNotificationService:
    def __init__(self):
        self.sent_emails = []

    def send_welcome_email(self, to_email, user_name):
        self.sent_emails.append(('welcome', to_email, user_name))

    def send_order_confirmation(self, *args): pass
    def send_payment_confirmation(self, *args): pass
    def send_password_reset(self, *args): pass


class TestCreateUserUseCase:

    def setup_method(self):
        """Setup que se ejecuta antes de cada test."""
        self.repository = FakeUserRepository()
        self.event_bus = InMemoryEventBus()
        self.notification_service = FakeNotificationService()
        self.password_hasher = FakePasswordHasher()

        self.use_case = CreateUserUseCase(
            user_repository=self.repository,
            event_bus=self.event_bus,
            notification_service=self.notification_service,
            password_hasher=self.password_hasher,
        )

    def _make_command(self, email='test@example.com', role='buyer') -> CreateUserCommand:
        return CreateUserCommand(
            email=email,
            first_name='Juan',
            last_name='García',
            password='SecurePass123',
            role=role,
        )

    def test_create_user_successfully(self):
        """Test del flujo feliz: crear usuario correctamente."""
        command = self._make_command()
        response = self.use_case.execute(command)

        assert response.email == 'test@example.com'
        assert response.first_name == 'Juan'
        assert response.role == 'buyer'
        assert response.status == 'pending_verification'

    def test_create_user_publishes_event(self):
        """Se debe publicar un UserCreatedEvent."""
        command = self._make_command()
        self.use_case.execute(command)

        events = self.event_bus.get_events_of_type(UserCreatedEvent)
        assert len(events) == 1
        assert events[0].email == 'test@example.com'

    def test_create_user_sends_welcome_email(self):
        """Se debe enviar email de bienvenida."""
        command = self._make_command()
        self.use_case.execute(command)

        assert len(self.notification_service.sent_emails) == 1
        assert self.notification_service.sent_emails[0][0] == 'welcome'
        assert self.notification_service.sent_emails[0][1] == 'test@example.com'

    def test_create_duplicate_user_raises_error(self):
        """No se puede crear dos usuarios con el mismo email."""
        self.repository = FakeUserRepository(existing_emails=['test@example.com'])
        self.use_case = CreateUserUseCase(
            user_repository=self.repository,
            event_bus=self.event_bus,
            notification_service=self.notification_service,
            password_hasher=self.password_hasher,
        )

        command = self._make_command(email='test@example.com')
        with pytest.raises(UserAlreadyExistsError):
            self.use_case.execute(command)

    def test_password_is_hashed(self):
        """La contraseña debe guardarse hasheada, nunca en texto plano."""
        command = self._make_command()
        response = self.use_case.execute(command)

        saved_user = self.repository.find_by_id(response.id)
        assert saved_user.password_hash == 'hashed:SecurePass123'
        assert 'SecurePass123' not in saved_user.password_hash  # No texto plano
