"""
============================================================
PAGINACIÓN ESTÁNDAR
============================================================
Paginación consistente en todos los endpoints de la API.
Cursor-based pagination es mejor para grandes datasets.
============================================================
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """
    Paginación estándar para todos los endpoints.
    Respuesta: { count, next, previous, results }
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'

    def get_paginated_response(self, data):
        return Response({
            'pagination': {
                'count': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'page_size': self.get_page_size(self.request),
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            },
            'results': data
        })
