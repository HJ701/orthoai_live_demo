from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_dependency
from app.config import settings
from app.core.research import (
    ai_reveal_response_payload,
    build_ai_snapshot,
    enum_value,
    get_episode_for_user,
    get_latest_inference_result,
    get_participant_for_user,
    get_study_or_404,
    research_mode_guard,
    sha256_json,
    utc_now,
)
from app.database import get_db
from app.core.s3_storage import download_file_from_s3
from app.models import (
    AIReveal,
    Adjudication,
    Case,
    FinalDecision,
    Image,
    InferenceJob,
    InferenceResult,
    JobState,
    PreAIDecision,
    ReferenceAssessment,
    ResearchCorrection,
    ResearchEpisode,
    ResearchEpisodeState,
    ResearchEpoch,
    ResearchEvent,
    ResearchParticipant,
    ResearchRole,
    ResearchSite,
    ResearchStudy,
    ResearchStudyStatus,
    StudyInstrument,
    SurveyResponse,
    User,
)
from app.research_schemas import (
    AdjudicationCreate,
    AdjudicationResponse,
    AIRevealResponse,
    DecisionSubmission,
    FinalDecisionResponse,
    FinalDecisionSubmission,
    PreAIDecisionResponse,
    ReferenceAssessmentCreate,
    ReferenceAssessmentDetail,
    ReferenceAssessmentResponse,
    ReferenceCaseResponse,
    ReferenceImageResponse,
    ReferenceQueueItem,
    ResearchClinicianAccessIn,
    ResearchContextResponse,
    ResearchCorrectionCreate,
    ResearchCorrectionResponse,
    ResearchEligibleUserResponse,
    ResearchEpisodeCreate,
    ResearchEpisodeList,
    ResearchEpisodeRepeatCreate,
    ResearchEpisodeResponse,
    ResearchFollowUpPlan,
    ResearchNextEpisodeCreate,
    ResearchEventIn,
    ResearchEventResponse,
    ResearchExportResponse,
    ResearchParticipantResponse,
    ResearchParticipantAdminCreate,
    ResearchParticipantWithdrawIn,
    StudyInstrumentCreate,
    StudyInstrumentResponse,
    SurveyResponseCreate,
    SurveyResponseOut,
)


router = APIRouter()

CLINICIAN_ROLES = {ResearchRole.CLINICIAN}
REVIEWER_ROLES = {ResearchRole.REVIEWER}
ADJUDICATOR_ROLES = {ResearchRole.ADJUDICATOR}
ADMIN_ROLES = {ResearchRole.RESEARCH_ADMIN}
CORRECTION_TARGET_MODELS = {
    "pre_ai_decision": PreAIDecision,
    "ai_reveal": AIReveal,
    "final_decision": FinalDecision,
    "survey_response": SurveyResponse,
    "reference_assessment": ReferenceAssessment,
    "adjudication": Adjudication,
}
MICRO_FOLLOW_UP_CODE = "ai-influence-micro"
MICRO_FOLLOW_UP_VERSION = "1.0"
MICRO_FOLLOW_UP_DEFINITION = {
    "instructions": "A brief case-level check on how the AI affected the decision.",
    "questions": [
        {
            "id": "influence",
            "label": "How did the AI affect your decision?",
            "type": "select",
            "required": True,
            "options": [
                "no_influence",
                "confirmed_assessment",
                "changed_part",
                "changed_final",
                "rejected_ai",
                "prefer_not_to_say",
            ],
        },
        {
            "id": "primary_reason",
            "label": "What was the main reason?",
            "type": "select",
            "required": False,
            "options": [
                "clinical_evidence_differed",
                "ai_appeared_incorrect",
                "image_quality",
                "patient_or_context",
                "uncertain",
                "other",
            ],
        },
        {
            "id": "usefulness",
            "label": "How useful was the AI for this case?",
            "type": "likert",
            "required": False,
            "min": 1,
            "max": 5,
        },
    ],
}


def _elapsed_seconds(start: datetime, end: datetime) -> float:
    if start.tzinfo is None and end.tzinfo is not None:
        end = end.replace(tzinfo=None)
    elif start.tzinfo is not None and end.tzinfo is None:
        end = end.replace(tzinfo=start.tzinfo)
    return max(0.0, round((end - start).total_seconds(), 3))


def _last_event_sequence(db: Session, episode_id: int) -> int:
    return int(
        db.query(func.max(ResearchEvent.sequence_no))
        .filter(ResearchEvent.episode_id == episode_id)
        .scalar()
        or 0
    )


