import json
import sqlite3

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_current_user_dependency
from app.api.routes import clinical
from app.database import get_db
from app.models import AuditLog, Case, InferenceJob, InferenceResult, JobState, User
from app.schemas import (
    ActivityCaseSummary,
    ActivityClinicalValidationSummary,
    AuditLogResponse,
    UserActivityResponse,
    UserResponse,
)


router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user_dependency),
):
    """Return the authenticated user's profile and terms status."""
    return current_user


def parse_audit_details(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return value if isinstance(value, dict) else {"value": value}


def build_case_summaries(db: Session, current_user: User) -> list[ActivityCaseSummary]:
    cases = db.query(Case).filter(
        Case.user_id == current_user.id,
    ).order_by(Case.created_at.desc()).all()

    summaries: list[ActivityCaseSummary] = []
    for case in cases:
        latest_job = db.query(InferenceJob).filter(
            InferenceJob.case_id == case.id,
        ).order_by(InferenceJob.created_at.desc()).first()
        has_results = False
        if latest_job and latest_job.state == JobState.DONE:
            has_results = db.query(InferenceResult).filter(
                InferenceResult.job_id == latest_job.id,
            ).first() is not None
        summaries.append(
            ActivityCaseSummary(
                id=case.id,
                patient_id=case.patient_id,
                title=case.title,
                status=latest_job.state if latest_job else None,
                has_results=has_results,
                created_at=case.created_at,
            )
        )
    return summaries


def load_clinical_validations(
    source_case_ids: list[int],
    limit: int,
) -> tuple[int, list[ActivityClinicalValidationSummary]]:
    if not source_case_ids:
        return 0, []

    clinical.init_clinical_db()
    placeholders = ", ".join("?" for _ in source_case_ids)
    query = f"""
        SELECT id, orthoai_case_id, site, case_id, m_class, dhc,
               ai_class, ai_dhc, class_match, created_at
        FROM clinical_cases
        WHERE orthoai_case_id IN ({placeholders})
        ORDER BY id DESC
        LIMIT ?
    """
    with sqlite3.connect(clinical.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(
            f"SELECT COUNT(*) FROM clinical_cases WHERE orthoai_case_id IN ({placeholders})",
            source_case_ids,
        ).fetchone()[0]
        rows = conn.execute(query, source_case_ids + [limit]).fetchall()

    validations: list[ActivityClinicalValidationSummary] = []
    for row in rows:
        row_dict = dict(row)
        row_dict["class_match"] = (
            None if row_dict["class_match"] is None else bool(row_dict["class_match"])
        )
        validations.append(ActivityClinicalValidationSummary(**row_dict))
    return int(total), validations


@router.get("/activity", response_model=UserActivityResponse)
def get_activity(
    audit_limit: int = Query(25, ge=1, le=100),
    clinical_limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
):
    """Return the authenticated user's real profile, cases, validations, and audit trail."""
    cases = build_case_summaries(db, current_user)
    source_case_ids = [case.id for case in cases]
    clinical_validation_count, clinical_validations = load_clinical_validations(
        source_case_ids,
        clinical_limit,
    )

    audit_rows = db.query(AuditLog).filter(
        AuditLog.user_id == current_user.id,
    ).order_by(AuditLog.created_at.desc()).limit(audit_limit).all()
    audit_logs = [
        AuditLogResponse(
            id=row.id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            details=parse_audit_details(row.details),
            ip_address=row.ip_address,
            created_at=row.created_at,
        )
        for row in audit_rows
    ]

    return UserActivityResponse(
        user=current_user,
        case_count=len(cases),
        completed_diagnoses=sum(1 for case in cases if case.has_results),
        clinical_validation_count=clinical_validation_count,
        cases=cases,
        clinical_validations=clinical_validations,
        audit_logs=audit_logs,
    )
