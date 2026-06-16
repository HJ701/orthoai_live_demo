from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request, Response
from sqlalchemy.orm import Session
from typing import List, Dict
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime
import uuid
from app.database import get_db
from app.models import Case, Image, InferenceJob, JobState
from app.schemas import CaseCreate, CaseResponse, ImageUploadResponse, ImageResponse, CaseNoteCreate, CaseNoteResponse
from app.api.deps import get_current_user_dependency, get_case_dependency
from app.core.audit import log_audit_event
from app.core.s3_storage import delete_file_from_s3, upload_file_to_s3, download_file_from_s3
from app.celery_app import celery_app
from app.config import settings
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=List[CaseResponse])
def list_cases(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dependency)
):
    """List all cases for the current user"""
    cases = db.query(Case).filter(Case.user_id == current_user.id).order_by(Case.created_at.desc()).all()
    
    # Get case IDs
    case_ids = [case.id for case in cases]
    
    # Get latest inference job state per case
    # Query all jobs for these cases, ordered by created_at DESC
    # Then group by case_id to get the latest one per case
    status_map: Dict[int, JobState] = {}
    if case_ids:
        # Get all jobs for these cases, ordered by created_at DESC
        all_jobs = db.query(InferenceJob).filter(
            InferenceJob.case_id.in_(case_ids)
        ).order_by(InferenceJob.created_at.desc()).all()
        
        # Build mapping, keeping only the first (latest) job per case_id
        for job in all_jobs:
            if job.case_id not in status_map:
                status_map[job.case_id] = job.state
    
    # Build response with status
    result = []
    for case in cases:
        case_dict = {
            "id": case.id,
            "user_id": case.user_id,
            "consent_checked": case.consent_checked,
            "patient_id": case.patient_id,
            "title": case.title,
            "clinic_location": case.clinic_location,
            "note": case.note,
            "tags": case.tags if case.tags else [],
            "status": status_map.get(case.id),
            "created_at": case.created_at
        }
        result.append(CaseResponse(**case_dict))
    
    return result


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    request: Request,
    case_data: CaseCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dependency)
):
    """Create a new case"""
    # Generate default patient_id if not provided
    patient_id = case_data.patient_id
    if not patient_id:
        # Use UUID for uniqueness: PATIENT_{uuid}
        patient_id = f"PATIENT_{uuid.uuid4().hex[:8].upper()}"
    
    # Generate default title if not provided
    title = case_data.title
    if not title:
        # Use timestamp-based title: Case {date}
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        title = f"Case {timestamp}"
    
    case = Case(
        user_id=current_user.id,
        consent_checked=case_data.consent_checked,
        patient_id=patient_id,
        title=title,
        clinic_location=case_data.clinic_location,
        tags=case_data.tags if case_data.tags else None,
        note=case_data.note
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    
    # Log audit event
    log_audit_event(
        db=db,
        user_id=current_user.id,
        action="create",
        resource_type="case",
        resource_id=case.id,
        ip_address=request.client.host if request.client else None
    )
    
    return case


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    case: Case = Depends(get_case_dependency),
):
    """Get one case for the current user."""
    latest_job = db.query(InferenceJob).filter(
        InferenceJob.case_id == case_id
    ).order_by(InferenceJob.created_at.desc()).first()

    return CaseResponse(
        id=case.id,
        user_id=case.user_id,
        consent_checked=case.consent_checked,
        patient_id=case.patient_id,
        title=case.title,
        clinic_location=case.clinic_location,
        note=case.note,
        tags=case.tags if case.tags else [],
        status=latest_job.state if latest_job else None,
        created_at=case.created_at,
    )