def _append_system_event(
    db: Session,
    *,
    episode: ResearchEpisode,
    participant_id: int,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> ResearchEvent:
    sequence_no = _last_event_sequence(db, episode.id) + 1
    event_row = ResearchEvent(
        episode_id=episode.id,
        participant_id=participant_id,
        event_uuid=str(uuid.uuid4()),
        idempotency_key=f"server:{event_type}:{uuid.uuid4()}",
        sequence_no=sequence_no,
        event_type=event_type,
        schema_version=settings.research_event_schema_version,
        client_timestamp=None,
        client_timezone_offset_minutes=None,
        payload=payload,
    )
    db.add(event_row)
    return event_row


def _participant_response(participant: ResearchParticipant) -> ResearchParticipantResponse:
    return ResearchParticipantResponse(
        id=participant.id,
        study_code=participant.study.code,
        site_code=participant.site.code,
        participant_code=participant.participant_code,
        role=participant.role,
        specialty=participant.specialty,
        experience_band=participant.experience_band,
        consent_version=participant.consent_version,
        consented_at=participant.consented_at,
        withdrawn_at=participant.withdrawn_at,
        is_active=participant.is_active,
    )


def _normalized_decision_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = " ".join(value.strip().lower().split())
        return normalized or None
    return value


def _predicted_class(episode: ResearchEpisode) -> Optional[str]:
    payload = episode.ai_reveal.payload if episode.ai_reveal else {}
    findings = payload.get("findings") if isinstance(payload, dict) else {}
    prediction = findings.get("prediction") if isinstance(findings, dict) else {}
    value = prediction.get("predicted_class") if isinstance(prediction, dict) else None
    return str(value) if value is not None else None


def _follow_up_period_code(episode: ResearchEpisode) -> str:
    return f"episode-{episode.id}-post"


def _follow_up_plan(db: Session, episode: ResearchEpisode) -> ResearchFollowUpPlan:
    triggers: list[str] = []
    pre = episode.pre_ai_decision
    final = episode.final_decision

    if pre and final:
        decision_fields = ("malocclusion_class", "dhc", "ac", "clinical_action")
        if any(
            _normalized_decision_value(pre.decision.get(field))
            != _normalized_decision_value(final.decision.get(field))
            for field in decision_fields
        ):
            triggers.append("decision_changed")

        predicted = _predicted_class(episode)
        if (
            predicted
            and _normalized_decision_value(final.decision.get("malocclusion_class"))
            != _normalized_decision_value(predicted)
        ):
            triggers.append("ai_disagreement")

        if abs(float(final.confidence) - float(pre.confidence)) >= 20:
            triggers.append("confidence_shift")

        cadence_value = (episode.epoch.config or {}).get(
            "case_pulse_every_n",
            (episode.study.config or {}).get("case_pulse_every_n", 3),
        )
        try:
            cadence = max(1, int(cadence_value))
        except (TypeError, ValueError):
            cadence = 3
        if episode.exposure_index % cadence == 0:
            triggers.append("scheduled_sample")

    reason_required = any(
        trigger in {"decision_changed", "ai_disagreement", "confidence_shift"}
        for trigger in triggers
    )
    pulse_required = "scheduled_sample" in triggers
    kind: str
    if reason_required and pulse_required:
        kind = "reason_and_pulse"
    elif reason_required:
        kind = "reason"
    elif pulse_required:
        kind = "pulse"
    else:
        kind = "none"

    instrument = (
        db.query(StudyInstrument)
        .filter(
            StudyInstrument.study_id == episode.study_id,
            StudyInstrument.code == MICRO_FOLLOW_UP_CODE,
            StudyInstrument.version == MICRO_FOLLOW_UP_VERSION,
            StudyInstrument.is_active.is_(True),
        )
        .first()
    )
    period_code = _follow_up_period_code(episode)
    completed = False
    if instrument:
        completed = (
            db.query(SurveyResponse.id)
            .filter(
                SurveyResponse.participant_id == episode.participant_id,
                SurveyResponse.instrument_id == instrument.id,
                SurveyResponse.episode_id == episode.id,
                SurveyResponse.period_code == period_code,
            )
            .first()
            is not None
        )

    return ResearchFollowUpPlan(
        required=bool(triggers),
        kind=kind,
        triggers=triggers,
        instrument_code=MICRO_FOLLOW_UP_CODE,
        instrument_version=MICRO_FOLLOW_UP_VERSION,
        period_code=period_code if triggers else None,
        completed=completed,
    )


def _ensure_default_instruments(db: Session, study: ResearchStudy) -> None:
    existing = (
        db.query(StudyInstrument.id)
        .filter(
            StudyInstrument.study_id == study.id,
            StudyInstrument.code == MICRO_FOLLOW_UP_CODE,
            StudyInstrument.version == MICRO_FOLLOW_UP_VERSION,
        )
        .first()
    )
    if existing:
        return
    db.add(
        StudyInstrument(
            study_id=study.id,
            code=MICRO_FOLLOW_UP_CODE,
            version=MICRO_FOLLOW_UP_VERSION,
            name="Case influence check",
            construct="perceived_ai_influence",
            definition=MICRO_FOLLOW_UP_DEFINITION,
            schedule={
                "level": "episode",
                "conditional": [
                    "decision_changed",
                    "ai_disagreement",
                    "confidence_shift",
                ],
                "sample_every_n_exposures": 3,
            },
            scoring_spec={
                "type": "categorical_with_optional_usefulness",
                "missingness": "explicit",
            },
            is_active=True,
        )
    )


def _episode_response(db: Session, episode: ResearchEpisode) -> ResearchEpisodeResponse:
    pre = episode.pre_ai_decision
    reveal = episode.ai_reveal
    final = episode.final_decision
    return ResearchEpisodeResponse(
        id=episode.id,
        study_code=episode.study.code,
        site_code=episode.site.code,
        epoch_code=episode.epoch.code,
        participant_code=episode.participant.participant_code,
        case_id=episode.case_id,
        state=episode.state,
        condition_code=episode.condition_code,
        exposure_index=episode.exposure_index,
        attempt_index=episode.attempt_index,
        repeat_of_episode_id=episode.repeat_of_episode_id,
        last_event_sequence=_last_event_sequence(db, episode.id),
        pre_ai_started_at=episode.pre_ai_started_at,
        pre_ai_locked_at=episode.pre_ai_locked_at,
        ai_revealed_at=episode.ai_revealed_at,
        final_locked_at=episode.final_locked_at,
        adjudicated_at=episode.adjudicated_at,
        pre_ai_decision=(
            PreAIDecisionResponse(
                id=pre.id,
                task_schema_version=pre.task_schema_version,
                decision=pre.decision,
                confidence=pre.confidence,
                client_active_seconds=pre.client_active_seconds,
                server_elapsed_seconds=pre.server_elapsed_seconds,
                submitted_at=pre.submitted_at,
                content_sha256=pre.content_sha256,
            )
            if pre
            else None
        ),
        ai_reveal=(
            AIRevealResponse(**ai_reveal_response_payload(reveal))
            if reveal
            else None
        ),
        final_decision=(
            FinalDecisionResponse(
                id=final.id,
                task_schema_version=final.task_schema_version,
                decision=final.decision,
                confidence=final.confidence,
                agreement=final.agreement,
                override=final.override,
                override_reason=final.override_reason,
                usefulness=final.usefulness,
                client_active_seconds=final.client_active_seconds,
                server_elapsed_seconds=final.server_elapsed_seconds,
                submitted_at=final.submitted_at,
                content_sha256=final.content_sha256,
            )
            if final
            else None
        ),
        follow_up=_follow_up_plan(db, episode),
    )


def _participant_for_study(
    db: Session,
    *,
    study: ResearchStudy,
    current_user: User,
    roles: Optional[Iterable[ResearchRole]] = None,
) -> ResearchParticipant:
    return get_participant_for_user(
        db,
        study_id=study.id,
        user_id=current_user.id,
        required_roles=roles,
    )


@router.get("/context", response_model=ResearchContextResponse)
def get_research_context(
    study_code: str = Query("ORTHOAI-HCI-V3"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchContextResponse:
    research_mode_guard()
    study = db.query(ResearchStudy).filter(ResearchStudy.code == study_code).first()
    if not study:
        return ResearchContextResponse(
            enabled=True,
            ui_version=settings.research_ui_version,
        )
    participant = (
        db.query(ResearchParticipant)
        .filter(
            ResearchParticipant.study_id == study.id,
            ResearchParticipant.user_id == current_user.id,
        )
        .first()
    )
    epoch = (
        db.query(ResearchEpoch)
        .filter(
            ResearchEpoch.study_id == study.id,
            ResearchEpoch.is_active.is_(True),
        )
        .order_by(ResearchEpoch.id.desc())
        .first()
    )
    return ResearchContextResponse(
        enabled=True,
        participant=_participant_response(participant) if participant else None,
        study_status=study.status,
        protocol_version=study.protocol_version,
        consent_version=study.consent_version,
        active_epoch_code=epoch.code if epoch else None,
        ui_version=settings.research_ui_version,
    )


def _automatic_participant_code(study: ResearchStudy, current_user: User) -> str:
    """Create a stable de-identified code without exposing an email address."""

    digest = hmac.new(
        settings.secret_key.encode("utf-8"),
        f"{study.code}:{current_user.id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"CLN-{digest[:12].upper()}"


@router.post(
    "/participants/ensure-clinician",
    response_model=ResearchContextResponse,
    status_code=status.HTTP_200_OK,
)
def ensure_clinician_access(
    body: ResearchClinicianAccessIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchContextResponse:
    """Idempotently enroll an authenticated, consented pilot clinician.

    The caller cannot select a role, participant code, site, consent version, or
    epoch. Those governed values are derived from the active pilot configuration.
    """

    research_mode_guard()
    study = get_study_or_404(db, body.study_code)
    if study.status != ResearchStudyStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The pilot study is not currently active",
        )

    epoch = (
        db.query(ResearchEpoch)
        .filter(
            ResearchEpoch.study_id == study.id,
            ResearchEpoch.is_active.is_(True),
        )
        .order_by(ResearchEpoch.id.desc())
        .first()
    )
    if not epoch:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The pilot study has no active research epoch",
        )

    participant = (
        db.query(ResearchParticipant)
        .filter(
            ResearchParticipant.study_id == study.id,
            ResearchParticipant.user_id == current_user.id,
        )
        .first()
    )
    if participant:
        if participant.role != ResearchRole.CLINICIAN:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This account is reserved for a non-clinician study function",
            )
        if not participant.is_active or participant.withdrawn_at is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Research participation for this account is inactive",
            )
        return ResearchContextResponse(
            enabled=True,
            participant=_participant_response(participant),
            study_status=study.status,
            protocol_version=study.protocol_version,
            consent_version=study.consent_version,
            active_epoch_code=epoch.code,
            ui_version=settings.research_ui_version,
        )

    if not current_user.terms_accepted or not current_user.terms_accepted_at:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="Accept the Terms & Data Use Agreement before starting Research Mode",
        )

    site = (
        db.query(ResearchSite)
        .filter(
            ResearchSite.study_id == study.id,
            ResearchSite.is_active.is_(True),
        )
        .order_by(ResearchSite.id)
        .first()
    )
    if not site:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The pilot study has no active clinical site",
        )

    participant = ResearchParticipant(
        study_id=study.id,
        site_id=site.id,
        user_id=current_user.id,
        participant_code=_automatic_participant_code(study, current_user),
        role=ResearchRole.CLINICIAN,
        consent_version=study.consent_version,
        consented_at=current_user.terms_accepted_at,
        is_active=True,
        participant_metadata={
            "enrollment_source": "automatic_authenticated_clinician",
            "identity_source": "professional_email_otp",
            "site_assignment": "default_active_site",
        },
    )
    db.add(participant)
    _ensure_default_instruments(db, study)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        participant = (
            db.query(ResearchParticipant)
            .filter(
                ResearchParticipant.study_id == study.id,
                ResearchParticipant.user_id == current_user.id,
            )
            .first()
        )
        if not participant:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A governed clinician enrollment could not be created",
            ) from exc
    db.refresh(participant)

    return ResearchContextResponse(
        enabled=True,
        participant=_participant_response(participant),
        study_status=study.status,
        protocol_version=study.protocol_version,
        consent_version=study.consent_version,
        active_epoch_code=epoch.code,
        ui_version=settings.research_ui_version,
    )


