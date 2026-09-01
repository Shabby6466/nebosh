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

        # Filter out small background detections (e.g., people in paintings)
        img_h, img_w = image_bgr.shape[:2]
        img_area = img_h * img_w
        min_area = img_area * 0.02  # Box must be at least 2% of the frame

        valid_boxes = []
        for i in range(len(boxes)):
            box = boxes[i].xyxy[0].cpu().numpy()  # [x1, y1, x2, y2]
            w = box[2] - box[0]
            h = box[3] - box[1]
            if (w * h) >= min_area:
                valid_boxes.append(boxes[i])

        if len(valid_boxes) == 0:
            return 0, 0.0

        # Re-evaluate confidences for valid boxes
        confidences = np.array([box.conf.cpu().numpy()[0] for box in valid_boxes])
        return len(valid_boxes), float(confidences.max())


person_detector = PersonDetector()
