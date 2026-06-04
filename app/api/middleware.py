from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.core.audit import log_audit_event
from app.config import settings
from typing import Callable
import time
import logging


logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting middleware"""
    
    def __init__(self, app, calls_per_minute: int = 60):
        super().__init__(app)
        self.calls_per_minute = calls_per_minute
        self.requests = {}  # In production, use Redis
        self.redis_client = None
        if settings.rate_limit_storage.lower() == "redis":
            try:
                import redis

                self.redis_client = redis.Redis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
            except Exception as exc:
                logger.error("Redis rate limit storage could not be initialized: %s", exc)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)
        
        # Skip rate limiting for health checks and docs
        if request.url.path in ["/docs", "/redoc", "/openapi.json", "/health"]:
            return await call_next(request)
        
        # Get client identifier
        client_id = get_remote_address(request)
        current_time = time.time()

        if self.redis_client is not None:
            key = f"rate-limit:{client_id}:{int(current_time // 60)}"
            try:
                request_count = self.redis_client.incr(key)
                if request_count == 1:
                    self.redis_client.expire(key, 120)
                if request_count > self.calls_per_minute:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": f"Rate limit exceeded. Maximum {self.calls_per_minute} requests per minute.",
                            "retry_after": 60 - int(current_time % 60),
                        },
                    )
                return await call_next(request)
            except Exception as exc:
                logger.error("Redis rate limiting failed; falling back to in-memory storage: %s", exc)
        
        # Clean old entries (simple cleanup)
        if client_id in self.requests:
            self.requests[client_id] = [
                ts for ts in self.requests[client_id]
                if current_time - ts < 60
            ]
        else:
            self.requests[client_id] = []
        
        # Check rate limit
        if len(self.requests[client_id]) >= self.calls_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Maximum {self.calls_per_minute} requests per minute.",
                    "retry_after": 60 - (current_time - self.requests[client_id][0])
                }
            )
        
        # Record request
        self.requests[client_id].append(current_time)
        
        return await call_next(request)


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log audit events"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for health checks and docs
        if request.url.path in ["/docs", "/redoc", "/openapi.json", "/health"]:
            return await call_next(request)
        
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Get user ID from request state if available
        user_id = getattr(request.state, "user_id", None)
        ip_address = get_remote_address(request)
        
        # Determine action and resource type from path
        action = self._determine_action(request.method, request.url.path)
        resource_type = self._determine_resource_type(request.url.path)
        resource_id = self._extract_resource_id(request.url.path)
        
        # Log audit event in background (non-blocking)
        try:
            db = SessionLocal()
            log_audit_event(
                db=db,
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "process_time": process_time
                },
                ip_address=ip_address
            )
            db.close()
        except Exception:
            # Don't fail the request if audit logging fails
            pass
        
        return response
    
    def _determine_action(self, method: str, path: str) -> str:
        """Determine the action from method and path"""
        if "images" in path and method == "POST":
            return "upload"
        elif "inference" in path and method == "POST":
            return "run"
        elif "results" in path or "summary.pdf" in path:
            return "view" if method == "GET" else "download"
        elif "notes" in path and method == "POST":
            return "note"
        return "access"
    
    def _determine_resource_type(self, path: str) -> str:
        """Determine the resource type from path"""
        if "cases" in path:
            return "case"
        elif "images" in path:
            return "image"
        elif "inference" in path:
            return "inference"
        elif "summary.pdf" in path:
            return "pdf"
        return "unknown"
    
    def _extract_resource_id(self, path: str) -> int:
        """Extract resource ID from path"""
        parts = path.split("/")
        for i, part in enumerate(parts):
            if part in ["cases", "inference"] and i + 1 < len(parts):
                try:
                    return int(parts[i + 1])
                except ValueError:
                    pass
        return None


def setup_rate_limiting(app):
    """Setup rate limiting on the app"""
    if settings.rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            calls_per_minute=settings.rate_limit_per_minute
        )
    return app

