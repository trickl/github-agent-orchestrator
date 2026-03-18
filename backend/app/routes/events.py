"""Observability routes for webhook event visibility."""

from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.services.event_log import get_recent_events


router = APIRouter(tags=["events"])


@router.get("/webhooks/events/recent")
async def recent_webhook_events(limit: int = Query(default=20, ge=1, le=500)) -> dict[str, object]:
    """List recent webhook events held in memory for local debugging."""
    events = get_recent_events(limit=limit)
    return {
        "count": len(events),
        "limit": limit,
        "events": events,
    }
