"""Results for integrating partners (LMS backends), authenticated by API key
and scoped to the caller's own organization. Anything belonging to another
organization is reported as 404, not 403, so IDs can't be probed across tenants.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.database import get_db
from app.models import Candidate, ExamSession, Organization
from app.schemas import CandidateDetailOut, SessionOut, SessionReportOut
from app.services.session_report import build_report, finalize_session

router = APIRouter(prefix="/api/v1", tags=["partner results"])


async def _own_candidate(db: AsyncSession, org: Organization, candidate_id: uuid.UUID) -> Candidate:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None or candidate.organization_id != org.id:
        raise HTTPException(404, "Candidate not found")
    return candidate


@router.get("/candidates/{candidate_id}", response_model=CandidateDetailOut)
async def get_candidate(
    candidate_id: uuid.UUID,
    org: Organization = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await _own_candidate(db, org, candidate_id)


@router.get("/candidates/{candidate_id}/sessions", response_model=list[SessionOut])
async def list_candidate_sessions(
    candidate_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    org: Organization = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    await _own_candidate(db, org, candidate_id)
    result = await db.execute(
        select(ExamSession)
        .where(ExamSession.candidate_id == candidate_id)
        .order_by(ExamSession.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/sessions/{session_id}/report", response_model=SessionReportOut)
async def session_report(
    session_id: uuid.UUID,
    org: Organization = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Trust score, violation counts and every violation with a signed snapshot
    URL (valid 1 hour — fetch the report again for fresh links)."""
    session = await db.get(ExamSession, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    await _own_candidate(db, org, session.candidate_id)
    return await build_report(db, session)


@router.post("/sessions/{session_id}/terminate", response_model=SessionOut)
async def terminate_session(
    session_id: uuid.UUID,
    org: Organization = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Server-side end, e.g. when the trainer closes the viva or the LMS
    cancels an attempt — doesn't depend on the learner's browser still being
    open. Ends as "terminated", scores it and sends session.ended. Idempotent."""
    session = await db.get(ExamSession, session_id, with_for_update=True, populate_existing=True)
    if session is None:
        raise HTTPException(404, "Session not found")
    await _own_candidate(db, org, session.candidate_id)
    if session.status == "active":
        await finalize_session(db, session, "terminated")
    return session
