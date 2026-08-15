from celery import Celery
from app.config import settings

celery_app = Celery(
    "medical_ai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.inference", "app.tasks.email"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    # A GPU task must be returned to Redis if a worker process is lost. The
    # single-message prefetch prevents one GPU worker from reserving a backlog
    # that other scaled workers could process.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 5,
        "interval_start": 0,
        "interval_step": 1,
        "interval_max": 5,
    },
    broker_transport_options={"visibility_timeout": 60 * 60},
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    task_routes={
        "app.tasks.inference.run_inference": {"queue": "gpu-inference"},
    },
)
