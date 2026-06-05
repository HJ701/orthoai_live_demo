from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models import JobState


# Auth Schemas
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


class OTPRequest(BaseModel):
    email: EmailStr


class OTPResponse(BaseModel):
    message: str
    # Note: In production, OTP should be sent via email/SMS, not returned in response


class OTPLogin(BaseModel):
    email: EmailStr
    otp: str  # 6-digit OTP code


class UserCreate(BaseModel):
    email: EmailStr


class UserResponse(BaseModel):
    id: int
    email: str
    auth_provider: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    terms_accepted: bool = False
    terms_accepted_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class TermsAcceptanceResponse(BaseModel):
    message: str
    id: int
    email: str
    auth_provider: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    terms_accepted: bool
    terms_accepted_at: datetime
    last_login_at: Optional[datetime] = None
    created_at: datetime


# Case Schemas
class CaseCreate(BaseModel):
    consent_checked: bool = False
    patient_id: Optional[str] = None
    title: Optional[str] = None
    clinic_location: Optional[str] = None
    tags: Optional[List[str]] = []
    note: Optional[str] = None


class CaseResponse(BaseModel):
    id: int
    user_id: int
    consent_checked: bool
    patient_id: str
    title: str
    clinic_location: Optional[str] = None
    note: Optional[str] = None
    tags: Optional[List[str]] = []
    status: Optional[JobState] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# Image Schemas
class ImageUploadResponse(BaseModel):
    image_ids: List[int]


class ImageResponse(BaseModel):
    id: int
    case_id: int
    filename: str
    file_size: Optional[int]
    content_type: Optional[str]
    uploaded_at: datetime
    
    class Config:
        from_attributes = True


# Inference Schemas
class InferenceRequest(BaseModel):
    case_id: int


class InferenceResponse(BaseModel):
    job_id: int


class InferenceStatusResponse(BaseModel):
    state: JobState
    progress: float
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# Results Schemas
class ImageEvidenceResponse(BaseModel):
    image_id: int
    filename: str
    findings: Dict[str, Any]
    confidence: float


class CaseResultsResponse(BaseModel):
    case_id: int
    model_version: str
    findings: Dict[str, Any]
    summary: str
    confidences: Dict[str, float]
    per_image_evidence: List[ImageEvidenceResponse]
    created_at: datetime


# Notes Schemas
class CaseNoteCreate(BaseModel):
    content: str


class CaseNoteResponse(BaseModel):
    id: int
    case_id: int
    content: str
    created_by: int
    created_at: datetime
    
    class Config:
        from_attributes = True

