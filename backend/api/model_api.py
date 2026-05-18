from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.services.model_service import model_service
from backend.utils.file_utils import UploadLimitExceededError, get_extension, is_allowed_model, save_named_upload_file


router = APIRouter(tags=["model"])


class ReloadModelRequest(BaseModel):
    model_path: str | None = None


class SelectModelRequest(BaseModel):
    model_name: str


@router.get("/api/model")
def get_model_info() -> dict:
    return model_service.info()


@router.get("/api/models")
def list_models() -> dict:
    return {"models": model_service.list_models(), "current": model_service.info()}


@router.post("/api/models/upload")
async def upload_model(
    file: UploadFile = File(...),
    activate: bool = Form(default=True),
) -> dict:
    settings = get_settings()
    max_upload_bytes = max(1, settings.runtime.max_upload_size_mb) * 1024 * 1024

    if not settings.model.allow_upload:
        raise HTTPException(status_code=403, detail="model upload is disabled by security policy")

    if not file.filename:
        raise HTTPException(status_code=400, detail="missing model filename")
    if not is_allowed_model(file.filename):
        raise HTTPException(status_code=400, detail="unsupported model type, expected .pt or .onnx")
    if get_extension(file.filename) == ".pt" and not settings.model.allow_unsafe_serialized_uploads:
        raise HTTPException(status_code=403, detail="uploading serialized .pt models is disabled by security policy")

    try:
        saved_path = await save_named_upload_file(file, settings.models_dir, file.filename, max_bytes=max_upload_bytes)
    except UploadLimitExceededError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    response: dict = {
        "uploaded": True,
        "model_name": saved_path.name,
        "model_path": str(saved_path),
    }

    if activate:
        try:
            response["current"] = model_service.load_model(str(saved_path))
        except (FileNotFoundError, RuntimeError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    else:
        response["current"] = model_service.info()

    response["models"] = model_service.list_models()
    return response


@router.post("/api/models/select")
def select_model(payload: SelectModelRequest) -> dict:
    try:
        current = model_service.select_model(payload.model_name)
        return {"selected": payload.model_name, "current": current, "models": model_service.list_models()}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/model/reload")
def reload_model(payload: ReloadModelRequest) -> dict:
    try:
        return model_service.load_model(payload.model_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
