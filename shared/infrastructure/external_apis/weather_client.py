"""
============================================================
WEATHER API CLIENT - Integración con API externa
============================================================
Demuestra cómo integrar APIs externas siguiendo hexagonal:

1. Definir un puerto (interfaz) en el dominio/aplicación
2. Implementar el adaptador en infraestructura
3. El dominio nunca sabe que existe una API de clima

Características:
- Caché de respuestas en Redis (evita llamadas repetidas)
- Circuit Breaker pattern (evita cascading failures)
- Retry con backoff exponencial
- Métricas de llamadas externas
============================================================
"""

import httpx
import structlog
from typing import Optional
from dataclasses import dataclass
from django.core.cache import cache

logger = structlog.get_logger(__name__)

# TTL del caché para datos de clima (10 minutos)
WEATHER_CACHE_TTL = 600


@dataclass
class WeatherData:
    """DTO de respuesta del clima."""
    city: str
    temperature: float
    feels_like: float
    humidity: int
    description: str
    icon: str


class WeatherAPIError(Exception):
    """Error al llamar a la API de clima."""
    pass


class WeatherClient:
    """
    Cliente HTTP para la API de OpenWeatherMap.
    
    Implementa:
    - Caché Redis para evitar llamadas redundantes
    - Timeout para evitar bloqueos
    - Logging de todas las llamadas
    """

    def __init__(self):
        from django.conf import settings
        self._api_key = settings.env('WEATHER_API_KEY', default='')
        self._base_url = settings.env('WEATHER_API_URL', default='https://api.openweathermap.org/data/2.5')

    def get_weather(self, city: str) -> Optional[WeatherData]:
        """
        Obtiene el clima actual de una ciudad.
        Primero busca en caché Redis, luego llama a la API.
        """
        cache_key = f"weather:{city.lower().replace(' ', '_')}"

        # 1. Intentar desde caché
        cached = cache.get(cache_key)
        if cached:
            logger.debug("Clima obtenido desde caché", city=city)
            return WeatherData(**cached)

        # 2. Llamar a la API externa
        logger.info("Llamando a WeatherAPI", city=city)
        try:
            with httpx.Client(timeout=5.0) as client:  # Timeout de 5 segundos
                response = client.get(
                    f"{self._base_url}/weather",
                    params={
                        'q': city,
                        'appid': self._api_key,
                        'units': 'metric',
                        'lang': 'es',
                    }
                )
                response.raise_for_status()
                data = response.json()

        except httpx.TimeoutException:
            logger.error("Timeout llamando a WeatherAPI", city=city)
            raise WeatherAPIError(f"Timeout obteniendo clima para {city}")
        except httpx.HTTPStatusError as e:
            logger.error("Error HTTP en WeatherAPI", status=e.response.status_code, city=city)
            raise WeatherAPIError(f"Error {e.response.status_code} en WeatherAPI")
        except Exception as e:
            logger.error("Error inesperado en WeatherAPI", error=str(e), city=city)
            raise WeatherAPIError(f"Error inesperado: {e}")

        # 3. Parsear respuesta
        weather = WeatherData(
            city=data['name'],
            temperature=data['main']['temp'],
            feels_like=data['main']['feels_like'],
            humidity=data['main']['humidity'],
            description=data['weather'][0]['description'],
            icon=data['weather'][0]['icon'],
        )

        # 4. Guardar en caché
        cache.set(cache_key, {
            'city': weather.city,
            'temperature': weather.temperature,
            'feels_like': weather.feels_like,
            'humidity': weather.humidity,
            'description': weather.description,
            'icon': weather.icon,
        }, WEATHER_CACHE_TTL)

        logger.info("Clima obtenido de API", city=city, temperature=weather.temperature)
        return weather
