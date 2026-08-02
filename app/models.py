from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    event,
    text as sa_text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
from app.database import Base


class JobState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class AuthProvider(str, enum.Enum):
    """Authentication provider types"""
    EMAIL = "email"  # Email/OTP authentication
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    GITHUB = "github"
    APPLE = "apple"
    # Add more providers as needed


class ResearchStudyStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class ResearchRole(str, enum.Enum):
    CLINICIAN = "clinician"
    REVIEWER = "reviewer"
    ADJUDICATOR = "adjudicator"
    RESEARCH_ADMIN = "research_admin"


class ResearchEpisodeState(str, enum.Enum):
    PRE_AI = "pre_ai"
    PRE_AI_LOCKED = "pre_ai_locked"
    AI_REVEALED = "ai_revealed"
    FINAL_LOCKED = "final_locked"
    ADJUDICATED = "adjudicated"
    WITHDRAWN = "withdrawn"


def _enum_values(enum_type):
    return [item.value for item in enum_type]


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)  # Not unique - same email can exist across providers
    
    # SSO Provider Information
    auth_provider = Column(SQLEnum(AuthProvider), nullable=False, default=AuthProvider.EMAIL, index=True)
    provider_user_id = Column(String, nullable=True, index=True)  # User ID from SSO provider
    
    # User Profile Information
    full_name = Column(String, nullable=True)  # Full name from SSO provider
    avatar_url = Column(String, nullable=True)  # Profile picture URL
    
    # Authentication
    hashed_password = Column(String, nullable=True)  # Optional - only for email/OTP auth
    
    # Status and Metadata
    is_active = Column(Boolean, default=True)
    terms_accepted = Column(Boolean, default=False, nullable=False)
    terms_accepted_at = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    provider_data = Column(JSON, nullable=True)  # Additional provider-specific data (e.g., roles, groups)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Unique constraint: same provider + provider_user_id should be unique
    # Email can be shared across providers, but provider_user_id is unique per provider
    __table_args__ = (
        UniqueConstraint('auth_provider', 'provider_user_id', name='uq_provider_user'),
    )
    
    # Relationships
    cases = relationship("Case", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")
    otps = relationship("OTP", back_populates="user", cascade="all, delete-orphan")
    research_participations = relationship("ResearchParticipant", back_populates="user")


class Case(Base):
    __tablename__ = "cases"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    consent_checked = Column(Boolean, default=False)
    patient_id = Column(String, nullable=True)
    title = Column(String, nullable=True)
    clinic_location = Column(String, nullable=True)
    note = Column(String, nullable=True)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="cases")
    images = relationship("Image", back_populates="case", cascade="all, delete-orphan")
    inference_jobs = relationship("InferenceJob", back_populates="case", cascade="all, delete-orphan")
    notes = relationship("CaseNote", back_populates="case", cascade="all, delete-orphan")
    research_episodes = relationship("ResearchEpisode", back_populates="case")


class Image(Base):
    __tablename__ = "images"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)
    content_type = Column(String)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    case = relationship("Case", back_populates="images")
    evidence = relationship("ImageEvidence", back_populates="image", cascade="all, delete-orphan")


class InferenceJob(Base):
    __tablename__ = "inference_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    celery_task_id = Column(String, unique=True, index=True)
    state = Column(SQLEnum(JobState), default=JobState.QUEUED)
    progress = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    case = relationship("Case", back_populates="inference_jobs")
    results = relationship("InferenceResult", back_populates="job", uselist=False, cascade="all, delete-orphan")


class InferenceResult(Base):
    __tablename__ = "inference_results"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("inference_jobs.id"), nullable=False, unique=True)
    model_version = Column(String, nullable=False)
    findings = Column(Text)  # JSON string
    summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    job = relationship("InferenceJob", back_populates="results")
    evidence = relationship("ImageEvidence", back_populates="result", cascade="all, delete-orphan")
    research_reveals = relationship("AIReveal", back_populates="inference_result")


