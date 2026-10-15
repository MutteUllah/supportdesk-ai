from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from app import init_storage


def s3_error(code, operation):
    return ClientError({"Error": {"Code": code, "Message": "Test failure"}}, operation)


def storage_client(monkeypatch):
    storage = Mock()
    monkeypatch.setattr(init_storage, "client", lambda: storage)
    return storage


def test_existing_bucket_does_not_create_again(monkeypatch):
    storage = storage_client(monkeypatch)
    init_storage.ensure_bucket()
    storage.head_bucket.assert_called_once_with(Bucket="supportdesk")
    storage.create_bucket.assert_not_called()


def test_absent_bucket_is_created(monkeypatch):
    storage = storage_client(monkeypatch)
    storage.head_bucket.side_effect = s3_error("404", "HeadBucket")
    init_storage.ensure_bucket()
    storage.create_bucket.assert_called_once_with(Bucket="supportdesk")


def test_inaccessible_bucket_fails_without_creating(monkeypatch):
    storage = storage_client(monkeypatch)
    storage.head_bucket.side_effect = s3_error("403", "HeadBucket")
    with pytest.raises(ClientError):
        init_storage.ensure_bucket()
    storage.create_bucket.assert_not_called()


def test_concurrent_creation_of_our_bucket_succeeds(monkeypatch):
    storage = storage_client(monkeypatch)
    storage.head_bucket.side_effect = s3_error("NoSuchBucket", "HeadBucket")
    storage.create_bucket.side_effect = s3_error("BucketAlreadyOwnedByYou", "CreateBucket")
    init_storage.ensure_bucket()


def test_conflicting_bucket_creation_fails(monkeypatch):
    storage = storage_client(monkeypatch)
    storage.head_bucket.side_effect = s3_error("NotFound", "HeadBucket")
    storage.create_bucket.side_effect = s3_error("BucketAlreadyExists", "CreateBucket")
    with pytest.raises(ClientError):
        init_storage.ensure_bucket()
