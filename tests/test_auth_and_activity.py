import datetime as dt
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user_dependency
from app.api.routes import clinical
from app.database import Base, get_db
from app.main import app
from app.models import AuditLog, Case, InferenceJob, InferenceResult, JobState, User


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
    user = User(
        email="profile@example.com",
        full_name="Profile User",
        is_active=True,
        terms_accepted=True,
        last_login_at=dt.datetime.utcnow(),
    )
    db.add(user)
    db.flush()
    case = Case(
        user_id=user.id,
        consent_checked=True,
        patient_id="PAT-100",
        title="Profile case",
    )
    db.add(case)
    db.flush()
    job = InferenceJob(
        case_id=case.id,
        state=JobState.DONE,
        progress=1.0,
        completed_at=dt.datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    db.add(
        InferenceResult(
            job_id=job.id,
            model_version="test-model",
            findings=json.dumps({"prediction": {"predicted_class": "0"}}),
            summary="Completed profile diagnosis.",
        )
    )
    db.add(
        AuditLog(
            user_id=user.id,
            action="view",
            resource_type="case",
            resource_id=case.id,
            details=json.dumps({"path": f"/api/v1/cases/{case.id}/results"}),
            ip_address="127.0.0.1",
        )
    )
    db.commit()
    user_id = user.id
    case_id = case.id
    db.close()

    clinical.init_clinical_db()
    with sqlite3.connect(clinical.DB_PATH) as conn:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO clinical_cases
                (orthoai_case_id, created_at, updated_at, site, case_id,
                 m_class, dhc, rec_opg, rec_photo, rec_other, high_need,
                 ai_class, ai_dhc, class_match)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                now,
                now,
                "DEMO",
                "VAL-100",
                "Class I",
                3,
                1,
                1,
                0,
                0,
                "Class I",
                3,
                1,
            ),
        )
        conn.commit()

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
        yield test_client
    app.dependency_overrides.clear()


def test_register_returns_existing_email_user(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'register.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            created = test_client.post(
                "/api/v1/auth/register",
                json={"email": "USER@example.com", "full_name": "Registered User"},
            )
            assert created.status_code == 201
            assert created.json()["email"] == "user@example.com"

            existing = test_client.post(
                "/api/v1/auth/register",
                json={"email": "user@example.com", "full_name": "Registered User"},
            )
            assert existing.status_code == 200
            assert existing.json()["id"] == created.json()["id"]
    finally:
        app.dependency_overrides.clear()


def test_sso_providers_report_unconfigured_status(client):
    res = client.get("/api/v1/auth/sso/providers")
    assert res.status_code == 200
    providers = {item["provider"]: item for item in res.json()["providers"]}
    assert providers["google"]["enabled"] is False

    login = client.get("/api/v1/auth/sso/google/login")
    assert login.status_code == 503
    assert "not configured" in login.json()["detail"]


def test_user_activity_returns_real_profile_audit_and_validation(client):
    res = client.get("/api/v1/users/activity")
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["email"] == "profile@example.com"
    assert body["user"]["full_name"] == "Profile User"
    assert body["case_count"] == 1
    assert body["completed_diagnoses"] == 1
    assert body["clinical_validation_count"] == 1
    assert body["clinical_validations"][0]["case_id"] == "VAL-100"
    assert body["audit_logs"][0]["details"]["path"].startswith("/api/v1/cases/")
