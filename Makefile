# ============================================================
# MAKEFILE - Comandos de desarrollo
# ============================================================
# Uso: make <comando>
# Ejemplo: make dev, make test, make migrate

.PHONY: help dev migrate test lint worker consumer docs

help:
	@echo "Comandos disponibles:"
	@echo "  make dev         - Inicia el servidor de desarrollo"
	@echo "  make migrate     - Aplica migraciones"
	@echo "  make test        - Ejecuta todos los tests"
	@echo "  make worker      - Inicia el worker de Celery"
	@echo "  make consumer    - Inicia el consumer de Kafka"
	@echo "  make infra       - Levanta infraestructura Docker"
	@echo "  make docs        - Abre la documentación Swagger"

# Levantar infraestructura (BD, Redis, Kafka, etc.)
infra:
	docker-compose -f docker/docker-compose.yml up -d

# Parar infraestructura
infra-down:
	docker-compose -f docker/docker-compose.yml down

# Migraciones
migrate:
	python manage.py makemigrations
	python manage.py migrate

# Servidor de desarrollo
dev:
	python manage.py runserver 0.0.0.0:8000

# Tests
test:
	pytest tests/ -v --tb=short

# Tests unitarios solo (rápidos, sin BD)
test-unit:
	pytest tests/unit/ -v

# Worker de Celery (tareas asíncronas)
worker:
	celery -A config worker --loglevel=info -Q notifications,default

# Celery Beat (tareas programadas)
beat:
	celery -A config beat --loglevel=info

# Consumer de Kafka
consumer:
	python manage.py run_kafka_consumer

# Crear superusuario
superuser:
	python manage.py createsuperuser

# Lint y formato
lint:
	flake8 apps/ shared/ --max-line-length=120
	
# Instalar dependencias
install:
	pip install -r requirements.txt

# Setup inicial completo
setup: install migrate superuser
	@echo "¡Proyecto configurado! Ejecuta 'make dev' para iniciar."
