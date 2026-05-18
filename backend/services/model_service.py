from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import cv2
import torch
from ultralytics import YOLO

from backend.core.config import Settings


logger = logging.getLogger(__name__)


class ModelService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._settings: Settings | None = None
        self._model: YOLO | None = None
        self._model_path: Path | None = None
        self._device: str = "cpu"
        self._loaded: bool = False
        self._last_error: str | None = None

    def initialize(self, settings: Settings) -> None:
        with self._lock:
            self._settings = settings
            self._device = settings.model.device
            torch.set_num_threads(settings.runtime.cpu_threads)
            try:
                torch.set_num_interop_threads(max(1, settings.runtime.cpu_threads))
            except RuntimeError:
                pass
            cv2.setNumThreads(max(1, settings.runtime.cpu_threads))
        self.load_model(settings.model.path, fail_silently=True)

    def _resolve_model_path(self, model_path: str | None = None) -> Path:
        if self._settings is None:
            raise RuntimeError("settings not initialized")

        if model_path:
            requested = Path(model_path)
            if requested.is_absolute():
                resolved_path = requested.resolve()
            else:
                resolved_path = (self._settings.models_dir / requested.name).resolve()
        else:
            resolved_path = self._settings.model_path.resolve()

        models_dir = self._settings.models_dir.resolve()
        if resolved_path != models_dir and models_dir not in resolved_path.parents:
            raise RuntimeError("model path outside configured models directory is not allowed")
        return resolved_path

    def load_model(self, model_path: str | None = None, fail_silently: bool = False) -> dict[str, Any]:
        if self._settings is None:
            raise RuntimeError("settings not initialized")

        with self._lock:
            resolved_path = self._resolve_model_path(model_path)

            if not resolved_path.exists():
                self._model = None
                self._model_path = resolved_path
                self._loaded = False
                self._last_error = f"model file not found: {resolved_path}"
                logger.warning(self._last_error)
                if not fail_silently:
                    raise FileNotFoundError(self._last_error)
                return self.info()

            try:
                self._model = YOLO(str(resolved_path))
                self._model_path = resolved_path
                self._loaded = True
                self._last_error = None
                self._settings.model.path = str(resolved_path)
                logger.info("model loaded: %s", resolved_path.name)
            except Exception as exc:  # pragma: no cover - runtime dependency path
                self._model = None
                self._model_path = resolved_path
                self._loaded = False
                self._last_error = str(exc)
                logger.exception("failed to load model: %s", resolved_path)
                if not fail_silently:
                    raise RuntimeError(f"failed to load model: {exc}") from exc

            return self.info()

    def info(self) -> dict[str, Any]:
        return {
            "model_path": str(self._model_path or ""),
            "model_name": self._model_path.name if self._model_path else None,
            "device": self._device,
            "loaded": self._loaded,
            "last_error": self._last_error,
        }

    def list_models(self) -> list[dict[str, Any]]:
        if self._settings is None:
            raise RuntimeError("settings not initialized")

        current_name = self._model_path.name if self._model_path else None
        models: list[dict[str, Any]] = []
        for path in sorted(self._settings.models_dir.glob("*")):
            if not path.is_file() or path.suffix.lower() not in {".pt", ".onnx"}:
                continue
            models.append(
                {
                    "model_name": path.name,
                    "model_path": str(path),
                    "is_current": path.name == current_name,
                }
            )
        return models

    def select_model(self, model_name: str) -> dict[str, Any]:
        if self._settings is None:
            raise RuntimeError("settings not initialized")

        target_path = self._settings.models_dir / Path(model_name).name
        return self.load_model(str(target_path))

    def get_model_path_by_name(self, model_name: str) -> Path:
        if self._settings is None:
            raise RuntimeError("settings not initialized")

        target_path = self._settings.models_dir / Path(model_name).name
        if not target_path.exists():
            raise FileNotFoundError(f"model file not found: {target_path}")
        return target_path

    def build_model_instance(self, model_name_or_path: str) -> tuple[YOLO, Path]:
        resolved_path = self.get_model_path_by_name(model_name_or_path)
        try:
            return YOLO(str(resolved_path)), resolved_path
        except Exception as exc:  # pragma: no cover - runtime dependency path
            raise RuntimeError(f"failed to load model: {exc}") from exc

    def predict_image(self, image_path: Path, conf: float, iou: float, imgsz: int):
        with self._lock:
            if not self._loaded or self._model is None:
                raise RuntimeError(self._last_error or "model not loaded")
            model = self._model

        results = model.predict(
            source=str(image_path),
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            device="cpu",
            verbose=False,
        )
        return results[0]

    def predict_frame(self, frame: Any, conf: float, iou: float, imgsz: int):
        with self._lock:
            if not self._loaded or self._model is None:
                raise RuntimeError(self._last_error or "model not loaded")
            model = self._model

        results = model.predict(
            source=frame,
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            device="cpu",
            verbose=False,
        )
        return results[0]

    def predict_image_with_model(self, model: YOLO, image_path: Path, conf: float, iou: float, imgsz: int):
        results = model.predict(
            source=str(image_path),
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            device="cpu",
            verbose=False,
        )
        return results[0]


model_service = ModelService()
