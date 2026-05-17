#!/usr/bin/env python3
"""Script to create a test user for development"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, AuthProvider

def create_test_user(email: str = "test@example.com", provider: str = "email"):
    """Create a test user
    
    Args:
        email: User email address
        provider: Authentication provider (email, google, microsoft, github, apple)
    """
    db = SessionLocal()
    try:
        # Map provider string to enum
        provider_map = {
            "email": AuthProvider.EMAIL,
            "google": AuthProvider.GOOGLE,
            "microsoft": AuthProvider.MICROSOFT,
            "github": AuthProvider.GITHUB,
            "apple": AuthProvider.APPLE
        }
        
        auth_provider = provider_map.get(provider.lower(), AuthProvider.EMAIL)
        
        # Check if user exists with this provider
        existing_user = db.query(User).filter(
            User.email == email,
            User.auth_provider == auth_provider
        ).first()
        
        if existing_user:
            print(f"User with email '{email}' and provider '{provider}' already exists")
            return
        
        # Create new user
        user_data = {
            "email": email,
            "auth_provider": auth_provider,
            "is_active": True
        }
        
        # Add provider_user_id for SSO providers
        if auth_provider != AuthProvider.EMAIL:
            user_data["provider_user_id"] = f"{provider}_test_{email.split('@')[0]}"
            user_data["full_name"] = f"Test User ({provider})"
        
        user = User(**user_data)
        db.add(user)
        db.commit()
        print(f"Created user successfully")
        print(f"Email: {email}")
        print(f"Provider: {provider}")
        if auth_provider == AuthProvider.EMAIL:
            print(f"Note: Use OTP authentication to login. Request OTP at /api/v1/auth/request-otp")
        else:
            print(f"Note: This is a test SSO user. Implement SSO flow to login.")
    except Exception as e:
        print(f"Error creating user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        email = sys.argv[1]
        provider = sys.argv[2] if len(sys.argv) > 2 else "email"
        create_test_user(email, provider)
    else:
        create_test_user()

