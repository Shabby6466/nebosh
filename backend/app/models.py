import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String)
    cnic_or_passport_no: Mapped[str] = mapped_column(String, nullable=False)
    exam_booking_ref: Mapped[str | None] = mapped_column(String)
    kyc_status: Mapped[str] = mapped_column(
        Enum("pending", "verified", "rejected", "expired", name="kyc_status"), default="pending"
    )
    id_document_s3_key: Mapped[str | None] = mapped_column(String)
    selfie_s3_key: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    embeddings: Mapped[list["FaceEmbedding"]] = relationship(back_populates="candidate")
    sessions: Mapped[list["ExamSession"]] = relationship(back_populates="candidate")


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    embedding = mapped_column(Vector(512), nullable=False)
    match_score: Mapped[float | None] = mapped_column(Float)
    liveness_score: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String, default="arcface-buffalo_l-v1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    candidate: Mapped["Candidate"] = relationship(back_populates="embeddings")


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    exam_code: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("active", "completed", "terminated", "abandoned", name="session_status"), default="active"
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trust_score: Mapped[float | None] = mapped_column(Float)
    client_ip: Mapped[str | None] = mapped_column(String)
    user_agent: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped["Candidate"] = relationship(back_populates="sessions")
    violations: Mapped[list["Violation"]] = relationship(back_populates="session")


class SessionFrame(Base):
    __tablename__ = "session_frames"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exam_sessions.id", ondelete="CASCADE"))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    person_count: Mapped[int | None] = mapped_column(SmallInteger)
    face_match: Mapped[bool | None] = mapped_column(Boolean)
    face_similarity: Mapped[float | None] = mapped_column(Float)
    liveness_pass: Mapped[bool | None] = mapped_column(Boolean)
    processing_ms: Mapped[int | None] = mapped_column(Integer)


class Violation(Base):
    __tablename__ = "violations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exam_sessions.id", ondelete="CASCADE"))
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(
        Enum(
            "candidate_missing",
            "multiple_people",
            "face_mismatch",
            "liveness_failed",
            "connection_lost",
            name="violation_type",
        )
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    snapshot_s3_key: Mapped[str] = mapped_column(String, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    review_status: Mapped[str] = mapped_column(
        Enum("unreviewed", "confirmed", "false_positive", name="review_status"), default="unreviewed"
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("admins.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)

    session: Mapped["ExamSession"] = relationship(back_populates="violations")


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(
        Enum("reviewer", "compliance_officer", "admin", name="admin_role"), default="reviewer"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
