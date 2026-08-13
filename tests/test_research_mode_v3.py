import datetime as dt
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user_dependency
from app.config import settings
from app.core.security import get_current_active_user
from app.database import Base, get_db
from app.main import app
from app.models import (
    Case,
    Image,
    InferenceJob,
    InferenceResult,
    JobState,
    PreAIDecision,
    ResearchEpisode,
    ResearchEpoch,
    ResearchEvent,
    ResearchParticipant,
    ResearchRole,
    ResearchSite,
    ResearchStudy,
    ResearchStudyStatus,
    User,
)


STUDY_CODE = "ORTHOAI-HCI-V3"
TASK_VERSION = "orthoai.malocclusion-decision/1.0.0"


@pytest.fixture()
def research_client(tmp_path):
    original_rate_limit_enabled = settings.rate_limit_enabled
    settings.rate_limit_enabled = False
    engine = create_engine(
        f"sqlite:///{tmp_path / 'research-v3.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    now = dt.datetime.now(dt.timezone.utc)
    db = session_factory()
    users = {}
    for key in ("clinician", "reviewer_1", "reviewer_2", "adjudicator", "admin"):
        user = User(
            email=f"{key}@example.test",
            full_name=key.replace("_", " ").title(),
            is_active=True,
            terms_accepted=True,
        )
        db.add(user)
        db.flush()
        users[key] = user

    study = ResearchStudy(
        code=STUDY_CODE,
        title="Research Mode v3 test",
        protocol_version="test-protocol/1.0",
        consent_version="test-consent/1.0",
        primary_task="malocclusion_classification",
        primary_outcome="Human-AI decision quality",
        status=ResearchStudyStatus.ACTIVE,
        minimum_reference_reviews=2,
        activated_at=now,
        config={"clinical_effect": "shadow_only"},
    )
    db.add(study)
    db.flush()
    site = ResearchSite(
        study_id=study.id,
        code="TEST",
        name="Test site",
        timezone="UTC",
        is_active=True,
    )
    db.add(site)
    db.flush()
    epoch = ResearchEpoch(
        study_id=study.id,
        code="TEST-E1",
        label="Test epoch",
        protocol_version=study.protocol_version,
        task_schema_version=TASK_VERSION,
        ui_version="research-ui/test",
        model_version="test-model",
        deployment_policy_version="shadow-test",
        result_schema_version="test-result/1.0",
        is_active=True,
        starts_at=now,
        config={"score_fusion": "none"},
    )
    db.add(epoch)
    db.flush()

    role_by_key = {
        "clinician": ResearchRole.CLINICIAN,
        "reviewer_1": ResearchRole.REVIEWER,
        "reviewer_2": ResearchRole.REVIEWER,
        "adjudicator": ResearchRole.ADJUDICATOR,
        "admin": ResearchRole.RESEARCH_ADMIN,
    }
    for index, (key, user) in enumerate(users.items(), start=1):
        db.add(
            ResearchParticipant(
                study_id=study.id,
                site_id=site.id,
                user_id=user.id,
                participant_code=f"P-{index:03d}",
                role=role_by_key[key],
                consent_version=study.consent_version,
                consented_at=now,
                is_active=True,
            )
        )

    case = Case(
        user_id=users["clinician"].id,
        consent_checked=True,
        patient_id="PATIENT-MUST-NOT-EXPORT",
        title="Research test case",
    )
    db.add(case)
    db.flush()
    db.add(
        Image(
            case_id=case.id,
            filename="source.jpg",
            file_path="local://tests/source.jpg",
            file_size=100,
            content_type="image/jpeg",
        )
    )
    job = InferenceJob(
        case_id=case.id,
        state=JobState.DONE,
        progress=1.0,
        completed_at=now,
    )
    db.add(job)
    db.flush()
    db.add(
        InferenceResult(
            job_id=job.id,
            model_version="test-model",
            findings=json.dumps(
                {
                    "prediction": {
                        "predicted_class": "Class II div 1",
                        "confidence": 0.81,
                    },
                    "quantitative_summary": {
                        "total_instances": 4,
                        "classes_present": 2,
                    },
                    "models": {},
                }
            ),
            summary="Frozen AI summary that must remain blinded before reveal.",
        )
    )
    db.commit()
    user_ids = {key: value.id for key, value in users.items()}
    case_id = case.id
    db.close()

    active_user = {"id": user_ids["clinician"]}

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        session = session_factory()
        try:
            return session.get(User, active_user["id"])
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_dependency] = override_user
    app.dependency_overrides[get_current_active_user] = override_user
    try:
        with TestClient(app) as client:
            client.active_user = active_user
            client.user_ids = user_ids
            client.case_id = case_id
            client.db_factory = session_factory
            yield client
    finally:
        app.dependency_overrides.clear()
        settings.rate_limit_enabled = original_rate_limit_enabled


