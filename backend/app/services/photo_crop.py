"""Local, CPU-only person detection and lossless-aspect portrait framing.

Model: OpenCV Zoo YOLOX-S (Apache-2.0), installed explicitly by
scripts/install_photo_model.py. Inference never downloads or uploads anything.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from threading import Lock

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

MODEL_REVISION = "78c368f74ce73ee28fc7a1be418a598c71b58b52"
MODEL_URL = (
    f"https://huggingface.co/opencv/object_detection_yolox/resolve/{MODEL_REVISION}/"
    "object_detection_yolox_2022nov.onnx"
)
MODEL_SHA256 = "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063"
INPUT_SIZE = 640
MARGIN = 0.08  # Eight percent on each side of the detected person.
_detector_lock = Lock()

Box = tuple[float, float, float, float]


class PhotoCropUnavailableError(RuntimeError):
    """Missing or unusable CPU model (not a failure to detect a person)."""


class PersonDetector:
    def __init__(self, model_path: str) -> None:
        if not Path(model_path).is_file():
            raise PhotoCropUnavailableError(
                "Модель обрезки фото не установлена. Запустите backend/scripts/install_photo_model.py."
            )
        options = ort.SessionOptions()
        # Do not monopolize the CPU used by the machine-control/backend processes.
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")
        try:
            self.session = ort.InferenceSession(
                model_path, sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception as error:
            raise PhotoCropUnavailableError("Не удалось загрузить CPU-модель обрезки фото.") from error
        self.input_name = self.session.get_inputs()[0].name
        grids, strides = [], []
        for stride in (8, 16, 32):
            y, x = np.mgrid[:INPUT_SIZE // stride, :INPUT_SIZE // stride]
            grid = np.stack((x, y), axis=-1).reshape(-1, 2)
            grids.append(grid)
            strides.append(np.full((len(grid), 1), stride, dtype=np.float32))
        self.grids = np.concatenate(grids).astype(np.float32)
        self.strides = np.concatenate(strides)
        self.lock = Lock()

    def detect(self, image: Image.Image) -> Box | None:
        ratio = min(INPUT_SIZE / image.width, INPUT_SIZE / image.height)
        resized = image.resize(
            (max(1, int(image.width * ratio)), max(1, int(image.height * ratio))), Image.Resampling.BILINEAR
        )
        # This OpenCV Zoo export expects raw RGB values 0..255, top-left image
        # with 114 padding, not /255 or ImageNet normalization.
        padded = np.full((INPUT_SIZE, INPUT_SIZE, 3), 114, dtype=np.float32)
        padded[:resized.height, :resized.width] = np.asarray(resized)
        tensor = np.ascontiguousarray(padded.transpose(2, 0, 1)[None])
        try:
            with self.lock:
                predictions = self.session.run(None, {self.input_name: tensor})[0][0]
        except Exception as error:
            raise PhotoCropUnavailableError("Не удалось обработать фото на CPU. Попробуйте снова.") from error
        return self._person_box(predictions, ratio, image.size)

    def _person_box(self, predictions: np.ndarray, ratio: float, size: tuple[int, int]) -> Box | None:
        # COCO class 0 = person. Discard candidates classified as a different object.
        scores = predictions[:, 4] * predictions[:, 5]
        keep = (scores >= 0.4) & (predictions[:, 5:].argmax(axis=1) == 0)
        indices = np.flatnonzero(keep)
        if not len(indices):
            return None
        selected = predictions[indices]
        centers = (selected[:, :2] + self.grids[indices]) * self.strides[indices] / ratio
        dimensions = np.exp(np.clip(selected[:, 2:4], -20, 20)) * self.strides[indices] / ratio
        boxes = np.concatenate((centers - dimensions / 2, centers + dimensions / 2), axis=1)
        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, size[0])
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, size[1])
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        order = np.argsort(scores[indices])[::-1]
        people: list[int] = []
        while len(order):
            current = int(order[0])
            if areas[current] <= 0:
                order = order[1:]
                continue
            people.append(current)
            others = order[1:]
            left_top = np.maximum(boxes[current, :2], boxes[others, :2])
            right_bottom = np.minimum(boxes[current, 2:], boxes[others, 2:])
            intersection = np.maximum(right_bottom - left_top, 0).prod(axis=1)
            iou = intersection / np.maximum(areas[current] + areas[others] - intersection, 1e-6)
            order = others[iou < 0.45]
        if not people:
            return None
        # The foreground/largest person is the subject, not smaller bystanders.
        chosen = max(people, key=lambda index: float(areas[index]))
        return tuple(float(value) for value in boxes[chosen])  # type: ignore[return-value]


@lru_cache(maxsize=2)
def _cached_detector(model_path: str) -> PersonDetector:
    return PersonDetector(model_path)


def detect_person(image: Image.Image, model_path: str) -> Box | None:
    with _detector_lock:
        detector = _cached_detector(model_path)
    return detector.detect(image)


def portrait_crop_box(size: tuple[int, int], person: Box) -> tuple[int, int, int, int]:
    """Expand, never cut the figure or distort it, including people near an edge."""
    left, top, right, bottom = person
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0 or not all(math.isfinite(value) for value in person):
        raise ValueError("Некорректная область человека на фото.")
    units = math.ceil(max(width * (1 + 2 * MARGIN) / 3, height * (1 + 2 * MARGIN) / 4))
    crop_width, crop_height = units * 3, units * 4
    x = math.floor((left + right - crop_width) / 2)
    y = math.floor((top + bottom - crop_height) / 2)
    # Prefer actual surrounding pixels over padding. If the required frame is
    # larger than the source, keep all source pixels and fill missing edges.
    x = max(min(0, size[0] - crop_width), min(x, max(0, size[0] - crop_width)))
    y = max(min(0, size[1] - crop_height), min(y, max(0, size[1] - crop_height)))
    return x, y, x + crop_width, y + crop_height


def crop_progress_photo(image: Image.Image, model_path: str) -> Image.Image:
    # Apply phone EXIF orientation before detection; remove EXIF/GPS on encoding.
    oriented = ImageOps.exif_transpose(image).convert("RGB")
    person = detect_person(oriented, model_path)
    if person is None:
        raise ValueError("Не удалось найти человека на фото. Встаньте в полный рост в кадр и переснимите.")
    result = oriented.crop(portrait_crop_box(oriented.size, person))
    # Exact integer 3:4, no stretching or needless upscaling. Cap at 900x1200.
    units = min(300, result.width // 3)
    return result.resize((units * 3, units * 4), Image.Resampling.LANCZOS)