"""S3-compatible object storage for ID scans, selfies, and violation snapshots."""
from __future__ import annotations

import uuid
from datetime import datetime

import boto3
import cv2
import numpy as np
from botocore.config import Config

from app.core.config import settings

# Path-style addressing is required for MinIO/local dev (no wildcard DNS for
# virtual-hosted-style buckets); real AWS S3 works fine with either.
_s3 = boto3.client(
    "s3",
    region_name=settings.s3_region,
    endpoint_url=settings.s3_endpoint_url or None,
    aws_access_key_id=settings.aws_access_key_id or None,
    aws_secret_access_key=settings.aws_secret_access_key or None,
    config=Config(s3={"addressing_style": "path"}) if settings.s3_endpoint_url else None,
)

# SSE-KMS requires a KMS-backed store (real AWS S3, or MinIO configured with
# its own KMS integration) — disable for local MinIO without KMS set up.
_encryption_kwargs = {"ServerSideEncryption": "aws:kms"} if settings.s3_use_kms_encryption else {}


def upload_image(image_bgr: np.ndarray, prefix: str, ext: str = "jpg") -> str:
    """Encode and upload an image; returns the S3 object key."""
    ok, buf = cv2.imencode(f".{ext}", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError("Failed to encode image")

    key = f"{prefix}/{datetime.utcnow():%Y/%m/%d}/{uuid.uuid4()}.{ext}"
    _s3.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=buf.tobytes(),
        ContentType=f"image/{ext}",
        **_encryption_kwargs,
    )
    return key


def upload_raw(data: bytes, prefix: str, content_type: str, ext: str) -> str:
    key = f"{prefix}/{datetime.utcnow():%Y/%m/%d}/{uuid.uuid4()}.{ext}"
    _s3.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
        **_encryption_kwargs,
    )
    return key


def signed_url(key: str, expires_in: int = 3600) -> str:
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_in,
    )
