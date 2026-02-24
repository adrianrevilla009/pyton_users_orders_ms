"""
============================================================
TESTS UNITARIOS DEL DOMINIO
============================================================

Los tests del dominio son los más importantes y los más fáciles
de escribir: no necesitan Django, ni BD, ni mocks de infra.

Principios de testing:
- AAA: Arrange, Act, Assert
- Un solo concepto por test
- Tests rápidos (< 1ms cada uno)
- Nombres descriptivos: test_CUANDO_hace_ALGO_entonces_RESULTADO

Herramientas:
- pytest: runner
- factory-boy: factories para crear objetos de prueba
- faker: datos falsos
============================================================
"""

import uuid
import pytest
from datetime import datetime

from domain.users.user import (
    User, Email, Money, Address, UserRole, UserStatus,
    EmailAlreadyExistsError, UserNotFoundError
)
from domain.orders.order import (
    Order, OrderLine, OrderStatus, Money, ProductId, OrderNumber,
    PaymentMethod
)
from domain.base import DomainException


# ─── Tests de Value Objects ───────────────────────────────────

class TestEmail:
    """Tests del Value Object Email."""

    def test_email_valido_crea_instancia_correctamente(self):
        # Arrange & Act
        email = Email("usuario@example.com")
        # Assert
        assert str(email) == "usuario@example.com"

    def test_email_se_normaliza_a_minusculas(self):
        email = Email("USUARIO@EXAMPLE.COM")
        assert str(email) == "usuario@example.com"

    def test_email_invalido_lanza_excepcion_de_dominio(self):
        with pytest.raises(DomainException) as exc_info:
            Email("no-es-un-email")
        assert exc_info.value.code == "INVALID_EMAIL"

    def test_email_sin_arroba_es_invalido(self):
        with pytest.raises(DomainException):
            Email("usuariosindominio")

    def test_dos_emails_iguales_son_iguales(self):
        email1 = Email("a@b.com")
        email2 = Email("a@b.com")
        assert email1 == email2

    def test_dos_emails_distintos_son_distintos(self):
        email1 = Email("a@b.com")
        email2 = Email("c@d.com")
        assert email1 != email2

    def test_email_extrae_dominio_correctamente(self):
        email = Email("user@gmail.com")
        assert email.domain == "gmail.com"


class TestMoney:
    """Tests del Value Object Money."""

    def test_money_se_crea_con_centimos_y_moneda(self):
        money = Money(1000, "EUR")
        assert money.amount_cents == 1000
        assert money.currency == "EUR"
        assert money.amount == 10.00

    def test_money_negativo_lanza_excepcion(self):
        with pytest.raises(DomainException) as exc_info:
            Money(-100, "EUR")
        assert exc_info.value.code == "INVALID_MONEY"

    def test_suma_de_dos_money_misma_moneda(self):
        m1 = Money(1000, "EUR")
        m2 = Money(500, "EUR")
        result = m1 + m2
        assert result.amount_cents == 1500
        assert result.currency == "EUR"

    def test_suma_monedas_distintas_lanza_excepcion(self):
        m1 = Money(1000, "EUR")
        m2 = Money(500, "USD")
        with pytest.raises(DomainException) as exc_info:
            m1 + m2
        assert exc_info.value.code == "CURRENCY_MISMATCH"

    def test_multiplicacion_por_escalar(self):
        money = Money(100, "EUR")
        result = money * 3
        assert result.amount_cents == 300

    def test_moneda_se_normaliza_a_mayusculas(self):
        money = Money(100, "eur")
        assert money.currency == "EUR"

    def test_money_es_inmutable(self):
        money = Money(100, "EUR")
        with pytest.raises(Exception):
            money.amount_cents = 200


# ─── Tests de Entidades ───────────────────────────────────────

