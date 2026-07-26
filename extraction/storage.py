"""Object storage — document bytes in S3 / MinIO (Phase A3).

Replaces app_data/uploads. The API uploads document bytes here; the Celery
worker reads them back to run the pipeline. The same code targets MinIO locally
(S3_ENDPOINT_URL set) and real AWS S3 in prod (endpoint unset).

Key scheme:  claims/{claim_id}/documents/{filename}
"""

import os

import boto3
from botocore.config import Config

from logging_setup import get_logger

log = get_logger("storage")

S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")     # None => real AWS S3
S3_BUCKET = os.environ.get("S3_BUCKET", "claimbridge")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")

_client = None


def client():
    """Lazily build the S3 client (boto3.client does not open a connection)."""
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name=S3_REGION,
            config=Config(signature_version="s3v4"),
        )
    return _client


def ensure_bucket() -> None:
    """Create the bucket if missing (best-effort; minio-init usually did it)."""
    c = client()
    try:
        c.head_bucket(Bucket=S3_BUCKET)
    except Exception:
        c.create_bucket(Bucket=S3_BUCKET)
        log.info("created bucket %s", S3_BUCKET)


def document_key(cid: str, filename: str) -> str:
    return f"claims/{cid}/documents/{filename}"


def put_bytes(key: str, data: bytes, content_type: str | None = None) -> None:
    extra = {"ContentType": content_type} if content_type else {}
    client().put_object(Bucket=S3_BUCKET, Key=key, Body=data, **extra)
    log.info("put %s (%d bytes)", key, len(data))


def get_bytes(key: str) -> bytes:
    obj = client().get_object(Bucket=S3_BUCKET, Key=key)
    data = obj["Body"].read()
    log.info("get %s (%d bytes)", key, len(data))
    return data


def presigned_get_url(key: str, expires: int = 900) -> str:
    """A time-limited download URL. Used for real-S3 direct download in prod; in
    local MinIO the `minio` hostname isn't browser-resolvable, so the preview
    endpoint streams bytes through the API instead of redirecting here."""
    return client().generate_presigned_url(
        "get_object", Params={"Bucket": S3_BUCKET, "Key": key}, ExpiresIn=expires)
