from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from app.database import get_db
from app.models import User, AuthProvider
from app.core.security import (
    create_access_token,
    create_otp_record,
    verify_otp
)
from app.core.email import send_otp_email_async
from app.schemas import (
    SSOProviderInfo,
    SSOProviderList,
    Token,
    OTPRequest,
    OTPResponse,
    OTPLogin,
    TermsAcceptanceResponse,
    UserCreate,
    UserResponse,
)
from app.config import settings
from app.api.deps import get_current_user_dependency
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


SSO_PROVIDER_CLIENT_IDS = {
    "google": "google_oauth_client_id",
    "microsoft": "microsoft_oauth_client_id",
    "github": "github_oauth_client_id",
    "apple": "apple_oauth_client_id",
}


def get_email_user(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(
        User.email == email,
        User.auth_provider == AuthProvider.EMAIL,
    ).first()


def create_email_user(db: Session, email: str, full_name: Optional[str] = None) -> User:
    user = User(
        email=email,
        auth_provider=AuthProvider.EMAIL,
        full_name=full_name,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/request-otp", response_model=OTPResponse)
def request_otp(
    otp_request: OTPRequest,
    db: Session = Depends(get_db)
):
    """Request OTP code - generates and stores OTP for email"""
    email = otp_request.email.lower().strip()
    
    # Check if user exists with email provider, if not create one
    user = get_email_user(db, email)
    user_id = None
    
    if not user:
        # Auto-create user if doesn't exist
        user = create_email_user(db, email)
        user_id = user.id
    else:
        user_id = user.id
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user"
            )
    
    # Generate and store OTP
    otp_code = create_otp_record(db, email, user_id)
    
    # Send OTP via email asynchronously
    send_otp_email_async(email, otp_code)
    
    return OTPResponse(
        message=f"OTP sent to {email}"
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    user_data: UserCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    """Register an email/OTP user or return the existing email account."""
    email = user_data.email.lower().strip()
    user = get_email_user(db, email)
    if user:
        response.status_code = status.HTTP_200_OK
        if user_data.full_name and user.full_name != user_data.full_name:
            user.full_name = user_data.full_name
            db.commit()
            db.refresh(user)
        return user

    return create_email_user(db, email, user_data.full_name)


@router.post("/login", response_model=Token)
def login(
    login_data: OTPLogin,
    db: Session = Depends(get_db)
):
    """Login with email and OTP - returns JWT token"""
    email = login_data.email.lower().strip()
    otp_code = login_data.otp.strip()
    
    # Verify OTP
    if not verify_otp(db, email, otp_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user (prefer email provider, but allow any provider)
    user = get_email_user(db, email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    # Update last login timestamp
    user.last_login_at = datetime.utcnow()
    db.commit()
    
    # Create JWT token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={
            "sub": user.email,
            "uid": user.id,
            "provider": user.auth_provider.value,
        },
        expires_delta=access_token_expires,
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/sso/providers", response_model=SSOProviderList)
def list_sso_providers():
    """Return SSO providers that are configured for the current deployment."""
    providers = []
    for provider, setting_name in SSO_PROVIDER_CLIENT_IDS.items():
        enabled = bool(getattr(settings, setting_name, ""))
        reason = None if enabled else "OAuth client ID is not configured for this deployment."
        providers.append(
            SSOProviderInfo(
                provider=provider,
                enabled=enabled,
                reason=reason,
            )
        )
    return SSOProviderList(providers=providers)


@router.get("/sso/{provider}/login")
def start_sso_login(provider: str):
    """Fail explicitly until OAuth code-flow routes are implemented and configured."""
    normalized = provider.lower().strip()
    if normalized not in SSO_PROVIDER_CLIENT_IDS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unsupported SSO provider",
        )

    if not getattr(settings, SSO_PROVIDER_CLIENT_IDS[normalized], ""):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"{normalized} SSO is not configured on this deployment. "
                "Use email OTP sign-in or configure the OAuth client before enabling this button."
            ),
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            f"{normalized} SSO has a client ID configured, but the OAuth callback/token "
            "exchange flow is not implemented in this backend."
        ),
    )


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user_dependency),
):
    """Return the authenticated user's profile and terms status."""
    return current_user


@router.put("/accept-terms", response_model=TermsAcceptanceResponse)
def accept_terms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
):
    """Mark the authenticated user's terms as accepted."""
    accepted_at = datetime.utcnow()
    current_user.terms_accepted = True
    current_user.terms_accepted_at = accepted_at
    db.commit()

    return TermsAcceptanceResponse(
        message="Terms accepted",
        id=current_user.id,
        email=current_user.email,
        auth_provider=current_user.auth_provider.value,
        full_name=current_user.full_name,
        avatar_url=current_user.avatar_url,
        is_active=current_user.is_active,
        terms_accepted=True,
        terms_accepted_at=accepted_at,
        last_login_at=current_user.last_login_at,
        created_at=current_user.created_at,
    )
