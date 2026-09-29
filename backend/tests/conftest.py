"""Test harness: real Postgres (schema from db/schema.sql, recreated per run),
fakeredis, in-memory S3 stubs, captured webhook HTTP. Face inference is
stubbed per-test via `frame_result`; test_frame_models.py runs the real models.

    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/proctoring_test \
        pytest

The database named in TEST_DATABASE_URL is DROPPED and recreated.
"""
import asyncio
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCHEMA = BACKEND.parent / "db" / "schema.sql"
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5433/proctoring_test"
)

os.environ.update(
    DATABASE_URL=TEST_DB_URL,
    JWT_SECRET="test-secret",
    API_DOCS_ENABLED="false",
    BACKGROUND_JOBS_ENABLED="false",  # tests drive the loops' functions directly
    CORS_ALLOWED_ORIGINS="",
)
os.chdir(BACKEND)  # model paths in services are relative to backend/
sys.path.insert(0, str(BACKEND))


def _create_database() -> None:
    import asyncpg

    dsn = TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://")
    db_name = dsn.rsplit("/", 1)[1]
    admin_dsn = dsn.rsplit("/", 1)[0] + "/postgres"

    async def go():
        admin = await asyncpg.connect(admin_dsn)
        await admin.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{db_name}"')
        await admin.close()

        conn = await asyncpg.connect(dsn)
        schema = SCHEMA.read_text()
        try:
            await conn.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
        except asyncpg.PostgresError:
            # No pgvector on this server: the app only reads/writes embeddings
            # (text-encoded by pgvector's SQLAlchemy type), so TEXT stands in.
            schema = schema.replace('CREATE EXTENSION IF NOT EXISTS "vector";', "")
            schema = schema.replace("vector(512)", "TEXT")
            schema = re.sub(r"CREATE INDEX idx_face_embeddings_vector[^;]*;", "", schema)
        await conn.execute(schema)
        await conn.close()

    asyncio.run(go())


_create_database()

# --- stubs, installed before the app is imported -----------------------------
import fakeredis.aioredis  # noqa: E402

import app.core.redis as core_redis  # noqa: E402

core_redis.redis_client = fakeredis.aioredis.FakeRedis()

import app.core.auth as core_auth  # noqa: E402
import app.services.violation_streaks as streaks  # noqa: E402

core_auth.redis_client = core_redis.redis_client
streaks._redis = core_redis.redis_client
streaks._BUMP = core_redis.redis_client.register_script(streaks._BUMP.script)

import httpx  # noqa: E402
import numpy as np  # noqa: E402

import app.services.webhooks as webhooks  # noqa: E402


class WebhookSink:
    """Captures outgoing webhook requests; `status` sets the response code."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status)


SINK = WebhookSink()
_RealAsyncClient = httpx.AsyncClient
webhooks.httpx.AsyncClient = lambda **kw: _RealAsyncClient(transport=httpx.MockTransport(SINK.handler), **kw)

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
import app.routers.kyc as kyc_router  # noqa: E402
import app.routers.proctoring as proctoring_router  # noqa: E402
import app.services.session_report as session_report  # noqa: E402
from app.schemas import FrameEvalResult  # noqa: E402

proctoring_router.upload_image = lambda img, prefix: f"{prefix}/snap.jpg"
kyc_router.upload_image = lambda img, prefix: f"{prefix}/img.jpg"
session_report.signed_url = lambda key: f"https://files.test/{key}?sig"
main.check_bucket = lambda: None

REFERENCE_EMBEDDING = np.ones(512, dtype=np.float32) / np.sqrt(512)
_DUMMY = np.zeros((8, 8, 3), np.uint8)
JPEG = b"\xff\xd8 not-decoded-by-stubs"  # stubs never decode; real-model tests use real images


class KycStub:
    verified = True

    def __call__(self, id_bytes, selfie_bytes, hold_bytes):
        v = self.verified
        return (_DUMMY, _DUMMY, _DUMMY, REFERENCE_EMBEDDING, v, 0.9 if v else 0.1, v, 0.7, v, 0.5)


class FrameStub:
    """Stands in for _analyze_frame: returns `violation` unless it's
    looking_away and the session mode disables that check."""

    violation: str | None = None

    def __init__(self):
        self.flags: list[bool] = []

    def __call__(self, image, reference, flag_looking_away):
        self.flags.append(flag_looking_away)
        v = self.violation
        if v == "looking_away" and not flag_looking_away:
            v = None
        return image, FrameEvalResult(
            person_count=1, face_match=True, face_similarity=0.8, liveness_pass=True,
            violation=v, processing_ms=5,
        ), 0.9


# Frames are posted as bytes that cv2 can't decode; bypass decoding for stubbed tests.
import cv2  # noqa: E402

_real_imdecode = cv2.imdecode


@pytest.fixture(scope="session")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset(client, monkeypatch):
    SINK.requests.clear()
    SINK.status = 200
    client.portal.call(core_redis.redis_client.flushall)
    sql("DELETE FROM webhook_deliveries")  # outbox rows left by earlier tests
    kyc = KycStub()
    frames = FrameStub()
    monkeypatch.setattr(kyc_router, "_run_kyc_checks", kyc)
    monkeypatch.setattr(proctoring_router, "_analyze_frame", frames)
    monkeypatch.setattr(
        proctoring_router.cv2, "imdecode",
        lambda arr, flags: _DUMMY if bytes(arr) == JPEG else _real_imdecode(arr, flags),
    )
    yield


@pytest.fixture
def kyc_stub():
    return kyc_router._run_kyc_checks


@pytest.fixture
def frame_stub():
    return proctoring_router._analyze_frame


@pytest.fixture
def sink():
    return SINK


def run(client, fn, *args):
    """Run an async function on the app's event loop (same DB pool/Redis)."""
    return client.portal.call(fn, *args)


