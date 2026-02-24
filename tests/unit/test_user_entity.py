"""
============================================================
TESTS UNITARIOS - Entidad de dominio User
============================================================
Tests del dominio puro: no necesitan BD, no necesitan Django.
Son los tests más rápidos y los más importantes.

Verifican las REGLAS DE NEGOCIO del dominio.

Ejecutar: pytest tests/unit/ -v
============================================================
"""

import pytest
from apps.users.domain.entities.user import User, UserRole, UserStatus
from apps.users.domain.value_objects.email import UserEmail
from apps.users.domain.value_objects.password import HashedPassword


class TestUserCreation:
    """Tests de creación de usuarios."""

    def test_create_user_generates_id(self):
        user = User.create("Ana García", "ana@test.com", "hashed_password_123!")
        assert user.id is not None
        assert len(user.id) > 0

    def test_new_user_has_pending_status(self):
        user = User.create("Ana García", "ana@test.com", "hashed_password_123!")
        assert user.status == UserStatus.PENDING_VERIFICATION

    def test_new_user_has_customer_role_by_default(self):
        user = User.create("Ana García", "ana@test.com", "hashed_password_123!")
        assert user.role == UserRole.CUSTOMER

    def test_create_user_records_domain_event(self):
        user = User.create("Ana García", "ana@test.com", "hashed_password_123!")
        events = user.pull_domain_events()
        assert len(events) == 1
        assert events[0].event_type == "user.registered"
        assert events[0].payload['email'] == "ana@test.com"

    def test_pulling_events_clears_them(self):
        user = User.create("Ana García", "ana@test.com", "hashed_password_123!")
        user.pull_domain_events()  # Primera vez
        events = user.pull_domain_events()  # Segunda vez
        assert len(events) == 0

    def test_invalid_email_raises_error(self):
        with pytest.raises(ValueError):
            User.create("Ana García", "not-an-email", "hashed_password_123!")


class TestUserLifecycle:
    """Tests del ciclo de vida del usuario."""

    @pytest.fixture
    def pending_user(self):
        return User.create("Ana García", "ana@test.com", "hashed_password_123!")

    @pytest.fixture
    def active_user(self, pending_user):
        pending_user.verify_email()
        pending_user.pull_domain_events()  # Limpiar eventos
        return pending_user

    def test_verify_email_activates_user(self, pending_user):
        pending_user.verify_email()
        assert pending_user.status == UserStatus.ACTIVE
        assert pending_user.is_active

    def test_cannot_verify_email_twice(self, pending_user):
        pending_user.verify_email()
        with pytest.raises(ValueError, match="No se puede verificar"):
            pending_user.verify_email()

    def test_suspend_active_user(self, active_user):
        active_user.suspend("Violación de términos de uso")
        assert active_user.status == UserStatus.SUSPENDED
        events = active_user.pull_domain_events()
        assert any(e.event_type == "user.suspended" for e in events)

    def test_cannot_suspend_pending_user(self, pending_user):
        with pytest.raises(ValueError, match="Solo se pueden suspender"):
            pending_user.suspend("Razón cualquiera")

    def test_suspend_requires_reason(self, active_user):
        with pytest.raises(ValueError):
            active_user.suspend("ab")  # Muy corto

    def test_reactivate_suspended_user(self, active_user):
        active_user.suspend("Razón de prueba")
        active_user.reactivate()
        assert active_user.status == UserStatus.ACTIVE

    def test_change_role(self, active_user):
        active_user.change_role(UserRole.ADMIN)
        assert active_user.role == UserRole.ADMIN

    def test_cannot_change_role_of_inactive_user(self, pending_user):
        with pytest.raises(ValueError):
            pending_user.change_role(UserRole.ADMIN)


class TestUserPermissions:
    """Tests del sistema de roles/permisos."""

    def test_admin_has_all_permissions(self):
        user = User.create("Admin", "admin@test.com", "hashed_password_123!")
        object.__setattr__(user, '_status', UserStatus.ACTIVE)
        user.change_role(UserRole.ADMIN)
        assert user.has_role(UserRole.ADMIN)
        assert user.has_role(UserRole.MANAGER)
        assert user.has_role(UserRole.CUSTOMER)
        assert user.has_role(UserRole.READONLY)

    def test_customer_cannot_access_admin(self):
        user = User.create("Customer", "cust@test.com", "hashed_password_123!")
        object.__setattr__(user, '_status', UserStatus.ACTIVE)
        assert not user.has_role(UserRole.ADMIN)
        assert not user.has_role(UserRole.MANAGER)
        assert user.has_role(UserRole.CUSTOMER)

    def test_two_users_with_same_id_are_equal(self):
        user1 = User(
            name="Ana",
            email=UserEmail("ana@test.com"),
            hashed_password=HashedPassword("hash123456"),
            entity_id="same-id"
        )
        user2 = User(
            name="Ana Modificada",  # Nombre diferente
            email=UserEmail("ana@test.com"),
            hashed_password=HashedPassword("hash123456"),
            entity_id="same-id"  # Mismo ID
        )
        # En DDD, entidades con el mismo ID son iguales
        assert user1 == user2


class TestOrderEntity:
    """Tests del aggregate Order."""

    def test_create_order_with_items(self):
        from apps.orders.domain.entities.order import Order
        from decimal import Decimal

        order = Order.create(user_id="user-123")
        order.add_item("prod-1", "Laptop", Decimal("999.99"), 1)
        order.add_item("prod-2", "Mouse", Decimal("29.99"), 2)

        assert order.item_count == 2
        assert order.total == Decimal("1059.97")

    def test_cannot_confirm_empty_order(self):
        from apps.orders.domain.entities.order import Order

        order = Order.create(user_id="user-123")
        with pytest.raises(ValueError, match="vacío"):
            order.confirm("Calle Falsa 123")

    def test_state_machine_prevents_invalid_transitions(self):
        from apps.orders.domain.entities.order import Order
        from decimal import Decimal

        order = Order.create(user_id="user-123")
        order.add_item("prod-1", "Laptop", Decimal("999.99"), 1)
        order.confirm("Calle Falsa 123")

        # No se puede confirmar dos veces
        with pytest.raises(ValueError, match="Transición inválida"):
            order.confirm("Otra dirección")

    def test_total_calculated_from_items(self):
        from apps.orders.domain.entities.order import Order
        from decimal import Decimal

        order = Order.create(user_id="user-123")
        order.add_item("prod-1", "Item A", Decimal("10.00"), 3)  # 30
        order.add_item("prod-2", "Item B", Decimal("5.50"), 2)   # 11

        assert order.total == Decimal("41.00")