@router.get(
    "/participants",
    response_model=list[ResearchParticipantResponse],
)
def list_governed_participants(
    study_code: str = Query(..., min_length=3, max_length=64),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> list[ResearchParticipantResponse]:
    research_mode_guard()
    study = get_study_or_404(db, study_code)
    _participant_for_study(
        db,
        study=study,
        current_user=current_user,
        roles=ADMIN_ROLES,
    )
    rows = (
        db.query(ResearchParticipant)
        .filter(ResearchParticipant.study_id == study.id)
        .order_by(ResearchParticipant.participant_code)
        .all()
    )
    return [_participant_response(row) for row in rows]


@router.get(
    "/eligible-users",
    response_model=list[ResearchEligibleUserResponse],
)
def list_eligible_users(
    study_code: str = Query(..., min_length=3, max_length=64),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> list[ResearchEligibleUserResponse]:
    """Give study administrators a precise authenticated identity to enroll."""
    research_mode_guard()
    study = get_study_or_404(db, study_code)
    _participant_for_study(
        db,
        study=study,
        current_user=current_user,
        roles=ADMIN_ROLES,
    )
    participants_by_user = {
        row.user_id: row
        for row in db.query(ResearchParticipant)
        .filter(
            ResearchParticipant.study_id == study.id,
            ResearchParticipant.user_id.is_not(None),
        )
        .all()
    }
    users = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.email, User.id)
        .all()
    )
    return [
        ResearchEligibleUserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_enrolled=user.id in participants_by_user,
            participant_code=(
                participants_by_user[user.id].participant_code
                if user.id in participants_by_user
                else None
            ),
            role=(
                participants_by_user[user.id].role
                if user.id in participants_by_user
                else None
            ),
        )
        for user in users
    ]


@router.post(
    "/participants",
    response_model=ResearchParticipantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_governed_participant(
    body: ResearchParticipantAdminCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchParticipantResponse:
    """Assign an existing authenticated user a protocol-bound study role."""
    research_mode_guard()
    study = get_study_or_404(db, body.study_code)
    admin = _participant_for_study(
        db,
        study=study,
        current_user=current_user,
        roles=ADMIN_ROLES,
    )
    if body.consent_version != study.consent_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Consent version does not match the study",
        )
    site = (
        db.query(ResearchSite)
        .filter(
            ResearchSite.study_id == study.id,
            ResearchSite.code == body.site_code,
            ResearchSite.is_active.is_(True),
        )
        .first()
    )
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active study site not found",
        )
    user = (
        db.query(User)
        .filter(User.id == body.user_id, User.is_active.is_(True))
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active authenticated user not found",
        )
    participant = ResearchParticipant(
        study_id=study.id,
        site_id=site.id,
        user_id=user.id,
        participant_code=body.participant_code,
        role=body.role,
        specialty=body.specialty,
        experience_band=body.experience_band,
        consent_version=body.consent_version,
        consented_at=body.consented_at,
        is_active=True,
        participant_metadata={
            "assignment_method": "research_admin",
            "assigned_by_participant_code": admin.participant_code,
        },
    )
    db.add(participant)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Participant code or user enrollment already exists",
        ) from exc
    db.refresh(participant)
    return _participant_response(participant)


@router.post(
    "/participants/{participant_code}/withdraw",
    response_model=ResearchParticipantResponse,
)
def withdraw_participant(
    participant_code: str,
    body: ResearchParticipantWithdrawIn,
    study_code: str = Query(..., min_length=3, max_length=64),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchParticipantResponse:
    """Record withdrawal without deleting any previously collected observation."""
    research_mode_guard()
    study = get_study_or_404(db, study_code)
    actor = _participant_for_study(
        db,
        study=study,
        current_user=current_user,
    )
    target = (
        db.query(ResearchParticipant)
        .filter(
            ResearchParticipant.study_id == study.id,
            ResearchParticipant.participant_code == participant_code,
        )
        .with_for_update()
        .first()
    )
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research participant not found",
        )
    if actor.role != ResearchRole.RESEARCH_ADMIN and actor.id != target.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Participant withdrawal is not authorized",
        )
    if target.withdrawn_at is not None:
        return _participant_response(target)

    now = utc_now()
    active_episodes = (
        db.query(ResearchEpisode)
        .filter(
            ResearchEpisode.participant_id == target.id,
            ResearchEpisode.state.in_(
                [
                    ResearchEpisodeState.PRE_AI,
                    ResearchEpisodeState.PRE_AI_LOCKED,
                    ResearchEpisodeState.AI_REVEALED,
                ]
            ),
        )
        .all()
    )
    for episode in active_episodes:
        episode.state = ResearchEpisodeState.WITHDRAWN
        episode.withdrawn_at = now
        _append_system_event(
            db,
            episode=episode,
            participant_id=actor.id,
            event_type="participant_withdrawn",
            payload={"reason_recorded": bool(body.reason)},
        )
    target.withdrawn_at = now
    target.is_active = False
    target.participant_metadata = {
        **(target.participant_metadata or {}),
        "withdrawal_reason": body.reason,
        "withdrawal_recorded_by": actor.participant_code,
    }
    db.commit()
    db.refresh(target)
    return _participant_response(target)


def _active_epoch_for_study(db: Session, study: ResearchStudy) -> ResearchEpoch:
    epoch = (
        db.query(ResearchEpoch)
        .filter(
            ResearchEpoch.study_id == study.id,
            ResearchEpoch.is_active.is_(True),
        )
        .order_by(ResearchEpoch.id.desc())
        .first()
    )
    if not epoch:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active research epoch is configured",
        )
    if epoch.protocol_version != study.protocol_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active epoch protocol version does not match the study",
        )
    return epoch


def _create_episode_record(
    db: Session,
    *,
    study: ResearchStudy,
    participant: ResearchParticipant,
    case: Case,
    client_session_id: str,
    condition_code: Optional[str],
    attempt_index: int = 1,
    repeat_of_episode_id: Optional[int] = None,
    repeat_reason_code: Optional[str] = None,
) -> ResearchEpisode:
    # Confirm availability without decoding or returning the AI result.
    get_latest_inference_result(db, case.id)
    epoch = _active_epoch_for_study(db, study)
    prior_reveals = (
        db.query(func.count(AIReveal.id))
        .join(ResearchEpisode, ResearchEpisode.id == AIReveal.episode_id)
        .filter(
            ResearchEpisode.study_id == study.id,
            ResearchEpisode.participant_id == participant.id,
        )
        .scalar()
        or 0
    )
    now = utc_now()
    episode = ResearchEpisode(
        study_id=study.id,
        site_id=participant.site_id,
        epoch_id=epoch.id,
        participant_id=participant.id,
        case_id=case.id,
        state=ResearchEpisodeState.PRE_AI,
        condition_code=condition_code,
        client_session_id=client_session_id,
        exposure_index=int(prior_reveals) + 1,
        attempt_index=attempt_index,
        repeat_of_episode_id=repeat_of_episode_id,
        pre_ai_started_at=now,
    )
    db.add(episode)
    try:
        db.flush()
        _append_system_event(
            db,
            episode=episode,
            participant_id=participant.id,
            event_type="episode_repeated" if repeat_of_episode_id else "episode_created",
            payload={
                "state": ResearchEpisodeState.PRE_AI.value,
                "exposure_index": episode.exposure_index,
                "attempt_index": episode.attempt_index,
                "repeat_of_episode_id": repeat_of_episode_id,
                "repeat_reason_code": repeat_reason_code,
                "ui_version": epoch.ui_version,
                "epoch_code": epoch.code,
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = (
            db.query(ResearchEpisode)
            .filter(
                ResearchEpisode.study_id == study.id,
                ResearchEpisode.participant_id == participant.id,
                ResearchEpisode.case_id == case.id,
                ResearchEpisode.attempt_index == attempt_index,
            )
            .first()
        )
        if existing:
            return existing
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A research episode could not be created",
        ) from exc
    db.refresh(episode)
    return episode


@router.post(
    "/episodes",
    response_model=ResearchEpisodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_episode(
    body: ResearchEpisodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchEpisodeResponse:
    research_mode_guard()
    study = get_study_or_404(db, body.study_code)
    if study.status != ResearchStudyStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The research study is not active",
        )
    participant = _participant_for_study(
        db,
        study=study,
        current_user=current_user,
        roles=CLINICIAN_ROLES,
    )
    case = (
        db.query(Case)
        .filter(Case.id == body.case_id, Case.user_id == current_user.id)
        .first()
    )
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )
    active = (
        db.query(ResearchEpisode)
        .filter(
            ResearchEpisode.study_id == study.id,
            ResearchEpisode.participant_id == participant.id,
            ResearchEpisode.state.in_(
                [
                    ResearchEpisodeState.PRE_AI,
                    ResearchEpisodeState.PRE_AI_LOCKED,
                    ResearchEpisodeState.AI_REVEALED,
                ]
            ),
        )
        .order_by(ResearchEpisode.id.desc())
        .first()
    )
    if active and active.case_id != case.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete the current research review before starting another case",
        )
    episode = _create_episode_record(
        db,
        study=study,
        participant=participant,
        case=case,
        client_session_id=body.client_session_id,
        condition_code=body.condition_code,
    )
    return _episode_response(db, episode)


