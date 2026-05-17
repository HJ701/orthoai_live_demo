from celery import Task
from sqlalchemy.orm import Session
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import InferenceJob, InferenceResult, ImageEvidence, Finding, Case, Image, JobState
from app.config import settings
import json
from datetime import datetime


class DatabaseTask(Task):
    """Custom task class that handles database sessions"""
    _db = None

    @property
    def db(self):
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(bind=True, base=DatabaseTask)
def run_inference(self, job_id: int, case_id: int):
    """
    Run inference on a case's images
    This is a placeholder - replace with actual ML model inference
    """
    db = self.db
    
    try:
        # Update job state to running
        job = db.query(InferenceJob).filter(InferenceJob.id == job_id).first()
        if not job:
            return {"error": "Job not found"}
        
        job.state = JobState.RUNNING
        job.started_at = datetime.utcnow()
        job.progress = 0.1
        db.commit()
        
        # Get case and images
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            job.state = JobState.ERROR
            job.error_message = "Case not found"
            db.commit()
            return {"error": "Case not found"}
        
        images = db.query(Image).filter(Image.case_id == case_id).all()
        if not images:
            job.state = JobState.ERROR
            job.error_message = "No images found for case"
            db.commit()
            return {"error": "No images found"}
        
        # Simulate inference progress
        total_images = len(images)
        findings_list = []
        confidences = {}
        per_image_evidence = []
        evidence_data = []  # Store evidence data to create after result is created
        
        for idx, image in enumerate(images):
            # Simulate processing each image
            # In production, call your ML model here
            progress = 0.1 + (idx + 1) / total_images * 0.8
            job.progress = progress
            db.commit()
            
            # Mock inference results
            mock_detections = [
                {"type": "lesion", "confidence": 0.85, "location": "upper_left", "factor": "high"},
                {"type": "normal", "confidence": 0.92, "location": "center", "factor": "low"}
            ]
            
            mock_confidence = 0.85 + (idx * 0.05) % 0.15
            
            # Store evidence data for later creation
            evidence_data.append({
                "image_id": image.id,
                "detections": mock_detections,
                "confidence": mock_confidence
            })
            
            # Build findings dict for overall findings (backward compatibility)
            mock_findings = {
                "image_id": image.id,
                "detections": mock_detections
            }
            findings_list.append(mock_findings)
            confidences[f"image_{image.id}"] = mock_confidence
            per_image_evidence.append({
                "image_id": image.id,
                "filename": image.filename,
                "findings": mock_findings,
                "confidence": mock_confidence
            })
        
        # Create overall findings
        overall_findings = {
            "total_images": total_images,
            "processed_at": datetime.utcnow().isoformat(),
            "findings": findings_list,
            "model_version": settings.model_version
        }
        
        # Create summary
        summary = f"Processed {total_images} image(s). Found {len(findings_list)} sets of findings with average confidence of {sum(confidences.values()) / len(confidences):.2%}."
        
        # Create inference result first
        result = InferenceResult(
            job_id=job_id,
            model_version=settings.model_version,
            findings=json.dumps(overall_findings),
            summary=summary
        )
        db.add(result)
        db.flush()  # Get the result ID
        
        # Now create image evidence with Finding records
        for evidence_info in evidence_data:
            evidence = ImageEvidence(
                result_id=result.id,
                image_id=evidence_info["image_id"],
                findings=None,  # No longer storing JSON findings
                confidence=evidence_info["confidence"]
            )
            db.add(evidence)
            db.flush()  # Get the evidence ID
            
            # Create Finding records for each detection
            for detection in evidence_info["detections"]:
                finding = Finding(
                    image_evidence_id=evidence.id,
                    type=detection["type"],
                    confidence=detection["confidence"],
                    location=detection.get("location"),
                    factor=detection.get("factor")
                )
                db.add(finding)
        
        # Update job to done
        job.state = JobState.DONE
        job.progress = 1.0
        job.completed_at = datetime.utcnow()
        db.commit()
        
        return {
            "status": "success",
            "job_id": job_id,
            "result_id": result.id
        }
        
    except Exception as e:
        # Update job to error state
        job = db.query(InferenceJob).filter(InferenceJob.id == job_id).first()
        if job:
            job.state = JobState.ERROR
            job.error_message = str(e)
            db.commit()
        return {"error": str(e)}

