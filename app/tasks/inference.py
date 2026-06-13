from celery import Task
from celery.signals import worker_process_init, worker_ready
from sqlalchemy.orm import Session
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import InferenceJob, InferenceResult, ImageEvidence, Finding, Case, Image, JobState
from app.config import settings
from app.core.model_inference import get_model_runtime, predict_case_with_timings
import json
from datetime import datetime
import logging
import time


logger = logging.getLogger(__name__)


_model_preloaded = False


def preload_model_runtime() -> None:
    global _model_preloaded
    if _model_preloaded or not settings.preload_model_runtime:
        return

    start = time.perf_counter()
    try:
        get_model_runtime()
        _model_preloaded = True
        logger.info("Preloaded OrthoAI model runtime in %.3fs", time.perf_counter() - start)
    except Exception:
        logger.exception("Failed to preload OrthoAI model runtime")


@worker_process_init.connect
def preload_model_on_worker_process_init(**_kwargs):
    preload_model_runtime()


@worker_ready.connect
def preload_model_on_worker_ready(**_kwargs):
    preload_model_runtime()


def mock_prediction(patient_id: str, images: list[Image]) -> tuple[dict, dict]:
    start = time.perf_counter()
    class_names = ["Class I", "Class II div 1", "Class III"]
    predicted_index = len(images) % len(class_names)
    confidence = 0.82
    prediction = {
        "patient_id": patient_id,
        "predicted_class": class_names[predicted_index],
        "predicted_index": predicted_index,
        "confidence": confidence,
        "probabilities": [
            {
                "class_name": class_name,
                "probability": confidence if index == predicted_index else round((1 - confidence) / 2, 3),
            }
            for index, class_name in enumerate(class_names)
        ],
        "images_used": [
            {
                "source": image.filename,
                "modality": "xray" if "opg" in image.filename.lower() else "rgb",
                "view": "opg" if "opg" in image.filename.lower() else "frontal",
            }
            for image in images
        ],
        "model": {
            "experiment_id": "local-demo",
            "experiment_name": "Mock OrthoAI Runtime",
            "device": "cpu",
        },
    }
    return prediction, {
        "runtime_load_seconds": 0.0,
        "image_load_seconds": 0.0,
        "model_predict_seconds": round(time.perf_counter() - start, 3),
        "total_inference_seconds": round(time.perf_counter() - start, 3),
    }


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
    Run multimodal OrthoAI inference on a case's images.
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
            job.progress = 1.0
            job.completed_at = datetime.utcnow()
            db.commit()
            return {"error": "Case not found"}
        
        images = db.query(Image).filter(Image.case_id == case_id).all()
        if not images:
            job.state = JobState.ERROR
            job.error_message = "No images found for case"
            job.progress = 1.0
            job.completed_at = datetime.utcnow()
            db.commit()
            return {"error": "No images found"}
        
        job.progress = 0.25
        db.commit()

        total_images = len(images)
        if settings.dev_mock_inference and settings.environment.lower() != "production":
            prediction, timings = mock_prediction(case.patient_id or f"case-{case.id}", images)
        else:
            prediction, timings = predict_case_with_timings(
                case.patient_id or f"case-{case.id}",
                images,
            )
        logger.info(
            "Inference job %s timings: runtime_load=%.3fs image_load=%.3fs model_predict=%.3fs total=%.3fs",
            job_id,
            timings["runtime_load_seconds"],
            timings["image_load_seconds"],
            timings["model_predict_seconds"],
            timings["total_inference_seconds"],
        )

        job.progress = 0.85
        db.commit()

        confidence = float(prediction.get("confidence", 0.0))
        predicted_class = str(prediction.get("predicted_class", "unknown"))
        images_used = prediction.get("images_used", [])
        confidences = {f"image_{image.id}": confidence for image in images}

        overall_findings = {
            "total_images": total_images,
            "processed_at": datetime.utcnow().isoformat(),
            "prediction": prediction,
            "findings": [
                {
                    "type": predicted_class,
                    "confidence": confidence,
                    "probabilities": prediction.get("probabilities", []),
                }
            ],
            "images_used": images_used,
            "timings": timings,
            "model_version": settings.model_version
        }

        summary = (
            f"Processed {total_images} image(s). "
            f"Predicted class: {predicted_class} "
            f"with {confidence:.2%} confidence."
        )

        # Create inference result first
        result = InferenceResult(
            job_id=job_id,
            model_version=settings.model_version,
            findings=json.dumps(overall_findings),
            summary=summary
        )
        db.add(result)
        db.flush()  # Get the result ID
        
        # Create per-image evidence rows for compatibility with the existing results API.
        for image in images:
            evidence = ImageEvidence(
                result_id=result.id,
                image_id=image.id,
                findings=None,  # No longer storing JSON findings
                confidence=confidence
            )
            db.add(evidence)
            db.flush()  # Get the evidence ID

            finding = Finding(
                image_evidence_id=evidence.id,
                type=predicted_class,
                confidence=confidence,
                location=None,
                factor="multimodal_prediction"
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
        logger.exception("Inference job %s failed for case %s", job_id, case_id)
        # Update job to error state
        job = db.query(InferenceJob).filter(InferenceJob.id == job_id).first()
        if job:
            job.state = JobState.ERROR
            job.error_message = str(e)
            job.progress = 1.0
            job.completed_at = datetime.utcnow()
            db.commit()
        return {"error": str(e)}
