# invest_proj/celery.py
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'invest_proj.settings')

app = Celery('invest_proj')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
