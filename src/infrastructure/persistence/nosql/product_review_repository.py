"""
=============================================================================
ADAPTADOR NoSQL: ProductReviewRepository (MongoDB)
=============================================================================

Las reseñas de productos son un caso de uso ideal para MongoDB:
- Esquema flexible (diferentes campos por tipo de producto)
- Alto volumen de lecturas
- Estructura anidada (comentarios, replies)
- No requieren ACID fuerte

Usamos PyMongo directamente para máximo control.
En producción podríamos usar Motor (async) para no bloquear el event loop.
"""
from datetime import datetime
from typing import Optional
import uuid

import structlog
from pymongo import MongoClient, DESCENDING, IndexModel
from pymongo.database import Database
from pymongo.collection import Collection
from django.conf import settings

logger = structlog.get_logger(__name__)


class ProductReviewRepository:
    """
    Repositorio de reseñas de productos usando MongoDB.

    Documento ejemplo:
    {
        "_id": "uuid",
        "product_id": "uuid",
        "reviewer_id": "uuid",
        "reviewer_name": "Juan García",
        "rating": 4,
        "title": "Muy buen producto",
        "body": "La calidad es excelente...",
        "pros": ["Calidad", "Precio"],
        "cons": ["Envío lento"],
        "verified_purchase": true,
        "helpful_votes": 12,
        "created_at": "2024-01-15T10:30:00Z",
        "media": [{"type": "image", "url": "..."}]
    }
    """

    COLLECTION_NAME = 'product_reviews'

    def __init__(self):
        # Conexión a MongoDB — en producción usar un pool de conexiones
        self._client = MongoClient(settings.MONGO_URI)
        self._db: Database = self._client[settings.MONGO_DB_NAME]
        self._collection: Collection = self._db[self.COLLECTION_NAME]

        # Crear índices si no existen
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """
        Crea los índices necesarios.
        Los índices en MongoDB son fundamentales para el rendimiento.
        Equivalente a CREATE INDEX en SQL.
        """
        self._collection.create_indexes([
            # Búsquedas por producto (más frecuente)
            IndexModel([("product_id", DESCENDING)]),
            # Búsquedas por reviewer
            IndexModel([("reviewer_id", DESCENDING)]),
            # Índice compuesto para reseñas de un producto ordenadas
            IndexModel([("product_id", DESCENDING), ("created_at", DESCENDING)]),
            # Texto completo para búsqueda en título y body
            IndexModel([("title", "text"), ("body", "text")]),
            # Un usuario solo puede reseñar un producto una vez
            IndexModel([("product_id", DESCENDING), ("reviewer_id", DESCENDING)], unique=True),
        ])

    def create_review(
        self,
        product_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        reviewer_name: str,
        rating: int,
        title: str,
        body: str,
        pros: list[str] = None,
        cons: list[str] = None,
        verified_purchase: bool = False,
    ) -> dict:
        """Crea una nueva reseña."""
        if not 1 <= rating <= 5:
            raise ValueError("El rating debe estar entre 1 y 5")

        review = {
            '_id': str(uuid.uuid4()),
            'product_id': str(product_id),
            'reviewer_id': str(reviewer_id),
            'reviewer_name': reviewer_name,
            'rating': rating,
            'title': title,
            'body': body,
            'pros': pros or [],
            'cons': cons or [],
            'verified_purchase': verified_purchase,
            'helpful_votes': 0,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
        }

        try:
            self._collection.insert_one(review)
            logger.info("review_created", product_id=str(product_id), rating=rating)
            return review
        except Exception as e:
            logger.error("review_creation_failed", error=str(e))
            raise

    def get_product_reviews(
        self,
        product_id: uuid.UUID,
        page: int = 1,
        page_size: int = 10,
        sort_by: str = 'recent',  # 'recent' | 'helpful' | 'rating_asc' | 'rating_desc'
    ) -> dict:
        """
        Obtiene reseñas de un producto con paginación.
        Retorna un dict con items y metadatos (patrón común en NoSQL).
        """
        filter_query = {'product_id': str(product_id)}

        sort_map = {
            'recent': [('created_at', DESCENDING)],
            'helpful': [('helpful_votes', DESCENDING)],
            'rating_asc': [('rating', 1)],
            'rating_desc': [('rating', DESCENDING)],
        }
        sort = sort_map.get(sort_by, sort_map['recent'])

        skip = (page - 1) * page_size
        total = self._collection.count_documents(filter_query)
        reviews = list(
            self._collection
            .find(filter_query)
            .sort(sort)
            .skip(skip)
            .limit(page_size)
        )

        return {
            'items': reviews,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
        }

    def get_product_rating_summary(self, product_id: uuid.UUID) -> dict:
        """
        Usa el pipeline de agregación de MongoDB para calcular estadísticas.
        Equivalente a un GROUP BY en SQL pero mucho más potente.
        """
        pipeline = [
            # Filtrar por producto
            {'$match': {'product_id': str(product_id)}},

            # Agrupar y calcular estadísticas
            {'$group': {
                '_id': None,
                'average_rating': {'$avg': '$rating'},
                'total_reviews': {'$count': {}},
                'rating_1': {'$sum': {'$cond': [{'$eq': ['$rating', 1]}, 1, 0]}},
                'rating_2': {'$sum': {'$cond': [{'$eq': ['$rating', 2]}, 1, 0]}},
                'rating_3': {'$sum': {'$cond': [{'$eq': ['$rating', 3]}, 1, 0]}},
                'rating_4': {'$sum': {'$cond': [{'$eq': ['$rating', 4]}, 1, 0]}},
                'rating_5': {'$sum': {'$cond': [{'$eq': ['$rating', 5]}, 1, 0]}},
            }},

            # Añadir campo calculado
            {'$addFields': {
                'average_rating': {'$round': ['$average_rating', 1]},
            }},
        ]

        results = list(self._collection.aggregate(pipeline))

        if not results:
            return {'average_rating': 0.0, 'total_reviews': 0, 'distribution': {}}

        result = results[0]
        return {
            'average_rating': result.get('average_rating', 0.0),
            'total_reviews': result.get('total_reviews', 0),
            'distribution': {
                '1': result.get('rating_1', 0),
                '2': result.get('rating_2', 0),
                '3': result.get('rating_3', 0),
                '4': result.get('rating_4', 0),
                '5': result.get('rating_5', 0),
            },
        }