def use_role(client, role_name):
    client.active_user["id"] = client.user_ids[role_name]


def create_episode(client):
    response = client.post(
        "/api/v1/research/episodes",
        json={
            "study_code": STUDY_CODE,
            "case_id": client.case_id,
            "client_session_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_unenrolled_user(client, *, email: str, accepted_terms: bool) -> int:
    db = client.db_factory()
    try:
        accepted_at = dt.datetime.now(dt.timezone.utc) if accepted_terms else None
        user = User(
            email=email,
            full_name="Pilot Clinician",
            is_active=True,
            terms_accepted=accepted_terms,
            terms_accepted_at=accepted_at,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def pre_ai_payload():
    return {
        "task_schema_version": TASK_VERSION,
        "decision": {
            "malocclusion_class": "Class I",
            "dhc": 3,
            "ac": 5,
        },
        "confidence": 64,
        "client_active_seconds": 42,
    }


def complete_clinician_episode(client):
    use_role(client, "clinician")
    episode = create_episode(client)
    episode_id = episode["id"]
    locked = client.post(
        f"/api/v1/research/episodes/{episode_id}/pre-ai",
        json=pre_ai_payload(),
    )
    assert locked.status_code == 201, locked.text
    revealed = client.post(f"/api/v1/research/episodes/{episode_id}/reveal")
    assert revealed.status_code == 201, revealed.text
    final = client.post(
        f"/api/v1/research/episodes/{episode_id}/final",
        json={
            "task_schema_version": TASK_VERSION,
            "decision": {
                "malocclusion_class": "Class II div 1",
                "dhc": 4,
                "ac": 6,
            },
            "confidence": 78,
            "agreement": "partial",
            "override": False,
            "usefulness": 4,
            "client_active_seconds": 31,
        },
    )
    assert final.status_code == 201, final.text
    return final.json()


def test_clinician_access_is_automatic_idempotent_and_governed(research_client):
    user_id = create_unenrolled_user(
        research_client,
        email="new.clinician@example.test",
        accepted_terms=True,
    )
    research_client.active_user["id"] = user_id

    before = research_client.get(
        f"/api/v1/research/context?study_code={STUDY_CODE}"
    )
    assert before.status_code == 200
    assert before.json()["participant"] is None

    ensured = research_client.post(
        "/api/v1/research/participants/ensure-clinician",
        json={"study_code": STUDY_CODE},
    )
    assert ensured.status_code == 200, ensured.text
    participant = ensured.json()["participant"]
    assert participant["role"] == "clinician"
    assert participant["participant_code"].startswith("CLN-")
    assert participant["site_code"] == "TEST"
    assert ensured.json()["active_epoch_code"] == "TEST-E1"

    repeated = research_client.post(
        "/api/v1/research/participants/ensure-clinician",
        json={"study_code": STUDY_CODE},
    )
    assert repeated.status_code == 200
    assert repeated.json()["participant"]["id"] == participant["id"]

    db = research_client.db_factory()
    try:
        rows = (
            db.query(ResearchParticipant)
            .filter(ResearchParticipant.user_id == user_id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].participant_metadata == {
            "enrollment_source": "automatic_authenticated_clinician",
            "identity_source": "professional_email_otp",
            "site_assignment": "default_active_site",
        }
    finally:
        db.close()


def test_automatic_clinician_access_requires_recorded_terms(research_client):
    user_id = create_unenrolled_user(
        research_client,
        email="terms.required@example.test",
        accepted_terms=False,
    )
    research_client.active_user["id"] = user_id

    response = research_client.post(
        "/api/v1/research/participants/ensure-clinician",
        json={"study_code": STUDY_CODE},
    )
    assert response.status_code == 428
    assert "Terms & Data Use Agreement" in response.json()["detail"]

    db = research_client.db_factory()
    try:
        assert (
            db.query(ResearchParticipant)
            .filter(ResearchParticipant.user_id == user_id)
            .count()
            == 0
        )
    finally:
        db.close()


def test_manual_bootstrap_and_self_enrollment_routes_are_removed(research_client):
    assert research_client.post(
        "/api/v1/research/bootstrap", json={}
    ).status_code in {404, 405}
    assert (
        research_client.post(
            "/api/v1/research/participants/enroll", json={}
        ).status_code
        in {404, 405}
    )


def test_next_episode_is_automatic_and_role_governed(research_client):
    created = research_client.post(
        "/api/v1/research/episodes/next",
        json={
            "study_code": STUDY_CODE,
            "client_session_id": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["case_id"] == research_client.case_id
    assert created.json()["state"] == "pre_ai"

    resumed = research_client.post(
        "/api/v1/research/episodes/next",
        json={
            "study_code": STUDY_CODE,
            "client_session_id": str(uuid.uuid4()),
        },
    )
    assert resumed.status_code == 201, resumed.text
    assert resumed.json()["id"] == created.json()["id"]

    use_role(research_client, "reviewer_1")
    forbidden = research_client.post(
        "/api/v1/research/episodes/next",
        json={
            "study_code": STUDY_CODE,
            "client_session_id": str(uuid.uuid4()),
        },
    )
    assert forbidden.status_code == 403


def test_completed_review_can_be_repeated_without_overwriting_original(research_client):
    original = complete_clinician_episode(research_client)
    assert original["attempt_index"] == 1
    if original["follow_up"]["required"]:
        follow_up = research_client.post(
            "/api/v1/research/surveys",
            json={
                "study_code": STUDY_CODE,
                "instrument_code": "ai-influence-micro",
                "instrument_version": "1.0",
                "episode_id": original["id"],
                "period_code": f"episode-{original['id']}-post",
                "responses": {
                    "influence": "changed_part",
                    "primary_reason": "clinical_evidence_differed",
                    "trigger_codes": original["follow_up"]["triggers"],
                },
                "completion_status": "completed",
            },
        )
        assert follow_up.status_code == 201, follow_up.text

    client_session_id = str(uuid.uuid4())
    repeated = research_client.post(
        f"/api/v1/research/episodes/{original['id']}/repeat",
        json={
            "client_session_id": client_session_id,
            "reason_code": "new_clinical_opinion",
        },
    )
    assert repeated.status_code == 201, repeated.text
    repeated_body = repeated.json()
    assert repeated_body["id"] != original["id"]
    assert repeated_body["case_id"] == original["case_id"]
    assert repeated_body["state"] == "pre_ai"
    assert repeated_body["attempt_index"] == 2
    assert repeated_body["repeat_of_episode_id"] == original["id"]
    assert repeated_body["pre_ai_decision"] is None

    idempotent = research_client.post(
        f"/api/v1/research/episodes/{original['id']}/repeat",
        json={
            "client_session_id": client_session_id,
            "reason_code": "new_clinical_opinion",
        },
    )
    assert idempotent.status_code == 201
    assert idempotent.json()["id"] == repeated_body["id"]

    db = research_client.db_factory()
    try:
        original_row = db.query(ResearchEpisode).filter_by(id=original["id"]).one()
        repeated_row = db.query(ResearchEpisode).filter_by(id=repeated_body["id"]).one()
        assert original_row.final_decision is not None
        assert original_row.attempt_index == 1
        assert repeated_row.repeat_of_episode_id == original_row.id
        assert repeated_row.events[0].event_type == "episode_repeated"
        assert repeated_row.events[0].payload["repeat_reason_code"] == "new_clinical_opinion"
    finally:
        db.close()

    use_role(research_client, "reviewer_1")
    forbidden = research_client.post(
        f"/api/v1/research/episodes/{original['id']}/repeat",
        json={
            "client_session_id": str(uuid.uuid4()),
            "reason_code": "participant_requested",
        },
    )
    assert forbidden.status_code == 404


def test_follow_up_plan_is_derived_versioned_and_completable(research_client):
    completed = complete_clinician_episode(research_client)
    assert completed["final_decision"]["agreement"] == "agree"
    assert completed["final_decision"]["override"] is False
    assert completed["final_decision"]["usefulness"] is None
    assert completed["follow_up"] == {
        "required": True,
        "kind": "reason",
        "triggers": ["decision_changed"],
        "instrument_code": "ai-influence-micro",
        "instrument_version": "1.0",
        "period_code": f"episode-{completed['id']}-post",
        "completed": False,
    }

    instruments = research_client.get(
        f"/api/v1/research/instruments?study_code={STUDY_CODE}"
    )
    assert instruments.status_code == 200, instruments.text
    assert any(
        row["code"] == "ai-influence-micro" and row["version"] == "1.0"
        for row in instruments.json()
    )

    follow_up = research_client.post(
        "/api/v1/research/surveys",
        json={
            "study_code": STUDY_CODE,
            "instrument_code": "ai-influence-micro",
            "instrument_version": "1.0",
            "episode_id": completed["id"],
            "period_code": f"episode-{completed['id']}-post",
            "responses": {
                "influence": "changed_part",
                "primary_reason": "clinical_evidence_differed",
                "trigger_codes": ["decision_changed"],
            },
            "completion_status": "completed",
        },
    )
    assert follow_up.status_code == 201, follow_up.text

    refreshed = research_client.get(
        f"/api/v1/research/episodes/{completed['id']}"
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["follow_up"]["completed"] is True

    db = research_client.db_factory()
    try:
        event_types = [
            row.event_type
            for row in db.query(ResearchEvent)
            .filter(ResearchEvent.episode_id == completed["id"])
            .order_by(ResearchEvent.sequence_no)
            .all()
        ]
    finally:
        db.close()
    assert "follow_up_scheduled" in event_types
    assert "survey_response_recorded" in event_types


def test_unchanged_non_sampled_case_skips_follow_up(research_client):
    episode = create_episode(research_client)
    episode_id = episode["id"]
    initial = {
        "task_schema_version": TASK_VERSION,
        "decision": {
            "malocclusion_class": "Class II div 1",
            "dhc": 3,
            "ac": 5,
        },
        "confidence": 70,
    }
    assert (
        research_client.post(
            f"/api/v1/research/episodes/{episode_id}/pre-ai",
            json=initial,
        ).status_code
        == 201
    )
    assert (
        research_client.post(
            f"/api/v1/research/episodes/{episode_id}/reveal"
        ).status_code
        == 201
    )
    final = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/final",
        json=initial,
    )
    assert final.status_code == 201, final.text
    assert final.json()["follow_up"]["required"] is False
    assert final.json()["follow_up"]["kind"] == "none"

    exhausted = research_client.post(
        "/api/v1/research/episodes/next",
        json={
            "study_code": STUDY_CODE,
            "client_session_id": str(uuid.uuid4()),
        },
    )
    assert exhausted.status_code == 409
    assert exhausted.json()["detail"] == "No eligible research cases are available"


def test_ai_is_absent_until_pre_ai_decision_is_locked(research_client):
    episode = create_episode(research_client)
    episode_id = episode["id"]
    assert episode["state"] == "pre_ai"
    assert episode["pre_ai_decision"] is None
    assert episode["ai_reveal"] is None
    assert "Frozen AI summary" not in json.dumps(episode)

    premature = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/reveal"
    )
    assert premature.status_code == 409

    out_of_order = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/events",
        json={
            "event_uuid": str(uuid.uuid4()),
            "idempotency_key": str(uuid.uuid4()),
            "sequence_no": 3,
            "event_type": "field_changed",
            "schema_version": "research-event/1.0.0",
            "payload": {},
        },
    )
    assert out_of_order.status_code == 409
    assert out_of_order.json()["detail"]["expected_sequence_no"] == 2

    event_id = str(uuid.uuid4())
    event_key = str(uuid.uuid4())
    event_body = {
        "event_uuid": event_id,
        "idempotency_key": event_key,
        "sequence_no": 2,
        "event_type": "field_changed",
        "schema_version": "research-event/1.0.0",
        "payload": {"field": "dhc"},
    }
    first_event = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/events",
        json=event_body,
    )
    assert first_event.status_code == 201
    duplicate_event = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/events",
        json=event_body,
    )
    assert duplicate_event.status_code == 201
    assert duplicate_event.json()["duplicate"] is True

    locked = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/pre-ai",
        json=pre_ai_payload(),
    )
    assert locked.status_code == 201
    assert locked.json()["state"] == "pre_ai_locked"
    assert locked.json()["ai_reveal"] is None
    assert "Frozen AI summary" not in locked.text

    second_lock = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/pre-ai",
        json=pre_ai_payload(),
    )
    assert second_lock.status_code == 409

    revealed = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/reveal"
    )
    assert revealed.status_code == 201
    assert revealed.json()["state"] == "ai_revealed"
    assert (
        revealed.json()["ai_reveal"]["payload"]["summary"]
        == "Frozen AI summary that must remain blinded before reveal."
    )


