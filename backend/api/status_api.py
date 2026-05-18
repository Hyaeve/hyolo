from __future__ import annotations

import time

from fastapi import APIRouter

from backend.services.model_service import model_service


router = APIRouter(tags=["status"])
START_TIME = time.time()


@router.get("/api/status")
def get_status() -> dict:
    uptime = int(time.time() - START_TIME)
    model_info = model_service.info()
    return {
        "status": "running",
        "model": model_info.get("model_name"),
        "device": model_info.get("device", "cpu"),
        "version": "1.0.0",
        "uptime": uptime,
        "loaded": model_info.get("loaded", False),
    }
