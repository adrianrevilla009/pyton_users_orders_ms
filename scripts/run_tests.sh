#!/bin/bash
# =============================================================================
# SCRIPT DE TESTS
# =============================================================================
set -e

echo "🧪 Ejecutando tests..."

# Tests unitarios (sin BD, ultra-rápidos)
echo "--- Unit Tests ---"
pytest tests/unit/ -v --tb=short

# Tests de integración (con BD de test)
echo "--- Integration Tests ---"
pytest tests/integration/ -v --tb=short

# Coverage report
echo "--- Coverage ---"
pytest tests/ --cov=src --cov-report=term-missing --cov-report=html

echo "✅ Todos los tests pasaron"
echo "   Coverage: open htmlcov/index.html"
