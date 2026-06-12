import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user_dependency
from app.api.routes import clinical
from app.database import Base, get_db
from app.main import app
from app.models import Case, InferenceJob, InferenceResult, JobState, User


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'app.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    clinical.DB_PATH = str(tmp_path / "clinical.db")

    db = TestingSessionLocal()
    user = User(email="clinician@example.com", is_active=True, terms_accepted=True)
    other_user = User(email="other@example.com", is_active=True, terms_accepted=True)
    db.add_all([user, other_user])
    db.flush()

    completed_case = Case(
        user_id=user.id,
        consent_checked=True,
        patient_id="PAT-001",
        title="Completed diagnosis",
    )
    pending_case = Case(
        user_id=user.id,
        consent_checked=True,
        patient_id="PAT-002",
        title="Pending diagnosis",
    )
    other_case = Case(
        user_id=other_user.id,
        consent_checked=True,
        patient_id="PAT-003",
        title="Other user diagnosis",
    )
    db.add_all([completed_case, pending_case, other_case])
    db.flush()

    completed_job = InferenceJob(
        case_id=completed_case.id,
        state=JobState.DONE,
        progress=1.0,
        completed_at=dt.datetime.utcnow(),
    )
    pending_job = InferenceJob(
        case_id=pending_case.id,
        state=JobState.RUNNING,
        progress=0.5,
    )
    db.add_all([completed_job, pending_job])
    db.flush()
    db.add(
        InferenceResult(
            job_id=completed_job.id,
            model_version="test-model",
            findings=json.dumps(
                {
                    "prediction": {
                        "predicted_class": "0",
                        "confidence": 0.6341,
                        "images_used": ["front.jpg", "opg.jpg"],
                    }
                }
            ),
            summary="Processed 2 image(s). Predicted class: 0 with 63.41% confidence.",
        )
    )
    db.commit()
    user_id = user.id
    completed_id = completed_case.id
    pending_id = pending_case.id
    other_id = other_case.id
    db.close()

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
    with TestClient(app) as test_client:
        test_client.completed_case_id = completed_id
        test_client.pending_case_id = pending_id
        test_client.other_case_id = other_id
        yield test_client
    app.dependency_overrides.clear()


def valid_clinical_payload():
    return {
        "site": "DEMO",
        "case_id": "VALIDATION-001",
        "m_class": "Class I",
        "dhc": 3,
        "ai_class": "Class I",
        "ai_dhc": 3,
        "ai_conf": 63,
        "agree": "Agree",
        "override": "No",
        "useful": 4,
    }


def test_clinical_health_requires_completed_diagnosis_with_results(client):
    ok = client.get(f"/api/v1/clinical/health?source_case_id={client.completed_case_id}")
    assert ok.status_code == 200
    assert ok.json()["diagnosis_complete"] is True

    pending = client.get(f"/api/v1/clinical/health?source_case_id={client.pending_case_id}")
    assert pending.status_code == 403
    assert "Complete the OrthoAI diagnosis" in pending.json()["detail"]

    other_user_case = client.get(f"/api/v1/clinical/health?source_case_id={client.other_case_id}")
    assert other_user_case.status_code == 404


def test_clinical_records_are_scoped_to_the_source_orthoai_case(client):
    created = client.post(
        f"/api/v1/clinical/cases?source_case_id={client.completed_case_id}",
        json=valid_clinical_payload(),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["orthoai_case_id"] == client.completed_case_id
    assert body["class_match"] is True
    assert body["dhc_delta"] == 0

    listed = client.get(
        f"/api/v1/clinical/cases?source_case_id={client.completed_case_id}"
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["case_id"] == "VALIDATION-001"

    stats = client.get(
        f"/api/v1/clinical/stats?source_case_id={client.completed_case_id}"
    )
    assert stats.status_code == 200
    assert stats.json()["n"] == 1
    assert stats.json()["class_agreement_pct"] == 100


def test_clinical_create_rejects_unfinished_or_unowned_source_cases(client):
    pending = client.post(
        f"/api/v1/clinical/cases?source_case_id={client.pending_case_id}",
        json=valid_clinical_payload(),
    )
    assert pending.status_code == 403

    other_user_case = client.post(
        f"/api/v1/clinical/cases?source_case_id={client.other_case_id}",
        json=valid_clinical_payload(),
    )
    assert other_user_case.status_code == 404
