"""Background loops started by every API worker (see app.main lifespan).

- Webhook outbox delivery: many workers share the queue via SKIP LOCKED.
- Maintenance (idle-session sweep + retention): once a minute, run by
  whichever worker grabs a Postgres advisory lock — the others skip that tick.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text

from app.core.config import settings
from app.database import SessionLocal
from app.models import ExamSession, SessionFrame, Violation, WebhookDelivery
from app.services import webhooks
from app.services.session_report import finalize_session

log = logging.getLogger(__name__)

_WEBHOOK_IDLE_POLL_S = 2
_MAINTENANCE_INTERVAL_S = 60
# Arbitrary app-wide key for pg_try_advisory_xact_lock
_MAINTENANCE_LOCK_KEY = 0x6E65626F  # "nebo"
_RETENTION_BATCH = 10_000


async def _webhook_loop() -> None:
    while True:
        try:
            sent = await webhooks.deliver_due()
        except Exception:
            log.exception("webhook delivery loop error")
            sent = 0
        if not sent:
            await asyncio.sleep(_WEBHOOK_IDLE_POLL_S)


async def abandon_idle_sessions() -> int:
    """Mark active sessions with no frame/event for the idle timeout as
    "abandoned" (closed tab, crashed browser, lost network). Scored and
    reported via session.ended like any other end."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.session_idle_timeout_minutes)
    last_frame = (
        select(func.max(SessionFrame.captured_at))
        .where(SessionFrame.session_id == ExamSession.id)
        .scalar_subquery()
    )
    last_event = (
        select(func.max(Violation.detected_at))
        .where(Violation.session_id == ExamSession.id)
        .scalar_subquery()
    )
    last_activity = func.greatest(ExamSession.started_at, last_frame, last_event)

    count = 0
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(ExamSession.id, last_activity)
                .where(ExamSession.status == "active", last_activity < cutoff)
                .limit(100)
            )
        ).all()
        for session_id, last_seen in rows:
            # Lock + recheck per row: the learner or partner may be ending it right now
            session = await db.get(ExamSession, session_id, with_for_update=True, populate_existing=True)
            if session is None or session.status != "active":
                await db.rollback()
                continue
            await finalize_session(db, session, "abandoned", ended_at=last_seen)
            count += 1
    return count


async def purge_expired_rows() -> tuple[int, int]:
    """Delete per-frame metadata and delivered/failed webhooks past retention.
    Batched so a large backlog doesn't hold one long transaction."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.session_frames_retention_days)
    frames = hooks = 0
    async with SessionLocal() as db:
        while True:
            batch = select(SessionFrame.id).where(SessionFrame.captured_at < cutoff).limit(_RETENTION_BATCH)
            n = (await db.execute(delete(SessionFrame).where(SessionFrame.id.in_(batch)))).rowcount
            await db.commit()
            frames += n
            if n < _RETENTION_BATCH:
                break
        hooks = (
            await db.execute(
                delete(WebhookDelivery).where(
                    WebhookDelivery.status != "pending", WebhookDelivery.created_at < cutoff
                )
            )
        ).rowcount
        await db.commit()
    return frames, hooks


async def run_maintenance_once() -> bool:
    """Returns False if another worker held the lock and this tick was skipped."""
    async with SessionLocal() as db:
        # Transaction-scoped lock held while this worker runs the tick. The
        # sweep and purge use their own sessions; this one just holds the lock.
        got = await db.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _MAINTENANCE_LOCK_KEY})
        if not got:
            return False
        abandoned = await abandon_idle_sessions()
        frames, hooks = await purge_expired_rows()
        if abandoned or frames or hooks:
            log.info("maintenance: abandoned=%d frames_purged=%d webhooks_purged=%d", abandoned, frames, hooks)
        await db.commit()
    return True


async def _maintenance_loop() -> None:
    while True:
        try:
            await run_maintenance_once()
        except Exception:
            log.exception("maintenance loop error")
        await asyncio.sleep(_MAINTENANCE_INTERVAL_S)


def start() -> list[asyncio.Task]:
    return [asyncio.create_task(_webhook_loop()), asyncio.create_task(_maintenance_loop())]


async def stop(tasks: list[asyncio.Task]) -> None:
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
