import uuid

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import get_db
from app.models import Candidate, FaceEmbedding
from app.schemas import KYCResult
from app.services.face_service import (
    MultipleFacesDetected,
    NoFaceDetected,
    UnexpectedFaceCount,
    face_service,
)
from app.services.storage import upload_image

router = APIRouter(prefix="/api/v1/kyc", tags=["kyc"])


def _decode_upload(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Could not decode image")
    return img


@router.post("/verify", response_model=KYCResult)
async def verify_kyc(
    candidate_id: uuid.UUID,
    id_document: UploadFile = File(...),
    selfie: UploadFile = File(...),
    hold_id_photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(404, "Candidate not found")

    id_bytes = await id_document.read()
    selfie_bytes = await selfie.read()
    hold_id_bytes = await hold_id_photo.read()
    id_img = _decode_upload(id_bytes)
    selfie_img = _decode_upload(selfie_bytes)
    hold_id_img = _decode_upload(hold_id_bytes)

    # 1. Face detection + embedding on both images
    try:
        id_face = face_service.get_single_face(id_img)
        id_embedding = id_face.normed_embedding.astype(np.float32)
        selfie_face = face_service.get_primary_face(selfie_img)
        selfie_embedding = selfie_face.normed_embedding.astype(np.float32)
    except NoFaceDetected:
        raise HTTPException(422, "No face detected in one of the uploaded images")
    except MultipleFacesDetected:
        raise HTTPException(422, "Multiple faces detected — please submit a photo with only your face visible")

    # 2. Liveness check on the selfie only (ID document is a static print/scan by nature)
    liveness_passed, liveness_score = face_service.check_liveness(selfie_img, selfie_face.bbox)

    # 3. 1:1 match between ID photo and live selfie
    match_passed, match_score = face_service.match(id_embedding, selfie_embedding)

    # 4. "Hold your ID next to your face" shot — proves physical possession of
    # the card at capture time. Must contain exactly two faces (the live face
    # and the card photo) and those two faces must match each other.
    try:
        hold_live_face, hold_card_face = face_service.get_hold_id_faces(hold_id_img)
    except UnexpectedFaceCount:
        raise HTTPException(
            422,
            "Could not find exactly one live face and one ID card photo in the hold-ID shot — "
            "make sure your face and your CNIC's photo are both clearly visible",
        )
    hold_live_embedding = hold_live_face.normed_embedding.astype(np.float32)
    hold_card_embedding = hold_card_face.normed_embedding.astype(np.float32)
    hold_id_match_passed, hold_id_match_score = face_service.match(
        hold_live_embedding, hold_card_embedding, threshold=settings.hold_id_match_threshold
    )

    verified = liveness_passed and match_passed and hold_id_match_passed

    # 5. Persist source images (encrypted at rest via SSE-KMS in storage layer)
    id_key = upload_image(id_img, prefix=f"kyc/{candidate_id}/id")
    selfie_key = upload_image(selfie_img, prefix=f"kyc/{candidate_id}/selfie")
    hold_id_key = upload_image(hold_id_img, prefix=f"kyc/{candidate_id}/hold_id")

    candidate.id_document_s3_key = id_key
    candidate.selfie_s3_key = selfie_key
    candidate.hold_id_s3_key = hold_id_key
    candidate.kyc_status = "verified" if verified else "rejected"

    if verified:
        # Deactivate any prior embedding, store the new one as the active reference
        await db.execute(
            FaceEmbedding.__table__.update()
            .where(FaceEmbedding.candidate_id == candidate_id)
            .values(is_active=False)
        )
        db.add(
            FaceEmbedding(
                candidate_id=candidate_id,
                embedding=selfie_embedding.tolist(),
                match_score=match_score,
                liveness_score=liveness_score,
                is_active=True,
            )
        )

    await db.commit()

    reason = None
    if not liveness_passed:
        reason = "liveness_check_failed"
    elif not match_passed:
        reason = "face_mismatch"
    elif not hold_id_match_passed:
        reason = "hold_id_mismatch"

    return KYCResult(
        candidate_id=candidate_id,
        verified=verified,
        match_score=match_score,
        liveness_score=liveness_score,
        liveness_passed=liveness_passed,
        hold_id_match_score=hold_id_match_score,
        hold_id_match_passed=hold_id_match_passed,
        reason=reason,
    )


@router.get("/{candidate_id}/status")
async def kyc_status(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(404, "Candidate not found")
    return {"candidate_id": candidate_id, "kyc_status": candidate.kyc_status}