async def _sql(query: str, *args):
    import asyncpg

    conn = await asyncpg.connect(TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        return await conn.fetch(query, *args)
    finally:
        await conn.close()


def sql(query: str, *args):
    return asyncio.run(_sql(query, *args))


@pytest.fixture(scope="session")
def admin_headers(client):
    import bcrypt

    sql(
        "INSERT INTO admins(email, password_hash, full_name, role) VALUES ('admin@example.com', $1, 'Admin', 'admin')",
        bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode(),
    )
    token = client.post("/api/v1/auth/admin/login", json={"email": "admin@example.com", "password": "pw"}).json()
    return {"Authorization": f"Bearer {token['access_token']}"}


@pytest.fixture
def make_org(client, admin_headers):
    def _make(webhook_url: str | None = "https://lms.test/hook"):
        org = client.post(
            "/api/v1/admin/organizations",
            json={"name": f"Org {uuid.uuid4().hex[:6]}", "webhook_url": webhook_url},
            headers=admin_headers,
        ).json()
        org["headers"] = {"X-API-Key": org["api_key"]}
        return org

    return _make


@pytest.fixture
def make_candidate(client):
    def _make(org, email: str | None = None):
        resp = client.post(
            "/api/v1/candidates",
            json={"full_name": "Learner", "email": email or f"{uuid.uuid4().hex[:8]}@test.com",
                  "cnic_or_passport_no": "35202-0000000-0"},
            headers=org["headers"],
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make


def token_for(client, org, candidate_id) -> dict:
    tok = client.post("/api/v1/auth/token", json={"candidate_id": candidate_id}, headers=org["headers"])
    assert tok.status_code == 200, tok.text
    return {"Authorization": f"Bearer {tok.json()['access_token']}"}


def kyc(client, candidate_id, headers):
    files = {k: ("x.jpg", JPEG, "image/jpeg") for k in ("id_document", "selfie", "hold_id_photo")}
    return client.post(f"/api/v1/kyc/verify?candidate_id={candidate_id}", files=files, headers=headers)


@pytest.fixture
def learner(client, make_org, make_candidate):
    """A KYC-verified learner: (org, candidate, session-token headers)."""
    org = make_org()
    cand = make_candidate(org)
    headers = token_for(client, org, cand["id"])
    assert kyc(client, cand["id"], headers).json()["verified"]
    return org, cand, headers


def start_session(client, cand, headers, mode="exam"):
    resp = client.post(
        "/api/v1/sessions", json={"candidate_id": cand["id"], "exam_code": "GIC1", "mode": mode}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def send_frames(client, session_id, headers, n):
    last = None
    for _ in range(n):
        last = client.post(
            f"/api/v1/sessions/{session_id}/frame", files={"frame": ("f.jpg", JPEG, "image/jpeg")}, headers=headers
        )
        assert last.status_code == 200, last.text
    return last.json()


def deliver_webhooks(client):
    return run(client, webhooks.deliver_due)