@router.post(
    "/episodes/{episode_id}/repeat",
    response_model=ResearchEpisodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def repeat_episode(
    episode_id: int,
    body: ResearchEpisodeRepeatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchEpisodeResponse:
    """Create a new immutable attempt while preserving the original observation."""
    research_mode_guard()
    source, participant = get_episode_for_user(
        db,
        episode_id=episode_id,
        current_user=current_user,
    )
    if participant.role not in CLINICIAN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Participant role is not authorized for this action",
        )
    if source.study.status != ResearchStudyStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The research study is not active",
        )
    if source.state not in {
        ResearchEpisodeState.FINAL_LOCKED,
        ResearchEpisodeState.ADJUDICATED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a completed research review can be repeated",
        )
    source_follow_up = _follow_up_plan(db, source)
    if source_follow_up.required and not source_follow_up.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete the outstanding follow-up before repeating this review",
        )

    idempotent = (
        db.query(ResearchEpisode)
        .filter(
            ResearchEpisode.study_id == source.study_id,
            ResearchEpisode.participant_id == participant.id,
            ResearchEpisode.case_id == source.case_id,
            ResearchEpisode.client_session_id == body.client_session_id,
        )
        .first()
    )
    if idempotent:
        return _episode_response(db, idempotent)

    active = (
        db.query(ResearchEpisode)
        .filter(
            ResearchEpisode.study_id == source.study_id,
            ResearchEpisode.participant_id == participant.id,
            ResearchEpisode.state.in_(
                [
                    ResearchEpisodeState.PRE_AI,
                    ResearchEpisodeState.PRE_AI_LOCKED,
                    ResearchEpisodeState.AI_REVEALED,
                ]
            ),
        )
        .order_by(ResearchEpisode.id.desc())
        .first()
    )
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete the current research review before starting a repeat",
        )

    max_attempt = (
        db.query(func.max(ResearchEpisode.attempt_index))
        .filter(
            ResearchEpisode.study_id == source.study_id,
            ResearchEpisode.participant_id == participant.id,
            ResearchEpisode.case_id == source.case_id,
        )
        .scalar()
        or 1
    )
    repeated = _create_episode_record(
        db,
        study=source.study,
        participant=participant,
        case=source.case,
        client_session_id=body.client_session_id,
        condition_code="participant_repeat",
        attempt_index=int(max_attempt) + 1,
        repeat_of_episode_id=source.id,
        repeat_reason_code=body.reason_code,
    )
    return _episode_response(db, repeated)


@router.post(
    "/episodes/next",
    response_model=ResearchEpisodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_next_episode(
    body: ResearchNextEpisodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchEpisodeResponse:
    research_mode_guard()
    study = get_study_or_404(db, body.study_code)
    if study.status != ResearchStudyStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The research study is not active",
        )
    participant = _participant_for_study(
        db,
        study=study,
        current_user=current_user,
        roles=CLINICIAN_ROLES,
    )

    active = (
        db.query(ResearchEpisode)
        .filter(
            ResearchEpisode.study_id == study.id,
            ResearchEpisode.participant_id == participant.id,
            ResearchEpisode.state.in_(
                [
                    ResearchEpisodeState.PRE_AI,
                    ResearchEpisodeState.PRE_AI_LOCKED,
                    ResearchEpisodeState.AI_REVEALED,
                ]
            ),
        )
        .order_by(ResearchEpisode.id.desc())
        .first()
    )
    if active:
        return _episode_response(db, active)

    latest_complete = (
        db.query(ResearchEpisode)
        .filter(
            ResearchEpisode.study_id == study.id,
            ResearchEpisode.participant_id == participant.id,
            ResearchEpisode.state.in_(
                [
                    ResearchEpisodeState.FINAL_LOCKED,
                    ResearchEpisodeState.ADJUDICATED,
                ]
            ),
        )
        .order_by(ResearchEpisode.id.desc())
        .first()
    )
    if latest_complete:
        plan = _follow_up_plan(db, latest_complete)
        if plan.required and not plan.completed:
            return _episode_response(db, latest_complete)

    used_case_ids = select(ResearchEpisode.case_id).where(
            ResearchEpisode.study_id == study.id,
            ResearchEpisode.participant_id == participant.id,
        )
    case = (
        db.query(Case)
        .join(InferenceJob, InferenceJob.case_id == Case.id)
        .join(InferenceResult, InferenceResult.job_id == InferenceJob.id)
        .filter(
            Case.user_id == current_user.id,
            InferenceJob.state == JobState.DONE,
            ~Case.id.in_(used_case_ids),
        )
        .order_by(Case.id.asc())
        .first()
    )
    if not case:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No eligible research cases are available",
        )
    episode = _create_episode_record(
        db,
        study=study,
        participant=participant,
        case=case,
        client_session_id=body.client_session_id,
        condition_code=body.condition_code,
    )
    return _episode_response(db, episode)


