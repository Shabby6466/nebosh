"""Prometheus metrics, exposed at /metrics (blocked from the internet by nginx).

With several uvicorn workers, set PROMETHEUS_MULTIPROC_DIR (the Dockerfile
does) so a scrape aggregates every worker instead of hitting a random one.
"""
import os
import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
# Time a frame/KYC job waits for a free inference thread — the first signal
# that a worker is saturated and more workers/instances are needed.
INFERENCE_QUEUE_WAIT = Histogram(
    "inference_queue_wait_seconds", "Wait for a free inference thread",
    buckets=(0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
FRAME_INFERENCE = Histogram(
    "frame_inference_seconds", "Model time per proctoring frame",
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1, 1.5, 2, 3, 5),
)
FRAMES = Counter("frames_evaluated_total", "Proctoring frames evaluated", ["mode", "violation"])
VIOLATIONS = Counter("violations_recorded_total", "Violations recorded (after debounce)", ["type"])
KYC = Counter("kyc_verifications_total", "KYC verifications", ["outcome"])
WEBHOOKS = Counter("webhook_delivery_attempts_total", "Webhook delivery attempts", ["outcome"])
SESSIONS_ENDED = Counter("sessions_ended_total", "Sessions ended", ["status"])
WS_CONNECTIONS = Gauge("ws_connections", "Open proctoring WebSockets", multiprocess_mode="livesum")


def render() -> tuple[bytes, str]:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


class MetricsMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware) so it adds no per-request task and
    leaves WebSockets alone. Labels by route template, not raw path, to keep
    UUIDs out of label cardinality."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        start = time.perf_counter()
        status = 500

        async def _send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            if route != "/metrics":
                HTTP_REQUESTS.labels(scope["method"], route, str(status)).inc()
                HTTP_LATENCY.labels(scope["method"], route).observe(time.perf_counter() - start)
