import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class CandidateCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None
    cnic_or_passport_no: str
    exam_booking_ref: str | None = None


class CandidateOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: EmailStr
    kyc_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class KYCResult(BaseModel):
    candidate_id: uuid.UUID
    verified: bool
    match_score: float
    liveness_score: float
    liveness_passed: bool
    reason: str | None = None


class SessionCreate(BaseModel):
    candidate_id: uuid.UUID
    exam_code: str


class SessionOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    exam_code: str
    status: str
    started_at: datetime

    class Config:
        from_attributes = True


class SessionSummaryOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    candidate_name: str
    exam_code: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    violation_count: int


class FrameEvalResult(BaseModel):
    person_count: int
    face_match: bool | None
    face_similarity: float | None
    liveness_pass: bool | None
    head_yaw: float | None = None
    head_pitch: float | None = None
    gaze_ratio_x: float | None = None
    gaze_ratio_y: float | None = None
    violation: str | None = None
    processing_ms: int


class ViolationOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    type: str
    confidence: float | None
    detected_at: datetime
    review_status: str
    snapshot_url: str  # signed URL, populated at serialization time

    class Config:
        from_attributes = True
