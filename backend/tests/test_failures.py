import io
from datetime import timedelta
from types import SimpleNamespace

import pytest
from conftest import conversation
from fastapi import HTTPException
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from redis.exceptions import ConnectionError
from sqlalchemy import select

from app import security
from app.chat import verify_tool
from app.config import settings
from app.db import SessionLocal
from app.ingestion import extract
from app.models import Conversation, WidgetSession, now


def text_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 250 Td (Shipping takes 3 days.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_pdf_text_and_scanned_rejection():
    pages = extract(text_pdf(), "policy.pdf")
    assert pages[0][0] == 1 and "Shipping takes 3 days." in pages[0][1]
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(ValueError, match="No text found"):
        extract(out.getvalue(), "scanned.pdf")


def test_real_pdf_upload_indexed(owner, workspace):
    wid = workspace["id"]
    result = owner.post(
        f"/workspaces/{wid}/documents",
        files={"file": ("policy.pdf", text_pdf(), "application/pdf")},
    )
    assert result.status_code == 200
    doc = owner.get(f"/workspaces/{wid}/documents").json()[0]
    assert doc["versions"][0]["status"] == "ready"


def test_body_limit(owner, workspace):
    response = owner.post(
        f"/workspaces/{workspace['id']}/documents",
        content=b"x" * (settings().max_upload_bytes + 65537),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413


def test_tool_does_not_report_unverified_success(owner, workspace):
    wid = workspace["id"]
    cid = conversation(owner, wid)
    with SessionLocal() as db:
        state = {
            "mode": "ticket",
            "db": db,
            "conversation": db.get(Conversation, cid),
            "ticket": SimpleNamespace(id="missing-ticket"),
        }
        with pytest.raises(HTTPException) as error:
            verify_tool(state)
        assert error.value.status_code == 503
        assert "could not be verified" in error.value.detail


def test_redis_failure_fails_closed(monkeypatch):
    monkeypatch.setattr(settings(), "test_memory_rate_limit", False)

    def unavailable(*args, **kwargs):
        raise ConnectionError("private redis endpoint")

    monkeypatch.setattr(security.Redis, "from_url", unavailable)
    with pytest.raises(HTTPException) as error:
        security.rate_limit("auth:test", 20)
    assert error.value.status_code == 503
    assert "private" not in error.value.detail


def test_rate_limit_enforced():
    security.rate_limit("limited", 1)
    with pytest.raises(HTTPException) as error:
        security.rate_limit("limited", 1)
    assert error.value.status_code == 429


def test_visitor_expiry(owner, workspace):
    wid = workspace["id"]
    owner.patch(
        f"/workspaces/{wid}",
        json={
            "name": "Test",
            "bot_name": "Bot",
            "welcome": "Hello",
            "color": "#123456",
            "origins": ["http://localhost:3001"],
        },
    )
    session = owner.post(
        f"/public/{workspace['public_id']}/session", json={"origin": "http://localhost:3001"}
    ).json()
    with SessionLocal.begin() as db:
        db.scalar(select(WidgetSession)).expires_at = now() - timedelta(seconds=1)
    response = owner.get(
        "/visitor/conversations/" + session["conversation_id"],
        headers={"Authorization": "Bearer " + session["token"]},
    )
    assert response.status_code == 401


def test_demo_seed_is_reproducible(monkeypatch):
    from sqlalchemy import func

    from app.models import DocumentVersion, User, Workspace
    from app.seed import seed

    monkeypatch.setattr(settings(), "demo_password", "Seed-test-password-123!")
    seed()
    seed()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 2
        assert db.scalar(select(func.count()).select_from(Workspace)) == 2
        versions = db.scalars(select(DocumentVersion)).all()
        assert len(versions) == 2
        assert all(version.status == "ready" for version in versions)
