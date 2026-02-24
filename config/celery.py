"""
============================================================
CELERY - Configuración del worker de tareas asíncronas
============================================================
Celery se usa para:
- Envío de emails/notificaciones en background
- Procesamiento pesado fuera del request/response cycle
- Tareas programadas (cron jobs)

Para iniciar el worker:
  celery -A config worker --loglevel=info
Para tareas programadas (beat):
  celery -A config beat --loglevel=info
============================================================
"""

import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('techlead')

# Lee la configuración desde Django settings con prefijo CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodiscover: busca tasks.py en cada app instalada
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Tarea de debug para verificar que Celery funciona."""
    print(f'Request: {self.request!r}')
