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
    hold_id_match_score: float
    hold_id_match_passed: bool
    reason: str | None = None


class FaceCheckResult(BaseModel):
    verified: bool
    face_match: bool | None
    face_similarity: float | None
    liveness_pass: bool | None
    liveness_score: float | None
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
    liveness_score: float | None = None
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


class ClientEventCreate(BaseModel):
    type: str  # e.g., 'tab_switched', 'window_unfocused'
    confidence: float = 1.0


class SessionTokenRequest(BaseModel):
    candidate_id: uuid.UUID
    session_id: uuid.UUID | None = None
    expires_minutes: int | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AdminLogin(BaseModel):
    email: EmailStr
    password: str


class OrganizationCreate(BaseModel):
    name: str
    allowed_origin: str | None = None
    webhook_url: str | None = None


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    allowed_origin: str | None
    webhook_url: str | None
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None
    candidate_count: int
    session_count: int
    violation_count: int


class OrganizationCreated(OrganizationOut):
    api_key: str  # raw key — shown exactly once, here, at creation time


class ApiKeyRotated(BaseModel):
    id: uuid.UUID
    api_key: str  # raw key — shown exactly once
