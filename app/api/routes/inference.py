from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import InferenceJob, InferenceResult, Case, Image, JobState
from app.schemas import InferenceRequest, InferenceResponse, InferenceStatusResponse
from app.api.deps import get_current_user_dependency, get_case_dependency
from app.celery_app import celery_app
from app.tasks.inference import run_inference
from app.core.audit import log_audit_event
from app.core.inference_health import get_gpu_worker_health
from app.core.inference_jobs import reconcile_stale_job
from datetime import datetime, timezone
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


TERMINAL_STATES = {JobState.DONE, JobState.ERROR}
ACTIVE_STATES = {JobState.QUEUED, JobState.RUNNING}


def seconds_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if not start or not end:
        return None
    if start.tzinfo is not None:
        start = start.astimezone(timezone.utc).replace(tzinfo=None)
    if end.tzinfo is not None:
        end = end.astimezone(timezone.utc).replace(tzinfo=None)
    return round(max((end - start).total_seconds(), 0.0), 3)


def timing_for_job(job: InferenceJob) -> dict:
    now = datetime.utcnow()
    terminal_time = job.completed_at or now
    queue_end = job.started_at or terminal_time
    return {
        "queue_seconds": seconds_between(job.created_at, queue_end),
        "run_seconds": seconds_between(job.started_at, terminal_time) if job.started_at else None,
        "total_seconds": seconds_between(job.created_at, terminal_time),
    }


def revoke_stale_delivery(job: InferenceJob) -> None:
    if not job.celery_task_id:
        return
    try:
        celery_app.control.revoke(job.celery_task_id, terminate=False)
    except Exception:
        logger.exception("Unable to revoke stale inference task %s", job.celery_task_id)


def require_ready_gpu_worker(health: Optional[dict] = None) -> dict:
    health = health or get_gpu_worker_health()
    if not health.get("available"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "OrthoAI processing is temporarily unavailable. Your uploaded "
                "case is preserved; please retry shortly."
            ),
            headers={"Retry-After": "30"},
        )
    return health


@router.post("", response_model=InferenceResponse, status_code=status.HTTP_201_CREATED)
def start_inference(
    request: Request,
    inference_data: InferenceRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dependency)
):
    """Start an inference job for a case"""
    # Verify case exists and belongs to user
    case = db.query(Case).filter(
        Case.id == inference_data.case_id,
        Case.user_id == current_user.id
    ).with_for_update().first()
    
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )
    
    # Check consent
    if not case.consent_checked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Consent must be checked before running inference"
        )
    
    # Check if case has images
    image_count = db.query(Image).filter(Image.case_id == case.id).count()
    if image_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Case must have at least one image"
        )

    worker_health = get_gpu_worker_health()
    active_job = db.query(InferenceJob).filter(
        InferenceJob.case_id == case.id,
        InferenceJob.state.in_(list(ACTIVE_STATES)),
    ).order_by(InferenceJob.created_at.desc()).first()
    if active_job:
        if reconcile_stale_job(
            active_job,
            worker_available=bool(worker_health.get("available")),
        ):
            db.commit()
            revoke_stale_delivery(active_job)
            # Reacquire the case lock after persisting the repair. Another
            # request may have started a replacement while the lock was
            # released; reuse it instead of creating a duplicate job.
            case = db.query(Case).filter(
                Case.id == inference_data.case_id,
                Case.user_id == current_user.id,
            ).with_for_update().first()
            replacement = db.query(InferenceJob).filter(
                InferenceJob.case_id == case.id,
                InferenceJob.state.in_(list(ACTIVE_STATES)),
            ).order_by(InferenceJob.created_at.desc()).first()
            if replacement:
                return InferenceResponse(job_id=replacement.id)
        else:
            return InferenceResponse(job_id=active_job.id)

    if not inference_data.force_rerun:
        completed_job = db.query(InferenceJob).filter(
            InferenceJob.case_id == case.id,
            InferenceJob.state == JobState.DONE,
        ).order_by(InferenceJob.completed_at.desc()).first()
        if completed_job:
            result_exists = db.query(InferenceResult).filter(
                InferenceResult.job_id == completed_job.id,
            ).first()
            if result_exists:
                return InferenceResponse(job_id=completed_job.id)

    require_ready_gpu_worker(worker_health)
    
    # Create inference job
    job = InferenceJob(
        case_id=case.id,
        state=JobState.QUEUED,
        progress=0.0
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Start Celery task
    try:
        task = run_inference.delay(job.id, case.id)
        job.celery_task_id = task.id
        db.commit()
    except Exception as exc:
        logger.exception("Unable to publish inference job %s", job.id)
        job.state = JobState.ERROR
        job.progress = 1.0
        job.error_message = (
            "The analysis could not be queued. Your uploaded case is preserved; "
            "please retry shortly."
        )
        job.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=job.error_message,
            headers={"Retry-After": "30"},
        ) from exc
    
    # Log audit event
    log_audit_event(
        db=db,
        user_id=current_user.id,
        action="run",
        resource_type="inference",
        resource_id=job.id,
        details={
            "case_id": case.id,
            "force_rerun": inference_data.force_rerun,
        },
        ip_address=request.client.host if request.client else None
    )
    
    return InferenceResponse(job_id=job.id)


