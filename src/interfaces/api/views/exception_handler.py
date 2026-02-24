"""
=============================================================================
MANEJADOR DE EXCEPCIONES GLOBAL
=============================================================================

Centraliza el formato de todas las respuestas de error.
Garantiza que la API devuelve siempre el mismo formato de error,
independientemente de dónde ocurra la excepción.

Formato estándar de error:
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Los datos enviados no son válidos",
        "details": {...}
    },
    "request_id": "uuid"
}
"""
import structlog
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = structlog.get_logger(__name__)


def custom_exception_handler(exc, context):
    """
    Handler de excepciones para DRF.
    Configurado en REST_FRAMEWORK['EXCEPTION_HANDLER'].
    """
    # Primero, intentar el handler estándar de DRF
    response = exception_handler(exc, context)

    # Obtener request_id si está disponible
    request = context.get('request')
    request_id = getattr(request, 'request_id', None) if request else None

    if response is not None:
        # Reformatear el error de DRF a nuestro formato estándar
        error_data = {
            'error': {
                'code': _get_error_code(response.status_code),
                'message': _get_error_message(response.status_code),
                'details': response.data,
            }
        }
        if request_id:
            error_data['request_id'] = request_id

        response.data = error_data
        return response

    # Si DRF no maneja la excepción, la manejamos nosotros
    logger.exception("unhandled_exception", exc_type=type(exc).__name__)

    return Response(
        {
            'error': {
                'code': 'INTERNAL_SERVER_ERROR',
                'message': 'Ha ocurrido un error interno. Por favor, inténtalo de nuevo.',
                'details': None,
            },
            'request_id': request_id,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _get_error_code(status_code: int) -> str:
    codes = {
        400: 'BAD_REQUEST',
        401: 'UNAUTHORIZED',
        403: 'FORBIDDEN',
        404: 'NOT_FOUND',
        405: 'METHOD_NOT_ALLOWED',
        409: 'CONFLICT',
        422: 'VALIDATION_ERROR',
        429: 'RATE_LIMIT_EXCEEDED',
        500: 'INTERNAL_SERVER_ERROR',
    }
    return codes.get(status_code, 'UNKNOWN_ERROR')


def _get_error_message(status_code: int) -> str:
    messages = {
        400: 'Los datos enviados no son válidos',
        401: 'Autenticación requerida',
        403: 'No tienes permisos para realizar esta acción',
        404: 'El recurso solicitado no existe',
        409: 'El recurso ya existe',
        429: 'Demasiadas peticiones. Por favor, espera un momento.',
        500: 'Error interno del servidor',
    }
    return messages.get(status_code, 'Ha ocurrido un error')
