"""
============================================================
TESTS DE USE CASES - Con mocks/fakes
============================================================
Testea los use cases sin BD real.
Usa implementaciones fake de los puertos (repositorios, servicios).
============================================================
"""

import pytest
from apps.users.application.use_cases.register_user import RegisterUserUseCase, UserAlreadyExistsError
from apps.users.application.dtos.user_dtos import RegisterUserDTO
from shared.infrastructure.messaging.event_publisher import InMemoryEventPublisher


class FakeUserRepository:
    """Repositorio en memoria para tests. No necesita BD."""

    def __init__(self):
        self._users = {}

    def save(self, user):
        self._users[user.id] = user
        return user

    def find_by_id(self, user_id):
        return self._users.get(user_id)

    def find_by_email(self, email):
        for user in self._users.values():
            if str(user.email) == str(email):
                return user
        return None

    def find_all(self, offset=0, limit=20):
        return list(self._users.values())[offset:offset + limit]

    def delete(self, user_id):
        self._users.pop(user_id, None)

    def exists_by_email(self, email):
        return self.find_by_email(email) is not None

    def count(self):
        return len(self._users)


class FakePasswordService:
    """Servicio de passwords fake para tests."""

    def hash(self, plain_password):
        return f"hashed:{plain_password}"

    def verify(self, plain_password, hashed_password):
        return hashed_password == f"hashed:{plain_password}"


class TestRegisterUserUseCase:
    """Tests del caso de uso de registro."""

    @pytest.fixture
    def use_case(self):
        return RegisterUserUseCase(
            user_repository=FakeUserRepository(),
            password_service=FakePasswordService(),
            event_publisher=InMemoryEventPublisher(),
        )

    def test_register_user_successfully(self, use_case):
        dto = RegisterUserDTO(
            name="Ana García",
            email="ana@test.com",
            password="Secure@123",
        )
        result = use_case.execute(dto)

        assert result.id is not None
        assert result.email == "ana@test.com"
        assert result.name == "Ana García"
        assert result.status == "pending_verification"

    def test_register_duplicate_email_raises_error(self, use_case):
        dto = RegisterUserDTO(
            name="Ana García",
            email="ana@test.com",
            password="Secure@123",
        )
        use_case.execute(dto)  # Primer registro

        with pytest.raises(UserAlreadyExistsError):
            use_case.execute(dto)  # Segundo registro con mismo email

    def test_register_publishes_domain_event(self):
        publisher = InMemoryEventPublisher()
        use_case = RegisterUserUseCase(
            user_repository=FakeUserRepository(),
            password_service=FakePasswordService(),
            event_publisher=publisher,
        )
        dto = RegisterUserDTO(
            name="Ana García",
            email="ana@test.com",
            password="Secure@123",
        )
        use_case.execute(dto)

        events = publisher.get_events_by_type("user.registered")
        assert len(events) == 1
        assert events[0].payload['email'] == "ana@test.com"

    def test_weak_password_raises_error(self, use_case):
        dto = RegisterUserDTO(
            name="Ana García",
            email="ana@test.com",
            password="weak",  # Sin mayúscula, número, símbolo
        )
        with pytest.raises(ValueError):
            use_case.execute(dto)
