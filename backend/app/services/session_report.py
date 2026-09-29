"""Session outcome: ending a session (trust score, frozen frame count,
session.ended webhook) and the partner-facing report."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import SESSIONS_ENDED
from app.models import Candidate, ExamSession, Organization, SessionFrame, Violation
from app.schemas import SessionReportOut, ViolationOut
from app.services import violation_streaks, webhooks
from app.services.storage import signed_url

CLIENT_EVENT_TYPES = ("tab_switched", "window_unfocused", "connection_lost")
# Each client-reported event (tab switch etc.) costs this many points.
CLIENT_EVENT_PENALTY = 2.0


async def compute_trust_score(db: AsyncSession, session_id: uuid.UUID) -> float | None:
    """0–100: share of evaluated frames that showed no violation, minus a fixed
    penalty per client event. None if no frames were ever evaluated."""
    total, clean = (
        await db.execute(
            select(
                func.count(SessionFrame.id),
                func.count(SessionFrame.id).filter(SessionFrame.violation.is_(None)),
            ).where(SessionFrame.session_id == session_id)
        )
    ).one()
    if not total:
        return None
    client_events = await db.scalar(
        select(func.count(Violation.id)).where(
            Violation.session_id == session_id, Violation.type.in_(CLIENT_EVENT_TYPES)
        )
    )
    score = 100.0 * clean / total - CLIENT_EVENT_PENALTY * client_events
    return round(max(0.0, min(100.0, score)), 1)


def violation_out(v: Violation) -> ViolationOut:
    return ViolationOut(
        id=v.id,
        session_id=v.session_id,
        type=v.type,
        confidence=v.confidence,
        detected_at=v.detected_at,
        review_status=v.review_status,
        snapshot_url=signed_url(v.snapshot_s3_key) if v.snapshot_s3_key != "none" else None,
    )


async def build_report(db: AsyncSession, session: ExamSession) -> SessionReportOut:
    violations = (
        await db.execute(
            select(Violation).where(Violation.session_id == session.id).order_by(Violation.detected_at)
        )
    ).scalars().all()
    frames = session.frames_evaluated
    if frames is None:  # still active — count live rows
        frames = await db.scalar(select(func.count(SessionFrame.id)).where(SessionFrame.session_id == session.id))

    counts: dict[str, int] = {}
    for v in violations:
        counts[v.type] = counts.get(v.type, 0) + 1

    return SessionReportOut(
        id=session.id,
        candidate_id=session.candidate_id,
        exam_code=session.exam_code,
        mode=session.mode,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        trust_score=session.trust_score,
        frames_evaluated=frames or 0,
        violation_counts=counts,
        violations=[violation_out(v) for v in violations],
    )


async def finalize_session(
    db: AsyncSession, session: ExamSession, status: str, ended_at: datetime | None = None
) -> None:
    """End an active session as `status` ("completed" by the learner,
    "terminated" by the partner, "abandoned" by the idle sweeper): score it,
    freeze the frame count, queue the session.ended webhook, commit."""
    session.status = status
    session.ended_at = ended_at or datetime.now(timezone.utc)
    session.frames_evaluated = await db.scalar(
        select(func.count(SessionFrame.id)).where(SessionFrame.session_id == session.id)
    )
    session.trust_score = await compute_trust_score(db, session.id)

    candidate = await db.get(Candidate, session.candidate_id)
    org = await db.get(Organization, candidate.organization_id)
    webhooks.enqueue(db, org, "session.ended", await build_report(db, session))
    await db.commit()
    await db.refresh(session)
    await violation_streaks.reset(session.id)
    SESSIONS_ENDED.labels(status).inc()
