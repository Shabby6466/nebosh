"""Face detection, embedding, 1:1 matching, passive liveness, and gaze/pose analysis.

Uses InsightFace (ArcFace, ONNXRuntime backend) for detection + embedding.
Head-pose (yaw / pitch) is estimated with cv2.solvePnP on the 3D-68-landmark
output already produced by buffalo_l's 1k3d68 model.  Eye gaze is derived from
the 2D 106-pt landmarks (also from buffalo_l) — no extra model required.
"""
from __future__ import annotations

import cv2
import numpy as np
import onnxruntime as ort
from insightface.app import FaceAnalysis

from app.core.config import settings

# 3D reference face model points (generic human face, mm scale).
# Indices correspond to landmarks produced by InsightFace's 1k3d68 model
# remapped to the standard 6-point subset used for head-pose PnP.
_MODEL_3D_POINTS = np.array([
    [0.0,   0.0,    0.0],    # nose tip          (lmk 30)
    [0.0,  -330.0, -65.0],   # chin              (lmk  8)
    [-225.0, 170.0, -135.0], # left eye corner   (lmk 36)
    [225.0,  170.0, -135.0], # right eye corner  (lmk 45)
    [-150.0, -150.0, -125.0],# left mouth corner (lmk 48)
    [150.0,  -150.0, -125.0],# right mouth corner(lmk 54)
], dtype=np.float64)


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

    def get_faces(self, image_bgr: np.ndarray) -> list:
        """Return all detected faces (no count constraint)."""
        return self._app.get(image_bgr)

    def get_single_face(self, image_bgr: np.ndarray):
        """Detect faces in an image; require exactly one for KYC enrollment."""
        faces = self.get_faces(image_bgr)
        if len(faces) == 0:
            raise NoFaceDetected("No face detected in image")
        if len(faces) > 1:
            raise MultipleFacesDetected("Multiple faces detected; expected exactly one")
        return faces[0]

    # ------------------------------------------------------------------
    # Head-pose + gaze
    # ------------------------------------------------------------------

    def estimate_pose(self, face, image_bgr: np.ndarray) -> tuple[float, float, float, float]:
        """Return (yaw_deg, pitch_deg, gaze_ratio_x, gaze_ratio_y) for an already-detected face.

        yaw_deg   > 0  → turning right,  < 0 → turning left
        pitch_deg > 0  → tilting up,     < 0 → looking down
        gaze_ratio     → 0.5 = centred; <0.35 or >0.65 = eyes flicked sideways
        """
        h, w = image_bgr.shape[:2]
        focal = w  # rough approximation: focal length ≈ image width in pixels
        cam_matrix = np.array([
            [focal, 0,     w / 2],
            [0,     focal, h / 2],
            [0,     0,     1   ],
        ], dtype=np.float64)
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        yaw_deg = pitch_deg = 0.0
        if face.landmark_3d_68 is not None:
            lmk = face.landmark_3d_68  # shape (68, 3) — x,y are image pixels; z is depth
            # 6-point subset matching _MODEL_3D_POINTS order
            image_pts = np.array([
                lmk[30, :2],  # nose tip
                lmk[8,  :2],  # chin
                lmk[36, :2],  # left eye outer corner
                lmk[45, :2],  # right eye outer corner
                lmk[48, :2],  # left mouth corner
                lmk[54, :2],  # right mouth corner
            ], dtype=np.float64)

            ok, rvec, tvec = cv2.solvePnP(
                _MODEL_3D_POINTS, image_pts, cam_matrix, dist_coeffs,
                flags=cv2.SOLVEPNP_ITERATIVE,
            )
            if ok:
                rmat, _ = cv2.Rodrigues(rvec)
                # The 3D model uses Y-up convention; OpenCV camera uses Y-down.
                # This injects a ~180° base rotation around X into solvePnP's output,
                # which is why a frontal face reads pitch≈180° instead of 0°.
                # Pre-multiply by Rx(-180°) = diag(1,-1,-1) to cancel that offset so
                # that frontal → 0°, looking down → negative, looking up → positive.
                _Rx_neg180 = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], dtype=np.float64)
                rmat_adj = _Rx_neg180 @ rmat

                sy = np.sqrt(rmat_adj[0, 0] ** 2 + rmat_adj[1, 0] ** 2)
                if sy > 1e-6:
                    pitch_deg = float(np.degrees(np.arctan2(rmat_adj[2, 1], rmat_adj[2, 2])))
                    yaw_deg   = float(np.degrees(np.arctan2(-rmat_adj[2, 0], sy)))
                else:  # gimbal lock
                    pitch_deg = float(np.degrees(np.arctan2(-rmat_adj[1, 2], rmat_adj[1, 1])))
                    yaw_deg   = float(np.degrees(np.arctan2(-rmat_adj[2, 0], sy)))

        # Eye gaze: compare actual pupil centers (from RetinaFace 5-pt keypoints) against
        # eye corner positions (from 68-pt landmarks).
        # Guard: compute Eye Aspect Ratio (EAR) first — if eyes are closed the kps pupil
        # centers drift unpredictably, so skip gaze and return the neutral 0.5 to avoid
        # false-positive violations on blinks / deliberate eye-closure.
        gaze_ratio_x = 0.5  # default — centred / unknown
        gaze_ratio_y = 0.5
        try:
            if face.kps is not None and face.landmark_3d_68 is not None:
                lmk = face.landmark_3d_68  # x,y in image pixels

                def _dist(a, b):
                    return float(np.linalg.norm(a - b))

                # EAR per eye using 68-pt landmarks (dlib/IBUG indices)
                # Left eye:  36(outer) 37 38 39(inner) 40 41
                # Right eye: 42(inner) 43 44 45(outer) 46 47
                left_ear  = (_dist(lmk[37,:2], lmk[41,:2]) + _dist(lmk[38,:2], lmk[40,:2])) \
                            / (2.0 * _dist(lmk[36,:2], lmk[39,:2]) + 1e-6)
                right_ear = (_dist(lmk[43,:2], lmk[47,:2]) + _dist(lmk[44,:2], lmk[46,:2])) \
                            / (2.0 * _dist(lmk[42,:2], lmk[45,:2]) + 1e-6)
                avg_ear = (left_ear + right_ear) / 2

                # Only compute gaze when eyes are open (EAR > 0.18 is reliably open)
                if avg_ear > 0.18:
                    # Eye corners X
                    left_outer_x  = float(lmk[36, 0])  # left eye outer corner (temple)
                    left_inner_x  = float(lmk[39, 0])  # left eye inner corner (nose)
                    right_inner_x = float(lmk[42, 0])  # right eye inner corner (nose)
                    right_outer_x = float(lmk[45, 0])  # right eye outer corner (temple)

                    # Eye lids Y (approximated by average of top and bottom points)
                    left_top_y = float((lmk[37, 1] + lmk[38, 1]) / 2)
                    left_bot_y = float((lmk[40, 1] + lmk[41, 1]) / 2)
                    right_top_y = float((lmk[43, 1] + lmk[44, 1]) / 2)
                    right_bot_y = float((lmk[46, 1] + lmk[47, 1]) / 2)

                    # Pupil/iris X, Y from RetinaFace keypoints (move with actual gaze)
                    left_pupil_x  = float(face.kps[0, 0])
                    left_pupil_y  = float(face.kps[0, 1])
                    right_pupil_x = float(face.kps[1, 0])
                    right_pupil_y = float(face.kps[1, 1])

                    def _gaze_ratio(pupil, val_a, val_b) -> float:
                        lo, hi = min(val_a, val_b), max(val_a, val_b)
                        span = hi - lo
                        if span < 2:
                            return 0.5
                        return float(np.clip((pupil - lo) / span, 0.0, 1.0))

                    # X gaze: 0.5 = centred, <0.5 = looking left, >0.5 = looking right
                    left_ratio_x  = _gaze_ratio(left_pupil_x, left_outer_x, left_inner_x)
                    right_ratio_x = _gaze_ratio(right_pupil_x, right_inner_x, right_outer_x)
                    gaze_ratio_x  = float((left_ratio_x + right_ratio_x) / 2)

                    # Y gaze: 0.5 = centred, <0.5 = looking up (since Y increases downwards), >0.5 = looking down
                    left_ratio_y = _gaze_ratio(left_pupil_y, left_top_y, left_bot_y)
                    right_ratio_y = _gaze_ratio(right_pupil_y, right_top_y, right_bot_y)
                    gaze_ratio_y = float((left_ratio_y + right_ratio_y) / 2)

        except Exception:
            pass

        return yaw_deg, pitch_deg, gaze_ratio_x, gaze_ratio_y

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
