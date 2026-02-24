"""
============================================================
INFRAESTRUCTURA - INTEGRACIONES CON APIs EXTERNAS
============================================================

Aquí viven todas las integraciones con servicios externos.
Cada integración sigue el mismo patrón:
1. Interface (Puerto) en la capa de aplicación
2. Implementación concreta aquí en infraestructura

Principios:
- Timeout en todas las llamadas (nunca dejes colgado el hilo)
- Reintentos con backoff exponencial para errores transitorios
- Circuit Breaker para evitar cascada de fallos
- Logging de todas las llamadas (entrada/salida/error)
- No exponer detalles de la API externa al dominio

APIs integradas:
- Stripe: procesamiento de pagos
- OpenWeather: datos meteorológicos (ejemplo de API de consulta)
- AWS S3: almacenamiento de archivos
============================================================
"""

import json
import time
import functools
from typing import Optional, Dict, Any, Callable

import httpx
import structlog
from django.conf import settings

logger = structlog.get_logger(__name__)


# ─── Circuit Breaker ──────────────────────────────────────────

class CircuitBreaker:
    """
    Implementación básica del patrón Circuit Breaker.
    
    Previene que fallos en servicios externos colapsen el sistema.
    
    Estados:
    - CLOSED: funcionando normalmente (peticiones pasan)
    - OPEN: demasiados fallos (peticiones bloqueadas durante timeout)
    - HALF-OPEN: probando si el servicio se recuperó
    
    Uso:
        breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        
        @breaker
        def call_external_api():
            ...
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,          # segundos hasta intentar de nuevo
        name: str = "unknown"
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.name = name
        self._state = self.STATE_CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None

    @property
    def state(self) -> str:
        if self._state == self.STATE_OPEN:
            if time.time() - self._last_failure_time > self.timeout:
                self._state = self.STATE_HALF_OPEN
                logger.info("circuit_breaker_half_open", name=self.name)
        return self._state

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Ejecuta la función con protección del circuit breaker."""
        if self.state == self.STATE_OPEN:
            raise ExternalServiceUnavailable(
                f"Circuit breaker abierto para {self.name}. "
                f"Servicio no disponible temporalmente."
            )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Se ejecuta cuando una llamada tiene éxito."""
        self._failure_count = 0
        if self._state == self.STATE_HALF_OPEN:
            self._state = self.STATE_CLOSED
            logger.info("circuit_breaker_closed", name=self.name)

    def _on_failure(self) -> None:
        """Se ejecuta cuando una llamada falla."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.failure_threshold:
            self._state = self.STATE_OPEN
            logger.error(
                "circuit_breaker_opened",
                name=self.name,
                failure_count=self._failure_count,
            )


class ExternalServiceUnavailable(Exception):
    """Se lanza cuando un servicio externo no está disponible."""
    pass


# ─── HTTP Client base ─────────────────────────────────────────