@router.get("/episodes", response_model=ResearchEpisodeList)
def list_episodes(
    study_code: str = Query(...),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchEpisodeList:
    research_mode_guard()
    study = get_study_or_404(db, study_code)
    participant = _participant_for_study(
        db,
        study=study,
        current_user=current_user,
    )
    query = db.query(ResearchEpisode).filter(ResearchEpisode.study_id == study.id)
    if participant.role != ResearchRole.RESEARCH_ADMIN:
        query = query.filter(ResearchEpisode.participant_id == participant.id)
    total = query.count()
    episodes = (
        query.order_by(ResearchEpisode.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return ResearchEpisodeList(
        total=total,
        items=[_episode_response(db, item) for item in episodes],
    )


@router.get("/episodes/{episode_id}", response_model=ResearchEpisodeResponse)
def get_episode(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchEpisodeResponse:
    research_mode_guard()
    episode, _ = get_episode_for_user(
        db,
        episode_id=episode_id,
        current_user=current_user,
    )
    return _episode_response(db, episode)


@router.get(
    "/episodes/{episode_id}/source-case",
    response_model=ReferenceCaseResponse,
)
def get_clinician_source_case(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ReferenceCaseResponse:
    """Return source images to the assigned clinician without any AI payload."""
    research_mode_guard()
    episode, participant = get_episode_for_user(
        db,
        episode_id=episode_id,
        current_user=current_user,
    )
    if (
        participant.role not in CLINICIAN_ROLES
        or participant.id != episode.participant_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned clinician can view episode source images",
        )
    return ReferenceCaseResponse(
        episode_id=episode.id,
        case_code=f"R-{episode.id:06d}",
        site_code=episode.site.code,
        epoch_code=episode.epoch.code,
        state=episode.state,
        images=[
            ReferenceImageResponse(
                id=image.id,
                filename=image.filename,
                content_type=image.content_type,
                image_url=(
                    f"/api/v1/research/episodes/{episode.id}/"
                    f"source-images/{image.id}"
                ),
            )
            for image in sorted(episode.case.images, key=lambda item: item.id)
        ],
    )


@router.get("/episodes/{episode_id}/source-images/{image_id}")
def get_clinician_source_image(
    episode_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> Response:
    research_mode_guard()
    episode, participant = get_episode_for_user(
        db,
        episode_id=episode_id,
        current_user=current_user,
    )
    if (
        participant.role not in CLINICIAN_ROLES
        or participant.id != episode.participant_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned clinician can view episode source images",
        )
    image = (
        db.query(Image)
        .filter(Image.id == image_id, Image.case_id == episode.case_id)
        .first()
    )
    if not image or not image.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        )
    try:
        data = download_file_from_s3(image.file_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image data not found",
        ) from exc
    except (ClientError, BotoCoreError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read image from storage",
        ) from exc
    return Response(
        content=data,
        media_type=image.content_type or "image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


@router.post(
    "/episodes/{episode_id}/events",
    response_model=ResearchEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def append_research_event(
    episode_id: int,
    body: ResearchEventIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchEventResponse:
    research_mode_guard()
    episode, participant = get_episode_for_user(
        db,
        episode_id=episode_id,
        current_user=current_user,
        lock=True,
    )
    if episode.participant_id != participant.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the episode participant can append interaction events",
        )
    existing = (
        db.query(ResearchEvent)
        .filter(
            ResearchEvent.episode_id == episode.id,
            ResearchEvent.idempotency_key == body.idempotency_key,
        )
        .first()
    )
    if existing:
        return ResearchEventResponse(
            id=existing.id,
            event_uuid=existing.event_uuid,
            sequence_no=existing.sequence_no,
            event_type=existing.event_type,
            server_timestamp=existing.server_timestamp,
            duplicate=True,
        )
    expected = _last_event_sequence(db, episode.id) + 1
    if body.sequence_no != expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Event sequence is out of order",
                "expected_sequence_no": expected,
            },
        )
    event_row = ResearchEvent(
        episode_id=episode.id,
        participant_id=participant.id,
        event_uuid=body.event_uuid,
        idempotency_key=body.idempotency_key,
        sequence_no=body.sequence_no,
        event_type=body.event_type,
        schema_version=body.schema_version,
        client_timestamp=body.client_timestamp,
        client_timezone_offset_minutes=body.client_timezone_offset_minutes,
        payload=body.payload,
    )
    db.add(event_row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        duplicate = (
            db.query(ResearchEvent)
            .filter(
                ResearchEvent.episode_id == episode.id,
                ResearchEvent.idempotency_key == body.idempotency_key,
            )
            .first()
        )
        if duplicate:
            return ResearchEventResponse(
                id=duplicate.id,
                event_uuid=duplicate.event_uuid,
                sequence_no=duplicate.sequence_no,
                event_type=duplicate.event_type,
                server_timestamp=duplicate.server_timestamp,
                duplicate=True,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Event UUID or sequence already exists",
        ) from exc
    db.refresh(event_row)
    return ResearchEventResponse(
        id=event_row.id,
        event_uuid=event_row.event_uuid,
        sequence_no=event_row.sequence_no,
        event_type=event_row.event_type,
        server_timestamp=event_row.server_timestamp,
    )


@router.post(
    "/episodes/{episode_id}/pre-ai",
    response_model=ResearchEpisodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def lock_pre_ai_decision(
    episode_id: int,
    body: DecisionSubmission,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchEpisodeResponse:
    research_mode_guard()
    episode, participant = get_episode_for_user(
        db,
        episode_id=episode_id,
        current_user=current_user,
        lock=True,
    )
    if episode.participant_id != participant.id or participant.role not in CLINICIAN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned clinician can lock the pre-AI decision",
        )
    if body.task_schema_version != episode.epoch.task_schema_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Decision schema does not match the frozen research epoch",
        )
    if episode.state != ResearchEpisodeState.PRE_AI or episode.pre_ai_decision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pre-AI decision is already locked or the episode is out of order",
        )
    now = utc_now()
    content = {
        "task_schema_version": body.task_schema_version,
        "decision": body.decision,
        "confidence": body.confidence,
        "client_active_seconds": body.client_active_seconds,
        "client_started_at": body.client_started_at,
        "client_submitted_at": body.client_submitted_at,
    }
    row = PreAIDecision(
        episode_id=episode.id,
        task_schema_version=body.task_schema_version,
        decision=body.decision,
        confidence=body.confidence,
        client_active_seconds=body.client_active_seconds,
        server_elapsed_seconds=_elapsed_seconds(episode.pre_ai_started_at, now),
        client_started_at=body.client_started_at,
        client_submitted_at=body.client_submitted_at,
        submitted_at=now,
        content_sha256=sha256_json(content),
    )
    db.add(row)
    episode.state = ResearchEpisodeState.PRE_AI_LOCKED
    episode.pre_ai_locked_at = now
    db.flush()
    _append_system_event(
        db,
        episode=episode,
        participant_id=participant.id,
        event_type="pre_ai_locked",
        payload={"content_sha256": row.content_sha256},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The pre-AI decision was already submitted",
        ) from exc
    db.refresh(episode)
    return _episode_response(db, episode)


@router.post(
    "/episodes/{episode_id}/reveal",
    response_model=ResearchEpisodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def reveal_ai(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchEpisodeResponse:
    research_mode_guard()
    episode, participant = get_episode_for_user(
        db,
        episode_id=episode_id,
        current_user=current_user,
        lock=True,
    )
    if episode.participant_id != participant.id or participant.role not in CLINICIAN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned clinician can reveal AI output",
        )
    if (
        episode.state != ResearchEpisodeState.PRE_AI_LOCKED
        or not episode.pre_ai_decision
        or episode.ai_reveal
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI reveal requires exactly one locked pre-AI decision",
        )
    result, payload, provenance, artifact_sha256 = build_ai_snapshot(
        db,
        case_id=episode.case_id,
    )
    if result.model_version != episode.epoch.model_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Inference model version does not match the frozen research epoch; "
                "start a new epoch before reveal"
            ),
        )
    if (
        artifact_sha256
        and episode.epoch.model_artifact_sha256
        and artifact_sha256.lower() != episode.epoch.model_artifact_sha256.lower()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inference artifact hash does not match the frozen research epoch",
        )
    now = utc_now()
    reveal = AIReveal(
        episode_id=episode.id,
        inference_result_id=result.id,
        model_version=result.model_version,
        model_artifact_sha256=artifact_sha256,
        result_schema_version=episode.epoch.result_schema_version,
        ui_version=episode.epoch.ui_version,
        payload=payload,
        payload_sha256=sha256_json(payload),
        provenance=provenance,
        inference_created_at=result.created_at,
        revealed_at=now,
    )
    db.add(reveal)
    episode.state = ResearchEpisodeState.AI_REVEALED
    episode.ai_revealed_at = now
    db.flush()
    _append_system_event(
        db,
        episode=episode,
        participant_id=participant.id,
        event_type="ai_revealed",
        payload={
            "payload_sha256": reveal.payload_sha256,
            "model_version": reveal.model_version,
            "artifact_sha256": reveal.model_artifact_sha256,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI output was already revealed for this episode",
        ) from exc
    db.refresh(episode)
    return _episode_response(db, episode)


@router.post(
    "/episodes/{episode_id}/final",
    response_model=ResearchEpisodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def lock_final_decision(
    episode_id: int,
    body: FinalDecisionSubmission,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchEpisodeResponse:
    research_mode_guard()
    episode, participant = get_episode_for_user(
        db,
        episode_id=episode_id,
        current_user=current_user,
        lock=True,
    )
    if episode.participant_id != participant.id or participant.role not in CLINICIAN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned clinician can lock the final decision",
        )
    if body.task_schema_version != episode.epoch.task_schema_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Decision schema does not match the frozen research epoch",
        )
    if (
        episode.state != ResearchEpisodeState.AI_REVEALED
        or not episode.ai_reveal
        or episode.final_decision
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Final decision requires a completed AI reveal",
        )
    now = utc_now()
    predicted_class = _predicted_class(episode)
    final_class = body.decision.get("malocclusion_class")
    agreement = None
    override = None
    if predicted_class and final_class:
        matches_ai = _normalized_decision_value(predicted_class) == (
            _normalized_decision_value(final_class)
        )
        agreement = "agree" if matches_ai else "disagree"
        override = not matches_ai
    content = {
        "task_schema_version": body.task_schema_version,
        "decision": body.decision,
        "confidence": body.confidence,
        "agreement": agreement,
        "override": override,
        "override_reason": None,
        "usefulness": None,
        "client_active_seconds": body.client_active_seconds,
        "client_started_at": body.client_started_at,
        "client_submitted_at": body.client_submitted_at,
    }
    final = FinalDecision(
        episode_id=episode.id,
        task_schema_version=body.task_schema_version,
        decision=body.decision,
        confidence=body.confidence,
        agreement=agreement,
        override=override,
        override_reason=None,
        usefulness=None,
        client_active_seconds=body.client_active_seconds,
        server_elapsed_seconds=_elapsed_seconds(episode.ai_revealed_at, now),
        client_started_at=body.client_started_at,
        client_submitted_at=body.client_submitted_at,
        submitted_at=now,
        content_sha256=sha256_json(content),
    )
    db.add(final)
    episode.final_decision = final
    _ensure_default_instruments(db, episode.study)
    episode.state = ResearchEpisodeState.FINAL_LOCKED
    episode.final_locked_at = now
    db.flush()
    _append_system_event(
        db,
        episode=episode,
        participant_id=participant.id,
        event_type="final_decision_locked",
        payload={
            "content_sha256": final.content_sha256,
            "agreement_derived": agreement,
            "override_derived": override,
        },
    )
    db.flush()
    follow_up = _follow_up_plan(db, episode)
    if follow_up.required:
        _append_system_event(
            db,
            episode=episode,
            participant_id=participant.id,
            event_type="follow_up_scheduled",
            payload={
                "kind": follow_up.kind,
                "triggers": follow_up.triggers,
                "instrument_code": follow_up.instrument_code,
                "instrument_version": follow_up.instrument_version,
                "period_code": follow_up.period_code,
            },
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Final decision was already submitted",
        ) from exc
    db.refresh(episode)
    return _episode_response(db, episode)


@router.post(
    "/episodes/{episode_id}/corrections",
    response_model=ResearchCorrectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def append_correction(
    episode_id: int,
    body: ResearchCorrectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchCorrectionResponse:
    research_mode_guard()
    episode, participant = get_episode_for_user(
        db,
        episode_id=episode_id,
        current_user=current_user,
        lock=True,
    )
    if (
        participant.role != ResearchRole.RESEARCH_ADMIN
        and participant.id != episode.participant_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Participant is not authorized to correct this episode",
        )
    target_model = CORRECTION_TARGET_MODELS[body.target_type]
    target = (
        db.query(target_model)
        .filter(
            target_model.id == body.target_id,
            target_model.episode_id == episode.id,
        )
        .first()
    )
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Correction target was not found in this research episode",
        )
    content = body.model_dump(mode="json")
    correction = ResearchCorrection(
        episode_id=episode.id,
        created_by_participant_id=participant.id,
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        corrected_payload=body.corrected_payload,
        content_sha256=sha256_json(content),
    )
    db.add(correction)
    db.flush()
    _append_system_event(
        db,
        episode=episode,
        participant_id=participant.id,
        event_type="correction_appended",
        payload={
            "target_type": body.target_type,
            "target_id": body.target_id,
            "correction_sha256": correction.content_sha256,
        },
    )
    db.commit()
    db.refresh(correction)
    return ResearchCorrectionResponse(
        id=correction.id,
        episode_id=correction.episode_id,
        target_type=correction.target_type,
        target_id=correction.target_id,
        reason=correction.reason,
        created_at=correction.created_at,
        content_sha256=correction.content_sha256,
    )


@router.post(
    "/instruments",
    response_model=StudyInstrumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_instrument(
    body: StudyInstrumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> StudyInstrumentResponse:
    research_mode_guard()
    study = get_study_or_404(db, body.study_code)
    _participant_for_study(
        db,
        study=study,
        current_user=current_user,
        roles=ADMIN_ROLES,
    )
    instrument = StudyInstrument(
        study_id=study.id,
        code=body.code,
        version=body.version,
        name=body.name,
        construct=body.construct,
        definition=body.definition,
        schedule=body.schedule,
        scoring_spec=body.scoring_spec,
        is_active=body.is_active,
    )
    db.add(instrument)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Instrument code and version already exist",
        ) from exc
    db.refresh(instrument)
    return StudyInstrumentResponse(
        id=instrument.id,
        study_code=study.code,
        code=instrument.code,
        version=instrument.version,
        name=instrument.name,
        construct=instrument.construct,
        definition=instrument.definition,
        schedule=instrument.schedule,
        is_active=instrument.is_active,
    )


@router.get("/instruments", response_model=list[StudyInstrumentResponse])
def list_instruments(
    study_code: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> list[StudyInstrumentResponse]:
    research_mode_guard()
    study = get_study_or_404(db, study_code)
    _participant_for_study(db, study=study, current_user=current_user)
    rows = (
        db.query(StudyInstrument)
        .filter(
            StudyInstrument.study_id == study.id,
            StudyInstrument.is_active.is_(True),
        )
        .order_by(StudyInstrument.code, StudyInstrument.version)
        .all()
    )
    return [
        StudyInstrumentResponse(
            id=row.id,
            study_code=study.code,
            code=row.code,
            version=row.version,
            name=row.name,
            construct=row.construct,
            definition=row.definition,
            schedule=row.schedule,
            is_active=row.is_active,
        )
        for row in rows
    ]


@router.post(
    "/surveys",
    response_model=SurveyResponseOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_survey(
    body: SurveyResponseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> SurveyResponseOut:
    research_mode_guard()
    study = get_study_or_404(db, body.study_code)
    participant = _participant_for_study(
        db,
        study=study,
        current_user=current_user,
    )
    instrument = (
        db.query(StudyInstrument)
        .filter(
            StudyInstrument.study_id == study.id,
            StudyInstrument.code == body.instrument_code,
            StudyInstrument.version == body.instrument_version,
            StudyInstrument.is_active.is_(True),
        )
        .first()
    )
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active study instrument not found",
        )
    episode = None
    if body.episode_id is not None:
        episode = (
            db.query(ResearchEpisode)
            .filter(
                ResearchEpisode.id == body.episode_id,
                ResearchEpisode.study_id == study.id,
                ResearchEpisode.participant_id == participant.id,
            )
            .first()
        )
        if not episode:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Research episode not found for participant",
            )
    existing_response = (
        db.query(SurveyResponse)
        .filter(
            SurveyResponse.participant_id == participant.id,
            SurveyResponse.instrument_id == instrument.id,
            SurveyResponse.episode_id == body.episode_id,
            SurveyResponse.period_code == body.period_code,
        )
        .first()
    )
    if existing_response:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This instrument was already submitted for the requested period",
        )
    content = body.model_dump(mode="json")
    now = utc_now()
    response = SurveyResponse(
        participant_id=participant.id,
        instrument_id=instrument.id,
        episode_id=body.episode_id,
        period_code=body.period_code,
        responses=body.responses,
        completion_status=body.completion_status,
        missing_reason=body.missing_reason,
        client_started_at=body.client_started_at,
        client_submitted_at=body.client_submitted_at,
        submitted_at=now,
        content_sha256=sha256_json(content),
    )
    db.add(response)
    db.flush()
    if episode is not None:
        _append_system_event(
            db,
            episode=episode,
            participant_id=participant.id,
            event_type="survey_response_recorded",
            payload={
                "instrument_code": instrument.code,
                "instrument_version": instrument.version,
                "period_code": body.period_code,
                "completion_status": body.completion_status,
                "content_sha256": response.content_sha256,
            },
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This instrument was already submitted for the requested period",
        ) from exc
    db.refresh(response)
    return SurveyResponseOut(
        id=response.id,
        instrument_code=instrument.code,
        instrument_version=instrument.version,
        episode_id=response.episode_id,
        period_code=response.period_code,
        completion_status=response.completion_status,
        submitted_at=response.submitted_at,
        content_sha256=response.content_sha256,
    )


@router.get(
    "/reference-queue",
    response_model=list[ReferenceQueueItem],
)
def list_reference_queue(
    study_code: str = Query(..., min_length=3, max_length=64),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> list[ReferenceQueueItem]:
    """Return reviewable episodes without clinician decisions or AI output."""
    research_mode_guard()
    study = get_study_or_404(db, study_code)
    reviewer = _participant_for_study(
        db,
        study=study,
        current_user=current_user,
        roles=REVIEWER_ROLES | ADJUDICATOR_ROLES,
    )
    episodes = (
        db.query(ResearchEpisode)
        .filter(
            ResearchEpisode.study_id == study.id,
            ResearchEpisode.state.in_(
                [
                    ResearchEpisodeState.FINAL_LOCKED,
                    ResearchEpisodeState.ADJUDICATED,
                ]
            ),
        )
        .order_by(ResearchEpisode.final_locked_at.asc(), ResearchEpisode.id.asc())
        .all()
    )
    items: list[ReferenceQueueItem] = []
    for episode in episodes:
        reviews = (
            db.query(ReferenceAssessment)
            .filter(ReferenceAssessment.episode_id == episode.id)
            .order_by(ReferenceAssessment.id)
            .all()
        )
        own_rounds = [
            row.review_round
            for row in reviews
            if row.reviewer_participant_id == reviewer.id
        ]
        distinct_reviewer_count = len(
            {row.reviewer_participant_id for row in reviews}
        )
        items.append(
            ReferenceQueueItem(
                episode_id=episode.id,
                case_code=f"R-{episode.id:06d}",
                site_code=episode.site.code,
                epoch_code=episode.epoch.code,
                state=episode.state,
                image_count=len(episode.case.images),
                submitted_review_rounds=own_rounds,
                total_reference_reviews=distinct_reviewer_count,
                required_reference_reviews=study.minimum_reference_reviews,
                adjudication_ready=(
                    distinct_reviewer_count >= study.minimum_reference_reviews
                    and episode.adjudication is None
                ),
            )
        )
    return items


@router.get(
    "/episodes/{episode_id}/reference-case",
    response_model=ReferenceCaseResponse,
)
def get_blinded_reference_case(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ReferenceCaseResponse:
    """Expose only source images and protocol identifiers to reference reviewers."""
    research_mode_guard()
    episode = db.query(ResearchEpisode).filter(ResearchEpisode.id == episode_id).first()
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research episode not found",
        )
    reviewer = get_participant_for_user(
        db,
        study_id=episode.study_id,
        user_id=current_user.id,
        required_roles=REVIEWER_ROLES | ADJUDICATOR_ROLES,
    )
    if reviewer.id == episode.participant_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The treating participant cannot review their own episode",
        )
    if episode.state not in {
        ResearchEpisodeState.FINAL_LOCKED,
        ResearchEpisodeState.ADJUDICATED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The episode is not available for reference review",
        )
    return ReferenceCaseResponse(
        episode_id=episode.id,
        case_code=f"R-{episode.id:06d}",
        site_code=episode.site.code,
        epoch_code=episode.epoch.code,
        state=episode.state,
        images=[
            ReferenceImageResponse(
                id=image.id,
                filename=image.filename,
                content_type=image.content_type,
                image_url=(
                    f"/api/v1/research/episodes/{episode.id}/"
                    f"reference-images/{image.id}"
                ),
            )
            for image in sorted(episode.case.images, key=lambda item: item.id)
        ],
    )


@router.get("/episodes/{episode_id}/reference-images/{image_id}")
def get_blinded_reference_image(
    episode_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> Response:
    research_mode_guard()
    episode = db.query(ResearchEpisode).filter(ResearchEpisode.id == episode_id).first()
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research episode not found",
        )
    reviewer = get_participant_for_user(
        db,
        study_id=episode.study_id,
        user_id=current_user.id,
        required_roles=REVIEWER_ROLES | ADJUDICATOR_ROLES,
    )
    if reviewer.id == episode.participant_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The treating participant cannot review their own episode",
        )
    if episode.state not in {
        ResearchEpisodeState.FINAL_LOCKED,
        ResearchEpisodeState.ADJUDICATED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The episode is not available for reference review",
        )
    image = (
        db.query(Image)
        .filter(Image.id == image_id, Image.case_id == episode.case_id)
        .first()
    )
    if not image or not image.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        )
    try:
        data = download_file_from_s3(image.file_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image data not found",
        ) from exc
    except (ClientError, BotoCoreError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read image from storage",
        ) from exc
    return Response(
        content=data,
        media_type=image.content_type or "image/jpeg",
        headers={"Cache-Control": "private, no-store"},
    )


@router.post(
    "/episodes/{episode_id}/reference-assessments",
    response_model=ReferenceAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_reference_assessment(
    episode_id: int,
    body: ReferenceAssessmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ReferenceAssessmentResponse:
    research_mode_guard()
    episode = (
        db.query(ResearchEpisode)
        .filter(ResearchEpisode.id == episode_id)
        .with_for_update()
        .first()
    )
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research episode not found",
        )
    reviewer = get_participant_for_user(
        db,
        study_id=episode.study_id,
        user_id=current_user.id,
        required_roles=REVIEWER_ROLES,
    )
    if episode.state != ResearchEpisodeState.FINAL_LOCKED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reference review requires a locked final decision",
        )
    if reviewer.id == episode.participant_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The treating participant cannot review their own episode",
        )
    if not body.blinded_to_clinician:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Independent reference assessments must remain blinded",
        )
    if body.task_schema_version != episode.epoch.task_schema_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reference schema does not match the frozen research epoch",
        )
    content = body.model_dump(mode="json")
    row = ReferenceAssessment(
        episode_id=episode.id,
        reviewer_participant_id=reviewer.id,
        review_round=body.review_round,
        task_schema_version=body.task_schema_version,
        decision=body.decision,
        confidence=body.confidence,
        blinded_to_clinician=body.blinded_to_clinician,
        submitted_at=utc_now(),
        content_sha256=sha256_json(content),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This reviewer already submitted the requested review round",
        ) from exc
    db.refresh(row)
    return ReferenceAssessmentResponse(
        id=row.id,
        episode_id=row.episode_id,
        reviewer_participant_code=reviewer.participant_code,
        review_round=row.review_round,
        task_schema_version=row.task_schema_version,
        confidence=row.confidence,
        blinded_to_clinician=row.blinded_to_clinician,
        submitted_at=row.submitted_at,
        content_sha256=row.content_sha256,
    )


@router.get(
    "/episodes/{episode_id}/reference-assessments",
    response_model=list[ReferenceAssessmentDetail],
)
def list_reference_assessments_for_adjudication(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> list[ReferenceAssessmentDetail]:
    """Expose independent reviews only to the adjudication role."""
    research_mode_guard()
    episode = db.query(ResearchEpisode).filter(ResearchEpisode.id == episode_id).first()
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research episode not found",
        )
    get_participant_for_user(
        db,
        study_id=episode.study_id,
        user_id=current_user.id,
        required_roles=ADJUDICATOR_ROLES,
    )
    rows = (
        db.query(ReferenceAssessment)
        .filter(ReferenceAssessment.episode_id == episode.id)
        .order_by(
            ReferenceAssessment.review_round,
            ReferenceAssessment.reviewer_participant_id,
        )
        .all()
    )
    return [
        ReferenceAssessmentDetail(
            id=row.id,
            episode_id=row.episode_id,
            reviewer_participant_code=row.reviewer.participant_code,
            review_round=row.review_round,
            task_schema_version=row.task_schema_version,
            decision=row.decision,
            confidence=row.confidence,
            blinded_to_clinician=row.blinded_to_clinician,
            submitted_at=row.submitted_at,
            content_sha256=row.content_sha256,
        )
        for row in rows
    ]


@router.post(
    "/episodes/{episode_id}/adjudication",
    response_model=AdjudicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_adjudication(
    episode_id: int,
    body: AdjudicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> AdjudicationResponse:
    research_mode_guard()
    episode = (
        db.query(ResearchEpisode)
        .filter(ResearchEpisode.id == episode_id)
        .with_for_update()
        .first()
    )
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research episode not found",
        )
    adjudicator = get_participant_for_user(
        db,
        study_id=episode.study_id,
        user_id=current_user.id,
        required_roles=ADJUDICATOR_ROLES,
    )
    if body.task_schema_version != episode.epoch.task_schema_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Adjudication schema does not match the frozen research epoch",
        )
    if episode.state != ResearchEpisodeState.FINAL_LOCKED or episode.adjudication:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Adjudication requires an unadjudicated, locked final decision",
        )
    review_count = (
        db.query(func.count(func.distinct(ReferenceAssessment.reviewer_participant_id)))
        .filter(ReferenceAssessment.episode_id == episode.id)
        .scalar()
        or 0
    )
    if review_count < episode.study.minimum_reference_reviews:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"At least {episode.study.minimum_reference_reviews} independent "
                "reference assessments are required"
            ),
        )
    now = utc_now()
    content = body.model_dump(mode="json")
    row = Adjudication(
        episode_id=episode.id,
        adjudicator_participant_id=adjudicator.id,
        reference_standard_version=body.reference_standard_version,
        task_schema_version=body.task_schema_version,
        consensus_decision=body.consensus_decision,
        uncertainty=body.uncertainty,
        rationale=body.rationale,
        submitted_at=now,
        content_sha256=sha256_json(content),
    )
    db.add(row)
    episode.state = ResearchEpisodeState.ADJUDICATED
    episode.adjudicated_at = now
    db.flush()
    _append_system_event(
        db,
        episode=episode,
        participant_id=adjudicator.id,
        event_type="episode_adjudicated",
        payload={
            "content_sha256": row.content_sha256,
            "reference_standard_version": row.reference_standard_version,
        },
    )
    db.commit()
    db.refresh(row)
    return AdjudicationResponse(
        id=row.id,
        episode_id=row.episode_id,
        reference_standard_version=row.reference_standard_version,
        task_schema_version=row.task_schema_version,
        uncertainty=row.uncertainty,
        submitted_at=row.submitted_at,
        content_sha256=row.content_sha256,
    )


