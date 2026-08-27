# NEBOSH/IOSH Remote Proctoring Platform — Architecture

Automated candidate KYC + continuous exam proctoring for online NEBOSH/IOSH sessions
in Pakistan. Optimized for low-spec webcams (480p/720p) and constrained bandwidth.

## 1. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | **React + TypeScript (Vite)**, `react-webcam`, MediaPipe FaceMesh (WASM, client-side) | Client-side liveness/face-presence pre-checks avoid uploading dead frames; MediaPipe runs at 30fps even on low-end laptops |
| Client CV (in-browser) | **MediaPipe FaceLandmarker (WASM)** or `face-api.js` (TinyFaceDetector) | Cheap presence/blink/gaze check before deciding whether to even send a frame to the server |
| Backend API | **FastAPI (Python 3.11)** + Uvicorn/Gunicorn workers | Async I/O for webcam frame ingestion, native fit with the CV/ML stack (no Node↔Python bridge) |
| Task queue | **Celery + Redis** (or RQ) | Frame evaluation (face match + person detection) is CPU/GPU-bound — must not block the request thread |
| Face recognition | **InsightFace (buffalo_l, ArcFace embeddings, ONNXRuntime)** | More accurate & faster than DeepFace's default backends at 480p; embeddings are 512-d, portable, CPU-friendly with ONNX |
| Liveness detection | **Silent-Face-Anti-Spoofing (MiniFASNet, ONNX)** for server-side re-check + client-side active liveness (blink/head-turn prompt via MediaPipe) | Defense in depth: client active challenge (hard to spoof with a photo) + server passive check (catches replay/screen attacks even if client is bypassed) |
| Person detection | **YOLOv8n (Ultralytics, exported to ONNX, `person` class only)** | Nano variant runs real-time on CPU; ONNXRuntime avoids pulling in full PyTorch on inference nodes |
| Database (relational) | **PostgreSQL 15 + pgvector** | pgvector gives native ANN cosine-similarity search on face embeddings, transactional consistency with candidate/session records |
| Object/blob storage | **S3-compatible (AWS S3, or DigitalOcean Spaces / Wasabi for lower egress cost in PK)** | Violation snapshots, ID scans, selfies — never store binary blobs in Postgres |
| Cache / pub-sub | **Redis** | Celery broker + short-lived session state (last-seen frame timestamp, current flag counters) |
| Auth | **JWT (candidate) + OAuth2/JWT (admin, role-based)** | Standard, stateless, works behind CDN |
| Realtime transport | **WebSocket** (`/ws/session/{id}`) for frame streaming + flag push to dashboard | Lower overhead than polling REST for a 5–10s cadence over possibly-flaky connections |
| Infra | Docker Compose (dev) → Kubernetes or a single beefy VM w/ GPU-optional inference (prod) | ONNX models run fine on CPU; add a GPU node only if candidate volume requires it |
| Monitoring | Prometheus + Grafana, Sentry for errors | Track flag rates, frame-processing latency, queue depth |

**Why InsightFace over DeepFace for this use case:** DeepFace is a convenient wrapper but its default pipeline (retinaface + VGG-Face/Facenet) is heavier and slower per frame than InsightFace's ArcFace ONNX models, which matters when you're evaluating a frame every 5–10s per active candidate at scale. DeepFace is referenced below because the prompt asks for it explicitly and it's a fine choice for a first prototype (fewer moving parts), with a clear upgrade path to InsightFace noted.

## 2. High-Level Flow

```
Candidate Browser                FastAPI Backend                 Workers/Storage
------------------               ----------------                ----------------
1. Upload ID + selfie  ────────▶ POST /kyc/verify
                                    - decode images
                                    - detect+align faces
                                    - liveness check (selfie)
                                    - InsightFace embed both
                                    - cosine similarity match
                                    - store embedding (pgvector)
                                    - store ID+selfie in S3
                                 ◀── verified / rejected + score

2. Exam starts          ────────▶ WS /ws/session/{id} connect
   client captures frame
   every 5-10s (canvas.toBlob,
   JPEG q=0.5, downscaled)
                        ────────▶ frame binary over WS
                                    - enqueue Celery task
                                    - fast path: person count (YOLOv8n)
                                    - face embed + compare vs stored vector
                                    - if flag: save snapshot to S3,
                                      write violation row
                                 ◀── ack / flag event over WS
   client shows local
   feedback (face not
   in frame, etc.)

3. Admin dashboard      ────────▶ GET /admin/candidates
                                 GET /admin/sessions/{id}/violations
                                 (signed S3 URLs for snapshots)
```

## 3. Database Schema

See [`db/schema.sql`](db/schema.sql). Summary:

- `candidates` — identity + KYC status
- `face_embeddings` — one row per candidate, `vector(512)` via pgvector, versioned so re-KYC doesn't lose history
- `exam_sessions` — one row per exam attempt
- `session_frames` — optional lightweight log of processed frames (rolling retention, not every frame kept)
- `violations` — flagged events with type, confidence, S3 snapshot key, timestamp
- `admins` — dashboard users with roles (`reviewer`, `compliance_officer`, `admin`)

## 4. API Endpoints (REST + WS)

### KYC / Registration
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/candidates` | Create candidate record (name, CNIC/passport no., email, exam booking ref) |
| POST | `/api/v1/kyc/verify` | Multipart upload: `id_document`, `selfie` → runs liveness + 1:1 match, stores embedding |
| GET | `/api/v1/kyc/{candidate_id}/status` | Poll verification status/result |

### Session Proctoring
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/sessions` | Start an exam session for a verified candidate |
| WS | `/ws/v1/sessions/{session_id}` | Streams frames up, flag events down |
| POST | `/api/v1/sessions/{session_id}/frame` | REST fallback if WS unavailable (multipart JPEG) |
| POST | `/api/v1/sessions/{session_id}/end` | Close session, finalize summary |
| GET | `/api/v1/sessions/{session_id}/summary` | Violation counts, trust score |

