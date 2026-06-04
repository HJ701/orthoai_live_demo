from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import engine, Base
from app.api.routes import auth, cases, clinical, inference, results
from app.api.middleware import AuditLoggingMiddleware, setup_rate_limiting
import uvicorn

# Create database tables (in production, use Alembic migrations)
# Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Medical AI Backend",
    description="Backend API for medical AI inference",
    version="1.0.0"
)

# CORS middleware - Configure via CORS_ORIGINS in .env
# For development: CORS_ORIGINS=*
# For production: CORS_ORIGINS=http://localhost:3000,https://yourdomain.com
# Note: When using "*" for origins, credentials must be False (CORS spec limitation)
def parse_cors_origins(origins_str: str) -> list:
    """Parse CORS origins from comma-separated string"""
    if origins_str.strip() == "*":
        return ["*"]
    return [origin.strip() for origin in origins_str.split(",") if origin.strip()]

def parse_cors_methods(methods_str: str) -> list:
    """Parse CORS methods from comma-separated string"""
    if methods_str.strip() == "*":
        return ["*"]
    return [method.strip() for method in methods_str.split(",") if method.strip()]

def parse_cors_headers(headers_str: str) -> list:
    """Parse CORS headers from comma-separated string"""
    if headers_str.strip() == "*":
        return ["*"]
    return [header.strip() for header in headers_str.split(",") if header.strip()]

# Parse CORS settings
cors_origins = parse_cors_origins(settings.cors_origins)
cors_methods = parse_cors_methods(settings.cors_allow_methods)
cors_headers = parse_cors_headers(settings.cors_allow_headers)

# CORS spec: Cannot use allow_credentials=True with allow_origins=["*"]
# If origins is ["*"], disable credentials automatically
cors_credentials = settings.cors_allow_credentials
if cors_origins == ["*"]:
    cors_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_credentials,
    allow_methods=cors_methods,
    allow_headers=cors_headers,
)

# Audit logging middleware
app.add_middleware(AuditLoggingMiddleware)

# Rate limiting (added as middleware)
app = setup_rate_limiting(app)


# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "healthy"}


# Include routers
app.include_router(
    auth.router,
    prefix=f"{settings.api_v1_prefix}/auth",
    tags=["auth"]
)

app.include_router(
    cases.router,
    prefix=f"{settings.api_v1_prefix}/cases",
    tags=["cases"]
)

app.include_router(
    inference.router,
    prefix=f"{settings.api_v1_prefix}/inference",
    tags=["inference"]
)

app.include_router(
    results.router,
    prefix=f"{settings.api_v1_prefix}",
    tags=["results"]
)

app.include_router(
    clinical.router,
    prefix=f"{settings.api_v1_prefix}/clinical",
    tags=["clinical"]
)


@app.get("/clinical", include_in_schema=False)
def clinical_entry():
    return RedirectResponse(url="/clinical/")


app.mount(
    "/clinical",
    StaticFiles(
        directory=Path(__file__).resolve().parent.parent / "app_clinicians" / "static",
        html=True,
    ),
    name="clinical",
)


# Store user_id in request state for audit logging
@app.middleware("http")
async def add_user_to_request(request: Request, call_next):
    # Extract user from token if available
    from app.core.security import get_current_user
    from app.database import SessionLocal
    
    try:
        # Try to get user from token
        authorization = request.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]
            db = SessionLocal()
            try:
                from jose import jwt
                payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
                email = payload.get("sub")  # Now using email as subject
                if email:
                    from app.models import User
                    user = db.query(User).filter(User.email == email).first()
                    if user:
                        request.state.user_id = user.id
            except Exception:
                pass
            finally:
                db.close()
    except Exception:
        pass
    
    response = await call_next(request)
    return response


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
