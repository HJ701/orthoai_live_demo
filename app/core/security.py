from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
import random
from app.config import settings
from app.database import get_db
from app.models import AuthProvider, User, OTP
from app.schemas import TokenData

security = HTTPBearer()
oauth2_scheme = security  # For backward compatibility


def generate_otp() -> str:
    """Generate a 6-digit OTP code"""
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])


def verify_otp(db: Session, email: str, code: str) -> bool:
    """Verify OTP code for an email"""
    otp = db.query(OTP).filter(
        OTP.email == email,
        OTP.code == code,
        OTP.used == False,
        OTP.expires_at > datetime.utcnow()
    ).order_by(OTP.created_at.desc()).first()
    
    if not otp:
        return False
    
    # Mark OTP as used
    otp.used = True
    db.commit()
    
    return True


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def create_otp_record(db: Session, email: str, user_id: Optional[int] = None) -> str:
    """Create an OTP record and return the code"""
    # Invalidate any existing unused OTPs for this email
    db.query(OTP).filter(
        OTP.email == email,
        OTP.used == False
    ).update({"used": True})
    
    # Generate new OTP
    code = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=10)  # OTP expires in 10 minutes
    
    otp = OTP(
        email=email,
        code=code,
        user_id=user_id,
        expires_at=expires_at
    )
    db.add(otp)
    db.commit()
    
    return code


def get_current_user(
    credentials: HTTPBearer = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get the current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str = payload.get("sub")
        user_id = payload.get("uid")
        if email is None and user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = None
    if user_id is not None:
        try:
            user = db.query(User).filter(User.id == int(user_id)).first()
        except (TypeError, ValueError):
            user = None
    if user is None and email:
        user = db.query(User).filter(
            User.email == email,
            User.auth_provider == AuthProvider.EMAIL,
        ).first()
    if user is None and email:
        user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get the current active user"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
