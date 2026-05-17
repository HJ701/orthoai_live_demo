# OTP Authentication Implementation

## Overview

The authentication system has been updated to use **Email + OTP (One-Time Password)** instead of username/password authentication.

## Changes Made

### 1. Database Models

- **User Model**: 
  - `username` is now optional (nullable)
  - `hashed_password` is now optional (nullable)
  - Added relationship to `OTP` model

- **New OTP Model**:
  - Stores 6-digit OTP codes
  - Links to user by email and optional user_id
  - Tracks expiration (10 minutes)
  - Marks OTPs as used after verification

### 2. Authentication Flow

#### Step 1: Request OTP
```
POST /api/v1/auth/request-otp
Body: { "email": "user@example.com" }
Response: { "message": "OTP sent to user@example.com. For development, check server logs." }
```

- Generates a 6-digit OTP code (0-9)
- Stores OTP in database with 10-minute expiration
- Auto-creates user if email doesn't exist
- **Development**: OTP is logged to console
- **Production**: Should send OTP via email/SMS service

#### Step 2: Login with OTP
```
POST /api/v1/auth/login
Body: { "email": "user@example.com", "otp": "123456" }
Response: { "access_token": "eyJ...", "token_type": "bearer" }
```

- Verifies OTP code matches and hasn't expired
- Marks OTP as used (one-time use)
- Returns JWT token with email as subject

### 3. Security Features

- **OTP Expiration**: 10 minutes
- **One-Time Use**: OTPs are marked as used after verification
- **Auto-Invalidation**: New OTP request invalidates previous unused OTPs
- **Email Normalization**: Emails are lowercased and trimmed

### 4. API Endpoints

#### `POST /api/v1/auth/request-otp`
Request OTP code for an email address.

**Request:**
```json
{
  "email": "user@example.com"
}
```

**Response:**
```json
{
  "message": "OTP sent to user@example.com. For development, check server logs."
}
```

**Notes:**
- Auto-creates user if email doesn't exist
- In development, OTP is printed to server logs
- In production, implement email/SMS sending

#### `POST /api/v1/auth/login`
Login with email and OTP code.

**Request:**
```json
{
  "email": "user@example.com",
  "otp": "123456"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Responses:**
- `401`: Invalid or expired OTP
- `403`: Inactive user
- `404`: User not found

#### `POST /api/v1/auth/register` (Optional)
Manually register a user (users are auto-created on OTP request).

**Request:**
```json
{
  "email": "user@example.com",
  "username": "optional_username"
}
```

## Migration

Run the migration to add OTP table and update User model:

```bash
alembic upgrade head
```

This will:
1. Make `username` nullable in `users` table
2. Make `hashed_password` nullable in `users` table
3. Create `otps` table

## Usage Example

### Using curl:

```bash
# 1. Request OTP
curl -X POST "http://localhost:8000/api/v1/auth/request-otp" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'

# Check server logs for OTP code (e.g., "OTP for user@example.com: 123456")

# 2. Login with OTP
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "otp": "123456"}'

# Response contains access_token
```

### Using Python:

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

# Request OTP
response = requests.post(
    f"{BASE_URL}/auth/request-otp",
    json={"email": "user@example.com"}
)
print(response.json())

# Login with OTP (get code from server logs or email)
response = requests.post(
    f"{BASE_URL}/auth/login",
    json={"email": "user@example.com", "otp": "123456"}
)
token_data = response.json()
access_token = token_data["access_token"]

# Use token for authenticated requests
headers = {"Authorization": f"Bearer {access_token}"}
response = requests.get(f"{BASE_URL}/cases", headers=headers)
```

## Production Considerations

### Email/SMS Integration

For production, implement OTP delivery:

1. **Email Service** (e.g., SendGrid, AWS SES):
```python
# In app/core/security.py or app/core/email.py
def send_otp_email(email: str, otp_code: str):
    # Send email with OTP code
    pass
```

2. **SMS Service** (e.g., Twilio, AWS SNS):
```python
def send_otp_sms(phone: str, otp_code: str):
    # Send SMS with OTP code
    pass
```

3. **Update request_otp endpoint**:
```python
# After creating OTP record
send_otp_email(email, otp_code)  # or send_otp_sms(phone, otp_code)
# Remove print statement and don't return OTP in response
```

### Security Best Practices

1. **Rate Limiting**: Implement rate limiting on OTP requests (already in place)
2. **OTP Expiration**: Currently 10 minutes (configurable)
3. **OTP Length**: Currently 6 digits (configurable in `generate_otp()`)
4. **Cleanup**: Add scheduled job to delete expired OTPs
5. **Logging**: Log OTP requests for security auditing
6. **IP Tracking**: Track IP addresses for OTP requests to detect abuse

### Cleanup Expired OTPs

Add a scheduled task to clean up expired OTPs:

```python
# In app/tasks/cleanup.py or similar
@celery_app.task
def cleanup_expired_otps():
    from app.database import SessionLocal
    from app.models import OTP
    from datetime import datetime
    
    db = SessionLocal()
    try:
        deleted = db.query(OTP).filter(
            OTP.expires_at < datetime.utcnow()
        ).delete()
        db.commit()
        return f"Deleted {deleted} expired OTPs"
    finally:
        db.close()
```

## Testing

### Test OTP Flow:

1. Request OTP for an email
2. Check server logs for OTP code
3. Login with the OTP code
4. Verify JWT token is returned
5. Try using expired OTP (should fail)
6. Try using already-used OTP (should fail)
7. Try using wrong OTP (should fail)

## Backward Compatibility

- Existing users with passwords can still exist in the database
- Password fields are optional, so old users won't break
- JWT tokens now use email as subject instead of username
- All existing endpoints continue to work with new authentication

