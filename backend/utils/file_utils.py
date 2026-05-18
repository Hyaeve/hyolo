from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".flv"}
ALLOWED_MODEL_EXTENSIONS = {".pt", ".onnx"}


class UploadLimitExceededError(ValueError):
    pass


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_allowed_image(filename: str) -> bool:
    return get_extension(filename) in ALLOWED_IMAGE_EXTENSIONS


def is_allowed_video(filename: str) -> bool:
    return get_extension(filename) in ALLOWED_VIDEO_EXTENSIONS


def is_allowed_model(filename: str) -> bool:
    return get_extension(filename) in ALLOWED_MODEL_EXTENSIONS


def sanitize_filename(filename: str) -> str:
    return Path(filename).name.replace("..", "_")


def detect_media_type(filename: str) -> str | None:
    extension = get_extension(filename)
    if extension in ALLOWED_IMAGE_EXTENSIONS:
        return "image"
    if extension in ALLOWED_VIDEO_EXTENSIONS:
        return "video"
    return None


async def save_upload_file(upload_file: UploadFile, destination_dir: Path, max_bytes: int | None = None) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    extension = get_extension(upload_file.filename or "upload.jpg")
    file_path = destination_dir / f"{uuid4().hex}{extension}"
    written = 0

    try:
        with file_path.open("wb") as output:
            while True:
                chunk = await upload_file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if max_bytes is not None and written > max_bytes:
                    raise UploadLimitExceededError(f"upload exceeds limit of {max_bytes} bytes")
                output.write(chunk)
    except Exception:
        await upload_file.close()
        file_path.unlink(missing_ok=True)
        raise

    await upload_file.close()
    return file_path


async def save_named_upload_file(
    upload_file: UploadFile,
    destination_dir: Path,
    filename: str | None = None,
    max_bytes: int | None = None,
) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    final_name = sanitize_filename(filename or upload_file.filename or f"upload{get_extension(upload_file.filename or 'upload.bin')}")
    file_path = destination_dir / final_name
    written = 0

    try:
        with file_path.open("wb") as output:
            while True:
                chunk = await upload_file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if max_bytes is not None and written > max_bytes:
                    raise UploadLimitExceededError(f"upload exceeds limit of {max_bytes} bytes")
                output.write(chunk)
    except Exception:
        await upload_file.close()
        file_path.unlink(missing_ok=True)
        raise

    await upload_file.close()
    return file_path