@router.delete("/{case_id}", status_code=status.HTTP_200_OK)
def delete_case(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
    case: Case = Depends(get_case_dependency),
):
    """Delete a case owned by the current user, including jobs and uploaded images."""
    jobs = db.query(InferenceJob).filter(InferenceJob.case_id == case_id).all()
    for job in jobs:
        if job.state in [JobState.QUEUED, JobState.RUNNING] and job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True)

    images = db.query(Image).filter(Image.case_id == case_id).all()
    for image in images:
        if image.file_path:
            delete_file_from_s3(image.file_path)

    log_audit_event(
        db=db,
        user_id=case.user_id,
        action="delete",
        resource_type="case",
        resource_id=case_id,
        ip_address=request.client.host if request.client else None,
    )

    db.delete(case)
    db.commit()

    return {"message": "Case deleted successfully", "case_id": case_id}


@router.post("/{case_id}/images", response_model=ImageUploadResponse)
def upload_images(
    request: Request,
    case_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    case: Case = Depends(get_case_dependency)
):
    """Upload images for a case"""
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )
    
    max_size_bytes = settings.max_upload_size_mb * 1024 * 1024
    image_ids = []
    
    for file in files:
        # Validate file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning
        
        if file_size > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {file.filename} exceeds maximum size of {settings.max_upload_size_mb}MB"
            )
        
        # Validate content type (basic check)
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {file.filename} is not a valid image"
            )
        
        # Create image record first to get the image_id for S3 key
        image = Image(
            case_id=case_id,
            filename=file.filename,
            file_path="",  # Will be set after S3 upload
            file_size=file_size,
            content_type=file.content_type
        )
        db.add(image)
        db.flush()  # Get the image ID
        
        try:
            # Upload file to S3
            # Reset file pointer to beginning for upload
            file.file.seek(0)
            s3_key = upload_file_to_s3(
                file_obj=file.file,
                case_id=case_id,
                image_id=image.id,
                filename=file.filename,
                content_type=file.content_type
            )
            
            # Update image record with S3 key
            image.file_path = s3_key
            db.flush()
            image_ids.append(image.id)
            
        except (ClientError, BotoCoreError, ValueError) as e:
            # Rollback the image record if S3 upload fails
            db.rollback()
            logger.error(f"Failed to upload {file.filename} to S3: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file {file.filename} to storage"
            )
        
        # Log audit event
        log_audit_event(
            db=db,
            user_id=case.user_id,
            action="upload",
            resource_type="image",
            resource_id=image.id,
            details={"filename": file.filename, "case_id": case_id},
            ip_address=request.client.host if request.client else None
        )
    
    db.commit()

    return ImageUploadResponse(image_ids=image_ids)


@router.get("/{case_id}/images/{image_id}")
def get_case_image(
    case_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    case: Case = Depends(get_case_dependency),
):
    """Stream a case image (auth + ownership enforced). Used by the results
    'Evidence & Visuals' section. Reads from S3 or local storage."""
    image = db.query(Image).filter(
        Image.id == image_id,
        Image.case_id == case_id,
    ).first()
    if not image or not image.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    try:
        data = download_file_from_s3(image.file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image data not found")
    except (ClientError, BotoCoreError, ValueError) as e:
        logger.error("Failed to read image %s: %s", image_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read image from storage",
        )

    return Response(
        content=data,
        media_type=image.content_type or "image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/{case_id}/notes", response_model=CaseNoteResponse, status_code=status.HTTP_201_CREATED)
def add_note(
    request: Request,
    case_id: int,
    note_data: CaseNoteCreate,
    db: Session = Depends(get_db),
    case: Case = Depends(get_case_dependency),
    current_user = Depends(get_current_user_dependency)
):
    """Add clinician notes to a case"""
    from app.models import CaseNote
    
    note = CaseNote(
        case_id=case_id,
        content=note_data.content,
        created_by=current_user.id
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    
    # Log audit event
    log_audit_event(
        db=db,
        user_id=current_user.id,
        action="note",
        resource_type="case",
        resource_id=case_id,
        ip_address=request.client.host if request.client else None
    )
    
    return note

