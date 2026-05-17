# SSO Integration Guide

## Overview

The users table has been updated to support Single Sign-On (SSO) integration with multiple providers. The system maintains backward compatibility with the existing email/OTP authentication while providing a foundation for SSO providers like Google, Microsoft, GitHub, and Apple.

## Database Schema

### User Model Fields

- **`id`** (Integer, Primary Key) - Unique user identifier
- **`email`** (String, Indexed) - User email (not unique - can be shared across providers)
- **`auth_provider`** (Enum, Indexed) - Authentication provider type:
  - `email` - Email/OTP authentication (default)
  - `google` - Google OAuth
  - `microsoft` - Microsoft OAuth
  - `github` - GitHub OAuth
  - `apple` - Apple Sign In
- **`provider_user_id`** (String, Indexed, Nullable) - User ID from SSO provider
- **`full_name`** (String, Nullable) - Full name from SSO provider
- **`avatar_url`** (String, Nullable) - Profile picture URL
- **`hashed_password`** (String, Nullable) - Only used for email/OTP auth
- **`is_active`** (Boolean) - Account status
- **`last_login_at`** (DateTime, Nullable) - Last login timestamp
- **`provider_data`** (JSON, Nullable) - Additional provider-specific data
- **`created_at`** (DateTime) - Account creation timestamp
- **`updated_at`** (DateTime, Nullable) - Last update timestamp

### Unique Constraints

- **`(auth_provider, provider_user_id)`** - Ensures unique provider user IDs per provider
  - Note: NULL values are allowed (for email provider users)
  - Multiple users can have the same email if they use different providers

## Current Authentication Flow

### Email/OTP Authentication

1. User requests OTP: `POST /api/v1/auth/request-otp`
2. System creates user with `auth_provider=email` if doesn't exist
3. User logs in with OTP: `POST /api/v1/auth/login`
4. System updates `last_login_at` timestamp
5. Returns JWT token with email as subject

## SSO Integration Implementation

### Step 1: Add OAuth Provider Configuration

Add provider credentials to `.env`:

```env
# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback

# Microsoft OAuth
MICROSOFT_CLIENT_ID=your_microsoft_client_id
MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret
MICROSOFT_TENANT_ID=your_tenant_id
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/v1/auth/microsoft/callback

# GitHub OAuth
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
GITHUB_REDIRECT_URI=http://localhost:8000/api/v1/auth/github/callback
```

### Step 2: Install OAuth Libraries

```bash
pip install authlib google-auth microsoft-auth-library
```

### Step 3: Create SSO Routes

Create `app/api/routes/sso.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.models import User, AuthProvider
from app.core.security import create_access_token
from app.config import settings

router = APIRouter()

@router.get("/google")
async def google_login():
    """Initiate Google OAuth flow"""
    # Redirect to Google OAuth
    pass

@router.get("/google/callback")
async def google_callback(
    code: str,
    db: Session = Depends(get_db)
):
    """Handle Google OAuth callback"""
    # 1. Exchange code for tokens
    # 2. Get user info from Google
    # 3. Find or create user
    # 4. Update last_login_at
    # 5. Return JWT token
    
    # Example user creation:
    user = db.query(User).filter(
        User.provider_user_id == google_user_id,
        User.auth_provider == AuthProvider.GOOGLE
    ).first()
    
    if not user:
        user = User(
            email=google_email,
            auth_provider=AuthProvider.GOOGLE,
            provider_user_id=google_user_id,
            full_name=google_name,
            avatar_url=google_picture,
            is_active=True
        )
        db.add(user)
    else:
        # Update user info
        user.full_name = google_name
        user.avatar_url = google_picture
        user.last_login_at = datetime.utcnow()
    
    db.commit()
    
    # Create JWT token
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}
```

### Step 4: User Lookup Strategy

When implementing SSO, consider these scenarios:

1. **New SSO User**: Create new user with provider info
2. **Existing SSO User**: Update profile info, set `last_login_at`
3. **Email Conflict**: Same email from different providers
   - Option A: Create separate accounts (current design)
   - Option B: Link accounts (requires additional logic)

### Step 5: Update JWT Token

Consider including provider info in JWT:

```python
access_token = create_access_token(
    data={
        "sub": user.email,
        "provider": user.auth_provider.value,
        "user_id": user.id
    }
)
```

## Helper Functions

### Find User by Provider

```python
def find_user_by_provider(
    db: Session,
    provider: AuthProvider,
    provider_user_id: str
) -> Optional[User]:
    """Find user by provider and provider_user_id"""
    return db.query(User).filter(
        User.auth_provider == provider,
        User.provider_user_id == provider_user_id
    ).first()
```

### Find User by Email (Any Provider)

```python
def find_user_by_email(
    db: Session,
    email: str
) -> List[User]:
    """Find all users with this email (across all providers)"""
    return db.query(User).filter(User.email == email).all()
```

### Link Accounts

```python
def link_accounts(
    db: Session,
    primary_user_id: int,
    secondary_user_id: int
):
    """Link two user accounts (e.g., email + SSO)"""
    # Implementation depends on your requirements
    # Could merge accounts or create account linking table
    pass
```

## Migration

Run the migration to add SSO fields:

```bash
alembic upgrade head
```

This will:
1. Create `AuthProvider` enum type
2. Remove unique constraint on email
3. Add SSO-related columns
4. Create indexes and unique constraint on (auth_provider, provider_user_id)

## Testing SSO Integration

### Test User Creation

```python
# Create a test SSO user
user = User(
    email="test@example.com",
    auth_provider=AuthProvider.GOOGLE,
    provider_user_id="google_123456",
    full_name="Test User",
    avatar_url="https://example.com/avatar.jpg",
    is_active=True
)
db.add(user)
db.commit()
```

### Test User Lookup

```python
# Find user by provider
user = db.query(User).filter(
    User.auth_provider == AuthProvider.GOOGLE,
    User.provider_user_id == "google_123456"
).first()

# Find all users with same email
users = db.query(User).filter(User.email == "test@example.com").all()
```

## Best Practices

1. **Email Verification**: Verify email ownership for SSO providers
2. **Account Linking**: Consider allowing users to link multiple providers
3. **Profile Updates**: Update user profile on each SSO login
4. **Token Storage**: Store provider tokens securely if needed (encrypted)
5. **Error Handling**: Handle provider-specific errors gracefully
6. **Rate Limiting**: Apply rate limiting to SSO endpoints
7. **Audit Logging**: Log SSO login attempts

## Security Considerations

1. **Token Validation**: Always validate OAuth tokens with provider
2. **State Parameter**: Use state parameter to prevent CSRF attacks
3. **PKCE**: Use PKCE for mobile/public clients
4. **Token Expiration**: Handle token refresh for long-lived sessions
5. **Account Merging**: Be careful when merging accounts to avoid privilege escalation

## Future Enhancements

- [ ] Account linking UI
- [ ] Provider token refresh
- [ ] Multi-factor authentication
- [ ] Account deletion with provider verification
- [ ] Provider-specific role mapping
- [ ] SSO provider admin panel

