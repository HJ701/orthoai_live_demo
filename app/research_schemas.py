from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import ResearchEpisodeState, ResearchRole, ResearchStudyStatus


def _normalize_iotn_grade(
    value: Any,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
) -> Any:
    """Accept ordinary numeric grades and clinician-entered IOTN codes/text."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number or text value")
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{field_name} numeric grades must be whole numbers")
        grade = int(value)
        if grade < minimum or grade > maximum:
            raise ValueError(
                f"{field_name} numeric grades must be between {minimum} and {maximum}"
            )
        return grade
    if isinstance(value, str):
        grade = value.strip()
        if not grade:
            return None
        if len(grade) > 64:
            raise ValueError(f"{field_name} must be 64 characters or fewer")
        if grade.isdigit():
            numeric_grade = int(grade)
            if numeric_grade < minimum or numeric_grade > maximum:
                raise ValueError(
                    f"{field_name} numeric grades must be between {minimum} and {maximum}"
                )
            return numeric_grade
        return grade
    raise ValueError(f"{field_name} must be a number or text value")


class ResearchClinicianAccessIn(BaseModel):
    """The client identifies only the fixed pilot; identity and role are derived."""

    study_code: str = Field("ORTHOAI-HCI-V3", min_length=3, max_length=64)


class ResearchParticipantAdminCreate(BaseModel):
    study_code: str = Field(..., min_length=3, max_length=64)
    site_code: str = Field(..., min_length=1, max_length=64)
    user_id: int = Field(..., gt=0)
    participant_code: str = Field(..., min_length=1, max_length=64)
    role: ResearchRole
    specialty: Optional[str] = Field(None, max_length=128)
    experience_band: Optional[str] = Field(None, max_length=64)
    consent_version: str = Field(..., min_length=1, max_length=64)
    consented_at: datetime


class ResearchParticipantWithdrawIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=1000)


class ResearchParticipantResponse(BaseModel):
    id: int
    study_code: str
    site_code: str
    participant_code: str
    role: ResearchRole
    specialty: Optional[str] = None
    experience_band: Optional[str] = None
    consent_version: str
    consented_at: datetime
    withdrawn_at: Optional[datetime] = None
    is_active: bool


class ResearchContextResponse(BaseModel):
    enabled: bool
    participant: Optional[ResearchParticipantResponse] = None
    study_status: Optional[ResearchStudyStatus] = None
    protocol_version: Optional[str] = None
    consent_version: Optional[str] = None
    active_epoch_code: Optional[str] = None
    ui_version: str


class ResearchEligibleUserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    is_enrolled: bool
    participant_code: Optional[str] = None
    role: Optional[ResearchRole] = None


class ResearchEpisodeCreate(BaseModel):
    study_code: str = Field(..., min_length=3, max_length=64)
    case_id: int = Field(..., gt=0)
    client_session_id: str = Field(..., min_length=8, max_length=128)
    condition_code: Optional[str] = Field(None, max_length=64)


class ResearchNextEpisodeCreate(BaseModel):
    study_code: str = Field(..., min_length=3, max_length=64)
    client_session_id: str = Field(..., min_length=8, max_length=128)
    condition_code: Optional[str] = Field(None, max_length=64)


class ResearchEpisodeRepeatCreate(BaseModel):
    client_session_id: str = Field(..., min_length=8, max_length=128)
    reason_code: Literal[
        "participant_requested",
        "new_clinical_opinion",
        "workflow_practice",
        "other",
    ] = "participant_requested"


class DecisionSubmission(BaseModel):
    task_schema_version: str = Field(..., min_length=1, max_length=64)
    decision: Dict[str, Any]
    confidence: float = Field(..., ge=0, le=100)
    client_active_seconds: Optional[float] = Field(None, ge=0, le=86_400)
    client_started_at: Optional[datetime] = None
    client_submitted_at: Optional[datetime] = None

    @field_validator("decision")
    @classmethod
    def decision_must_not_be_empty(cls, value: Dict[str, Any]):
        if not value:
            raise ValueError("decision must contain at least one field")
        normalized = dict(value)
        if "dhc" in normalized:
            normalized["dhc"] = _normalize_iotn_grade(
                normalized["dhc"],
                field_name="IOTN DHC",
                minimum=1,
                maximum=5,
            )
        if "ac" in normalized:
            normalized["ac"] = _normalize_iotn_grade(
                normalized["ac"],
                field_name="IOTN AC",
                minimum=1,
                maximum=10,
            )
        return normalized


class FinalDecisionSubmission(DecisionSubmission):
    agreement: Optional[Literal["agree", "partial", "disagree"]] = None
    override: Optional[bool] = None
    override_reason: Optional[str] = Field(None, max_length=2000)
    usefulness: Optional[int] = Field(None, ge=1, le=5)


class ResearchEventIn(BaseModel):
    event_uuid: str = Field(..., min_length=8, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    sequence_no: int = Field(..., ge=1)
    event_type: str = Field(..., min_length=1, max_length=64)
    schema_version: str = Field("research-event/1.0.0", min_length=1, max_length=64)
    client_timestamp: Optional[datetime] = None
    client_timezone_offset_minutes: Optional[int] = Field(None, ge=-840, le=840)
    payload: Optional[Dict[str, Any]] = None


class ResearchEventResponse(BaseModel):
    id: int
    event_uuid: str
    sequence_no: int
    event_type: str
    server_timestamp: datetime
    duplicate: bool = False


class PreAIDecisionResponse(BaseModel):
    id: int
    task_schema_version: str
    decision: Dict[str, Any]
    confidence: float
    client_active_seconds: Optional[float] = None
    server_elapsed_seconds: float
    submitted_at: datetime
    content_sha256: str


class AIRevealResponse(BaseModel):
    id: int
    model_version: str
    model_artifact_sha256: Optional[str] = None
    result_schema_version: str
    ui_version: str
    payload: Dict[str, Any]
    payload_sha256: str
    provenance: Optional[Dict[str, Any]] = None
    inference_created_at: datetime
    revealed_at: datetime


class FinalDecisionResponse(BaseModel):
    id: int
    task_schema_version: str
    decision: Dict[str, Any]
    confidence: float
    agreement: Optional[str] = None
    override: Optional[bool] = None
    override_reason: Optional[str] = None
    usefulness: Optional[int] = None
    client_active_seconds: Optional[float] = None
    server_elapsed_seconds: float
    submitted_at: datetime
    content_sha256: str


class ResearchFollowUpPlan(BaseModel):
    required: bool
    kind: Literal["none", "reason", "pulse", "reason_and_pulse"]
    triggers: List[str]
    instrument_code: str = "ai-influence-micro"
    instrument_version: str = "1.0"
    period_code: Optional[str] = None
    completed: bool = False


class ResearchEpisodeResponse(BaseModel):
    id: int
    study_code: str
    site_code: str
    epoch_code: str
    participant_code: str
    case_id: int
    state: ResearchEpisodeState
    condition_code: Optional[str] = None
    exposure_index: int
    attempt_index: int
    repeat_of_episode_id: Optional[int] = None
    last_event_sequence: int
    pre_ai_started_at: datetime
    pre_ai_locked_at: Optional[datetime] = None
    ai_revealed_at: Optional[datetime] = None
    final_locked_at: Optional[datetime] = None
    adjudicated_at: Optional[datetime] = None
    pre_ai_decision: Optional[PreAIDecisionResponse] = None
    ai_reveal: Optional[AIRevealResponse] = None
    final_decision: Optional[FinalDecisionResponse] = None
    follow_up: ResearchFollowUpPlan


class ResearchEpisodeList(BaseModel):
    total: int
    items: List[ResearchEpisodeResponse]


class StudyInstrumentCreate(BaseModel):
    study_code: str = Field(..., min_length=3, max_length=64)
    code: str = Field(..., min_length=1, max_length=64)
    version: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    construct: str = Field(..., min_length=1, max_length=128)
    definition: Dict[str, Any]
    schedule: Optional[Dict[str, Any]] = None
    scoring_spec: Optional[Dict[str, Any]] = None
    is_active: bool = True


class StudyInstrumentResponse(BaseModel):
    id: int
    study_code: str
    code: str
    version: str
    name: str
    construct: str
    definition: Dict[str, Any]
    schedule: Optional[Dict[str, Any]] = None
    is_active: bool


class SurveyResponseCreate(BaseModel):
    study_code: str = Field(..., min_length=3, max_length=64)
    instrument_code: str = Field(..., min_length=1, max_length=64)
    instrument_version: str = Field(..., min_length=1, max_length=64)
    episode_id: Optional[int] = Field(None, gt=0)
    period_code: str = Field(..., min_length=1, max_length=64)
    responses: Optional[Dict[str, Any]] = None
    completion_status: Literal["completed", "declined", "missed"]
    missing_reason: Optional[str] = Field(None, max_length=255)
    client_started_at: Optional[datetime] = None
    client_submitted_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_completion(self):
        if self.completion_status == "completed" and not self.responses:
            raise ValueError("responses are required for a completed survey")
        if self.completion_status != "completed" and not self.missing_reason:
            raise ValueError("missing_reason is required for a non-completed survey")
        return self


class SurveyResponseOut(BaseModel):
    id: int
    instrument_code: str
    instrument_version: str
    episode_id: Optional[int] = None
    period_code: str
    completion_status: str
    submitted_at: datetime
    content_sha256: str


class ReferenceAssessmentCreate(BaseModel):
    task_schema_version: str = Field(..., min_length=1, max_length=64)
    decision: Dict[str, Any]
    confidence: Optional[float] = Field(None, ge=0, le=100)
    review_round: int = Field(1, ge=1, le=10)
    blinded_to_clinician: bool = True

    @field_validator("decision")
    @classmethod
    def reference_decision_must_not_be_empty(cls, value: Dict[str, Any]):
        if not value:
            raise ValueError("decision must contain at least one field")
        return value


class ReferenceAssessmentResponse(BaseModel):
    id: int
    episode_id: int
    reviewer_participant_code: str
    review_round: int
    task_schema_version: str
    confidence: Optional[float] = None
    blinded_to_clinician: bool
    submitted_at: datetime
    content_sha256: str


class ReferenceAssessmentDetail(ReferenceAssessmentResponse):
    decision: Dict[str, Any]


class ReferenceImageResponse(BaseModel):
    id: int
    filename: str
    content_type: Optional[str] = None
    image_url: str


class ReferenceCaseResponse(BaseModel):
    episode_id: int
    case_code: str
    site_code: str
    epoch_code: str
    state: ResearchEpisodeState
    images: List[ReferenceImageResponse]


class ReferenceQueueItem(BaseModel):
    episode_id: int
    case_code: str
    site_code: str
    epoch_code: str
    state: ResearchEpisodeState
    image_count: int
    submitted_review_rounds: List[int]
    total_reference_reviews: int
    required_reference_reviews: int
    adjudication_ready: bool


class AdjudicationCreate(BaseModel):
    reference_standard_version: str = Field(..., min_length=1, max_length=64)
    task_schema_version: str = Field(..., min_length=1, max_length=64)
    consensus_decision: Dict[str, Any]
    uncertainty: Optional[str] = Field(None, max_length=64)
    rationale: Optional[str] = Field(None, max_length=4000)

    @field_validator("consensus_decision")
    @classmethod
    def consensus_must_not_be_empty(cls, value: Dict[str, Any]):
        if not value:
            raise ValueError("consensus_decision must contain at least one field")
        return value


class AdjudicationResponse(BaseModel):
    id: int
    episode_id: int
    reference_standard_version: str
    task_schema_version: str
    uncertainty: Optional[str] = None
    submitted_at: datetime
    content_sha256: str


class ResearchCorrectionCreate(BaseModel):
    target_type: Literal[
        "pre_ai_decision",
        "ai_reveal",
        "final_decision",
        "survey_response",
        "reference_assessment",
        "adjudication",
    ]
    target_id: int = Field(..., gt=0)
    reason: str = Field(..., min_length=3, max_length=4000)
    corrected_payload: Dict[str, Any]


class ResearchCorrectionResponse(BaseModel):
    id: int
    episode_id: int
    target_type: str
    target_id: int
    reason: str
    created_at: datetime
    content_sha256: str


class ResearchExportResponse(BaseModel):
    study: Dict[str, Any]
    generated_at: datetime
    schema_version: str
    participants: List[Dict[str, Any]]
    epochs: List[Dict[str, Any]]
    instruments: List[Dict[str, Any]]
    episodes: List[Dict[str, Any]]
    pre_ai_decisions: List[Dict[str, Any]]
    ai_reveals: List[Dict[str, Any]]
    final_decisions: List[Dict[str, Any]]
    events: List[Dict[str, Any]]
    survey_responses: List[Dict[str, Any]]
    reference_assessments: List[Dict[str, Any]]
    adjudications: List[Dict[str, Any]]
    corrections: List[Dict[str, Any]]
