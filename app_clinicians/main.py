"""Compatibility entrypoint for the integrated clinician feature.

The clinician APIs now live in ``app.api.routes.clinical`` and are mounted by
``app.main`` under ``/api/v1/clinical``. Keeping this module lets older local
commands such as ``uvicorn app_clinicians.main:app`` start the unified backend
instead of the retired standalone service.
"""

from app.main import app
