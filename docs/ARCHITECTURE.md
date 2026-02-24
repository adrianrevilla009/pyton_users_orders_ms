# Arquitectura del Proyecto

## Capas (de dentro hacia fuera)

```
┌─────────────────────────────────────────────────┐
│               INTERFACES (API)                  │  ← HTTP, Views, Serializers
├─────────────────────────────────────────────────┤
│              APPLICATION                        │  ← Use Cases, DTOs, Ports
├─────────────────────────────────────────────────┤
│                DOMAIN                           │  ← Entities, VOs, Services, Events
├─────────────────────────────────────────────────┤
│             INFRASTRUCTURE                      │  ← SQL, NoSQL, Redis, Kafka, Stripe
└─────────────────────────────────────────────────┘
```

## Regla de Dependencia

Las dependencias SOLO van hacia adentro:
- Infrastructure depende de Application/Domain
- Application depende de Domain
- Domain NO depende de nadie

## Flujo de una Request

```
HTTP Request
     ↓
[View] → deserializar, autenticar, autorizar
     ↓
[Use Case] → orquestar la lógica
     ↓
[Domain] → lógica de negocio, eventos
     ↓
[Repository Interface] → puerto de salida
     ↓
[Repository Impl] → SQL/NoSQL/Redis
     ↓
HTTP Response ← serializar el DTO de respuesta
```

## Patrones Aplicados

| Patrón | Dónde | Para qué |
|--------|-------|----------|
| Aggregate Root | Order, User | Consistencia transaccional |
| Value Object | Money, Email, Address | Inmutabilidad, validación |
| Factory Method | Entity.create() | Centralizar creación |
| Repository | UserRepository, etc. | Abstraer persistencia |
| Domain Events | UserCreated, etc. | Desacoplar efectos |
| Port & Adapter | EventBus, PaymentGateway | Invertir dependencias |
| DTO | Commands, Responses | Transferir datos entre capas |

## Tecnologías y Por Qué

| Tecnología | Rol | Por qué |
|-----------|-----|---------|
| PostgreSQL | BD principal | ACID, relaciones, madurez |
| MongoDB | Reseñas, logs, esquema flexible | Documentos, sin schema rígido |
| Redis | Caché, sesiones, rate limiting | Ultra-rápido, in-memory |
| Kafka | Eventos de dominio, streams | Durabilidad, replay, escalabilidad |
| RabbitMQ | Tareas async (Celery) | Routing complejo, dead-letter |
| JWT | Autenticación stateless | Escalable, sin estado en servidor |
| Structlog | Logging | JSON estructurado, correlación |
| Prometheus | Métricas | Estándar de industria |