class BaseAPIClient:
    """
    Cliente HTTP base para integraciones con APIs externas.
    
    Provee:
    - Timeout configurable
    - Reintentos con backoff exponencial
    - Logging automático de todas las llamadas
    - Manejo consistente de errores
    
    Usamos httpx (moderno, async-compatible) en lugar de requests.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 10,          # segundos
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

        # Headers por defecto
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
        )

    def get(self, path: str, params: Optional[Dict] = None) -> Dict:
        """Hace una petición GET con reintentos."""
        return self._request("GET", path, params=params)

    def post(self, path: str, data: Dict) -> Dict:
        """Hace una petición POST con reintentos."""
        return self._request("POST", path, json=data)

    def _request(self, method: str, path: str, **kwargs) -> Dict:
        """
        Ejecuta una petición HTTP con reintentos y logging.
        
        Backoff exponencial: 1s, 2s, 4s entre reintentos.
        """
        url = f"{self.base_url}{path}"
        last_exception = None

        for attempt in range(self.max_retries):
            if attempt > 0:
                # Backoff exponencial
                wait_time = 2 ** (attempt - 1)
                logger.info(
                    "api_call_retry",
                    url=url,
                    attempt=attempt + 1,
                    wait_seconds=wait_time,
                )
                time.sleep(wait_time)

            try:
                start = time.perf_counter()
                response = self._client.request(method, path, **kwargs)
                duration = time.perf_counter() - start

                logger.info(
                    "api_call_completed",
                    method=method,
                    url=url,
                    status_code=response.status_code,
                    duration_ms=round(duration * 1000, 2),
                )

                response.raise_for_status()
                return response.json()

            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning("api_call_timeout", url=url, attempt=attempt + 1)

            except httpx.HTTPStatusError as e:
                # 4xx: no reintentamos (el problema es nuestro)
                if 400 <= e.response.status_code < 500:
                    logger.error(
                        "api_call_client_error",
                        url=url,
                        status_code=e.response.status_code,
                        body=e.response.text[:500],
                    )
                    raise APIClientError(
                        f"Error {e.response.status_code} en {url}",
                        status_code=e.response.status_code,
                        response_body=e.response.text,
                    )
                # 5xx: reintentamos
                last_exception = e
                logger.warning(
                    "api_call_server_error",
                    url=url,
                    status_code=e.response.status_code,
                    attempt=attempt + 1,
                )

            except httpx.RequestError as e:
                last_exception = e
                logger.warning("api_call_request_error", url=url, error=str(e), attempt=attempt + 1)

        logger.error("api_call_failed_all_retries", url=url, attempts=self.max_retries)
        raise APIClientError(f"Fallo después de {self.max_retries} intentos: {url}") from last_exception

    def __del__(self):
        self._client.close()


class APIClientError(Exception):
    """Error en llamada a API externa."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)


# ─── Integración con Stripe ───────────────────────────────────

