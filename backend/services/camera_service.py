from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import cv2

from backend.core.config import Settings
from backend.services.model_service import model_service
from backend.services.onvif_service import onvif_service
from backend.utils.draw_utils import annotate_result


logger = logging.getLogger(__name__)


@dataclass
class CameraTask:
    camera_id: str
    name: str
    type: str
    url: str | None = None
    host: str | None = None
    port: int = 80
    username: str | None = None
    password: str | None = None
    profile_token: str | None = None
    enabled: bool = False
    status: str = "idle"
    fps: float = 0.0
    last_error: str | None = None
    latest_frame: bytes | None = None
    last_detections: list[dict[str, Any]] = field(default_factory=list)
    resolved_url: str | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class CameraService:
    def __init__(self) -> None:
        self._settings: Settings | None = None
        self._tasks: dict[str, CameraTask] = {}
        self._lock = threading.RLock()

    def initialize(self, settings: Settings) -> None:
        with self._lock:
            self._settings = settings

    def add_camera(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = CameraTask(
            camera_id=payload["camera_id"],
            name=payload.get("name") or payload["camera_id"],
            type=payload.get("type", "rtsp"),
            url=payload.get("url"),
            host=payload.get("host"),
            port=payload.get("port", 80),
            username=payload.get("username"),
            password=payload.get("password"),
            profile_token=payload.get("profile_token"),
            enabled=payload.get("enabled", False),
        )

        with self._lock:
            self._tasks[task.camera_id] = task

        if task.enabled:
            self.start(task.camera_id)
        return self.status(task.camera_id)

    def list_cameras(self) -> dict[str, Any]:
        with self._lock:
            return {"cameras": [self._serialize(task) for task in self._tasks.values()]}

    def start(self, camera_id: str) -> dict[str, Any]:
        task = self._get_task(camera_id)
        with self._lock:
            if task.thread and task.thread.is_alive():
                return self._serialize(task)
            task.stop_event = threading.Event()
            task.status = "starting"
            task.enabled = True
            task.thread = threading.Thread(target=self._camera_loop, args=(task,), daemon=True)
            task.thread.start()
        return self._serialize(task)

    def stop(self, camera_id: str) -> dict[str, Any]:
        task = self._get_task(camera_id)
        task.stop_event.set()
        if task.thread and task.thread.is_alive():
            task.thread.join(timeout=2)
        task.status = "stopped"
        task.enabled = False
        return self._serialize(task)

    def stop_all(self) -> None:
        with self._lock:
            camera_ids = list(self._tasks.keys())
        for camera_id in camera_ids:
            self.stop(camera_id)

    def status(self, camera_id: str) -> dict[str, Any]:
        task = self._get_task(camera_id)
        return self._serialize(task)

    def stream_generator(self, camera_id: str):
        task = self._get_task(camera_id)
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        while not task.stop_event.is_set() or task.latest_frame is not None:
            if task.latest_frame:
                yield boundary + task.latest_frame + b"\r\n"
            time.sleep(0.08)

    def _camera_loop(self, task: CameraTask) -> None:
        settings = self._require_settings()
        fps_limit = max(settings.camera.default_fps_limit, 1)
        frame_interval = 1.0 / fps_limit

        source = self._resolve_source(task)
        task.resolved_url = source
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            task.status = "error"
            task.last_error = f"unable to open camera source: {source}"
            logger.error(task.last_error)
            return

        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        task.status = "running"
        task.last_error = None
        processed_frames = 0
        started = time.perf_counter()
        last_infer_time = 0.0

        try:
            while not task.stop_event.is_set():
                success, frame = capture.read()
                if not success:
                    task.status = "reconnecting"
                    task.last_error = "camera stream interrupted"
                    time.sleep(settings.camera.reconnect_interval)
                    capture.release()
                    capture = cv2.VideoCapture(source)
                    if capture.isOpened():
                        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        task.status = "running"
                        task.last_error = None
                    continue

                now = time.perf_counter()
                if now - last_infer_time < frame_interval:
                    continue
                last_infer_time = now

                result = model_service.predict_frame(
                    frame=frame,
                    conf=settings.model.conf,
                    iou=settings.model.iou,
                    imgsz=settings.model.imgsz,
                )
                annotated = annotate_result(frame, result)
                success_jpeg, jpeg = cv2.imencode('.jpg', annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                if success_jpeg:
                    task.latest_frame = jpeg.tobytes()

                names = result.names or {}
                detections: list[dict[str, Any]] = []
                if result.boxes is not None:
                    for box in result.boxes:
                        cls_id = int(box.cls[0].item())
                        detections.append(
                            {
                                "class_id": cls_id,
                                "class_name": names.get(cls_id, str(cls_id)),
                                "confidence": round(float(box.conf[0].item()), 4),
                            }
                        )
                task.last_detections = detections
                processed_frames += 1
                elapsed = max(time.perf_counter() - started, 0.001)
                task.fps = round(processed_frames / elapsed, 2)
        except Exception as exc:  # pragma: no cover - runtime camera dependent
            task.status = "error"
            task.last_error = str(exc)
            logger.exception("camera task failed: %s", task.camera_id)
        finally:
            capture.release()
            if task.status != "error":
                task.status = "stopped" if task.stop_event.is_set() else task.status

    def _resolve_source(self, task: CameraTask) -> str:
        if task.type == "onvif":
            if not task.host:
                raise RuntimeError("onvif camera host is required")
            resolved = onvif_service.resolve_stream_uri(
                host=task.host,
                port=task.port,
                username=task.username or "",
                password=task.password or "",
                profile_token=task.profile_token,
            )
            return onvif_service.build_authenticated_rtsp_url(
                resolved["rtsp_url"],
                task.username or "",
                task.password or "",
            )
        if not task.url:
            raise RuntimeError("camera url is required")
        return task.url

    def _mask_source(self, source: str | None) -> str | None:
        if not source:
            return source
        return onvif_service.mask_rtsp_url(source)

    def _serialize(self, task: CameraTask) -> dict[str, Any]:
        return {
            "camera_id": task.camera_id,
            "name": task.name,
            "type": task.type,
            "status": task.status,
            "fps": task.fps,
            "last_error": task.last_error,
            "detections": task.last_detections,
            "resolved_url": self._mask_source(task.resolved_url),
            "source": self._mask_source(task.url) if task.url else task.host,
        }

    def _get_task(self, camera_id: str) -> CameraTask:
        with self._lock:
            if camera_id not in self._tasks:
                raise RuntimeError(f"camera not found: {camera_id}")
            return self._tasks[camera_id]

    def _require_settings(self) -> Settings:
        if self._settings is None:
            raise RuntimeError("settings not initialized")
        return self._settings


camera_service = CameraService()
