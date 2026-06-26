from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "capable_u",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "refresh-exchange-rates-daily": {
            "task": "app.worker.tasks.refresh_exchange_rates",
            "schedule": crontab(hour=6, minute=0),
        },
    },
)