def _export_participants(rows: Iterable[ResearchParticipant]) -> list[Dict[str, Any]]:
    return [
        {
            "participant_code": row.participant_code,
            "site_code": row.site.code,
            "role": enum_value(row.role),
            "specialty": row.specialty,
            "experience_band": row.experience_band,
            "consent_version": row.consent_version,
            "consented_at": row.consented_at,
            "withdrawn_at": row.withdrawn_at,
            "is_active": row.is_active,
        }
        for row in rows
    ]


def _deidentify_research_payload(value: Any, episode_id: int) -> Any:
    """Replace operational case/image identifiers in exported nested JSON."""
    image_codes: Dict[str, str] = {}

    def scrub(item: Any) -> Any:
        if isinstance(item, list):
            return [scrub(child) for child in item]
        if not isinstance(item, dict):
            return item
        result: Dict[str, Any] = {}
        for key, child in item.items():
            if key == "case_id":
                result[key] = f"R-{episode_id:06d}"
            elif key == "image_id" and child is not None:
                raw = str(child)
                if raw not in image_codes:
                    image_codes[raw] = (
                        f"R-{episode_id:06d}-IMG-{len(image_codes) + 1:02d}"
                    )
                result[key] = image_codes[raw]
            else:
                result[key] = scrub(child)
        return result

    return scrub(value)


