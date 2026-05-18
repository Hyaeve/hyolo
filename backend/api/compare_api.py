from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.core.config import get_settings
from backend.services.compare_service import CompareService
from backend.utils.file_utils import UploadLimitExceededError, is_allowed_image, save_upload_file


router = APIRouter(tags=["compare"])


@router.post("/api/compare/models")
async def compare_models(
    files: list[UploadFile] = File(...),
    model_a: str = Form(...),
    model_b: str = Form(...),
    conf: float = Form(default=0.25),
    iou: float = Form(default=0.45),
    imgsz: int = Form(default=640),
) -> dict:
    settings = get_settings()
    max_upload_bytes = max(1, settings.runtime.max_upload_size_mb) * 1024 * 1024
    if not files:
        raise HTTPException(status_code=400, detail="missing image files")
    if len(files) > settings.runtime.max_batch_files:
        raise HTTPException(status_code=400, detail=f"too many files, maximum is {settings.runtime.max_batch_files}")

    image_paths = []
    for file in files:
        if not file.filename or not is_allowed_image(file.filename):
            raise HTTPException(status_code=400, detail="only image files are allowed for model comparison")
        try:
            image_paths.append(await save_upload_file(file, settings.upload_images_dir, max_bytes=max_upload_bytes))
        except UploadLimitExceededError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc

    try:
        return await CompareService(settings).build_comparison_result(
            image_paths=image_paths,
            model_a_name=model_a,
            model_b_name=model_b,
            conf=conf,
            iou=iou,
            imgsz=imgsz,
        )
    except (RuntimeError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/compare/history")
def compare_history() -> dict:
    return CompareService(get_settings()).list_history()


@router.get("/api/compare/history/{compare_id}")
def compare_history_detail(compare_id: str) -> dict:
    try:
        return CompareService(get_settings()).get_history_detail(compare_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
