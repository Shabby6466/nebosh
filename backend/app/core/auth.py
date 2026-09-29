"""Auth primitives for the API.

Two trust levels, matching the integration model documented for LMS clients:

  1. API key (Organization-scoped) — server-to-server only. Sent as
     `X-API-Key`. Used to create candidates and to mint session tokens.
     Never meant to reach a browser.

  2. Session token (short-lived JWT) — minted by us via `/api/v1/auth/token`
     from an API key, scoped to one candidate (and optionally one session).
     This is what a browser or a Zoom-capture script actually sends as
     `Authorization: Bearer <token>` for uploads/WS frames.

A third, separate token type authenticates admin/reviewer users (email +
password login) for the compliance dashboard endpoints.
"""

import hashlib
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import redis_client
from app.database import get_db
from app.models import Admin, ExamSession, Organization

_bearer = HTTPBearer(auto_error=False)

# Using the `bcrypt` package directly rather than passlib[bcrypt]: passlib
# 1.7.4 (last released 2020) probes for a `bcrypt.__about__` attribute that
# bcrypt>=4.1 removed, so the two don't work together as pinned.

SESSION_TOKEN_SCOPE = "session"
ADMIN_TOKEN_SCOPE = "admin"


# ---------------------------------------------------------------------------
# API keys (Organization <-> raw key)
# ---------------------------------------------------------------------------

def generate_api_key(vendor_name: str | None = None) -> str:
    # vendor_name is cosmetic only (helps an operator eyeball which key
    # belongs to whom in a list) — the actual secret is the random suffix.
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", vendor_name).strip("-").lower() if vendor_name else ""
    prefix = f"{slug}_" if slug else "nb_live_"
    return f"{prefix}{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    # API keys are high-entropy random tokens (not user-chosen passwords), so a
    # fast, salt-free digest is fine here and lets lookup happen by equality
    # rather than needing to re-check against every stored hash.
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def require_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    result = await db.execute(
        select(Organization).where(
            Organization.api_key_hash == hash_api_key(x_api_key),
            Organization.is_active.is_(True),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(401, "Invalid or inactive API key")
    await _enforce_api_key_rate_limit(org.id)
    return org


async def _enforce_api_key_rate_limit(organization_id: uuid.UUID) -> None:
    """Fixed 1-minute window per organization, shared across workers via Redis.
    Keyed on the org rather than the caller's IP: a partner's backend is one IP
    making calls for all its learners, which a per-IP limit would throttle."""
    now = time.time()
    key = f"ratelimit:apikey:{organization_id}:{int(now // 60)}"
    async with redis_client.pipeline(transaction=True) as pipe:
        count, _ = await pipe.incr(key).expire(key, 120).execute()
    if count > settings.api_key_rate_limit_per_minute:
        raise HTTPException(
            429, "API key rate limit exceeded", headers={"Retry-After": str(60 - int(now) % 60)}
        )


# ---------------------------------------------------------------------------
# Session tokens (short-lived JWT, scoped to one candidate/session)
# ---------------------------------------------------------------------------

def create_session_token(
    *,
    organization_id: uuid.UUID,
    candidate_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
    expires_minutes: int | None = None,
) -> tuple[str, int]:
    expires_minutes = expires_minutes or settings.jwt_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "scope": SESSION_TOKEN_SCOPE,
        "org": str(organization_id),
        "sub": str(candidate_id),
        "sid": str(session_id) if session_id else None,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_minutes * 60


def _decode_token(credentials: HTTPAuthorizationCredentials | None) -> dict:
    if credentials is None:
        raise HTTPException(401, "Missing bearer token")
    try:
        return jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")


async def require_session_token(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    claims = _decode_token(creds)
    if claims.get("scope") != SESSION_TOKEN_SCOPE:
        raise HTTPException(403, "Wrong token type for this endpoint")
    return claims


def require_candidate_scope(candidate_id: uuid.UUID, claims: dict = Depends(require_session_token)) -> dict:
    """Use as a route dependency alongside a `candidate_id` path param — FastAPI
    resolves `candidate_id` from the request the same way it does for the
    endpoint itself, so this only needs declaring, not passing explicitly."""
    if claims["sub"] != str(candidate_id):
        raise HTTPException(403, "Token does not authorize this candidate")
    return claims


async def require_session_scope(
    session_id: uuid.UUID,
    claims: dict = Depends(require_session_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Checks against the session's actual candidate in the DB, not just the
    token's optional `sid` claim. A token minted without a `session_id` (the
    normal case before a session exists — see /auth/token) carries `sid: null`
    and must NOT be treated as authorizing every session; only checking `sid`
    when present let such a token be replayed against any session_id at all.
    This mirrors the ownership check the WS endpoint already does."""
    session = await db.get(ExamSession, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if claims["sub"] != str(session.candidate_id):
        raise HTTPException(403, "Token does not authorize this session")
    if claims.get("sid") and claims["sid"] != str(session_id):
        raise HTTPException(403, "Token does not authorize this session")
    return claims


def decode_ws_token(token: str) -> dict:
    """Same as require_session_token, for the WebSocket path where a bearer
    header isn't practical — the token is passed as a query param instead."""
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")
    if claims.get("scope") != SESSION_TOKEN_SCOPE:
        raise HTTPException(403, "Wrong token type")
    return claims


# ---------------------------------------------------------------------------
# Admin auth (email/password login -> JWT with a role claim)
# ---------------------------------------------------------------------------

def hash_password(raw_password: str) -> str:
    return bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(raw_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_admin_token(admin: Admin, expires_minutes: int | None = None) -> tuple[str, int]:
    expires_minutes = expires_minutes or settings.jwt_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "scope": ADMIN_TOKEN_SCOPE,
        "sub": str(admin.id),
        "role": admin.role,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_minutes * 60


def require_admin(*allowed_roles: str):
    """Dependency factory: `Depends(require_admin())` for any admin,
    `Depends(require_admin("admin"))` to restrict to specific roles."""

    async def _dep(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
        claims = _decode_token(creds)
        if claims.get("scope") != ADMIN_TOKEN_SCOPE:
            raise HTTPException(403, "Wrong token type for this endpoint")
        if allowed_roles and claims.get("role") not in allowed_roles:
            raise HTTPException(403, "Insufficient role for this endpoint")
        return claims

    return _dep