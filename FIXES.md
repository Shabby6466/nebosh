# Fixes before partner (LMS) integration

## Blockers
- [x] Sync `db/schema.sql` with the models (`session_frames` pose/gaze columns, missing `violation_type` values) + migration for existing DBs
- [x] Presign snapshot/KYC URLs against a public S3 endpoint, not the internal `http://minio:9000`
- [x] Move CPU-bound inference (InsightFace, YOLO, liveness) and blocking S3 uploads off the event loop
- [x] Move violation debounce streaks from in-process memory to Redis (works across workers, cleared on session end)

## Integration
- [x] Partner-facing results endpoints on API key, scoped to the caller's organization (session report, violations, signed snapshots)
- [x] Make candidate email unique per organization (not global); case-insensitive lookup
- [x] Cap `expires_minutes` when minting session tokens
- [x] Validate `/events` `type` against allowed values (400 instead of 500)
- [x] Stop evaluating WS frames once a session is ended
- [x] `mode: "interview"` on sessions — relax/disable `looking_away` for viva
- [x] Webhooks (KYC completed, session ended); populate `trust_score`, `client_ip`, `user_agent`
- [x] Disable or protect `/docs` and `/redoc` in production
- [x] Per-API-key rate limiting (nginx per-IP limit throttles partner backends)
- [ ] KYC: OCR the CNIC number/name and compare to `cnic_or_passport_no` (or document the limitation)

## Scale & ops
- [x] Durable webhook delivery (outbox table + worker) — current delivery is in-process with retries, lost on restart
- [x] API-key endpoint for the partner to end a session (today only the learner's browser token can; a closed tab leaves it `active`)
- [x] Load-test script + local sizing (1 worker, 8 cores: ~40 learners @ 7 s/frame; ONNX thread tuning +40%)
- [ ] Run `scripts/load_test.py` with 100 learners on staging (real server, real photos) and set worker/host count
- [x] Retention job for `session_frames`
- [x] Pagination on admin list endpoints
- [x] `/health` checks DB + Redis + storage
- [x] Error tracking and metrics (Sentry, Prometheus)
- [x] Tests for auth scoping, KYC, frame evaluation

## Handover
- [ ] Integration guide (auth flow, per-use-case flows, error codes, violation types, frame requirements, Zoom capture guidance)
- [ ] Export `openapi.json` for the partner
- [ ] Sandbox environment + test API key
