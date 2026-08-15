from __future__ import annotations

import json
import logging
import os
import socket
import threading
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict

import redis

from app.config import settings


logger = logging.getLogger(__name__)

GPU_WORKER_HEARTBEAT_KEY = "orthoai:gpu-inference:ready"
_heartbeat_stop = threading.Event()
_heartbeat_thread: threading.Thread | None = None


@lru_cache(maxsize=1)
def _redis_client():
    timeout = 1.0
    return redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
    )


def publish_gpu_worker_heartbeat() -> None:
    payload = {
        "available": True,
        "build_commit": settings.build_commit,
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _redis_client().set(
        GPU_WORKER_HEARTBEAT_KEY,
        json.dumps(payload),
        ex=max(settings.gpu_worker_heartbeat_ttl_seconds, 5),
    )


def _heartbeat_loop() -> None:
    interval = max(settings.gpu_worker_heartbeat_interval_seconds, 2)
    while not _heartbeat_stop.is_set():
        try:
            publish_gpu_worker_heartbeat()
        except Exception:
            logger.exception("Unable to publish GPU worker heartbeat")
        _heartbeat_stop.wait(interval)


def start_gpu_worker_heartbeat() -> None:
    global _heartbeat_thread
    if _heartbeat_thread is not None and _heartbeat_thread.is_alive():
        return
    _heartbeat_stop.clear()
    try:
        publish_gpu_worker_heartbeat()
    except Exception:
        logger.exception("Unable to publish initial GPU worker heartbeat")
    _heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        name="orthoai-gpu-heartbeat",
        daemon=True,
    )
    _heartbeat_thread.start()


def stop_gpu_worker_heartbeat() -> None:
    _heartbeat_stop.set()


def get_gpu_worker_health() -> Dict[str, Any]:
    if (
        settings.environment.lower() != "production"
        or not settings.require_gpu_worker_heartbeat
    ):
        return {"available": True, "reason": "heartbeat_not_required"}

    try:
        raw = _redis_client().get(GPU_WORKER_HEARTBEAT_KEY)
    except Exception as exc:
        logger.error("GPU worker heartbeat check failed: %s", exc)
        return {"available": False, "reason": "heartbeat_check_unavailable"}

    if not raw:
        return {"available": False, "reason": "no_ready_gpu_worker"}

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {"available": False, "reason": "invalid_gpu_worker_heartbeat"}

    return {
        "available": bool(payload.get("available")),
        "reason": "ready" if payload.get("available") else "not_ready",
        "build_commit": payload.get("build_commit"),
        "updated_at": payload.get("updated_at"),
    }
