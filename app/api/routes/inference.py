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
from datetime import datetime, timezone

router = APIRouter()


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
    ).first()
    
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

    active_job = db.query(InferenceJob).filter(
        InferenceJob.case_id == case.id,
        InferenceJob.state.in_(list(ACTIVE_STATES)),
    ).order_by(InferenceJob.created_at.desc()).first()
    if active_job:
        return InferenceResponse(job_id=active_job.id)

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
    task = run_inference.delay(job.id, case.id)
    job.celery_task_id = task.id
    db.commit()
    
    # Log audit event
    log_audit_event(
        db=db,
        user_id=current_user.id,
        action="run",
        resource_type="inference",
        resource_id=job.id,
        details={"case_id": case.id},
        ip_address=request.client.host if request.client else None
    )
    
    return InferenceResponse(job_id=job.id)


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

    is_terminal = job.state in TERMINAL_STATES
    
    return InferenceStatusResponse(
        case_id=job.case_id,
        state=job.state,
        progress=1.0 if is_terminal else job.progress,
        error_message=job.error_message,
        is_terminal=is_terminal,
        can_cancel=job.state in [JobState.QUEUED, JobState.RUNNING],
        **timing_for_job(job),
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
        celery_app.control.revoke(job.celery_task_id, terminate=True)
    
    job.state = JobState.ERROR
    job.error_message = "Cancelled by user"
    job.progress = 1.0
    job.completed_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Job cancelled successfully", "state": job.state, "can_cancel": False}
