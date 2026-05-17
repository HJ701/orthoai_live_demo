import logging
from app.config import settings
from app.core.mailgun_service import get_email_service

logger = logging.getLogger(__name__)

# Lazy import of celery_app to avoid circular dependencies
_celery_app = None


def _get_celery_app():
    """Get Celery app instance (lazy import to avoid circular dependencies)"""
    global _celery_app
    if _celery_app is None:
        try:
            from app.celery_app import celery_app
            _celery_app = celery_app
        except ImportError:
            logger.warning("Celery app not available")
            return None
    return _celery_app


def send_otp_email(email: str, otp_code: str) -> bool:
    """
    Send OTP code via email.
    
    Args:
        email: Recipient email address
        otp_code: The OTP code to send
    
    Returns:
        True if email was sent successfully, False otherwise
    """
    email_service = get_email_service()
    email_sent = email_service.send_text_email(
        to=email,
        subject="Your OTP Code",
        text=f"Your OTP code is: {otp_code}"
    )
    
    if not email_sent:
        # In development, log OTP if email fails
        if settings.environment.lower() == "development":
            logger.warning(f"Failed to send email. OTP for {email}: {otp_code}")
        else:
            logger.error(f"Failed to send OTP email to {email}")
    
    return email_sent


def send_otp_email_async(email: str, otp_code: str):
    """
    Send OTP code via email asynchronously using Celery.
    
    Args:
        email: Recipient email address
        otp_code: The OTP code to send
    
    Returns:
        Celery AsyncResult object or result of synchronous send if Celery unavailable
    """
    celery_app = _get_celery_app()
    if celery_app is None:
        # Fallback to synchronous sending if Celery is not available
        logger.warning("Celery app not available, falling back to synchronous email sending")
        return send_otp_email(email, otp_code)
    
    # Use send_task with task name to avoid circular import
    return celery_app.send_task("send_otp_email_task", args=[email, otp_code])

