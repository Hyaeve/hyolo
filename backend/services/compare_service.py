from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from uuid import uuid4

import cv2

from backend.core.config import Settings
from backend.services.herb_knowledge_service import HerbKnowledgeService
from backend.services.model_service import model_service
from backend.utils.draw_utils import annotate_result


logger = logging.getLogger(__name__)


class CompareService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def history_dir(self) -> Path:
        directory = self.settings.output_comparisons_dir
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    async def build_comparison_result(
        self,
        image_paths: list[Path],
        model_a_name: str,
        model_b_name: str,
        conf: float,
        iou: float,
        imgsz: int,
    ) -> dict:
        compare_id = uuid4().hex
        compare_dir = self.history_dir() / compare_id
        model_a_dir = compare_dir / "model_a"
        model_b_dir = compare_dir / "model_b"
        model_a_dir.mkdir(parents=True, exist_ok=True)
        model_b_dir.mkdir(parents=True, exist_ok=True)

        model_a, resolved_a = model_service.build_model_instance(model_a_name)
        model_b, resolved_b = model_service.build_model_instance(model_b_name)

        items = []
        for image_path in image_paths:
            frame = cv2.imread(str(image_path))
            if frame is None:
                continue

            items.append(
                {
                    "source_name": image_path.name,
                    "source_path": str(image_path),
                    "model_a": self._run_single(model_a, resolved_a.name, frame, image_path, model_a_dir, conf, iou, imgsz),
                    "model_b": self._run_single(model_b, resolved_b.name, frame, image_path, model_b_dir, conf, iou, imgsz),
                }
            )

        payload = {
            "compare_id": compare_id,
            "created_at": int(time.time()),
            "model_a": {"model_name": resolved_a.name, "model_path": str(resolved_a)},
            "model_b": {"model_name": resolved_b.name, "model_path": str(resolved_b)},
            "image_count": len(items),
            "items": items,
        }

        analysis_payload = {
            "model_a": {
                "name": resolved_a.name,
                "images": [
                    {
                        "source_name": item["source_name"],
                        "detection_count": item["model_a"]["detection_count"],
                        "avg_confidence": item["model_a"]["avg_confidence"],
                        "inference_ms": item["model_a"]["inference_ms"],
                    }
                    for item in items
                ],
            },
            "model_b": {
                "name": resolved_b.name,
                "images": [
                    {
                        "source_name": item["source_name"],
                        "detection_count": item["model_b"]["detection_count"],
                        "avg_confidence": item["model_b"]["avg_confidence"],
                        "inference_ms": item["model_b"]["inference_ms"],
                    }
                    for item in items
                ],
            },
        }

        payload["analysis"] = await HerbKnowledgeService(self.settings).analyze_model_comparison(analysis_payload)

        meta_path = compare_dir / "meta.json"
        with meta_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

        logger.info(
            "comparison completed: %s vs %s, images=%s, compare_id=%s",
            resolved_a.name,
            resolved_b.name,
            len(items),
            compare_id,
        )

        return payload

    def list_history(self) -> dict:
        history = []
        for meta_path in sorted(self.history_dir().glob("*/meta.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            with meta_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            history.append(
                {
                    "compare_id": payload.get("compare_id"),
                    "created_at": payload.get("created_at"),
                    "image_count": payload.get("image_count", 0),
                    "model_a": payload.get("model_a", {}),
                    "model_b": payload.get("model_b", {}),
                }
            )
        return {"history": history}

    def get_history_detail(self, compare_id: str) -> dict:
        meta_path = self.history_dir() / Path(compare_id).name / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"comparison history not found: {compare_id}")

        with meta_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        logger.info("comparison history loaded: compare_id=%s", compare_id)
        return payload

    def _run_single(
        self,
        model,
        model_name: str,
        frame,
        image_path: Path,
        output_dir: Path,
        conf: float,
        iou: float,
        imgsz: int,
    ) -> dict:
        started = time.perf_counter()
        result = model_service.predict_image_with_model(model, image_path, conf, iou, imgsz)
        inference_ms = int((time.perf_counter() - started) * 1000)

        annotated = annotate_result(frame.copy(), result)
        output_name = f"{image_path.stem}_{uuid4().hex}.jpg"
        output_path = output_dir / output_name
        cv2.imwrite(str(output_path), annotated)

        names = result.names or {}
        detections = []
        confidences = []
        if result.boxes is not None:
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                confidence = float(box.conf[0].item())
                detections.append(
                    {
                        "class_id": cls_id,
                        "class_name": names.get(cls_id, str(cls_id)),
                        "confidence": round(confidence, 4),
                    }
                )
                confidences.append(confidence)

        avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        return {
            "model_name": model_name,
            "result_url": f"/outputs/comparisons/{output_dir.parent.name}/{output_dir.name}/{output_name}",
            "detection_count": len(detections),
            "avg_confidence": avg_confidence,
            "inference_ms": inference_ms,
            "detections": detections,
        }
