from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.watch_service import watch_service


router = APIRouter(tags=["watch"])


class StartWatchRequest(BaseModel):
    watch_dir: str | None = None


@router.post("/api/watch/start")
def start_watch(payload: StartWatchRequest) -> dict:
    try:
        return watch_service.start(payload.watch_dir)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/watch/stop")
def stop_watch() -> dict:
    return watch_service.stop()


@router.get("/api/watch/status")
def watch_status() -> dict:
    return watch_service.status()
