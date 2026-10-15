"""Initialize the configured S3 bucket before API and worker startup."""

from botocore.exceptions import ClientError

from .config import settings
from .storage import client


def ensure_bucket():
    bucket = settings().s3_bucket
    storage = client()
    try:
        storage.head_bucket(Bucket=bucket)
        return
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchBucket", "NotFound"}:
            raise

    try:
        storage.create_bucket(Bucket=bucket)
    except ClientError as error:
        # Another initializer may have created our bucket after head_bucket.
        if error.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
            raise


if __name__ == "__main__":
    ensure_bucket()
    print("Object storage bucket is ready.")
