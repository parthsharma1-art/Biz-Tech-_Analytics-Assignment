import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "emailsystem.settings")

celeryApp = Celery("emailsystem")
celeryApp.config_from_object("django.conf:settings", namespace="CELERY")
celeryApp.autodiscover_tasks()

celeryApp.conf.update(
    result_backend=None,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

