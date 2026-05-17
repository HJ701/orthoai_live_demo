from app.celery_app import celery_app
from app.core.email import send_otp_email


@celery_app.task(name="send_otp_email_task")
def send_otp_email_task(email: str, otp_code: str) -> bool:
    """
    Celery task to send OTP email asynchronously.
    
    Args:
        email: Recipient email address
        otp_code: The OTP code to send
    
    Returns:
        True if email was sent successfully, False otherwise
    """
    return send_otp_email(email, otp_code)

