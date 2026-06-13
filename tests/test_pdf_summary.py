import datetime as dt
import json
from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user_dependency
from app.api.routes import results as results_routes
from app.core.pdf_generator import generate_pdf_summary
from app.core.security import get_current_active_user
from app.database import Base, get_db
from app.main import app
from app.models import (
    Case,
    Finding,
    Image,
    ImageEvidence,
    InferenceJob,
    InferenceResult,
    JobState,
    User,
)


def test_generate_pdf_summary_returns_clinician_report_pdf():
    generated = generate_pdf_summary(
        case_id=42,
        model_version="v1.0.0",
        findings={
            "total_images": 2,
            "prediction": {
                "predicted_class": "Class II div 1",
                "confidence": 0.91,
            },
            "findings": [
                {
                    "type": "Class II div 1",
                    "confidence": 0.91,
                    "factor": "multimodal_prediction",
                }
            ],
            "timings": {
                "runtime_load_seconds": 0.01,
                "image_load_seconds": 0.42,
                "model_predict_seconds": 0.78,
                "total_inference_seconds": 1.21,
            },
        },
        summary="Processed 2 image(s). Predicted class: Class II div 1 with 91.00% confidence.",
        confidences={"image_1": 0.91, "image_2": 0.88},
        per_image_evidence=[
            {
                "image_id": 1,
                "filename": "opg.jpg",
                "confidence": 0.91,
                "findings": {
                    "detections": [
                        {
                            "type": "Class II div 1",
                            "confidence": 0.91,
                            "factor": "multimodal_prediction",
                        }
                    ]
                },
            }
        ],
        case_metadata={
            "title": "Routine orthodontic assessment",
            "patient_id": "PT-123456",
            "clinic_location": "Abu Dhabi",
            "created_at": dt.datetime(2026, 6, 13, 10, 30, tzinfo=dt.timezone.utc),
        },
        job_metadata={
            "job_id": 34,
            "completed_at": dt.datetime(2026, 6, 13, 10, 31, tzinfo=dt.timezone.utc),
        },
    )

    data = generated.getvalue()
    assert data.startswith(b"%PDF")
    assert len(data) > 4_000


def test_download_pdf_summary_passes_overall_findings_and_case_metadata(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pdf.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    user = User(email="pdf@example.com", is_active=True, terms_accepted=True)
    db.add(user)
    db.flush()
    case = Case(
        user_id=user.id,
        consent_checked=True,
        patient_id="PAT-PDF",
        title="PDF report case",
        clinic_location="Dubai",
        note="No PHI names included.",
        tags=["OPG (Panoramic)", "RGB Intra-oral"],
    )
    db.add(case)
    db.flush()
    image = Image(
        case_id=case.id,
        filename="opg.jpg",
        file_path="cases/opg.jpg",
        file_size=2048,
        content_type="image/jpeg",
    )
    db.add(image)
    db.flush()
    job = InferenceJob(
        case_id=case.id,
        state=JobState.DONE,
        progress=1.0,
        started_at=dt.datetime.utcnow(),
        completed_at=dt.datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    result = InferenceResult(
        job_id=job.id,
        model_version="test-model",
        findings=json.dumps(
            {
                "prediction": {
                    "predicted_class": "Class III",
                    "confidence": 0.77,
                },
                "findings": [{"type": "Class III", "confidence": 0.77}],
            }
        ),
        summary="Processed 1 image(s). Predicted class: Class III with 77.00% confidence.",
    )
    db.add(result)
    db.flush()
    evidence = ImageEvidence(result_id=result.id, image_id=image.id, confidence=0.66)
    db.add(evidence)
    db.flush()
    db.add(
        Finding(
            image_evidence_id=evidence.id,
            type="Class I",
            confidence=0.66,
            factor="image_evidence",
        )
    )
    db.commit()
    user_id = user.id
    case_id = case.id
    job_id = job.id
    db.close()

    captured = {}

    def fake_generate_pdf_summary(**kwargs):
        captured.update(kwargs)
        return BytesIO(b"%PDF-1.4\n% OrthoAI test report\n")

    monkeypatch.setattr(results_routes, "generate_pdf_summary", fake_generate_pdf_summary)
    monkeypatch.setattr(results_routes, "sign_pdf", lambda pdf_buffer: pdf_buffer)

    def override_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        session = TestingSessionLocal()
        try:
            return session.get(User, user_id)
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_dependency] = override_user
    app.dependency_overrides[get_current_active_user] = override_user
    try:
        with TestClient(app) as test_client:
            response = test_client.get(f"/api/v1/cases/{case_id}/summary.pdf")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert captured["findings"]["prediction"]["predicted_class"] == "Class III"
    assert captured["per_image_evidence"][0]["findings"]["detections"][0]["type"] == "Class I"
    assert captured["case_metadata"]["patient_id"] == "PAT-PDF"
    assert captured["case_metadata"]["clinic_location"] == "Dubai"
    assert captured["job_metadata"]["job_id"] == job_id
