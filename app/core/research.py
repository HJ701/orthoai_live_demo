from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AIReveal,
    Finding,
    Image,
    ImageEvidence,
    InferenceJob,
    InferenceResult,
    JobState,
    ResearchEpisode,
    ResearchParticipant,
    ResearchRole,
    ResearchStudy,
    User,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def research_mode_guard() -> None:
    if not settings.research_mode_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Research Mode is disabled",
        )


def get_study_or_404(db: Session, study_code: str) -> ResearchStudy:
    study = db.query(ResearchStudy).filter(ResearchStudy.code == study_code).first()
    if not study:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research study not found",
        )
    return study


def get_participant_for_user(
    db: Session,
    *,
    study_id: int,
    user_id: int,
    required_roles: Optional[Iterable[ResearchRole]] = None,
) -> ResearchParticipant:
    participant = (
        db.query(ResearchParticipant)
        .filter(
            ResearchParticipant.study_id == study_id,
            ResearchParticipant.user_id == user_id,
            ResearchParticipant.is_active.is_(True),
            ResearchParticipant.withdrawn_at.is_(None),
        )
        .first()
    )
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active participant enrollment exists for this study",
        )
    allowed = set(required_roles or [])
    if allowed and participant.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Participant role is not authorized for this action",
        )
    return participant


def get_episode_for_user(
    db: Session,
    *,
    episode_id: int,
    current_user: User,
    lock: bool = False,
) -> Tuple[ResearchEpisode, ResearchParticipant]:
    query = db.query(ResearchEpisode).filter(ResearchEpisode.id == episode_id)
    if lock:
        query = query.with_for_update()
    episode = query.first()
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research episode not found",
        )
    participant = get_participant_for_user(
        db,
        study_id=episode.study_id,
        user_id=current_user.id,
    )
    if (
        participant.role not in {ResearchRole.RESEARCH_ADMIN}
        and episode.participant_id != participant.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research episode not found",
        )
    return episode, participant


def get_latest_inference_result(
    db: Session,
    case_id: int,
) -> Tuple[InferenceJob, InferenceResult]:
    job = (
        db.query(InferenceJob)
        .filter(
            InferenceJob.case_id == case_id,
            InferenceJob.state == JobState.DONE,
        )
        .order_by(InferenceJob.completed_at.desc())
        .first()
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The case has no completed inference result available for controlled reveal",
        )
    result = (
        db.query(InferenceResult)
        .filter(InferenceResult.job_id == job.id)
        .first()
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The completed inference job has no result",
        )
    return job, result


def _decode_json(value: Any, fallback: Any):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _finding_location(value: Any):
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def build_ai_snapshot(
    db: Session,
    *,
    case_id: int,
) -> Tuple[InferenceResult, Dict[str, Any], Dict[str, Any], Optional[str]]:
    _, result = get_latest_inference_result(db, case_id)
    findings = _decode_json(result.findings, {})
    evidence_records = (
        db.query(ImageEvidence)
        .filter(ImageEvidence.result_id == result.id)
        .order_by(ImageEvidence.id)
        .all()
    )
    evidence_payload = []
    confidences: Dict[str, float] = {}
    for evidence in evidence_records:
        image = db.query(Image).filter(Image.id == evidence.image_id).first()
        stored_findings = _decode_json(evidence.findings, None)
        if not isinstance(stored_findings, dict):
            finding_rows = (
                db.query(Finding)
                .filter(Finding.image_evidence_id == evidence.id)
                .order_by(Finding.id)
                .all()
            )
            stored_findings = {
                "image_id": evidence.image_id,
                "detections": [
                    {
                        "type": finding.type,
                        "label": finding.type,
                        "confidence": finding.confidence,
                        "location": _finding_location(finding.location),
                        "factor": finding.factor,
                    }
                    for finding in finding_rows
                ],
            }
        evidence_payload.append(
            {
                "image_id": evidence.image_id,
                "filename": image.filename if image else "unknown",
                "findings": stored_findings,
                "confidence": evidence.confidence,
            }
        )
        if evidence.confidence is not None:
            confidences[f"image_{evidence.image_id}"] = evidence.confidence

    payload = {
        "case_id": case_id,
        "model_version": result.model_version,
        "findings": findings,
        "summary": result.summary or "",
        "confidences": confidences,
        "per_image_evidence": evidence_payload,
        "created_at": (
            result.created_at.isoformat()
            if isinstance(result.created_at, datetime)
            else result.created_at
        ),
    }
    model_records = findings.get("models", {}) if isinstance(findings, dict) else {}
    malocclusion = (
        model_records.get("malocclusion", {})
        if isinstance(model_records, dict)
        else {}
    )
    primary_provenance = (
        malocclusion.get("provenance", {})
        if isinstance(malocclusion, dict)
        else {}
    )
    provenance = {
        "model_run_id": findings.get("model_run_id") if isinstance(findings, dict) else None,
        "models": model_records,
        "build_commit": settings.build_commit,
        "snapshot_created_at": utc_now().isoformat(),
    }
    artifact_sha256 = (
        primary_provenance.get("artifact_sha256")
        if isinstance(primary_provenance, dict)
        else None
    )
    return result, payload, provenance, artifact_sha256


def ai_reveal_response_payload(reveal: AIReveal) -> Dict[str, Any]:
    return {
        "id": reveal.id,
        "model_version": reveal.model_version,
        "model_artifact_sha256": reveal.model_artifact_sha256,
        "result_schema_version": reveal.result_schema_version,
        "ui_version": reveal.ui_version,
        "payload": reveal.payload,
        "payload_sha256": reveal.payload_sha256,
        "provenance": reveal.provenance,
        "inference_created_at": reveal.inference_created_at,
        "revealed_at": reveal.revealed_at,
    }
