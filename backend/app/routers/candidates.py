import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Candidate, ExamSession
from app.schemas import CandidateCreate, CandidateOut, SessionCreate, SessionOut

router = APIRouter(prefix="/api/v1", tags=["candidates"])


@router.post("/candidates", response_model=CandidateOut, status_code=201)
async def create_candidate(payload: CandidateCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Candidate).where(Candidate.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Candidate with this email already exists")

    candidate = Candidate(**payload.model_dump())
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return candidate


@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_session(payload: SessionCreate, db: AsyncSession = Depends(get_db)):
    candidate = await db.get(Candidate, payload.candidate_id)
    if candidate is None:
        raise HTTPException(404, "Candidate not found")
    if candidate.kyc_status != "verified":
        raise HTTPException(403, "Candidate has not completed KYC verification")

    session = ExamSession(candidate_id=payload.candidate_id, exam_code=payload.exam_code)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
async def end_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    session = await db.get(ExamSession, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    session.status = "completed"
    session.ended_at = datetime.utcnow()
    await db.commit()
    await db.refresh(session)
    return session