class ImageEvidence(Base):
    __tablename__ = "image_evidence"
    
    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("inference_results.id"), nullable=False)
    image_id = Column(Integer, ForeignKey("images.id"), nullable=False)
    findings = Column(Text, nullable=True)  # JSON string - deprecated, kept for migration
    confidence = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    result = relationship("InferenceResult", back_populates="evidence")
    image = relationship("Image", back_populates="evidence")
    finding_records = relationship("Finding", back_populates="image_evidence", cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"
    
    id = Column(Integer, primary_key=True, index=True)
    image_evidence_id = Column(Integer, ForeignKey("image_evidence.id"), nullable=False)
    type = Column(String, nullable=False)  # e.g., "lesion", "normal"
    confidence = Column(Float, nullable=False)
    location = Column(String, nullable=True)  # e.g., "upper_left", "center"
    factor = Column(String, nullable=True)  # e.g., severity factor, risk factor, or other classification
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    image_evidence = relationship("ImageEvidence", back_populates="finding_records")


class CaseNote(Base):
    __tablename__ = "case_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    case = relationship("Case", back_populates="notes")


class OTP(Base):
    __tablename__ = "otps"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, index=True)
    code = Column(String, nullable=False)  # 6-digit OTP code
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="otps")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)  # upload, run, view, download
    resource_type = Column(String, nullable=False)  # case, image, inference, pdf
    resource_id = Column(Integer, nullable=True)
    details = Column(Text)  # JSON string for additional context
    ip_address = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")


class ResearchStudy(Base):
    __tablename__ = "research_studies"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    protocol_version = Column(String(64), nullable=False)
    consent_version = Column(String(64), nullable=False)
    primary_task = Column(String(128), nullable=False)
    primary_outcome = Column(String(255), nullable=True)
    status = Column(
        SQLEnum(
            ResearchStudyStatus,
            values_callable=_enum_values,
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=ResearchStudyStatus.DRAFT,
        index=True,
    )
    minimum_reference_reviews = Column(Integer, nullable=False, default=2)
    config = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'closed')",
            name="ck_research_study_status",
        ),
        CheckConstraint(
            "minimum_reference_reviews >= 1",
            name="ck_research_study_minimum_reviews",
        ),
    )

    sites = relationship("ResearchSite", back_populates="study")
    epochs = relationship("ResearchEpoch", back_populates="study")
    participants = relationship("ResearchParticipant", back_populates="study")
    episodes = relationship("ResearchEpisode", back_populates="study")
    instruments = relationship("StudyInstrument", back_populates="study")


