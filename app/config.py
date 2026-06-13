from pydantic_settings import BaseSettings
from typing import Optional
import logging
import os

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Environment
    environment: str = "development"  # "development" or "production"
    
    # Database - Read from .env file
    database_url: str = "postgresql://user:password@localhost:5432/medical_ai_db"
    
    # JWT - Read from .env file
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # Redis/Celery - Read from .env file
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    
    # Application
    api_v1_prefix: str = "/api/v1"
    model_version: str = "v1.0.0"
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50
    preload_model_runtime: bool = True
    model_max_download_workers: int = 4
    
    # PDF Signing
    pdf_signing_key_path: Optional[str] = None
    pdf_signing_cert_path: Optional[str] = None
    
    # AWS S3 - Read from .env file
    aws_s3_bucket_name: str = ""
    aws_s3_region: str = "eu-north-1"
    aws_access_key_id: Optional[str] = None  # Optional - can use IAM role in ECS
    aws_secret_access_key: Optional[str] = None  # Optional - can use IAM role in ECS
    
    # Mailgun - Read from .env file
    mailgun_api_key: str = ""
    mailgun_domain: str = ""
    mailgun_from_email: str = ""

    # SSO/OAuth provider client IDs. Callback/client-secret handling is not
    # enabled until the OAuth code flow is implemented end to end.
    google_oauth_client_id: str = ""
    microsoft_oauth_client_id: str = ""
    github_oauth_client_id: str = ""
    apple_oauth_client_id: str = ""
    
    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    rate_limit_storage: str = "memory"  # "memory" or "redis"
    
    # CORS
    cors_origins: str = "*"  # Comma-separated list of origins, or "*" for all
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"  # Comma-separated list or "*" for all
    cors_allow_headers: str = "*"  # Comma-separated list or "*" for all
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Ensure .env file is loaded (pydantic-settings loads it automatically, but verify)
        env_file_path = ".env"
        if os.path.exists(env_file_path):
            logger.debug(f"Loading configuration from {env_file_path}")
        
        # Log environment mode on initialization
        if self.environment.lower() == "production":
            logger.info("Running in PRODUCTION mode")
            # Validate critical production settings
            errors = []
            if not self.secret_key or self.secret_key == "dev-secret-key-change-in-production":
                errors.append("SECRET_KEY must be set to a strong non-default value")
            if (
                not self.database_url
                or "localhost" in self.database_url
                or self.database_url == "postgresql://user:password@localhost:5432/medical_ai_db"
            ):
                errors.append("DATABASE_URL must point to the production database")
            if self.cors_origins.strip() == "*":
                errors.append("CORS_ORIGINS must list explicit production origins")
            if not self.aws_s3_bucket_name:
                errors.append("AWS_S3_BUCKET_NAME must be configured")
            if self.rate_limit_enabled and self.rate_limit_storage.lower() != "redis":
                errors.append("RATE_LIMIT_STORAGE=redis is required in production")
            if errors:
                raise ValueError("Invalid production configuration: " + "; ".join(errors))
            
            # Log which values are being used (without exposing secrets)
            logger.info("Configuration loaded from environment variables/.env file")
            logger.debug(f"Database URL: {self.database_url.split('@')[1] if '@' in self.database_url else 'configured'}")
            logger.debug(f"Redis URL: {self.redis_url.split('@')[1] if '@' in self.redis_url else 'configured'}")
        else:
            logger.info(f"Running in {self.environment.upper()} mode")


settings = Settings()
