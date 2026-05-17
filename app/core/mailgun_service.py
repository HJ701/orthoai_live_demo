import requests
from typing import Optional
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class MailgunEmailService:
    """Service class for sending emails via Mailgun API"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        domain: Optional[str] = None,
        from_email: Optional[str] = None
    ):
        """
        Initialize Mailgun email service.
        
        Args:
            api_key: Mailgun API key (defaults to settings.mailgun_api_key)
            domain: Mailgun domain (defaults to settings.mailgun_domain)
            from_email: Default sender email (defaults to settings.mailgun_from_email)
        """
        self.api_key = api_key or settings.mailgun_api_key
        self.domain = domain or settings.mailgun_domain
        self.from_email = from_email or settings.mailgun_from_email
        self.base_url = f"https://api.mailgun.net/v3/{self.domain}/messages"
        
        if not self.api_key:
            logger.warning("Mailgun API key not configured")
        if not self.domain:
            logger.warning("Mailgun domain not configured")
        if not self.from_email:
            logger.warning("Mailgun from_email not configured")
    
    def send_text_email(
        self,
        to: str,
        subject: str,
        text: str,
        from_email: Optional[str] = None
    ) -> bool:
        """
        Send a text email via Mailgun.
        
        Args:
            to: Recipient email address
            subject: Email subject
            text: Email body text
            from_email: Sender email (defaults to instance from_email)
        
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.api_key or not self.domain:
            logger.error("Mailgun not properly configured. Cannot send email.")
            return False
        
        sender = from_email or self.from_email
        if not sender:
            logger.error("No sender email configured. Cannot send email.")
            return False
        
        try:
            response = requests.post(
                self.base_url,
                auth=("api", self.api_key),
                data={
                    "from": sender,
                    "to": to,
                    "subject": subject,
                    "text": text
                },
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Email sent successfully to {to}")
                return True
            else:
                logger.error(
                    f"Failed to send email to {to}. "
                    f"Status: {response.status_code}, Response: {response.text}"
                )
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending email to {to}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending email to {to}: {e}")
            return False


# Global instance (initialized lazily)
_email_service = None


def get_email_service() -> MailgunEmailService:
    """Get or create Mailgun email service instance"""
    global _email_service
    
    if _email_service is None:
        _email_service = MailgunEmailService()
        logger.info("Mailgun email service initialized")
    
    return _email_service

