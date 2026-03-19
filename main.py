"""Render entrypoint.

Render is configured to import ``main:app``. Keep this file as a thin shim that
exports the control-plane backend app defined under ``backend/app``.
"""

from backend.app.main import app
