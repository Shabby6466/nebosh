import asyncio
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core import metrics
from app.core.config import settings
from app.core.redis import redis_client
from app.database import SessionLocal
from app.routers import admin, auth, candidates, kyc, partner, proctoring, vendors
from app.services import background
from app.services.storage import check_bucket

if settings.sentry_dsn:
    # FastAPI/Starlette integrations are enabled automatically. PII (IPs,
    # headers, bodies) is not sent: send_default_pii stays off.
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tasks = background.start() if settings.background_jobs_enabled else []
    yield
    await background.stop(tasks)


_docs = settings.api_docs_enabled
app = FastAPI(
    title="Proctoring API",
    version="1.0.0",
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
    lifespan=lifespan,
)

_allowed_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(metrics.MetricsMiddleware)

app.include_router(auth.router)
app.include_router(candidates.router)
app.include_router(partner.router)
app.include_router(kyc.router)
app.include_router(proctoring.router)
app.include_router(admin.router)
app.include_router(vendors.router)


@app.get("/health")
async def health():
    """Liveness: the process is up. Used by the Docker healthcheck, so it must
    not depend on Postgres/Redis/S3 — a DB blip shouldn't restart the API."""
    return {"status": "ok"}


@app.get("/health/ready")
async def ready(response: Response):
    """Readiness: dependencies reachable. For load balancers / uptime checks."""

    async def _db():
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))

    checks = {"database": _db(), "redis": redis_client.ping(), "storage": asyncio.to_thread(check_bucket)}
    results = await asyncio.gather(
        *(asyncio.wait_for(c, timeout=3) for c in checks.values()), return_exceptions=True
    )
    status = {name: "ok" if not isinstance(r, BaseException) else "error" for name, r in zip(checks, results)}
    healthy = "error" not in status.values()
    if not healthy:
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "checks": status}


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    body, content_type = metrics.render()
    return Response(body, media_type=content_type)
