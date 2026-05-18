from __future__ import annotations

from fastapi import APIRouter, Query

from backend.core.config import get_settings
from backend.services.log_service import LogService


router = APIRouter(tags=["logs"])


@router.get("/api/logs")
def get_logs(lines: int = Query(default=200, ge=1, le=1000)) -> dict:
    settings = get_settings()
    service = LogService(settings.log_dir / "app.log")
    return service.tail(lines=lines)
