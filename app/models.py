from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Boolean, ForeignKey, Enum as SQLEnum, UniqueConstraint, JSON
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

