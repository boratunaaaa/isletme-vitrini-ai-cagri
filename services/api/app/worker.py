"""Celery uygulaması. `services/worker` konteyneri bu modülü çalıştırır:
celery -A app.worker.celery_app worker -Q default,calls
celery -A app.worker.celery_app beat
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.LOG_LEVEL)

celery_app = Celery(
    "ivac",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.call_tasks", "app.tasks.campaign_tasks", "app.tasks.maintenance_tasks"],
)

celery_app.conf.update(
    task_default_queue="default",
    task_routes={"app.tasks.call_tasks.*": {"queue": "calls"}},
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,
    task_soft_time_limit=540,
    timezone=settings.APP_TIMEZONE,
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "campaign-tick": {
            "task": "app.tasks.campaign_tasks.campaign_tick",
            "schedule": 60.0,
        },
        "call-watchdog": {
            "task": "app.tasks.call_tasks.watchdog_sweep",
            "schedule": 60.0,
        },
        "callback-due-sweep": {
            "task": "app.tasks.campaign_tasks.callback_due_sweep",
            "schedule": 300.0,
        },
        "retention-cleanup": {
            "task": "app.tasks.maintenance_tasks.retention_cleanup",
            "schedule": crontab(hour=4, minute=30),
        },
    },
)
