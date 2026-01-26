"""LLM client helpers for gap analysis and capability updates."""

from __future__ import annotations

from typing import Any

import requests
from fastapi import HTTPException

from github_agent_orchestrator.server.config import ServerSettings


def _require_openai_key(settings: ServerSettings) -> None:
    if not settings.openai_api_key.strip():
        raise HTTPException(
            status_code=409,
            detail="OPENAI_API_KEY is required when ORCHESTRATOR_*_MODE=openai",
        )


def _require_ollama_base_url(settings: ServerSettings) -> None:
    if not settings.ollama_base_url.strip():
        raise HTTPException(
            status_code=409,
            detail="OLLAMA_BASE_URL is required when ORCHESTRATOR_*_MODE=ollama",
        )


def _normalize_model_mode(mode: str) -> str:
    return (mode or "").strip().lower()


def generate_chat_completion(
    *,
    settings: ServerSettings,
    mode: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> str:
    """Generate a chat completion using OpenAI or Ollama."""

    normalized = _normalize_model_mode(mode)
    if normalized == "openai":
        _require_openai_key(settings)
        url = f"{settings.openai_base_url.rstrip('/')}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": settings.openai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"OpenAI request failed (HTTP {resp.status_code}): {resp.text}",
            )
        data = resp.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=502, detail="OpenAI response missing choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=502, detail="OpenAI response missing content")
        return content

    if normalized == "ollama":
        _require_ollama_base_url(settings)
        url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
        payload = {
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        resp = requests.post(url, json=payload, timeout=120)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Ollama request failed (HTTP {resp.status_code}): {resp.text}",
            )
        data = resp.json()
        if isinstance(data, dict):
            if isinstance(data.get("message"), dict):
                content = data["message"].get("content")
            else:
                content = data.get("response")
        else:
            content = None
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=502, detail="Ollama response missing content")
        return content

    raise HTTPException(
        status_code=409,
        detail="Unsupported model mode; expected 'openai' or 'ollama'",
    )
