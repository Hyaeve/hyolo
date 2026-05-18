from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


PALETTE = [
    (255, 99, 71),
    (0, 191, 255),
    (50, 205, 50),
    (255, 215, 0),
    (186, 85, 211),
    (255, 140, 0),
    (0, 0, 0),
    (255, 255, 255),
]

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]


def annotate_result(frame: np.ndarray, result: Any) -> np.ndarray:
    canvas = frame.copy()
    names = result.names or {}

    if result.boxes is None:
        return canvas

    for box in result.boxes:
        cls_id = int(box.cls[0].item())
        confidence = float(box.conf[0].item())
        x1, y1, x2, y2 = [int(round(value)) for value in box.xyxy[0].tolist()]
        class_name = names.get(cls_id, str(cls_id))
        label = f"{class_name} {confidence:.2f}"

        color = choose_annotation_color(canvas, (x1, y1, x2, y2))
        text_color = choose_text_color(color)
        draw_labelled_box(canvas, (x1, y1, x2, y2), label, color, text_color)

    return canvas


def draw_labelled_box(
    image: np.ndarray,
    bbox: tuple[int, int, int, int],
    label: str,
    color: tuple[int, int, int],
    text_color: tuple[int, int, int],
) -> None:
    x1, y1, x2, y2 = bbox
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 3, cv2.LINE_AA)

    _draw_unicode_label(image, label, (x1, y1), color, text_color)


def _draw_unicode_label(
    image: np.ndarray,
    label: str,
    anchor: tuple[int, int],
    color: tuple[int, int, int],
    text_color: tuple[int, int, int],
) -> None:
    x1, y1 = anchor
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_image)
    font = _load_font(28)

    if font is None:
        font_cv = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.72
        thickness = 2
        (text_w, text_h), baseline = cv2.getTextSize(label, font_cv, font_scale, thickness)
        label_x1 = max(0, x1)
        label_y2 = max(text_h + baseline + 10, y1)
        label_y1 = max(0, label_y2 - text_h - baseline - 12)
        label_x2 = min(image.shape[1] - 1, label_x1 + text_w + 16)
        cv2.rectangle(image, (label_x1, label_y1), (label_x2, label_y2), color, -1, cv2.LINE_AA)
        cv2.putText(
            image,
            label,
            (label_x1 + 8, label_y2 - baseline - 5),
            font_cv,
            font_scale,
            text_color,
            thickness,
            cv2.LINE_AA,
        )
        return

    left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
    text_w = right - left
    text_h = bottom - top
    padding_x = 10
    padding_y = 8
    label_x1 = max(0, x1)
    label_y2 = max(text_h + padding_y * 2, y1)
    label_y1 = max(0, label_y2 - text_h - padding_y * 2)
    label_x2 = min(image.shape[1] - 1, label_x1 + text_w + padding_x * 2)

    draw.rounded_rectangle(
        [(label_x1, label_y1), (label_x2, label_y2)],
        radius=8,
        fill=(color[2], color[1], color[0]),
    )
    draw.text(
        (label_x1 + padding_x, label_y1 + padding_y - top),
        label,
        font=font,
        fill=(text_color[2], text_color[1], text_color[0]),
    )

    converted = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    image[:, :] = converted
    return


def choose_annotation_color(image: np.ndarray, bbox: tuple[int, int, int, int]) -> tuple[int, int, int]:
    x1, y1, x2, y2 = bbox
    h, w = image.shape[:2]

    pad = 6
    sx1 = max(0, x1 - pad)
    sy1 = max(0, y1 - pad)
    sx2 = min(w, x2 + pad)
    sy2 = min(h, y2 + pad)

    patch = image[sy1:sy2, sx1:sx2]
    if patch.size == 0:
        return (0, 191, 255)

    mean_color = patch.mean(axis=(0, 1))
    best_color = PALETTE[0]
    best_score = -1.0

    for color in PALETTE:
        score = color_distance(mean_color, np.array(color, dtype=np.float32))
        luminance_gap = abs(calc_luminance(mean_color) - calc_luminance(np.array(color, dtype=np.float32)))
        total_score = score + luminance_gap * 1.4
        if total_score > best_score:
            best_score = total_score
            best_color = color

    return best_color


def choose_text_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    luminance = calc_luminance(np.array(color, dtype=np.float32))
    return (20, 32, 44) if luminance > 160 else (255, 255, 255)


def calc_luminance(color: np.ndarray) -> float:
    b, g, r = color.tolist()
    return 0.114 * b + 0.587 * g + 0.299 * r


def color_distance(color1: np.ndarray, color2: np.ndarray) -> float:
    return float(np.linalg.norm(color1 - color2))


@lru_cache(maxsize=8)
def _load_font(size: int) -> ImageFont.FreeTypeFont | None:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return None
