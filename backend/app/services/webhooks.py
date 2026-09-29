"""Signed webhook delivery to an organization's `webhook_url`, via an outbox.

`enqueue()` adds a `webhook_deliveries` row in the caller's DB transaction, so
the event is recorded if and only if the change it reports is committed.
`deliver_due()` (driven by services.background in every API worker) sends due
rows; `FOR UPDATE SKIP LOCKED` lets many workers share the queue without
double-sending. Rows survive restarts, so nothing is lost on a deploy.

Every POST carries:
    X-Webhook-Id         unique per event (dedupe on this — retries reuse it)
    X-Webhook-Event      e.g. "kyc.completed", "session.ended"
    X-Webhook-Timestamp  unix seconds
    X-Webhook-Signature  "sha256=" + hex HMAC-SHA256(webhook_secret, f"{timestamp}.{body}")

Delivery is at-least-once; partners should dedupe on X-Webhook-Id and treat
the GET endpoints as the source of truth.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import WEBHOOKS
from app.database import SessionLocal
from app.models import Organization, WebhookDelivery

log = logging.getLogger(__name__)

_BATCH_SIZE = 20
_MAX_BACKOFF_S = 6 * 3600


def sign(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def enqueue(db: AsyncSession, org: Organization, event: str, data) -> None:
    """Queue `event` for `org` in the current transaction (caller commits).
    No-op if the org has no webhook configured."""
    if not org.webhook_url or not org.webhook_secret:
        return
    event_id = uuid.uuid4()
    db.add(
        WebhookDelivery(
            id=event_id,
            organization_id=org.id,
            event=event,
            payload={
                "id": str(event_id),
                "event": event,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "data": jsonable_encoder(data),
            },
        )
    )


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * 4 ** (attempts - 1), _MAX_BACKOFF_S))


async def _attempt(client: httpx.AsyncClient, delivery: WebhookDelivery, org: Organization) -> None:
    now = datetime.now(timezone.utc)
    delivery.attempts += 1
    error = None
    if not org.webhook_url or not org.webhook_secret:
        error = "webhook no longer configured for this organization"
    else:
        body = json.dumps(delivery.payload).encode()
        timestamp = str(int(time.time()))
        try:
            resp = await client.post(
                org.webhook_url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Id": str(delivery.id),
                    "X-Webhook-Event": delivery.event,
                    "X-Webhook-Timestamp": timestamp,
                    "X-Webhook-Signature": sign(org.webhook_secret, timestamp, body),
                },
            )
            if not resp.is_success:
                error = f"HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            error = repr(exc)

    if error is None:
        delivery.status = "delivered"
        delivery.delivered_at = now
        delivery.last_error = None
        WEBHOOKS.labels("delivered").inc()
        return

    delivery.last_error = error[:1000]
    if delivery.attempts >= settings.webhook_max_attempts:
        delivery.status = "failed"
        WEBHOOKS.labels("failed").inc()
        log.error("webhook %s %s failed permanently: %s", delivery.event, delivery.id, error)
    else:
        delivery.next_attempt_at = now + _backoff(delivery.attempts)
        WEBHOOKS.labels("retry").inc()
        log.warning("webhook %s %s attempt %d: %s", delivery.event, delivery.id, delivery.attempts, error)


async def deliver_due() -> int:
    """Send one batch of due deliveries; returns how many were attempted."""
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(WebhookDelivery, Organization)
                .join(Organization, Organization.id == WebhookDelivery.organization_id)
                .where(
                    WebhookDelivery.status == "pending",
                    WebhookDelivery.next_attempt_at <= datetime.now(timezone.utc),
                )
                .order_by(WebhookDelivery.next_attempt_at)
                .limit(_BATCH_SIZE)
                .with_for_update(skip_locked=True, of=WebhookDelivery)
            )
        ).all()
        if not rows:
            return 0
        async with httpx.AsyncClient(timeout=settings.webhook_timeout_s) as client:
            await asyncio.gather(*(_attempt(client, d, org) for d, org in rows))
        await db.commit()
        return len(rows)