class StripePaymentGateway:
    """
    Integración con Stripe para procesar pagos.
    
    En producción, usa el SDK oficial de Stripe (stripe-python).
    Aquí mostramos el patrón de integración.
    
    PCI-DSS: NUNCA almacenes datos de tarjetas. Stripe los gestiona.
    Solo almacenamos los payment_intent_id y customer_id de Stripe.
    """

    def __init__(self):
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        self._stripe = stripe
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            timeout=30,
            name="stripe"
        )

    def create_payment_intent(
        self,
        amount_cents: int,
        currency: str,
        customer_email: str,
        order_id: str,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Crea un PaymentIntent en Stripe.
        
        El PaymentIntent representa una intención de cobro.
        El cliente lo usa para completar el pago en el frontend.
        Devuelve el client_secret que se pasa al frontend.
        """
        log = logger.bind(order_id=order_id, amount_cents=amount_cents, currency=currency)
        log.info("stripe_create_payment_intent_started")

        def _create():
            intent = self._stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency.lower(),
                receipt_email=customer_email,
                metadata={
                    "order_id": order_id,
                    **(metadata or {}),
                },
                # Captura automática al confirmar
                capture_method="automatic",
            )
            return {
                "payment_intent_id": intent.id,
                "client_secret": intent.client_secret,
                "status": intent.status,
            }

        try:
            result = self._circuit_breaker.call(_create)
            log.info("stripe_payment_intent_created", payment_intent_id=result["payment_intent_id"])
            return result
        except self._stripe.StripeError as e:
            log.error("stripe_error", error=str(e), error_code=e.code)
            raise PaymentGatewayError(f"Error de Stripe: {e.user_message or str(e)}")

    def verify_webhook(self, payload: bytes, signature: str) -> Dict:
        """
        Verifica y parsea un webhook de Stripe.
        
        Los webhooks notifican eventos asíncronos:
        - payment_intent.succeeded: pago completado
        - payment_intent.payment_failed: pago fallido
        - charge.refunded: reembolso procesado
        """
        try:
            event = self._stripe.Webhook.construct_event(
                payload, signature, settings.STRIPE_WEBHOOK_SECRET
            )
            logger.info("stripe_webhook_received", event_type=event.type)
            return event
        except self._stripe.SignatureVerificationError:
            logger.error("stripe_webhook_invalid_signature")
            raise ValueError("Firma de webhook inválida")


class PaymentGatewayError(Exception):
    """Error en el procesamiento de pagos."""
    pass


# ─── Integración con OpenWeather API ─────────────────────────

class WeatherAPIClient:
    """
    Cliente para la API de OpenWeatherMap.
    
    Ejemplo de integración con una API de consulta externa.
    Muestra el patrón: cliente HTTP base + caché + circuit breaker.
    
    En sistemas de ecommerce puede usarse para: estimar tiempos de entrega,
    mostrar info sobre clima en la dirección de envío, etc.
    """

    def __init__(self):
        self._client = BaseAPIClient(
            base_url=settings.OPENWEATHER_BASE_URL,
            timeout=5,  # Las APIs de terceros deben tener timeouts cortos
            max_retries=2,
        )
        self._api_key = settings.OPENWEATHER_API_KEY

    def get_weather_by_city(self, city: str, country_code: str = "ES") -> Optional[Dict]:
        """
        Obtiene el clima actual de una ciudad.
        
        La respuesta se cachea 30 minutos para no saturar la API.
        OpenWeather actualiza datos cada 10 minutos, así que 30min es razonable.
        """
        from django.core.cache import cache

        cache_key = f"weather:{city.lower()}:{country_code.lower()}"
        cached = cache.get(cache_key)
        if cached:
            logger.debug("weather_cache_hit", city=city)
            return cached

        if not self._api_key:
            logger.warning("weather_api_key_not_configured")
            return None

        try:
            data = self._client.get("/weather", params={
                "q": f"{city},{country_code}",
                "appid": self._api_key,
                "units": "metric",
                "lang": "es",
            })

            result = {
                "city": data.get("name"),
                "temperature": data.get("main", {}).get("temp"),
                "feels_like": data.get("main", {}).get("feels_like"),
                "description": data.get("weather", [{}])[0].get("description"),
                "humidity": data.get("main", {}).get("humidity"),
                "wind_speed": data.get("wind", {}).get("speed"),
            }

            # Cachear 30 minutos
            cache.set(cache_key, result, timeout=1800)
            return result

        except APIClientError as e:
            logger.error("weather_api_error", city=city, error=str(e))
            return None


# ─── Integración con AWS S3 ───────────────────────────────────

class S3StorageService:
    """
    Servicio de almacenamiento con AWS S3.
    
    Para: subir archivos de usuarios (avatares, documentos),
    almacenar exports de reportes, backups, etc.
    
    En producción, configura:
    - Bucket privado (no acceso público por defecto)
    - URLs firmadas (pre-signed URLs) con TTL corto
    - Encriptación en reposo (SSE-S3 o SSE-KMS)
    - Versionado del bucket (para recuperar archivos borrados)
    - Lifecycle rules (para archivar/eliminar archivos viejos en Glacier)
    """

    def __init__(self):
        import boto3
        self._s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        self._bucket = settings.AWS_STORAGE_BUCKET_NAME

    def upload_file(self, file_obj, key: str, content_type: str = "application/octet-stream") -> str:
        """
        Sube un archivo a S3.
        
        Devuelve la URL del archivo.
        """
        try:
            self._s3.upload_fileobj(
                file_obj,
                self._bucket,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    "ServerSideEncryption": "AES256",  # Encriptación en reposo
                }
            )
            url = f"https://{self._bucket}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{key}"
            logger.info("s3_upload_success", key=key)
            return url
        except Exception as e:
            logger.error("s3_upload_error", key=key, error=str(e))
            raise

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Genera una URL firmada con acceso temporal a un archivo privado.
        
        Ideal para: descargar facturas, documentos privados.
        La URL expira automáticamente después de expires_in segundos.
        """
        try:
            url = self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            logger.debug("s3_presigned_url_generated", key=key, expires_in=expires_in)
            return url
        except Exception as e:
            logger.error("s3_presigned_url_error", key=key, error=str(e))
            raise
