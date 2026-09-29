"""Ending sessions (learner / partner / idle sweeper), trust score, webhook
outbox delivery + retries, retention."""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

from app.services import background
from conftest import JPEG, deliver_webhooks, run, send_frames, sql, start_session


def _events(sink):
    return [json.loads(r.content)["event"] for r in sink.requests]


def test_end_scores_and_sends_signed_webhook_once(client, learner, frame_stub, sink):
    org, cand, headers = learner
    deliver_webhooks(client); sink.requests.clear()  # drop kyc.completed
    s = start_session(client, cand, headers)
    frame_stub.violation = None
    send_frames(client, s["id"], headers, 3)
    frame_stub.violation = "candidate_missing"
    send_frames(client, s["id"], headers, 1)
    client.post(f"/api/v1/sessions/{s['id']}/events", json={"type": "tab_switched"}, headers=headers)

    ended = client.post(f"/api/v1/sessions/{s['id']}/end", headers=headers).json()
    assert ended["status"] == "completed"
    assert ended["trust_score"] == 73.0  # 3/4 clean frames = 75, minus 2 for one tab switch
    again = client.post(f"/api/v1/sessions/{s['id']}/end", headers=headers).json()
    assert again["trust_score"] == 73.0

    assert deliver_webhooks(client) == 1
    req = sink.requests[0]
    body = json.loads(req.content)
    assert body["event"] == "session.ended" and body["data"]["frames_evaluated"] == 4
    expected = "sha256=" + hmac.new(
        org["webhook_secret"].encode(), f"{req.headers['x-webhook-timestamp']}.".encode() + req.content, hashlib.sha256
    ).hexdigest()
    assert req.headers["x-webhook-signature"] == expected
    assert req.headers["x-webhook-id"] == body["id"]
    assert deliver_webhooks(client) == 0


def test_partner_terminate(client, learner, sink):
    org, cand, headers = learner
    s = start_session(client, cand, headers)
    resp = client.post(f"/api/v1/sessions/{s['id']}/terminate", headers=org["headers"])
    assert resp.status_code == 200 and resp.json()["status"] == "terminated"
    assert resp.json()["trust_score"] is None  # no frames evaluated
    client.post(f"/api/v1/sessions/{s['id']}/terminate", headers=org["headers"])  # idempotent
    deliver_webhooks(client)
    assert _events(sink).count("session.ended") == 1


def test_webhook_retries_with_backoff_then_succeeds(client, learner, sink):
    org, cand, headers = learner
    sink.status = 500
    assert deliver_webhooks(client) == 1  # kyc.completed, fails
    row = sql("SELECT status, attempts, next_attempt_at, last_error FROM webhook_deliveries "
              "WHERE organization_id = $1", uuid.UUID(org["id"]))[0]
    assert row["status"] == "pending" and row["attempts"] == 1 and row["last_error"] == "HTTP 500"
    assert row["next_attempt_at"] > datetime.now(timezone.utc) + timedelta(seconds=20)
    assert deliver_webhooks(client) == 0  # not due yet

    sql("UPDATE webhook_deliveries SET next_attempt_at = now() WHERE status = 'pending'")
    sink.status = 200
    assert deliver_webhooks(client) == 1
    assert sql("SELECT status FROM webhook_deliveries WHERE organization_id = $1",
               uuid.UUID(org["id"]))[0]["status"] == "delivered"


def test_webhook_gives_up_after_max_attempts(client, learner, sink, monkeypatch):
    from app.core.config import settings

    org, _, _ = learner
    monkeypatch.setattr(settings, "webhook_max_attempts", 2)
    sink.status = 503
    deliver_webhooks(client)
    sql("UPDATE webhook_deliveries SET next_attempt_at = now() WHERE status = 'pending'")
    deliver_webhooks(client)
    row = sql("SELECT status, attempts FROM webhook_deliveries WHERE organization_id = $1", uuid.UUID(org["id"]))[0]
    assert (row["status"], row["attempts"]) == ("failed", 2)


def test_idle_sessions_abandoned_active_ones_kept(client, learner, sink):
    org, cand, headers = learner
    idle = start_session(client, cand, headers)
    busy = start_session(client, cand, headers)
    send_frames(client, busy["id"], headers, 1)
    sql("UPDATE exam_sessions SET started_at = now() - interval '2 hours' WHERE id = ANY($1::uuid[])",
        [uuid.UUID(idle["id"]), uuid.UUID(busy["id"])])

    assert run(client, background.run_maintenance_once) is True
    statuses = {r["id"]: r["status"] for r in sql(
        "SELECT id::text, status::text FROM exam_sessions WHERE id = ANY($1::uuid[])",
        [uuid.UUID(idle["id"]), uuid.UUID(busy["id"])])}
    assert statuses == {idle["id"]: "abandoned", busy["id"]: "active"}  # busy had a recent frame
    deliver_webhooks(client)
    ended = [json.loads(r.content) for r in sink.requests if json.loads(r.content)["event"] == "session.ended"]
    assert [e["data"]["status"] for e in ended] == ["abandoned"]


def test_retention_purges_old_frames_but_report_keeps_count(client, learner):
    org, cand, headers = learner
    s = start_session(client, cand, headers)
    send_frames(client, s["id"], headers, 3)
    client.post(f"/api/v1/sessions/{s['id']}/end", headers=headers)
    sql("UPDATE session_frames SET captured_at = now() - interval '400 days' WHERE session_id = $1", uuid.UUID(s["id"]))

    run(client, background.run_maintenance_once)
    assert sql("SELECT count(*) FROM session_frames WHERE session_id = $1", uuid.UUID(s["id"]))[0][0] == 0
    rep = client.get(f"/api/v1/sessions/{s['id']}/report", headers=org["headers"]).json()
    assert rep["frames_evaluated"] == 3


def test_maintenance_lock_is_exclusive(client):
    async def two_at_once():
        import asyncio
        return await asyncio.gather(background.run_maintenance_once(), background.run_maintenance_once())

    assert sorted(run(client, two_at_once)) == [False, True]
