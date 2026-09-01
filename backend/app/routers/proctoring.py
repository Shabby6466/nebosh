import time
import uuid
from collections import defaultdict

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import SessionLocal, get_db
from app.models import ExamSession, FaceEmbedding, SessionFrame, Violation
from app.schemas import FrameEvalResult
from app.services.face_service import MultipleFacesDetected, NoFaceDetected, face_service
from app.services.person_detector import person_detector
from app.services.storage import upload_image

router = APIRouter(tags=["proctoring"])

# In-memory debounce counters: {session_id: {violation_type: consecutive_count}}
# For multi-instance deployments, back this with Redis instead.
_violation_streaks: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))


async def _load_reference_embedding(db: AsyncSession, candidate_id: uuid.UUID) -> np.ndarray:
    result = await db.execute(
        select(FaceEmbedding)
        .where(FaceEmbedding.candidate_id == candidate_id, FaceEmbedding.is_active.is_(True))
        .order_by(FaceEmbedding.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(409, "No verified reference embedding for this candidate")
    return np.array(row.embedding, dtype=np.float32)


def _resize_cap(image_bgr: np.ndarray, max_dim: int) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    scale = max_dim / max(h, w)
    if scale >= 1:
        return image_bgr
    return cv2.resize(image_bgr, (int(w * scale), int(h * scale)))


async def evaluate_frame(
    db: AsyncSession, session: ExamSession, image_bgr: np.ndarray, reference_embedding: np.ndarray
) -> FrameEvalResult:
    t0 = time.monotonic()
    image_bgr = _resize_cap(image_bgr, settings.max_frame_dim_px)

    person_count, person_conf = person_detector.count_people(image_bgr)

    face_match: bool | None = None
    face_similarity: float | None = None
    liveness_pass: bool | None = None
    head_yaw: float | None = None
    head_pitch: float | None = None
    gaze_ratio_x: float | None = None
    gaze_ratio_y: float | None = None
    violation_type: str | None = None
    snapshot_needed = False

    if person_count == 0:
        violation_type = "candidate_missing"
        snapshot_needed = True
    elif person_count > 1:
        violation_type = "multiple_people"
        snapshot_needed = True
    else:
        # Exactly one person — run face match against the enrolled reference
        try:
            faces = face_service.get_faces(image_bgr)
            if len(faces) == 0:
                raise NoFaceDetected()
            if len(faces) > 1:
                raise MultipleFacesDetected()

            face = faces[0]
            emb = face.normed_embedding.astype("float32")
            face_match, face_similarity = face_service.match(reference_embedding, emb)

            if not face_match:
                violation_type = "face_mismatch"
                snapshot_needed = True
            else:
                # Face confirmed — now check head pose and gaze
                yaw, pitch, gaze_x, gaze_y = face_service.estimate_pose(face, image_bgr)
                head_yaw = round(yaw, 1)
                head_pitch = round(pitch, 1)
                gaze_ratio_x = round(gaze_x, 3)
                gaze_ratio_y = round(gaze_y, 3)

                head_turned   = abs(yaw)   > settings.head_yaw_threshold
                head_down     = pitch      < -settings.head_pitch_down_threshold
                head_up       = pitch      >  settings.head_pitch_up_threshold
                gaze_flicked_x = abs(gaze_x - 0.5) > settings.gaze_deviation_threshold
                gaze_flicked_y = abs(gaze_y - 0.5) > settings.gaze_deviation_threshold

                if head_turned or head_down or head_up or gaze_flicked_x or gaze_flicked_y:
                    violation_type = "looking_away"
                    snapshot_needed = True

        except MultipleFacesDetected:
            # InsightFace found more faces than YOLO counted (e.g. a photo/screen in background)
            violation_type = "multiple_people"
            snapshot_needed = True
        except NoFaceDetected:
            # Person detected by YOLO but no clear face (e.g. facing away) — treat as missing
            violation_type = "candidate_missing"
            snapshot_needed = True

    processing_ms = int((time.monotonic() - t0) * 1000)

    if violation_type:
        streaks = _violation_streaks[str(session.id)]
        streaks[violation_type] += 1
        # reset other streak counters on a differing observation
        for k in list(streaks.keys()):
            if k != violation_type:
                streaks[k] = 0

        if streaks[violation_type] >= settings.violation_debounce_frames and snapshot_needed:
            snapshot_key = upload_image(image_bgr, prefix=f"violations/{session.id}")
            db.add(
                Violation(
                    session_id=session.id,
                    candidate_id=session.candidate_id,
                    type=violation_type,
                    confidence=person_conf if violation_type != "face_mismatch" else (1 - (face_similarity or 0)),
                    snapshot_s3_key=snapshot_key,
                )
            )
    else:
        _violation_streaks[str(session.id)] = defaultdict(int)

    db.add(
        SessionFrame(
            session_id=session.id,
            person_count=person_count,
            face_match=face_match,
            face_similarity=face_similarity,
            liveness_pass=liveness_pass,
            head_yaw=head_yaw,
            head_pitch=head_pitch,
            gaze_ratio_x=gaze_ratio_x,
            gaze_ratio_y=gaze_ratio_y,
            processing_ms=processing_ms,
        )
    )
    await db.commit()

    return FrameEvalResult(
        person_count=person_count,
        face_match=face_match,
        face_similarity=face_similarity,
        liveness_pass=liveness_pass,
        head_yaw=head_yaw,
        head_pitch=head_pitch,
        gaze_ratio_x=gaze_ratio_x,
        gaze_ratio_y=gaze_ratio_y,
        violation=violation_type,
        processing_ms=processing_ms,
    )


@router.post("/api/v1/sessions/{session_id}/frame", response_model=FrameEvalResult)
async def evaluate_frame_rest(
    session_id: uuid.UUID,
    frame: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """REST fallback for clients where WebSocket is blocked (restrictive corporate/campus networks)."""
    session = await db.get(ExamSession, session_id)
    if session is None or session.status != "active":
        raise HTTPException(404, "Active session not found")

    reference_embedding = await _load_reference_embedding(db, session.candidate_id)

    data = await frame.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    image_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise HTTPException(400, "Could not decode frame")

    return await evaluate_frame(db, session, image_bgr, reference_embedding)


@router.websocket("/ws/v1/sessions/{session_id}")
async def proctoring_ws(websocket: WebSocket, session_id: uuid.UUID):
    await websocket.accept()

    async with SessionLocal() as db:
        session = await db.get(ExamSession, session_id)
        if session is None or session.status != "active":
            await websocket.close(code=4404, reason="Active session not found")
            return
        try:
            reference_embedding = await _load_reference_embedding(db, session.candidate_id)
        except HTTPException as exc:
            await websocket.close(code=4409, reason=exc.detail)
            return

        try:
            while True:
                # Client sends raw JPEG bytes for each captured frame (binary WS message)
                data = await websocket.receive_bytes()
                arr = np.frombuffer(data, dtype=np.uint8)
                image_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if image_bgr is None:
                    await websocket.send_json({"error": "invalid_frame"})
                    continue

                result = await evaluate_frame(db, session, image_bgr, reference_embedding)
                await websocket.send_json(result.model_dump())
        except WebSocketDisconnect:
            pass