class ResearchSite(Base):
    __tablename__ = "research_sites"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(
        Integer,
        ForeignKey("research_studies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    timezone = Column(String(64), nullable=False, default="UTC")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("study_id", "code", name="uq_research_site_study_code"),
    )

    study = relationship("ResearchStudy", back_populates="sites")
    participants = relationship("ResearchParticipant", back_populates="site")
    episodes = relationship("ResearchEpisode", back_populates="site")


class ResearchEpoch(Base):
    __tablename__ = "research_epochs"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(
        Integer,
        ForeignKey("research_studies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code = Column(String(64), nullable=False)
    label = Column(String(255), nullable=False)
    protocol_version = Column(String(64), nullable=False)
    task_schema_version = Column(String(64), nullable=False)
    ui_version = Column(String(64), nullable=False)
    model_version = Column(String(255), nullable=False)
    model_artifact_sha256 = Column(String(64), nullable=True)
    deployment_policy_version = Column(String(64), nullable=False)
    result_schema_version = Column(String(128), nullable=False)
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    config = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("study_id", "code", name="uq_research_epoch_study_code"),
        Index(
            "uq_research_epoch_one_active_per_study",
            "study_id",
            unique=True,
            postgresql_where=sa_text("is_active"),
            sqlite_where=sa_text("is_active = 1"),
        ),
    )

    study = relationship("ResearchStudy", back_populates="epochs")
    episodes = relationship("ResearchEpisode", back_populates="epoch")


class ResearchParticipant(Base):
    __tablename__ = "research_participants"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(
        Integer,
        ForeignKey("research_studies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    site_id = Column(
        Integer,
        ForeignKey("research_sites.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    participant_code = Column(String(64), nullable=False)
    role = Column(
        SQLEnum(
            ResearchRole,
            values_callable=_enum_values,
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=ResearchRole.CLINICIAN,
        index=True,
    )
    specialty = Column(String(128), nullable=True)
    experience_band = Column(String(64), nullable=True)
    consent_version = Column(String(64), nullable=False)
    consented_at = Column(DateTime(timezone=True), nullable=False)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    participant_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "study_id",
            "participant_code",
            name="uq_research_participant_study_code",
        ),
        UniqueConstraint(
            "study_id",
            "user_id",
            name="uq_research_participant_study_user",
        ),
        CheckConstraint(
            "role IN ('clinician', 'reviewer', 'adjudicator', 'research_admin')",
            name="ck_research_participant_role",
        ),
    )

    study = relationship("ResearchStudy", back_populates="participants")
    site = relationship("ResearchSite", back_populates="participants")
    user = relationship("User", back_populates="research_participations")
    episodes = relationship("ResearchEpisode", back_populates="participant")
    events = relationship("ResearchEvent", back_populates="participant")
    survey_responses = relationship("SurveyResponse", back_populates="participant")


class ResearchEpisode(Base):
    __tablename__ = "research_episodes"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(
        Integer,
        ForeignKey("research_studies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    site_id = Column(
        Integer,
        ForeignKey("research_sites.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    epoch_id = Column(
        Integer,
        ForeignKey("research_epochs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    participant_id = Column(
        Integer,
        ForeignKey("research_participants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    case_id = Column(
        Integer,
        ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    state = Column(
        SQLEnum(
            ResearchEpisodeState,
            values_callable=_enum_values,
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=ResearchEpisodeState.PRE_AI,
        index=True,
    )
    condition_code = Column(String(64), nullable=True)
    client_session_id = Column(String(128), nullable=False)
    exposure_index = Column(Integer, nullable=False)
    attempt_index = Column(Integer, nullable=False, default=1, server_default="1")
    repeat_of_episode_id = Column(
        Integer,
        ForeignKey("research_episodes.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    pre_ai_started_at = Column(DateTime(timezone=True), nullable=False)
    pre_ai_locked_at = Column(DateTime(timezone=True), nullable=True)
    ai_revealed_at = Column(DateTime(timezone=True), nullable=True)
    final_locked_at = Column(DateTime(timezone=True), nullable=True)
    adjudicated_at = Column(DateTime(timezone=True), nullable=True)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    protocol_deviation = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "study_id",
            "participant_id",
            "case_id",
            "attempt_index",
            name="uq_research_episode_study_participant_case_attempt",
        ),
        CheckConstraint("exposure_index >= 1", name="ck_research_episode_exposure"),
        CheckConstraint("attempt_index >= 1", name="ck_research_episode_attempt"),
        CheckConstraint(
            "state IN ('pre_ai', 'pre_ai_locked', 'ai_revealed', "
            "'final_locked', 'adjudicated', 'withdrawn')",
            name="ck_research_episode_state",
        ),
    )

    study = relationship("ResearchStudy", back_populates="episodes")
    site = relationship("ResearchSite", back_populates="episodes")
    epoch = relationship("ResearchEpoch", back_populates="episodes")
    participant = relationship("ResearchParticipant", back_populates="episodes")
    case = relationship("Case", back_populates="research_episodes")
    pre_ai_decision = relationship("PreAIDecision", back_populates="episode", uselist=False)
    ai_reveal = relationship("AIReveal", back_populates="episode", uselist=False)
    final_decision = relationship("FinalDecision", back_populates="episode", uselist=False)
    events = relationship("ResearchEvent", back_populates="episode")
    survey_responses = relationship("SurveyResponse", back_populates="episode")
    reference_assessments = relationship("ReferenceAssessment", back_populates="episode")
    adjudication = relationship("Adjudication", back_populates="episode", uselist=False)
    corrections = relationship("ResearchCorrection", back_populates="episode")


class PreAIDecision(Base):
    __tablename__ = "pre_ai_decisions"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(
        Integer,
        ForeignKey("research_episodes.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    task_schema_version = Column(String(64), nullable=False)
    decision = Column(JSON, nullable=False)
    confidence = Column(Float, nullable=False)
    client_active_seconds = Column(Float, nullable=True)
    server_elapsed_seconds = Column(Float, nullable=False)
    client_started_at = Column(DateTime(timezone=True), nullable=True)
    client_submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    content_sha256 = Column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_pre_ai_confidence",
        ),
        CheckConstraint(
            "server_elapsed_seconds >= 0",
            name="ck_pre_ai_server_elapsed",
        ),
        CheckConstraint(
            "client_active_seconds IS NULL OR client_active_seconds >= 0",
            name="ck_pre_ai_client_active",
        ),
    )

    episode = relationship("ResearchEpisode", back_populates="pre_ai_decision")


class AIReveal(Base):
    __tablename__ = "ai_reveals"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(
        Integer,
        ForeignKey("research_episodes.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    inference_result_id = Column(
        Integer,
        ForeignKey("inference_results.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_version = Column(String(255), nullable=False)
    model_artifact_sha256 = Column(String(64), nullable=True)
    result_schema_version = Column(String(128), nullable=False)
    ui_version = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    provenance = Column(JSON, nullable=True)
    inference_created_at = Column(DateTime(timezone=True), nullable=False)
    revealed_at = Column(DateTime(timezone=True), nullable=False)

    episode = relationship("ResearchEpisode", back_populates="ai_reveal")
    inference_result = relationship("InferenceResult", back_populates="research_reveals")


class FinalDecision(Base):
    __tablename__ = "final_decisions"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(
        Integer,
        ForeignKey("research_episodes.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    task_schema_version = Column(String(64), nullable=False)
    decision = Column(JSON, nullable=False)
    confidence = Column(Float, nullable=False)
    agreement = Column(String(32), nullable=True)
    override = Column(Boolean, nullable=True)
    override_reason = Column(Text, nullable=True)
    usefulness = Column(Integer, nullable=True)
    client_active_seconds = Column(Float, nullable=True)
    server_elapsed_seconds = Column(Float, nullable=False)
    client_started_at = Column(DateTime(timezone=True), nullable=True)
    client_submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    content_sha256 = Column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_final_decision_confidence",
        ),
        CheckConstraint(
            "server_elapsed_seconds >= 0",
            name="ck_final_decision_server_elapsed",
        ),
        CheckConstraint(
            "client_active_seconds IS NULL OR client_active_seconds >= 0",
            name="ck_final_decision_client_active",
        ),
        CheckConstraint(
            "usefulness IS NULL OR (usefulness >= 1 AND usefulness <= 5)",
            name="ck_final_decision_usefulness",
        ),
    )

    episode = relationship("ResearchEpisode", back_populates="final_decision")


class ResearchEvent(Base):
    __tablename__ = "research_events"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(
        Integer,
        ForeignKey("research_episodes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    participant_id = Column(
        Integer,
        ForeignKey("research_participants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_uuid = Column(String(64), nullable=False, unique=True, index=True)
    idempotency_key = Column(String(128), nullable=False)
    sequence_no = Column(Integer, nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    schema_version = Column(String(64), nullable=False)
    client_timestamp = Column(DateTime(timezone=True), nullable=True)
    client_timezone_offset_minutes = Column(Integer, nullable=True)
    server_timestamp = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    payload = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "episode_id",
            "sequence_no",
            name="uq_research_event_episode_sequence",
        ),
        UniqueConstraint(
            "episode_id",
            "idempotency_key",
            name="uq_research_event_episode_idempotency",
        ),
        CheckConstraint("sequence_no >= 1", name="ck_research_event_sequence"),
    )

    episode = relationship("ResearchEpisode", back_populates="events")
    participant = relationship("ResearchParticipant", back_populates="events")


class StudyInstrument(Base):
    __tablename__ = "study_instruments"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(
        Integer,
        ForeignKey("research_studies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code = Column(String(64), nullable=False)
    version = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    construct = Column(String(128), nullable=False)
    definition = Column(JSON, nullable=False)
    schedule = Column(JSON, nullable=True)
    scoring_spec = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "study_id",
            "code",
            "version",
            name="uq_study_instrument_code_version",
        ),
    )

    study = relationship("ResearchStudy", back_populates="instruments")
    responses = relationship("SurveyResponse", back_populates="instrument")


class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(
        Integer,
        ForeignKey("research_participants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    instrument_id = Column(
        Integer,
        ForeignKey("study_instruments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    episode_id = Column(
        Integer,
        ForeignKey("research_episodes.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    period_code = Column(String(64), nullable=False)
    responses = Column(JSON, nullable=True)
    completion_status = Column(String(32), nullable=False)
    missing_reason = Column(String(255), nullable=True)
    client_started_at = Column(DateTime(timezone=True), nullable=True)
    client_submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    content_sha256 = Column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "participant_id",
            "instrument_id",
            "episode_id",
            "period_code",
            name="uq_survey_response_period",
        ),
        CheckConstraint(
            "completion_status IN ('completed', 'declined', 'missed')",
            name="ck_survey_response_completion",
        ),
    )

    participant = relationship("ResearchParticipant", back_populates="survey_responses")
    instrument = relationship("StudyInstrument", back_populates="responses")
    episode = relationship("ResearchEpisode", back_populates="survey_responses")


class ReferenceAssessment(Base):
    __tablename__ = "reference_assessments"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(
        Integer,
        ForeignKey("research_episodes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reviewer_participant_id = Column(
        Integer,
        ForeignKey("research_participants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    review_round = Column(Integer, nullable=False, default=1)
    task_schema_version = Column(String(64), nullable=False)
    decision = Column(JSON, nullable=False)
    confidence = Column(Float, nullable=True)
    blinded_to_clinician = Column(Boolean, nullable=False, default=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    content_sha256 = Column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "episode_id",
            "reviewer_participant_id",
            "review_round",
            name="uq_reference_assessment_reviewer_round",
        ),
        CheckConstraint(
            "review_round >= 1",
            name="ck_reference_assessment_round",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_reference_assessment_confidence",
        ),
        CheckConstraint(
            "blinded_to_clinician = true",
            name="ck_reference_assessment_blinded",
        ),
    )

    episode = relationship("ResearchEpisode", back_populates="reference_assessments")
    reviewer = relationship("ResearchParticipant")


class Adjudication(Base):
    __tablename__ = "adjudications"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(
        Integer,
        ForeignKey("research_episodes.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    adjudicator_participant_id = Column(
        Integer,
        ForeignKey("research_participants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reference_standard_version = Column(String(64), nullable=False)
    task_schema_version = Column(String(64), nullable=False)
    consensus_decision = Column(JSON, nullable=False)
    uncertainty = Column(String(64), nullable=True)
    rationale = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    content_sha256 = Column(String(64), nullable=False)

    episode = relationship("ResearchEpisode", back_populates="adjudication")
    adjudicator = relationship("ResearchParticipant")


class ResearchCorrection(Base):
    __tablename__ = "research_corrections"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(
        Integer,
        ForeignKey("research_episodes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_participant_id = Column(
        Integer,
        ForeignKey("research_participants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_type = Column(String(64), nullable=False)
    target_id = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    corrected_payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    content_sha256 = Column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "target_type IN ("
            "'pre_ai_decision', 'ai_reveal', 'final_decision', "
            "'survey_response', 'reference_assessment', 'adjudication'"
            ")",
            name="ck_research_correction_target_type",
        ),
    )

    episode = relationship("ResearchEpisode", back_populates="corrections")
    created_by = relationship("ResearchParticipant")


_IMMUTABLE_RESEARCH_MODELS = (
    PreAIDecision,
    AIReveal,
    FinalDecision,
    ResearchEvent,
    SurveyResponse,
    ReferenceAssessment,
    Adjudication,
    ResearchCorrection,
    StudyInstrument,
)


def _reject_immutable_mutation(_mapper, _connection, target):
    raise ValueError(
        f"{target.__class__.__name__} is immutable; append a ResearchCorrection instead"
    )


for _immutable_model in _IMMUTABLE_RESEARCH_MODELS:
    event.listen(_immutable_model, "before_update", _reject_immutable_mutation)
    event.listen(_immutable_model, "before_delete", _reject_immutable_mutation)
