"""Views para APIs externas."""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from shared.infrastructure.external_apis.weather_client import WeatherClient, WeatherAPIError


class WeatherView(APIView):
    """GET /api/v1/weather/?city=Barcelona - Clima de una ciudad."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        city = request.query_params.get('city', 'Madrid')
        try:
            client = WeatherClient()
            weather = client.get_weather(city)
            return Response({
                'city': weather.city,
                'temperature': weather.temperature,
                'feels_like': weather.feels_like,
                'humidity': weather.humidity,
                'description': weather.description,
            })
        except WeatherAPIError as e:
            return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
