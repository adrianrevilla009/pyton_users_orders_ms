"""
=============================================================================
CELERY — Configuración de la aplicación de tareas asíncronas
=============================================================================

Celery permite ejecutar tareas fuera del ciclo request/response de Django:
- Envío de emails
- Procesamiento de pagos
- Generación de reportes
- Sincronización con APIs externas
"""
import os
from celery import Celery

# Usamos el settings de producción por defecto; cada entorno puede sobreescribir
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('techlead')

# Configuración desde Django settings (prefijo CELERY_)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Descubrir tareas automáticamente en todos los módulos tasks.py
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Tarea de debug para verificar que Celery funciona."""
    print(f'Request: {self.request!r}')
