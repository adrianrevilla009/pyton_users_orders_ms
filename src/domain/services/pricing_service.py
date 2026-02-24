"""
=============================================================================
SERVICIO DE DOMINIO: PricingService
=============================================================================

Los Servicios de Dominio contienen lógica que NO pertenece naturalmente
a una sola entidad — generalmente porque involucra múltiples entidades.

Regla: si una operación necesita más de una entidad/VO para realizarse,
probablemente es un servicio de dominio.

PricingService calcula precios finales considerando:
- Descuentos por volumen
- Descuentos por rol de usuario (sellers tienen descuento en su propio catálogo)
- Impuestos por país
"""
from decimal import Decimal
from src.domain.entities.product import Product
from src.domain.entities.user import User, UserRole
from src.domain.value_objects.money import Money


class PricingService:
    """
    Servicio de dominio para cálculo de precios.
    Stateless — no guarda estado entre llamadas.
    """

    # Descuentos por volumen (número de unidades → porcentaje de descuento)
    VOLUME_DISCOUNTS = {
        10: Decimal('5'),    # 5% desde 10 unidades
        25: Decimal('10'),   # 10% desde 25 unidades
        50: Decimal('15'),   # 15% desde 50 unidades
        100: Decimal('20'),  # 20% desde 100 unidades
    }

    # IVA por país (simplificado)
    TAX_RATES = {
        'ES': Decimal('21'),   # España: IVA 21%
        'DE': Decimal('19'),   # Alemania: MwSt 19%
        'FR': Decimal('20'),   # Francia: TVA 20%
        'GB': Decimal('20'),   # Reino Unido: VAT 20%
        'US': Decimal('0'),    # USA: calculado por estado (simplificamos)
    }

    def calculate_unit_price(
        self,
        product: Product,
        buyer: User,
        quantity: int,
        country: str = 'ES',
    ) -> Money:
        """
        Calcula el precio final por unidad para una compra específica.
        Aplica: descuentos por volumen + descuentos por rol + impuestos.
        """
        base_price = product.price

        # 1. Descuento por volumen
        volume_discount = self._get_volume_discount(quantity)

        # 2. Descuento por rol (los sellers no pagan comisión en sus propios productos)
        role_discount = self._get_role_discount(buyer, product)

        # 3. Descuento total (no acumulativo — se aplica el mayor)
        total_discount = max(volume_discount, role_discount)

        # 4. Aplicar descuento
        discounted_price = base_price.multiply(1 - total_discount / 100) if total_discount else base_price

        # 5. Aplicar impuestos
        tax_rate = self.TAX_RATES.get(country.upper(), Decimal('21'))
        final_price = discounted_price.multiply(1 + tax_rate / 100)

        return final_price

    def _get_volume_discount(self, quantity: int) -> Decimal:
        """Retorna el porcentaje de descuento por volumen."""
        discount = Decimal('0')
        for min_qty, pct in sorted(self.VOLUME_DISCOUNTS.items()):
            if quantity >= min_qty:
                discount = pct
        return discount

    def _get_role_discount(self, buyer: User, product: Product) -> Decimal:
        """Descuentos especiales por rol."""
        if buyer.role == UserRole.ADMIN:
            return Decimal('10')  # Los admin tienen 10% de descuento
        # Los sellers tienen descuento en sus propias compras
        if buyer.role == UserRole.SELLER and buyer.id == product.seller_id:
            return Decimal('5')
        return Decimal('0')
