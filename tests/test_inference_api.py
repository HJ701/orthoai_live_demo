import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user_dependency
from app.api.routes import inference as inference_routes
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Case, Image, InferenceJob, JobState, User


class FakeTask:
    def __init__(self, task_id: str):
        self.id = task_id


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

    task_counter = 0

    def fake_delay(_job_id, _case_id):
        nonlocal task_counter
        task_counter += 1
        return FakeTask(f"fake-celery-task-{task_counter}")

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


def test_force_rerun_preserves_completed_job_and_creates_a_new_one(client):
    created = client.post("/api/v1/inference", json={"case_id": client.case_id})
    assert created.status_code == 201

    db = client.db_factory()
    try:
        original = db.query(InferenceJob).filter_by(id=created.json()["job_id"]).one()
        original.state = JobState.DONE
        original.progress = 1.0
        original.started_at = dt.datetime.utcnow()
        original.completed_at = dt.datetime.utcnow()
        from app.models import InferenceResult

        db.add(
            InferenceResult(
                job_id=original.id,
                model_version="test-model",
                findings="{}",
                summary="Original preserved result",
            )
        )
        db.commit()
        original_id = original.id
    finally:
        db.close()

    rerun = client.post(
        "/api/v1/inference",
        json={"case_id": client.case_id, "force_rerun": True},
    )
    assert rerun.status_code == 201
    assert rerun.json()["job_id"] != original_id

    db = client.db_factory()
    try:
        assert db.query(InferenceJob).filter_by(id=original_id).one().state == JobState.DONE
        assert db.query(InferenceJob).count() == 2
    finally:
        db.close()


def test_stale_queued_job_is_closed_and_retry_creates_new_job(client, monkeypatch):
    created = client.post("/api/v1/inference", json={"case_id": client.case_id})
    original_id = created.json()["job_id"]

    db = client.db_factory()
    try:
        original = db.get(InferenceJob, original_id)
        original.created_at = dt.datetime.utcnow() - dt.timedelta(hours=2)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(settings, "inference_queued_stale_seconds", 60)
    monkeypatch.setattr(
        inference_routes.celery_app.control,
        "revoke",
        lambda *_args, **_kwargs: None,
    )

    retried = client.post(
        "/api/v1/inference",
        json={"case_id": client.case_id, "force_rerun": True},
    )
    assert retried.status_code == 201
    assert retried.json()["job_id"] != original_id

    db = client.db_factory()
    try:
        original = db.get(InferenceJob, original_id)
        assert original.state == JobState.ERROR
        assert "case is preserved" in original.error_message
    finally:
        db.close()


def test_queue_publish_failure_is_recoverable(client, monkeypatch):
    def fail_publish(*_args, **_kwargs):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(inference_routes.run_inference, "delay", fail_publish)
    response = client.post("/api/v1/inference", json={"case_id": client.case_id})
    assert response.status_code == 503
    assert "case is preserved" in response.json()["detail"]

    db = client.db_factory()
    try:
        job = db.query(InferenceJob).filter_by(case_id=client.case_id).one()
        assert job.state == JobState.ERROR
        assert job.completed_at is not None
    finally:
        db.close()


def test_start_fails_fast_when_no_gpu_worker_is_ready(client, monkeypatch):
    monkeypatch.setattr(
        inference_routes,
        "get_gpu_worker_health",
        lambda: {"available": False, "reason": "no_ready_gpu_worker"},
    )
    response = client.post("/api/v1/inference", json={"case_id": client.case_id})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"

    db = client.db_factory()
    try:
        assert db.query(InferenceJob).count() == 0
    finally:
        db.close()


def test_cases_response_exposes_resume_job_id(client):
    created = client.post("/api/v1/inference", json={"case_id": client.case_id})
    job_id = created.json()["job_id"]

    response = client.get("/api/v1/cases")
    assert response.status_code == 200
    row = response.json()[0]
    assert row["status"] == "queued"
    assert row["latest_job_id"] == job_id
