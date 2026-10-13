from pathlib import Path

import boto3
from botocore.config import Config

from .config import settings


def client():
    s = settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        config=Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 2}),
    )


def path(key):
    root = Path(settings().local_storage_path).resolve()
    candidate = (root / key).resolve()
    if root not in candidate.parents:
        raise ValueError("Invalid object key")
    return candidate


def put(key, data):
    if settings().storage_mode == "local":
        dest = path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    else:
        client().put_object(Bucket=settings().s3_bucket, Key=key, Body=data)


def get(key):
    if settings().storage_mode == "local":
        return path(key).read_bytes()
    return client().get_object(Bucket=settings().s3_bucket, Key=key)["Body"].read()


def remove(key):
    if settings().storage_mode == "local":
        path(key).unlink(missing_ok=True)
    else:
        client().delete_object(Bucket=settings().s3_bucket, Key=key)
