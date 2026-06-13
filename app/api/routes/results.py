from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
import json
from app.database import get_db
from app.models import InferenceResult, InferenceJob, ImageEvidence, Finding, Image, JobState
from app.schemas import CaseResultsResponse, ImageEvidenceResponse
from app.api.deps import get_current_user_dependency, get_case_dependency
from app.core.pdf_generator import generate_pdf_summary, sign_pdf
from app.core.audit import log_audit_event
from app.config import settings

router = APIRouter()


@router.get("/cases/{case_id}/results", response_model=CaseResultsResponse)
def get_case_results(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
    case = Depends(get_case_dependency)
):
    """Get results for a case"""
    # Find the latest completed inference job
    job = db.query(InferenceJob).filter(
        InferenceJob.case_id == case_id,
        InferenceJob.state == JobState.DONE
    ).order_by(InferenceJob.completed_at.desc()).first()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed inference results found for this case"
        )
    
    result = db.query(InferenceResult).filter(InferenceResult.job_id == job.id).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Results not found"
        )
    
    # Get all image evidence
    evidence_records = db.query(ImageEvidence).filter(ImageEvidence.result_id == result.id).all()
    
    # Build per-image evidence
    per_image_evidence = []
    confidences = {}
    
    for evidence in evidence_records:
        image = db.query(Image).filter(Image.id == evidence.image_id).first()
        
        # Get Finding records for this evidence
        findings_records = db.query(Finding).filter(Finding.image_evidence_id == evidence.id).all()
        
        # Build findings dictionary from Finding records
        findings = {
            "image_id": evidence.image_id,
            "detections": [
                {
                    "type": f.type,
                    "confidence": f.confidence,
                    "location": f.location,
                    "factor": f.factor
                }
                for f in findings_records
            ]
        }
        
        per_image_evidence.append(ImageEvidenceResponse(
            image_id=evidence.image_id,
            filename=image.filename if image else "unknown",
            findings=findings,
            confidence=evidence.confidence
        ))
        
        confidences[f"image_{evidence.image_id}"] = evidence.confidence
    
    # Parse findings
    findings_dict = json.loads(result.findings) if result.findings else {}
    
    # Log audit event
    log_audit_event(
        db=db,
        user_id=case.user_id,
        action="view",
        resource_type="case",
        resource_id=case_id,
        ip_address=request.client.host if request.client else None
    )
    
    return CaseResultsResponse(
        case_id=case_id,
        model_version=result.model_version,
        findings=findings_dict,
        summary=result.summary or "",
        confidences=confidences,
        per_image_evidence=per_image_evidence,
        created_at=result.created_at
    )


@router.get("/cases/{case_id}/summary.pdf")
def download_pdf_summary(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
    case = Depends(get_case_dependency)
):
    """Download signed PDF summary for a case"""
    # Get results
    job = db.query(InferenceJob).filter(
        InferenceJob.case_id == case_id,
        InferenceJob.state == JobState.DONE
    ).order_by(InferenceJob.completed_at.desc()).first()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed inference results found for this case"
        )
    
    result = db.query(InferenceResult).filter(InferenceResult.job_id == job.id).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Results not found"
        )
    
    # Get evidence and build data structures
    evidence_records = db.query(ImageEvidence).filter(ImageEvidence.result_id == result.id).all()
    
    findings_dict = json.loads(result.findings) if result.findings else {}
    confidences = {f"image_{e.image_id}": e.confidence for e in evidence_records}
    
    per_image_evidence = []
    for evidence in evidence_records:
        image = db.query(Image).filter(Image.id == evidence.image_id).first()
        
        # Get Finding records for this evidence
        findings_records = db.query(Finding).filter(Finding.image_evidence_id == evidence.id).all()
        
        # Build findings dictionary from Finding records
        evidence_findings = {
            "image_id": evidence.image_id,
            "detections": [
                {
                    "type": f.type,
                    "confidence": f.confidence,
                    "location": f.location,
                    "factor": f.factor
                }
                for f in findings_records
            ]
        }
        
        per_image_evidence.append({
            "image_id": evidence.image_id,
            "filename": image.filename if image else "unknown",
            "findings": evidence_findings,
            "confidence": evidence.confidence
        })
    
    # Generate PDF
    pdf_buffer = generate_pdf_summary(
        case_id=case_id,
        model_version=result.model_version,
        findings=findings_dict,
        summary=result.summary or "",
        confidences=confidences,
        per_image_evidence=per_image_evidence,
        case_metadata={
            "title": case.title,
            "patient_id": case.patient_id,
            "clinic_location": case.clinic_location,
            "note": case.note,
            "tags": case.tags,
            "created_at": case.created_at,
        },
        job_metadata={
            "job_id": job.id,
            "state": job.state.value if hasattr(job.state, "value") else str(job.state),
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
        },
    )
    
    # Sign PDF
    signed_pdf = sign_pdf(pdf_buffer)
    
    # Log audit event
    log_audit_event(
        db=db,
        user_id=case.user_id,
        action="download",
        resource_type="pdf",
        resource_id=case_id,
        ip_address=request.client.host if request.client else None
    )
    
    return Response(
        content=signed_pdf.read(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=case_{case_id}_summary.pdf"
        }
    )
