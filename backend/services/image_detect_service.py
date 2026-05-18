from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

import cv2

from backend.core.config import Settings
from backend.services.model_service import model_service
from backend.utils.draw_utils import annotate_result


class ImageDetectService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def detect(self, image_path: Path, conf: float, iou: float, imgsz: int) -> dict:
        started = time.perf_counter()
        frame = cv2.imread(str(image_path))
        if frame is None:
            raise RuntimeError(f"unable to open image: {image_path}")
        result = model_service.predict_image(image_path=image_path, conf=conf, iou=iou, imgsz=imgsz)
        annotated = annotate_result(frame, result)

        output_name = f"result_{uuid4().hex}.jpg"
        output_path = self.settings.output_images_dir / output_name
        cv2.imwrite(str(output_path), annotated)

        detections = []
        primary_class_name: str | None = None
        highest_confidence = -1.0
        herb_summary_map: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {"count": 0, "max_confidence": 0.0}
        )
        names = result.names or {}
        if result.boxes is not None:
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                confidence = float(box.conf[0].item())
                xyxy = box.xyxy[0].tolist()
                class_name = names.get(cls_id, str(cls_id))

                herb_summary_map[class_name]["count"] += 1
                herb_summary_map[class_name]["max_confidence"] = max(
                    float(herb_summary_map[class_name]["max_confidence"]),
                    confidence,
                )

                if confidence > highest_confidence:
                    highest_confidence = confidence
                    primary_class_name = class_name
                detections.append(
                    {
                        "class_id": cls_id,
                        "class_name": class_name,
                        "confidence": round(confidence, 4),
                        "bbox": [round(value, 2) for value in xyxy],
                    }
                )

        herb_candidates = [
            {
                "herb_name": herb_name,
                "count": int(summary["count"]),
                "max_confidence": round(float(summary["max_confidence"]), 4),
            }
            for herb_name, summary in sorted(
                herb_summary_map.items(),
                key=lambda item: (-int(item[1]["count"]), -float(item[1]["max_confidence"]), item[0]),
            )
        ]

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "success": True,
            "type": "image",
            "result_url": f"/outputs/images/{output_name}",
            "detections": detections,
            "primary_class_name": primary_class_name,
            "herb_candidates": herb_candidates,
            "cost_ms": elapsed_ms,
        }
