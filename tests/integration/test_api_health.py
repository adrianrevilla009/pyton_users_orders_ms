"""
=============================================================================
TESTS DE INTEGRACIÓN: Health Check API
=============================================================================

Tests de integración: prueban la API completa con Django TestClient.
Usan BD de test real (SQLite en memoria por defecto en tests).
"""
import pytest
from django.test import TestCase, Client


class TestHealthEndpoints(TestCase):
    """Tests para los endpoints de health check."""

    def setUp(self):
        self.client = Client()

    def test_liveness_returns_200(self):
        response = self.client.get('/api/v1/health/live/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'alive')

    def test_readiness_includes_postgresql_check(self):
        response = self.client.get('/api/v1/health/ready/')
        # En tests usa SQLite, así que debe estar OK
        data = response.json()
        self.assertIn('checks', data)
