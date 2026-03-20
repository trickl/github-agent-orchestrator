"""GitHub webhook ingress routes."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from backend.app.config import Settings
from backend.app.routes.dependencies import get_settings
from backend.app.services.event_log import append_event
from backend.app.services.webhooks import handle_webhook_event


router = APIRouter(tags=["webhooks"])


def _verify_github_signature(*, body: bytes, signature_header: str, secret: str) -> bool:
    if not signature_header.startswith("sha256="):
        return False
    provided = signature_header.split("=", 1)[1].strip()
    computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, provided)


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
) -> dict[str, Any]:
    """Receive GitHub webhooks with signature verification."""
    if not settings.github_webhook_secret.strip():
        raise HTTPException(status_code=503, detail="GITHUB_WEBHOOK_SECRET is not configured")

    body = await request.body()
    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")
    if not _verify_github_signature(
        body=body,
        signature_header=x_hub_signature_256,
        secret=settings.github_webhook_secret,
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    action = payload.get("action") if isinstance(payload, dict) else None
    handled = handle_webhook_event(x_github_event, payload if isinstance(payload, dict) else {})

    append_event(
        {
            "delivery_id": x_github_delivery,
            "event": x_github_event,
            "action": action,
            "handled": handled,
        }
    )

    return {
        "accepted": True,
        "delivery_id": x_github_delivery,
        "event": x_github_event,
        "action": action,
        "handled": handled,
    }