@router.get("/capacity")
def get_inference_capacity(
    db: Session = Depends(get_db),
    _current_user = Depends(get_current_user_dependency),
):
    health = get_gpu_worker_health()
    return {
        "available": bool(health.get("available")),
        "queued_jobs": db.query(InferenceJob).filter(
            InferenceJob.state == JobState.QUEUED,
        ).count(),
        "running_jobs": db.query(InferenceJob).filter(
            InferenceJob.state == JobState.RUNNING,
        ).count(),
        "reason": health.get("reason"),
    }


@router.get("/{job_id}/status", response_model=InferenceStatusResponse)
def get_inference_status(
    job_id: int,
    case_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dependency)
):
    """Get the status of an inference job"""
    job = db.query(InferenceJob).filter(InferenceJob.id == job_id).first()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    # Verify case ownership
    if job.case.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

    if case_id is not None and job.case_id != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found for this case",
        )

    worker_health = get_gpu_worker_health()
    if reconcile_stale_job(
        job,
        worker_available=bool(worker_health.get("available")),
    ):
        db.commit()
        revoke_stale_delivery(job)

    is_terminal = job.state in TERMINAL_STATES
    queue_position = None
    if job.state == JobState.QUEUED:
        queue_position = db.query(InferenceJob).filter(
            InferenceJob.state == JobState.QUEUED,
            InferenceJob.created_at <= job.created_at,
        ).count()
    
    return InferenceStatusResponse(
        case_id=job.case_id,
        state=job.state,
        progress=1.0 if is_terminal else job.progress,
        error_message=job.error_message,
        is_terminal=is_terminal,
        can_cancel=job.state in [JobState.QUEUED, JobState.RUNNING],
        **timing_for_job(job),
        queue_position=queue_position,
        worker_available=bool(worker_health.get("available")),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )


@router.post("/{job_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_inference(
    job_id: int,
    case_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dependency)
):
    """Cancel a running inference job"""
    job = db.query(InferenceJob).filter(InferenceJob.id == job_id).first()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    # Verify case ownership
    if job.case.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

    if case_id is not None and job.case_id != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found for this case",
        )
    
    if job.state in TERMINAL_STATES:
        return {
            "message": f"Inference job is already in terminal state: {job.state.value}",
            "state": job.state,
            "can_cancel": False,
        }

    # Only cancel if queued or running
    if job.state not in [JobState.QUEUED, JobState.RUNNING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in {job.state} state"
        )
    
    # Revoke Celery task
    if job.celery_task_id:
        # The CUDA-safe solo worker cannot terminate one task without killing
        # the whole worker and forcing an expensive model reload. Revocation
        # prevents queued delivery; a running task observes the terminal DB
        # state before publishing any result.
        celery_app.control.revoke(job.celery_task_id, terminate=False)
    
    job.state = JobState.ERROR
    job.error_message = "Cancelled by user"
    job.progress = 1.0
    job.completed_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Job cancelled successfully", "state": job.state, "can_cancel": False}
