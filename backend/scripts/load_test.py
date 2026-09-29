"""Load test: N simulated learners, each doing the real partner flow and then
streaming webcam frames over the proctoring WebSocket.

Per learner: create candidate (API key) -> mint session token -> KYC (3 photos)
-> start session -> connect WS -> send a frame every --interval seconds for
--duration -> end session. Reports frame round-trip latency and throughput.

Run it against staging, never production (it creates real candidates/sessions).
The KYC/frame photos must be of one real person, so KYC passes and frames
match; any volunteer's photos work (every simulated learner reuses them):

    python scripts/load_test.py --base-url https://api-staging.example.com \\
        --api-key $STAGING_KEY --learners 100 --interval 7 --duration 300 \\
        --id-photo id.jpg --selfie selfie.jpg --hold-id-photo hold.jpg --frame frame.jpg

Reading the result: the system keeps up while p95 latency stays well under
--interval and received ~= sent. When p95 approaches the interval, frames
queue up per worker; add workers/instances (see README "Capacity & sizing").
"""
import argparse
import asyncio
import json
import statistics
import time
import uuid
from collections import Counter
from pathlib import Path

import httpx
import websockets


class Stats:
    def __init__(self):
        self.latencies: list[float] = []
        self.sent = 0
        self.errors: Counter[str] = Counter()
        self.violations: Counter[str] = Counter()
        self.setup_failed = 0


async def learner(i: int, args, http: httpx.AsyncClient, stats: Stats, photos: dict, start_at: float):
    await asyncio.sleep(max(0.0, start_at - time.monotonic()))
    key = {"X-API-Key": args.api_key}
    try:
        cand = (await http.post("/api/v1/candidates", headers=key, json={
            "full_name": f"Load Test {i}", "email": f"loadtest-{uuid.uuid4().hex[:12]}@example.com",
            "cnic_or_passport_no": "00000-0000000-0",
        })).raise_for_status().json()
        token = (await http.post("/api/v1/auth/token", headers=key, json={
            "candidate_id": cand["id"], "expires_minutes": 240,
        })).raise_for_status().json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        kyc = (await http.post(f"/api/v1/kyc/verify?candidate_id={cand['id']}", headers=auth, files={
            "id_document": ("id.jpg", photos["id"], "image/jpeg"),
            "selfie": ("selfie.jpg", photos["selfie"], "image/jpeg"),
            "hold_id_photo": ("hold.jpg", photos["hold"], "image/jpeg"),
        })).raise_for_status().json()
        if not kyc["verified"]:
            raise RuntimeError(f"KYC not verified ({kyc['reason']}) — use photos of one real person")

        session = (await http.post("/api/v1/sessions", headers=auth, json={
            "candidate_id": cand["id"], "exam_code": "LOADTEST", "mode": args.mode,
        })).raise_for_status().json()
    except Exception as exc:
        stats.setup_failed += 1
        stats.errors[f"setup: {str(exc)[:80]}"] += 1
        return

    ws_url = args.base_url.replace("http", "ws", 1) + f"/ws/v1/sessions/{session['id']}?token={token}"
    deadline = time.monotonic() + args.duration
    try:
        async with websockets.connect(ws_url, max_size=2**20, open_timeout=30) as ws:
            # Stagger within the interval so learners don't all send in lockstep
            await asyncio.sleep((i * 0.37) % args.interval)
            while time.monotonic() < deadline:
                t0 = time.monotonic()
                await ws.send(photos["frame"])
                stats.sent += 1
                try:
                    reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=args.interval * 4))
                except asyncio.TimeoutError:
                    stats.errors["frame timeout"] += 1
                    continue
                stats.latencies.append(time.monotonic() - t0)
                if "error" in reply:
                    stats.errors[reply["error"]] += 1
                else:
                    stats.violations[reply.get("violation") or "none"] += 1
                await asyncio.sleep(max(0.0, args.interval - (time.monotonic() - t0)))
    except Exception as exc:
        stats.errors[f"ws: {type(exc).__name__}: {str(exc)[:60]}"] += 1
    finally:
        await http.post(f"/api/v1/sessions/{session['id']}/end", headers=auth)


def pct(values: list[float], p: float) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[p - 1] if len(values) >= 2 else (values[0] if values else 0.0)


async def main(args):
    photos = {
        "id": Path(args.id_photo).read_bytes(),
        "selfie": Path(args.selfie).read_bytes(),
        "hold": Path(args.hold_id_photo).read_bytes(),
        "frame": Path(args.frame).read_bytes(),
    }
    stats = Stats()
    limits = httpx.Limits(max_connections=args.learners + 10)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=120, limits=limits) as http:
        t0 = time.monotonic()
        await asyncio.gather(*(
            learner(i, args, http, stats, photos, t0 + args.ramp * i / max(1, args.learners))
            for i in range(args.learners)
        ))
        elapsed = time.monotonic() - t0

    lat = sorted(stats.latencies)
    offered = (args.learners - stats.setup_failed) / args.interval
    print(f"\nlearners={args.learners} interval={args.interval}s duration={args.duration}s mode={args.mode}")
    print(f"setup failures: {stats.setup_failed}")
    print(f"frames sent={stats.sent} answered={len(lat)}  offered load ~{offered:.1f} frames/s, "
          f"achieved {len(lat) / max(1e-9, elapsed - args.ramp):.1f} frames/s")
    if lat:
        print(f"latency  p50={pct(lat, 50):.2f}s  p95={pct(lat, 95):.2f}s  p99={pct(lat, 99):.2f}s  max={lat[-1]:.2f}s")
    print(f"violations: {dict(stats.violations)}")
    if stats.errors:
        print(f"errors: {dict(stats.errors)}")
    ok = lat and pct(lat, 95) < args.interval * 0.5 and not stats.errors
    print("RESULT:", "OK — keeping up" if ok else "SATURATED or ERRORS — see above")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", required=True)
    p.add_argument("--api-key", required=True)
    p.add_argument("--learners", type=int, default=100)
    p.add_argument("--interval", type=float, default=7.0, help="seconds between frames per learner")
    p.add_argument("--duration", type=float, default=300.0, help="streaming seconds per learner")
    p.add_argument("--ramp", type=float, default=30.0, help="seconds to spread learner starts over")
    p.add_argument("--mode", choices=["exam", "interview"], default="exam")
    p.add_argument("--id-photo", required=True)
    p.add_argument("--selfie", required=True)
    p.add_argument("--hold-id-photo", required=True)
    p.add_argument("--frame", required=True, help="a typical webcam frame (JPEG, ~640x480)")
    asyncio.run(main(p.parse_args()))