class TestUser:
    """Tests de la entidad de dominio User."""

    def _make_user(self, role: UserRole = UserRole.CUSTOMER) -> User:
        """Factory helper para crear usuarios de test."""
        return User(
            email=Email(f"test_{uuid.uuid4().hex[:6]}@example.com"),
            role=role,
            first_name="Test",
            last_name="User",
        )

    def test_usuario_nuevo_tiene_estado_pending_verification(self):
        user = self._make_user()
        assert user.status == UserStatus.PENDING_VERIFICATION

    def test_usuario_nuevo_genera_evento_user_registered(self):
        user = self._make_user()
        events = user.pull_events()
        assert len(events) == 1
        assert events[0].event_type == "UserRegistered"

    def test_verificar_email_cambia_estado_a_activo(self):
        user = self._make_user()
        user.verify_email()
        assert user.status == UserStatus.ACTIVE

    def test_verificar_email_dos_veces_lanza_excepcion(self):
        user = self._make_user()
        user.verify_email()
        with pytest.raises(DomainException) as exc_info:
            user.verify_email()
        assert exc_info.value.code == "EMAIL_ALREADY_VERIFIED"

    def test_verificar_email_genera_evento_domain(self):
        user = self._make_user()
        user.pull_events()  # Limpiar evento de registro
        user.verify_email()
        events = user.pull_events()
        assert len(events) == 1
        assert events[0].event_type == "UserEmailVerified"

    def test_usuario_activo_puede_crear_pedidos(self):
        user = self._make_user()
        user.verify_email()  # Activar
        assert user.can_create_orders is True

    def test_usuario_pendiente_no_puede_crear_pedidos(self):
        user = self._make_user()
        # Sin verificar email
        assert user.can_create_orders is False

    def test_cambiar_rol_por_admin(self):
        admin = self._make_user(UserRole.ADMIN)
        user = self._make_user(UserRole.CUSTOMER)

        user.change_role(UserRole.MANAGER, changed_by=admin)

        assert user.role == UserRole.MANAGER

    def test_admin_no_puede_asignar_super_admin(self):
        admin = self._make_user(UserRole.ADMIN)
        user = self._make_user(UserRole.CUSTOMER)

        with pytest.raises(DomainException) as exc_info:
            user.change_role(UserRole.SUPER_ADMIN, changed_by=admin)
        assert exc_info.value.code == "INSUFFICIENT_PERMISSIONS"

    def test_super_admin_puede_asignar_super_admin(self):
        super_admin = self._make_user(UserRole.SUPER_ADMIN)
        user = self._make_user(UserRole.CUSTOMER)

        user.change_role(UserRole.SUPER_ADMIN, changed_by=super_admin)

        assert user.role == UserRole.SUPER_ADMIN

    def test_suspender_usuario(self):
        admin = self._make_user(UserRole.ADMIN)
        user = self._make_user()

        user.suspend("Comportamiento inapropiado", suspended_by=admin)

        assert user.status == UserStatus.SUSPENDED

    def test_no_puede_suspenderse_a_si_mismo(self):
        user = self._make_user(UserRole.ADMIN)

        with pytest.raises(DomainException) as exc_info:
            user.suspend("Auto-suspensión", suspended_by=user)
        assert exc_info.value.code == "SELF_SUSPENSION_NOT_ALLOWED"

    def test_usuario_suspendido_no_puede_hacer_login(self):
        admin = self._make_user(UserRole.ADMIN)
        user = self._make_user()
        user.suspend("Test", suspended_by=admin)

        with pytest.raises(DomainException) as exc_info:
            user.record_login()
        assert exc_info.value.code == "USER_SUSPENDED"


# ─── Tests del Agregado Order ─────────────────────────────────

