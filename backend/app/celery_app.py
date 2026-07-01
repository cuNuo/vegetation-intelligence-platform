"""Celery部署入口与五级优先队列。"""

from celery import Celery
from kombu import Queue

from app.settings import settings

celery_app = Celery(
    "vegetation_jobs",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker_tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_transport_options={"queue_order_strategy": "priority"},
    task_queues=(
        Queue("urgent", routing_key="priority.1"),
        Queue("high", routing_key="priority.2"),
        Queue("normal", routing_key="priority.3"),
        Queue("low", routing_key="priority.4"),
        Queue("batch", routing_key="priority.5"),
    ),
    task_default_queue="normal",
    task_always_eager=settings.celery_always_eager,
)