def test_research_observations_and_linked_cases_are_immutable(research_client):
    episode = create_episode(research_client)
    episode_id = episode["id"]
    locked = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/pre-ai",
        json=pre_ai_payload(),
    )
    assert locked.status_code == 201

    db = research_client.db_factory()
    try:
        row = (
            db.query(PreAIDecision)
            .filter(PreAIDecision.episode_id == episode_id)
            .one()
        )
        row.decision = {"malocclusion_class": "tampered"}
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()

        row = (
            db.query(PreAIDecision)
            .filter(PreAIDecision.episode_id == episode_id)
            .one()
        )
        db.delete(row)
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()
    finally:
        db.close()

    deleted = research_client.delete(f"/api/v1/cases/{research_client.case_id}")
    assert deleted.status_code == 409
    assert "immutable research record" in deleted.json()["detail"]


def test_independent_reference_and_adjudication_workflow(research_client):
    final_episode = complete_clinician_episode(research_client)
    episode_id = final_episode["id"]

    use_role(research_client, "reviewer_1")
    queue = research_client.get(
        f"/api/v1/research/reference-queue?study_code={STUDY_CODE}"
    )
    assert queue.status_code == 200
    queue_text = queue.text
    assert "pre_ai_decision" not in queue_text
    assert "ai_reveal" not in queue_text
    assert "PATIENT-MUST-NOT-EXPORT" not in queue_text

    blinded_case = research_client.get(
        f"/api/v1/research/episodes/{episode_id}/reference-case"
    )
    assert blinded_case.status_code == 200
    assert set(blinded_case.json()) == {
        "episode_id",
        "case_code",
        "site_code",
        "epoch_code",
        "state",
        "images",
    }
    assert "patient" not in blinded_case.text.lower()
    assert "prediction" not in blinded_case.text.lower()

    review_payload = {
        "task_schema_version": TASK_VERSION,
        "decision": {"malocclusion_class": "Class II div 1", "dhc": 4},
        "confidence": 85,
        "review_round": 1,
        "blinded_to_clinician": True,
    }
    first_review = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/reference-assessments",
        json=review_payload,
    )
    assert first_review.status_code == 201, first_review.text

    use_role(research_client, "reviewer_2")
    second_review = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/reference-assessments",
        json={
            **review_payload,
            "decision": {"malocclusion_class": "Class II div 1", "dhc": 3},
            "confidence": 72,
        },
    )
    assert second_review.status_code == 201, second_review.text

    use_role(research_client, "adjudicator")
    assessments = research_client.get(
        f"/api/v1/research/episodes/{episode_id}/reference-assessments"
    )
    assert assessments.status_code == 200
    assert len(assessments.json()) == 2
    assert all("decision" in row for row in assessments.json())

    adjudication = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/adjudication",
        json={
            "reference_standard_version": "reference/1.0",
            "task_schema_version": TASK_VERSION,
            "consensus_decision": {
                "malocclusion_class": "Class II div 1",
                "dhc": 4,
            },
            "uncertainty": "low",
            "rationale": "Consensus after two independent reviews.",
        },
    )
    assert adjudication.status_code == 201, adjudication.text

    use_role(research_client, "admin")
    exported = research_client.get(
        f"/api/v1/research/studies/{STUDY_CODE}/export"
    )
    assert exported.status_code == 200, exported.text
    export_text = exported.text
    assert "PATIENT-MUST-NOT-EXPORT" not in export_text
    assert "@example.test" not in export_text
    assert '"user_id"' not in export_text
    assert '"source_case_id"' not in export_text
    assert exported.json()["episodes"][0]["case_code"].startswith("R-")
    assert (
        exported.json()["ai_reveals"][0]["payload"]["case_id"]
        == exported.json()["episodes"][0]["case_code"]
    )


