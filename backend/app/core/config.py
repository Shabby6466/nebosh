from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/proctoring"
    redis_url: str = "redis://localhost:6379/0"

    s3_bucket: str = "nebosh-proctoring"
    s3_region: str = "me-central-1"
    s3_endpoint_url: str | None = None  # set for DO Spaces / Wasabi / local MinIO
    s3_use_kms_encryption: bool = True  # disable for local MinIO without KMS configured
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    face_match_threshold: float = 0.38   # cosine similarity, ArcFace embeddings
    liveness_threshold: float = 0.5
    person_conf_threshold: float = 0.5
    violation_debounce_frames: int = 2   # consecutive positive frames before flagging

    max_frame_dim_px: int = 640

    class Config:
        env_file = ".env"


settings = Settings()
