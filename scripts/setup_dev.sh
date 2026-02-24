#!/bin/bash
# =============================================================================
# SCRIPT DE SETUP PARA DESARROLLO
# =============================================================================
set -e  # Salir si hay error

echo "🚀 Configurando entorno de desarrollo..."

# Crear .env desde .env.example si no existe
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Creado .env desde .env.example"
fi

# Crear directorio de logs
mkdir -p logs

# Instalar dependencias
pip install -r requirements.txt
echo "✅ Dependencias instaladas"

# Levantar infraestructura
docker-compose up -d postgres redis mongo rabbitmq
echo "✅ Infraestructura levantada"

# Esperar a que PostgreSQL esté listo
echo "⏳ Esperando a PostgreSQL..."
sleep 5

# Migraciones
python manage.py makemigrations
python manage.py migrate
echo "✅ Migraciones aplicadas"

# Crear superusuario de desarrollo
echo "Creando superusuario de desarrollo..."
python manage.py shell -c "
from src.infrastructure.persistence.sql.models import User
if not User.objects.filter(email='admin@example.com').exists():
    User.objects.create_superuser('admin@example.com', 'Admin1234!', first_name='Admin', last_name='User')
    print('Superusuario creado: admin@example.com / Admin1234!')
else:
    print('El superusuario ya existe')
"

echo ""
echo "🎉 Setup completado!"
echo "   Servidor: python manage.py runserver"
echo "   Admin:    http://localhost:8000/admin"
echo "   Swagger:  http://localhost:8000/swagger/"
echo "   Métricas: http://localhost:8000/metrics"
echo "   RabbitMQ: http://localhost:15672 (guest/guest)"
