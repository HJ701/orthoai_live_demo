from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
from app.models import InferenceJob, JobState


QUEUED_STALE_MESSAGE = (
    "The analysis did not start because processing capacity was temporarily "
    "unavailable. Your uploaded case is preserved; select Retry diagnosis."
)
RUNNING_STALE_MESSAGE = (
    "The analysis exceeded the processing time limit. Your uploaded case is "
    "preserved; select Retry diagnosis."
)


def utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def age_seconds(value: datetime | None, *, now: datetime | None = None) -> float:
    if value is None:
        return 0.0
    current = utc_naive(now or datetime.utcnow())
    return max((current - utc_naive(value)).total_seconds(), 0.0)


def reconcile_stale_job(
    job: InferenceJob,
    *,
    now: datetime | None = None,
    worker_available: bool | None = None,
) -> bool:
    """Move jobs abandoned by the queue/worker into a recoverable terminal state."""
    unavailable_timeout = max(settings.inference_unavailable_worker_grace_seconds, 1)
    queued_timeout = max(settings.inference_queued_stale_seconds, 1)
    running_timeout = max(settings.inference_running_stale_seconds, 1)
    if worker_available is False:
        queued_timeout = min(queued_timeout, unavailable_timeout)
        running_timeout = min(running_timeout, unavailable_timeout)

    if job.state == JobState.QUEUED and age_seconds(
        job.created_at,
        now=now,
    ) >= queued_timeout:
        job.state = JobState.ERROR
        job.progress = 1.0
        job.error_message = QUEUED_STALE_MESSAGE
        job.completed_at = utc_naive(now or datetime.utcnow())
        return True

    if job.state == JobState.RUNNING and age_seconds(
        job.started_at,
        now=now,
    ) >= running_timeout:
        job.state = JobState.ERROR
        job.progress = 1.0
        job.error_message = RUNNING_STALE_MESSAGE
        job.completed_at = utc_naive(now or datetime.utcnow())
        return True

    return False
