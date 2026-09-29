"""Vendor (LMS tenant) management — issuing, revoking and rotating the API
keys that back the Organization model, plus basic usage reporting per key.

Restricted to the `admin` role specifically (not reviewer/compliance_officer)
since these actions hand out or revoke production credentials.
"""

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import generate_api_key, hash_api_key, require_admin
from app.database import get_db
from app.models import Candidate, ExamSession, Organization, Violation
from app.schemas import (
    ApiKeyRotated,
    OrganizationCreate,
    OrganizationCreated,
    OrganizationOut,
    OrganizationUpdate,
    WebhookSecretRotated,
)

router = APIRouter(
    prefix="/api/v1/admin/organizations",
    tags=["vendors"],
    dependencies=[Depends(require_admin("admin"))],
)


async def _with_usage(db: AsyncSession, org: Organization) -> OrganizationOut:
    """Usage is derived from existing candidate/session/violation rows rather
    than a per-request counter, so reads carry zero extra write load — the
    thing that matters for the API's own scaling (see architecture notes)."""
    stmt = (
        select(
            func.count(func.distinct(Candidate.id)),
            func.count(func.distinct(ExamSession.id)),
            func.count(func.distinct(Violation.id)),
            func.max(Candidate.created_at),
        )
        .select_from(Candidate)
        .outerjoin(ExamSession, ExamSession.candidate_id == Candidate.id)
        .outerjoin(Violation, Violation.candidate_id == Candidate.id)
        .where(Candidate.organization_id == org.id)
    )
    candidate_count, session_count, violation_count, last_active_at = (await db.execute(stmt)).one()
    return OrganizationOut(
        id=org.id,
        name=org.name,
        allowed_origin=org.allowed_origin,
        webhook_url=org.webhook_url,
        is_active=org.is_active,
        created_at=org.created_at,
        last_active_at=last_active_at,
        candidate_count=candidate_count,
        session_count=session_count,
        violation_count=violation_count,
    )


@router.get("", response_model=list[OrganizationOut])
async def list_organizations(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    orgs = (
        await db.execute(
            select(Organization).order_by(Organization.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return [await _with_usage(db, org) for org in orgs]


@router.post("", response_model=OrganizationCreated, status_code=201)
async def create_organization(payload: OrganizationCreate, db: AsyncSession = Depends(get_db)):
    raw_key = generate_api_key(payload.name)
    webhook_secret = _generate_webhook_secret()
    org = Organization(
        name=payload.name,
        api_key_hash=hash_api_key(raw_key),
        allowed_origin=payload.allowed_origin,
        webhook_url=payload.webhook_url,
        webhook_secret=webhook_secret,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)

    out = await _with_usage(db, org)
    return OrganizationCreated(**out.model_dump(), api_key=raw_key, webhook_secret=webhook_secret)


def _generate_webhook_secret() -> str:
    # Stored in plaintext (unlike API keys): we need the raw value to sign with.
    return f"whsec_{secrets.token_urlsafe(32)}"


async def _get_org(db: AsyncSession, organization_id: uuid.UUID) -> Organization:
    org = await db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    return org


@router.patch("/{organization_id}", response_model=OrganizationOut)
async def update_organization(
    organization_id: uuid.UUID, payload: OrganizationUpdate, db: AsyncSession = Depends(get_db)
):
    """Set or change the webhook URL / allowed origin. Only fields present in
    the body are changed; send `null` to clear one."""
    org = await _get_org(db, organization_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return await _with_usage(db, org)


@router.post("/{organization_id}/rotate-webhook-secret", response_model=WebhookSecretRotated)
async def rotate_webhook_secret(organization_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """New signing secret takes effect for the next webhook sent — the partner
    must switch their verification over at the same time."""
    org = await _get_org(db, organization_id)
    org.webhook_secret = _generate_webhook_secret()
    await db.commit()
    return WebhookSecretRotated(id=org.id, webhook_secret=org.webhook_secret)


@router.post("/{organization_id}/revoke", response_model=OrganizationOut)
async def revoke_organization(organization_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    org = await db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    org.is_active = False
    await db.commit()
    await db.refresh(org)
    return await _with_usage(db, org)


@router.post("/{organization_id}/reactivate", response_model=OrganizationOut)
async def reactivate_organization(organization_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    org = await db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    org.is_active = True
    await db.commit()
    await db.refresh(org)
    return await _with_usage(db, org)


@router.post("/{organization_id}/rotate-key", response_model=ApiKeyRotated)
async def rotate_key(organization_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Issues a new key and immediately invalidates the old one — any client
    still using the previous key starts getting 401s right after this call."""
    org = await db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    raw_key = generate_api_key(org.name)
    org.api_key_hash = hash_api_key(raw_key)
    await db.commit()
    return ApiKeyRotated(id=org.id, api_key=raw_key)