def test_clinician_source_case_is_available_before_ai_without_leakage(
    research_client,
):
    episode = create_episode(research_client)
    episode_id = episode["id"]

    source_case = research_client.get(
        f"/api/v1/research/episodes/{episode_id}/source-case"
    )
    assert source_case.status_code == 200, source_case.text
    assert set(source_case.json()) == {
        "episode_id",
        "case_code",
        "site_code",
        "epoch_code",
        "state",
        "images",
    }
    assert source_case.json()["state"] == "pre_ai"
    assert source_case.json()["images"][0]["image_url"].endswith(
        f"/episodes/{episode_id}/source-images/1"
    )
    source_text = source_case.text.lower()
    assert "patient-must-not-export" not in source_text
    assert "prediction" not in source_text
    assert "confidence" not in source_text
    assert "ai_reveal" not in source_text

    use_role(research_client, "reviewer_1")
    reviewer_access = research_client.get(
        f"/api/v1/research/episodes/{episode_id}/source-case"
    )
    assert reviewer_access.status_code == 404


def test_correction_must_reference_an_observation_in_the_same_episode(
    research_client,
):
    episode = create_episode(research_client)
    episode_id = episode["id"]
    locked = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/pre-ai",
        json=pre_ai_payload(),
    )
    assert locked.status_code == 201
    pre_ai_id = locked.json()["pre_ai_decision"]["id"]

    missing_target = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/corrections",
        json={
            "target_type": "pre_ai_decision",
            "target_id": pre_ai_id + 1000,
            "reason": "Correct a documented transcription error.",
            "corrected_payload": {"decision": {"dhc": 4}},
        },
    )
    assert missing_target.status_code == 404

    correction = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/corrections",
        json={
            "target_type": "pre_ai_decision",
            "target_id": pre_ai_id,
            "reason": "Correct a documented transcription error.",
            "corrected_payload": {"decision": {"dhc": 4}},
        },
    )
    assert correction.status_code == 201, correction.text

    db = research_client.db_factory()
    try:
        original = db.query(PreAIDecision).filter(PreAIDecision.id == pre_ai_id).one()
        assert original.decision["dhc"] == 3
    finally:
        db.close()


def test_epoch_model_drift_and_role_separation_are_blocked(research_client):
    episode = create_episode(research_client)
    episode_id = episode["id"]
    schema_drift = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/pre-ai",
        json={
            **pre_ai_payload(),
            "task_schema_version": "unexpected-task-schema/9.9",
        },
    )
    assert schema_drift.status_code == 409
    assert "frozen research epoch" in schema_drift.json()["detail"]

    locked = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/pre-ai",
        json=pre_ai_payload(),
    )
    assert locked.status_code == 201

    db = research_client.db_factory()
    try:
        result = db.query(InferenceResult).one()
        result.model_version = "unexpected-model"
        db.commit()
    finally:
        db.close()
    drifted = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/reveal"
    )
    assert drifted.status_code == 409
    assert "frozen research epoch" in drifted.json()["detail"]

    use_role(research_client, "admin")
    admin_cannot_lock = research_client.post(
        f"/api/v1/research/episodes/{episode_id}/pre-ai",
        json=pre_ai_payload(),
    )
    assert admin_cannot_lock.status_code == 403
