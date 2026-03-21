"""GitHub webhook ingress routes."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from backend.app.config import Settings
from backend.app.github.auth import create_github_client
from backend.app.routes.dependencies import get_settings
from backend.app.services.event_log import append_event
from backend.app.services.install import ensure_orchestrator_workflow
from backend.app.services.webhooks import handle_webhook_event
from backend.app.services.workflows import dispatch_workflow


router = APIRouter(tags=["webhooks"])


def _split_repo_full_name(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or "/" not in value:
        return None
    owner, repo = value.split("/", 1)
    owner = owner.strip()
    repo = repo.strip()
    if not owner or not repo:
        return None
    return owner, repo


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

    auto_dispatched_run: dict[str, Any] | None = None
    if settings.webhook_auto_run_on_pr_merge:
        kind = handled.get("kind") if isinstance(handled, dict) else None
        should_trigger_run = bool(handled.get("should_trigger_run")) if isinstance(handled, dict) else False
        repository_full_name = handled.get("repository") if isinstance(handled, dict) else None
        pull_request_data = handled.get("pull_request") if isinstance(handled, dict) else None

        if kind == "pull_request" and should_trigger_run:
            split_repo = _split_repo_full_name(repository_full_name)
            if split_repo is not None:
                owner, repo = split_repo
                base_ref = None
                if isinstance(pull_request_data, dict):
                    raw_base_ref = pull_request_data.get("base_ref")
                    if isinstance(raw_base_ref, str) and raw_base_ref.strip():
                        base_ref = raw_base_ref.strip()

                try:
                    client = await create_github_client(settings, owner=owner, repo=repo)
                    effective_ref = base_ref
                    if not effective_ref:
                        repo_data = await client.request("GET", f"/repos/{owner}/{repo}")
                        default_branch = repo_data.get("default_branch") if isinstance(repo_data, dict) else None
                        if isinstance(default_branch, str) and default_branch.strip():
                            effective_ref = default_branch.strip()
                        else:
                            raise RuntimeError(
                                f"Repository '{owner}/{repo}' did not include a valid default_branch"
                            )

                    await ensure_orchestrator_workflow(client, owner, repo)
                    dispatch_result = await dispatch_workflow(
                        client,
                        owner,
                        repo,
                        workflow_file=settings.default_workflow_file,
                        ref=effective_ref,
                    )
                    auto_dispatched_run = {
                        "attempted": True,
                        "dispatched": bool(dispatch_result.get("dispatched", False)),
                        "workflow": dispatch_result.get("workflow"),
                        "ref": dispatch_result.get("ref"),
                    }
                except Exception as exc:  # noqa: BLE001
                    auto_dispatched_run = {
                        "attempted": True,
                        "dispatched": False,
                        "error": str(exc),
                    }

    append_event(
        {
            "delivery_id": x_github_delivery,
            "event": x_github_event,
            "action": action,
            "handled": handled,
            "auto_dispatched_run": auto_dispatched_run,
        }
    )

    return {
        "accepted": True,
        "delivery_id": x_github_delivery,
        "event": x_github_event,
        "action": action,
        "handled": handled,
        "auto_dispatched_run": auto_dispatched_run,
    }
