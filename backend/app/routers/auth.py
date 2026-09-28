from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_admin_token, create_session_token, require_api_key, verify_password
from app.database import get_db
from app.models import Admin, Candidate, Organization
from app.schemas import AdminLogin, SessionTokenRequest, TokenOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token", response_model=TokenOut)
async def issue_session_token(
    payload: SessionTokenRequest,
    org: Organization = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Server-to-server: exchange an API key for a short-lived token scoped to
    one candidate (and optionally one session). This is the only credential
    that should ever reach a browser or a Zoom-capture script."""
    candidate = await db.get(Candidate, payload.candidate_id)
    if candidate is None or candidate.organization_id != org.id:
        raise HTTPException(404, "Candidate not found for this organization")

    access_token, expires_in = create_session_token(
        organization_id=org.id,
        candidate_id=candidate.id,
        session_id=payload.session_id,
        expires_minutes=payload.expires_minutes,
    )
    return TokenOut(access_token=access_token, expires_in=expires_in)


@router.post("/admin/login", response_model=TokenOut)
async def admin_login(payload: AdminLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Admin).where(Admin.email == payload.email))
    admin = result.scalar_one_or_none()
    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(401, "Invalid email or password")

    access_token, expires_in = create_admin_token(admin)
    return TokenOut(access_token=access_token, expires_in=expires_in)
