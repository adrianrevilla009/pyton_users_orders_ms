"""
============================================================
ORDER VIEWS - Vistas del contexto de órdenes
============================================================
Implementa RESTful endpoints para gestión de pedidos.
Demuestra permisos por rol y acceso a recursos propios.
============================================================
"""

import structlog
from decimal import Decimal
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.orders.domain.entities.order import Order
from apps.orders.infrastructure.models.order_model import OrderModel, OrderItemModel

logger = structlog.get_logger(__name__)


class OrderListCreateView(APIView):
    """GET /api/v1/orders/ - Lista pedidos del usuario. POST - Crea pedido."""
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Pedidos'], summary='Listar pedidos del usuario')
    def get(self, request):
        """Lista los pedidos del usuario autenticado."""
        orders = OrderModel.objects.filter(
            user=request.user
        ).prefetch_related('items').order_by('-created_at')

        return Response({
            'count': orders.count(),
            'results': [self._serialize_order(o) for o in orders]
        })

    @extend_schema(tags=['Pedidos'], summary='Crear nuevo pedido')
    def post(self, request):
        """Crea un nuevo pedido en estado DRAFT."""
        notes = request.data.get('notes', '')
        items_data = request.data.get('items', [])

        # Crear entidad de dominio
        order = Order.create(user_id=str(request.user.id), notes=notes)

        # Añadir items via dominio (valida invariantes)
        for item in items_data:
            try:
                order.add_item(
                    product_id=item['product_id'],
                    product_name=item['product_name'],
                    unit_price=Decimal(str(item['unit_price'])),
                    quantity=int(item['quantity']),
                )
            except (KeyError, ValueError) as e:
                return Response({'error': f"Item inválido: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        # Persistir
        order_model = OrderModel.objects.create(
            id=order.id,
            user=request.user,
            status=order.status.value,
            notes=order.notes if hasattr(order, 'notes') else notes,
            total_amount=order.total,
        )

        for item in order.items:
            OrderItemModel.objects.create(
                id=item.item_id,
                order=order_model,
                product_id=item.product_id,
                product_name=item.product_name,
                unit_price=item.unit_price,
                quantity=item.quantity,
            )

        logger.info("Pedido creado", order_id=order.id, user_id=str(request.user.id))

        return Response(self._serialize_order(order_model), status=status.HTTP_201_CREATED)

    def _serialize_order(self, order_model: OrderModel) -> dict:
        return {
            'id': str(order_model.id),
            'status': order_model.status,
            'total_amount': str(order_model.total_amount),
            'created_at': order_model.created_at.isoformat(),
            'items': [
                {
                    'id': str(i.id),
                    'product_name': i.product_name,
                    'unit_price': str(i.unit_price),
                    'quantity': i.quantity,
                    'total': str(i.total_price),
                }
                for i in order_model.items.all()
            ]
        }


class OrderDetailView(APIView):
    """GET /api/v1/orders/{id}/ - Detalle de pedido."""
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = OrderModel.objects.prefetch_related('items').get(
                id=order_id,
                user=request.user  # El usuario solo ve sus pedidos
            )
        except OrderModel.DoesNotExist:
            return Response({'error': 'Pedido no encontrado'}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'id': str(order.id),
            'status': order.status,
            'total_amount': str(order.total_amount),
            'shipping_address': order.shipping_address,
            'tracking_code': order.tracking_code,
            'notes': order.notes,
            'created_at': order.created_at.isoformat(),
            'updated_at': order.updated_at.isoformat(),
            'items': [
                {
                    'product_name': i.product_name,
                    'unit_price': str(i.unit_price),
                    'quantity': i.quantity,
                }
                for i in order.items.all()
            ]
        })


class OrderActionView(APIView):
    """
    POST /api/v1/orders/{id}/actions/{action}/
    
    Implementa el patrón de acciones para transiciones de estado.
    Más RESTful que endpoints como /confirm, /ship, etc.
    
    Acciones: confirm, cancel, pay, ship, deliver
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id, action):
        try:
            order_model = OrderModel.objects.prefetch_related('items').get(
                id=order_id,
                user=request.user,
            )
        except OrderModel.DoesNotExist:
            return Response({'error': 'Pedido no encontrado'}, status=status.HTTP_404_NOT_FOUND)

        # Reconstruir entidad de dominio desde modelo
        from apps.orders.domain.entities.order import Order as DomainOrder, OrderStatus, OrderItem
        domain_order = self._to_domain(order_model)

        # Ejecutar la acción en el dominio
        try:
            if action == 'confirm':
                shipping_address = request.data.get('shipping_address', '')
                domain_order.confirm(shipping_address)
            elif action == 'cancel':
                reason = request.data.get('reason', '')
                domain_order.cancel(reason)
            elif action == 'pay':
                domain_order.mark_as_paid()
            elif action == 'process':
                domain_order.start_processing()
            elif action == 'ship':
                tracking = request.data.get('tracking_code', '')
                domain_order.ship(tracking)
            elif action == 'deliver':
                domain_order.deliver()
            else:
                return Response({'error': f"Acción desconocida: {action}"}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # Actualizar modelo
        order_model.status = domain_order.status.value
        order_model.shipping_address = domain_order.shipping_address
        order_model.tracking_code = domain_order.tracking_code
        order_model.save()

        logger.info("Acción ejecutada en pedido", order_id=str(order_id), action=action, new_status=order_model.status)

        return Response({'status': order_model.status, 'message': f"Acción '{action}' ejecutada"})

    def _to_domain(self, model: OrderModel):
        from apps.orders.domain.entities.order import Order, OrderStatus, OrderItem
        from decimal import Decimal

        order = Order(user_id=str(model.user_id), entity_id=str(model.id))
        object.__setattr__(order, '_status', OrderStatus(model.status))
        object.__setattr__(order, '_shipping_address', model.shipping_address)
        object.__setattr__(order, '_tracking_code', model.tracking_code)

        items = []
        for item in model.items.all():
            items.append(OrderItem(
                product_id=item.product_id,
                product_name=item.product_name,
                unit_price=item.unit_price,
                quantity=item.quantity,
                item_id=str(item.id),
            ))
        object.__setattr__(order, '_items', items)
        return order
