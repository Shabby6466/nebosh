"""Vendor (LMS tenant) management — issuing, revoking and rotating the API
keys that back the Organization model, plus basic usage reporting per key.

Restricted to the `admin` role specifically (not reviewer/compliance_officer)
since these actions hand out or revoke production credentials.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import generate_api_key, hash_api_key, require_admin
from app.database import get_db
from app.models import Candidate, ExamSession, Organization, Violation
from app.schemas import ApiKeyRotated, OrganizationCreate, OrganizationCreated, OrganizationOut

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
async def list_organizations(db: AsyncSession = Depends(get_db)):
    orgs = (await db.execute(select(Organization).order_by(Organization.created_at.desc()))).scalars().all()
    return [await _with_usage(db, org) for org in orgs]


@router.post("", response_model=OrganizationCreated, status_code=201)
async def create_organization(payload: OrganizationCreate, db: AsyncSession = Depends(get_db)):
    raw_key = generate_api_key(payload.name)
    org = Organization(
        name=payload.name,
        api_key_hash=hash_api_key(raw_key),
        allowed_origin=payload.allowed_origin,
        webhook_url=payload.webhook_url,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)

    out = await _with_usage(db, org)
    return OrganizationCreated(**out.model_dump(), api_key=raw_key)


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
