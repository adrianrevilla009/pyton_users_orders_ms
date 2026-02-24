"""
=============================================================================
CASO DE USO: CreateOrder
=============================================================================

Orquesta la creación de un pedido:
1. Validar que los productos existen y tienen stock
2. Calcular precios con el servicio de dominio
3. Crear la entidad Order
4. Reducir el stock de cada producto (transaccional)
5. Persistir el pedido
6. Publicar eventos
7. Notificar al comprador
"""
import uuid
import structlog
from src.domain.entities.order import Order
from src.domain.repositories.order_repository import OrderRepository
from src.domain.repositories.product_repository import ProductRepository
from src.domain.repositories.user_repository import UserRepository
from src.domain.services.pricing_service import PricingService
from src.domain.value_objects.address import Address
from src.application.dtos.order_dtos import CreateOrderCommand, OrderResponse
from src.application.ports.event_bus import EventBus
from src.application.ports.notification_service import NotificationService

logger = structlog.get_logger(__name__)


class InsufficientStockError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


class CreateOrderUseCase:
    """Caso de uso: Crear un pedido nuevo."""

    def __init__(
        self,
        order_repository: OrderRepository,
        product_repository: ProductRepository,
        user_repository: UserRepository,
        pricing_service: PricingService,
        event_bus: EventBus,
        notification_service: NotificationService,
    ):
        self.order_repository = order_repository
        self.product_repository = product_repository
        self.user_repository = user_repository
        self.pricing_service = pricing_service
        self.event_bus = event_bus
        self.notification_service = notification_service

    def execute(self, command: CreateOrderCommand, buyer_id: uuid.UUID) -> OrderResponse:
        log = logger.bind(buyer_id=str(buyer_id), item_count=len(command.items))
        log.info("creating_order")

        # 1. Obtener el comprador
        buyer = self.user_repository.find_by_id(buyer_id)
        if not buyer:
            raise ValueError(f"Usuario no encontrado: {buyer_id}")

        # 2. Validar y recopilar productos
        items_data = []
        products_to_update = []

        for item_cmd in command.items:
            product = self.product_repository.find_by_id(item_cmd.product_id)
            if not product:
                raise ProductNotFoundError(f"Producto no encontrado: {item_cmd.product_id}")

            if not product.is_available():
                raise InsufficientStockError(
                    f"Producto no disponible: {product.name} (estado: {product.status.value})"
                )

            if product.stock < item_cmd.quantity:
                raise InsufficientStockError(
                    f"Stock insuficiente para {product.name}: "
                    f"disponible={product.stock}, solicitado={item_cmd.quantity}"
                )

            # Calcular precio con el servicio de dominio
            final_price = self.pricing_service.calculate_unit_price(
                product=product,
                buyer=buyer,
                quantity=item_cmd.quantity,
                country=command.shipping_country,
            )

            items_data.append({
                'product_id': str(product.id),
                'name': product.name,
                'price': str(final_price.amount),
                'currency': final_price.currency,
                'quantity': item_cmd.quantity,
            })

            # Reducir stock (en memoria, se persistirá después)
            product.reduce_stock(item_cmd.quantity)
            products_to_update.append(product)

        # 3. Construir dirección de envío
        shipping_address = Address(
            street=command.shipping_street,
            city=command.shipping_city,
            postal_code=command.shipping_postal_code,
            country=command.shipping_country,
            state=command.shipping_state,
        )

        # 4. Crear el aggregate Order
        order = Order.create(
            buyer_id=buyer_id,
            items_data=items_data,
            shipping_address=shipping_address,
        )
        order.confirm()  # Auto-confirmar en este flujo simplificado

        # 5. Persistir todo (idealmente en una transacción)
        # En producción usaríamos Unit of Work pattern
        for product in products_to_update:
            self.product_repository.save(product)

        saved_order = self.order_repository.save(order)

        # 6. Publicar eventos
        events = saved_order.pull_domain_events()
        self.event_bus.publish_many(events)

        # 7. Notificar
        self.notification_service.send_order_confirmation(
            to_email=str(buyer.email),
            order_id=str(saved_order.id),
            total=str(saved_order.total),
        )

        log.info("order_created", order_id=str(saved_order.id), total=str(saved_order.total))

        return self._to_response(saved_order)

    def _to_response(self, order: Order) -> OrderResponse:
        """Mapea la entidad de dominio al DTO de respuesta."""
        return OrderResponse(
            id=order.id,
            buyer_id=order.buyer_id,
            items=[
                {
                    'id': item.id,
                    'product_id': item.product_id,
                    'product_name': item.product_name,
                    'unit_price': item.unit_price.amount,
                    'currency': item.unit_price.currency,
                    'quantity': item.quantity,
                    'subtotal': item.subtotal.amount,
                }
                for item in order.items
            ],
            total_amount=order.total.amount,
            currency=order.total.currency,
            status=order.status.value,
            shipping_address=str(order.shipping_address),
            created_at=order.created_at,
        )
