"""Person counting via YOLOv8n, exported to ONNX for lightweight CPU inference."""
from __future__ import annotations

import numpy as np
from ultralytics import YOLO

from app.core.config import settings

PERSON_CLASS_ID = 0  # COCO class 0 = 'person'


class PersonDetector:
    def __init__(self, model_path: str = "app/ml_models/yolov8n.onnx") -> None:
        self._model = YOLO(model_path, task="detect")

    def count_people(self, image_bgr: np.ndarray) -> tuple[int, float]:
        """Returns (person_count, max_confidence_among_detections)."""
        results = self._model.predict(
            image_bgr,
            classes=[PERSON_CLASS_ID],
            conf=settings.person_conf_threshold,
            verbose=False,
        )
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return 0, 0.0
        confidences = boxes.conf.cpu().numpy()
        return len(boxes), float(confidences.max())


person_detector = PersonDetector()
