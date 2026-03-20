"""Shared route dependencies."""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.config import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Resolve validated settings once, with API-safe error translation."""
    try:
        return Settings()
    except ValidationError as exc:
        errors = exc.errors()
        field_names: list[str] = []
        for err in errors:
            loc = err.get("loc")
            if isinstance(loc, (list, tuple)) and loc:
                field_names.append(str(loc[-1]))

        joined = ", ".join(sorted(set(field_names))) if field_names else "unknown"
        raise HTTPException(
            status_code=503,
            detail=f"Backend configuration is invalid. Check environment variables: {joined}",
        ) from exc
