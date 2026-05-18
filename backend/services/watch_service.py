from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from backend.core.config import Settings
from backend.services.image_detect_service import ImageDetectService
from backend.services.video_detect_service import VideoDetectService
from backend.utils.file_utils import detect_media_type


logger = logging.getLogger(__name__)


@dataclass
class WatchState:
    enabled: bool = False
    processed_count: int = 0
    last_error: str | None = None


class WatchService:
    def __init__(self) -> None:
        self._settings: Settings | None = None
        self._observer: Observer | None = None
        self._state = WatchState()
        self._lock = threading.RLock()

    def initialize(self, settings: Settings) -> None:
        with self._lock:
            self._settings = settings

    def start(self, watch_dir: str | None = None) -> dict:
        if self._settings is None:
            raise RuntimeError("settings not initialized")

        with self._lock:
            if self._state.enabled:
                return self.status()

            directory = Path(watch_dir) if watch_dir else self._settings.watch_dir
            if not directory.is_absolute():
                directory = (Path.cwd() / directory).resolve()
            directory.mkdir(parents=True, exist_ok=True)

            handler = _WatchHandler(self, self._settings)
            observer = Observer()
            observer.schedule(handler, str(directory), recursive=False)
            observer.start()

            self._observer = observer
            self._settings.path.watch_dir = str(directory)
            self._state.enabled = True
            self._state.last_error = None
            logger.info("watch service started: %s", directory)
            return self.status()

    def stop(self) -> dict:
        with self._lock:
            if self._observer is not None:
                self._observer.stop()
                self._observer.join(timeout=5)
                self._observer = None
            self._state.enabled = False
            logger.info("watch service stopped")
            return self.status()

    def status(self) -> dict:
        watch_dir = ""
        if self._settings is not None:
            watch_dir = str(self._settings.watch_dir)
        return {
            "enabled": self._state.enabled,
            "watch_dir": watch_dir,
            "processed_count": self._state.processed_count,
            "last_error": self._state.last_error,
        }

    def process_file(self, path: Path) -> None:
        if self._settings is None:
            return

        media_type = detect_media_type(path.name)
        if media_type is None:
            return

        self._wait_until_ready(path)
        try:
            if media_type == "image":
                service = ImageDetectService(self._settings)
            else:
                service = VideoDetectService(self._settings)

            service.detect(
                path,
                conf=self._settings.model.conf,
                iou=self._settings.model.iou,
                imgsz=self._settings.model.imgsz,
            )
            with self._lock:
                self._state.processed_count += 1
                self._state.last_error = None
            logger.info("watch file processed: %s", path.name)
        except Exception as exc:  # pragma: no cover - depends on runtime files
            with self._lock:
                self._state.last_error = str(exc)
            logger.exception("watch file processing failed: %s", path)

    @staticmethod
    def _wait_until_ready(path: Path, retries: int = 10, delay: float = 0.5) -> None:
        last_size = -1
        for _ in range(retries):
            if not path.exists():
                time.sleep(delay)
                continue
            current_size = path.stat().st_size
            if current_size > 0 and current_size == last_size:
                return
            last_size = current_size
            time.sleep(delay)


class _WatchHandler(FileSystemEventHandler):
    def __init__(self, service: WatchService, settings: Settings) -> None:
        super().__init__()
        self.service = service
        self.settings = settings

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self.service.process_file(Path(event.src_path))


watch_service = WatchService()
