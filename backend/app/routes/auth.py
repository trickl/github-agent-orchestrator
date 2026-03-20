"""Authentication routes and request guards for control-plane backend."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.responses import JSONResponse

from backend.app.config import Settings
from backend.app.routes.dependencies import get_settings


router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "gao_session"
OAUTH_STATE_COOKIE_NAME = "gao_oauth_state"


def _oauth_authorization_url(settings: Settings, state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.github_oauth_client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "state": state,
            "scope": "read:user",
        }
    )
    return f"https://github.com/login/oauth/authorize?{query}"


def _github_app_install_url(settings: Settings) -> str:
    explicit = settings.github_app_install_url.strip()
    if explicit:
        logger.info("Using explicit GitHub App install URL")
        return explicit

    slug = settings.github_app_slug.strip()
    if slug:
        normalized_slug = _normalize_github_app_slug(slug)
        if normalized_slug:
            logger.info(
                "Using GitHub App slug to construct install URL (raw=%s normalized=%s)",
                slug,
                normalized_slug,
            )
            return f"https://github.com/apps/{normalized_slug}/installations/new"

    logger.warning(
        "GitHub App install URL not configured; falling back to GitHub installations settings page"
    )
    return "https://github.com/settings/installations"


def _normalize_github_app_slug(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""

    # Accept full URLs like https://github.com/apps/<slug>[/installations/new]
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        path = parsed.path
    elif value.startswith("github.com/"):
        path = "/" + value[len("github.com/") :]
    else:
        path = value

    normalized_path = path.strip().strip("/")
    if normalized_path.startswith("apps/"):
        suffix = normalized_path[len("apps/") :]
        slug = suffix.split("/", 1)[0].strip()
        return slug

    # Fallback: treat as raw slug and ignore accidental extra path segments.
    return normalized_path.split("/", 1)[0].strip()


async def _exchange_oauth_code_for_token(settings: Settings, code: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
        )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise HTTPException(status_code=502, detail="Failed to exchange OAuth code for access token")
    return token


async def _fetch_github_user(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Unexpected user payload from GitHub")
    return payload


def _allowed_users(settings: Settings) -> set[str]:
    raw = settings.auth_allowed_github_users.strip()
    if not raw:
        return set()
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _create_session_token(settings: Settings, *, login: str, user_id: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": login,
        "uid": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.auth_session_max_age_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.auth_session_secret, algorithm="HS256")


def _decode_session_token(settings: Settings, token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.auth_session_secret, algorithms=["HS256"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="Invalid session payload")
    return payload


async def require_authenticated_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if not settings.backend_require_auth:
        return {"login": "dev-local", "id": 0}

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = _decode_session_token(settings, token)
    login = payload.get("sub")
    user_id = payload.get("uid")
    if not isinstance(login, str) or not login.strip() or not isinstance(user_id, int):
        raise HTTPException(status_code=401, detail="Invalid session payload")
    return {"login": login, "id": user_id}


@router.post("/auth/github/start")
async def start_github_auth(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    if not settings.backend_require_auth:
        logger.info("Auth bypass enabled (BACKEND_REQUIRE_AUTH=false); returning frontend redirect")
        return {"authorizationUrl": settings.auth_frontend_redirect_url}

    state = secrets.token_urlsafe(24)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=state,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="none",
        max_age=600,
        path="/",
    )
    return {"authorizationUrl": _oauth_authorization_url(settings, state)}


@router.get("/auth/github-app/install-url")
async def github_app_install_url(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {"installUrl": _github_app_install_url(settings)}


@router.get("/auth/github/callback", include_in_schema=False)
async def github_auth_callback(
    request: Request,
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    if not settings.backend_require_auth:
        logger.info("Auth callback with auth disabled; redirecting to frontend")
        return RedirectResponse(url=settings.auth_frontend_redirect_url)

    state_cookie = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    if not state_cookie or state_cookie != state:
        logger.warning("OAuth state mismatch during callback")
        raise HTTPException(status_code=401, detail="OAuth state mismatch")

    access_token = await _exchange_oauth_code_for_token(settings, code)
    user = await _fetch_github_user(access_token)
    login = user.get("login")
    user_id = user.get("id")
    if not isinstance(login, str) or not isinstance(user_id, int):
        logger.warning("Failed to resolve GitHub user identity from OAuth response")
        raise HTTPException(status_code=502, detail="Failed to resolve GitHub user identity")

    allowed = _allowed_users(settings)
    if allowed and login.lower() not in allowed:
        logger.warning("Authenticated GitHub user is not allowlisted (login=%s)", login)
        raise HTTPException(status_code=403, detail=f"User '{login}' is not allowed")

    session_token = _create_session_token(settings, login=login, user_id=user_id)

    redirect = RedirectResponse(url=settings.auth_frontend_redirect_url)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="none",
        max_age=settings.auth_session_max_age_seconds,
        path="/",
    )
    redirect.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/")
    logger.info("OAuth callback successful for user %s", login)
    return redirect


@router.get("/auth/me")
async def auth_me(
    user: dict[str, Any] = Depends(require_authenticated_user),
) -> dict[str, Any]:
    return {
        "authenticated": True,
        "login": user["login"],
        "id": user["id"],
    }


@router.post("/auth/logout")
async def auth_logout(settings: Settings = Depends(get_settings)) -> JSONResponse:
    response = JSONResponse(content={"ok": True})
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/")
    return response
