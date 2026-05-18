from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.core.config import get_settings
from backend.services.herb_knowledge_service import HerbKnowledgeService
from backend.services.image_detect_service import ImageDetectService
from backend.services.video_detect_service import VideoDetectService
from backend.utils.file_utils import UploadLimitExceededError, detect_media_type, save_upload_file


logger = logging.getLogger(__name__)
router = APIRouter(tags=["detect"])


@router.post("/api/detect/upload")
async def detect_upload(
    file: UploadFile = File(...),
    conf: float = Form(default=0.25),
    iou: float = Form(default=0.45),
    imgsz: int = Form(default=640),
    device: str = Form(default="cpu"),
) -> dict:
    settings = get_settings()
    max_upload_bytes = max(1, settings.runtime.max_upload_size_mb) * 1024 * 1024

    if device.lower() != "cpu":
        raise HTTPException(status_code=400, detail="only cpu device is supported in phase 2")

    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")

    media_type = detect_media_type(file.filename)
    if media_type is None:
        raise HTTPException(status_code=400, detail="unsupported file type, expected image or video file")

    try:
        if media_type == "image":
            saved_path = await save_upload_file(file, settings.upload_images_dir, max_bytes=max_upload_bytes)
            service = ImageDetectService(settings)
        else:
            saved_path = await save_upload_file(file, settings.upload_videos_dir, max_bytes=max_upload_bytes)
            service = VideoDetectService(settings)

        result = service.detect(saved_path, conf=conf, iou=iou, imgsz=imgsz)
        if media_type == "image":
            herb_service = HerbKnowledgeService(settings)
            result["herb_info"] = await herb_service.generate_for_candidates(result.get("herb_candidates"))
        logger.info("%s detected: %s", media_type, saved_path.name)
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UploadLimitExceededError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("failed to detect %s: %s", media_type, saved_path)
        raise HTTPException(status_code=500, detail=f"failed to detect {media_type}: {exc}") from exc


@router.post("/api/detect/upload-batch")
async def detect_upload_batch(
    files: list[UploadFile] = File(...),
    conf: float = Form(default=0.25),
    iou: float = Form(default=0.45),
    imgsz: int = Form(default=640),
    device: str = Form(default="cpu"),
) -> dict:
    settings = get_settings()
    max_upload_bytes = max(1, settings.runtime.max_upload_size_mb) * 1024 * 1024

    if device.lower() != "cpu":
        raise HTTPException(status_code=400, detail="only cpu device is supported in phase 2")
    if not files:
        raise HTTPException(status_code=400, detail="missing files")
    if len(files) > settings.runtime.max_batch_files:
        raise HTTPException(status_code=400, detail=f"too many files, maximum is {settings.runtime.max_batch_files}")

    image_service = ImageDetectService(settings)
    herb_service = HerbKnowledgeService(settings)
    items = []

    for file in files:
        if not file.filename or detect_media_type(file.filename) != "image":
            raise HTTPException(status_code=400, detail="batch upload only supports image files")

        try:
            saved_path = await save_upload_file(file, settings.upload_images_dir, max_bytes=max_upload_bytes)
            result = image_service.detect(saved_path, conf=conf, iou=iou, imgsz=imgsz)
            result["herb_info"] = await herb_service.generate_for_candidates(result.get("herb_candidates"))
            result["source_name"] = file.filename
            items.append(result)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except UploadLimitExceededError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("failed to detect image batch item: %s", saved_path)
            raise HTTPException(status_code=500, detail=f"failed to detect image: {exc}") from exc

    logger.info("image batch detected: %s items", len(items))

    return {
        "success": True,
        "type": "image_batch",
        "count": len(items),
        "items": items,
    }
