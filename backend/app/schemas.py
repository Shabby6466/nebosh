import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.config import settings

SessionMode = Literal["exam", "interview"]


class CandidateCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None
    cnic_or_passport_no: str
    exam_booking_ref: str | None = None

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, v: str) -> str:
        return v.lower()


class CandidateOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: EmailStr
    kyc_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class CandidateDetailOut(CandidateOut):
    cnic_or_passport_no: str
    exam_booking_ref: str | None
    updated_at: datetime


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
    mode: SessionMode = "exam"


class SessionOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    exam_code: str
    mode: SessionMode
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    trust_score: float | None = None

    class Config:
        from_attributes = True


class SessionSummaryOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    candidate_name: str
    exam_code: str
    mode: SessionMode
    status: str
    started_at: datetime
    ended_at: datetime | None
    trust_score: float | None
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
    snapshot_url: str | None  # signed URL; None for client events (no snapshot)

    class Config:
        from_attributes = True


class SessionReportOut(BaseModel):
    """Partner-facing outcome of one session (API key, own organization only)."""
    id: uuid.UUID
    candidate_id: uuid.UUID
    exam_code: str
    mode: SessionMode
    status: str
    started_at: datetime
    ended_at: datetime | None
    trust_score: float | None
    frames_evaluated: int
    violation_counts: dict[str, int]
    violations: list[ViolationOut]


class ClientEventCreate(BaseModel):
    type: Literal["tab_switched", "window_unfocused", "connection_lost"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SessionTokenRequest(BaseModel):
    candidate_id: uuid.UUID
    session_id: uuid.UUID | None = None
    expires_minutes: int | None = Field(default=None, ge=1, le=settings.session_token_max_minutes)


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


class OrganizationUpdate(BaseModel):
    allowed_origin: str | None = None
    webhook_url: str | None = None


class OrganizationCreated(OrganizationOut):
    api_key: str  # raw key — shown exactly once, here, at creation time
    webhook_secret: str  # HMAC key for verifying our webhook signatures — shown once


class WebhookSecretRotated(BaseModel):
    id: uuid.UUID
    webhook_secret: str  # shown exactly once


class ApiKeyRotated(BaseModel):
    id: uuid.UUID
    api_key: str  # raw key — shown exactly once