### Admin / Compliance
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/admin/candidates` | List + filter by verification status |
| GET | `/api/v1/admin/sessions/{id}/violations` | Timestamped violation log with signed snapshot URLs |
| POST | `/api/v1/admin/violations/{id}/review` | Mark reviewed (false positive / confirmed) |
| GET | `/api/v1/admin/candidates/{id}/audit-log` | Full audit trail for compliance export |

Full OpenAPI schema is auto-generated by FastAPI at `/docs` once the app runs.

## 5. Code

- [`backend/app/services/face_service.py`](backend/app/services/face_service.py) — embedding, matching, liveness
- [`backend/app/services/person_detector.py`](backend/app/services/person_detector.py) — YOLOv8n person counting
- [`backend/app/services/storage.py`](backend/app/services/storage.py) — S3 upload + signed URLs
- [`backend/app/routers/kyc.py`](backend/app/routers/kyc.py) — KYC endpoint
- [`backend/app/routers/proctoring.py`](backend/app/routers/proctoring.py) — real-time frame evaluation (WS + REST fallback)
- [`backend/app/models.py`](backend/app/models.py) — SQLAlchemy models
- [`backend/app/schemas.py`](backend/app/schemas.py) — Pydantic request/response models

Run locally:
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d postgres redis   # or point at existing instances
alembic upgrade head                  # or run db/schema.sql directly
celery -A app.worker worker --loglevel=info &
uvicorn app.main:app --reload
```

## 6. Low-Bandwidth / Low-Spec Webcam Best Practices

**Client-side (biggest lever — most savings happen before a byte leaves the browser):**
- Run MediaPipe FaceLandmarker (WASM, ~2MB) locally at low cost; only trigger a server upload when a face is actually present, roughly centered, and not obviously a photo of a photo (basic texture/moire heuristic). Skip the upload entirely on frames with no face — send a lightweight "no-face" event instead of a JPEG.
- Downscale before encode: capture at native resolution but draw to an offscreen `<canvas>` at 320×240–480×360 for the analysis frame; the visible preview can stay higher-res for the candidate.
- Encode as JPEG quality 0.4–0.6, not PNG. A 320×240 JPEG at q=0.5 is typically 8–20KB — at a 7s cadence that's ~1.5–3 KB/s average, workable on a 3G/weak broadband link common outside Karachi/Lahore metro areas.
- Adaptive cadence: widen the interval (e.g., 5s → 15s) automatically when `navigator.connection.downlink` or measured RTT indicates a poor link (Network Information API, with a manual fallback timer-based RTT probe since Safari doesn't support it), and tighten it after any flag.
- Buffer-and-retry: if a frame upload fails, don't block the exam UI — queue up to N frames locally (with timestamps) and flush on reconnect, capped so memory doesn't grow unbounded. WS with exponential backoff reconnect.
- Local pre-flight liveness challenge (one-time at KYC and randomly during the session): "blink" or "turn head" prompt validated client-side via landmark motion before ever hitting the server — cuts server liveness compute and catches photo spoofing early.

**Server-side:**
- Run YOLOv8n and InsightFace as ONNXRuntime sessions (not full PyTorch) — smaller memory footprint, faster cold start, easier to horizontally scale on CPU-only instances, which are cheaper to host and don't need GPU availability in-region.
- Batch-friendly worker pool: Celery workers pull from Redis; size worker concurrency to CPU cores, and process person-detection + face-match for a frame in a single task to avoid two decode passes.
- Downsample server-side too as a safety net (cap incoming frame at 480p max, reject/resize anything larger) — protects against a candidate on a good connection sending unnecessarily large frames.
- Store only violation snapshots + a periodic "heartbeat" thumbnail (e.g., every 60s) in S3, not every evaluated frame — keeps storage/egress cost down while preserving an audit trail.
- Use S3 lifecycle rules to move snapshots to cold/infrequent-access storage after the exam review window (e.g., 90 days) per your compliance retention policy.
- Terminate WebSockets at a layer that supports idle-timeout/backpressure (e.g., behind an ALB or nginx with proxy_read_timeout tuned) so a stalled client doesn't hold a worker slot.

## 7. Accuracy / Anti-Spoofing Notes

- 1:1 match threshold: start at cosine similarity ≥ 0.35–0.40 for ArcFace embeddings (tune on a labeled validation set of PK candidate photos — lighting/webcam quality shifts the ideal threshold); log the raw score even on pass so you can retune later.
- Liveness must combine **client active challenge** (blink/turn, hard to fake with a static photo) and **server passive check** (MiniFASNet or similar, catches phone/tablet replay and printed photo attacks) — neither alone is sufficient.
- Multiple-person flags should debounce (e.g., require 2 consecutive positive frames before flagging) to avoid false positives from someone briefly walking past a webcam's field of view.
- Every flag must be reviewable by a human before it affects exam validity — this system should generate an audit trail and trust score, not auto-fail candidates, both for fairness and to stay defensible if a candidate disputes a result.

## 8. Data Protection

Government ID images, selfies, and face embeddings are sensitive biometric data. In Pakistan this sits under evolving PECA/data-protection guidance and NEBOSH/IOSH's own data-handling requirements as an accreditation body — before going to production, confirm retention periods and cross-border storage restrictions with legal counsel, encrypt biometric data at rest (KMS-managed keys, not app-level static keys), and restrict embedding-table access to the KYC service role only, not the general app DB user.
