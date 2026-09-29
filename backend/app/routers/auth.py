from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_admin_token, create_session_token, require_api_key, verify_password
from app.core.config import settings
from app.core.redis import redis_client
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


# The admin panel is publicly reachable, so failed logins are throttled both
# per client IP (one attacker, many accounts) and per email (many IPs, one account).
_LOGIN_MAX_FAILURES = 10
_LOGIN_WINDOW_S = 15 * 60


@router.post("/admin/login", response_model=TokenOut)
async def admin_login(payload: AdminLogin, request: Request, db: AsyncSession = Depends(get_db)):
    ip = request.headers.get(settings.client_ip_header) or (request.client.host if request.client else "?")
    keys = [f"admin_login_failed:ip:{ip}", f"admin_login_failed:email:{payload.email.lower()}"]
    counts = await redis_client.mget(keys)
    if any(int(c or 0) >= _LOGIN_MAX_FAILURES for c in counts):
        raise HTTPException(429, "Too many failed sign-in attempts. Try again in 15 minutes.")

    result = await db.execute(select(Admin).where(Admin.email == payload.email))
    admin = result.scalar_one_or_none()
    if admin is None or not verify_password(payload.password, admin.password_hash):
        async with redis_client.pipeline(transaction=True) as pipe:
            for k in keys:
                pipe.incr(k).expire(k, _LOGIN_WINDOW_S)
            await pipe.execute()
        raise HTTPException(401, "Invalid email or password")

    await redis_client.delete(*keys)
    access_token, expires_in = create_admin_token(admin)
    return TokenOut(access_token=access_token, expires_in=expires_in)
