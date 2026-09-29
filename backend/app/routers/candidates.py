import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key, require_session_scope, require_session_token
from app.core.config import settings
from app.database import get_db
from app.models import Candidate, ExamSession, Organization
from app.schemas import CandidateCreate, CandidateOut, SessionCreate, SessionOut
from app.services.session_report import finalize_session

router = APIRouter(prefix="/api/v1", tags=["candidates"])


@router.post("/candidates", response_model=CandidateOut, status_code=201)
async def create_candidate(
    payload: CandidateCreate,
    org: Organization = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    # payload.email is already lowercased by the schema; uniqueness is per org.
    existing = await db.execute(
        select(Candidate).where(
            Candidate.organization_id == org.id, func.lower(Candidate.email) == payload.email
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Candidate with this email already exists")

    candidate = Candidate(organization_id=org.id, **payload.model_dump())
    db.add(candidate)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a race with a concurrent create for the same email
        raise HTTPException(409, "Candidate with this email already exists")
    await db.refresh(candidate)
    return candidate


@router.get("/candidates/lookup", response_model=CandidateOut)
async def lookup_candidate(
    email: str = Query(...),
    org: Organization = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Lets your backend resolve a returning candidate by email. Requires your
    API key (server-to-server) — never call this from a browser, since it
    would let anyone who guesses an email pull that candidate's KYC status."""
    result = await db.execute(
        select(Candidate).where(
            func.lower(Candidate.email) == email.lower(), Candidate.organization_id == org.id
        )
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(404, "No candidate found with this email")
    return candidate


def _client_ip(request: Request) -> str | None:
    # The fronting proxy (nginx or Cloudflare Tunnel, see CLIENT_IP_HEADER) sets
    # this header; the app port isn't publicly reachable, so clients can't forge it.
    return request.headers.get(settings.client_ip_header) or (request.client.host if request.client else None)


@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_session(
    payload: SessionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    claims: dict = Depends(require_session_token),
):
    # candidate_id is in the body, not the path, so check the token's scope
    # against it explicitly rather than via a path-based dependency.
    if claims["sub"] != str(payload.candidate_id):
        raise HTTPException(403, "Token does not authorize this candidate")

    candidate = await db.get(Candidate, payload.candidate_id)
    if candidate is None:
        raise HTTPException(404, "Candidate not found")
    if candidate.kyc_status != "verified":
        raise HTTPException(403, "Candidate has not completed KYC verification")

    session = ExamSession(
        candidate_id=payload.candidate_id,
        exam_code=payload.exam_code,
        mode=payload.mode,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
async def end_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_session_scope),
):
    # Row lock (re-read, bypassing the identity map) so concurrent end calls
    # serialize: the second sees the ended status instead of finalizing twice.
    session = await db.get(ExamSession, session_id, with_for_update=True, populate_existing=True)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.status != "active":
        # Idempotent: a retried end call must not recompute the score or re-send the webhook
        return session

    await finalize_session(db, session, "completed")
    return session