class TestOrder:
    """Tests del Agregado Order."""

    def _make_address(self) -> Address:
        return Address(
            street="Calle Mayor 1",
            city="Madrid",
            postal_code="28001",
            country="ES",
        )

    def _make_order(self) -> Order:
        return Order(
            user_id=uuid.uuid4(),
            shipping_address=self._make_address(),
            order_number=OrderNumber("ORD-2024-000001"),
        )

    def _make_product_id(self) -> ProductId:
        return ProductId(uuid.uuid4())

    def test_pedido_nuevo_tiene_estado_draft(self):
        order = self._make_order()
        assert order.status == OrderStatus.DRAFT

    def test_añadir_linea_incrementa_total(self):
        order = self._make_order()
        product_id = self._make_product_id()

        order.add_line(
            product_id=product_id,
            product_name="Producto A",
            unit_price=Money(1000, "EUR"),
            quantity=2,
        )

        assert order.total.amount_cents == 2000
        assert order.item_count == 2

    def test_añadir_mismo_producto_dos_veces_acumula_cantidad(self):
        order = self._make_order()
        product_id = self._make_product_id()

        order.add_line(product_id, "Producto A", Money(1000, "EUR"), 1)
        order.add_line(product_id, "Producto A", Money(1000, "EUR"), 2)

        assert len(order.lines) == 1  # Solo una línea
        assert order.lines[0].quantity == 3  # Con cantidad acumulada

    def test_confirmar_pedido_vacio_lanza_excepcion(self):
        order = self._make_order()

        with pytest.raises(DomainException) as exc_info:
            order.confirm()
        assert exc_info.value.code == "EMPTY_ORDER"

    def test_confirmar_pedido_con_lineas_cambia_estado(self):
        order = self._make_order()
        order.add_line(self._make_product_id(), "Producto", Money(1000, "EUR"), 1)
        order.confirm()

        assert order.status == OrderStatus.PENDING_PAYMENT

    def test_confirmar_pedido_genera_evento_order_placed(self):
        order = self._make_order()
        order.add_line(self._make_product_id(), "Producto", Money(1000, "EUR"), 1)
        order.confirm()

        events = order.pull_events()
        assert any(e.event_type == "OrderPlaced" for e in events)

    def test_no_se_pueden_añadir_lineas_despues_de_confirmar(self):
        order = self._make_order()
        order.add_line(self._make_product_id(), "Producto", Money(1000, "EUR"), 1)
        order.confirm()

        with pytest.raises(DomainException) as exc_info:
            order.add_line(self._make_product_id(), "Otro", Money(500, "EUR"), 1)
        assert exc_info.value.code == "ORDER_NOT_EDITABLE"

    def test_cancelar_pedido_en_draft(self):
        order = self._make_order()
        order.add_line(self._make_product_id(), "Producto", Money(1000, "EUR"), 1)
        order.cancel(reason="El cliente cambió de opinión")

        assert order.status == OrderStatus.CANCELLED

    def test_no_se_puede_cancelar_pedido_enviado(self):
        order = self._make_order()
        order.add_line(self._make_product_id(), "Producto", Money(1000, "EUR"), 1)
        order.confirm()
        order.mark_as_paid(transaction_id="tx_123")
        order.ship(tracking_number="TRACK123")

        with pytest.raises(DomainException) as exc_info:
            order.cancel(reason="Demasiado tarde")
        assert exc_info.value.code == "ORDER_CANNOT_BE_CANCELLED"

    def test_flujo_completo_pedido(self):
        """Test de integración del agregado: draft → paid → shipped → delivered."""
        order = self._make_order()

        # Añadir productos
        order.add_line(self._make_product_id(), "Laptop", Money(100000, "EUR"), 1)
        order.add_line(self._make_product_id(), "Mouse", Money(2500, "EUR"), 2)

        assert order.total.amount_cents == 105000  # 1000 + 50 = 1050€

        # Confirmar
        order.confirm()
        assert order.status == OrderStatus.PENDING_PAYMENT

        # Pagar
        order.mark_as_paid(transaction_id="stripe_pi_123")
        assert order.status == OrderStatus.PAID

        # Enviar
        order.ship(tracking_number="DHL-ABC123")
        assert order.status == OrderStatus.SHIPPED

        # Entregar
        order.deliver()
        assert order.status == OrderStatus.DELIVERED

        # Verificar eventos
        events = order.pull_events()
        event_types = {e.event_type for e in events}
        assert "OrderPlaced" in event_types
        assert "PaymentProcessed" in event_types
        assert "OrderShipped" in event_types
