from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.services.camera_service import camera_service
from backend.services.onvif_service import onvif_service


router = APIRouter(tags=["camera"])


class CameraCreateRequest(BaseModel):
    camera_id: str
    name: str
    type: str = "rtsp"
    url: str | None = None
    host: str | None = None
    port: int = 80
    username: str | None = None
    password: str | None = None
    profile_token: str | None = None
    enabled: bool = False


class OnvifResolveRequest(BaseModel):
    host: str
    port: int = 80
    username: str = ""
    password: str = ""
    profile_token: str | None = None


@router.get("/api/cameras")
def list_cameras() -> dict:
    return camera_service.list_cameras()


@router.post("/api/cameras")
def create_camera(payload: CameraCreateRequest) -> dict:
    try:
        return camera_service.add_camera(payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/cameras/{camera_id}/start")
def start_camera(camera_id: str) -> dict:
    try:
        return camera_service.start(camera_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/cameras/{camera_id}/stop")
def stop_camera(camera_id: str) -> dict:
    try:
        return camera_service.stop(camera_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/cameras/{camera_id}/status")
def camera_status(camera_id: str) -> dict:
    try:
        return camera_service.status(camera_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/stream/{camera_id}")
def stream_camera(camera_id: str) -> StreamingResponse:
    try:
        generator = camera_service.stream_generator(camera_id)
        return StreamingResponse(generator, media_type="multipart/x-mixed-replace; boundary=frame")
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/onvif/resolve")
def resolve_onvif(payload: OnvifResolveRequest) -> dict:
    try:
        return onvif_service.resolve_stream_uri(**payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
