from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

import cv2

from backend.core.config import Settings
from backend.services.model_service import model_service
from backend.utils.draw_utils import annotate_result


class VideoDetectService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def detect(self, video_path: Path, conf: float, iou: float, imgsz: int) -> dict:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise RuntimeError(f"unable to open video: {video_path}")

        fps = capture.get(cv2.CAP_PROP_FPS)
        fps = fps if fps and fps > 0 else 25.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if width <= 0 or height <= 0:
            capture.release()
            raise RuntimeError("invalid video dimensions")

        output_name = f"result_{uuid4().hex}.mp4"
        output_path = self.settings.output_videos_dir / output_name
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )

        started = time.perf_counter()
        frame_count = 0
        class_counter: Counter[str] = Counter()

        try:
            while True:
                success, frame = capture.read()
                if not success:
                    break

                result = model_service.predict_frame(frame=frame, conf=conf, iou=iou, imgsz=imgsz)
                annotated = annotate_result(frame, result)
                writer.write(annotated)
                frame_count += 1

                if result.boxes is not None:
                    names = result.names or {}
                    for box in result.boxes:
                        class_id = int(box.cls[0].item())
                        class_counter.update([names.get(class_id, str(class_id))])
        finally:
            capture.release()
            writer.release()

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        detections = [{"class_name": key, "count": value} for key, value in class_counter.items()]

        return {
            "success": True,
            "type": "video",
            "result_url": f"/outputs/videos/{output_name}",
            "detections": detections,
            "processed_frames": frame_count,
            "cost_ms": elapsed_ms,
        }
