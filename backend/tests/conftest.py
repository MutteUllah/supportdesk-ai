import os
import tempfile
from pathlib import Path

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", "sqlite:///" + str(Path(tempfile.mkdtemp()) / "tests.db")
)
os.environ["STORAGE_MODE"] = "local"
os.environ["LOCAL_STORAGE_PATH"] = tempfile.mkdtemp()
os.environ["MODEL_MODE"] = "mock"
os.environ["TEST_INLINE_JOBS"] = "true"
os.environ["TEST_MEMORY_RATE_LIMIT"] = "true"
os.environ["EMBEDDING_DIMENSIONS"] = "128"
os.environ["RETRIEVAL_MAX_DISTANCE"] = "0.95"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.security import memory_limits  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    if engine.dialect.name == "postgresql":
        with engine.begin() as db:
            db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    memory_limits.clear()
    yield


def account(email="owner@example.com"):
    c = TestClient(app)
    c.headers["Origin"] = "http://localhost:3000"
    result = c.post("/auth/register", json={"email": email, "password": "Test-password-123!"})
    assert result.status_code == 200, result.text
    c.headers["X-CSRF-Token"] = result.json()["csrf"]
    return c


@pytest.fixture
def owner():
    return account()


@pytest.fixture
def workspace(owner):
    return owner.post("/workspaces", json={"name": "Northstar"}).json()


def upload(c, wid, text="Shipping takes 3 days. Returns accepted within 30 days."):
    r = c.post(
        f"/workspaces/{wid}/documents",
        files={"file": ("policy.md", text.encode(), "text/markdown")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def conversation(c, wid):
    return c.post(f"/workspaces/{wid}/conversations").json()["id"]


def send(c, wid, cid, text="How long does shipping take?", key="request-123", **extra):
    return c.post(
        f"/workspaces/{wid}/conversations/{cid}/chat",
        json={"text": text, "request_key": key, **extra},
    )
