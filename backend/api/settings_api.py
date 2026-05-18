from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.config import get_settings


router = APIRouter(tags=["settings"])


class AISettingsPayload(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    clear_api_key: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=600)


def _mask_secret(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 4:
        return "*" * len(cleaned)
    return f"{cleaned[:2]}{'*' * max(4, len(cleaned) - 4)}{cleaned[-2:]}"


@router.get("/api/settings/ai")
def get_ai_settings() -> dict:
    settings = get_settings()
    return {
        "base_url": settings.ai.base_url,
        "model": settings.ai.model,
        "api_key_masked": _mask_secret(settings.ai.api_key),
        "api_key_configured": bool(settings.ai.api_key.strip()),
        "timeout_seconds": settings.ai.timeout_seconds,
        "enabled": bool(settings.ai.api_key.strip()),
    }


@router.post("/api/settings/ai")
def save_ai_settings(payload: AISettingsPayload) -> dict:
    settings = get_settings()
    settings.ai.base_url = payload.base_url.strip()
    settings.ai.model = payload.model.strip()
    if payload.clear_api_key:
        settings.ai.api_key = ""
    elif payload.api_key.strip():
        settings.ai.api_key = payload.api_key.strip()
    settings.ai.timeout_seconds = payload.timeout_seconds
    try:
        settings.save()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"AI 配置写入失败: {exc}") from exc
    return {
        "saved": True,
        "base_url": settings.ai.base_url,
        "model": settings.ai.model,
        "api_key_masked": _mask_secret(settings.ai.api_key),
        "api_key_configured": bool(settings.ai.api_key.strip()),
        "timeout_seconds": settings.ai.timeout_seconds,
        "enabled": bool(settings.ai.api_key.strip()),
    }
