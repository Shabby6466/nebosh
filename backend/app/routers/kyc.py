import uuid

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Candidate, FaceEmbedding
from app.schemas import KYCResult
from app.services.face_service import MultipleFacesDetected, NoFaceDetected, face_service
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
    db: AsyncSession = Depends(get_db),
):
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(404, "Candidate not found")

    id_bytes = await id_document.read()
    selfie_bytes = await selfie.read()
    id_img = _decode_upload(id_bytes)
    selfie_img = _decode_upload(selfie_bytes)

    # 1. Face detection + embedding on both images
    try:
        id_face = face_service.get_single_face(id_img)
        id_embedding = id_face.normed_embedding.astype(np.float32)
        selfie_face = face_service.get_single_face(selfie_img)
        selfie_embedding = selfie_face.normed_embedding.astype(np.float32)
    except NoFaceDetected:
        raise HTTPException(422, "No face detected in one of the uploaded images")
    except MultipleFacesDetected:
        raise HTTPException(422, "Multiple faces detected — please submit a photo with only your face visible")

    # 2. Liveness check on the selfie only (ID document is a static print/scan by nature)
    x1, y1, x2, y2 = selfie_face.bbox.astype(int)
    selfie_crop = selfie_img[max(y1, 0):y2, max(x1, 0):x2]
    liveness_passed, liveness_score = face_service.check_liveness(selfie_crop)

    # 3. 1:1 match between ID photo and live selfie
    match_passed, match_score = face_service.match(id_embedding, selfie_embedding)

    verified = liveness_passed and match_passed

    # 4. Persist source images (encrypted at rest via SSE-KMS in storage layer)
    id_key = upload_image(id_img, prefix=f"kyc/{candidate_id}/id")
    selfie_key = upload_image(selfie_img, prefix=f"kyc/{candidate_id}/selfie")

    candidate.id_document_s3_key = id_key
    candidate.selfie_s3_key = selfie_key
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

    return KYCResult(
        candidate_id=candidate_id,
        verified=verified,
        match_score=match_score,
        liveness_score=liveness_score,
        liveness_passed=liveness_passed,
        reason=reason,
    )


@router.get("/{candidate_id}/status")
async def kyc_status(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(404, "Candidate not found")
    return {"candidate_id": candidate_id, "kyc_status": candidate.kyc_status}
