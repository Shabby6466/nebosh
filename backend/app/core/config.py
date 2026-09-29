from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/proctoring"
    redis_url: str = "redis://localhost:6379/0"

    s3_bucket: str = "nebosh-proctoring"
    s3_region: str = "me-central-1"
    s3_endpoint_url: str | None = None  # set for DO Spaces / Wasabi / local MinIO
    # Externally reachable URL of the same store, used only to presign download
    # links (e.g. "https://files.example.com"). SigV4 signs the host, so a URL
    # presigned against the internal Docker hostname can't be rewritten after
    # the fact. Leave unset when s3_endpoint_url is already public (or AWS S3).
    s3_public_endpoint_url: str | None = None
    s3_use_kms_encryption: bool = True  # disable for local MinIO without KMS configured
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    # Upper bound on a partner-requested session token lifetime. The WS only
    # checks the token at connect, but REST-fallback clients need it valid for
    # the whole session — longer sessions should re-mint rather than raise this.
    session_token_max_minutes: int = 240

    # Swagger UI / ReDoc / openapi.json. Off in production: partners get the
    # exported spec + integration guide instead of a public schema.
    api_docs_enabled: bool = True

    # Per-organization limit on API-key (server-to-server) calls, fixed 1-minute window.
    api_key_rate_limit_per_minute: int = 600

    webhook_timeout_s: float = 10.0
    # Backoff between attempts: 30s, 2m, 8m, 32m, ~2h, then every 6h (~17h total)
    webhook_max_attempts: int = 8

    # Background loops (webhook outbox + maintenance) run inside every API
    # worker; safe to run concurrently (SKIP LOCKED / advisory lock).
    background_jobs_enabled: bool = True
    # Active sessions with no frame/event for this long are marked abandoned.
    session_idle_timeout_minutes: int = 30
    # session_frames rows (per-frame metadata) and delivered webhooks are deleted
    # after this many days. Violations, snapshots and session results are kept.
    session_frames_retention_days: int = 30

    # Observability
    sentry_dsn: str | None = None
    sentry_environment: str = "production"
    sentry_traces_sample_rate: float = 0.0

    # Comma-separated list of origins allowed to call the API from a browser,
    # e.g. "https://learn.savefast.example.com". Empty = no cross-origin
    # browser access at all (server-to-server calls are unaffected by CORS).
    cors_allowed_origins: str = ""

    face_match_threshold: float = 0.38   # cosine similarity, ArcFace embeddings
    # Lower than face_match_threshold on purpose: this compares a live face against
    # a small, handheld, glare-prone printed photo on the CNIC (vs. a clean selfie),
    # which inherently scores lower with ArcFace even for a genuine match.
    hold_id_match_threshold: float = 0.22
    liveness_threshold: float = 0.5
    person_conf_threshold: float = 0.5
    violation_debounce_frames: int = 2   # consecutive positive frames before flagging

    # Head-pose / gaze thresholds (degrees / ratio)
    # yaw: left-right rotation  |  pitch: up-down tilt
    head_yaw_threshold: float = 25.0        # |yaw| > this → looking away (left/right)
    head_pitch_down_threshold: float = 20.0 # pitch < -this → looking down (notes)
    head_pitch_up_threshold: float = 30.0   # pitch > +this → looking up  (ceiling)
    gaze_deviation_threshold: float = 0.20  # |gaze_ratio - 0.5| > this → eyes flicked sideways

    max_frame_dim_px: int = 640

    # Concurrent inference calls per worker process (see services/inference.py)
    inference_threads: int = 2
    # Threads each ONNX model call may use; 0 = ONNX Runtime default (all cores).
    # See services/onnx_runtime.py for sizing.
    onnx_intra_op_threads: int = 0

    class Config:
        env_file = ".env"


settings = Settings()
