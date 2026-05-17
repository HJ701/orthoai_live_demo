from sqlalchemy.orm import Session
from app.models import AuditLog
from datetime import datetime
from typing import Optional, Dict, Any
import json


def log_audit_event(
    db: Session,
    user_id: Optional[int],
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None
):
    """Log an audit event"""
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=json.dumps(details) if details else None,
        ip_address=ip_address
    )
    db.add(audit_log)
    db.commit()

