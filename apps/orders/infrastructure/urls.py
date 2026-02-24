"""URLs del contexto de órdenes."""
from django.urls import path
from apps.orders.infrastructure.views import OrderListCreateView, OrderDetailView, OrderActionView

urlpatterns = [
    path('', OrderListCreateView.as_view(), name='order-list-create'),
    path('<uuid:order_id>/', OrderDetailView.as_view(), name='order-detail'),
    path('<uuid:order_id>/actions/<str:action>/', OrderActionView.as_view(), name='order-action'),
]
