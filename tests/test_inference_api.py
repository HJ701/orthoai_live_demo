import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user_dependency
from app.api.routes import inference as inference_routes
from app.database import Base, get_db
from app.main import app
from app.models import Case, Image, InferenceJob, JobState, User


class FakeTask:
    id = "fake-celery-task"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'inference.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    user = User(email="infer@example.com", is_active=True, terms_accepted=True)
    db.add(user)
    db.flush()
    case = Case(
        user_id=user.id,
        consent_checked=True,
        patient_id="PAT-INF",
        title="Inference case",
    )
    db.add(case)
    db.flush()
    db.add(
        Image(
            case_id=case.id,
            filename="front.jpg",
            file_path="cases/front.jpg",
            file_size=1024,
            content_type="image/jpeg",
        )
    )
    db.commit()
    user_id = user.id
    case_id = case.id
    db.close()

    def fake_delay(_job_id, _case_id):
        return FakeTask()

    monkeypatch.setattr(inference_routes.run_inference, "delay", fake_delay)

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
        test_client.case_id = case_id
        test_client.db_factory = TestingSessionLocal
        yield test_client
    app.dependency_overrides.clear()


def test_start_inference_reuses_active_job(client):
    first = client.post("/api/v1/inference", json={"case_id": client.case_id})
    assert first.status_code == 201
    first_job_id = first.json()["job_id"]

    second = client.post("/api/v1/inference", json={"case_id": client.case_id})
    assert second.status_code == 201
    assert second.json()["job_id"] == first_job_id


def test_inference_status_includes_timing_fields(client):
    created = client.post("/api/v1/inference", json={"case_id": client.case_id})
    job_id = created.json()["job_id"]

    status = client.get(f"/api/v1/inference/{job_id}/status?case_id={client.case_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["queue_seconds"] is not None
    assert body["total_seconds"] is not None
    assert body["run_seconds"] is None


def test_done_job_with_results_is_reused(client):
    created = client.post("/api/v1/inference", json={"case_id": client.case_id})
    assert created.status_code == 201

    db = client.db_factory()
    try:
        job = db.query(InferenceJob).filter(InferenceJob.case_id == client.case_id).first()
        job.state = JobState.DONE
        job.progress = 1.0
        job.started_at = dt.datetime.utcnow()
        job.completed_at = dt.datetime.utcnow()
        from app.models import InferenceResult

        db.add(
            InferenceResult(
                job_id=job.id,
                model_version="test-model",
                findings="{}",
                summary="Done",
            )
        )
        db.commit()
        job_id = job.id
    finally:
        db.close()

    next_run = client.post("/api/v1/inference", json={"case_id": client.case_id})
    assert next_run.status_code == 201
    assert next_run.json()["job_id"] == job_id
