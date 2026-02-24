"""
=============================================================================
PUERTO: NotificationService
=============================================================================

Interface para envío de notificaciones.
Implementación concreta: SendGrid (en infraestructura).
"""
from abc import ABC, abstractmethod


class NotificationService(ABC):
    """Puerto de salida para notificaciones."""

    @abstractmethod
    def send_welcome_email(self, to_email: str, user_name: str) -> None:
        ...

    @abstractmethod
    def send_order_confirmation(self, to_email: str, order_id: str, total: str) -> None:
        ...

    @abstractmethod
    def send_payment_confirmation(self, to_email: str, order_id: str, amount: str) -> None:
        ...

    @abstractmethod
    def send_password_reset(self, to_email: str, reset_token: str) -> None:
        ...
