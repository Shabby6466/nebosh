import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func

from app.database import get_db
from app.models import Candidate, ExamSession, Violation
from app.schemas import CandidateOut, SessionSummaryOut, ViolationOut
from app.services.storage import signed_url

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# NOTE: add auth dependency (JWT + role check) to every route in this router
# before deploying — omitted here for brevity, see docs/auth.md


@router.get("/candidates", response_model=list[CandidateOut])
async def list_candidates(
    kyc_status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Candidate)
    if kyc_status:
        stmt = stmt.where(Candidate.kyc_status == kyc_status)
    result = await db.execute(stmt.order_by(Candidate.created_at.desc()))
    return result.scalars().all()


@router.get("/sessions", response_model=list[SessionSummaryOut])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    violation_counts = (
        select(Violation.session_id, func.count(Violation.id).label("count"))
        .group_by(Violation.session_id)
        .subquery()
    )
    stmt = (
        select(ExamSession, Candidate.full_name, func.coalesce(violation_counts.c.count, 0))
        .join(Candidate, Candidate.id == ExamSession.candidate_id)
        .outerjoin(violation_counts, violation_counts.c.session_id == ExamSession.id)
        .order_by(ExamSession.started_at.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    return [
        SessionSummaryOut(
            id=session.id,
            candidate_id=session.candidate_id,
            candidate_name=candidate_name,
            exam_code=session.exam_code,
            status=session.status,
            started_at=session.started_at,
            ended_at=session.ended_at,
            violation_count=violation_count,
        )
        for session, candidate_name, violation_count in result.all()
    ]


@router.get("/sessions/{session_id}/violations", response_model=list[ViolationOut])
async def session_violations(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Violation).where(Violation.session_id == session_id).order_by(Violation.detected_at)
    )
    violations = result.scalars().all()
    return [
        ViolationOut(
            id=v.id,
            session_id=v.session_id,
            type=v.type,
            confidence=v.confidence,
            detected_at=v.detected_at,
            review_status=v.review_status,
            snapshot_url=signed_url(v.snapshot_s3_key),
        )
        for v in violations
    ]


@router.post("/violations/{violation_id}/review")
async def review_violation(
    violation_id: uuid.UUID,
    review_status: str,
    notes: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if review_status not in ("confirmed", "false_positive"):
        raise HTTPException(400, "review_status must be 'confirmed' or 'false_positive'")

    violation = await db.get(Violation, violation_id)
    if violation is None:
        raise HTTPException(404, "Violation not found")

    violation.review_status = review_status
    violation.review_notes = notes
    violation.reviewed_at = datetime.utcnow()
    await db.commit()
    return {"id": violation_id, "review_status": review_status}