@router.get(
    "/studies/{study_code}/export",
    response_model=ResearchExportResponse,
)
def export_study(
    study_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ResearchExportResponse:
    research_mode_guard()
    study = get_study_or_404(db, study_code)
    _participant_for_study(
        db,
        study=study,
        current_user=current_user,
        roles=ADMIN_ROLES,
    )
    participants = (
        db.query(ResearchParticipant)
        .filter(ResearchParticipant.study_id == study.id)
        .order_by(ResearchParticipant.id)
        .all()
    )
    epochs = (
        db.query(ResearchEpoch)
        .filter(ResearchEpoch.study_id == study.id)
        .order_by(ResearchEpoch.id)
        .all()
    )
    instruments = (
        db.query(StudyInstrument)
        .filter(StudyInstrument.study_id == study.id)
        .order_by(StudyInstrument.code, StudyInstrument.version)
        .all()
    )
    episodes = (
        db.query(ResearchEpisode)
        .filter(ResearchEpisode.study_id == study.id)
        .order_by(ResearchEpisode.id)
        .all()
    )
    episode_ids = [row.id for row in episodes]

    def rows_for(model):
        if not episode_ids:
            return []
        return (
            db.query(model)
            .filter(model.episode_id.in_(episode_ids))
            .order_by(model.id)
            .all()
        )

    pre_rows = rows_for(PreAIDecision)
    reveal_rows = rows_for(AIReveal)
    final_rows = rows_for(FinalDecision)
    event_rows = rows_for(ResearchEvent)
    survey_rows = (
        db.query(SurveyResponse)
        .filter(
            SurveyResponse.participant_id.in_([row.id for row in participants])
        )
        .order_by(SurveyResponse.id)
        .all()
        if participants
        else []
    )
    reference_rows = rows_for(ReferenceAssessment)
    adjudication_rows = rows_for(Adjudication)
    correction_rows = rows_for(ResearchCorrection)

    return ResearchExportResponse(
        study={
            "code": study.code,
            "title": study.title,
            "protocol_version": study.protocol_version,
            "consent_version": study.consent_version,
            "primary_task": study.primary_task,
            "primary_outcome": study.primary_outcome,
            "status": enum_value(study.status),
        },
        generated_at=utc_now(),
        schema_version=settings.research_export_schema_version,
        participants=_export_participants(participants),
        epochs=[
            {
                "epoch_id": row.id,
                "code": row.code,
                "protocol_version": row.protocol_version,
                "task_schema_version": row.task_schema_version,
                "ui_version": row.ui_version,
                "model_version": row.model_version,
                "model_artifact_sha256": row.model_artifact_sha256,
                "deployment_policy_version": row.deployment_policy_version,
                "result_schema_version": row.result_schema_version,
                "starts_at": row.starts_at,
                "ends_at": row.ends_at,
                "is_active": row.is_active,
            }
            for row in epochs
        ],
        instruments=[
            {
                "code": row.code,
                "version": row.version,
                "name": row.name,
                "construct": row.construct,
                "definition": row.definition,
                "schedule": row.schedule,
                "scoring_spec": row.scoring_spec,
                "is_active": row.is_active,
                "created_at": row.created_at,
            }
            for row in instruments
        ],
        episodes=[
            {
                "episode_id": row.id,
                "participant_code": row.participant.participant_code,
                "site_code": row.site.code,
                "epoch_code": row.epoch.code,
                "case_code": f"R-{row.id:06d}",
                "state": enum_value(row.state),
                "condition_code": row.condition_code,
                "exposure_index": row.exposure_index,
                "pre_ai_started_at": row.pre_ai_started_at,
                "pre_ai_locked_at": row.pre_ai_locked_at,
                "ai_revealed_at": row.ai_revealed_at,
                "final_locked_at": row.final_locked_at,
                "adjudicated_at": row.adjudicated_at,
                "protocol_deviation": row.protocol_deviation,
            }
            for row in episodes
        ],
        pre_ai_decisions=[
            {
                "id": row.id,
                "episode_id": row.episode_id,
                "task_schema_version": row.task_schema_version,
                "decision": row.decision,
                "confidence": row.confidence,
                "client_active_seconds": row.client_active_seconds,
                "server_elapsed_seconds": row.server_elapsed_seconds,
                "submitted_at": row.submitted_at,
                "content_sha256": row.content_sha256,
            }
            for row in pre_rows
        ],
        ai_reveals=[
            {
                "id": row.id,
                "episode_id": row.episode_id,
                "model_version": row.model_version,
                "model_artifact_sha256": row.model_artifact_sha256,
                "result_schema_version": row.result_schema_version,
                "ui_version": row.ui_version,
                "payload": _deidentify_research_payload(
                    row.payload,
                    row.episode_id,
                ),
                "payload_sha256": row.payload_sha256,
                "provenance": row.provenance,
                "inference_created_at": row.inference_created_at,
                "revealed_at": row.revealed_at,
            }
            for row in reveal_rows
        ],
        final_decisions=[
            {
                "id": row.id,
                "episode_id": row.episode_id,
                "task_schema_version": row.task_schema_version,
                "decision": row.decision,
                "confidence": row.confidence,
                "agreement": row.agreement,
                "override": row.override,
                "override_reason": row.override_reason,
                "usefulness": row.usefulness,
                "client_active_seconds": row.client_active_seconds,
                "server_elapsed_seconds": row.server_elapsed_seconds,
                "submitted_at": row.submitted_at,
                "content_sha256": row.content_sha256,
            }
            for row in final_rows
        ],
        events=[
            {
                "id": row.id,
                "episode_id": row.episode_id,
                "participant_code": row.participant.participant_code,
                "event_uuid": row.event_uuid,
                "sequence_no": row.sequence_no,
                "event_type": row.event_type,
                "schema_version": row.schema_version,
                "client_timestamp": row.client_timestamp,
                "client_timezone_offset_minutes": row.client_timezone_offset_minutes,
                "server_timestamp": row.server_timestamp,
                "payload": row.payload,
            }
            for row in event_rows
        ],
        survey_responses=[
            {
                "id": row.id,
                "participant_code": row.participant.participant_code,
                "instrument_code": row.instrument.code,
                "instrument_version": row.instrument.version,
                "episode_id": row.episode_id,
                "period_code": row.period_code,
                "responses": row.responses,
                "completion_status": row.completion_status,
                "missing_reason": row.missing_reason,
                "submitted_at": row.submitted_at,
                "content_sha256": row.content_sha256,
            }
            for row in survey_rows
        ],
        reference_assessments=[
            {
                "id": row.id,
                "episode_id": row.episode_id,
                "reviewer_participant_code": row.reviewer.participant_code,
                "review_round": row.review_round,
                "task_schema_version": row.task_schema_version,
                "decision": row.decision,
                "confidence": row.confidence,
                "blinded_to_clinician": row.blinded_to_clinician,
                "submitted_at": row.submitted_at,
                "content_sha256": row.content_sha256,
            }
            for row in reference_rows
        ],
        adjudications=[
            {
                "id": row.id,
                "episode_id": row.episode_id,
                "adjudicator_participant_code": row.adjudicator.participant_code,
                "reference_standard_version": row.reference_standard_version,
                "task_schema_version": row.task_schema_version,
                "consensus_decision": row.consensus_decision,
                "uncertainty": row.uncertainty,
                "rationale": row.rationale,
                "submitted_at": row.submitted_at,
                "content_sha256": row.content_sha256,
            }
            for row in adjudication_rows
        ],
        corrections=[
            {
                "id": row.id,
                "episode_id": row.episode_id,
                "created_by_participant_code": row.created_by.participant_code,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "reason": row.reason,
                "corrected_payload": _deidentify_research_payload(
                    row.corrected_payload,
                    row.episode_id,
                ),
                "created_at": row.created_at,
                "content_sha256": row.content_sha256,
            }
            for row in correction_rows
        ],
    )
