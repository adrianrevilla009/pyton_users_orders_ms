# =============================================================================
# DOCKERFILE — Multi-stage build para producción
# =============================================================================
# Multi-stage: la imagen final es más pequeña porque no incluye
# las herramientas de compilación usadas en el build

# Etapa 1: Builder (instalar dependencias con compiladores)
FROM python:3.12-slim as builder

WORKDIR /app

# Instalar dependencias de compilación (solo en builder)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar y instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# =============================================================================
# Etapa 2: Production image (imagen final, sin compiladores)
FROM python:3.12-slim

WORKDIR /app

# Instalar solo runtime dependencies (no compiladores)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar las dependencias instaladas del builder
COPY --from=builder /root/.local /root/.local

# Copiar el código fuente
COPY . .

# Crear directorio de logs
RUN mkdir -p /app/logs

# Usuario no-root para seguridad
RUN adduser --disabled-password --gecos '' appuser
RUN chown -R appuser:appuser /app
USER appuser

# Variables de entorno por defecto
ENV DJANGO_SETTINGS_MODULE=config.settings.production
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH=/root/.local/bin:$PATH

# Puerto que expone la aplicación
EXPOSE 8000

# Health check a nivel Docker
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live/')"

# Comando de producción — Gunicorn con múltiples workers
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--worker-class", "sync", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
