# 🏗️ Tech Lead Demo Project

Proyecto Django de referencia con arquitectura productiva para entrevistas de Tech Lead.

## 🎯 Conceptos Demostrados

| Concepto | Implementación |
|----------|---------------|
| **DDD** | Entidades, Value Objects, Aggregates, Domain Events, Repositories |
| **Hexagonal** | Puertos & Adaptadores, capas Domain/Application/Infrastructure |
| **BD SQL** | PostgreSQL con Django ORM + índices optimizados |
| **BD NoSQL** | MongoDB con MongoEngine para logs de actividad |
| **Caché** | Redis con patrón Cache-Aside + invalidación |
| **Kafka** | Publicación y consumo de Domain Events |
| **RabbitMQ** | Colas de tareas con routing por topic exchange |
| **Celery** | Tareas asíncronas con reintentos y queues |
| **JWT** | Autenticación stateless con refresh tokens |
| **RBAC** | Roles: Admin > Manager > Customer > Readonly |
| **ABAC** | Permisos a nivel de objeto con django-guardian |
| **Logging** | Structlog con formato JSON + request_id |
| **Métricas** | Prometheus + Grafana via django-prometheus |
| **Health Checks** | Endpoint /health/ con checks de BD, Redis, disco |
| **OpenAPI** | Swagger automático con drf-spectacular |
| **Tests** | Unitarios (dominio puro) + Use cases con fakes |

## 🏛️ Arquitectura

```
techlead_project/
├── config/                    # Configuración Django
│   ├── settings.py            # Settings con 12-factor app
│   ├── urls.py                # Router principal
│   └── celery.py              # Configuración Celery
│
├── apps/                      # Bounded Contexts (DDD)
│   ├── users/                 # Contexto de usuarios
│   │   ├── domain/            # 🔵 Dominio puro (sin dependencias externas)
│   │   │   ├── entities/      # User (Aggregate Root)
│   │   │   ├── value_objects/ # Email, HashedPassword
│   │   │   ├── repositories/  # Interfaces (puertos)
│   │   │   └── services/      # PasswordHashService (interfaz)
│   │   ├── application/       # 🟡 Casos de uso
│   │   │   ├── use_cases/     # RegisterUser, LoginUser
│   │   │   └── dtos/          # DTOs de entrada/salida
│   │   └── infrastructure/    # 🔴 Adaptadores
│   │       ├── models/        # ORM Django (PostgreSQL)
│   │       ├── repositories/  # DjangoUserRepo + CachedUserRepo
│   │       ├── services/      # DjangoPasswordService, JwtTokenService
│   │       ├── serializers/   # DRF Serializers
│   │       ├── views.py       # Adaptadores HTTP
│   │       └── dependencies.py # Inyección de dependencias
│   │
│   ├── orders/                # Contexto de pedidos
│   │   ├── domain/entities/   # Order (Aggregate con State Machine)
│   │   └── infrastructure/    # Models, views con CRUD + acciones
│   │
│   └── notifications/         # Contexto de notificaciones
│       └── infrastructure/    # Celery tasks (email async)
│
├── shared/                    # Código compartido entre contextos
│   ├── domain/                # BaseEntity, Value Objects base, DomainEvent
│   └── infrastructure/
│       ├── messaging/         # KafkaPublisher, RabbitMQPublisher, Consumer
│       ├── monitoring/        # RequestLoggingMiddleware
│       ├── external_apis/     # WeatherClient (httpx + cache)
│       ├── permissions.py     # RBAC permissions DRF
│       └── pagination.py      # Paginación estándar
│
├── tests/
│   └── unit/                  # Tests de dominio (sin BD)
│
└── docker/
    ├── docker-compose.yml     # PostgreSQL + MongoDB + Redis + Kafka + RabbitMQ
    └── prometheus.yml         # Configuración Prometheus
```

## 🚀 Inicio Rápido

```bash
# 1. Clonar y crear entorno virtual
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
copy .env.example .env       # Windows
cp .env.example .env         # Linux/Mac

# 4. Levantar infraestructura
docker-compose -f docker/docker-compose.yml up -d

# 5. Aplicar migraciones
python manage.py migrate

# 6. Crear superusuario
python manage.py createsuperuser

# 7. Iniciar servidor
python manage.py runserver
```

## 🌐 URLs de Interés

| URL | Descripción |
|-----|-------------|
| http://localhost:8000/api/docs/ | Swagger UI |
| http://localhost:8000/health/ | Health Checks |
| http://localhost:8000/metrics | Métricas Prometheus |
| http://localhost:8000/admin/ | Admin Django |
| http://localhost:15672/ | RabbitMQ Management UI |
| http://localhost:3001/ | Grafana (admin/admin) |
| http://localhost:9090/ | Prometheus |

## 🧪 Tests

```bash
# Todos los tests
pytest tests/ -v

# Solo unitarios (rápidos, sin BD)
pytest tests/unit/ -v

# Con cobertura
pytest tests/ --cov=apps --cov-report=html
```

## 🔧 Workers y Consumers

```bash
# Celery worker (procesa emails, notificaciones)
celery -A config worker --loglevel=info

# Celery Beat (tareas programadas)
celery -A config beat --loglevel=info

# Kafka consumer (procesa domain events)
python manage.py run_kafka_consumer
```

## 📝 API Endpoints

### Autenticación
- `POST /api/v1/auth/register/` - Registro de usuario
- `POST /api/v1/auth/login/` - Login (obtener JWT)
- `POST /api/v1/auth/token/refresh/` - Refrescar token

### Usuarios
- `GET /api/v1/users/` - Lista usuarios (admin/manager)
- `GET /api/v1/users/me/` - Perfil propio

### Pedidos
- `GET/POST /api/v1/orders/` - Listar/crear pedidos
- `GET /api/v1/orders/{id}/` - Detalle de pedido
- `POST /api/v1/orders/{id}/actions/{action}/` - Acciones (confirm, cancel, ship...)

## 🎤 Puntos para la Entrevista

### DDD
- **Aggregate Root**: `User` y `Order` son los puntos de acceso a sus aggregates
- **Domain Events**: se registran en la entidad y se publican tras persistir
- **Value Objects**: `UserEmail`, `HashedPassword` son inmutables y se validan al crear
- **Repository pattern**: el dominio define la interfaz; infraestructura implementa

### Hexagonal
- El **dominio** (azul) no importa nada externo
- La **aplicación** (amarillo) solo importa del dominio
- La **infraestructura** (rojo) implementa los puertos del dominio
- Los **Use Cases** son los puertos de entrada

### Caché
- `CachedUserRepository` usa el patrón Decorator sobre el repositorio real
- Cache-aside: busca en Redis primero, si no → BD → guarda en Redis
- Invalidación explícita al escribir (write-through)

### Mensajería
- `KafkaEventPublisher`: alta throughput, log persistente, replay
- `RabbitMQEventPublisher`: routing complejo, dead-letter queues
- Celery: tareas async con reintentos automáticos y backoff exponencial
