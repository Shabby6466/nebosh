"""Face detection, embedding, 1:1 matching, and passive liveness.

Uses InsightFace (ArcFace, ONNXRuntime backend) for detection + embedding.
Passive liveness uses a Silent-Face-Anti-Spoofing style ONNX model; swap the
model path if you train/fine-tune your own on local (PK) webcam samples.
"""
from __future__ import annotations

import numpy as np
import onnxruntime as ort
from insightface.app import FaceAnalysis

from app.core.config import settings


class NoFaceDetected(Exception):
    pass


class MultipleFacesDetected(Exception):
    pass


class FaceService:
    def __init__(self) -> None:
        # buffalo_l bundles a RetinaFace detector + ArcFace recognizer (512-d embeddings)
        self._app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        self._app.prepare(ctx_id=0, det_size=(640, 640))

        # Passive anti-spoofing model (MiniFASNet-style, binary real/spoof classifier).
        # Path is a local ONNX export — see docs/models.md for training/export notes.
        self._liveness_session = ort.InferenceSession(
            "app/ml_models/minifasnet_liveness.onnx", providers=["CPUExecutionProvider"]
        )

    def get_single_face(self, image_bgr: np.ndarray):
        """Detect faces in an image; require exactly one for KYC enrollment."""
        faces = self._app.get(image_bgr)
        if len(faces) == 0:
            raise NoFaceDetected("No face detected in image")
        if len(faces) > 1:
            raise MultipleFacesDetected("Multiple faces detected; expected exactly one")
        return faces[0]

    def embed(self, image_bgr: np.ndarray) -> np.ndarray:
        """Return a single L2-normalized 512-d embedding for the primary face."""
        face = self.get_single_face(image_bgr)
        emb = face.normed_embedding  # already L2-normalized by insightface
        return emb.astype(np.float32)

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

    def match(self, embedding_a: np.ndarray, embedding_b: np.ndarray) -> tuple[bool, float]:
        score = self.cosine_similarity(embedding_a, embedding_b)
        return score >= settings.face_match_threshold, score

    def check_liveness(self, face_crop_bgr: np.ndarray) -> tuple[bool, float]:
        """Passive liveness on a cropped face. Returns (is_live, score)."""
        inp = self._preprocess_liveness(face_crop_bgr)
        input_name = self._liveness_session.get_inputs()[0].name
        output = self._liveness_session.run(None, {input_name: inp})[0]
        # Model outputs [spoof_prob, real_prob] softmax; index 1 = "real"
        real_score = float(output[0][1])
        return real_score >= settings.liveness_threshold, real_score

    @staticmethod
    def _preprocess_liveness(face_crop_bgr: np.ndarray) -> np.ndarray:
        import cv2

        resized = cv2.resize(face_crop_bgr, (80, 80))
        normalized = resized.astype(np.float32) / 255.0
        chw = np.transpose(normalized, (2, 0, 1))
        return np.expand_dims(chw, axis=0)


face_service = FaceService()
